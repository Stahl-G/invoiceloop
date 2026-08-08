#!/usr/bin/env python3
"""Regenerate the H2 click list with progress marks. Zero API, safe to rerun.

The live workbench queue is the whole run — 468 slots — and this arm is only the
200 pre-registered ones, so the queue is the wrong door. This page is the right
one. Rerun it any time to refresh which slots are already adjudicated.

    python3 scripts/arm_h2_index.py && open runs/arm-h2/h2_index.html
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import arms  # noqa: E402
from invoiceloop.review import load_decisions, project  # noqa: E402

ARM_WS = Path("runs/arm-h2")
ARM_RUN = ARM_WS / "runs" / "run-0001"
SAMPLE = Path("docs/arm_slot_sample.json")
PORT = 8791


def main() -> None:
    slots = json.loads(SAMPLE.read_text(encoding="utf-8"))["slots"]
    matrix = json.loads(
        (ARM_RUN / "support_matrix.json").read_text(encoding="utf-8"))
    rows = {arms.slot_key(r): r for r in matrix["rows"] if "doc_id" in r}

    decisions = load_decisions(ARM_RUN)
    tips = project(decisions)
    decided: dict[str, str] = {}
    for slot in tips.values():
        tip = slot.get("tip")
        if tip:
            decided[f"{tip['doc_id']}|{tip['field']}"] = tip["decision"]

    items = []
    for n, key in enumerate(slots, 1):
        doc, field = key.split("|", 1)
        row = rows[key]
        val = (row.get("value") or "").strip() or "（抽取器没给值）"
        got = decided.get(key)
        mark = f'<b class="done">✓ {html.escape(got)}</b>' if got else \
            '<span class="todo">待判</span>'
        items.append(
            f'<li class="{"done" if got else "todo"}">'
            f'<a href="http://127.0.0.1:{PORT}/adjudicate?run=run-0001'
            f'&amp;doc={html.escape(doc)}&amp;field={html.escape(field)}'
            f'&amp;lang=zh" target="_blank">{n:03d} · {html.escape(field)}</a> '
            f'{mark} <code>{html.escape(val[:44])}</code> '
            f'<small>{html.escape(doc[:8])}…</small></li>')

    page = f"""<meta charset="utf-8"><title>H2 臂 · 我要做的 200 槽</title>
<style>
body{{font:13px/1.75 ui-monospace,SFMono-Regular,monospace;max-width:900px;
margin:2rem auto;padding:0 1rem;color:#1c1c1c}}
h1{{font-size:1.25rem}} li{{margin:.2rem 0}} code{{color:#555}}
small{{color:#aaa}} li.done{{opacity:.45}} b.done{{color:#1a7f37}}
.todo{{color:#b45309}}
.warn{{background:#fff8e1;border-left:4px solid #e0a800;padding:.9rem 1.1rem;
margin:1.1rem 0;line-height:1.7}}
.bar{{height:10px;background:#eee;border-radius:5px;overflow:hidden;margin:.6rem 0}}
.bar>i{{display:block;height:100%;background:#1a7f37;width:{len(decided)/max(1,len(slots))*100:.1f}%}}
@media(prefers-color-scheme:dark){{body{{background:#141414;color:#e8e8e8}}
code{{color:#aaa}} .warn{{background:#2a2410;color:#e8e8e8}} .bar{{background:#333}}}}
</style>
<h1>H2 臂 —— 我自己要判的 200 槽</h1>
<div class="bar"><i></i></div>
<p><b>{len(decided)} / {len(slots)}</b> 已判 · 刷新进度:
<code>python3 scripts/arm_h2_index.py</code></p>

<div class="warn">
<b>别用 workbench 的 /queue。</b>那是整个 run 的 468 槽队列,不是这个实验的 200 槽。
只走本页的链接。<br><br>
<b>盲法</b>:这 200 槽 agent 已经判过一遍,结果封在 <code>runs/arm-ta/</code>。
你判完之前不会有人告诉你它判了什么。<br><br>
<b>唯一要求:按你平时的标准判。</b>不要为了"和机器比"改尺度 —— 那会把
「人 vs 真值」这个度量一起毁掉,而那是这个项目第一次量自己的错误率。<br><br>
不确定就 <code>abstain</code>,那是正当答案,不是失败。心码(reason code)请填,
不填的事件进不了挖掘臂。
</div>

<p>顺序是抽样顺序,不必按序做。已判的槽会变灰并显示裁决。</p>
<ol style="padding-left:3rem">{''.join(items)}</ol>"""
    out = ARM_WS / "h2_index.html"
    out.write_text(page, encoding="utf-8")
    print(f"{len(decided)}/{len(slots)} 已判 → {out}")


if __name__ == "__main__":
    main()
