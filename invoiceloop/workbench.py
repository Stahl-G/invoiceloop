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
    GET  / /queue /adjudicate /report /upload /deliver /files/<run>/<rel> /download/<run>/audit_bundle.zip
    POST /decide /upload?filename= /ingest /bundle /verify(原始字节)

/adjudicate 是 Gradescope 风格的单槽裁决页:左栏整页渲染 + bbox 高亮
overlay(冻结绑定绿实线 / DWS 引用紫虚线),右栏判定卡 + 决策表单(与队列页
同一套表单字段、同一个 /decide 端点),底栏按分诊序导航上一条/下一条未裁决。
表单多带一个 hidden next=adjudicate:提交后服务器推进到队列序里下一个未裁决
槽位;不带该字段的提交(队列页)仍跳回队列锚点 —— 两条路的裁决语义一字不差。
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
from .gateinfo import tooltip as _gate_tooltip
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
        "sec_required": "Needs adjudication ({n})",
        "sec_corroborated": "Corroborated — no machine flags, spot-check ({n})",
        "reviewed": "{x} / {y} reviewed",
        "accept": "Accept", "reject": "Reject", "correct": "Correct", "abstain": "Abstain",
        "confirm_absent": "Confirm absent", "not_applicable": "N/A",
        "corrected_ph": "corrected value",
        "rationale_ph": "Issue / rationale (required) — write down what's wrong",
        "reason_code_label": "Reason code (optional, feeds the improvement loop):",
        "adjudicator_ph": "reviewer name",
        "issue_chips": ["matches the page", "wrong value", "wrong location",
                        "illegible", "label-convention conflict", "not on page", "other"],
        "accept_preset": "matches the page",
        "quick_accept": "✓ value is right — accept & next",
        "quick_draft": "✓ draft is right — adopt “{value}” & next",
        "quick_dws": "✓ value is right — adopt DWS read “{value}” & next",
        "why_queue": "why this is in your queue",
        "why_infra": "independent OCR unavailable for this document — machine "
                     "checks never ran here; “not checked” ≠ “checked clean”, "
                     "so every slot is human-reviewed",
        "why_slot": "blocking finding on this slot — resolve it before release",
        "why_unsupported": "no bindable claim — look on the page; if the value "
                           "is there, correct and enter it",
        "why_disputed": "label-convention dispute (paper Gross/Net reads "
                        "opposite to EN 16931) — human classifies, never "
                        "counted as an error",
        "why_gate_fail": "gate failed: {gates}",
        "why_gate_warn": "gate warning: {gates}",
        "why_qa": "random QA probe watching the auto-release policy — machine "
                  "checks all passed; a glance and “value is right” is enough",
        "quick_draft_rationale": "confirmed on page: rejected draft value is "
                                 "correct (binding failed, human vouches)",
        "vision_suggest": "Vision suggestion",
        "vision_agree": "{a}/{n} readers agree",
        "vision_split": "readers disagree",
        "vision_adopt": "Adopt",
        "vision_blind": "vision readers can't read it either",
        "vision_rejected": "same value rejected at freeze — no adopt",
        "vision_rationale": "confirmed vision suggestion",
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
        "task_with_value": "Task: verify the {label} on the page — "
                           "DWS read “{value}”. Is it there? Is it right?",
        "task_no_value": "Task: DWS gave no {label} — look for it on the page: "
                         "“Correct” to supply it, “Abstain” if truly absent or illegible.",
        "lim_value_not_in_cited_span": "value not found in DWS's cited region (possible misplacement)",
        "lim_draft_rejected_at_freeze": "draft rejected at freeze (value doesn't bind to this document)",
        "lim_dws_returned_no_value": "DWS returned no value for this field",
        "lim_vision_offers": "vision reader {model} saw “{value}” (reference only)",
        "lim_visual_not_measured": "visual gate not measured",
        "lim_ocr_unavailable_pipeline_blocked": "independent OCR unavailable — no mechanical checks on this row; your eyes only",
        "lim_citation_not_checkable": "citation not mechanically checkable (no cited region)",
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
        "doc_status": "Document release status",
        "status_released": "released", "status_pending": "pending",
        "status_blocked": "blocked",
        "status_released_with_caveats": "released w/ caveats",
        "download_deliverable": "Download deliverable.json (final-value projection)",
        "release_note": "released = every slot adjudicated (tier-1 fields require an explicit "
                        "decision even when corroborated); pending = slots awaiting decision; "
                        "blocked = a tier-1 field was rejected. unreviewed_corroborated slots "
                        "are exported with values and labelled as such.",
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
        # ---- Gradescope 风格裁决页(左页面证据 / 右判定卡 / 底栏导航) ----
        "open_adj": "Adjudicate →",
        "page_view": "Page evidence",
        "legend_bind": "frozen binding (span_ids)",
        "legend_cited": "DWS citation (cited_span_ids)",
        "no_page": "No rendered page for this document — use the evidence "
                   "crops on the right.",
        "prev_pending": "← previous undecided",
        "next_pending": "next undecided →",
        "none_pending": "no more undecided",
        "queue_pos": "slot {x} / {n} · {y} decided",
        "judgement": "InvoiceLoop assessment",
        "frozen_value": "Frozen value",
        "no_claim": "(no claim)",
        "src_tiers": "sources",
        "applicability": "applicability",
        "policy_note": "Not flagged for required adjudication — if you don't "
                       "decide, delivery exports it as policy_accepted / "
                       "unreviewed_corroborated. Spot-checks welcome.",
    },
    "zh": {
        "brand": "InvoiceLoop 工作台",
        "thesis": "抽取的正确性不可信,支持关系可验证。你裁决,系统只给证据,不给判决。",
        "queue": "复核队列", "report": "交付报告",
        "upload": "上传", "deliver": "交付与验证",
        "all": "全部", "pending": "待复核", "done": "已裁决",
        "sec_required": "需要裁决 ({n})",
        "sec_corroborated": "印证行 —— 机器未见异常,抽检性质 ({n})",
        "reviewed": "已复核 {x} / {y}",
        "accept": "接受", "reject": "拒绝", "correct": "修正", "abstain": "弃权",
        "confirm_absent": "确认缺失", "not_applicable": "不适用",
        "corrected_ph": "修正值",
        "rationale_ph": "发现的问题 / 理由(必填)—— 把问题直接写在这里",
        "reason_code_label": "原因码(可选,喂给改进循环):",
        "adjudicator_ph": "裁决人",
        "issue_chips": ["与页面一致", "值不对", "位置不对", "看不清", "口径冲突", "页面上没有", "其他"],
        "accept_preset": "与页面一致",
        "quick_accept": "✓ 原值正确 —— 接受,下一条",
        "quick_draft": "✓ 原值正确 —— 采用被拒草稿「{value}」,下一条",
        "quick_dws": "✓ 原值正确 —— 采用 DWS 读到「{value}」,下一条",
        "why_queue": "为什么在我的队列里",
        "why_infra": "本文档独立 OCR 缺失/受阻,机检没覆盖它 —— 「没查过」不等于"
                     "「查过没问题」,所以每槽都要人工",
        "why_slot": "这一槽有阻断级发现 —— 解决之前不许放行",
        "why_unsupported": "没有可绑定的声明值 —— 页面上找,有就「修正」补录",
        "why_disputed": "口径争议(纸面 Gross/Net 与 EN 16931 方向相反)—— "
                        "人来定性,不算任何错误",
        "why_gate_fail": "门禁未过:{gates}",
        "why_gate_warn": "门禁警告:{gates}",
        "why_qa": "随机抽检 —— 盯着自动放行政策的探针;机检全过,"
                  "扫一眼点「原值正确」即可,不用细审",
        "quick_draft_rationale": "页面上确认被拒草稿的值正确(绑定失败,人证成立)",
        "vision_suggest": "读图建议",
        "vision_agree": "{a}/{n} 读者一致",
        "vision_split": "读者分歧",
        "vision_adopt": "采用建议",
        "vision_blind": "读图也看不清",
        "vision_rejected": "同值冻结时被拒,不提供采用",
        "vision_rationale": "确认读图建议",
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
        "task_with_value": "任务:在页面上核对{label} —— DWS 读到“{value}”。"
                           "页面上有吗?对不对?",
        "task_no_value": "任务:DWS 没给出{label} —— 请在页面上找:"
                         "有就「修正」补录,确实没有或看不清就「弃权」。",
        "lim_value_not_in_cited_span": "值不在 DWS 指的引用区里(可能错位)",
        "lim_draft_rejected_at_freeze": "草稿在冻结时被拒(值绑不进本文档)",
        "lim_dws_returned_no_value": "DWS 没返回这个字段",
        "lim_vision_offers": "读图模型 {model} 看到的值:“{value}”(仅参考)",
        "lim_visual_not_measured": "读图门未测",
        "lim_ocr_unavailable_pipeline_blocked": "独立 OCR 产不出:本行没有机械核对,全靠你人工看整页",
        "lim_citation_not_checkable": "引用无法机检(无引用区)",
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
        "doc_status": "整单放行状态",
        "status_released": "可放行", "status_pending": "待完成",
        "status_blocked": "被阻断",
        "status_released_with_caveats": "放行(带披露)",
        "download_deliverable": "下载 deliverable.json(最终值投影)",
        "release_note": "可放行 = 全部槽位裁决完毕(关键字段即使多方印证也须显式裁决);"
                        "待完成 = 仍有槽位未裁决;被阻断 = 有关键字段被拒。"
                        "unreviewed_corroborated 槽照出值并如实标注「未逐个人看」。",
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
        # ---- Gradescope 风格裁决页(左页面证据 / 右判定卡 / 底栏导航) ----
        "open_adj": "去裁决 →",
        "page_view": "页面证据",
        "legend_bind": "冻结绑定(span_ids)",
        "legend_cited": "DWS 引用(cited_span_ids)",
        "no_page": "本文档没有整页渲染 —— 用右侧的证据裁剪图复核。",
        "prev_pending": "← 上一条未裁决",
        "next_pending": "下一条未裁决 →",
        "none_pending": "没有未裁决的了",
        "queue_pos": "第 {x} / {n} 条 · 已裁决 {y}",
        "judgement": "InvoiceLoop 判定",
        "frozen_value": "冻结值",
        "no_claim": "(无声明)",
        "src_tiers": "来源",
        "applicability": "口径",
        "policy_note": "不在必须裁决之列 —— 不裁决的话,交付时按 "
                       "policy_accepted / 未复核印证导出。欢迎抽检。",
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
  // 接受的天然理由预设:空着就预填「与页面一致」(可改可删);
  // 切走且理由一字未动过预设,就还回空白,不把预设带去别的决策
  var ta = form.querySelector('.wb-rationale');
  var preset = form.dataset.acceptPreset;
  if (ta && preset) {
    if (e.target.value === 'accept' && !ta.value.trim()) ta.value = preset;
    else if (e.target.value !== 'accept' && ta.value === preset) ta.value = '';
  }
});
document.addEventListener('click', function (e) {
  // 一键快路:人看了页面,点一下就完成「原值正确」并跳下一条。
  // 预填决策/修正值/理由 → armed 置位 → requestSubmit(绕过二段确认:
  // 按钮自己的文案就是确认语义)。仍是人逐槽点击,账本照记。
  var quick = e.target.closest('.wb-quick-ok');
  if (quick) {
    var qform = quick.closest('form');
    var qradio = qform.querySelector(
      'input[name=decision][value="' + quick.dataset.decision + '"]');
    if (!qradio) return;
    qradio.checked = true;
    qradio.dispatchEvent(new Event('change', { bubbles: true }));
    if (quick.dataset.value) {
      var qcorr = qform.querySelector('.wb-corr');
      qcorr.disabled = false;
      qcorr.value = quick.dataset.value;
    }
    var qta = qform.querySelector('.wb-rationale');
    if (qta && !qta.value.trim()) qta.value = quick.dataset.rationale || '';
    qform.dataset.armed = '1';
    qform.requestSubmit();
    return;
  }
  var chip = e.target.closest('.wb-issue-chip');
  if (chip) {
    var form = chip.closest('form');
    var ta = form.querySelector('.wb-rationale');
    // 同一条不重复追加(连点两次不会再出「与页面一致; 与页面一致」)
    if (ta.value.indexOf(chip.dataset.text) === -1) {
      ta.value = (ta.value ? ta.value.replace(/[;\s]+$/, '') + '; ' : '') + chip.dataset.text;
    }
    ta.focus();
    return;
  }
  // 读图「采用建议」:只预填表单 —— 人不点提交,账本一个字不进(宪章)
  var btn = e.target.closest('.wb-vs-adopt');
  if (!btn) return;
  // 队列页按钮在 .wb-row 里;单槽裁决页在 .wb-adj-card 里 —— 两处都能用
  var scope = btn.closest('.wb-row') || btn.closest('.wb-adj-card');
  if (!scope) return;
  var form2 = scope.querySelector('form.decide');
  if (!form2) return;
  var value = btn.dataset.value;
  var ta2 = form2.querySelector('.wb-rationale');
  if (ta2 && !ta2.value.trim()) ta2.value = btn.dataset.rationale || '';
  var rowValue = scope.querySelector('.wb-value');
  var same = rowValue && !rowValue.classList.contains('none') &&
             rowValue.textContent.trim() === value;
  var radio = form2.querySelector(
    'input[name=decision][value="' + (same ? 'accept' : 'correct') + '"]');
  if (!radio) return;
  radio.checked = true;
  radio.dispatchEvent(new Event('change', { bubbles: true }));
  if (!same) form2.querySelector('.wb-corr').value = value;
  ta2.focus();
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

_DECISIONS = ("accept", "confirm_absent", "not_applicable",
              "reject", "correct", "abstain")

#: 字段的人类名字 —— 复核者找的是「买方名称」,不是 buyer_name(2026-08-03
#: 用户反馈:字段名又小又灰,不知道自己的任务是什么)
_FIELD_LABEL = {
    "en": {"invoice_number": "Invoice number", "issue_date": "Issue date",
           "due_date": "Due date", "seller_name": "Seller name",
           "seller_vat_id": "Seller VAT ID", "buyer_name": "Buyer name",
           "total_net": "Total (net)", "total_vat": "VAT",
           "total_gross": "Total (gross)", "amount_due": "Amount due"},
    "zh": {"invoice_number": "发票号码", "issue_date": "开票日期",
           "due_date": "到期日", "seller_name": "卖方名称",
           "seller_vat_id": "卖方 VAT 号", "buyer_name": "买方名称",
           "total_net": "净额(未含税)", "total_vat": "税额",
           "total_gross": "总额(含税)", "amount_due": "应付金额"},
}


def _lim(lang: str, code: str) -> str:
    """matrix 的限制码 → 人话。vision_offers 带动态载荷单独拆;
    没收录的码原样显示(诚实,不编)。"""
    if code.startswith("vision_offers:"):
        payload = code.split(":", 1)[1]
        model, _, value = payload.partition("=")
        return _t(lang, "lim_vision_offers", model=model, value=value)
    return _t(lang, f"lim_{code}")
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
        # The matrix is authoritative about which claim backs a row.  Taking
        # the last ledger claim can silently select agentic/vision instead of
        # the understand claim displayed by the matrix.
        self.claim_by_slot = {
            (row["doc_id"], row["field"]): row.get("claim_id") or ""
            for row in self.matrix.get("rows", [])
        }
        self.spans_by_id = {s["span_id"]: s for s in self.spans}
        self.orphans = [d for d in self.decisions if d.get("orphan")]
        # 读图作答 → 建议层:{(doc, field): [(读者, 值)]}。建议只是建议:
        # 它出现在表单旁边,人不点「采用」不进表单,人不点「提交」不进账本
        from .dws import load_vision_answers

        self.vision: dict[tuple[str, str], list[tuple[str, str]]] = {}
        local_vision = self.dir / "vision"
        vision_dir = local_vision if local_vision.is_dir() else None
        for model, rows in load_vision_answers(vision_dir=vision_dir).items():
            for key, ans in rows.items():
                self.vision.setdefault(key, []).append((model, ans["value"]))

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
             run_name: str | None = None, notice: str = "", ooc: bool = False,
             compact: bool = False) -> str:
        # 导航永远指向一个真实存在的 run:消息页/404 页不传 run,
        # 也得给人回得去的路(2026-08-03 实测:404 页只剩上传 tab,出不来)
        nav_run = run_name
        if nav_run is None:
            current = self.current_run()
            nav_run = current.name if current else None
        tabs = []
        if nav_run:
            for key, href in (
                ("queue", f"/queue?run={nav_run}"),
                ("report", f"/report?run={nav_run}"),
                ("deliver", f"/deliver?run={nav_run}"),
                ("upload", "/upload"),
            ):
                cls = "wb-tab active" if key == active else "wb-tab"
                sep = "&" if "?" in href else "?"
                tabs.append(f'<a class="{cls}" href="{href}{sep}lang={lang}">'
                            f'{_esc(_t(lang, key))}</a>')
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
</head><body{' class="wb-compact"' if compact else ''}>
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
        # 分节呈现:矩阵本来就知道哪些行「需要裁决」、哪些是多方印证。
        # 不分节,印证行和待裁决行混在一起,用户会以为「全绿的也要我复审 =
        # 假错误」(2026-08-03 用户实测原话)。印证行仍在(机器不设免审通道 —
        # 六轮实验发现最危险的错恰是看起来全对的错),但标明是抽检性质。
        groups = (
            ("sec_required", [(r, t) for r, t in filt_rows if r["requires_adjudication"]]),
            ("sec_corroborated", [(r, t) for r, t in filt_rows if not r["requires_adjudication"]]),
        )
        cards = []
        for key, items in groups:
            if not items:
                continue
            cards.append(f'<h2 class="wb-section">{_esc(_t(lang, key, n=len(items)))}</h2>')
            cards.extend(self.row_card(lang, ctx, r, tip, adjudicator) for r, tip in items)
        pct = int(100 * decided / len(rows)) if rows else 0
        body = f"""
<div class="wb-progress" title="{_esc(_t(lang, 'reviewed', x=decided, y=len(rows)))}">
<div class="wb-progress-bar" style="width:{pct}%"></div></div>
<p>{_esc(_t(lang, 'reviewed', x=decided, y=len(rows)))}</p>
<div class="wb-filters">{chips}</div>
{''.join(cards)}
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

    def _gates_html(self, lang: str, row: dict) -> str:
        """六道门禁逐项 chip,悬停一句话解释(gateinfo.tooltip 给文案)。"""
        return "".join(
            f'<span class="wb-gate {v}" title="{_esc(_gate_tooltip(g, v, lang))}">'
            f'{_GATE_SHORT.get(g, (g, g))[0 if lang == "en" else 1]}:'
            f'{_VERDICT.get(v, (v, v))[0 if lang == "en" else 1]}</span>'
            for g, v in sorted(row["gate_verdicts"].items())
        )

    def _status_chip(self, lang: str, tip: dict | None, conflict: bool) -> str:
        """裁决状态 chip:冲突 / 已裁决(蓝,human-confirmed)/ 待复核(灰)。"""
        if conflict:
            return f'<span class="wb-status conflict">{_esc(_t(lang, "conflict_note"))}</span>'
        if tip:
            label = _esc(_t(lang, tip["decision"]))
            corr = (f' → “{_esc(tip["corrected_value"])}”'
                    if tip["decision"] == "correct" else "")
            return (f'<span class="wb-status {tip["decision"]}" '
                    f'title="{_esc(tip["decision_id"])} · {_esc(tip["adjudicator"])} · '
                    f'{_esc(tip["decided_at"])}">{label}{corr}</span>')
        return f'<span class="wb-status pending">{_esc(_t(lang, "pending"))}</span>'

    def row_card(self, lang: str, ctx: RunCtx, row: dict, tip: dict | None,
                 adjudicator: str) -> str:
        doc, field = row["doc_id"], row["field"]
        slot = ctx.slot(doc, field)
        conflict = bool(slot and slot["conflict"])
        orphans = [o for o in ctx.orphans if o["doc_id"] == doc and o["field"] == field]
        anchor = f"row-{doc}-{field}"

        strength = row["support_strength"]
        gates = self._gates_html(lang, row)
        value = row["value"]
        value_html = (f'<span class="wb-value none">{_esc(_t(lang, "no_value"))}</span>'
                      if value in (None, "") else f'<span class="wb-value">{_esc(value)}</span>')
        status = self._status_chip(lang, tip, conflict)
        adj_href = (f"/adjudicate?run={_esc(ctx.name)}&doc={urllib.parse.quote(doc)}"
                    f"&field={urllib.parse.quote(field)}&lang={lang}")

        label = _FIELD_LABEL[lang].get(field, field)
        task = (_t(lang, "task_no_value", label=label) if value in (None, "")
                else _t(lang, "task_with_value", label=label, value=value))
        return f"""<div class="wb-row" id="{_esc(anchor)}">
<div class="wb-row-head">
<span class="wb-doc" title="{_esc(doc)}">{_esc(doc[:8])}</span>
<span class="wb-field">{_esc(label)}<span class="wb-raw">{_esc(field)}</span></span>
{value_html}
<span class="wb-badge {strength}">{_esc(_STRENGTH_LABEL[lang][strength])}</span>
<span class="wb-gates">{gates}</span>
{status}
<a class="wb-adj-link" href="{adj_href}">{_esc(_t(lang, "open_adj"))}</a>
</div>
<div class="wb-task">{_esc(task)}</div>
{self._vision_suggest(lang, ctx, row)}
{self._evidence(lang, ctx, row)}
{self._decide_form(lang, ctx, row, tip, conflict, len(orphans), adjudicator)}
</div>"""

    def _vision_suggest(self, lang: str, ctx: RunCtx, row: dict) -> str:
        """读图预填建议:一致 → 可「采用」(只预填表单,不写账本);
        分歧 → 摊开各读者的值,不给采用按钮;全弃权 → 如实说也看不清。

        一致性用与双模式门禁同一套归一化(fields.normalise)—— 两侧同规则,
        不搞第二套「差不多就行」的比较。
        """
        answers = ctx.vision.get((row["doc_id"], row["field"]))
        if not answers:
            return ""
        label = _esc(_t(lang, "vision_suggest"))
        live = [(m, v) for m, v in answers if v and v.upper() != "ABSTAIN"]
        if not live:
            return (f'<div class="wb-vision-suggest muted"><span class="wb-vs-label">'
                    f'{label}</span> <span class="wb-vs-blind">'
                    f'{_esc(_t(lang, "vision_blind"))}</span></div>')
        from .fields import FIELD_KINDS, normalise

        kind = FIELD_KINDS.get(row["field"])
        normalised = {normalise(v, kind) for _, v in live}
        if len(normalised) == 1:
            value = live[0][1]
            value_norm = normalise(value, kind) or str(value).strip()
            rejected = {(normalise(r["value"], kind) or str(r["value"]).strip())
                        for r in row["rejections"]}
            if value_norm in rejected:
                # 同值已被冻结拒掉(绑不进本文档 —— 注入载荷也走这条路):
                # 建议层如实展示但绝不给「采用」按钮,否则 200px 外写着
                # 「冻结时被拒」、这里一个按钮就把它架空(82 评 P1-5)
                return (f'<div class="wb-vision-suggest muted"><span class="wb-vs-label">'
                        f'{label}</span> <b class="wb-vs-value">{_esc(value)}</b>'
                        f'<span class="wb-vs-rejected">'
                        f'{_esc(_t(lang, "vision_rejected"))}</span></div>')
            return (f'<div class="wb-vision-suggest"><span class="wb-vs-label">{label}</span> '
                    f'<b class="wb-vs-value">{_esc(value)}</b>'
                    f'<span class="wb-vs-agree">{_esc(_t(lang, "vision_agree", a=len(live), n=len(answers)))}</span>'
                    f'<button type="button" class="wb-vs-adopt" data-value="{_esc(value)}" '
                    f'data-rationale="{_esc(_t(lang, "vision_rationale"))}">'
                    f'{_esc(_t(lang, "vision_adopt"))}</button></div>')
        split = " · ".join(f"{_esc(m)}={_esc(v)}" for m, v in live)
        return (f'<div class="wb-vision-suggest"><span class="wb-vs-label">{label}</span> '
                f'<span class="wb-vs-split">{_esc(_t(lang, "vision_split"))}:{split}</span></div>')

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
            items = "".join(f"<li>{_esc(_lim(lang, x))}</li>" for x in row["limitations"])
            parts.append(f"<ul>{items}</ul>")
        inner = "".join(parts) or "—"
        # 默认摊开:证据是复核的主信息,不是高级选项 —— 每行多点一下才看得见,
        # 这个交互就是无意义的(2026-08-03 用户原话)。仍可手动折叠。
        return (f'<details class="wb-evidence" open><summary>{_esc(_t(lang, "evidence"))}'
                f"</summary>{inner}</details>")

    def _decide_form(self, lang: str, ctx: RunCtx, row: dict, tip: dict | None,
                     conflict: bool, n_orphans: int, adjudicator: str,
                     next_hint: str = "") -> str:
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
        # 决策集按槽位形状分(81 评 P0):有冻结声明 → accept/reject/correct/abstain;
        # 无声明 → confirm_absent(页面上确实没有)/correct(补录)/
        # not_applicable(不适用)/abstain —— 「确认没有」和「人看不懂」不许混
        decisions_for_row = (_DECISIONS[:1] + _DECISIONS[3:]) if claim_id \
            else (_DECISIONS[1:3] + _DECISIONS[4:])
        # 一键快路(2026-08-05 用户实测):「原值正确」是复核的主流量,
        # 不该要四次点击。有声明 → accept 预填;草稿被冻结拒 → correct
        # 预填被拒草稿的值(冻结绑定是机械门槛,人看了页面说对就是对,
        # 账本记 correct + 人工理由,诚实)。仍是人逐槽点击,不批量。
        quick = ""
        draft_value = next((r["value"] for r in row["rejections"]
                            if r.get("value")), None)
        if claim_id:
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="accept" data-value="" '
                     f'data-rationale="{_esc(_t(lang, "accept_preset"))}">'
                     f'{_esc(_t(lang, "quick_accept"))}</button>')
        elif draft_value:
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="correct" data-value="{_esc(draft_value)}" '
                     f'data-rationale="{_esc(_t(lang, "quick_draft_rationale"))}">'
                     f'{_esc(_t(lang, "quick_draft", value=draft_value))}</button>')
        elif row.get("value") not in (None, ""):
            # 无声明也没走到冻结(如 OCR 受阻、草稿被排除),但 DWS 读到了值
            # —— 人看页面确认后采用该值,账本记 correct + 人证理由
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="correct" data-value="{_esc(row["value"])}" '
                     f'data-rationale="{_esc(_t(lang, "quick_draft_rationale"))}">'
                     f'{_esc(_t(lang, "quick_dws", value=row["value"]))}</button>')
        radios = "".join(
            f'<label class="wb-radio {d}"><input type="radio" name="decision" '
            f'value="{d}" required>{_esc(_t(lang, d))}</label>'
            for d in decisions_for_row
        )
        chips = "".join(
            f'<button type="button" class="wb-issue-chip" data-text="{_esc(c)}">{_esc(c)}</button>'
            for c in _T[lang]["issue_chips"]
        )
        from .feedback import REASON_CODES

        reason_options = ('<option value=""></option>' + "".join(
            f'<option value="{c}">{c}</option>' for c in REASON_CODES))
        next_input = (f'<input type="hidden" name="next" value="{_esc(next_hint)}">'
                      if next_hint else "")
        return f"""<div class="wb-decide">{''.join(notes)}
<form class="decide" method="post" action="/decide"
 data-accept-preset="{_esc(_t(lang, 'accept_preset'))}">
<input type="hidden" name="run" value="{_esc(ctx.name)}">
<input type="hidden" name="doc" value="{_esc(doc)}">
<input type="hidden" name="field" value="{_esc(field)}">
<input type="hidden" name="claim_id" value="{_esc(claim_id)}">
<input type="hidden" name="supersedes" value="{_esc(supersedes)}">
<input type="hidden" name="lang" value="{_esc(lang)}">{next_input}
{quick}
<div class="wb-decide-row">{radios}
<input class="wb-corr" type="text" name="corrected_value"
 placeholder="{_esc(_t(lang, 'corrected_ph'))}"></div>
<textarea class="wb-rationale" name="rationale" rows="2" required
 placeholder="{_esc(_t(lang, 'rationale_ph'))}"></textarea>
<div class="wb-issue-chips">{chips}</div>
<div class="wb-decide-row"><label class="wb-label">{_esc(_t(lang, 'reason_code_label'))}
<select name="reason_code" class="wb-reason">{reason_options}</select></label></div>
<div class="wb-decide-row">
<input class="wb-adjudicator" type="text" name="adjudicator" required
 placeholder="{_esc(_t(lang, 'adjudicator_ph'))}" value="{_esc(adjudicator)}">
<button type="submit" class="wb-btn" data-confirm="{_esc(_t(lang, 'confirm'))}">
{_esc(_t(lang, 'submit'))}</button></div>
</form></div>"""

    # ---- Gradescope 风格单槽裁决页
    @staticmethod
    def _queue_order(ctx: RunCtx) -> list[dict]:
        """复核队列序(分诊序):需要裁决的行在前,印证行(抽检)在后,
        组内保矩阵原序 —— 与队列页的分节呈现严格一致,两处不许各排各的。"""
        rows = ctx.matrix["rows"]
        return ([r for r in rows if r["requires_adjudication"]]
                + [r for r in rows if not r["requires_adjudication"]])

    @staticmethod
    def _decided(ctx: RunCtx, row: dict) -> bool:
        return bool((ctx.slot(row["doc_id"], row["field"]) or {}).get("tip"))

    def adjudicate_page(self, lang: str, run_dir: Path, params: dict) -> str:
        ctx = RunCtx(run_dir)
        doc = params.get("doc", [""])[0]
        field = params.get("field", [""])[0]
        row = next((r for r in ctx.matrix["rows"]
                    if r["doc_id"] == doc and r["field"] == field), None)
        if row is None:
            raise _HttpError(404, f"槽位不存在:{doc}/{field}", run=ctx.name)
        ordered = self._queue_order(ctx)
        idx = next(i for i, r in enumerate(ordered)
                   if r["doc_id"] == doc and r["field"] == field)
        slot = ctx.slot(doc, field)
        tip = slot["tip"] if slot else None
        conflict = bool(slot and slot["conflict"])
        orphans = [o for o in ctx.orphans
                   if o["doc_id"] == doc and o["field"] == field]
        adjudicator = params.get("adjudicator", [""])[0]
        try:
            page_no = int(params.get("page", [""])[0])
        except ValueError:
            page_no = None
        body = f"""
<div class="wb-adj">
<div class="wb-adj-left">{self._page_column(lang, ctx, row, page_no)}</div>
<div class="wb-adj-right">{self._judgement_card(lang, ctx, row, tip, conflict,
                                                 len(orphans), adjudicator)}</div>
</div>
{self._adj_nav(lang, ctx, ordered, idx)}
<div class="wb-footer">{_esc(_t(lang, 'snapshot'))}={_esc(ctx.snapshot_id)}</div>"""
        return self.page(lang, "queue", body, run_name=ctx.name,
                         notice=self._notice(lang, params),
                         ooc=ctx.manifest.get("out_of_calibration", False),
                         compact=True)

    def _page_column(self, lang: str, ctx: RunCtx, row: dict,
                     page: int | None = None) -> str:
        """左栏:整页渲染 + bbox overlay(不重渲染图片,相对坐标 → CSS 百分比)。

        两类框两种颜色:span_ids = 冻结绑定(机检确定性,绿实线);
        cited_span_ids = DWS 指向(advisory,紫虚线)—— 颜色纪律与全站一致,
        图例注明。多页文档给页码切换(服务器端 ?page=,零 JS 依赖):
        默认落在 span 所在页,没有 span 就第 1 页。
        """
        doc = row["doc_id"]
        containing = [ctx.spans_by_id[s] for s in row["span_ids"]
                      if s in ctx.spans_by_id]
        cited = [ctx.spans_by_id[s] for s in row.get("cited_span_ids", [])
                 if s in ctx.spans_by_id and s not in row["span_ids"]]
        pages_dir = ctx.dir / "pages"
        available = sorted(
            int(p.stem.rsplit("-", 1)[1])
            for p in pages_dir.glob(f"{doc}-*.png")
            if p.stem.rsplit("-", 1)[1].isdigit()) if pages_dir.is_dir() else []
        span_pages = sorted({s["page"] for s in containing + cited
                             if s.get("bbox_rel")})
        current = page if page in available else (
            span_pages[0] if span_pages else (available[0] if available else 1))
        tabs = ""
        if len(available) > 1:
            links = []
            for n in available:
                cls = "wb-page-tab active" if n == current else "wb-page-tab"
                links.append(
                    f'<a class="{cls}" href="/adjudicate?run={_esc(ctx.name)}'
                    f'&doc={_esc(doc)}&field={_esc(row["field"])}'
                    f'&lang={_esc(lang)}&page={n}">p{n}</a>')
            tabs = f'<div class="wb-page-tabs">{"".join(links)}</div>'
        blocks = []
        img = pages_dir / f"{doc}-{current}.png"
        if img.is_file():
            src = f"/files/{ctx.name}/pages/{urllib.parse.quote(img.name)}"
            overlays = []
            for spans, cls in ((containing, "wb-hl-bind"), (cited, "wb-hl-cited")):
                for s in spans:
                    rect = s.get("bbox_rel")
                    if not rect or s.get("page") != current:
                        continue
                    x0, y0, x1, y1 = rect
                    style = (f"left:{x0 * 100:.3f}%;top:{y0 * 100:.3f}%;"
                             f"width:{max(x1 - x0, 0.0) * 100:.3f}%;"
                             f"height:{max(y1 - y0, 0.0) * 100:.3f}%")
                    overlays.append(
                        f'<div class="wb-hl {cls}" style="{style}" '
                        f'title="{_esc(s["span_id"])} · '
                        f'{_esc(s.get("printed_label", ""))}"></div>')
            blocks.append(
                f'<figure class="wb-page-wrap"><figcaption class="wb-page-cap">'
                f'{_esc(doc[:8])} · p{current}{tabs}</figcaption>'
                f'<div class="wb-page-stage">'
                f'<img class="wb-page" src="{src}" alt="{_esc(doc)} p{current}">'
                f'{"".join(overlays)}</div></figure>')
        legend_items = []
        if containing:
            legend_items.append(
                f'<span class="wb-legend-item"><span class="wb-legend-swatch bind">'
                f'</span>{_esc(_t(lang, "legend_bind"))}</span>')
        if cited:
            legend_items.append(
                f'<span class="wb-legend-item"><span class="wb-legend-swatch cited">'
                f'</span>{_esc(_t(lang, "legend_cited"))}</span>')
        legend = (f'<div class="wb-legend">{"".join(legend_items)}</div>'
                  if legend_items else "")
        if not blocks:
            return (f'<h2 class="wb-adj-colhead">{_esc(_t(lang, "page_view"))}</h2>'
                    f'<div class="wb-banner">{_esc(_t(lang, "no_page"))}</div>')
        return (f'<h2 class="wb-adj-colhead">{_esc(_t(lang, "page_view"))}</h2>'
                f'{"".join(blocks)}{legend}')

    def _judgement_card(self, lang: str, ctx: RunCtx, row: dict,
                        tip: dict | None, conflict: bool, n_orphans: int,
                        adjudicator: str) -> str:
        """右栏判定卡:字段、冻结值(或「无声明」)、支持强度、六道门禁、
        来源层 / 口径、状态与来源、证据与限制、决策表单(与队列页同一套)。"""
        doc, field = row["doc_id"], row["field"]
        claim_id = ctx.claim_by_slot.get((doc, field), "")
        value = row["value"]
        if not claim_id:
            value_html = (f'<span class="wb-value none">'
                          f'{_esc(_t(lang, "no_claim"))}</span>')
        elif value in (None, ""):
            value_html = (f'<span class="wb-value none">'
                          f'{_esc(_t(lang, "no_value"))}</span>')
        else:
            value_html = f'<span class="wb-value">{_esc(value)}</span>'
        strength = row["support_strength"]
        label = _FIELD_LABEL[lang].get(field, field)
        task = (_t(lang, "task_no_value", label=label) if value in (None, "")
                else _t(lang, "task_with_value", label=label, value=value))
        tiers = " · ".join(row.get("source_tiers") or []) or "—"
        applicability = row.get("applicability") or "—"
        policy = ""
        if not tip and not conflict and not row["requires_adjudication"]:
            policy = f'<div class="wb-policy">{_esc(_t(lang, "policy_note"))}</div>'
        why = self._why_html(lang, row)
        return f"""<div class="wb-adj-card">
<div class="wb-row-head">
<span class="wb-doc" title="{_esc(doc)}">{_esc(doc[:8])}</span>
<span class="wb-field">{_esc(label)}<span class="wb-raw">{_esc(field)}</span></span>
{self._status_chip(lang, tip, conflict)}
</div>
<div class="wb-task">{_esc(task)}</div>
{why}
<div class="wb-adj-verdict">
<h2 class="wb-adj-colhead">{_esc(_t(lang, 'judgement'))}</h2>
<div class="wb-adj-kv"><span class="wb-adj-k">{_esc(_t(lang, 'frozen_value'))}</span>
{value_html}</div>
<div class="wb-adj-kv"><span class="wb-badge {strength}">{_esc(_STRENGTH_LABEL[lang][strength])}</span>
<span class="wb-label">{_esc(_t(lang, 'src_tiers'))}: {_esc(tiers)} ·
{_esc(_t(lang, 'applicability'))}: {_esc(applicability)}</span></div>
<div class="wb-gates">{self._gates_html(lang, row)}</div>
{policy}
</div>
{self._vision_suggest(lang, ctx, row)}
{self._evidence(lang, ctx, row)}
{self._decide_form(lang, ctx, row, tip, conflict, n_orphans, adjudicator,
                   next_hint="adjudicate")}
</div>"""

    def _why_html(self, lang: str, row: dict) -> str:
        """「为什么在队列里」—— 入队原因放在判定卡顶部显眼处(2026-08-05
        用户实测:全绿 chips + 小字限制 = 以为系统让自己白审)。
        门禁绿只代表「在 DWS 数据上自洽」,不代表独立核查覆盖过。"""
        if not row.get("requires_adjudication"):
            return ""
        codes = row.get("reason_codes") or []
        # CLEAN 只是「没毛病」的占位,不是入队原因 —— QA_SAMPLE 等真原因
        # 常排在它后面,跳过占位找第一个实义码
        first = next((c for c in codes if c != "CLEAN"), "")
        if first == "INFRA_BLOCKED":
            key, cls, kw = "why_infra", "blocked", {}
        elif first == "SLOT_BLOCKING":
            key, cls, kw = "why_slot", "blocked", {}
        elif first == "UNSUPPORTED":
            key, cls, kw = "why_unsupported", "", {}
        elif first == "LABEL_CONVENTION_DISPUTED":
            key, cls, kw = "why_disputed", "", {}
        elif first.startswith("GATE_FAIL:"):
            gates = ", ".join(c.split(":", 1)[1] for c in codes
                              if c.startswith("GATE_FAIL:"))
            key, cls, kw = "why_gate_fail", "blocked", {"gates": gates}
        elif first.startswith("GATE_WARNING:"):
            gates = ", ".join(c.split(":", 1)[1] for c in codes
                              if c.startswith("GATE_WARNING:"))
            key, cls, kw = "why_gate_warn", "", {"gates": gates}
        elif first.startswith("QA_SAMPLE:"):
            key, cls, kw = "why_qa", "", {}
        else:
            return ""
        return (f'<div class="wb-why {cls}"><b>{_esc(_t(lang, "why_queue"))}</b>'
                f'{_esc(_t(lang, key, **kw))}</div>')

    def _adj_nav(self, lang: str, ctx: RunCtx, ordered: list[dict],
                 idx: int) -> str:
        """底栏:上一条 / 下一条未裁决(按分诊序)+ 队列进度 + 回队列锚点。"""
        row = ordered[idx]
        doc, field = row["doc_id"], row["field"]
        prev_r = next((r for r in reversed(ordered[:idx])
                       if not self._decided(ctx, r)), None)
        next_r = next((r for r in ordered[idx + 1:]
                       if not self._decided(ctx, r)), None)
        decided = sum(1 for r in ordered if self._decided(ctx, r))

        def _btn(target: dict | None, key: str) -> str:
            if target is None:
                return (f'<span class="wb-nav-btn disabled">'
                        f'{_esc(_t(lang, "none_pending"))}</span>')
            href = (f"/adjudicate?run={_esc(ctx.name)}"
                    f"&doc={urllib.parse.quote(target['doc_id'])}"
                    f"&field={urllib.parse.quote(target['field'])}&lang={lang}")
            return f'<a class="wb-nav-btn" href="{href}">{_esc(_t(lang, key))}</a>'

        back = (f"/queue?run={_esc(ctx.name)}&lang={lang}"
                f"#row-{urllib.parse.quote(doc)}-{urllib.parse.quote(field)}")
        progress = _esc(_t(lang, "queue_pos", x=idx + 1, n=len(ordered), y=decided))
        return (f'<div class="wb-adj-nav">{_btn(prev_r, "prev_pending")}'
                f'<span class="wb-adj-progress">{progress} · '
                f'<a href="{back}">{_esc(_t(lang, "back"))}</a></span>'
                f'{_btn(next_r, "next_pending")}</div>')

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
        # 整单放行状态 + 最终值投影(纯投影,读文件;没有就现场重算)
        deliverable_path = ctx.dir / "deliverable.json"
        if deliverable_path.exists():
            deliverable = json.loads(deliverable_path.read_text(encoding="utf-8"))
        else:
            from .deliver import build_deliverable

            deliverable = build_deliverable(ctx.dir)
        by_status = deliverable["summary"]["by_status"]
        status_parts = " ".join(
            f'<span class="wb-stat"><b>{n}</b>{_esc(_t(lang, f"status_{k}"))}</span>'
            for k, n in sorted(by_status.items()))
        deliverable_dl = (
            f'<p><a class="wb-btn" href="/download/{ctx.name}/deliverable.json">'
            f'{_esc(_t(lang, "download_deliverable"))}</a></p>'
            if deliverable_path.exists() else "")
        release_html = (
            f'<h2>{_esc(_t(lang, "doc_status"))}</h2>'
            f'<div class="wb-report-stats">{status_parts}</div>'
            f'{deliverable_dl}'
            f'<p class="wb-label">{_esc(_t(lang, "release_note"))}</p>')
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
{release_html}
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
            if method == "GET" and path == "/adjudicate":
                params.setdefault("adjudicator", [self._adjudicator()])
                run = self._require_run(params)
                return self._html(200, self.bench.adjudicate_page(lang, run, params),
                                  set_cookies)
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
            reason_code=form.get("reason_code", [""])[0] or None,
        )
        notice = "recorded" if result["panel_refreshed"] else "recorded_stale"
        cookies = [("wb_adjudicator", adjudicator)]
        if form.get("next", [""])[0] == "adjudicate":
            # 裁决页提交:推进到分诊序里的下一个未裁决槽位;没有了就回队列。
            # 裁决本身一字未差 —— 只是落点不同(Gradescope 式流水作业)
            loc = self._next_adjudicate_url(
                run, form.get("doc", [""])[0], form.get("field", [""])[0],
                lang, notice)
        else:
            anchor = f"#row-{form.get('doc', [''])[0]}-{form.get('field', [''])[0]}"
            loc = f"/queue?run={run_name}&lang={lang}&notice={notice}{anchor}"
        self._redirect(loc, cookies)

    def _next_adjudicate_url(self, run: Path, doc: str, field: str,
                             lang: str, notice: str) -> str:
        ctx = RunCtx(run)
        ordered = Workbench._queue_order(ctx)
        idx = next((i for i, r in enumerate(ordered)
                    if r["doc_id"] == doc and r["field"] == field), -1)
        following = ordered[idx + 1:] if idx >= 0 else ordered
        nxt = next((r for r in following if not Workbench._decided(ctx, r)), None)
        if nxt is None:
            return f"/queue?run={ctx.name}&lang={lang}&notice={notice}"
        return (f"/adjudicate?run={ctx.name}&doc={urllib.parse.quote(nxt['doc_id'])}"
                f"&field={urllib.parse.quote(nxt['field'])}&lang={lang}"
                f"&notice={notice}")

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
        from .ingest import discover

        # 文档集 = input/pdfs ∪ raw:抽取失败的文档不许从 run 里隐身(评审 P1)
        doc_ids = sorted(set(discover(self.bench.ws)) | set(dws.stored_docs()))
        if not doc_ids:
            raise _HttpError(400, "raw/ 里没有存盘响应 —— 先放 PDF 并勾选 DWS 抽取")
        fingerprint = build_input_manifest(doc_ids)["execution_fingerprint"]
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
        if len(parts) != 2 or parts[1] not in ("audit_bundle.zip", "deliverable.json"):
            raise _HttpError(404, "bad path")
        run = self.bench.get_run(parts[0])
        target = (run or Path(".")) / parts[1]
        if run is None or not target.exists():
            raise _HttpError(404, f"{parts[1]} 不存在")
        mime = ("application/zip" if parts[1].endswith(".zip")
                else "application/json")
        self._send(200, target.read_bytes(), mime)


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
    # 主变量与别名同设:评委照 README export 过 INVOICELOOP_CORPUS 的话,
    # 只设别名会被环境里的主变量遮蔽,工作台直接读错根(81 评 P1-1 的产品侧孪生)
    os.environ["INVOICELOOP_CORPUS"] = str(workspace)
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
