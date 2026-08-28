"""support_panel.html — static, offline, no server. The demo's main view.

The discipline for what goes on the panel (charter rule six plus GOAL.md; the
fourth item is the one most easily sanded off near a deadline, so hold it):

- It must say that extraction itself is untrustworthy. That is not a
  contradictory footnote; it is the reason this exists.
- Every gate's interception rate carries the three qualifications from
  ARCHITECTURE.md §8.
- Convention disputes (label_convention_disputed) are shown explicitly and enter
  no "error" count.
- The footer gives the input signature: every number on the panel recomputes from
  stored evidence with zero API calls.
"""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

_STRENGTH_LABEL = {
    "unsupported": "unsupported",
    "single_source": "single source",
    "corroborated": "corroborated",
}
_TIER_LABEL = {
    "dws_extraction": "DWS extraction",
    "independent_ocr": "independent OCR",
    "vision_reading": "full-page vision",
    "arithmetic": "arithmetic identity",
}
_VERDICT_LABEL = {"pass": "pass", "warning": "warn", "fail": "fail", "unavailable": "—"}
_DECISION_LABEL = {
    "accept": "human-accepted",
    "reject": "human-rejected",
    "correct": "human-corrected",
    "abstain": "human-abstained",
}
_GATE_SHORT = {
    "arithmetic_consistency": "arith",
    "field_wellformed": "form",
    "extraction_present": "present",
    "citation_holds": "citation",
    "cross_mode_agreement": "dual-mode",
    "visual_corroboration": "vision",
}

_QUALIFIERS = [
    "The gates were designed after seeing round-one data (self-declared in "
    "THRESHOLDS.md §6c B-4), an optimistic bias; held-out confirmation ran "
    "2026-08-02 (100 documents, pre-registered criteria, H1–H6 all passed, "
    "lift 3.04×) — see docs/HELDOUT.md.",
    "DocILE annotations are themselves disputed — round-four per-document "
    "vision reading found 8 of 14 cases were annotation errors.",
    "The calibration set is all US broadcast-advertising invoices; the held-out "
    "set reproduced triage concentration across DocILE types, but behavior "
    "outside DocILE remains unknown.",
]

_NON_CLAIMS = [
    "No claim that DWS is trustworthy or that extraction quality improved — six "
    "pre-registered rounds say the opposite.",
    "No claim of semantic correctness — the output is a support matrix, not "
    "a verdict that any value is right.",
    "No claim of unattended operation — unsupported rows are designed to be "
    "seen by a human.",
    "No claim of production readiness — 160 documents, English, one vendor, "
    "one point in time.",
]


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _chips(verdicts: dict) -> str:
    from .gateinfo import tooltip

    return "".join(
        f'<span class="gate {v}" title="{_esc(tooltip(g, v, "en"))}">{_esc(_GATE_SHORT.get(g, g))}:{_VERDICT_LABEL.get(v, v)}</span>'
        for g, v in sorted(verdicts.items())
    )


def _span_html(span: dict, run_dir: Path) -> str:
    crop = ""
    if span.get("crop") and (run_dir / "crops" / span["crop"]).exists():
        crop = (f'<a href="crops/{_esc(span["crop"])}" target="_blank">'
                f'<img class="crop" src="crops/{_esc(span["crop"])}" loading="lazy" '
                f'alt="{_esc(span["span_id"])}"></a>')
    return (
        f'<div class="span">{crop}<div class="span-meta">'
        f'<b>{_esc(span["span_id"])}</b> p{span["page"]} · label: <i>{_esc(span["printed_label"])}</i><br>'
        f'<span class="ocr">OCR: {_esc(span["ocr_text"][:160])}</span></div></div>'
    )


def _overlay_html(slot: dict | None) -> str:
    """一行的人工裁决叠加层:current human state + 历史规模。

    原 DWS/冻结值永远留在原处(值列不动),修正值只出现在这里 ——
    裁决是叠加,不是篡改。链冲突显式标出,不替人猜。
    """
    if not slot:
        return ""
    if slot["conflict"]:
        return ('<div class="human conflict"><b>Adjudication chain conflict:</b> '
                'multiple tips — fix adjudication_ledger.jsonl by hand; the system '
                'will not guess which one counts</div>')
    tip = slot["tip"]
    # label 也要转义:v1/手编账本的 decision 字段没经过枚举校验,不能信
    label = _esc(_DECISION_LABEL.get(tip["decision"], tip["decision"]))
    corrected = (f' → “{_esc(tip["corrected_value"])}”'
                 if tip["decision"] == "correct" else "")
    supersedes = (f' · supersedes {_esc(tip["supersedes_decision_id"])}'
                  if tip.get("supersedes_decision_id") else "")
    legacy = ' · <span title="v1 format, chained deterministically at load">v1 entry</span>' if tip.get("legacy") else ""
    n = len(slot["history"])
    history = f' · <a href="adjudication_ledger.jsonl">{n} in history</a>' if n > 1 else ""
    return (f'<div class="human"><b>{label}{corrected}</b>'
            f'({_esc(tip["decision_id"])} · {_esc(tip["adjudicator"])} · '
            f'{_esc(tip["decided_at"])}{supersedes}{legacy})<br>'
            f'<i>rationale: {_esc(tip["rationale"])}</i>{history}</div>')


def _row_html(row: dict, spans_by_id: dict, run_dir: Path, overlay: dict | None = None) -> str:
    strength = row["support_strength"]
    tiers = " ".join(
        f'<span class="tier">{_esc(_TIER_LABEL.get(t, t))}</span>' for t in row["source_tiers"]
    ) or '<span class="tier none">none</span>'
    applicability = (
        '<span class="disputed">convention dispute</span>'
        if row["applicability"] == "label_convention_disputed" else ""
    )
    limitations = "".join(f"<li>{_esc(x)}</li>" for x in row["limitations"])
    evidence = []
    containing = [spans_by_id[s] for s in row["span_ids"] if s in spans_by_id]
    cited = [spans_by_id[s] for s in row.get("cited_span_ids", []) if s in spans_by_id]
    cited_only = [s for s in cited if s["span_id"] not in set(row["span_ids"])]
    if containing:
        evidence.append('<div class="evlabel">value falls here (corroboration):</div>')
        evidence.extend(_span_html(s, run_dir) for s in containing)
    if cited_only:
        # 被拒/未落在引用区的行:这里才是复核者裁决"值到底在不在页上"的依据
        evidence.append('<div class="evlabel">DWS points here (for review):</div>')
        evidence.extend(_span_html(s, run_dir) for s in cited_only)
    if not containing and not cited_only:
        # 没有任何引用(DWS 没返回值时总是如此)—— 复核者需要整页自己找
        from .evidence import page_images
        pages = page_images(run_dir / "pages", row["doc_id"])
        if pages:
            links = " ".join(
                f'<a href="pages/{p.name}" target="_blank">p{i + 1}</a>'
                for i, p in enumerate(pages))
            evidence.append(f'<div class="evlabel">no cited region — see the full page: {links}</div>')
    rejected = ""
    if row["rejections"]:
        items = "".join(
            f'<li>{_esc(r["drafted_by"])}: “{_esc(r["value"])}” — {_esc(r["reason"])}'
            + (f'(coverage {r["coverage"]})' if r.get("coverage") is not None else "")
            + "</li>"
            for r in row["rejections"]
        )
        rejected = f'<div class="rejected"><b>rejected at freeze:</b><ul>{items}</ul></div>'
    blocking = ""
    if row["blocking_findings"]:
        blocking = f'<div class="blocking">blocking findings: {_esc(", ".join(row["blocking_findings"]))}</div>'
    human = _overlay_html(overlay)
    return f"""<tr class="row {strength}">
<td class="doc" title="{_esc(row['doc_id'])}">{_esc(row['doc_id'][:8])}</td>
<td class="field">{_esc(row['field'])}</td>
<td class="value">{_esc(row['value'])}{' <span class="novalue">(no value)</span>' if row['value'] in (None, '') else ''}</td>
<td><span class="badge {strength}">{_STRENGTH_LABEL[strength]}</span>{applicability}</td>
<td>{tiers}</td>
<td class="gates">{_chips(row['gate_verdicts'])}</td>
<td class="detail"><ul class="lim">{limitations}</ul>{''.join(evidence)}{rejected}{blocking}{human}</td>
</tr>"""


def render_panel(
    run_dir: Path,
    *,
    support: dict,
    gate_report: dict,
    spans: list[dict],
    ledger: dict,
    artifact_digest: str,
    out_of_calibration: bool = False,
) -> Path:
    """从 run 目录的冻结工件渲染 panel。只读工件,不重算任何门禁。

    out_of_calibration:输入契约(§12.3)—— 非校准集文档必须声明
    "校准数字不直接适用",不声明就是把校准的信心偷渡给没测过的分布。
    """
    run_dir = Path(run_dir)
    spans_by_id = {s["span_id"]: s for s in spans}
    s = support["summary"]

    # 人工裁决叠加层:panel 只是投影 —— 裁决的权威是 adjudication_ledger.jsonl,
    # 这里读出来叠上去;一条没有就什么都不叠
    from .review import load_decisions, project, target_id_for
    from .snapshot import load_or_derive_snapshot

    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    decisions = load_decisions(run_dir)
    slots = project(decisions)
    # 账本自报的 sha256 必须自己重算比对 —— 只打印文件里写着的哈希,
    # 等于让被改过的账本自己证明自己没改过(评审 P1)
    ledger_check = "matches the declared digest"
    recomputed = hashlib.sha256(
        json.dumps({"claims": ledger["claims"]}, sort_keys=True,
                   ensure_ascii=False).encode()
    ).hexdigest()
    if recomputed != ledger["sha256"]:
        ledger_check = "⚠ does not match the declared digest — the ledger was modified"
    orphans = [e for e in decisions if e.get("orphan")]
    rows_html = "\n".join(
        _row_html(r, spans_by_id, run_dir,
                  slots.get(target_id_for(snapshot_id, r["doc_id"], r["field"])))
        for r in support["rows"]
    )

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
    # 跨文档查重(C8):从同一冻结账本重算(确定性),与 gate_report 里的
    # finding 互为印证 —— 这里给并排视图,finding 给裁决路由
    from .crossdoc import duplicate_groups

    dup_groups = duplicate_groups(ledger["claims"])
    dup_section = ""
    if dup_groups:
        kind_label = {"content_conflict": "same number, different content", "resubmission": "suspected resubmission"}
        group_html = ""
        for g in dup_groups:
            rows_g = "".join(
                f"<tr><td>{_esc(d['doc_id'][:12])}</td><td>{_esc(g['invoice_number'])}</td>"
                f"<td>{_esc(g['seller'][:24])}</td><td>{_esc(d['total_gross'] or '—')}</td>"
                f"<td>{_esc(d['issue_date'] or '—')}</td></tr>"
                for d in g["docs"]
            )
            group_html += (
                f"<table><tr><th colspan='5' style='text-align:left'>"
                f"{_esc(kind_label[g['kind']])} — invoice number {_esc(g['invoice_number'])}"
                f"</th></tr>"
                f"<tr><th>document</th><th>number</th><th>seller</th><th>gross</th><th>issue date</th></tr>"
                f"{rows_g}</table>"
            )
        dup_section = (
            f"<h2>Cross-document duplicate check ({len(dup_groups)} groups)</h2>"
            "<p>Invoices sharing a number and seller appear in this document set. "
            "This is not a verdict — content conflicts and resubmissions both "
            "require a human to view the two side by side; they are already in "
            "the review queue and enter no error rate.</p>"
            f"{group_html}"
        )
    qualifiers = "".join(f"<li>{_esc(q)}</li>" for q in _QUALIFIERS)
    non_claims = "".join(f"<li>{_esc(c)}</li>" for c in _NON_CLAIMS)
    decided_stat = (f'<div class="stat"><b>{len(decisions)}</b>human-adjudicated '
                    f'(current state by supersession chain)</div>' if decisions else "")
    orphan_banner = ""
    if orphans:
        shown = ", ".join(_esc(e["decision_id"]) for e in orphans[:8])
        orphan_banner = (
            f'<div class="caveats"><b>⚠ {len(orphans)} adjudications are bound to a '
            f'different review_snapshot ({shown}) and are not projected onto this '
            f'panel.</b> They remain in adjudication_ledger.jsonl — typically a '
            f'ledger copied from another run. History is not hidden, but it may not '
            f'be misattributed onto the slots of this run.</div>'
        )
    ooc_banner = (
        '<div class="caveats"><b>Input is outside the calibration set (§12 input '
        'contract).</b> These documents took part in no calibration or held-out '
        'validation: the calibration figures on this panel (4.2×, 78%) do not '
        'directly apply to them (§8 qualifier three). The per-document mechanical '
        'checks — binding, gates, freezing, adjudication — need no calibration '
        'and hold as usual.</div>'
        if out_of_calibration else ""
    )

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>InvoiceLoop support matrix</title><style>
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
.evlabel {{ font-size:.78em; font-weight:600; color:#555; margin-top:.4rem; }}
.rejected {{ font-size:.8em; color:var(--bad); }} .rejected ul {{ margin:.1rem 0; padding-left:1.1rem; }}
.blocking {{ font-size:.8em; color:var(--bad); font-weight:600; }}
.human {{ font-size:.85em; background:#eef4ff; border:1px solid #b9cdf0; border-radius:4px;
         padding:.3rem .5rem; margin-top:.4rem; }}
.human.conflict {{ background:#fdecea; border-color:#f0b4ae; color:var(--bad); }}
.human a {{ color:#3457a8; }}
tr.blk td {{ background:#fdecea; }}
.novalue {{ color:var(--mute); }}
.footer {{ margin-top:2rem; font-size:.8em; color:var(--mute); border-top:1px solid var(--line); padding-top:.6rem; word-break:break-all; }}
</style></head><body>
<h1>InvoiceLoop — support matrix</h1>
<div class="thesis"><b>Extraction correctness is untrustworthy; support is verifiable.</b><br>
This panel delivers a mechanically verifiable support relation for every field: evidence
spans, source tiers, six deterministic gate verdicts, and where the system cannot say.
It does <b>not</b> say "this value is right". The review queue is sorted by ascending
support strength — the top rows are exactly where the system says it does not know,
or where the evidence disagrees with itself.</div>
{ooc_banner}
{orphan_banner}

<h2>What this is, and what it does not claim</h2>
<ul>{non_claims}</ul>

<h2>Overview (every number recomputes from stored evidence)</h2>
<div class="grid">
<div class="stat"><b>{s['docs']}</b>documents</div>
<div class="stat"><b>{s['slots']}</b>field slots</div>
<div class="stat"><b style="color:var(--bad)">{s['by_strength']['unsupported']}</b>unsupported</div>
<div class="stat"><b style="color:var(--warn)">{s['by_strength']['single_source']}</b>single source</div>
<div class="stat"><b style="color:var(--ok)">{s['by_strength']['corroborated']}</b>corroborated</div>
<div class="stat"><b>{s.get('human_queue', s['requires_adjudication'])}</b>awaiting human</div>
<div class="stat"><b>{s.get('machine_decided', '—')}</b>machine-decided</div>
<div class="stat"><b>{s.get('machine_absent', '—')}</b>policy-confirmed absent</div>
<div class="stat"><b>{s['applicability_disputed']}</b>convention disputes (outside any error rate)</div>
<div class="stat"><b>{s['blocking_findings']}</b>blocking findings</div>
<div class="stat"><b>{s['drafts_rejected']}</b>drafts rejected at freeze</div>
{decided_stat}
</div>
<p>Calibration evidence for the triage ordering (every number recomputes):
six calibration rounds (dws-derisk, R-D routing projection) measured deviation
rates of 50.0% vs 11.8% with a concentration of 4.2×; this repository's
projection re-measured <b>4.10×</b> on 160 pre-registered calibration documents
(pinned by test_triage_concentration.py), and <b>3.04×</b> on a 100-document
held-out set (docs/HELDOUT.md, pre-registered floor 1.5×) — reviewing 46% of
fields covers 78% of the deviation. Triage does not require any tier to be
"trustworthy"; it only requires the ordering to beat random.</p>

<h2>The three calibration qualifiers (ARCHITECTURE.md §8; charter rule six requires them on screen)</h2>
<div class="caveats"><ol>{qualifiers}</ol></div>

<h2>Drafts stopped by the freeze transaction (by drafter)</h2>
<table><tr><th>drafter</th><th>rejected</th></tr>{rejected_rows}</table>
<p style="font-size:.85em;color:var(--mute)">Every rejection reason is document-level
binding: the value is absent from that invoice's independent OCR (token match
&lt;80%). The 118 GPT 5.6 SOL rows are the round-six real misbinding incident —
discovered by after-the-fact OCR archaeology then, rejected on the spot now.</p>

{dup_section}

<h2>Review queue (ascending support strength = look at the top first)</h2>
<table><thead><tr><th>doc</th><th>field</th><th>value</th><th>support</th><th>source tiers</th><th>gates</th><th>evidence &amp; limitations</th></tr></thead>
<tbody>{rows_html}</tbody></table>

<h2>Gate findings ({len(findings)} total, {len(blocking)} blocking)</h2>
<table><thead><tr><th>ID</th><th>gate</th><th>doc</th><th>field</th><th>severity</th><th>repair route</th><th>recommendation</th></tr></thead>
<tbody>{findings_html}</tbody></table>

<div class="footer">
Input signature (§5.3): artifact_digest={artifact_digest}<br>
field_ledger sha256={ledger['sha256']} ({ledger_check})<br>
review_snapshot_id={snapshot_id} (the full snapshot human adjudications bind to, not just the ledger)<br>
Adjudication ledger had {len(decisions)} entries at render time — if this differs from the file's line count, the panel is stale; run render to rebuild<br>
This panel was rendered by Python from frozen artifacts; every number on it recomputes from the same stored evidence with zero API calls.
</div>
</body></html>"""
    out = run_dir / "support_panel.html"
    out.write_text(page, encoding="utf-8")
    return out


def render_panel_from_run(run_dir: Path) -> Path:
    """只从盘上工件重渲 panel —— panel 是纯投影,任何时候都可重建。

    裁决后重渲、HTML 弄丢了重建、换了样式重出,都走这里;不重算任何门禁。
    """
    run_dir = Path(run_dir)

    def _load(name: str):
        return json.loads((run_dir / name).read_text(encoding="utf-8"))

    from .evidence import digest_registry

    manifest = _load("run_manifest.json")
    panel = render_panel(
        run_dir,
        support=_load("support_matrix.json"),
        gate_report=_load("gate_report.json"),
        spans=_load("evidence_span_registry.json"),
        ledger=_load("field_ledger.json"),
        artifact_digest=digest_registry(_load("artifact_registry.json")),
        out_of_calibration=manifest.get("out_of_calibration", False),
    )
    # deliverable 与 panel 同为纯投影,同生命周期:裁决变了,两者一起重算
    from .deliver import write_deliverable

    write_deliverable(run_dir)
    return panel
