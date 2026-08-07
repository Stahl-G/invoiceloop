"""阶段 B / Q2:三种「无类型证据」阻断粒度对 SEALED-2 负载的影响(零 API)。

粒度:
  none     — 基线(HAR-0004,现网)
  doc      — 无证据文档 → 全部 10 槽进 human_queue(模拟 doc_blocked)
  typedep  — 无证据文档 → 不适用类型级放宽,但本脚本只量「标注可见」:
             路由与基线相同,另计 would_flag 槽数(交付物标注代价)
  finding  — 同 typedep(非阻断 finding;负载 = 基线)

用法:
  INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_block_impact.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import dws, doctype  # noqa: E402
from invoiceloop.ocr import OcrUnavailable  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("INVOICELOOP_CORPUS",
                      str(REPO / "runs" / "sealed2-workspace"))


def blocked_docs(ids: list[str]) -> set[str]:
    out = set()
    for doc in ids:
        u = dws.load_response(doc, "understand")
        raw = None if not u else u.data.get("invoice_type")
        cls = doctype.classify(None if raw is None else str(raw))
        if cls in (doctype.NO_CLAIM, doctype.UNMAPPED):
            continue
        try:
            hit = doctype.find_evidence(doc, cls)
        except OcrUnavailable:
            out.add(doc)
            continue
        if hit is None:
            out.add(doc)
    return out


def main() -> None:
    ids = json.load(open(REPO / "docs" / "sealed2_doc_list.json"))["doc_ids"]
    matrix = json.load(open(REPO / "runs" / "sealed2" / "support_matrix.json"))
    routes = { (r["doc_id"], r["field"]): r for r in matrix["rows"] }
    base_hq = sum(1 for r in matrix["rows"] if r.get("in_human_queue"))
    bad = blocked_docs(ids)
    print(f"SEALED-2 docs without type evidence: {len(bad)}")
    print(f"baseline human_queue: {base_hq}/1000 ({base_hq/10:.1f}%)")

    # doc-level: force all 10 fields of bad docs into queue
    doc_hq = 0
    for r in matrix["rows"]:
        if r["doc_id"] in bad or r.get("in_human_queue"):
            doc_hq += 1
    # recount unique slots
    doc_hq = sum(
        1 for (d, f), r in routes.items()
        if d in bad or r.get("in_human_queue")
    )
    print(f"doc-block human_queue: {doc_hq}/1000 ({doc_hq/10:.1f}%)  "
          f"Δpp={(doc_hq-base_hq)/10:.1f}")

    # fields that were machine-decided on bad docs become newly queued
    newly = sum(
        1 for (d, f), r in routes.items()
        if d in bad and not r.get("in_human_queue")
    )
    print(f"  of which newly forced into queue: {newly} slots "
          f"({newly/10:.1f}pp)")
    print("typedep / finding-only: human_queue unchanged at baseline; "
          f"would flag {len(bad)} docs on deliverable")


if __name__ == "__main__":
    main()
