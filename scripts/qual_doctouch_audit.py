#!/usr/bin/env python3
"""Re-score stored qualification arms without rerunning extraction or routing.

This is a superseding audit, not a fourth execution path.  It verifies the
historical route matrices and their run identities, binds the current scorer
commit, and adds the release-gating safety subset that the original report did
not calculate.  Existing metric values are compared recursively and any drift
is blocking; only additive fields are permitted.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from doctouch_arms import (  # type: ignore[import-not-found]
    ARM_POLICIES,
    active_for,
    measure,
    require_clean_code_revision,
    strata,
)

from invoiceloop.fields import FIELDS
from invoiceloop.release_profile import PAYMENT_REQUIRED_V1


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


def validate_route_matrix(
    routes: Sequence[Mapping[str, Any]],
    doc_ids: Sequence[str],
    fields: Sequence[str],
) -> None:
    """Require exactly one route for every frozen (document, field) slot."""
    expected_docs = set(doc_ids)
    expected_fields = set(fields)
    seen: set[tuple[str, str]] = set()
    for row in routes:
        doc_id = str(row.get("doc_id"))
        field = str(row.get("field"))
        if doc_id not in expected_docs:
            raise ValueError(f"路由含名单外文档:{doc_id}")
        if field not in expected_fields:
            raise ValueError(f"路由含 schema 外字段:{field}")
        key = (doc_id, field)
        if key in seen:
            raise ValueError(f"路由槽重复:{doc_id}|{field}")
        seen.add(key)
    expected = {(doc_id, field) for doc_id in doc_ids for field in fields}
    missing = sorted(expected - seen)
    if missing:
        raise ValueError(
            f"路由矩阵不完整:expected={len(expected)},actual={len(seen)},"
            f"missing={missing[:5]}")


def legacy_metric_drift(
    legacy: Mapping[str, Any], rescored: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Compare all legacy leaves while allowing new additive report fields."""
    drift: list[dict[str, Any]] = []
    missing = object()

    def walk(old: Any, new: Any, parts: list[str]) -> None:
        if isinstance(old, Mapping):
            if not isinstance(new, Mapping):
                drift.append({"path": ".".join(parts),
                              "legacy": old, "rescored": new})
                return
            for key, value in old.items():
                candidate = new.get(key, missing)
                if candidate is missing:
                    drift.append({"path": ".".join([*parts, str(key)]),
                                  "legacy": value, "rescored": "<missing>"})
                else:
                    walk(value, candidate, [*parts, str(key)])
            return
        if old != new:
            drift.append({"path": ".".join(parts),
                          "legacy": old, "rescored": new})

    walk(legacy, rescored, [])
    return drift


def load_understand(path: Path, doc_id: str) -> dict[str, Any]:
    """Load one exact audited understand record and verify its binding."""
    record = _json(path)
    if record.get("doc_id") != doc_id or record.get("mode") != "understand":
        raise ValueError(f"understand 文件内容绑定错误:{path.name}")
    if record.get("http_status") != 200:
        raise ValueError(f"understand 非 200:{path.name}")
    body = record.get("body")
    output = body.get("output") if isinstance(body, Mapping) else None
    data = output.get("data") if isinstance(output, Mapping) else None
    if not isinstance(data, dict):
        raise ValueError(f"understand output.data 不是 object:{path.name}")
    return data


def _identity_check(identity: Mapping[str, Any], active: Mapping[str, Any],
                    doc_ids: Sequence[str]) -> None:
    expected = {
        "harness_id": active["harness_id"],
        "policy_digest": active["policy_digest"],
        "policy_sha256": active["policy_sha256"],
        "schema_sha256": active["schema_sha256"],
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(sorted(doc_ids)).encode("utf-8")).hexdigest(),
    }
    mismatch = {key: {"expected": value, "actual": identity.get(key)}
                for key, value in expected.items()
                if identity.get(key) != value}
    if mismatch:
        raise ValueError(f"历史臂身份与冻结输入不符:{mismatch}")


def audit(workspace: Path) -> dict[str, Any]:
    workspace = Path(workspace)
    revision = require_clean_code_revision()
    list_path = workspace / "doc_list.json"
    doc_spec = _json(list_path)
    doc_ids = doc_spec.get("doc_ids")
    if not isinstance(doc_ids, list) or not all(
            isinstance(doc_id, str) and doc_id for doc_id in doc_ids):
        raise ValueError("doc_list.doc_ids 必须是非空字符串数组")
    if len(doc_ids) != len(set(doc_ids)):
        raise ValueError("doc_list.doc_ids 有重复")
    doc_ids = sorted(doc_ids)

    extract_path = workspace / "extract_audit.json"
    extract = _json(extract_path)
    if not extract.get("complete") or extract.get("n_docs") != len(doc_ids):
        raise ValueError("聚合抽取审计未完整通过,不能复算路由安全")
    audited_files = extract.get("files")
    if not isinstance(audited_files, Mapping):
        raise ValueError("聚合抽取审计缺 files 哈希表")

    understand: dict[str, dict[str, Any]] = {}
    for doc_id in doc_ids:
        name = f"{doc_id}.understand.json"
        path = workspace / "raw" / name
        if audited_files.get(name) != _sha(path):
            raise ValueError(f"understand 响应不属于聚合抽取审计:{name}")
        understand[doc_id] = load_understand(path, doc_id)

    strength = strata(doc_ids)
    legacy_path = workspace / "doctouch" / "doctouch_metrics.json"
    legacy = _json(legacy_path)
    rescored = copy.deepcopy(legacy)
    if legacy.get("n_docs") != len(doc_ids):
        raise ValueError("旧指标 n_docs 与冻结名单不符")
    expected_strata = dict(Counter(strength.values()))
    if legacy.get("strata") != expected_strata:
        raise ValueError("旧指标 strata 与当前冻结分层复算不符")

    sources: dict[str, Any] = {}
    routes_by_arm: dict[str, list[dict[str, Any]]] = {}
    for arm in ("HAR-0001", "HAR-0021", "HAR-0023"):
        arm_dir = workspace / "doctouch" / "arms" / arm
        active = active_for(arm)
        identity_path = arm_dir / "arm_identity.json"
        manifest_path = arm_dir / "run_manifest.json"
        routing_path = arm_dir / "routing_report.json"
        identity = _json(identity_path)
        manifest = _json(manifest_path)
        report = _json(routing_path)
        _identity_check(identity, active, doc_ids)
        source_revision = manifest.get("code_revision")
        if not isinstance(source_revision, str) or not source_revision:
            raise ValueError(f"{arm} run_manifest 缺 code_revision")
        identity_revision = identity.get("code_revision")
        if identity_revision is not None and identity_revision != source_revision:
            raise ValueError(f"{arm} identity 与 run_manifest 代码身份不符")
        routes = report.get("routes")
        if not isinstance(routes, list):
            raise ValueError(f"{arm} routing_report.routes 不是 array")
        validate_route_matrix(routes, doc_ids, list(FIELDS))
        routes_by_arm[arm] = routes
        rescored["arms"][arm]["metrics"] = measure(
            routes, active["policy"], strength, understand)
        sources[arm] = {
            "source_code_revision": source_revision,
            "identity_had_code_revision": identity_revision is not None,
            "arm_identity_sha256": _sha(identity_path),
            "run_manifest_sha256": _sha(manifest_path),
            "routing_report_sha256": _sha(routing_path),
            "policy_digest": active["policy_digest"],
            "policy_sha256": active["policy_sha256"],
            "schema_sha256": active["schema_sha256"],
        }

    projected = _json(ARM_POLICIES["HAR-0021"])
    projected["release_profile"] = {
        "id": "payment_required_v1",
        "fields": sorted(PAYMENT_REQUIRED_V1),
    }
    projection = "HAR-0021+payment(projection)"
    rescored["arms"][projection]["metrics"] = measure(
        routes_by_arm["HAR-0021"], projected, strength, understand)

    drift = legacy_metric_drift(legacy, rescored)
    d_safety = (rescored["arms"]["HAR-0023"]["metrics"]["ALL"]
                ["zero_touch_release_safety"])
    return {
        "audit_version": "qual-doctouch-superseding-audit-v2",
        "complete": not drift,
        "blocking_level": "none" if not drift else "blocking",
        "blocking_reasons": [] if not drift else ["legacy_metric_drift"],
        "scorer_code_revision": revision,
        "n_docs": len(doc_ids),
        "doc_list_sha256": _sha(list_path),
        "extract_audit_sha256": _sha(extract_path),
        "legacy_metrics_sha256": _sha(legacy_path),
        "source_arms": sources,
        "legacy_metric_drift": drift,
        "har_0023_zero_touch_release_safety": d_safety,
        "rescored": rescored,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    report = audit(args.workspace)
    out = args.out or args.workspace / "doctouch" / "doctouch_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    safety = report["har_0023_zero_touch_release_safety"]
    print(json.dumps({
        "complete": report["complete"],
        "blocking_level": report["blocking_level"],
        "n_docs": report["n_docs"],
        "legacy_metric_drift": len(report["legacy_metric_drift"]),
        "har_0023_zero_touch_docs": safety["zero_touch_docs"],
        "har_0023_zero_touch_gating_slots": safety["gating_slots"],
        "har_0023_zero_touch_silent_wrong": safety["silent_wrong"],
        "har_0023_zero_touch_unscored_auto_accept":
            safety["unscored_auto_accept_slots"],
        "har_0023_zero_touch_release_error_docs":
            safety["docs_with_release_error"],
    }, ensure_ascii=False, indent=1))
    print(f"→ {out}")
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
