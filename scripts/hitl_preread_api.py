#!/usr/bin/env python3
"""HITL 阶段的 API 预读(替代 agent 预读,docs/HITL_R1_AMENDMENT_STAGED_2026-08-11.md)。

对已装配的 run:队列槽(in_human_queue)→ 每份单调一次
vision_ingest.read_doc(整页渲染 + 第六轮五律 prompt)→ 解析行过滤到队列槽
→ suggest_inject 以 **run-dir 展示型** 注入。展示型 = 不进输入指纹、不成草稿,
队列构成与未带该读者的阶段保持可比;agent 预读的 kimi tag 走同一条路。

凭证与模型走 env 模块(与 vision-ingest 同源);tag 默认就是模型名 ——
显示名不许撒谎(vision_ingest.DEFAULT_MODEL 的注释纪律)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import suggest_inject  # noqa: E402
from invoiceloop import env as env_mod  # noqa: E402
from invoiceloop import vision_ingest as vi  # noqa: E402


def queue_slots(run_dir: Path) -> dict[str, set[str]]:
    """run 的支持矩阵 → {doc_id: {队列字段}}。只认 in_human_queue 的行。"""
    sm = json.loads((run_dir / "support_matrix.json").read_text())
    slots: dict[str, set[str]] = {}
    for row in sm["rows"]:
        if row.get("in_human_queue"):
            slots.setdefault(row["doc_id"], set()).add(row["field"])
    return slots


def to_suggestion_rows(parsed: list[list[str]],
                       fields: set[str]) -> list[dict]:
    """vision_ingest._parse_rows 的五行行 → 建议行,只留队列字段。
    ABSTAIN / 空值 → ""(下游即弃权,与 agent 预读口径一致)。"""
    rows = []
    for doc_id, field, value, printed_label, note in parsed:
        if field not in fields:
            continue
        if value.upper() == "ABSTAIN":
            value, printed_label = "", printed_label or "NONE"
        rows.append({"doc_id": doc_id, "field": field, "value": value,
                     "printed_label": printed_label or "NONE", "note": note})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--tag", help="建议读者显示名;默认用模型名")
    ap.add_argument("--model", help="覆盖 env 里的 anthropic_model")
    args = ap.parse_args()
    run_dir = args.run_dir

    key = env_mod.credential("anthropic")
    if not key:
        raise SystemExit("缺 anthropic 凭证(env 模块)—— 跑不了,不是跳过")
    base = env_mod.credential("anthropic_base")
    model = args.model or env_mod.credential("anthropic_model") or vi.DEFAULT_MODEL
    tag = args.tag or model

    ws = run_dir.parent.parent  # runs/<round>/runs/<run> → runs/<round>
    slots = queue_slots(run_dir)
    rows, failed = [], []
    for doc_id in sorted(slots):
        pages = sorted((run_dir / "pages").glob(f"{doc_id}-*.png"))
        if not pages:
            failed.append({"doc_id": doc_id, "error": "无整页渲染"})
            continue
        try:
            text = vi.read_doc(doc_id, pages, model=model, api_key=key,
                               base_url=base)
            rows.extend(to_suggestion_rows(
                vi._parse_rows(text, doc_id), slots[doc_id]))
        except Exception as exc:  # noqa: BLE001 —— 记失败,不中断整批
            failed.append({"doc_id": doc_id, "error": repr(exc)})

    summary = suggest_inject.inject(ws, tag, rows, run_dir=run_dir)
    print(json.dumps({
        "run": str(run_dir), "model": model, "tag": tag,
        "queue_slots": sum(len(f) for f in slots.values()),
        "docs": len(slots),
        "abstained": sum(1 for r in rows if not r["value"]),
        "injected": {k: summary[k] for k in
                     ("written", "skipped_existing", "reread_rows")},
        "dropped": summary["dropped"], "failed": failed,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
