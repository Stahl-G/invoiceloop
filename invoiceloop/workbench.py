"""H1 评委面向复核工作台 —— 本地 loopback Web 应用(127.0.0.1,零新增依赖)。

形态决定(钉死,别悄悄改):
- **stdlib http.server,不加 Flask/FastAPI** —— pyproject 运行时仍只有
  requests 一个依赖,评委 clean clone 后 pip install . 即可,不多装任何东西。
- **server-rendered HTML + 渐进增强 JS** —— 无 JS 时除浏览器上传外全部可用
  (上传可回落到输入契约:把 PDF 放进 workspace/input/pdfs/)。
- **人只写裁决,且只能写裁决** —— /decide 走 adjudicate.append_adjudication
  的同一套校验(快照一致性、三元一致、supersession),工作台不开任何后门。
- **decided_at 由服务器在点击时盖章** —— 点击就是人给出时间的动作;
  裁决是人的输入不是重算工件,不违反"工件不读墙钟"(run 工件仍全确定)。
- 视觉纪律借 briefloop-prototypes:DWS/模型值 = 紫(advisory,永不绿),
  人工确认 = 蓝,确定性通过 = 绿,阻断 = 红,不可用 = 灰。

路由契约(tests/test_workbench.py 以此为准):
    GET  / /queue /report /upload /deliver /files/<run>/<rel> /download/<run>/audit_bundle.zip
    POST /decide /upload?filename= /ingest /bundle /verify(原始字节)
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .ingest import sanitise_doc_id
from .review import load_decisions, project, target_id_for
from .snapshot import (
    allocate_run_dir,
    build_input_manifest,
    find_run_by_fingerprint,
    load_or_derive_snapshot,
)

HOST = "127.0.0.1"
MAX_UPLOAD = 50 * 1024 * 1024  # 50MB,上传上限,先查 Content-Length 再读体

#: Host 白名单 —— loopback 不等于安全:浏览器跨站表单可以直接 POST 到
#: 127.0.0.1(CSRF),DNS rebinding 可以让恶意页面以任意 Host 读这个服务。
#: 两道闸:Host 头必须在此列(杀 rebinding);POST 的 Origin 若在且外来 = 403
#: (杀跨站表单;现代浏览器跨源 POST 必带 Origin)。
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}

# ---------------------------------------------------------------------- i18n

_T = {
    "en": {
        "brand": "InvoiceLoop Workbench",
        "thesis": "Extraction correctness is untrustworthy; support is verifiable. "
                  "You decide — the system shows evidence, not verdicts.",
        "queue": "Review queue", "report": "Delivery report",
        "upload": "Upload", "deliver": "Deliver & verify",
        "all": "All", "pending": "Pending", "done": "Decided",
        "reviewed": "{x} / {y} reviewed",
        "accept": "Accept", "reject": "Reject", "correct": "Correct", "abstain": "Abstain",
        "corrected_ph": "corrected value",
        "rationale_ph": "Issue / rationale (required) — write down what's wrong",
        "adjudicator_ph": "reviewer name",
        "issue_chips": ["wrong value", "wrong location", "illegible",
                        "label-convention conflict", "not on page", "other"],
        "submit": "Submit decision", "confirm": "Confirm",
        "current_note": "Current: {id} · {decision} · {by} · {at} — submitting supersedes it",
        "reason": "Reason",
        "orphan_note": "{n} decision(s) bound to a different snapshot — not projected here",
        "conflict_note": "Decision chain conflict — fix adjudication_ledger.jsonl manually; new decisions blocked",
        "evidence": "Evidence & limitations",
        "no_value": "(no value)",
        "value_here": "Value found here (corroborating):",
        "cited_here": "DWS pointed here (for review):",
        "no_citation": "No citation region — see full page:",
        "ooc": "Inputs are outside the calibration set (§12): calibration numbers "
               "(4.2×, 78%) do not directly apply. Per-document mechanical checks "
               "(binding, gates, freeze, adjudication) need no calibration.",
        "stat_reviewed": "slots reviewed", "stat_corrections": "corrections",
        "stat_decisions": "decisions total",
        "corrections_title": "Corrections (deliverable)",
        "residual": "Residual risk: the reviewed queue covers most measured deviations "
                    "(calibration 4.2×, held-out 3.04× lift), but errors outside the "
                    "reviewed fraction remain — the residual is NOT zero. "
                    "See docs/HELDOUT.md for the pre-registered numbers.",
        "was": "was", "now": "now",
        "upload_title": "Upload invoices",
        "drop_hint": "…or drop PDFs into workspace/input/pdfs/ directly (input contract), "
                     "then press Process.",
        "same_name_note": "Same-name file with new content: its old OCR and DWS responses "
                          "are invalidated automatically (re-OCR/re-extract on next Process).",
        "start": "Process",
        "extract_cb": "Extract with DWS (spends API credits, needs DWS_API_KEY)",
        "no_key": "DWS_API_KEY not set — local OCR only; missing extraction blocks per charter",
        "build_bundle": "Build audit bundle",
        "download": "Download audit_bundle.zip",
        "verify_title": "Verify a bundle (offline)",
        "choose_zip": "Choose .zip",
        "verify_btn": "Verify",
        "notice_recorded": "Decision recorded.",
        "notice_recorded_stale": "Decision recorded; panel refresh failed — run: python3 -m invoiceloop render --run ",
        "notice_replayed": "Same inputs — replaying the existing run (runs are immutable).",
        "notice_ingested": "New run created.",
        "notice_bundled": "Bundle built.",
        "notice_uploaded": "Uploaded.",
        "snapshot": "review_snapshot_id",
        "back": "← back to queue",
        "error_title": "Blocked",
        "runs": "runs",
        "no_runs": "No runs yet — upload invoices to start.",
    },
    "zh": {
        "brand": "InvoiceLoop 工作台",
        "thesis": "抽取的正确性不可信,支持关系可验证。你裁决,系统只给证据,不给判决。",
        "queue": "复核队列", "report": "交付报告",
        "upload": "上传", "deliver": "交付与验证",
        "all": "全部", "pending": "待复核", "done": "已裁决",
        "reviewed": "已复核 {x} / {y}",
        "accept": "接受", "reject": "拒绝", "correct": "修正", "abstain": "弃权",
        "corrected_ph": "修正值",
        "rationale_ph": "发现的问题 / 理由(必填)—— 把问题直接写在这里",
        "adjudicator_ph": "裁决人",
        "issue_chips": ["值不对", "位置不对", "看不清", "口径冲突", "页面上没有", "其他"],
        "submit": "提交裁决", "confirm": "确认",
        "current_note": "当前裁决 {id} · {decision} · {by} · {at} —— 提交将取代它",
        "reason": "理由",
        "orphan_note": "{n} 条裁决绑定到其他快照 —— 不在此投影",
        "conflict_note": "裁决链冲突 —— 请人工整理 adjudication_ledger.jsonl;新裁决已阻断",
        "evidence": "证据与限制",
        "no_value": "(无值)",
        "value_here": "值落在这里(印证):",
        "cited_here": "DWS 指向这里(复核用):",
        "no_citation": "无引用区,看整页:",
        "ooc": "输入不在校准集内(§12):校准数字(4.2×、78%)不直接适用;"
               "逐文档的机械核对(绑定、门禁、冻结、裁决)不需要校准,照常成立。",
        "stat_reviewed": "槽位已复核", "stat_corrections": "处修正",
        "stat_decisions": "条裁决总数",
        "corrections_title": "修正清单(交付物)",
        "residual": "残余风险:复核队列覆盖了实测偏差的大头(校准 4.2×,留出集 lift 3.04×),"
                    "但未复核部分的错误仍在 —— 残余不是零。预注册数字见 docs/HELDOUT.md。",
        "was": "原值", "now": "改为",
        "upload_title": "上传发票",
        "drop_hint": "……也可以直接把 PDF 放进 workspace/input/pdfs/(输入契约),再点「开始处理」。",
        "same_name_note": "同名文件内容变化:旧 OCR 与旧 DWS 响应自动失效(下次处理重新 OCR/重抽)。",
        "start": "开始处理",
        "extract_cb": "调用 DWS 抽取(消耗 API credits,需要 DWS_API_KEY)",
        "no_key": "未配置 DWS_API_KEY —— 只做本地 OCR;抽取缺失按宪章四阻断",
        "build_bundle": "打 audit bundle",
        "download": "下载 audit_bundle.zip",
        "verify_title": "离线校验 bundle",
        "choose_zip": "选择 .zip",
        "verify_btn": "校验",
        "notice_recorded": "裁决已记录。",
        "notice_recorded_stale": "裁决已记录;panel 刷新失败 —— 跑:python3 -m invoiceloop render --run ",
        "notice_replayed": "输入未变 —— 重放既有 run(run 不可变)。",
        "notice_ingested": "已创建新 run。",
        "notice_bundled": "bundle 已打好。",
        "notice_uploaded": "已上传。",
        "snapshot": "review_snapshot_id",
        "back": "← 回到复核队列",
        "error_title": "阻断",
        "runs": "run 列表",
        "no_runs": "还没有 run —— 先上传发票。",
    },
}


def _t(lang: str, key: str, **kw) -> str:
    text = _T.get(lang, _T["en"]).get(key, _T["en"].get(key, key))
    return text.format(**kw) if kw else text


def _esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


_JS = r"""
document.addEventListener('submit', function (e) {
  var form = e.target;
  if (!form.classList || !form.classList.contains('decide')) return;
  if (form.dataset.armed === '1') return;   // 第二次点击:放行
  e.preventDefault();
  var btn = form.querySelector('.wb-btn');
  var d = form.querySelector('input[name=decision]:checked');
  if (!d) return;
  form.dataset.armed = '1';
  btn.classList.add('armed');
  btn.dataset.orig = btn.textContent;
  btn.textContent = btn.dataset.confirm + ': ' + d.value + '?';
  setTimeout(function () {
    if (form.dataset.armed === '1') {
      form.dataset.armed = '';
      btn.classList.remove('armed');
      btn.textContent = btn.dataset.orig;
    }
  }, 4000);
});
document.addEventListener('change', function (e) {
  if (e.target.name !== 'decision') return;
  var form = e.target.closest('form');
  // 换决策 = 上一次武装作废:确认文案必须说的是即将提交的那个决策
  if (form.dataset.armed === '1') {
    form.dataset.armed = '';
    var b = form.querySelector('.wb-btn');
    b.classList.remove('armed');
    b.textContent = b.dataset.orig;
  }
  var corr = form.querySelector('.wb-corr');
  if (corr) { corr.disabled = e.target.value !== 'correct'; if (!corr.disabled) corr.focus(); }
});
document.addEventListener('click', function (e) {
  var chip = e.target.closest('.wb-issue-chip');
  if (!chip) return;
  var form = chip.closest('form');
  var ta = form.querySelector('.wb-rationale');
  ta.value = (ta.value ? ta.value + '; ' : '') + chip.dataset.text;
  ta.focus();
});
document.addEventListener('DOMContentLoaded', function () {
  // 修正值输入:HTML 里不带 disabled(无 JS 也要能提交 correct ——
  // 语义由服务器守);有 JS 才按当前选择禁用,纯渐进增强
  document.querySelectorAll('form.decide').forEach(function (form) {
    var d = form.querySelector('input[name=decision]:checked');
    var corr = form.querySelector('.wb-corr');
    if (corr && (!d || d.value !== 'correct')) corr.disabled = true;
  });
  var fi = document.getElementById('wb-files');
  if (fi) fi.addEventListener('change', async function () {
    var list = document.getElementById('wb-ul');
    for (var f of fi.files) {
      var li = document.createElement('li');
      li.textContent = f.name + ' …';
      list.appendChild(li);
      try {
        var r = await fetch('/upload?filename=' + encodeURIComponent(f.name),
                            { method: 'POST', body: f });
        li.textContent = f.name + (r.ok ? ' ✓' : ' ✗ HTTP ' + r.status);
      } catch (err) { li.textContent = f.name + ' ✗'; }
    }
  });
  // verify 也走 fetch:file input 只有 multipart 或原始字节两条路,
  // Python 3.14 没有 cgi,不自己糊 multipart —— 原始字节最干净
  var zi = document.getElementById('wb-zip');
  if (zi) zi.addEventListener('change', async function () {
    var out = document.getElementById('wb-verify-result');
    var f = zi.files[0];
    if (!f) return;
    out.textContent = '…';
    try {
      var r = await fetch('/verify?lang=' + (document.documentElement.lang || 'en'),
                          { method: 'POST', body: f });
      out.innerHTML = await r.text();
    } catch (e) { out.textContent = '✗'; }
  });
});
"""

_DECISIONS = ("accept", "reject", "correct", "abstain")
_STRENGTH_LABEL = {
    "en": {"unsupported": "unsupported", "single_source": "single source",
           "corroborated": "corroborated"},
    "zh": {"unsupported": "无支持", "single_source": "单一来源", "corroborated": "多方印证"},
}
_GATE_SHORT = {
    "arithmetic_consistency": ("arith", "算术"),
    "field_wellformed": ("form", "形态"),
    "extraction_present": ("present", "在场"),
    "citation_holds": ("cite", "引用"),
    "cross_mode_agreement": ("2-mode", "双模式"),
    "visual_corroboration": ("vision", "读图"),
}
_VERDICT = {"pass": ("pass", "过"), "warning": ("warn", "警"),
            "fail": ("fail", "拒"), "unavailable": ("—", "—")}


# ---------------------------------------------------------------------- 加载

class RunCtx:
    """一个 run 目录的读取视图。run 不可变 + 裁决只追加 → 每请求现读现投,
    demo 规模下足够快,而且永远不会看到缓存的旧投影。"""

    def __init__(self, run_dir: Path):
        self.dir = Path(run_dir)
        self.name = self.dir.name

        def _load(name, default=None):
            path = self.dir / name
            if not path.exists():
                return default
            return json.loads(path.read_text(encoding="utf-8"))

        self.manifest = _load("run_manifest.json", {})
        self.matrix = _load("support_matrix.json", {"rows": [], "summary": {}})
        self.gate_report = _load("gate_report.json", {"findings": []})
        self.spans = _load("evidence_span_registry.json", [])
        self.ledger = _load("field_ledger.json", {"claims": []})
        self.snapshot_id = load_or_derive_snapshot(self.dir)["review_snapshot_id"]
        self.decisions = load_decisions(self.dir)
        self.projection = project(self.decisions)
        self.claim_by_slot = {(c["doc_id"], c["field"]): c["claim_id"]
                              for c in self.ledger["claims"]}
        self.spans_by_id = {s["span_id"]: s for s in self.spans}
        self.orphans = [d for d in self.decisions if d.get("orphan")]

    def slot(self, doc_id: str, field: str) -> dict | None:
        return self.projection.get(target_id_for(self.snapshot_id, doc_id, field))


# ---------------------------------------------------------------------- 页面

class Workbench:
    def __init__(self, workspace: Path):
        self.ws = Path(workspace)

    # ---- run 定位
    def runs(self) -> list[Path]:
        root = self.ws / "runs"
        if not root.is_dir():
            return []
        return sorted(p for p in root.glob("run-*") if p.is_dir())

    def current_run(self) -> Path | None:
        pointer = self.ws / "runs" / "current.json"
        if pointer.exists():
            try:
                named = self.ws / "runs" / json.loads(pointer.read_text())["run"]
                if (named / "event_log.jsonl").exists():
                    return named
            except (json.JSONDecodeError, KeyError):
                pass
        complete = [p for p in self.runs() if (p / "event_log.jsonl").exists()]
        return complete[-1] if complete else None

    def get_run(self, name: str | None) -> Path | None:
        if name:
            candidate = self.ws / "runs" / name
            if re.fullmatch(r"run-\d{4,}", name) and (candidate / "event_log.jsonl").exists():
                return candidate
            return None
        return self.current_run()

    # ---- 骨架
    def page(self, lang: str, active: str, body: str, *,
             run_name: str | None = None, notice: str = "", ooc: bool = False) -> str:
        tabs = []
        if run_name:
            for key, href in (
                ("queue", f"/queue?run={run_name}"),
                ("report", f"/report?run={run_name}"),
                ("deliver", f"/deliver?run={run_name}"),
                ("upload", "/upload"),
            ):
                cls = "wb-tab active" if key == active else "wb-tab"
                tabs.append(f'<a class="{cls}" href="{href}&lang={lang}">{_esc(_t(lang, key))}</a>')
        else:
            tabs.append(f'<a class="wb-tab{" active" if active == "upload" else ""}" '
                        f'href="/upload?lang={lang}">{_esc(_t(lang, "upload"))}</a>')
        other = "zh" if lang == "en" else "en"
        notice_html = f'<div class="wb-notice">{_esc(notice)}</div>' if notice else ""
        ooc_html = f'<div class="wb-banner">{_esc(_t(lang, "ooc"))}</div>' if ooc else ""
        runs_nav = ""
        if len(self.runs()) > 1:
            links = " ".join(
                f'<a class="wb-chip{" active" if p.name == run_name else ""}" '
                f'href="/queue?run={p.name}&lang={lang}">{p.name}</a>'
                for p in self.runs() if (p / "event_log.jsonl").exists()
            )
            runs_nav = f'<span class="wb-runs">{links}</span>'
        return f"""<!DOCTYPE html>
<html lang="{'zh' if lang == 'zh' else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(_t(lang, 'brand'))}</title>
<link rel="stylesheet" href="/assets.css">
</head><body>
<div class="wb-topbar"><div class="wb-topbar-inner">
<span class="wb-brand">{_esc(_t(lang, 'brand'))}</span>
<nav class="wb-tabs">{''.join(tabs)}</nav>
{runs_nav}
<span class="wb-lang"><a href="?lang={other}">{"中文" if other == "zh" else "EN"}</a></span>
</div></div>
<div class="wb-thesis">{_esc(_t(lang, 'thesis'))}</div>
{notice_html}{ooc_html}
<main class="wb-main">{body}</main>
<script src="/assets.js"></script>
</body></html>"""

    # ---- 复核队列
    def queue_page(self, lang: str, run_dir: Path, params: dict) -> str:
        ctx = RunCtx(run_dir)
        rows = ctx.matrix["rows"]
        decided = sum(1 for r in rows if (ctx.slot(r["doc_id"], r["field"]) or {}).get("tip"))
        filter_ = params.get("filter", ["all"])[0]
        filt_rows = []
        for r in rows:
            tip = (ctx.slot(r["doc_id"], r["field"]) or {}).get("tip")
            if filter_ == "pending" and tip:
                continue
            if filter_ == "done" and not tip:
                continue
            filt_rows.append((r, tip))
        n_pending = sum(1 for r in rows if not (ctx.slot(r["doc_id"], r["field"]) or {}).get("tip"))
        chips = " ".join(
            f'<a class="wb-chip{" active" if filter_ == k else ""}" '
            f'href="/queue?run={ctx.name}&filter={k}&lang={lang}">{_esc(_t(lang, k))}'
            f'{"(" + str(n_pending) + ")" if k == "pending" else ""}</a>'
            for k in ("all", "pending", "done")
        )
        adjudicator = params.get("adjudicator", [""])[0]
        cards = "\n".join(
            self.row_card(lang, ctx, r, tip, adjudicator) for r, tip in filt_rows
        )
        pct = int(100 * decided / len(rows)) if rows else 0
        body = f"""
<div class="wb-progress" title="{_esc(_t(lang, 'reviewed', x=decided, y=len(rows)))}">
<div class="wb-progress-bar" style="width:{pct}%"></div></div>
<p>{_esc(_t(lang, 'reviewed', x=decided, y=len(rows)))}</p>
<div class="wb-filters">{chips}</div>
{cards}
<div class="wb-footer">{_esc(_t(lang, 'snapshot'))}={_esc(ctx.snapshot_id)}<br>
field_ledger sha256={_esc(ctx.ledger.get('sha256', ''))} · invoiceloop {__version__}</div>"""
        notice = self._notice(lang, params)
        return self.page(lang, "queue", body, run_name=ctx.name, notice=notice,
                         ooc=ctx.manifest.get("out_of_calibration", False))

    def _notice(self, lang: str, params: dict) -> str:
        code = params.get("notice", [""])[0]
        if not code:
            return ""
        text = _t(lang, f"notice_{code}")
        if code == "recorded_stale":
            text += _esc(params.get("run", [""])[0])
        return text

    def row_card(self, lang: str, ctx: RunCtx, row: dict, tip: dict | None,
                 adjudicator: str) -> str:
        doc, field = row["doc_id"], row["field"]
        slot = ctx.slot(doc, field)
        conflict = bool(slot and slot["conflict"])
        orphans = [o for o in ctx.orphans if o["doc_id"] == doc and o["field"] == field]
        anchor = f"row-{doc}-{field}"

        strength = row["support_strength"]
        gates = "".join(
            f'<span class="wb-gate {v}" title="{_esc(g)}">'
            f'{_GATE_SHORT.get(g, (g, g))[0 if lang == "en" else 1]}:'
            f'{_VERDICT.get(v, (v, v))[0 if lang == "en" else 1]}</span>'
            for g, v in sorted(row["gate_verdicts"].items())
        )
        value = row["value"]
        value_html = (f'<span class="wb-value none">{_esc(_t(lang, "no_value"))}</span>'
                      if value in (None, "") else f'<span class="wb-value">{_esc(value)}</span>')
        if conflict:
            status = f'<span class="wb-status conflict">{_esc(_t(lang, "conflict_note"))}</span>'
        elif tip:
            label = _esc(_t(lang, tip["decision"]))
            corr = (f' → “{_esc(tip["corrected_value"])}”'
                    if tip["decision"] == "correct" else "")
            status = (f'<span class="wb-status {tip["decision"]}" '
                      f'title="{_esc(tip["decision_id"])} · {_esc(tip["adjudicator"])} · '
                      f'{_esc(tip["decided_at"])}">{label}{corr}</span>')
        else:
            status = f'<span class="wb-status pending">{_esc(_t(lang, "pending"))}</span>'

        return f"""<div class="wb-row" id="{_esc(anchor)}">
<div class="wb-row-head">
<span class="wb-doc" title="{_esc(doc)}">{_esc(doc[:8])}</span>
<span class="wb-field">{_esc(field)}</span>
{value_html}
<span class="wb-badge {strength}">{_esc(_STRENGTH_LABEL[lang][strength])}</span>
<span class="wb-gates">{gates}</span>
{status}
</div>
{self._evidence(lang, ctx, row)}
{self._decide_form(lang, ctx, row, tip, conflict, len(orphans), adjudicator)}
</div>"""

    def _evidence(self, lang: str, ctx: RunCtx, row: dict) -> str:
        parts = []
        containing = [ctx.spans_by_id[s] for s in row["span_ids"] if s in ctx.spans_by_id]
        cited = [ctx.spans_by_id[s] for s in row.get("cited_span_ids", [])
                 if s in ctx.spans_by_id and s not in row["span_ids"]]
        for label_key, spans in (("value_here", containing), ("cited_here", cited)):
            if not spans:
                continue
            parts.append(f'<div class="wb-evlabel">{_esc(_t(lang, label_key))}</div>')
            for s in spans:
                crop = ""
                if s.get("crop"):
                    src = f"/files/{ctx.name}/crops/{urllib.parse.quote(s['crop'])}"
                    crop = f'<a href="{src}" target="_blank"><img class="wb-crop" src="{src}" loading="lazy"></a>'
                parts.append(
                    f'<div class="wb-span">{crop}<div><b>{_esc(s["span_id"])}</b> '
                    f'p{s["page"]} · <span class="wb-label">{_esc(s["printed_label"])}</span><br>'
                    f'<span class="wb-ocr">{_esc(s["ocr_text"][:160])}</span></div></div>')
        if not containing and not cited:
            pages = sorted((ctx.dir / "pages").glob(f"{row['doc_id']}-*.png")) \
                if (ctx.dir / "pages").exists() else []
            if pages:
                links = " ".join(
                    f'<a href="/files/{ctx.name}/pages/{p.name}" target="_blank">p{i + 1}</a>'
                    for i, p in enumerate(pages))
                parts.append(f'<div class="wb-evlabel">{_esc(_t(lang, "no_citation"))} {links}</div>')
        if row["rejections"]:
            items = "".join(
                f'<li>{_esc(r["drafted_by"])}: “{_esc(r["value"])}” — {_esc(r["reason"])}</li>'
                for r in row["rejections"])
            parts.append(f'<div class="wb-rejected"><ul>{items}</ul></div>')
        if row["blocking_findings"]:
            parts.append(f'<div class="wb-blocking">{_esc(", ".join(row["blocking_findings"]))}</div>')
        if row["limitations"]:
            items = "".join(f"<li>{_esc(x)}</li>" for x in row["limitations"])
            parts.append(f"<ul>{items}</ul>")
        inner = "".join(parts) or "—"
        return (f'<details class="wb-evidence"><summary>{_esc(_t(lang, "evidence"))}'
                f"</summary>{inner}</details>")

    def _decide_form(self, lang: str, ctx: RunCtx, row: dict, tip: dict | None,
                     conflict: bool, n_orphans: int, adjudicator: str) -> str:
        doc, field = row["doc_id"], row["field"]
        claim_id = ctx.claim_by_slot.get((doc, field), "")
        supersedes = tip["decision_id"] if tip else ""
        notes = []
        if tip:
            note = _t(lang, "current_note", id=tip["decision_id"],
                      decision=tip["decision"], by=tip["adjudicator"],
                      at=tip["decided_at"])
            notes.append(f'<div class="wb-current">{_esc(note)}<br>'
                         f'<i>{_esc(_t(lang, "reason"))}:{_esc(tip["rationale"])}</i></div>')
        if n_orphans:
            notes.append(f'<div class="wb-orphan">{_esc(_t(lang, "orphan_note", n=n_orphans))}</div>')
        if conflict:
            return f'<div class="wb-decide">{"".join(notes)}</div>'
        radios = "".join(
            f'<label class="wb-radio {d}"><input type="radio" name="decision" '
            f'value="{d}" required>{_esc(_t(lang, d))}</label>'
            for d in _DECISIONS
        )
        chips = "".join(
            f'<button type="button" class="wb-issue-chip" data-text="{_esc(c)}">{_esc(c)}</button>'
            for c in _T[lang]["issue_chips"]
        )
        return f"""<div class="wb-decide">{''.join(notes)}
<form class="decide" method="post" action="/decide">
<input type="hidden" name="run" value="{_esc(ctx.name)}">
<input type="hidden" name="doc" value="{_esc(doc)}">
<input type="hidden" name="field" value="{_esc(field)}">
<input type="hidden" name="claim_id" value="{_esc(claim_id)}">
<input type="hidden" name="supersedes" value="{_esc(supersedes)}">
<input type="hidden" name="lang" value="{_esc(lang)}">
<div class="wb-decide-row">{radios}
<input class="wb-corr" type="text" name="corrected_value"
 placeholder="{_esc(_t(lang, 'corrected_ph'))}"></div>
<textarea class="wb-rationale" name="rationale" rows="2" required
 placeholder="{_esc(_t(lang, 'rationale_ph'))}"></textarea>
<div class="wb-issue-chips">{chips}</div>
<div class="wb-decide-row">
<input class="wb-adjudicator" type="text" name="adjudicator" required
 placeholder="{_esc(_t(lang, 'adjudicator_ph'))}" value="{_esc(adjudicator)}">
<button type="submit" class="wb-btn" data-confirm="{_esc(_t(lang, 'confirm'))}">
{_esc(_t(lang, 'submit'))}</button></div>
</form></div>"""

    # ---- 交付报告
    def report_page(self, lang: str, run_dir: Path, params: dict) -> str:
        ctx = RunCtx(run_dir)
        rows = ctx.matrix["rows"]
        tips = [(r, ctx.slot(r["doc_id"], r["field"])) for r in rows]
        decided = [(r, s["tip"]) for r, s in tips if s and s["tip"]]
        by_decision = {d: 0 for d in _DECISIONS}
        for _, tip in decided:
            by_decision[tip["decision"]] = by_decision.get(tip["decision"], 0) + 1
        corrections = []
        for r, tip in decided:
            if tip["decision"] != "correct":
                continue
            old = r["value"] if r["value"] not in (None, "") else _t(lang, "no_value")
            corrections.append(
                f'<div class="wb-corr-item"><b>{_esc(r["doc_id"][:8])} · {_esc(r["field"])}</b>: '
                f'{_esc(_t(lang, "was"))} “{_esc(old)}” → {_esc(_t(lang, "now"))} '
                f'“{_esc(tip["corrected_value"])}”<br>'
                f'<i>{_esc(tip["rationale"])}</i> — {_esc(tip["adjudicator"])}, '
                f'{_esc(tip["decided_at"])} ({_esc(tip["decision_id"])})</div>')
        stats = (
            f'<div class="wb-stat"><b>{len(decided)} / {len(rows)}</b>{_esc(_t(lang, "stat_reviewed"))}</div>'
            f'<div class="wb-stat"><b>{by_decision.get("correct", 0)}</b>{_esc(_t(lang, "stat_corrections"))}</div>'
            f'<div class="wb-stat"><b>{len(ctx.decisions)}</b>{_esc(_t(lang, "stat_decisions"))}</div>'
        )
        dist = " ".join(f"{_esc(_t(lang, d))}: {n}" for d, n in by_decision.items())
        body = f"""
<div class="wb-report-stats">{stats}</div>
<p>{dist}</p>
<h2>{_esc(_t(lang, 'corrections_title'))}</h2>
{''.join(corrections) or '—'}
<div class="wb-banner">{_esc(_t(lang, 'residual'))}</div>
<div class="wb-footer">{_esc(_t(lang, 'snapshot'))}={_esc(ctx.snapshot_id)}</div>"""
        return self.page(lang, "report", body, run_name=ctx.name,
                         notice=self._notice(lang, params),
                         ooc=ctx.manifest.get("out_of_calibration", False))

    # ---- 上传
    def upload_page(self, lang: str, params: dict, has_key: bool) -> str:
        notice = self._notice(lang, params)
        key_note = "" if has_key else f'<p class="wb-orphan">{_esc(_t(lang, "no_key"))}</p>'
        checked = "checked" if has_key else ""
        disabled = "" if has_key else "disabled"
        body = f"""
<h1>{_esc(_t(lang, 'upload_title'))}</h1>
<div class="wb-upload">
<p><input type="file" id="wb-files" accept=".pdf" multiple></p>
<ul class="wb-list" id="wb-ul"></ul>
<p class="wb-label">{_esc(_t(lang, 'drop_hint'))}</p>
<p class="wb-label">{_esc(_t(lang, 'same_name_note'))}</p>
<form class="wb-form" method="post" action="/ingest">
<input type="hidden" name="lang" value="{_esc(lang)}">
<label><input type="checkbox" name="do_extract" value="1" {checked} {disabled}>
{_esc(_t(lang, 'extract_cb'))}</label>
{key_note}
<button type="submit" class="wb-btn">{_esc(_t(lang, 'start'))}</button>
</form></div>"""
        return self.page(lang, "upload", body, notice=notice)

    # ---- 交付与验证
    def deliver_page(self, lang: str, run_dir: Path, params: dict,
                     verify_report: dict | None = None) -> str:
        ctx = RunCtx(run_dir)
        bundle = ctx.dir / "audit_bundle.zip"
        download = (f'<p><a class="wb-btn" href="/download/{ctx.name}/audit_bundle.zip">'
                    f'{_esc(_t(lang, "download"))}</a></p>' if bundle.exists() else "")
        verify_html = ""
        if verify_report is not None:
            if verify_report["ok"]:
                verify_html = (f'<div class="wb-verify-ok">ok — {verify_report["members"]} '
                               f'members verified</div>')
            else:
                items = "".join(f"<li>{_esc(f)}</li>" for f in verify_report["failures"])
                verify_html = f'<div class="wb-verify-fail"><ul>{items}</ul></div>'
        body = f"""
<h1>{_esc(_t(lang, 'deliver'))}</h1>
<form class="wb-form" method="post" action="/bundle">
<input type="hidden" name="run" value="{_esc(ctx.name)}">
<input type="hidden" name="lang" value="{_esc(lang)}">
<button type="submit" class="wb-btn">{_esc(_t(lang, 'build_bundle'))}</button>
</form>
{download}
<h2>{_esc(_t(lang, 'verify_title'))}</h2>
<p><input type="file" id="wb-zip" accept=".zip"></p>
<p class="wb-label">no-JS: <code>python3 -m invoiceloop verify &lt;bundle.zip&gt;</code></p>
<div id="wb-verify-result">{verify_html}</div>
<div class="wb-footer">{_esc(_t(lang, 'snapshot'))}={_esc(ctx.snapshot_id)}</div>"""
        return self.page(lang, "deliver", body, run_name=ctx.name,
                         notice=self._notice(lang, params))

    def verify_fragment(self, report: dict) -> str:
        if report["ok"]:
            return (f'<div class="wb-verify-ok">ok — {report["members"]} '
                    f'members verified</div>')
        items = "".join(f"<li>{_esc(f)}</li>" for f in report["failures"])
        return f'<div class="wb-verify-fail"><ul>{items}</ul></div>'

    def message_page(self, lang: str, title: str, lines: list[str],
                     back_href: str | None = None) -> str:
        items = "".join(f"<p>{line}</p>" for line in lines)
        back = f'<p><a href="{_esc(back_href)}">{_esc(_t(lang, "back"))}</a></p>' if back_href else ""
        return self.page(lang, "", f'<div class="wb-msg-page"><h1>{_esc(title)}</h1>{items}{back}</div>')


# ---------------------------------------------------------------------- HTTP

class _Handler(BaseHTTPRequestHandler):
    wb: Workbench  # 由 make_server 挂在 server 上

    def log_message(self, *args):  # 测试与 demo 都安静点
        pass

    # ---- 基础设施
    @property
    def bench(self) -> Workbench:
        return self.server.bench

    def _lang(self, params: dict, *, set_cookie: list | None = None) -> str:
        lang = params.get("lang", [""])[0]
        if lang not in ("en", "zh"):
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            lang = cookie["wb_lang"].value if "wb_lang" in cookie else "en"
            lang = lang if lang in ("en", "zh") else "en"
        elif set_cookie is not None:
            set_cookie.append(("wb_lang", lang))
        return lang

    def _adjudicator(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        if "wb_adjudicator" not in cookie:
            return ""
        return urllib.parse.unquote(cookie["wb_adjudicator"].value)

    def _params(self) -> tuple[str, dict]:
        split = urllib.parse.urlsplit(self.path)
        return split.path, urllib.parse.parse_qs(split.query)

    @staticmethod
    def _host_of(header_value: str | None) -> str | None:
        """从 Host/Origin 头取出主机名;没有头 → None(本地老工具,放行)。"""
        if not header_value:
            return None
        host = urllib.parse.urlsplit(header_value).hostname \
            if "://" in header_value else header_value
        if host.startswith("[") and "]" in host:
            return host[1:host.index("]")]
        return host.split(":")[0].lower()

    def _check_gates(self, method: str) -> None:
        host = self._host_of(self.headers.get("Host"))
        if host is not None and host not in _ALLOWED_HOSTS:
            raise _HttpError(403, f"Host {host!r} 不在 loopback 白名单 —— "
                                  f"这通常是 DNS rebinding 的特征,已拒")
        if method == "POST":
            origin = self._host_of(self.headers.get("Origin"))
            if origin is not None and origin not in _ALLOWED_HOSTS:
                raise _HttpError(403, f"跨源 POST(Origin {origin!r})已拒 —— "
                                      f"本服务只接受本页发起的写操作")

    def _body(self, limit: int = 10 * 1024 * 1024) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise _HttpError(413, "body too large")
        return self.rfile.read(length) if length else b""

    def _form(self) -> dict:
        return urllib.parse.parse_qs(self._body().decode("utf-8", "replace"))

    def _send(self, status: int, body: bytes, content_type: str,
              cookies: list[tuple[str, str]] | None = None,
              extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in cookies or []:
            self.send_header("Set-Cookie", f"{name}={urllib.parse.quote(value)}; Path=/")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, text: str, cookies=None) -> None:
        self._send(status, text.encode("utf-8"), "text/html; charset=utf-8", cookies)

    def _redirect(self, location: str, cookies=None) -> None:
        self._send(303, b"", "text/plain", cookies, {"Location": location})

    # ---- 入口
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        from .workbench_style import CSS

        path, params = self._params()
        set_cookies: list = []
        lang = self._lang(params, set_cookie=set_cookies)
        try:
            self._check_gates(method)
            if method == "GET" and path == "/assets.css":
                return self._send(200, CSS.encode(), "text/css; charset=utf-8")
            if method == "GET" and path == "/assets.js":
                return self._send(200, _JS.encode(), "text/javascript; charset=utf-8")
            if method == "GET" and path == "/":
                run = self.bench.current_run()
                if run is None:
                    return self._redirect(f"/upload?lang={lang}", set_cookies)
                return self._redirect(f"/queue?run={run.name}&lang={lang}", set_cookies)
            if method == "GET" and path == "/queue":
                if not params.get("run") and self.bench.current_run() is None:
                    return self._redirect(f"/upload?lang={lang}", set_cookies)
                params.setdefault("adjudicator", [self._adjudicator()])
                run = self._require_run(params)
                return self._html(200, self.bench.queue_page(lang, run, params), set_cookies)
            if method == "GET" and path == "/report":
                run = self._require_run(params)
                return self._html(200, self.bench.report_page(lang, run, params), set_cookies)
            if method == "GET" and path == "/upload":
                import os
                return self._html(200, self.bench.upload_page(
                    lang, params, has_key=bool(os.environ.get("DWS_API_KEY"))), set_cookies)
            if method == "GET" and path == "/deliver":
                run = self._require_run(params)
                return self._html(200, self.bench.deliver_page(lang, run, params), set_cookies)
            if method == "GET" and path.startswith("/files/"):
                return self._files(path)
            if method == "GET" and path.startswith("/download/"):
                return self._download(path)
            if method == "POST" and path == "/decide":
                return self._decide(lang)
            if method == "POST" and path == "/upload":
                return self._upload(params)
            if method == "POST" and path == "/ingest":
                return self._ingest(lang)
            if method == "POST" and path == "/bundle":
                return self._bundle(lang)
            if method == "POST" and path == "/verify":
                return self._verify(lang)
            return self._html(404, self.bench.message_page(lang, "404", [_esc(path)]))
        except _HttpError as exc:
            run_q = f"/queue?run={exc.run}" if exc.run else None
            self._html(exc.status, self.bench.message_page(
                lang, _t(lang, "error_title"), [_esc(exc.message)], run_q))
        except ValueError as exc:
            # 裁决校验失败(400):append_adjudication 的中文错误信息原样给用户
            back = None
            try:
                form_run = getattr(self, "_last_run", None)
                back = f"/queue?run={form_run}&lang={lang}" if form_run else None
            except Exception:  # noqa: BLE001
                pass
            self._html(400, self.bench.message_page(lang, _t(lang, "error_title"),
                                                    [_esc(str(exc))], back))
        except Exception as exc:  # noqa: BLE001 —— demo 工具,500 给完整 repr
            import traceback
            self._html(500, self.bench.message_page(
                lang, "500", [f"<pre>{_esc(repr(exc))}\n{_esc(traceback.format_exc())}</pre>"]))

    def _require_run(self, params: dict) -> Path:
        run = self.bench.get_run(params.get("run", [None])[0])
        if run is None:
            raise _HttpError(404, f"run 不存在或不完整:{params.get('run', ['?'])[0]}")
        return run

    # ---- 动作
    def _decide(self, lang: str) -> None:
        from .adjudicate import adjudicate_and_render

        form = self._form()
        run_name = form.get("run", [""])[0]
        self._last_run = run_name
        form_lang = form.get("lang", [""])[0]
        if form_lang in ("en", "zh"):
            lang = form_lang
        run = self.bench.get_run(run_name)
        if run is None:
            raise _HttpError(404, f"run 不存在:{run_name}")
        decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rationale = form.get("rationale", [""])[0].strip()
        adjudicator = form.get("adjudicator", [""])[0].strip()
        if not rationale:
            raise ValueError("rationale 不能为空 —— 把发现的问题或理由写出来")
        if not adjudicator:
            raise ValueError("adjudicator 不能为空 —— 裁决要署名")
        result = adjudicate_and_render(
            run,
            claim_id=form.get("claim_id", [""])[0] or None,
            doc_id=form.get("doc", [""])[0],
            field=form.get("field", [""])[0],
            decision=form.get("decision", [""])[0],
            corrected_value=form.get("corrected_value", [""])[0] or None,
            rationale=rationale,
            adjudicator=adjudicator,
            decided_at=decided_at,
            supersedes_decision_id=form.get("supersedes", [""])[0] or None,
        )
        notice = "recorded" if result["panel_refreshed"] else "recorded_stale"
        cookies = [("wb_adjudicator", adjudicator)]
        anchor = f"#row-{form.get('doc', [''])[0]}-{form.get('field', [''])[0]}"
        self._redirect(f"/queue?run={run_name}&lang={lang}&notice={notice}{anchor}", cookies)

    def _upload(self, params: dict) -> None:
        filename = Path(params.get("filename", [""])[0]).name
        if not filename.lower().endswith(".pdf"):
            raise _HttpError(400, f"只接受 .pdf:{filename!r}")
        body = self._body(limit=MAX_UPLOAD)
        if not body:
            raise _HttpError(400, "空文件")
        if not body.startswith(b"%PDF"):
            raise _HttpError(400, f"{filename!r} 不是 PDF(魔数不符)")
        doc_id = sanitise_doc_id(Path(filename).stem)
        target = self.bench.ws / "input" / "pdfs" / f"{doc_id}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        invalidated: list[str] = []
        if target.exists() and target.read_bytes() == body:
            pass  # 幂等:同样内容重传不动作
        else:
            target.write_bytes(body)
            # 同名不同内容(或 sanitise 撞名):下游证据(旧 OCR / 旧 DWS 响应)
            # 全部失效。断点续跑续的是「同一份输入」的跑;拿旧 OCR/旧抽取配
            # 新文档,门禁全绿而证据全错 —— 最坏的一种静默(对抗复核 2026-08-03)
            from .dws import MODES

            stale = [self.bench.ws / "ocr" / f"{doc_id}.json"] + [
                self.bench.ws / "raw" / f"{doc_id}.{mode}.json" for mode in MODES
            ]
            for path in stale:
                if path.exists():
                    path.unlink()
                    invalidated.append(path.name)
        payload = json.dumps({"saved": doc_id, "invalidated": invalidated}).encode()
        self._send(200, payload, "application/json")

    def _ingest(self, lang: str) -> None:
        import contextlib
        import io
        import os

        from . import dws, ocr as ocr_mod
        from .ingest import cmd_ingest
        from .pipeline import run as pipeline_run

        form = self._form()
        do_extract = form.get("do_extract", [""])[0] == "1"
        if do_extract and not os.environ.get("DWS_API_KEY"):
            raise _HttpError(400, _t(lang, "no_key"))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                summary = cmd_ingest(self.bench.ws, do_ocr=True, do_extract=do_extract)
        except SystemExit as exc:
            # cmd_ingest 用 SystemExit 报输入契约不满足(没目录/没 PDF);
            # BaseException,通用 except Exception 接不住 —— 不接的话连接被
            # 掐、线程静默死,用户连一句提示都看不到
            raise _HttpError(400, str(exc)) from exc
        # 长驻进程:OCR 可能刚被换过(upload 失效传播 / 用户手工删了重跑),
        # lru_cache 只按 doc_id 记 —— 不清就用旧 OCR 绑新文档,
        # 而清单与快照记的是新文件的 sha(对抗复核 2026-08-03)
        ocr_mod.load_ocr.cache_clear()
        ocr_mod.doc_tokens.cache_clear()
        doc_ids = dws.stored_docs()
        if not doc_ids:
            raise _HttpError(400, "raw/ 里没有存盘响应 —— 先放 PDF 并勾选 DWS 抽取")
        fingerprint = build_input_manifest(doc_ids)["fingerprint"]
        existing = find_run_by_fingerprint(self.bench.ws / "runs", fingerprint)
        if existing is not None:
            return self._redirect(f"/queue?run={existing.name}&lang={lang}&notice=replayed")
        run_dir = allocate_run_dir(self.bench.ws / "runs")
        pipeline_run(doc_ids, run_dir, render_crops=True,
                     include_vision=True, out_of_calibration=True)
        (self.bench.ws / "runs" / "current.json").write_text(
            json.dumps({"run": run_dir.name}, ensure_ascii=False) + "\n", encoding="utf-8")
        # 失败必须显式:OCR/抽取失败的文档不悄悄消失,列出名字与原因
        failures = [(f["doc_id"], f.get("reason", "")) for f in summary.get("ocr_blocked", [])]
        failures += [(f["doc_id"], f.get("error", "")) for f in summary.get("extract_failed", [])]
        if failures:
            lines = [f"{_esc(doc)} — {_esc(why)}" for doc, why in failures]
            lines.append(f'<a href="/queue?run={run_dir.name}&lang={lang}">'
                         f'{_esc(_t(lang, "back"))}</a>')
            return self._html(200, self.bench.message_page(
                lang, _t(lang, "error_title"), lines))
        self._redirect(f"/queue?run={run_dir.name}&lang={lang}&notice=ingested")

    def _bundle(self, lang: str) -> None:
        from .adjudicate import build_audit_bundle

        form = self._form()
        run = self._require_run(form)
        build_audit_bundle(run)
        self._redirect(f"/deliver?run={run.name}&lang={lang}&notice=bundled")

    def _verify(self, lang: str) -> None:
        import tempfile

        from .adjudicate import verify_bundle

        body = self._body(limit=MAX_UPLOAD)
        if not body:
            raise _HttpError(400, "先选一个 .zip 文件")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(body)
            tmp_path = Path(tmp.name)
        try:
            report = verify_bundle(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        # 返回片段,JS 塞进 #wb-verify-result;不整页跳转,结果留在交付页上下文里
        self._send(200, self.bench.verify_fragment(report).encode("utf-8"),
                   "text/html; charset=utf-8")

    # ---- 静态文件
    def _files(self, path: str) -> None:
        rel = path[len("/files/"):]
        parts = rel.split("/", 1)
        if len(parts) != 2:
            raise _HttpError(404, "bad path")
        run = self.bench.get_run(parts[0])
        if run is None:
            raise _HttpError(404, "run 不存在")
        target = (run / urllib.parse.unquote(parts[1])).resolve()
        if not target.is_relative_to(run.resolve()) or target.suffix not in (".png", ".html", ".json"):
            raise _HttpError(404, "not found")
        if not target.is_file():
            raise _HttpError(404, "not found")
        mime = {".png": "image/png", ".html": "text/html; charset=utf-8",
                ".json": "application/json"}[target.suffix]
        self._send(200, target.read_bytes(), mime)

    def _download(self, path: str) -> None:
        rel = path[len("/download/"):]
        parts = rel.split("/")
        if len(parts) != 2 or parts[1] != "audit_bundle.zip":
            raise _HttpError(404, "bad path")
        run = self.bench.get_run(parts[0])
        bundle = (run or Path(".")) / "audit_bundle.zip"
        if run is None or not bundle.exists():
            raise _HttpError(404, "bundle 不存在 —— 先打 bundle")
        self._send(200, bundle.read_bytes(), "application/zip")


class _HttpError(Exception):
    def __init__(self, status: int, message: str, run: str = ""):
        super().__init__(message)
        self.status = status
        self.message = message
        self.run = run


def make_server(workspace: Path, port: int) -> ThreadingHTTPServer:
    """绑定 127.0.0.1 的工作台服务器。loopback only —— 不提供 host 参数,
    要暴露给别人的话走 audit bundle,不要把这个服务放到网络上。"""
    import os

    workspace = Path(workspace)
    os.environ["INVOICELOOP_DWS_DERISK"] = str(workspace)
    server = ThreadingHTTPServer((HOST, port), _Handler)
    server.daemon_threads = True
    server.bench = Workbench(workspace)
    return server


def cmd_workbench(workspace: Path, port: int) -> int:
    server = make_server(workspace, port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"InvoiceLoop 工作台:{url}(仅本机 loopback,Ctrl-C 停止)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
