#!/usr/bin/env python3
"""Aggregate every stored qualification response into one immutable audit.

``extract_summary.json`` describes one invocation.  A budget break followed by
resume therefore leaves the final invocation saying ``done=178, skipped=222``
even though the evidence tree contains all 400 calls.  This command scans the
frozen list and raw files themselves, binds every filename to its content hash,
and fails closed on missing, extra, malformed, non-200, or misbound records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from invoiceloop.heldout import qualification_run_identity

MODES = ("understand", "agentic")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cost(record: dict[str, Any]) -> float:
    usage = (record.get("body") or {}).get("usage") or {}
    return float((usage.get("data_extraction_credits") or {}).get("cost") or 0.0)


def audit(
    workspace: Path,
    *,
    qualification_round: str | None = None,
    qualification_protocol: Path | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace)
    if (qualification_round is None) != (qualification_protocol is None):
        raise ValueError("qualification round/protocol 必须同时提供")
    list_path = workspace / "doc_list.json"
    spec = json.loads(list_path.read_text(encoding="utf-8"))
    doc_ids = spec.get("doc_ids")
    if not isinstance(doc_ids, list) or not all(
            isinstance(doc_id, str) and doc_id for doc_id in doc_ids):
        raise ValueError("doc_list.doc_ids 必须是非空字符串数组")
    if len(doc_ids) != len(set(doc_ids)):
        raise ValueError("doc_list.doc_ids 有重复")

    expected = {f"{doc_id}.{mode}.json" for doc_id in doc_ids for mode in MODES}
    raw = workspace / "raw"
    actual = {path.name for path in raw.glob("*.json") if path.is_file()}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    malformed: list[dict[str, str]] = []
    binding_errors: list[dict[str, str]] = []
    statuses: Counter[str] = Counter()
    per_mode: Counter[str] = Counter()
    files: dict[str, str] = {}
    credits = 0.0

    for name in sorted(expected & actual):
        path = raw / name
        files[name] = _sha(path)
        doc_id, mode, _suffix = name.rsplit(".", 2)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            malformed.append({"file": name, "error": str(exc)})
            continue
        if not isinstance(record, dict):
            malformed.append({"file": name, "error": "top level is not object"})
            continue
        if record.get("doc_id") != doc_id or record.get("mode") != mode:
            binding_errors.append({
                "file": name,
                "record_doc_id": str(record.get("doc_id")),
                "record_mode": str(record.get("mode")),
            })
        statuses[str(record.get("http_status"))] += 1
        per_mode[mode] += 1
        credits += _cost(record)

    tree = hashlib.sha256()
    for name, digest in sorted(files.items()):
        tree.update(f"{name}={digest}\n".encode("utf-8"))
    non_200 = sum(count for status, count in statuses.items() if status != "200")
    blocking_reasons = []
    if missing:
        blocking_reasons.append(f"missing={len(missing)}")
    if extra:
        blocking_reasons.append(f"extra={len(extra)}")
    if malformed:
        blocking_reasons.append(f"malformed={len(malformed)}")
    if binding_errors:
        blocking_reasons.append(f"binding_errors={len(binding_errors)}")
    if non_200:
        blocking_reasons.append(f"non_200={non_200}")

    identity_path = workspace / "qualification_run_identity.json"
    identity: dict[str, Any] | None = None
    identity_sha: str | None = None
    identity_error: str | None = None
    if qualification_round is not None and qualification_protocol is not None:
        if not identity_path.is_file():
            blocking_reasons.append("qualification_identity_missing")
            identity_error = f"不存在:{identity_path}"
        else:
            identity_sha = _sha(identity_path)
            try:
                candidate = json.loads(identity_path.read_text(encoding="utf-8"))
                if not isinstance(candidate, dict):
                    raise ValueError("top level is not object")
                identity = candidate
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                blocking_reasons.append("qualification_identity_malformed")
                identity_error = str(exc)
            if identity is not None:
                try:
                    expected_identity = qualification_run_identity(
                        workspace, round_name=qualification_round,
                        protocol_path=qualification_protocol)
                except (OSError, RuntimeError, ValueError) as exc:
                    expected_identity = None
                    identity_error = str(exc)
                    blocking_reasons.append(
                        "qualification_identity_recompute_failed")
                if expected_identity is not None and identity != expected_identity:
                    blocking_reasons.append("qualification_identity_mismatch")
                    identity_error = (
                        f"stored={identity!r};recomputed={expected_identity!r}")

    prior_path = workspace / "extract_summary.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) \
        if prior_path.is_file() else None
    return {
        "audit_version": "qual-extract-audit-v1",
        "complete": not blocking_reasons,
        "blocking_level": "none" if not blocking_reasons else "blocking",
        "blocking_reasons": blocking_reasons,
        "n_docs": len(doc_ids),
        "expected_calls": len(expected),
        "stored_calls": len(files),
        "per_mode": dict(sorted(per_mode.items())),
        "http_status_counts": dict(sorted(statuses.items())),
        "total_credits": round(credits, 1),
        "doc_list_sha256": _sha(list_path),
        "missing": missing,
        "extra": extra,
        "malformed": malformed,
        "binding_errors": binding_errors,
        "raw_tree_sha256": tree.hexdigest(),
        "files": files,
        "qualification_run_identity": identity,
        "qualification_run_identity_sha256": identity_sha,
        "qualification_identity_error": identity_error,
        "last_invocation_summary": prior,
        "last_invocation_summary_sha256": _sha(prior_path)
        if prior_path.is_file() else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--qualification-round", default=None)
    ap.add_argument("--qualification-protocol", type=Path, default=None)
    args = ap.parse_args()
    report = audit(
        args.workspace,
        qualification_round=args.qualification_round,
        qualification_protocol=args.qualification_protocol)
    out = args.out or args.workspace / "extract_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "complete", "blocking_level", "n_docs", "expected_calls",
        "stored_calls", "http_status_counts", "total_credits",
        "raw_tree_sha256")}, ensure_ascii=False, indent=1))
    print(f"→ {out}")
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
