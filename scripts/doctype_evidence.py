"""docs/DOCTYPE_EVIDENCE_2026-08-07.md 的零 API 复算。

用法:
  INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/doctype_evidence.py
  INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_evidence.py --sealed2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import dws, doctype  # noqa: E402
from invoiceloop.ocr import OcrUnavailable  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def _raw_type(doc_id: str) -> str | None:
    u = dws.load_response(doc_id, "understand")
    if u is None:
        return None
    v = u.data.get("invoice_type")
    return None if v is None else str(v)


def measure(doc_ids: list[str]) -> dict:
    by_class: dict[str, int] = {}
    no_claim = unmapped = 0
    with_claim = 0
    evidenced = 0
    blocked: list[dict] = []
    ocr_miss = 0
    for doc in doc_ids:
        raw = _raw_type(doc)
        cls = doctype.classify(raw)
        by_class[cls] = by_class.get(cls, 0) + 1
        if cls == doctype.NO_CLAIM:
            no_claim += 1
            continue
        if cls == doctype.UNMAPPED:
            unmapped += 1
            continue
        with_claim += 1
        try:
            hit = doctype.find_evidence(doc, cls)
        except OcrUnavailable:
            ocr_miss += 1
            blocked.append({"doc_id": doc, "raw": raw, "class": cls,
                            "reason": "ocr_unavailable"})
            continue
        if hit is None:
            blocked.append({"doc_id": doc, "raw": raw, "class": cls,
                            "reason": "no_literal_evidence"})
        else:
            evidenced += 1
    return {
        "n": len(doc_ids),
        "by_class": dict(sorted(by_class.items())),
        "with_claim": with_claim,
        "evidenced": evidenced,
        "evidence_rate": evidenced / with_claim if with_claim else None,
        "no_claim": no_claim,
        "unmapped": unmapped,
        "ocr_miss": ocr_miss,
        "blocked": blocked,
        # 名字要说清它测的是什么:页面上找不到字面支撑的比例。
        # 不是「声明错了」—— 那要人看语义(宪章六)。
        "no_literal_evidence_rate":
            len(blocked) / with_claim if with_claim else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sealed2", action="store_true",
                    help="用 sealed2 名单(默认:sealed1 未人工 88)")
    args = ap.parse_args()
    if args.sealed2:
        os.environ.setdefault("INVOICELOOP_CORPUS",
                              str(REPO / "runs" / "sealed2-workspace"))
        ids = json.load(open(REPO / "docs" / "sealed2_doc_list.json"))["doc_ids"]
        label = "SEALED-2"
    else:
        os.environ.setdefault("INVOICELOOP_CORPUS",
                              str(REPO / "runs" / "sealed1-workspace"))
        hitl = {p.stem for p in
                (REPO / "runs" / "hitl-sealed" / "input" / "pdfs").glob("*.pdf")}
        ids = [d for d in json.load(open(
            REPO / "docs" / "sealed1_doc_list.json"))["doc_ids"] if d not in hitl]
        label = "SEALED-1 unseen-88"
    r = measure(ids)
    print(f"=== {label} ===")
    print(json.dumps({k: v for k, v in r.items() if k != "blocked"},
                     indent=2, ensure_ascii=False))
    print(f"blocked ({len(r['blocked'])}):")
    for b in r["blocked"]:
        print(f"  {b['doc_id']}  class={b['class']}  raw={b['raw']!r}  "
              f"({b['reason']})")


if __name__ == "__main__":
    main()
