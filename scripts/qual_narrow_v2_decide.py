#!/usr/bin/env python3
"""Deterministically adjudicate QUALIFICATION_NARROW_V2 from frozen evidence.

The Markdown result is not a control plane.  This command verifies every
evidence-stage manifest and the cross-artifact hashes recorded by the extract
and arm audits, then emits the protocol's I/II/III decision as JSON.  It makes
no API calls and never edits a harness or run artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from doctouch_arms import require_clean_code_revision  # noqa: E402
from invoiceloop.fields import FIELDS  # noqa: E402
from invoiceloop.release_profile import parse_release_profile  # noqa: E402
from qual_doctouch_audit import validate_route_matrix  # noqa: E402

ROUND = "qual-narrow-v2-2026-08-23"
PROTOCOL = REPO / "docs" / "QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md"
EVIDENCE = REPO / "docs" / "evidence" / ROUND
GATING_FIELDS = frozenset({"invoice_number", "seller_name", "amount_due"})
AUTO_ROUTES = frozenset({"auto_accept", "auto_absent"})


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"不可读 JSON:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 顶层必须是 object:{path}")
    return payload


def verify_stage(stage: Path) -> dict[str, str]:
    """Verify a flat immutable evidence stage, including undeclared extras."""
    stage = Path(stage)
    manifest = stage / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ValueError(f"冻结 stage 缺 MANIFEST.sha256:{stage}")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, sep, name = line.partition("  ")
        name = name.strip()
        if (not sep or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
                or not name or Path(name).name != name):
            raise ValueError(f"非法 evidence manifest 行:{stage}:{line!r}")
        if name in entries:
            raise ValueError(f"evidence manifest 重复成员:{stage}:{name}")
        entries[name] = digest
    if not entries:
        raise ValueError(f"evidence manifest 为空:{stage}")
    actual = {path.name for path in stage.iterdir() if path.is_file()}
    expected = set(entries) | {"MANIFEST.sha256"}
    extra = sorted(actual - expected)
    missing = sorted(expected - actual)
    dirs = sorted(path.name for path in stage.iterdir() if path.is_dir())
    if extra or missing or dirs:
        raise ValueError(
            f"evidence stage 成员不闭合:{stage}:"
            f"missing={missing},extra={extra},dirs={dirs}")
    for name, expected_sha in entries.items():
        got = _sha(stage / name)
        if got != expected_sha:
            raise ValueError(
                f"evidence manifest 哈希不符:{stage.name}/{name}:"
                f"expected={expected_sha},actual={got}")
    return entries


def _wilson95(successes: int, total: int) -> list[float]:
    if total <= 0:
        raise ValueError("Wilson 区间分母必须为正")
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    center = p + z * z / (2 * total)
    margin = z * math.sqrt(
        p * (1 - p) / total + z * z / (4 * total * total))
    return [round(100 * (center - margin) / denominator, 1),
            round(100 * (center + margin) / denominator, 1)]


def all_gates_automatic(routes: Sequence[Mapping[str, Any]]) -> list[str]:
    """Documents whose three payment-gating fields all route automatically."""
    by_doc: dict[str, dict[str, str]] = defaultdict(dict)
    for row in routes:
        field = str(row.get("field"))
        if field in GATING_FIELDS:
            by_doc[str(row.get("doc_id"))][field] = str(row.get("route"))
    return sorted(
        doc_id for doc_id, slots in by_doc.items()
        if set(slots) == GATING_FIELDS
        and all(route in AUTO_ROUTES for route in slots.values())
    )


def evaluate(rescored: Mapping[str, Any],
             d_routes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply protocol sections 5 and 6 to already-audited measurements."""
    arms = rescored.get("arms")
    if not isinstance(arms, Mapping):
        raise ValueError("审计缺 rescored.arms")

    def overall(arm: str) -> Mapping[str, Any]:
        try:
            value = arms[arm]["metrics"]["ALL"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"审计缺 {arm}.metrics.ALL") from exc
        if not isinstance(value, Mapping):
            raise ValueError(f"{arm}.metrics.ALL 不是 object")
        return value

    a = overall("HAR-0001")
    b = overall("HAR-0021")
    c = overall("HAR-0021+payment(projection)")
    d = overall("HAR-0023")
    safety = d.get("zero_touch_release_safety")
    if not isinstance(safety, Mapping):
        raise ValueError("HAR-0023 缺 zero_touch_release_safety")
    n_docs = int(d["docs"])
    if any(int(row["docs"]) != n_docs for row in (a, b, c)):
        raise ValueError("四臂 ALL 文档数不一致")

    d_zero = int(d["zero_touch_docs"])
    c_zero = int(c["zero_touch_docs"])
    all_auto_ids = all_gates_automatic(d_routes)
    p = {
        "P1": {
            "expected": "A zero-touch = 0/200",
            "actual": int(a["zero_touch_docs"]),
            "passed": int(a["zero_touch_docs"]) == 0,
        },
        "P2": {
            "expected": "D zero-touch in [5%, 20%]",
            "actual": {"docs": d_zero, "n": n_docs,
                       "pct": round(100 * d_zero / n_docs, 1),
                       "wilson95_pct": _wilson95(d_zero, n_docs)},
            "passed": 0.05 <= d_zero / n_docs <= 0.20,
        },
        "P3": {
            "expected": "C zero-touch >= D zero-touch",
            "actual": {"C": c_zero, "D": d_zero},
            "passed": c_zero >= d_zero,
        },
        "P4": {
            "expected": "D all-arm silent_wrong <= B",
            "actual": {"D": int(d["silent_wrong"]),
                       "B": int(b["silent_wrong"])},
            "passed": int(d["silent_wrong"]) <= int(b["silent_wrong"]),
        },
        "P5": {
            "expected": "D zero-touch silent_wrong in [8,18] and error docs in [6,14]",
            "actual": {"silent_wrong": int(safety["silent_wrong"]),
                       "error_docs": int(safety["docs_with_release_error"])},
            "passed": (8 <= int(safety["silent_wrong"]) <= 18
                       and 6 <= int(safety["docs_with_release_error"]) <= 14),
        },
        "P6": {
            "expected": "D zero-touch unscored auto-accept slots in [0,6]",
            "actual": int(safety["unscored_auto_accept_slots"]),
            "passed": 0 <= int(safety["unscored_auto_accept_slots"]) <= 6,
        },
        "P7": {
            "expected": "three payment gates all automatic in [15%,19%]",
            "actual": {"docs": len(all_auto_ids), "n": n_docs,
                       "pct": round(100 * len(all_auto_ids) / n_docs, 1)},
            "passed": 0.15 <= len(all_auto_ids) / n_docs <= 0.19,
        },
    }
    workflow_pass = bool(p["P1"]["passed"] and p["P2"]["passed"]
                         and p["P3"]["passed"])
    safety_criteria = {
        "silent_absent_true": {
            "required": 0, "actual": int(safety["silent_absent_true"]),
            "passed": int(safety["silent_absent_true"]) == 0,
        },
        "silent_wrong": {
            "required": 0, "actual": int(safety["silent_wrong"]),
            "passed": int(safety["silent_wrong"]) == 0,
        },
        "unscored_auto_accept_slots": {
            "required": 0,
            "actual": int(safety["unscored_auto_accept_slots"]),
            "passed": int(safety["unscored_auto_accept_slots"]) == 0,
        },
    }
    safety_pass = all(rec["passed"] for rec in safety_criteria.values())
    reasons = []
    if not workflow_pass:
        reasons.append("workflow_effect_gate_failed")
    if not safety_criteria["silent_absent_true"]["passed"]:
        reasons.append("zero_touch_silent_absent_true_nonzero")
    if not safety_criteria["silent_wrong"]["passed"]:
        reasons.append("zero_touch_silent_wrong_nonzero")
    if not safety_criteria["unscored_auto_accept_slots"]["passed"]:
        reasons.append("zero_touch_unscored_auto_accept_nonzero")
    qualification_pass = workflow_pass and safety_pass
    return {
        "predictions": p,
        "workflow_effect": {
            "passed": workflow_pass,
            "zero_touch_docs": d_zero,
            "n_docs": n_docs,
            "zero_touch_pct": round(100 * d_zero / n_docs, 1),
            "wilson95_pct": _wilson95(d_zero, n_docs),
        },
        "safety_product_capability": {
            "passed": safety_pass,
            "zero_touch_docs": int(safety["zero_touch_docs"]),
            "gating_slots": int(safety["gating_slots"]),
            "docs_with_release_error": int(safety["docs_with_release_error"]),
            "criteria": safety_criteria,
        },
        "qualification": {
            "passed": qualification_pass,
            "status": "pass" if qualification_pass else "fail",
            "promotion": "allowed" if qualification_pass else "denied",
            "reason_codes": reasons,
        },
        "three_gate_all_automatic_doc_ids": all_auto_ids,
    }


def load_and_verify(evidence_root: Path, protocol_path: Path) -> dict[str, Any]:
    """Close the hash chain from frozen plan/extract through all three arms."""
    evidence_root = Path(evidence_root)
    protocol_path = Path(protocol_path)
    stages = ["plan", "extract", "arms", "analysis-audit",
              "source-har-0001", "source-har-0021", "source-har-0023"]
    stage_entries = {stage: verify_stage(evidence_root / stage)
                     for stage in stages}

    plan = evidence_root / "plan"
    frozen_protocol = plan / protocol_path.name
    if frozen_protocol.name not in stage_entries["plan"]:
        raise ValueError("plan manifest 缺协议副本")
    if not protocol_path.is_file() or protocol_path.read_bytes() != \
            frozen_protocol.read_bytes():
        raise ValueError("live 协议与冻结 plan 协议不一致")

    extract = _json(evidence_root / "extract" / "extract_audit.json")
    if (not extract.get("complete") or extract.get("blocking_level") != "none"
            or extract.get("n_docs") != 200
            or extract.get("expected_calls") != 400
            or extract.get("stored_calls") != 400
            or extract.get("http_status_counts") != {"200": 400}
            or any(extract.get(key) for key in
                   ("missing", "extra", "malformed", "binding_errors"))
            or extract.get("qualification_identity_error") is not None):
        raise ValueError("冻结 extraction audit 未完整通过")
    identity_path = evidence_root / "extract" / "qualification_run_identity.json"
    identity = _json(identity_path)
    if (extract.get("qualification_run_identity") != identity
            or extract.get("qualification_run_identity_sha256") != _sha(identity_path)):
        raise ValueError("extraction audit 与 qualification identity 不一致")
    plan_manifest = plan / "MANIFEST.sha256"
    if (identity.get("plan_manifest_sha256") != _sha(plan_manifest)
            or identity.get("protocol_sha256") != _sha(protocol_path)
            or identity.get("round") != ROUND
            or identity.get("context") != "qual-narrow-v2"):
        raise ValueError("qualification identity 没有绑定当前冻结 plan/protocol")

    metrics_path = evidence_root / "arms" / "doctouch_metrics.json"
    audit_path = evidence_root / "analysis-audit" / "doctouch_audit.json"
    audit = _json(audit_path)
    if (not audit.get("complete") or audit.get("blocking_level") != "none"
            or audit.get("legacy_metric_drift")
            or audit.get("n_docs") != 200
            or audit.get("legacy_metrics_sha256") != _sha(metrics_path)
            or audit.get("extract_audit_sha256") !=
            _sha(evidence_root / "extract" / "extract_audit.json")
            or audit.get("doc_list_sha256") !=
            _sha(evidence_root / "plan" / "doc_list.json")):
        raise ValueError("冻结 doctouch audit 未完整通过或哈希链断裂")

    source_revisions = set()
    for arm in ("HAR-0001", "HAR-0021", "HAR-0023"):
        stage = evidence_root / f"source-{arm.lower()}"
        source = (audit.get("source_arms") or {}).get(arm) or {}
        expected = {
            "arm_identity.json": source.get("arm_identity_sha256"),
            "routing_report.json": source.get("routing_report_sha256"),
            "run_manifest.json": source.get("run_manifest_sha256"),
        }
        for name, digest in expected.items():
            if digest is None or _sha(stage / name) != digest:
                raise ValueError(f"{arm} source hash 与 doctouch audit 不一致:{name}")
        if source.get("identity_had_code_revision") is not True:
            raise ValueError(f"{arm} arm identity 缺 code revision")
        source_revisions.add(source.get("source_code_revision"))
    if len(source_revisions) != 1 or audit.get("scorer_code_revision") not in \
            source_revisions:
        raise ValueError("三臂与 scorer 不是同一 code revision")

    doc_spec = _json(plan / "doc_list.json")
    doc_ids = doc_spec.get("doc_ids")
    if not isinstance(doc_ids, list) or len(doc_ids) != 200:
        raise ValueError("冻结 doc list 不是 200 份")
    d_report = _json(
        evidence_root / "source-har-0023" / "routing_report.json")
    routes = d_report.get("routes")
    if not isinstance(routes, list):
        raise ValueError("HAR-0023 routing_report.routes 不是 array")
    validate_route_matrix(routes, sorted(doc_ids), list(FIELDS))
    policy = d_report.get("policy") or {}
    release = parse_release_profile(policy)
    release_fields = set((release or {}).get("fields") or [])
    if d_report.get("harness_id") != "HAR-0023" or release_fields != GATING_FIELDS:
        raise ValueError("HAR-0023 source 不是冻结 payment_required_v1 三字段策略")

    return {
        "extract_audit": extract,
        "doctouch_audit": audit,
        "d_routes": routes,
        "source_arm_code_revision": next(iter(source_revisions)),
        "source_hashes": {
            "plan_manifest_sha256": _sha(plan_manifest),
            "extract_audit_sha256": _sha(
                evidence_root / "extract" / "extract_audit.json"),
            "doctouch_metrics_sha256": _sha(metrics_path),
            "doctouch_audit_sha256": _sha(audit_path),
            "har_0023_routing_report_sha256": _sha(
                evidence_root / "source-har-0023" / "routing_report.json"),
        },
    }


def decide(evidence_root: Path, protocol_path: Path, *,
           decision_code_revision: str) -> dict[str, Any]:
    verified = load_and_verify(evidence_root, protocol_path)
    measured = evaluate(
        verified["doctouch_audit"]["rescored"], verified["d_routes"])
    return {
        "decision_version": "qual-narrow-v2-decision-v1",
        "round": ROUND,
        "protocol": str(Path(protocol_path).relative_to(REPO)),
        "protocol_sha256": _sha(protocol_path),
        "integrity": {
            "passed": True,
            "blocking_reasons": [],
            "extract_calls": verified["extract_audit"]["stored_calls"],
            "http_200": verified["extract_audit"]["http_status_counts"]["200"],
            "total_credits": verified["extract_audit"]["total_credits"],
            "raw_tree_sha256": verified["extract_audit"]["raw_tree_sha256"],
            "source_arm_code_revision": verified["source_arm_code_revision"],
            "decision_code_revision": decision_code_revision,
            "source_hashes": verified["source_hashes"],
        },
        **measured,
        "public_claim_boundary": {
            "allowed": "On this unseen DocILE round, HAR-0023 measured 10.5% routing-time zero-touch.",
            "forbidden": [
                "safe zero-touch product capability",
                "extraction accuracy improvement",
                "10.5% human-time savings",
                "promotion of HAR-0023",
            ],
            "qualifiers": [
                "single corpus: DocILE",
                "single provider: Nutrient DWS",
                "single truth caliber: DocILE annotations plus truth-caliber-v1",
            ],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    ap.add_argument("--protocol", type=Path, default=PROTOCOL)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    revision = require_clean_code_revision()
    try:
        result = decide(args.evidence_root, args.protocol,
                        decision_code_revision=revision)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {
            "decision_version": "qual-narrow-v2-decision-v1",
            "round": ROUND,
            "integrity": {"passed": False,
                          "blocking_reasons": [f"{type(exc).__name__}: {exc}"],
                          "decision_code_revision": revision},
            "qualification": {"passed": False, "status": "invalid",
                              "promotion": "denied",
                              "reason_codes": ["integrity_failed"]},
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps({
        "integrity": result["integrity"]["passed"],
        "workflow_effect": (result.get("workflow_effect") or {}).get("passed"),
        "safety_product_capability":
            (result.get("safety_product_capability") or {}).get("passed"),
        "qualification": result["qualification"]["status"],
        "promotion": result["qualification"]["promotion"],
        "reason_codes": result["qualification"]["reason_codes"],
    }, ensure_ascii=False, indent=1))
    print(f"→ {args.out}")
    if not result["integrity"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
