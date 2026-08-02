"""support_panel.html —— 静态、离线、无需服务。demo 主画面。

写进 panel 的纪律(宪章六 + GOAL.md,第 4 条最容易在收尾时被磨掉,守住它):

- 必须写"抽取本身不可信" —— 这不是矛盾的注脚,是这套东西存在的理由。
- 每个门禁的拦截率必须带 ARCHITECTURE.md §8 那三条限定。
- 口径争议(label_convention_disputed)显式展示,不进任何"错误"计数。
- 页脚给出输入签名:panel 上每个数都能从存盘证据零 API 重算。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

_STRENGTH_LABEL = {
    "unsupported": "无支持",
    "single_source": "单一来源",
    "corroborated": "多方印证",
}
_TIER_LABEL = {
    "dws_extraction": "DWS 抽取",
    "independent_ocr": "独立 OCR",
    "vision_reading": "整页读图",
    "arithmetic": "算术恒等",
}
_VERDICT_LABEL = {"pass": "过", "warning": "警", "fail": "拒", "unavailable": "—"}
_GATE_SHORT = {
    "arithmetic_consistency": "算术",
    "field_wellformed": "形态",
    "extraction_present": "在场",
    "citation_holds": "引用",
    "cross_mode_agreement": "双模式",
    "visual_corroboration": "读图",
}

_QUALIFIERS = [
    "门禁是看过第一轮数据之后设计的(THRESHOLDS.md §6c B-4 自陈),带乐观偏差;"
    "留出集确认已于 2026-08-02 执行(100 份,判据预注册,H1–H6 全过,lift 3.04×),详见 docs/HELDOUT.md。",
    "DocILE 标注本身有争议 —— 第四轮逐份读图,14 例中 8 例是标注错。",
    "校准集全为美国广播广告发票;留出集在 DocILE 全类型内复现了分诊集中度,DocILE 之外的表现仍未知。",
]

_NON_CLAIMS = [
    "不主张 DWS 可信,不主张抽取质量提升 —— 六轮预注册实验说的恰恰相反。",
    "不主张语义正确性 —— 输出是支持矩阵,不是「这个值是对的」。",
    "不主张可无人值守 —— 无支持项按设计就要人看。",
    "不主张适用于生产 —— 160 份、英文、单一供应商、单一时间点。",
]


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _chips(verdicts: dict) -> str:
    return "".join(
        f'<span class="gate {v}" title="{_esc(g)}">{_esc(_GATE_SHORT.get(g, g))}:{_VERDICT_LABEL.get(v, v)}</span>'
        for g, v in sorted(verdicts.items())
    )


def _row_html(row: dict, spans_by_id: dict, run_dir: Path) -> str:
    strength = row["support_strength"]
    tiers = " ".join(
        f'<span class="tier">{_esc(_TIER_LABEL.get(t, t))}</span>' for t in row["source_tiers"]
    ) or '<span class="tier none">无</span>'
    applicability = (
        '<span class="disputed">口径争议</span>'
        if row["applicability"] == "label_convention_disputed" else ""
    )
    limitations = "".join(f"<li>{_esc(x)}</li>" for x in row["limitations"])
    evidence = []
    for span_id in row["span_ids"]:
        span = spans_by_id.get(span_id)
        if not span:
            continue
        crop = ""
        if span.get("crop") and (run_dir / "crops" / span["crop"]).exists():
            crop = f'<a href="crops/{_esc(span["crop"])}" target="_blank"><img class="crop" src="crops/{_esc(span["crop"])}" loading="lazy" alt="{_esc(span_id)}"></a>'
        evidence.append(
            f'<div class="span">{crop}<div class="span-meta">'
            f'<b>{_esc(span_id)}</b> p{span["page"]} · 标签:<i>{_esc(span["printed_label"])}</i><br>'
            f'<span class="ocr">OCR: {_esc(span["ocr_text"][:160])}</span></div></div>'
        )
    rejected = ""
    if row["rejections"]:
        items = "".join(
            f'<li>{_esc(r["drafted_by"])}: “{_esc(r["value"])}” — {_esc(r["reason"])}'
            + (f'(coverage {r["coverage"]})' if r.get("coverage") is not None else "")
            + "</li>"
            for r in row["rejections"]
        )
        rejected = f'<div class="rejected"><b>冻结时被拒:</b><ul>{items}</ul></div>'
    blocking = ""
    if row["blocking_findings"]:
        blocking = f'<div class="blocking">阻断发现: {_esc(", ".join(row["blocking_findings"]))}</div>'
    return f"""<tr class="row {strength}">
<td class="doc" title="{_esc(row['doc_id'])}">{_esc(row['doc_id'][:8])}</td>
<td class="field">{_esc(row['field'])}</td>
<td class="value">{_esc(row['value'])}{' <span class="novalue">(无值)</span>' if row['value'] in (None, '') else ''}</td>
<td><span class="badge {strength}">{_STRENGTH_LABEL[strength]}</span>{applicability}</td>
<td>{tiers}</td>
<td class="gates">{_chips(row['gate_verdicts'])}</td>
<td class="detail"><ul class="lim">{limitations}</ul>{''.join(evidence)}{rejected}{blocking}</td>
</tr>"""


def render_panel(
    run_dir: Path,
    *,
    support: dict,
    gate_report: dict,
    spans: list[dict],
    ledger: dict,
    artifact_digest: str,
) -> Path:
    """从 run 目录的冻结工件渲染 panel。只读工件,不重算任何门禁。"""
    run_dir = Path(run_dir)
    spans_by_id = {s["span_id"]: s for s in spans}
    s = support["summary"]
    rows_html = "\n".join(_row_html(r, spans_by_id, run_dir) for r in support["rows"])

    findings = gate_report["findings"]
    blocking = [f for f in findings if f["blocking"]]
    findings_html = "".join(
        f'<tr class="{"blk" if f["blocking"] else ""}"><td>{_esc(f["finding_id"])}</td>'
        f"<td>{_esc(f['gate_id'])}</td><td>{_esc((f['doc_id'] or '')[:8])}</td>"
        f"<td>{_esc(f['field'] or '—')}</td><td>{_esc(f['severity'])}</td>"
        f"<td>{_esc(f['repair_owner'])}</td><td>{_esc(f['recommendation'])}</td></tr>"
        for f in findings
    )
    rejected_rows = "".join(
        f"<tr><td>{_esc(model)}</td><td>{_esc(n)}</td></tr>"
        for model, n in s["rejected_by_drafter"].items()
    )
    qualifiers = "".join(f"<li>{_esc(q)}</li>" for q in _QUALIFIERS)
    non_claims = "".join(f"<li>{_esc(c)}</li>" for c in _NON_CLAIMS)

    page = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>InvoiceLoop 支持矩阵</title><style>
:root {{ --bad:#b3261e; --warn:#8f5b00; --ok:#1a6b3c; --mute:#666; --line:#ddd; }}
body {{ font: 14px/1.5 -apple-system, "PingFang SC", sans-serif; margin: 2rem auto; max-width: 1440px; color:#222; }}
h1 {{ font-size: 1.5rem; }} h2 {{ margin-top: 2.2rem; border-bottom: 2px solid #444; padding-bottom:.2rem; }}
.thesis {{ background:#fff8e6; border:1px solid #e0c97f; padding:.8rem 1rem; border-radius:6px; }}
.thesis b {{ color:#7a5b00; }}
.caveats {{ background:#fdecea; border:1px solid #f0b4ae; padding:.8rem 1rem; border-radius:6px; }}
.grid {{ display:flex; gap:1rem; flex-wrap:wrap; margin:1rem 0; }}
.stat {{ border:1px solid var(--line); border-radius:6px; padding:.6rem 1rem; min-width:9rem; }}
.stat b {{ display:block; font-size:1.4rem; }}
table {{ border-collapse:collapse; width:100%; }}
th, td {{ border:1px solid var(--line); padding:.3rem .5rem; vertical-align:top; text-align:left; }}
th {{ background:#f4f4f4; position:sticky; top:0; }}
.badge {{ padding:.1rem .45rem; border-radius:10px; color:#fff; font-size:.85em; white-space:nowrap; }}
.badge.unsupported {{ background:var(--bad); }} .badge.single_source {{ background:var(--warn); }} .badge.corroborated {{ background:var(--ok); }}
.disputed {{ background:#5b33a2; color:#fff; padding:.1rem .45rem; border-radius:10px; font-size:.85em; margin-left:.3rem; white-space:nowrap; }}
.tier {{ border:1px solid #9db; border-radius:4px; padding:0 .3rem; font-size:.8em; margin-right:.2rem; white-space:nowrap; }}
.tier.none {{ border-color:#ccc; color:var(--mute); }}
.gate {{ font-size:.75em; margin-right:.25rem; padding:0 .2rem; border-radius:3px; white-space:nowrap; }}
.gate.pass {{ background:#e6f4ea; }} .gate.warning {{ background:#fdf3e0; }} .gate.fail {{ background:#fdecea; color:var(--bad); }} .gate.unavailable {{ color:#aaa; }}
ul.lim {{ margin:0; padding-left:1.1rem; color:var(--mute); font-size:.85em; }}
.span {{ display:flex; gap:.5rem; margin-top:.4rem; align-items:flex-start; }}
.crop {{ max-width:340px; border:1px solid var(--line); }}
.span-meta {{ font-size:.8em; color:#444; }}
.ocr {{ color:var(--mute); }}
.rejected {{ font-size:.8em; color:var(--bad); }} .rejected ul {{ margin:.1rem 0; padding-left:1.1rem; }}
.blocking {{ font-size:.8em; color:var(--bad); font-weight:600; }}
tr.blk td {{ background:#fdecea; }}
.novalue {{ color:var(--mute); }}
.footer {{ margin-top:2rem; font-size:.8em; color:var(--mute); border-top:1px solid var(--line); padding-top:.6rem; word-break:break-all; }}
</style></head><body>
<h1>InvoiceLoop —— 支持矩阵</h1>
<div class="thesis"><b>抽取的正确性不可信,支持关系可验证。</b><br>
本 panel 交付的是每个字段可机械验证的支持关系:证据片段、来源层级、六个门禁裁决、
以及哪里说不准。它<b>不</b>说「这个值是对的」。复核队列按支持强度升序 ——
排在最前的就是系统明确表示自己不知道、或证据互相打架的地方。</div>

<h2>这是什么、不主张什么</h2>
<ul>{non_claims}</ul>

<h2>总览(全部可从存盘证据重算)</h2>
<div class="grid">
<div class="stat"><b>{s['docs']}</b>文档</div>
<div class="stat"><b>{s['slots']}</b>字段槽</div>
<div class="stat"><b style="color:var(--bad)">{s['by_strength']['unsupported']}</b>无支持</div>
<div class="stat"><b style="color:var(--warn)">{s['by_strength']['single_source']}</b>单一来源</div>
<div class="stat"><b style="color:var(--ok)">{s['by_strength']['corroborated']}</b>多方印证</div>
<div class="stat"><b>{s['requires_adjudication']}</b>需人工裁决</div>
<div class="stat"><b>{s['applicability_disputed']}</b>口径争议(不进错误率)</div>
<div class="stat"><b>{s['blocking_findings']}</b>阻断发现</div>
<div class="stat"><b>{s['drafts_rejected']}</b>草稿被冻结事务拒绝</div>
</div>
<p>分诊排序经 160 份预注册文档实测:门禁挑出的字段偏差率 50.0%,未挑出的 11.8%,
集中度 4.2× —— 看 46% 的字段覆盖 78% 的偏差。分诊不要求任何一档「可信」,
只要求排序优于随机。</p>

<h2>校准的三条限定(ARCHITECTURE.md §8,宪章六要求同屏展示)</h2>
<div class="caveats"><ol>{qualifiers}</ol></div>

<h2>冻结事务拦下的草稿(按来源)</h2>
<table><tr><th>来源</th><th>拒绝数</th></tr>{rejected_rows}</table>
<p style="font-size:.85em;color:var(--mute)">拒绝理由都是文档级绑定:值不在该发票的独立 OCR 里
(token 匹配 &lt;80%)。GPT 5.6 SOL 那 118 行是第六轮真实错位事故 —— 当时靠事后 OCR 考古发现,
现在当场被拒。</p>

<h2>复核队列(支持强度升序 = 先看最上面的)</h2>
<table><thead><tr><th>doc</th><th>字段</th><th>值</th><th>支持强度</th><th>来源层级</th><th>门禁</th><th>证据与限制</th></tr></thead>
<tbody>{rows_html}</tbody></table>

<h2>门禁发现({len(findings)} 条,其中阻断 {len(blocking)} 条)</h2>
<table><thead><tr><th>ID</th><th>门禁</th><th>doc</th><th>字段</th><th>严重度</th><th>修复路由</th><th>建议</th></tr></thead>
<tbody>{findings_html}</tbody></table>

<div class="footer">
输入签名(§5.3):artifact_digest={artifact_digest}<br>
field_ledger sha256={ledger['sha256']}<br>
本 panel 由 Python 从冻结工件渲染;上面每个数字都可用同一份存盘证据零 API 重算。
</div>
</body></html>"""
    out = run_dir / "support_panel.html"
    out.write_text(page, encoding="utf-8")
    return out
