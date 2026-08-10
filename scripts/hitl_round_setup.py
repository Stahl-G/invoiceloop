#!/usr/bin/env python3
"""Assemble one HITL round workspace (docs/HITL_R1R2_PROTOCOL_2026-08-10.md).

Steps: populate corpus (pdfs/ocr/raw copies) → run the pipeline under the
SEALED-4-qualified HAR-0021 (frozen, product state untouched) → inject the
protocol's two offline suggestion sources into the run (display-only) →
register the run as current.  Zero new DWS calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import suggest_inject  # noqa: E402
from invoiceloop import ocr as ocr_mod  # noqa: E402
from invoiceloop import pipeline  # noqa: E402
from invoiceloop.fields import FIELD_KINDS  # noqa: E402
from invoiceloop.harness import schema_digest  # noqa: E402
from invoiceloop.routing import policy_digest  # noqa: E402
from invoiceloop.sealed_batch import _corpus_environment, frozen_harness  # noqa: E402

DERISK = Path("~/Developer/dws-derisk").expanduser()
RAW_WORKSPACES = ("sealed1-workspace", "sealed2-workspace",
                  "heldout-workspace", "sealed3-workspace")
HAR_POLICY = REPO / "docs/evidence/absence_v3_2026-08-10/HAR-0021.routing_policy.json"
HAR_SCHEMA = REPO / "invoiceloop/harnesses/HAR-0001/extraction_schema.json"


def _har0021_active() -> dict:
    policy = json.loads(HAR_POLICY.read_text(encoding="utf-8"))
    schema = json.loads(HAR_SCHEMA.read_text(encoding="utf-8"))
    return {
        "harness_id": "HAR-0021",
        "policy": policy,
        "policy_digest": policy_digest(policy),
        "policy_sha256": hashlib.sha256(HAR_POLICY.read_bytes()).hexdigest(),
        "schema": schema,
        "schema_digest": schema_digest(schema),
        "schema_sha256": hashlib.sha256(HAR_SCHEMA.read_bytes()).hexdigest(),
    }


def _populate(ws: Path, doc_ids: list[str]) -> dict:
    stats = {"pdfs": 0, "ocr": 0, "raw": 0, "missing": []}
    for sub in ("input/pdfs", "ocr", "raw"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    for doc in doc_ids:
        pdf_src = DERISK / "data" / "docile" / "pdfs" / f"{doc}.pdf"
        ocr_src = DERISK / "data" / "docile" / "ocr" / f"{doc}.json"
        raw_u = raw_a = None
        for name in RAW_WORKSPACES:
            raw = REPO / "runs" / name / "raw"
            if (raw / f"{doc}.understand.json").is_file() and \
                    (raw / f"{doc}.agentic.json").is_file():
                raw_u = raw / f"{doc}.understand.json"
                raw_a = raw / f"{doc}.agentic.json"
                break
        if not (pdf_src.is_file() and ocr_src.is_file() and raw_u):
            stats["missing"].append(doc)
            continue
        shutil.copyfile(pdf_src, ws / "input" / "pdfs" / f"{doc}.pdf")
        shutil.copyfile(ocr_src, ws / "ocr" / f"{doc}.json")
        shutil.copyfile(raw_u, ws / "raw" / f"{doc}.understand.json")
        shutil.copyfile(raw_a, ws / "raw" / f"{doc}.agentic.json")
        stats["pdfs"] += 1
        stats["ocr"] += 1
        stats["raw"] += 1
    return stats


def _data_values(raw_path: Path) -> dict[str, str]:
    """存盘响应 → {field: value};结构损坏 = 该源无建议,不 crash。"""
    try:
        record = json.loads(raw_path.read_text(encoding="utf-8"))
        data = (record.get("body") or {}).get("output", {}).get("data", {})
        return {f: str(v) for f, v in data.items()
                if f in FIELD_KINDS and v is not None and str(v).strip()}
    except (json.JSONDecodeError, AttributeError):
        return {}


def _suggestion_rows(ws: Path, run_dir: Path, doc_ids: list[str]) -> dict:
    """协议 §2 的两个离线源:derived(run 自己的派生工件,单一路径)
    与 xmode-u/xmode-a(另一模式的存盘值,交叉读者)。"""
    rows: dict[str, list[dict]] = {"derived": [], "xmode-u": [], "xmode-a": []}
    calc = json.loads((run_dir / "calculated_due_dates.json").read_text())
    for doc in doc_ids:
        rec = (calc.get("records") or {}).get(doc) or {}
        value = rec.get("value")
        if value:
            rows["derived"].append({
                "doc_id": doc, "field": "due_date", "value": str(value),
                "printed_label": "NONE",
                "note": f"derived {rec.get('rule_id')} {rec.get('formula')}"})
        for tag, mode in (("xmode-u", "understand"), ("xmode-a", "agentic")):
            values = _data_values(ws / "raw" / f"{doc}.{mode}.json")
            for field in sorted(FIELD_KINDS):
                rows[tag].append({
                    "doc_id": doc, "field": field,
                    "value": values.get(field, "")})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--round", required=True, choices=("hitl-r1", "hitl-r2"))
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()

    ws = REPO / "runs" / args.round
    doc_list = json.loads((ws / "doc_list.json").read_text())
    doc_ids = doc_list["doc_ids"]

    stats = _populate(ws, doc_ids)
    if stats["missing"]:
        print(json.dumps({"fatal": "语料缺失,协议要求缺响应换单不补抽",
                          "missing": stats["missing"]}, indent=1))
        sys.exit(1)

    run_dir = ws / "runs" / "run-0001"
    if not run_dir.exists():
        active = _har0021_active()
        with _corpus_environment(ws), frozen_harness(active):
            pipeline.run(doc_ids, run_dir,
                         render_crops=not args.no_crops,
                         include_vision=True,
                         out_of_calibration=True)
    else:
        print(f"run 已存在,重放:{run_dir}")

    rows = _suggestion_rows(ws, run_dir, doc_ids)
    inject_summary = {
        tag: suggest_inject.inject(ws, tag, r, run_dir=run_dir)
        for tag, r in rows.items()}
    (ws / "runs" / "current.json").write_text(
        '{"run": "run-0001"}\n', encoding="utf-8")

    print(json.dumps({
        "round": args.round, "docs": len(doc_ids), "corpus": stats,
        "run": str(run_dir),
        "suggestions": {t: {k: s[k] for k in ("written", "skipped_existing",
                                              "reread_rows")}
                        for t, s in inject_summary.items()},
        "dropped": {t: s["dropped"] for t, s in inject_summary.items()
                    if s["dropped"]},
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
