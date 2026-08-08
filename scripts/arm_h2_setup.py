#!/usr/bin/env python3
"""Stand up the H2 arm: the same 200 slots, for a human, blind to TA. Zero API.

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md` §3 and §8.

The run directory is rsynced from `runs/sealed2` exactly as the TA arm's was, so
both arms bind to the same `review_snapshot_id` and judge byte-identical
artifacts. `pages/` is added here because the workbench's left column needs it;
it is not a snapshot component, so adding it does not break that parity.

Nothing under `runs/arm-ta/` is referenced, linked or copied. The human must not
see the agent's answers before their own ledger is frozen, or the comparison
measures anchoring instead of judgement.

    python3 scripts/arm_h2_setup.py
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import arms, evidence  # noqa: E402
from invoiceloop.snapshot import compute_review_snapshot  # noqa: E402

SOURCE_RUN = Path("runs/sealed2")
SOURCE_WS = Path("runs/sealed2-workspace")
ARM_WS = Path("runs/arm-h2")
ARM_RUN = ARM_WS / "runs" / "run-0001"
SAMPLE = Path("docs/arm_slot_sample.json")


def stage() -> None:
    ARM_RUN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["rsync", "-a", "--exclude", "audit_bundle.zip",
         f"{SOURCE_RUN}/", f"{ARM_RUN}/"], check=True)
    # 空账本:H2 从零开始判,不继承任何裁决
    (ARM_RUN / "adjudication_ledger.jsonl").write_text("", encoding="utf-8")
    for stale in ("adjudication_ledger.lock",):
        (ARM_RUN / stale).unlink(missing_ok=True)


def render(docs: set[str]) -> dict[str, int]:
    """整页渲染进 <run>/pages,平铺命名 —— workbench 左栏按 `<doc>-<n>.png` 找。"""
    out = ARM_RUN / "pages"
    out.mkdir(exist_ok=True)
    counts = {}
    for i, doc in enumerate(sorted(docs), 1):
        if list(out.glob(f"{doc}-*.png")):
            counts[doc] = len(list(out.glob(f"{doc}-*.png")))
            continue
        names = evidence.render_pages(SOURCE_WS / "input" / "pdfs" / f"{doc}.pdf", out)
        counts[doc] = len(names)
        if i % 20 == 0:
            print(f"  rendered {i}/{len(docs)} docs", flush=True)
    return counts


def index(slots: list[str], rows: dict[str, dict]) -> Path:
    """200 槽的点击清单,**按抽样顺序** —— 队列全长 468,不给清单会做错题。"""
    items = []
    for n, key in enumerate(slots, 1):
        doc, field = key.split("|", 1)
        row = rows[key]
        val = (row.get("value") or "").strip() or "（无值）"
        items.append(
            f'<li><a href="/adjudicate?run=run-0001&amp;doc={html.escape(doc)}'
            f'&amp;field={html.escape(field)}&amp;lang=zh" target="_blank">'
            f'{n:03d} · {html.escape(field)}</a> '
            f'<code>{html.escape(val[:40])}</code> '
            f'<small>{html.escape(doc[:8])}…</small></li>')
    page = f"""<meta charset="utf-8"><title>H2 臂 · 200 槽</title>
<style>body{{font:13px/1.7 ui-monospace,monospace;max-width:820px;margin:2rem auto;padding:0 1rem}}
li{{margin:.15rem 0}} code{{color:#555}} small{{color:#999}}
.warn{{background:#fff3cd;border-left:4px solid #e0a800;padding:.8rem 1rem;margin:1rem 0}}</style>
<h1>H2 臂 —— 人工裁决 200 槽</h1>
<div class="warn"><b>盲法</b>:这 200 槽 agent 已经判过一遍,结果封在
<code>runs/arm-ta/</code>,你判完之前我不会讲它判了什么。<br>
判据只有一条:<b>按你平时的标准判</b>。不要为了"和机器比"改变尺度。</div>
<p>顺序是抽样顺序,不必按序做;做过的槽 workbench 会显示既有裁决。
共 {len(slots)} 槽。</p>
<ol style="padding-left:2.5rem">{''.join(items)}</ol>"""
    path = ARM_WS / "h2_index.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> None:
    slots = json.loads(SAMPLE.read_text(encoding="utf-8"))["slots"]
    stage()
    matrix = json.loads(
        (ARM_RUN / "support_matrix.json").read_text(encoding="utf-8"))
    rows = {arms.slot_key(r): r for r in matrix["rows"] if "doc_id" in r}
    docs = {k.split("|", 1)[0] for k in slots}
    print(f"slots={len(slots)} docs={len(docs)}", flush=True)
    counts = render(docs)

    stored = json.loads(
        (ARM_RUN / "review_snapshot.json").read_text(encoding="utf-8"))
    current = compute_review_snapshot(ARM_RUN)
    same = stored["review_snapshot_id"] == current["review_snapshot_id"]
    ta_snapshot = None
    ta = Path("runs/arm-ta/runs/run-0001/review_snapshot.json")
    if ta.exists():
        ta_snapshot = json.loads(ta.read_text(encoding="utf-8"))["review_snapshot_id"]

    report = {
        "arm": "H2",
        "protocol": "docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md",
        "slots": len(slots),
        "docs": len(docs),
        "pages_rendered": sum(counts.values()),
        "docs_with_no_page": sorted(d for d, n in counts.items() if n == 0),
        "review_snapshot_id": stored["review_snapshot_id"],
        "snapshot_consistent": same,
        # 两臂必须绑同一个快照,否则不是同一道题
        "same_snapshot_as_ta": (ta_snapshot == stored["review_snapshot_id"]
                                if ta_snapshot else None),
        "index": str(index(slots, rows)),
    }
    (ARM_WS / "arm_setup.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if not same:
        sys.exit("快照不一致 —— 裁决会被 append_adjudication 挡住,先查工件")


if __name__ == "__main__":
    main()
