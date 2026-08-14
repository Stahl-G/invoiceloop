#!/usr/bin/env python3
"""Assemble the HITL-narrow round (docs/HITL_NARROW_PROTOCOL_2026-08-14.md).

Frozen HAR-0023 (payment_required_v1, TIER1 explicit off). Display-only
suggestions: caliber names, amount triad, derived due dates. No xmode,
no API preread. Product active / HAR-0021 untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import hitl_round_setup as r1setup  # noqa: E402
import suggest_inject  # noqa: E402
from invoiceloop import pipeline  # noqa: E402
from invoiceloop.amount_triad import suggest_amount_triad  # noqa: E402
from invoiceloop.harness import schema_digest  # noqa: E402
from invoiceloop.party_caliber import suggest_party_names  # noqa: E402
from invoiceloop.routing import policy_digest  # noqa: E402
from invoiceloop.sealed_batch import _corpus_environment, frozen_harness  # noqa: E402

LIST = REPO / "docs" / "hitl_narrow_doc_list.json"
HAR_POLICY = REPO / "docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json"
HAR_SCHEMA = REPO / "invoiceloop/harnesses/HAR-0001/extraction_schema.json"
CALIBER = REPO / "docs/evidence/narrow_v1_2026-08-14/caliber_broadcast_v1.json"


def _har0023_active() -> dict:
    policy = json.loads(HAR_POLICY.read_text(encoding="utf-8"))
    schema = json.loads(HAR_SCHEMA.read_text(encoding="utf-8"))
    return {
        "harness_id": "HAR-0023",
        "policy": policy,
        "policy_digest": policy_digest(policy),
        "policy_sha256": hashlib.sha256(HAR_POLICY.read_bytes()).hexdigest(),
        "schema": schema,
        "schema_digest": schema_digest(schema),
        "schema_sha256": hashlib.sha256(HAR_SCHEMA.read_bytes()).hexdigest(),
    }


def _load_docs() -> list[str]:
    spec = json.loads(LIST.read_text(encoding="utf-8"))
    doc_ids = spec["doc_ids"]
    digest = hashlib.sha256("\n".join(doc_ids).encode()).hexdigest()
    if digest != spec["doc_ids_sha256"]:
        raise SystemExit("fatal: hitl-narrow 名单 sha 不符,名单被改过")
    return doc_ids


def _suggestion_rows(ws: Path, run_dir: Path, doc_ids: list[str]) -> dict:
    rows: dict[str, list[dict]] = {"caliber": [], "triad": [], "derived": []}
    calc = json.loads((run_dir / "calculated_due_dates.json").read_text())
    for doc in doc_ids:
        ocr = json.loads((ws / "ocr" / f"{doc}.json").read_text(encoding="utf-8"))
        for field, rec in suggest_party_names(ocr).items():
            rows["caliber"].append({
                "doc_id": doc, "field": field, "value": rec["value"],
                "printed_label": "NONE",
                "note": f"caliber {rec['rule_id']} {rec['version']}",
            })
        for field, rec in suggest_amount_triad(ocr).items():
            rows["triad"].append({
                "doc_id": doc, "field": field, "value": rec["value"],
                "printed_label": "NONE",
                "note": f"triad {rec['rule_id']} {rec['version']}",
            })
        rec = (calc.get("records") or {}).get(doc) or {}
        value = rec.get("value")
        if value:
            rows["derived"].append({
                "doc_id": doc, "field": "due_date", "value": str(value),
                "printed_label": "NONE",
                "note": f"derived {rec.get('rule_id')} {rec.get('formula')}",
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()

    ws = REPO / "runs" / "hitl-narrow"
    doc_ids = _load_docs()
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "doc_list.json").write_text(LIST.read_text(encoding="utf-8"))
    budget_path = ws / "review_budget.json"
    if budget_path.exists():
        budget_path.unlink()
    (ws / "round_status.json").write_text(json.dumps({
        "round": "hitl-narrow",
        "status": "live",
        "harness_id": "HAR-0023",
        "protocol": "docs/HITL_NARROW_PROTOCOL_2026-08-14.md",
        "caliber": str(CALIBER.relative_to(REPO)),
    }, indent=1) + "\n", encoding="utf-8")

    stats = r1setup._populate(ws, doc_ids)
    if stats["missing"]:
        print(json.dumps({"fatal": "语料缺失,协议要求缺响应换单不补抽",
                          "missing": stats["missing"]}, indent=1))
        sys.exit(1)

    run_dir = ws / "runs" / "run-0001"
    if not run_dir.exists():
        active = _har0023_active()
        with _corpus_environment(ws), frozen_harness(active):
            pipeline.run(doc_ids, run_dir,
                         render_crops=not args.no_crops,
                         include_vision=False,
                         out_of_calibration=True)
    else:
        print(f"run 已存在,重放:{run_dir}")

    rows = _suggestion_rows(ws, run_dir, doc_ids)
    inject_summary = {
        tag: suggest_inject.inject(ws, tag, r, run_dir=run_dir)
        for tag, r in rows.items()}
    (ws / "runs" / "current.json").write_text(
        json.dumps({"run": "run-0001"}) + "\n", encoding="utf-8")

    routing = json.loads((run_dir / "routing_report.json").read_text())
    from invoiceloop.release_profile import document_touch_metrics
    touch = document_touch_metrics(routing["routes"], routing["policy"])
    print(json.dumps({
        "round": "hitl-narrow",
        "docs": len(doc_ids),
        "corpus": stats,
        "run": str(run_dir),
        "harness_id": routing.get("harness_id"),
        "touch": touch,
        "suggestions": {t: {k: s[k] for k in ("written", "skipped_existing",
                                              "reread_rows")}
                        for t, s in inject_summary.items()},
        "dropped": {t: s["dropped"] for t, s in inject_summary.items()
                    if s["dropped"]},
        "workbench": ".venv/bin/python -m invoiceloop workbench "
                     "--workspace runs/hitl-narrow --port 8793",
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
