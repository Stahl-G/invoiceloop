"""The H1 review workbench — a local loopback web application (127.0.0.1, no new
dependencies).

Shape decisions, pinned; do not quietly change them:
- **stdlib http.server, no Flask or FastAPI** — the pyproject runtime still has
  exactly one dependency, requests, so a clean clone plus `pip install .` is enough
  and installs nothing extra.
- **Server-rendered HTML with progressive-enhancement JS** — everything except
  browser upload works with JS off, and upload falls back to the input contract
  (put the PDF in workspace/input/pdfs/).
- **A person writes adjudications, and only adjudications** — /decide goes through
  the same checks as adjudicate.append_adjudication (snapshot consistency, the
  claim/doc/field triple, supersession). The workbench opens no back door.
- **decided_at is stamped by the server at click time** — clicking *is* the act of
  a person supplying the time. An adjudication is human input, not a recomputed
  artifact, so this does not violate "artifacts never read the wall clock"; run
  artifacts remain fully deterministic.
- **A review scope is a write boundary, not a visual filter** — when supplied at
  server start, the same ordered allowlist constrains queue rendering, navigation,
  direct slot URLs, and `/decide`.
- Visual discipline borrowed from briefloop-prototypes: DWS/model values are purple
  (advisory, never green), human confirmation is blue, deterministic pass is green,
  blocked is red, unavailable is grey.

Route contract (tests/test_workbench.py is the authority):
    GET  / /queue /adjudicate /report /upload /deliver /files/<run>/<rel> /download/<run>/audit_bundle.zip
    POST /decide /upload?filename= /ingest /bundle /verify (raw bytes)

/adjudicate is a Gradescope-style single-slot page: the left column renders the
full page with bbox highlight overlays (frozen binding in a solid green line,
DWS citation in a dashed purple one, and passing literal document-type evidence
in a dotted green one). The right column reads only the frozen
`gate_report.document_checks` result and presents document class as context: it
never changes buttons, preselects a decision, or removes a slot. Runs created
before that key existed are shown as not measured; the workbench never backfills
a modern result into their history. The right column also holds the decision form
(the same form fields and the same /decide endpoint as the queue page); a refused
submission re-renders *this same page* with HTTP 400 —
everything the reviewer typed is filled back in and the reason is shown beside
the form, in interface words rather than the raw exception (the exception text
itself is unchanged; it belongs to API callers and logs). The footer navigates to
the previous or next unadjudicated slot in triage order. The form carries one
extra hidden field, next=adjudicate: on submit the server advances to the next
unadjudicated slot in queue order, while a submit without it (from the queue
page) returns to the queue anchor. The adjudication semantics of the two paths
are identical, and a refusal lands on this page either way.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from . import plainwords as _pw
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
#: Cloud Run / 容器公开绑定用 0.0.0.0;默认仍是 loopback(见 make_server)。
PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::"})
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
        "search_ph": "doc id or field…", "search_btn": "Search",
        "upload": "Upload", "deliver": "Deliver & verify",
        "improve": "Improvement loop",
        "imp_intro": "What reviewers actually wrote, grouped by cohort. "
                     "Candidates are leads, not authorisations — you write "
                     "the proposal, evaluate re-routes it counterfactually, "
                     "and only a human promotes it.",
        "imp_overturn": "Auto-accepts a human overturned (tightening signal)",
        "imp_overturn_none": "None — no policy-released slot has been "
                             "overturned in this workspace.",
        "imp_absence": "Expected-absence candidates",
        "imp_low_yield": "Low-yield candidates (high review, zero correction)",
        "imp_notes": "Reviewer's own words",
        "imp_no_notes": "No reviewer notes yet — run a review round first.",
        "imp_model": "Model draft (advisory — a human decides)",
        "imp_model_none": "No model draft. Run `invoiceloop suggest "
                          "--workspace <ws>` to have a model read the notes "
                          "above and draft proposals.",
        "imp_cites": "reads",
        "imp_dropped": "Drafts rejected by the validator",
        "imp_cmd": "Proposal command (copy, edit, run — nothing is written "
                   "from this page)",
        "imp_lead": "Every note you wrote while reviewing has been read. "
                    "Below are the rule changes proposed from them — none "
                    "takes effect until you say so, and you can always say no.",
        "imp_alert_h": "Worth your attention: something released "
                       "automatically, which you then overturned",
        "imp_alert_body": "These are cases the system judged safe to handle "
                          "without you, and you corrected or rejected on "
                          "review. This is the most important kind of record "
                          "— it means a rule is too loose.",
        "imp_sug_h": "The AI read your notes and proposed this",
        "imp_sug_sub": "Read {n} notes you wrote, proposed {m} changes. The "
                       "AI decides nothing; every proposal must name which "
                       "of your notes it rests on.",
        "imp_ai": "AI proposal",
        "imp_conf": "Confidence",
        "imp_why": "Why",
        "imp_then": "What changes if you accept",
        "imp_your_words": "Your own words",
        "imp_notes_sub": "These are the AI's only input. It sees nothing "
                         "else, and may not propose anything uncited.",
        "imp_tech": "Technical detail",
        "imp_rewrite": "Rewrite these in your own words "
                       "(yours is what the ledger records)",
        "imp_carried": "carried over",
        "imp_eval_h": "Trial run (replayed over invoices you already reviewed)",
        "imp_cand_schema": "Reword the extraction hint so this field is found "
                           "more often",
        "imp_cand_unknown": "A rule change (see technical detail)",
        "imp_reextract_warn": "This change alters what the extraction service "
                              "is told, so a replay cannot measure it — a "
                              "batch must actually be re-extracted, which "
                              "costs money. You set the size and the cap.",
        "imp_adopt": "Adopt as a pending change",
        "imp_adopt_hint": "Adopting writes a candidate harness and evaluates "
                          "it. It does not change the active harness — "
                          "promotion is a separate, signed step below.",
        "imp_adopt_schema_hint": "Adopting writes a candidate. Schema "
                                 "candidates cannot be evaluated by "
                                 "counterfactual replay — they need a "
                                 "re-extraction that spends credits, which "
                                 "you authorise below.",
        "imp_words": "Your words (the model's draft is a starting point — "
                     "you sign this, so say it your way)",
        "imp_cohort_id": "Cohort id",
        "imp_finding": "Finding",
        "imp_prediction": "Prediction (say what this could damage)",
        "imp_new_desc": "New field description (sent to DWS)",
        "imp_candidates": "Waiting on your decision",
        "imp_no_candidates": "No candidate yet. Adopt a draft above, or run "
                             "`improve propose` on the command line.",
        "imp_active": "active",
        "imp_eval_none": "Not evaluated — a candidate cannot be promoted "
                         "until it has been.",
        "imp_eval_run": "Try it (free)",
        "imp_eval_reextract": "Re-extract a batch to try it (costs money)",
        "imp_sample": "How many invoices to try on",
        "imp_budget": "Spending cap",
        "imp_gate_ok": "Safety checks pass — may take effect",
        "imp_gate_no": "Safety checks fail — this cannot take effect",
        "imp_promote": "I agree — make it effective",
        "imp_promote_hint": "Promotion changes how every future invoice is "
                            "routed. Your name and reason go into the "
                            "promotion ledger, permanently.",
        "imp_approved_by": "Your name",
        "imp_rationale": "Reason (what residual risk are you accepting?)",
        "imp_approved_at": "Decided at (ISO 8601)",
        "imp_load": "Fields you have to look at",
        "imp_silent_absent": "Treated a value that was on the page as absent",
        "imp_silent_wrong": "Let a mis-copied value through",
        "imp_basis": "Evidence basis",
        "imp_unscored": "No ground truth in this workspace — safety unscored, "
                        "so the gates cannot vouch for this candidate.",
        "imp_schema_changed": "changes the extraction schema",
        "imp_revoke_manual": "Revocation is not a candidate type — there is "
                             "no one-click path. Use `improve rollback` to "
                             "return to a known policy, or edit the policy by "
                             "hand and propose again.",
        "imp_gate_unrun": "Safety gates did not run (no ground truth in this "
                          "workspace) — they did not refuse this candidate, "
                          "but they do not vouch for it either. Whether "
                          "silent errors or review load went up is unknown.",
        "imp_lineage_bad": "Lineage does not match the active harness — this "
                           "candidate was derived from a different one "
                           "(usually an already-promoted candidate). Promote "
                           "would refuse it; propose again from active.",
        "all": "All", "pending": "Pending", "done": "Decided",
        "sec_required": "Needs adjudication ({n})",
        "sec_corroborated": "Corroborated — no machine flags, spot-check ({n})",
        "reviewed": "{x} / {y} reviewed",
        "accept": "Accept", "reject": "Reject", "correct": "Correct", "abstain": "Abstain",
        "confirm_absent": "Confirm absent", "not_applicable": "N/A",
        "corrected_ph": "corrected value",
        "rationale_ph": "Issue / rationale (required) — write down what's wrong",
        # 「可选」是误导:不填 → feedback.actionable=false → 整条被 mine 排除。
        # 对复核来说它不是可选的,所以说后果,不说「可选」(2026-08-08)
        "reason_code_label": "Reason code — without one this note never "
                             "reaches the improvement loop:",
        "confidence_label": "Flag doubt (only if unsure) — “low” also drops "
                            "this note from the improvement loop:",
        # 提交被拒:回到本槽,内容原样保留,错误说界面上的词
        "err_not_recorded": "This submission was not recorded",
        "err_kept": "Everything you typed is still below — fix this and "
                    "submit again.",
        "err_combo": "The reason code “{reason}” only goes with “{allowed}”; "
                     "you picked “{decision}”. Change one of them, or clear "
                     "the reason code — a mis-picked code feeds the "
                     "improvement loop a wrong supervision signal.",
        "conf_high": "high", "conf_medium": "medium", "conf_low": "low",
        "adjudicator_ph": "reviewer name",
        "issue_chips": ["matches the page", "wrong value", "wrong location",
                        "illegible", "label-convention conflict", "not on page", "other"],
        "accept_preset": "matches the page",
        "absent_preset": "not on page",
        "quick_accept": "✓ value is right — accept & next",
        "quick_accept_fp": "✓ right — and this slot did not need review",
        "quick_fp_rationale": "matches the page; this queue rule was a "
                              "false positive",
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
        "why_absent_qa": "expected-absent field spot-check — confirm the value "
                         "is truly not on the page (one click if so)",
        "quick_absent": "✓ not on the page — confirm absent & next",
        "quick_absent_rationale": "checked the page — value is not there",
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
        "doctype_title": "Document type",
        "doctype_pass": "Page-evidenced type: {label}. This is context only; "
                        "whether the field applies is still your decision.",
        "doctype_proof": "literal “{phrase}” · p{page}",
        "doctype_fail": "DWS proposed {label}, but there is no literal page "
                        "evidence. Do not use that type to judge field "
                        "applicability.",
        "doctype_no_claim": "DWS gave no document type. Judge this field from "
                            "the page.",
        "doctype_unmapped": "DWS type “{raw}” is outside the controlled "
                            "vocabulary. Judge this field from the page.",
        "doctype_ocr_unavailable": "Document type could not be checked because "
                                    "independent OCR is unavailable. Not checked "
                                    "is not a pass.",
        "doctype_not_measured": "This run did not execute the document-type "
                                "check. A later check cannot be backfilled as "
                                "the result at review time.",
        "doctype_not_checked": "This run has document-type checks, but none for "
                               "this document. Do not infer a type.",
        "doctype_malformed": "The frozen type check says pass, but its literal "
                             "evidence is incomplete. Do not use the type.",
        "legend_doctype": "literal document-type evidence",
        "task_with_value": "Task: DWS read “{value}” as {label}. Confirm that "
                           "the value actually belongs to this field, not merely "
                           "that it appears somewhere on the page.",
        "task_no_value": "Task: DWS gave no {label}. Check whether the page "
                         "states it explicitly; do not derive it from another "
                         "field or from payment terms.",
        "task_doctype_with_value": "Task: page evidence supports that this is "
                                   "a {doctype}. Check whether DWS correctly "
                                   "mapped “{value}” to {label}, not merely "
                                   "whether the value appears on the page.",
        "task_doctype_no_value": "Task: page evidence supports that this is a "
                                 "{doctype}. Check whether the page explicitly "
                                 "states {label}. Do not assume it is absent "
                                 "from the document type, or derive it from "
                                 "payment terms or another field.",
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
        "status_ready_for_approval": "awaiting your approval",
        "status_ready_for_approval_with_caveats":
            "awaiting approval (w/ caveats)",
        "status_approved_for_export": "approved for export",
        "status_approved_for_export_with_caveats":
            "approved for export (w/ caveats)",
        "approve_h": "Approve for export",
        "approve_lead": "Every slot on these documents has been dealt with — "
                        "by you or by the routing policy. Posting them is a "
                        "separate decision, and it is yours: the system will "
                        "not sign off an invoice.",
        "approve_unreviewed": "Released by policy without individual review: "
                              "{fields}",
        "approve_unreviewed_tier1": "including key fields: {fields}",
        "approve_none_unreviewed": "Every slot on this document was decided by "
                                   "a person.",
        "approve_by": "Your name",
        "approve_why": "Why you are approving",
        "approve_btn": "Approve for export",
        "approve_stale": "Approved by {who} on {when}, but the content has "
                         "changed since — approve again to export.",
        "approve_done": "Approved for export by {who} on {when}.",
        "approve_caveats_kept": "The caveats above stay on this document after "
                                "approval; approving does not clear them.",
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
        "notice_approved": "Approved for export. Your name, your reason and "
                           "what nobody reviewed are all in the ledger.",
        "notice_proposed": "Candidate written. It is not in effect — it must "
                           "pass evaluation and be promoted under your name.",
        "notice_evaluated": "Evaluated. The numbers are below, including what "
                            "it may have damaged.",
        "notice_promoted": "Promoted. Future runs use the new harness; the "
                           "promotion is in the ledger.",
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
        "hide_highlights": "Hide highlights",
        "show_highlights": "Show highlights",
        "open_clean_image": "Open clean image",
        "no_page": "No rendered page for this document — use the evidence "
                   "crops on the right.",
        "prev_pending": "← previous undecided",
        "next_pending": "next undecided →",
        "none_pending": "no more undecided",
        "queue_pos": "slot {x} / {n} · {y} decided",
        "review_scope": "Review scope: {n} slots · {name} · sha256 {digest}",
        "scope_outside": "This slot is outside the active review scope: {doc}/{field}",
        "scope_missing": "The review scope contains slots missing from this run: {slots}",
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
        "search_ph": "发票号 / 字段名…", "search_btn": "搜索",
        "upload": "上传", "deliver": "交付与验证",
        "improve": "改进循环",
        "imp_intro": "复核者到底写了什么,按 cohort 归堆。候选是线索,"
                     "不是授权 —— 提案由你写,evaluate 做反事实重路由,"
                     "promote 只有人能点。",
        "imp_overturn": "自动放行被人推翻(收紧信号)",
        "imp_overturn_none": "无 —— 本 workspace 还没有策略放行的槽被推翻。",
        "imp_absence": "预期缺失候选",
        "imp_low_yield": "低收益候选(高频复核、零修正)",
        "imp_notes": "你写过的全部意见",
        "imp_no_notes": "你还没写过复核意见。先去复核队列过一轮,这里就会有内容。",
        "imp_model": "模型草稿(顾问性质,人决定)",
        "imp_model_none": "没有模型草稿。跑 `invoiceloop suggest "
                          "--workspace <ws>` 让模型读上面这些原话出提案草稿。",
        "imp_cites": "读的是",
        "imp_dropped": "被挡下的 AI 建议(没出处或越权)",
        "imp_cmd": "提案命令(复制、改、自己跑)",
        "imp_lead": "你复核发票时写下的每一条意见,系统都读过了。"
                    "下面是据此提出的规则改动 —— 每一条都要你点头才会生效,"
                    "你随时可以不同意。",
        "imp_alert_h": "需要你注意:系统自动放过的,被你推翻了",
        "imp_alert_body": "下面这些是系统当时判断「不用麻烦人」、"
                          "而你复核时改掉或驳回了的。这类记录最要紧 —— "
                          "它说明规则放得太松了。",
        "imp_sug_h": "AI 读完你的意见,提了这些建议",
        "imp_sug_sub": "读了你写的 {n} 条意见,提出 {m} 条建议。"
                       "AI 没有决定权,它只能提;每条都必须说出依据的是你哪句话。",
        "imp_ai": "AI 建议",
        "imp_conf": "把握",
        "imp_why": "为什么这么建议",
        "imp_then": "采纳后会怎样",
        "imp_your_words": "你当时是这么写的",
        "imp_notes_sub": "这些是 AI 唯一的依据。它读不到别的东西,"
                         "也不许提没有出处的建议。",
        "imp_tech": "技术细节",
        "imp_rewrite": "我想改写这两段话(会记进账本的是你的版本)",
        "imp_carried": "上一轮携带",
        "imp_eval_h": "试算结果(拿你已经复核过的发票重放一遍)",
        "imp_cand_schema": "改进抽取说明,让系统更容易找到这个字段",
        "imp_cand_unknown": "一条规则改动(看技术细节)",
        "imp_reextract_warn": "这条改动动的是发给抽取服务的说明,"
                              "光靠重放算不出效果 —— 必须真的重抽一批发票,"
                              "会产生费用。份数和上限由你定。",
        "imp_adopt": "采纳,做成待定改动",
        "imp_adopt_hint": "采纳只是把它变成一条「待定改动」并试算一遍,"
                          "现在的规则一点都不会变。要不要真的生效,"
                          "在下面单独决定,而且要签你的名字。",
        "imp_adopt_schema_hint": "采纳只是把它变成一条「待定改动」,现在的规则"
                                 "不会变。这一类改动动的是发给抽取服务的说明,"
                                 "要看效果必须真的重抽一批发票,费用由你在下面授权。",
        "imp_words": "你的话(模型草稿只是起点 —— 签字的是你,用你自己的说法写)",
        "imp_cohort_id": "候选 cohort 名",
        "imp_finding": "用你自己的话说,这是怎么回事",
        "imp_prediction": "你预计它会带来什么(包括可能的坏处)",
        "imp_new_desc": "新的说明(这段话会发给抽取服务)",
        "imp_candidates": "等你拍板的改动",
        "imp_no_candidates": "还没有待定改动。在上面采纳一条 AI 建议,它就会出现在这里。",
        "imp_active": "当前 active",
        "imp_eval_none": "还没试算过。没试算过的改动不许生效 —— 先看看它会带来什么。",
        "imp_eval_run": "试算一下(不花钱)",
        "imp_eval_reextract": "重抽一批来试算(会产生费用)",
        "imp_sample": "抽多少张发票来试",
        "imp_budget": "费用上限",
        "imp_gate_ok": "安全检查通过 —— 可以生效",
        "imp_gate_no": "安全检查不通过,这条不能生效",
        "imp_promote": "我同意,从现在起生效",
        "imp_promote_hint": "同意之后,之后每一张发票都按新规则处理。"
                            "你的名字和理由会永久留在账本里,可以随时查到"
                            "是谁在什么时候基于什么理由做的这个决定。",
        "imp_approved_by": "你的名字",
        "imp_rationale": "你为什么同意?(写清你接受了什么风险)",
        "imp_approved_at": "决定时间",
        "imp_load": "需要你过目的字段",
        "imp_silent_absent": "把单据上真有的值当成了「没有」",
        "imp_silent_wrong": "把抄错的值直接放过了",
        "imp_basis": "证据基底",
        "imp_unscored": "这批发票没有标准答案可比对,所以「会不会漏值、"
                        "会不会放过错值」这两行没法算 —— 不是零,是不知道。",
        "imp_schema_changed": "改动了抽取 schema",
        "imp_revoke_manual": "这条建议是要「收回一条已经生效的规则」。"
                             "这件事没有一键按钮 —— 收紧要么退回上一版规则,"
                             "要么人工改完再走一遍这个流程。请找管理员处理。",
        "imp_gate_unrun": "安全检查没跑 —— 这批发票没有标准答案可比对。"
                          "系统没有拒绝这条改动,但也没有为它背书:"
                          "它会不会多漏几个值、会不会反而更费事,这里不知道。",
        "imp_lineage_bad": "这条改动是基于一版更早的规则做的,现在的规则已经"
                           "不是那一版了 —— 直接生效会覆盖掉中间的改动。"
                           "要用它,请照现在的规则重新采纳一次。",
        "all": "全部", "pending": "待复核", "done": "已裁决",
        "sec_required": "需要裁决 ({n})",
        "sec_corroborated": "印证行 —— 机器未见异常,抽检性质 ({n})",
        "reviewed": "已复核 {x} / {y}",
        "accept": "接受", "reject": "拒绝", "correct": "修正", "abstain": "弃权",
        "confirm_absent": "确认缺失", "not_applicable": "不适用",
        "corrected_ph": "修正值",
        "rationale_ph": "发现的问题 / 理由(必填)—— 把问题直接写在这里",
        # 「可选」是误导:不填 → feedback.actionable=false → 整条被 mine 排除。
        # 对复核来说它不是可选的,所以说后果,不说「可选」(2026-08-08)
        "reason_code_label": "原因码(不填,这条意见进不了改进循环):",
        "confidence_label": "标注存疑(只在没把握时填;标「低」这条意见"
                            "同样进不了改进循环):",
        # 提交被拒:回到本槽,内容原样保留,错误说界面上的词
        "err_not_recorded": "这次提交没有进账本",
        "err_kept": "你填的内容都还在下面,改完直接再提交。",
        "err_combo": "原因码「{reason}」只能配决策「{allowed}」,"
                     "你这次选的是「{decision}」。改其中一个,或者把原因码"
                     "清空 —— 点错的原因码会把错误的监督信号喂给改进循环。",
        "conf_high": "高", "conf_medium": "中", "conf_low": "低",
        "adjudicator_ph": "裁决人",
        "issue_chips": ["与页面一致", "值不对", "位置不对", "看不清", "口径冲突", "页面上没有", "其他"],
        "accept_preset": "与页面一致",
        "absent_preset": "页面上没有",
        "quick_accept": "✓ 原值正确 —— 接受,下一条",
        "quick_accept_fp": "✓ 原值正确,而且这条不该进队列",
        "quick_fp_rationale": "与页面一致;这条路由是误报",
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
        "why_absent_qa": "预期缺失字段的抽检 —— 确认页面上真没有即可,"
                         "没有就点「确认缺失」一键过",
        "quick_absent": "✓ 页面上没有 —— 确认缺失,下一条",
        "quick_absent_rationale": "看过页面,确实没有这个值",
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
        "doctype_title": "单据类型",
        "doctype_pass": "页面字面证据支持类别:{label}。这只提供上下文;"
                        "字段是否适用仍由你判断。",
        "doctype_proof": "字面“{phrase}” · 第 {page} 页",
        "doctype_fail": "DWS 自报为{label},但没有页面字面证据。"
                        "不得用它判断字段适用性。",
        "doctype_no_claim": "DWS 没给单据类型;请只按页面判断本字段。",
        "doctype_unmapped": "DWS 类型“{raw}”不在受控词表;"
                            "请只按页面判断本字段。",
        "doctype_ocr_unavailable": "独立 OCR 不可用,单据类型检查没跑完。"
                                    "没查过不等于通过。",
        "doctype_not_measured": "本 run 未执行单据类型检查;"
                                "后来的检查不能补算成当时的结果。",
        "doctype_not_checked": "本 run 有单据类型检查,但没有这份文档的结果;"
                               "不得猜类型。",
        "doctype_malformed": "冻结结果写着类型检查通过,但字面证据不完整;"
                             "不得使用该类型。",
        "legend_doctype": "单据类型字面证据",
        "task_with_value": "任务:DWS 把“{value}”读成{label}。"
                           "请确认该值确实属于{label},不只是出现在页面上。",
        "task_no_value": "任务:DWS 没给出{label}。请检查页面是否明确写出;"
                         "不要从相邻字段或付款条款推算。",
        "task_doctype_with_value": "任务:页面字面证据支持这是{doctype}。"
                                   "请确认 DWS 是否把“{value}”正确映射为{label},"
                                   "不只是确认这个值出现在页面上。",
        "task_doctype_no_value": "任务:页面字面证据支持这是{doctype}。"
                                 "请检查页面是否明确写出{label};"
                                 "不要仅凭单据类别假定缺失,"
                                 "也不要从付款条款或其他字段推算。",
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
        "status_ready_for_approval": "等你批准",
        "status_ready_for_approval_with_caveats": "等你批准(带披露)",
        "status_approved_for_export": "已批准外发",
        "status_approved_for_export_with_caveats": "已批准外发(带披露)",
        "approve_h": "批准外发",
        "approve_lead": "下面这些单据的每个槽都已处置 —— 你判的,或路由策略"
                        "判的。要不要入账是另一个决定,而且是你的决定:"
                        "系统不给单据签字。",
        "approve_unreviewed": "由策略放行、没有逐个人看的字段:{fields}",
        "approve_unreviewed_tier1": "其中关键字段:{fields}",
        "approve_none_unreviewed": "这份单的每个槽都是人判的。",
        "approve_by": "你的署名",
        "approve_why": "批准理由",
        "approve_btn": "批准外发",
        "approve_stale": "{who} 在 {when} 批准过,但之后内容变了 —— "
                         "要外发得重新批一次。",
        "approve_done": "{who} 于 {when} 批准外发。",
        "approve_caveats_kept": "上面的披露在批准之后仍然跟着这份单走;"
                                "批准不会把它抹掉。",
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
        "notice_approved": "已批准外发。你的署名、理由,以及这份单里没有人"
                           "看过的字段,都记进账本了。",
        "notice_proposed": "候选已写出。它还没有生效 —— 评测通过并由你署名晋升才算。",
        "notice_evaluated": "评测完成。数字在下面,包括它可能伤害了什么。",
        "notice_promoted": "已晋升。之后的 run 会用新 harness;晋升记录已入账本。",
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
        "hide_highlights": "隐藏高亮框",
        "show_highlights": "显示高亮框",
        "open_clean_image": "打开无框原图",
        "no_page": "本文档没有整页渲染 —— 用右侧的证据裁剪图复核。",
        "prev_pending": "← 上一条未裁决",
        "next_pending": "下一条未裁决 →",
        "none_pending": "没有未裁决的了",
        "queue_pos": "第 {x} / {n} 条 · 已裁决 {y}",
        "review_scope": "限定复核范围:{n} 槽 · {name} · sha256 {digest}",
        "scope_outside": "这个槽不在当前限定复核范围内:{doc}/{field}",
        "scope_missing": "限定复核范围含有当前 run 不存在的槽:{slots}",
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


def _dws_key() -> str | None:
    """抽取用的 DWS key:进程环境 → 项目 .env(统一入口,见 env.py)。
    工作台只问「有没有」,值不进页面、不进日志。"""
    from .env import credential

    return credential("dws")


def _esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def _json_compact(obj) -> str:
    """技术细节折叠区里的一行 JSON(不换行,不缩进)。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


_JS = r"""
// 心码下拉跟着决策走。判据**只从 option 的 data-decisions 读** ——
// 那串属性是服务器按 adjudicate.REASON_CODE_COMBOS 渲染的,前端不许内置
// 第二份表(两处定义会漂移,而漂移的表现是人填完一屏被服务器拒掉)。
// 三件事:配不上当前决策的选项藏起来、残值清掉、一对一的自动预填。
function wbReasonSync(form, decision) {
  var rc = form.querySelector('select[name=reason_code]');
  if (!rc) return;
  var only = [];
  for (var i = 0; i < rc.options.length; i++) {
    var opt = rc.options[i];
    var allowed = (opt.dataset.decisions || '').split(' ').filter(Boolean);
    var ok = !opt.value || !allowed.length || allowed.indexOf(decision) !== -1;
    opt.hidden = !ok;
    opt.disabled = !ok;
    if (ok && allowed.length === 1) only.push(opt.value);
  }
  var sel = rc.options[rc.selectedIndex];
  if (sel && sel.disabled) rc.value = '';         // 上一次留下的残值
  if (!rc.value && only.length === 1) rc.value = only[0];  // 决策已唯一确定
}
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
  // 接受/确认缺失的天然理由预设:空着就预填(可改可删);
  // 切走且理由一字未动过预设,就还回空白,不把预设带去别的决策
  var ta = form.querySelector('.wb-rationale');
  var presets = { accept: form.dataset.acceptPreset,
                  confirm_absent: form.dataset.absentPreset };
  if (ta) {
    if (presets[e.target.value] && !ta.value.trim()) {
      ta.value = presets[e.target.value];
    } else {
      for (var pk in presets) {
        if (pk !== e.target.value && presets[pk] && ta.value === presets[pk]) {
          ta.value = '';
          break;
        }
      }
    }
  }
  // 心码跟着决策裁剪:配不上的藏掉、残值清掉、一对一的自动预填。
  // 决策变了就重算 —— 界面不该让人拼出一个必然被拒的组合(2026-08-08)
  wbReasonSync(form, e.target.value);
});
document.addEventListener('click', function (e) {
  // 扁 bbox 的框线即使画在外侧,复核者也应能随时看完全无覆盖的原图。
  // 切换只改呈现,不改 span、裁决或任何持久状态。
  var hl = e.target.closest('.wb-hl-toggle');
  if (hl) {
    var figure = hl.closest('.wb-page-wrap');
    var stage = figure && figure.querySelector('.wb-page-stage');
    if (!stage) return;
    var off = stage.classList.toggle('wb-hl-off');
    hl.setAttribute('aria-pressed', off ? 'true' : 'false');
    hl.textContent = off ? hl.dataset.show : hl.dataset.hide;
    return;
  }
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
    // 按钮自带的心码最后写,盖过上面 change 事件的一对一预填 ——
    // 「不该进队列」那一支要的是 ROUTING_FALSE_POSITIVE,不是决策推出来的码
    var qrc = qform.querySelector('select[name=reason_code]');
    if (qrc) qrc.value = quick.dataset.reason || '';
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
    // chip 也带一对一心码,但**只在下拉还空着时**写:第一个点的 chip 定调,
    // 之后的不覆盖,人手选的更不覆盖 —— 连点多个 chip 时最后一个说了算
    // 会把监督标签变成手滑的产物。配不上当前决策的也不写(那一支已被
    // 裁剪禁用,写进去只是让人填完一屏再吃一个 400)
    var crc = form.querySelector('select[name=reason_code]');
    if (crc && !crc.value && chip.dataset.reason) {
      var want = crc.querySelector('option[value="' + chip.dataset.reason + '"]');
      if (want && !want.disabled) crc.value = chip.dataset.reason;
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
    // 载入时也裁剪一次心码 —— 浏览器回退/刷新会把上一次的选择还原回来,
    // 那个残值正是「弃权 + 上一条的心码」这类必被拒组合的来源。
    // 被拒回填的表单(data-rejected)跳过:那一屏的心码是人刚提交的,
    // 错误文案正指着它说事,清掉就成了「你选的是空」
    if (d && !form.dataset.rejected) wbReasonSync(form, d.value);
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


#: 心码的人类名字 —— 复核者在界面上读到的是「弃权」「确认缺失」,而
#: adjudicate 抛的原始异常说的是 abstain / ['confirm_absent'](2026-08-08
#: 用户实测:对不上号)。原始异常文本不动(给 API 调用方与日志,有测试
#: 钉着);对不上号的问题在呈现层解决。码本身一并显示 —— 它进账本,
#: 复核者对账时要认得出。
_REASON_LABEL = {
    "en": {"WRONG_VALUE": "Wrong value",
           "WRONG_FIELD_MAPPING": "Mapped to the wrong field",
           "BAD_SOURCE_BINDING": "Value doesn't bind to the page",
           "MISSING_EXTRACTION": "Extraction missed it",
           "NORMALIZATION_ERROR": "Normalisation error",
           "ROUTING_FALSE_NEGATIVE": "Should have been queued",
           "ROUTING_FALSE_POSITIVE": "Should not have been queued",
           "CONFIRMED_ABSENT": "Confirmed absent",
           "NOT_APPLICABLE": "Not applicable to this document",
           "AMBIGUOUS_DOCUMENT": "Document itself is unreadable",
           "PROVIDER_FAILURE": "Provider failure",
           "REVIEWER_PREFERENCE": "Reviewer preference", "OTHER": "Other"},
    "zh": {"WRONG_VALUE": "值不对",
           "WRONG_FIELD_MAPPING": "对错字段了",
           "BAD_SOURCE_BINDING": "值绑不到页面上",
           "MISSING_EXTRACTION": "抽取漏了",
           "NORMALIZATION_ERROR": "规范化出错",
           "ROUTING_FALSE_NEGATIVE": "该进队列却没进",
           "ROUTING_FALSE_POSITIVE": "不该进队列",
           "CONFIRMED_ABSENT": "确认缺失",
           "NOT_APPLICABLE": "本单不适用",
           "AMBIGUOUS_DOCUMENT": "单据本身看不清",
           "PROVIDER_FAILURE": "服务方故障",
           "REVIEWER_PREFERENCE": "复核者偏好", "OTHER": "其他"},
}


def _reason_label(lang: str, code: str) -> str:
    """心码 → 「人话(CODE)」。没收录的码原样显示(诚实,不编)。"""
    label = _REASON_LABEL.get(lang, _REASON_LABEL["en"]).get(code)
    return f"{label}({code})" if label else code


def _decide_error(lang: str, decision: str, reason_code: str,
                  exc: Exception) -> str:
    """裁决被拒 → 给复核者看的一句话。

    只翻译**呈现层认得出的**那一类:心码 ↔ 决策组合(判据从
    adjudicate.REASON_CODE_COMBOS 现读,不在这里复制第二份表)。
    其余异常原样透传 —— 编一句好听的话去盖住一个没预料到的失败,
    比 Python 的 repr 更坏。
    """
    from .adjudicate import REASON_CODE_COMBOS

    allowed = REASON_CODE_COMBOS.get(reason_code)
    if allowed is not None and decision not in allowed:
        return _t(lang, "err_combo",
                  reason=_reason_label(lang, reason_code),
                  allowed=" / ".join(_t(lang, d) for d in sorted(allowed)),
                  decision=_t(lang, decision) if decision in _DECISIONS
                  else decision)
    return str(exc)


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
_DOCTYPE_LABEL = {
    "en": {
        "credit_note": "Credit note", "proforma": "Pro forma invoice",
        "confirmation": "Order confirmation",
        "purchase_order": "Purchase order", "estimate": "Estimate / quote",
        "contract": "Contract", "receipt": "Receipt", "invoice": "Invoice",
    },
    "zh": {
        "credit_note": "贷记单", "proforma": "形式发票",
        "confirmation": "订单确认", "purchase_order": "采购订单",
        "estimate": "报价 / 估价单", "contract": "合同",
        "receipt": "收据", "invoice": "发票",
    },
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

@dataclass(frozen=True)
class ReviewScope:
    """Server-start review boundary loaded from a frozen slot list.

    This is not a visual filter.  It constrains every queue/navigation read and
    the `/decide` write path.  Otherwise a stale tab can write outside an
    experiment even when the index page only links to sampled slots.
    """

    source: Path
    slots: tuple[tuple[str, str], ...]
    sha256: str


def load_review_scope(path: Path | str) -> ReviewScope:
    """Read `{\"slots\": [\"doc|field\", ...]}` as an ordered write boundary."""
    source = Path(path).resolve()
    raw = source.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"review scope 不是合法 JSON:{source}") from exc
    values = payload.get("slots") if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not values:
        raise ValueError("review scope 必须含非空 slots 列表")
    slots: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if not isinstance(value, str) or value.count("|") != 1:
            raise ValueError(f"review scope 槽位必须是 doc|field,收到 {value!r}")
        doc, field = value.split("|", 1)
        if not doc or not field or value != value.strip():
            raise ValueError(f"review scope 槽位必须是非空 doc|field,收到 {value!r}")
        key = (doc, field)
        if key in seen:
            raise ValueError(f"review scope 有重复槽位:{value}")
        seen.add(key)
        slots.append(key)
    return ReviewScope(source=source, slots=tuple(slots),
                       sha256=hashlib.sha256(raw).hexdigest())

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
        # Presence of the top-level key is itself historical evidence.  Runs
        # created before doctype landed must stay "not measured"; the UI may
        # not recompute a modern check and present it as part of an old run.
        raw_document_checks = self.gate_report.get("document_checks")
        self.has_document_checks = "document_checks" in self.gate_report
        self.document_checks = raw_document_checks
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
    def __init__(self, workspace: Path,
                 review_scope: Path | str | ReviewScope | None = None):
        self.ws = Path(workspace)
        self.review_scope = (review_scope if isinstance(review_scope, ReviewScope)
                             else load_review_scope(review_scope)
                             if review_scope is not None else None)
        self._review_keys = (frozenset(self.review_scope.slots)
                             if self.review_scope else frozenset())

    def _scope_banner(self, lang: str) -> str:
        if self.review_scope is None:
            return ""
        text = _t(lang, "review_scope", n=len(self.review_scope.slots),
                  name=self.review_scope.source.name,
                  digest=self.review_scope.sha256[:12])
        return f'<div class="wb-scope" role="status">{_esc(text)}</div>'

    def review_order(self, ctx: RunCtx, lang: str = "zh") -> list[dict]:
        """Rows this server may review, in the scope file's exact order."""
        ordered = self._queue_order(ctx)
        if self.review_scope is None:
            return ordered
        by_key = {(r["doc_id"], r["field"]): r for r in ordered}
        missing = [f"{doc}|{field}" for doc, field in self.review_scope.slots
                   if (doc, field) not in by_key]
        if missing:
            shown = ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")
            raise _HttpError(409, _t(lang, "scope_missing", slots=shown),
                             run=ctx.name)
        return [by_key[key] for key in self.review_scope.slots]

    def require_review_slot(self, run_dir: Path, doc: str, field: str,
                            lang: str = "zh") -> None:
        """Refuse writes from stale tabs or hand-edited URLs outside the scope."""
        if self.review_scope is None:
            return
        ctx = RunCtx(run_dir)
        # Validate the whole scope against this run before testing membership;
        # a scope/run mismatch is a blocking configuration error, not a 404.
        self.review_order(ctx, lang)
        if (doc, field) not in self._review_keys:
            raise _HttpError(409, _t(lang, "scope_outside", doc=doc, field=field),
                             run=ctx.name)

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
             compact: bool = False, keep_params: dict | None = None) -> str:
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
                ("improve", f"/improve?run={nav_run}"),
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
        # 语言切换必须保留当前查询参数(run/doc/field/…),裸 ?lang= 会把
        # 裁决页切成空槽 404(2026-08-06 用户实测)
        if keep_params is not None:
            q = {k: v[0] for k, v in keep_params.items()
                 if k != "lang" and v}
            q["lang"] = other
            lang_href = "?" + urllib.parse.urlencode(q)
        else:
            lang_href = f"?lang={other}"
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
        # 搜索框放顶栏(2026-08-06 用户要求):全局可达,提交去队列页;
        # 当前页带 q 参数时保留原词
        search_nav = ""
        if nav_run:
            q = ""
            if keep_params is not None:
                q = (keep_params.get("q") or [""])[0]
            search_nav = (
                f'<form class="wb-search wb-search-top" method="get" action="/queue">'
                f'<input type="hidden" name="run" value="{_esc(nav_run)}">'
                f'<input type="hidden" name="lang" value="{_esc(lang)}">'
                f'<input type="search" name="q" value="{_esc(q)}" '
                f'placeholder="{_esc(_t(lang, "search_ph"))}">'
                f'<button type="submit" class="wb-search-btn">'
                f'{_esc(_t(lang, "search_btn"))}</button></form>')
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
{search_nav}
<span class="wb-lang"><a href="{lang_href}">{"中文" if other == "zh" else "EN"}</a></span>
</div></div>
<div class="wb-thesis">{_esc(_t(lang, 'thesis'))}</div>
{self._scope_banner(lang)}{notice_html}{ooc_html}
<main class="wb-main">{body}</main>
<script src="/assets.js"></script>
</body></html>"""

    # ---- 复核队列
    def queue_page(self, lang: str, run_dir: Path, params: dict) -> str:
        ctx = RunCtx(run_dir)
        rows = self.review_order(ctx, lang)
        decided = sum(1 for r in rows if (ctx.slot(r["doc_id"], r["field"]) or {}).get("tip"))
        filter_ = params.get("filter", ["all"])[0]
        query = params.get("q", [""])[0].strip().lower()
        filt_rows = []
        for r in rows:
            tip = (ctx.slot(r["doc_id"], r["field"]) or {}).get("tip")
            if filter_ == "pending" and tip:
                continue
            if filter_ == "done" and not tip:
                continue
            # 搜索框(2026-08-06 用户实测):doc_id 前缀/子串或字段名,
            # 大小写不敏感 —— 「找不到那张发票」不该靠翻页
            if query and query not in r["doc_id"].lower() \
                    and query not in r["field"].lower():
                continue
            filt_rows.append((r, tip))
        n_pending = sum(1 for r in rows if not (ctx.slot(r["doc_id"], r["field"]) or {}).get("tip"))
        q_param = f"&q={urllib.parse.quote(query)}" if query else ""
        chips = " ".join(
            f'<a class="wb-chip{" active" if filter_ == k else ""}" '
            f'href="/queue?run={ctx.name}&filter={k}&lang={lang}{q_param}">'
            f'{_esc(_t(lang, k))}'
            f'{"(" + str(n_pending) + ")" if k == "pending" else ""}</a>'
            for k in ("all", "pending", "done")
        )
        search = (f'<form class="wb-search" method="get" action="/queue">'
                  f'<input type="hidden" name="run" value="{_esc(ctx.name)}">'
                  f'<input type="hidden" name="filter" value="{_esc(filter_)}">'
                  f'<input type="hidden" name="lang" value="{_esc(lang)}">'
                  f'<input type="search" name="q" value="{_esc(query)}" '
                  f'placeholder="{_esc(_t(lang, "search_ph"))}">'
                  f'<button type="submit" class="wb-search-btn">'
                  f'{_esc(_t(lang, "search_btn"))}</button></form>')
        adjudicator = params.get("adjudicator", [""])[0]
        # 分节呈现:矩阵本来就知道哪些行「需要裁决」、哪些是多方印证。
        # 不分节,印证行和待裁决行混在一起,用户会以为「全绿的也要我复审 =
        # 假错误」(2026-08-03 用户实测原话)。印证行仍在(机器不设免审通道 —
        # 六轮实验发现最危险的错恰是看起来全对的错),但标明是抽检性质。
        groups = (
            ("sec_required", [(r, t) for r, t in filt_rows
                              if r.get("in_human_queue",
                                       r["requires_adjudication"])]),
            ("sec_corroborated", [(r, t) for r, t in filt_rows
                                 if not r.get("in_human_queue",
                                              r["requires_adjudication"])]),
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
                         ooc=ctx.manifest.get("out_of_calibration", False),
                         keep_params=params)

    def _notice(self, lang: str, params: dict) -> str:
        code = params.get("notice", [""])[0]
        if not code:
            return ""
        text = _t(lang, f"notice_{code}")
        if code == "recorded_stale":
            text += _esc(params.get("run", [""])[0])
        return text

    @staticmethod
    def _doctype_check(ctx: RunCtx, doc_id: str) -> tuple[str, dict]:
        """Return the frozen document check, never an on-demand recomputation."""
        if not ctx.has_document_checks:
            return "not_measured", {}
        if not isinstance(ctx.document_checks, dict):
            return "not_checked", {}
        check = ctx.document_checks.get(doc_id)
        if not isinstance(check, dict):
            return "not_checked", {}
        status = str(check.get("status") or "not_checked")
        if status not in {
                "pass", "fail", "no_claim", "unmapped", "ocr_unavailable"}:
            return "not_checked", {}
        return status, check

    @classmethod
    def _doctype_overlay(cls, ctx: RunCtx, doc_id: str) -> dict | None:
        """Validated, presentation-only geometry from a frozen passing check.

        `doctype.find_evidence` stores zero-based OCR pages and nested relative
        bboxes.  Workbench page images are one-based and use flat rectangles.
        Malformed artifact data fails closed: no class evidence is drawn or
        described as usable.
        """
        status, check = cls._doctype_check(ctx, doc_id)
        evidence = check.get("evidence") if status == "pass" else None
        if check.get("doc_class") not in _DOCTYPE_LABEL["en"]:
            return None
        if not isinstance(evidence, dict):
            return None
        try:
            raw_page = evidence["page"]
            if isinstance(raw_page, bool) or not isinstance(raw_page, int):
                return None
            page = raw_page + 1
            (x0, y0), (x1, y1) = evidence["bbox"]
            rect = tuple(float(v) for v in (x0, y0, x1, y1))
        except (KeyError, TypeError, ValueError):
            return None
        if page < 1 or not all(math.isfinite(v) for v in rect):
            return None
        x0, y0, x1, y1 = rect
        if not (0.0 <= x0 <= x1 <= 1.0 and 0.0 <= y0 <= y1 <= 1.0):
            return None
        phrase = evidence.get("phrase")
        if not isinstance(phrase, str) or not phrase.strip():
            return None
        return {"page": page, "bbox_rel": rect, "phrase": phrase.strip()}

    @classmethod
    def _doctype_html(cls, lang: str, ctx: RunCtx, row: dict) -> str:
        """Document-class context for HITL, with no decision-side effects."""
        status, check = cls._doctype_check(ctx, row["doc_id"])
        doc_class = check.get("doc_class")
        label = _DOCTYPE_LABEL[lang].get(str(doc_class), str(doc_class or "—"))
        css = "unavailable"
        proof = ""
        if status == "pass":
            evidence = cls._doctype_overlay(ctx, row["doc_id"])
            if evidence is None:
                status = "malformed"
                text = _t(lang, "doctype_malformed")
                css = "warn"
            else:
                text = _t(lang, "doctype_pass", label=label)
                proof_text = _t(
                    lang, "doctype_proof", phrase=evidence["phrase"],
                    page=evidence["page"])
                proof = (f'<span class="wb-doctype-proof">'
                         f'{_esc(proof_text)}</span>')
                css = "pass"
        elif status == "fail":
            text = _t(lang, "doctype_fail", label=label)
            css = "warn"
        elif status == "unmapped":
            text = _t(lang, "doctype_unmapped",
                      raw=str(check.get("raw_type") or "—"))
            css = "warn"
        else:
            key = {
                "no_claim": "doctype_no_claim",
                "ocr_unavailable": "doctype_ocr_unavailable",
                "not_measured": "doctype_not_measured",
                "not_checked": "doctype_not_checked",
            }[status]
            text = _t(lang, key)
        return (f'<div class="wb-doctype {css}" '
                f'data-doctype-status="{_esc(status)}">'
                f'<b>{_esc(_t(lang, "doctype_title"))}</b>'
                f'<span>{_esc(text)}</span>{proof}</div>')

    def _gates_html(self, lang: str, row: dict) -> str:
        """六道门禁逐项 chip,悬停一句话解释(gateinfo.tooltip 给文案)。"""
        return "".join(
            f'<span class="wb-gate {v}" title="{_esc(_gate_tooltip(g, v, lang))}">'
            f'{_GATE_SHORT.get(g, (g, g))[0 if lang == "en" else 1]}:'
            f'{_VERDICT.get(v, (v, v))[0 if lang == "en" else 1]}</span>'
            for g, v in sorted(row["gate_verdicts"].items())
        )

    @classmethod
    def _task_text(cls, lang: str, ctx: RunCtx, row: dict) -> str:
        """Neutral review question, specialised only by frozen type evidence.

        A passing status alone is not enough: `_doctype_overlay` revalidates the
        controlled class, literal phrase and geometry.  Any malformed or
        untrusted type falls back to the generic wording.  This helper is shared
        by the queue and single-slot views so explanatory context cannot drift
        into two different review contracts.
        """
        label = _FIELD_LABEL[lang].get(row["field"], row["field"])
        value = row.get("value")
        status, check = cls._doctype_check(ctx, row["doc_id"])
        evidence = cls._doctype_overlay(ctx, row["doc_id"]) \
            if status == "pass" else None
        doc_class = check.get("doc_class")
        if evidence is not None and doc_class in _DOCTYPE_LABEL[lang]:
            doctype_label = _DOCTYPE_LABEL[lang][doc_class]
            if value in (None, ""):
                return _t(lang, "task_doctype_no_value", label=label,
                          doctype=doctype_label)
            return _t(lang, "task_doctype_with_value", label=label,
                      value=value, doctype=doctype_label)
        if value in (None, ""):
            return _t(lang, "task_no_value", label=label)
        return _t(lang, "task_with_value", label=label, value=value)

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
        task = self._task_text(lang, ctx, row)
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

    @staticmethod
    def _vision_state(ctx: RunCtx, row: dict) -> tuple[str, str | None]:
        """建议状态的单一判定点:_vision_suggest 的展示与 decide 表单的
        suggestion_seen 隐藏字段必须看到同一个世界(Phase 0-2)。

        返回 (state, value):
        - ("none", None)      没有任何读者作答 → 不建议行,表单不带该字段
        - ("blind", None)     全弃权
        - ("split", None)     读者分歧
        - ("agree", value)    一致且可「采用」
        - ("agree_rejected", value) 一致但该值已被冻结拒掉(展示但不给采用)
        """
        answers = ctx.vision.get((row["doc_id"], row["field"]))
        if not answers:
            return "none", None
        live = [(m, v) for m, v in answers if v and v.upper() != "ABSTAIN"]
        if not live:
            return "blind", None
        from .fields import FIELD_KINDS, normalise

        kind = FIELD_KINDS.get(row["field"])
        normalised = {normalise(v, kind) for _, v in live}
        if len(normalised) != 1:
            return "split", None
        value = live[0][1]
        value_norm = normalise(value, kind) or str(value).strip()
        rejected = {(normalise(r["value"], kind) or str(r["value"]).strip())
                    for r in row["rejections"]}
        if value_norm in rejected:
            return "agree_rejected", value
        return "agree", value

    def _vision_suggest(self, lang: str, ctx: RunCtx, row: dict) -> str:
        """读图预填建议:一致 → 可「采用」(只预填表单,不写账本);
        分歧 → 摊开各读者的值,不给采用按钮;全弃权 → 如实说也看不清。

        一致性用与双模式门禁同一套归一化(fields.normalise)—— 两侧同规则,
        不搞第二套「差不多就行」的比较。
        """
        state, value = self._vision_state(ctx, row)
        if state == "none":
            return ""
        label = _esc(_t(lang, "vision_suggest"))
        if state == "blind":
            return (f'<div class="wb-vision-suggest muted"><span class="wb-vs-label">'
                    f'{label}</span> <span class="wb-vs-blind">'
                    f'{_esc(_t(lang, "vision_blind"))}</span></div>')
        answers = ctx.vision[(row["doc_id"], row["field"])]
        live = [(m, v) for m, v in answers if v and v.upper() != "ABSTAIN"]
        if state == "agree_rejected":
            # 同值已被冻结拒掉(绑不进本文档 —— 注入载荷也走这条路):
            # 建议层如实展示但绝不给「采用」按钮,否则 200px 外写着
            # 「冻结时被拒」、这里一个按钮就把它架空(82 评 P1-5)
            return (f'<div class="wb-vision-suggest muted"><span class="wb-vs-label">'
                    f'{label}</span> <b class="wb-vs-value">{_esc(value)}</b>'
                    f'<span class="wb-vs-rejected">'
                    f'{_esc(_t(lang, "vision_rejected"))}</span></div>')
        if state == "agree":
            return (f'<div class="wb-vision-suggest"><span class="wb-vs-label">{label}</span> '
                    f'<b class="wb-vs-value">{_esc(value)}</b>'
                    f'<span class="wb-vs-agree">{_esc(_t(lang, "vision_agree", a=len(live), n=len(answers)))}</span>'
                    f'<button type="button" class="wb-vs-adopt" data-value="{_esc(value)}" '
                    f'data-rationale="{_esc(_t(lang, "vision_rationale"))}">'
                    f'{_esc(_t(lang, "vision_adopt"))}</button></div>')
        split = " · ".join(f"{_esc(m)}={_esc(v)}" for m, v in live)
        return (f'<div class="wb-vision-suggest"><span class="wb-vs-label">{label}</span> '
                f'<span class="wb-vs-split">{_esc(_t(lang, "vision_split"))}:{split}</span></div>')

    def _evidence(self, lang: str, ctx: RunCtx, row: dict,
                  open_by_default: bool = True) -> str:
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
        # 队列页默认摊开:证据是复核的主信息(2026-08-03 用户原话);
        # 单槽裁决页默认收起(2026-08-06 用户实测:判定卡一屏放不下,
        # 要看再展开)—— 两处场景不同,各自默认
        open_attr = " open" if open_by_default else ""
        return (f'<details class="wb-evidence"{open_attr}><summary>'
                f'{_esc(_t(lang, "evidence"))}</summary>{inner}</details>')

    def _decide_form(self, lang: str, ctx: RunCtx, row: dict, tip: dict | None,
                     conflict: bool, n_orphans: int, adjudicator: str,
                     next_hint: str = "", form_values: dict | None = None,
                     form_error: str = "") -> str:
        doc, field = row["doc_id"], row["field"]
        # 提交被拒时的回填(2026-08-08):本站服务器端渲染,回填只能在服务端做。
        # 保留的是复核者**打出来的**东西 —— 理由、修正值、署名,以及他刚做的
        # 那个判断;丢一次就要重打一次,而重打的代价会把理由写短,
        # 恰恰写短的是 improve.mine 唯一原样带给人读的那一栏。
        filled = form_values or {}

        def _val(name: str) -> str:
            return filled.get(name, "")
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
        # 快路按钮**自带心码**(2026-08-06):按钮的文案本来就是一次语义
        # 选择,人已经做过了;系统丢掉再用下拉问一遍,是同一件事问两遍
        # (run-0002:93% 的裁决走预设理由,心码填写率 8/123)。
        # 纪律:只在按钮语义与心码**一对一**时带,含糊的一律留空 ——
        # 代填心码就是伪造监督信号(GOAL.md「不在没有依据下让数字变好看」)。
        quick = ""
        draft_value = next((r["value"] for r in row["rejections"]
                            if r.get("value")), None)
        if claim_id:
            # accept 有两种互斥含义,只有人知道是哪种:
            #   「该拦,我确认没问题」→ 无心码(词表里没有「路由判对了」,
            #     而它也不构成放松规则的证据);
            #   「白拦了」→ ROUTING_FALSE_POSITIVE,这是挖掘低收益 cohort
            #     唯一需要的信号。所以拆成两个按钮,不是多加一个表单字段。
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="accept" data-value="" data-reason="" '
                     f'data-rationale="{_esc(_t(lang, "accept_preset"))}">'
                     f'{_esc(_t(lang, "quick_accept"))}</button>'
                     f'<button type="button" class="wb-quick-ok wb-quick-fp" '
                     f'data-decision="accept" data-value="" '
                     f'data-reason="ROUTING_FALSE_POSITIVE" '
                     f'data-rationale="{_esc(_t(lang, "quick_fp_rationale"))}">'
                     f'{_esc(_t(lang, "quick_accept_fp"))}</button>')
        elif draft_value:
            # 值对、冻结绑定没接住 —— 这正是 BAD_SOURCE_BINDING 的定义
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="correct" data-value="{_esc(draft_value)}" '
                     f'data-reason="BAD_SOURCE_BINDING" '
                     f'data-rationale="{_esc(_t(lang, "quick_draft_rationale"))}">'
                     f'{_esc(_t(lang, "quick_draft", value=draft_value))}</button>')
        elif row.get("value") not in (None, ""):
            # 无声明也没走到冻结(如 OCR 受阻、草稿被排除),但 DWS 读到了值
            # —— 人看页面确认后采用该值,账本记 correct + 人证理由。
            # 心码留空:这一支既可能是绑定失败,也可能是 OCR 阻断导致门禁
            # unavailable,两者诊断不同,机器分不出来就不替人选。
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="correct" data-value="{_esc(row["value"])}" '
                     f'data-reason="" '
                     f'data-rationale="{_esc(_t(lang, "quick_draft_rationale"))}">'
                     f'{_esc(_t(lang, "quick_dws", value=row["value"]))}</button>')
        else:
            # 无声明且无值(预期缺失抽检等):一键确认缺失。
            # CONFIRMED_ABSENT 与 confirm_absent 在 adjudicate 的 combo 表里
            # 就是一对一,再问一遍等于让人把刚点的东西重打一遍
            quick = (f'<button type="button" class="wb-quick-ok" '
                     f'data-decision="confirm_absent" data-value="" '
                     f'data-reason="CONFIRMED_ABSENT" '
                     f'data-rationale="{_esc(_t(lang, "quick_absent_rationale"))}">'
                     f'{_esc(_t(lang, "quick_absent"))}</button>')
        radios = "".join(
            f'<label class="wb-radio {d}"><input type="radio" name="decision" '
            f'value="{d}" required'
            f'{" checked" if _val("decision") == d else ""}>'
            f'{_esc(_t(lang, d))}</label>'
            for d in decisions_for_row
        )
        # 问题 chip 与快路按钮同一条纪律:chip 是**封闭词表**里的一次语义
        # 选择(点了就原样追加进理由),所以语义一对一的可以带心码;
        # 含糊的留空。「与页面一致」不带(词表里没有「路由判对了」),
        # 「口径冲突」不带(applicability 争议在心码集里没有对应项,
        # 硬塞一个就是编)。
        chip_reasons = {
            0: "", 1: "WRONG_VALUE", 2: "BAD_SOURCE_BINDING",
            3: "AMBIGUOUS_DOCUMENT", 4: "", 5: "CONFIRMED_ABSENT", 6: "OTHER",
        }
        chips = "".join(
            f'<button type="button" class="wb-issue-chip" data-text="{_esc(c)}" '
            f'data-reason="{chip_reasons.get(i, "")}">{_esc(c)}</button>'
            for i, c in enumerate(_T[lang]["issue_chips"])
        )
        from .adjudicate import REASON_CODE_COMBOS
        from .feedback import REASON_CODES

        # 心码 option 自带「允许配哪些决策」—— 判据从 adjudicate 现读,
        # 前端按这个属性过滤(2026-08-08)。**表只有一份**:在界面上复制
        # 第二份就会与校验漂移,而漂移的表现正是人填完一屏被服务器拒掉。
        # 不受限的心码声明为空串:漏掉属性和「故意不限制」必须区分得开。
        reason_options = ('<option value=""></option>' + "".join(
            f'<option value="{c}" data-decisions='
            f'"{" ".join(sorted(REASON_CODE_COMBOS.get(c, ())))}"'
            f'{" selected" if _val("reason_code") == c else ""}>'
            f'{_esc(_reason_label(lang, c))}</option>' for c in REASON_CODES))
        confidence_options = "".join(
            f'<option value="{v}"{" selected" if _val("reviewer_confidence") == v else ""}>'
            f'{_esc(_t(lang, k)) if k else ""}</option>'
            for v, k in (("", ""), ("high", "conf_high"),
                         ("medium", "conf_medium"), ("low", "conf_low")))
        next_input = (f'<input type="hidden" name="next" value="{_esc(next_hint)}">'
                      if next_hint else "")
        # suggestion_seen(Phase 0-2):渲染时的建议状态随表单进账本 ——
        # 记的是「人提交那一刻屏幕上展示了什么建议」,与 _vision_suggest
        # 同一个判定点(_vision_state),不许两处各算各的。
        sug_state, sug_value = self._vision_state(ctx, row)
        sug_input = ""
        if sug_state != "none":
            seen = f"{sug_state}:{sug_value}" if sug_value is not None else sug_state
            sug_input = (f'<input type="hidden" name="suggestion_seen" '
                         f'value="{_esc(seen)}">')
        error_html = ""
        if form_error:
            error_html = (f'<div class="wb-form-error">'
                          f'<b>{_esc(_t(lang, "err_not_recorded"))}</b>'
                          f'<p>{_esc(form_error)}</p>'
                          f'<p class="wb-form-error-kept">'
                          f'{_esc(_t(lang, "err_kept"))}</p></div>')
        return f"""<div class="wb-decide">{''.join(notes)}{error_html}
<form class="decide" method="post" action="/decide"
 data-accept-preset="{_esc(_t(lang, 'accept_preset'))}"
 data-absent-preset="{_esc(_t(lang, 'absent_preset'))}"
{' data-rejected="1"' if form_error else ''}
<input type="hidden" name="run" value="{_esc(ctx.name)}">
<input type="hidden" name="doc" value="{_esc(doc)}">
<input type="hidden" name="field" value="{_esc(field)}">
<input type="hidden" name="claim_id" value="{_esc(claim_id)}">
<input type="hidden" name="supersedes" value="{_esc(supersedes)}">
<input type="hidden" name="lang" value="{_esc(lang)}">{next_input}
{sug_input}
{quick}
<div class="wb-decide-row">{radios}
<input class="wb-corr" type="text" name="corrected_value"
 value="{_esc(_val('corrected_value'))}"
 placeholder="{_esc(_t(lang, 'corrected_ph'))}"></div>
<textarea class="wb-rationale" name="rationale" rows="2" required
 placeholder="{_esc(_t(lang, 'rationale_ph'))}">{_esc(_val('rationale'))}</textarea>
<div class="wb-issue-chips">{chips}</div>
<div class="wb-decide-row"><label class="wb-label">{_esc(_t(lang, 'reason_code_label'))}
<select name="reason_code" class="wb-reason">{reason_options}</select></label>
<label class="wb-label">{_esc(_t(lang, 'confidence_label'))}
<select name="reviewer_confidence" class="wb-reason">
{confidence_options}</select></label></div>
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
        return ([r for r in rows if r.get("in_human_queue",
                                          r["requires_adjudication"])]
                + [r for r in rows if not r.get("in_human_queue",
                                                r["requires_adjudication"])])

    @staticmethod
    def _decided(ctx: RunCtx, row: dict) -> bool:
        return bool((ctx.slot(row["doc_id"], row["field"]) or {}).get("tip"))

    def adjudicate_page(self, lang: str, run_dir: Path, params: dict,
                        form_values: dict | None = None,
                        form_error: str = "") -> str:
        ctx = RunCtx(run_dir)
        doc = params.get("doc", [""])[0]
        field = params.get("field", [""])[0]
        ordered = self.review_order(ctx, lang)
        row = next((r for r in ordered
                    if r["doc_id"] == doc and r["field"] == field), None)
        if row is None:
            exists = any(r["doc_id"] == doc and r["field"] == field
                         for r in ctx.matrix["rows"])
            if exists and self.review_scope is not None:
                raise _HttpError(
                    409, _t(lang, "scope_outside", doc=doc, field=field),
                    run=ctx.name)
            raise _HttpError(404, f"槽位不存在:{doc}/{field}", run=ctx.name)
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
                                                 len(orphans), adjudicator,
                                                 form_values, form_error)}</div>
</div>
{self._adj_nav(lang, ctx, ordered, idx)}
<div class="wb-footer">{_esc(_t(lang, 'snapshot'))}={_esc(ctx.snapshot_id)}</div>"""
        return self.page(lang, "queue", body, run_name=ctx.name,
                         notice=self._notice(lang, params),
                         ooc=ctx.manifest.get("out_of_calibration", False),
                         compact=True, keep_params=params)

    def _page_column(self, lang: str, ctx: RunCtx, row: dict,
                     page: int | None = None) -> str:
        """左栏:整页渲染 + bbox overlay(不重渲染图片,相对坐标 → CSS 百分比)。

        三类框保持可区分:span_ids = 冻结绑定(机检确定性,绿实线);
        cited_span_ids = DWS 指向(advisory,紫虚线);通过的 doctype 字面证据
        = 绿点线。类型框只提供上下文,不改表单。多页文档给页码切换
        (服务器端 ?page=,零 JS 依赖):默认落在证据所在页,没有证据就第 1 页。
        """
        doc = row["doc_id"]
        containing = [ctx.spans_by_id[s] for s in row["span_ids"]
                      if s in ctx.spans_by_id]
        cited = [ctx.spans_by_id[s] for s in row.get("cited_span_ids", [])
                 if s in ctx.spans_by_id and s not in row["span_ids"]]
        doctype_evidence = self._doctype_overlay(ctx, doc)
        pages_dir = ctx.dir / "pages"
        available = sorted(
            int(p.stem.rsplit("-", 1)[1])
            for p in pages_dir.glob(f"{doc}-*.png")
            if p.stem.rsplit("-", 1)[1].isdigit()) if pages_dir.is_dir() else []
        span_pages = {s["page"] for s in containing + cited
                      if s.get("bbox_rel")}
        if doctype_evidence is not None:
            span_pages.add(doctype_evidence["page"])
        span_pages = sorted(span_pages)
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
            overlay_groups = (
                (containing, "wb-hl-bind"),
                (cited, "wb-hl-cited"),
                (([doctype_evidence] if doctype_evidence else []),
                 "wb-hl-doctype"),
            )
            for spans, cls in overlay_groups:
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
                        f'title="{_esc(s.get("span_id", "doctype_evidence"))} · '
                        f'{_esc(s.get("printed_label", s.get("phrase", "")))}"></div>')
            blocks.append(
                f'<figure class="wb-page-wrap"><figcaption class="wb-page-cap">'
                f'{_esc(doc[:8])} · p{current}{tabs}</figcaption>'
                f'<div class="wb-page-tools">'
                f'<button type="button" class="wb-hl-toggle" aria-pressed="false" '
                f'data-hide="{_esc(_t(lang, "hide_highlights"))}" '
                f'data-show="{_esc(_t(lang, "show_highlights"))}">'
                f'{_esc(_t(lang, "hide_highlights"))}</button>'
                f'<a class="wb-page-clean" href="{src}" target="_blank" '
                f'rel="noopener">{_esc(_t(lang, "open_clean_image"))}</a></div>'
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
        if doctype_evidence:
            legend_items.append(
                f'<span class="wb-legend-item"><span class="wb-legend-swatch doctype">'
                f'</span>{_esc(_t(lang, "legend_doctype"))}</span>')
        legend = (f'<div class="wb-legend">{"".join(legend_items)}</div>'
                  if legend_items else "")
        if not blocks:
            return (f'<h2 class="wb-adj-colhead">{_esc(_t(lang, "page_view"))}</h2>'
                    f'<div class="wb-banner">{_esc(_t(lang, "no_page"))}</div>')
        return (f'<h2 class="wb-adj-colhead">{_esc(_t(lang, "page_view"))}</h2>'
                f'{"".join(blocks)}{legend}')

    def _judgement_card(self, lang: str, ctx: RunCtx, row: dict,
                        tip: dict | None, conflict: bool, n_orphans: int,
                        adjudicator: str, form_values: dict | None = None,
                        form_error: str = "") -> str:
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
        task = self._task_text(lang, ctx, row)
        tiers = " · ".join(row.get("source_tiers") or []) or "—"
        applicability = row.get("applicability") or "—"
        policy = ""
        if not tip and not conflict and not row.get(
                "in_human_queue", row["requires_adjudication"]):
            policy = f'<div class="wb-policy">{_esc(_t(lang, "policy_note"))}</div>'
        why = self._why_html(lang, row)
        return f"""<div class="wb-adj-card">
<div class="wb-row-head">
<span class="wb-doc" title="{_esc(doc)}">{_esc(doc[:8])}</span>
<span class="wb-field">{_esc(label)}<span class="wb-raw">{_esc(field)}</span></span>
{self._status_chip(lang, tip, conflict)}
</div>
{self._doctype_html(lang, ctx, row)}
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
{self._evidence(lang, ctx, row, open_by_default=False)}
{self._decide_form(lang, ctx, row, tip, conflict, n_orphans, adjudicator,
                   next_hint="adjudicate", form_values=form_values,
                   form_error=form_error)}
</div>"""

    def _why_html(self, lang: str, row: dict) -> str:
        """「为什么在队列里」—— 入队原因放在判定卡顶部显眼处(2026-08-05
        用户实测:全绿 chips + 小字限制 = 以为系统让自己白审)。
        门禁绿只代表「在 DWS 数据上自洽」,不代表独立核查覆盖过。"""
        if not row.get("in_human_queue", row.get("requires_adjudication")):
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
        elif first.startswith("EXPECTED_ABSENT:"):
            key, cls, kw = "why_absent_qa", "", {}
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

    # ---- 改进循环:把复核者原话与(可选的)模型草稿摆在一起给人读
    def improve_page(self, lang: str, run_dir: Path, params: dict) -> str:
        """**只读页 + 三个写入口。** 面向不写代码的应付会计(AP)。

        版式是叙事顺序,不是数据结构顺序:
        「你复核时发现了什么」→「AI 据此建议改什么」→「等你拍板的改动」。
        工程标识(harness id、digest、cohort 键、路由词)一律收进每张卡
        底部的「技术细节」折叠区 —— 不删,因为它们是可复算的前提;
        不摆在最前,因为它们不是 AP 要读的东西(plainwords.py 首段)。

        写入口的分级摩擦不变:采纳/试算只写候选,晋升要署名。
        """
        import json as _json

        ctx = RunCtx(run_dir)
        ws = self.ws
        report_path = ws / "improve" / "mine_report.json"
        sug_path = ws / "improve" / "suggestions.json"
        report = (_json.loads(report_path.read_text(encoding="utf-8"))
                  if report_path.exists() else {})
        parts = [f'<p class="wb-imp-lead">{_esc(_t(lang, "imp_lead"))}</p>']

        # ---- 一、需要你注意:系统放过了,你把它推翻了(安全方向,排最前)
        overturns = report.get("overturned_auto_accepts") or []
        if overturns:
            rows = "".join(
                f'<li><b>{_esc(_pw.field(o["field"], lang))}</b> — '
                f'{_esc(_pw.decision(o["human_action"], lang))}'
                f'({_esc(_pw.reason(o.get("reason_code"), lang))})'
                f'<div class="wb-imp-quote">'
                f'{_esc(_pw.quote(o.get("rationale") or "", lang)[0])}'
                f'</div></li>'
                for o in overturns)
            parts.append(
                f'<section class="wb-imp-alert">'
                f'<h3>{_esc(_t(lang, "imp_alert_h"))}</h3>'
                f'<p>{_esc(_t(lang, "imp_alert_body"))}</p>'
                f'<ul class="wb-imp-plainlist">{rows}</ul></section>')

        # ---- 二、AI 读了你的话,提出这些建议
        drafts, dropped = [], []
        if sug_path.exists():
            sug = _json.loads(sug_path.read_text(encoding="utf-8"))
            drafts = sug.get("suggestions") or []
            dropped = sug.get("dropped") or []
        note_total = sum(len(c.get("notes") or [])
                         for c in report.get("cohorts") or [])
        parts.append(f'<h3 class="wb-imp-h">{_esc(_t(lang, "imp_sug_h"))}</h3>')
        if drafts:
            parts.append(
                f'<p class="wb-imp-sub">'
                f'{_esc(_t(lang, "imp_sug_sub").format(n=note_total, m=len(drafts)))}'
                f'</p>')
            for i, s in enumerate(drafts):
                parts.append(self._suggestion_html(lang, ctx, i, s))
        else:
            parts.append(f'<p class="wb-imp-empty">'
                         f'{_esc(_t(lang, "imp_model_none"))}</p>')
        # 被挡下的草稿**独立于**留下的草稿显示 —— 全被挡下时更该看见:
        # 那说明 AI 提了一堆没出处或越权的东西,是关于它可信度的重要信息。
        # (先前写在 if drafts 分支里,恰好把最该看见的情形吞掉了)
        if dropped:
            items = "".join(f'<li>{_esc(d)}</li>' for d in dropped)
            parts.append(
                f'<details class="wb-imp-tech"><summary>'
                f'{_esc(_t(lang, "imp_dropped"))}({len(dropped)})</summary>'
                f'<ul class="wb-imp-plainlist">{items}</ul></details>')

        # ---- 三、等你拍板
        parts.append(self._candidates_html(lang, ctx))

        # ---- 四、你自己写的话(原始材料,折叠;AI 的建议都是从这里来的)
        parts.append(self._notes_html(lang, report))

        body = (f'<div class="wb-improve"><h2>{_esc(_t(lang, "improve"))}</h2>'
                + "".join(parts) + "</div>")
        return self.page(lang, "improve", body, run_name=ctx.name,
                         notice=self._notice(lang, params),
                         ooc=ctx.manifest.get("out_of_calibration", False),
                         keep_params=params)

    def _notes_html(self, lang: str, report: dict) -> str:
        """复核者原话,按字段归堆。默认折叠 —— 它是**出处**,不是待办。"""
        blocks, total = [], 0
        for c in report.get("cohorts") or []:
            notes = c.get("notes") or []
            if not notes:
                continue
            total += len(notes)
            items = "".join(
                f'<li>{_esc(_pw.decision(n.get("decision"), lang))}'
                f'({_esc(_pw.reason(n.get("reason_code"), lang))}):'
                f'{_esc(_pw.quote(n["rationale"], lang)[0])}'
                + (f' <span class="wb-imp-carry">'
                   f'{_esc(_t(lang, "imp_carried"))}</span>'
                   if _pw.quote(n["rationale"], lang)[1] else "")
                + '</li>' for n in notes)
            blocks.append(
                f'<div class="wb-imp-notegroup"><b>'
                f'{_esc(_pw.field(c["field"], lang))}</b> · '
                f'{_esc(_pw.invoices(c["reviewed"], lang))}'
                f'<ul class="wb-imp-plainlist">{items}</ul></div>')
        if not blocks:
            return (f'<h3 class="wb-imp-h">{_esc(_t(lang, "imp_notes"))}</h3>'
                    f'<p class="wb-imp-empty">'
                    f'{_esc(_t(lang, "imp_no_notes"))}</p>')
        return (f'<details class="wb-imp-notes-box"><summary>'
                f'{_esc(_t(lang, "imp_notes"))}({total})</summary>'
                f'<p class="wb-imp-sub">{_esc(_t(lang, "imp_notes_sub"))}</p>'
                + "".join(blocks) + "</details>")

    def _quote_list(self, lang: str, notes: list) -> tuple[str, int]:
        """引用原话列表 —— 剥掉携带溯源前缀,携带的另标一个小签。

        复核者要看见的是他自己写的那句话,不是 `[replay run-0002 HD-0009]`。
        原文在工件里一个字没动(plainwords.quote 只服务展示层)。
        """
        # 同一句话说了 9 遍就合并成「…… ×9」—— 逐条列出只是噪音,
        # 而「9 次都这么写」恰恰是这条建议的分量所在,合并反而更清楚
        counts: dict[tuple[str, bool], int] = {}
        for n in notes:
            key = _pw.quote(n.get("rationale", ""), lang)
            counts[key] = counts.get(key, 0) + 1
        items = []
        for (text, carried), n in counts.items():
            mark = (f' <span class="wb-imp-carry">'
                    f'{_esc(_t(lang, "imp_carried"))}</span>' if carried else "")
            times = (f' <b>×{n}</b>' if n > 1 else "")
            items.append(f'<li>{_esc(text)}{times}{mark}</li>')
        return "".join(items), len(notes)

    def _suggestion_html(self, lang: str, ctx: RunCtx, idx: int,
                         s: dict) -> str:
        """一条 AI 建议 = 一句话标题 + 为什么 + 会怎样 + 你写的原话 + 采纳表单。

        finding/prediction 是**可编辑文本框**,预填 AI 的话:签字的人要用
        自己的说法写,晋升账本里留下的应该是人的判断。
        """
        kind = s.get("kind") or ("schema" if s.get("action") ==
                                 "schema_description" else "cohort")
        target = _pw.field(
            s.get("field") if kind == "schema"
            else (s.get("cohort") or {}).get("field"), lang)
        title = _pw.headline(s["action"], target, lang)
        quotes, n_quotes = self._quote_list(lang, s.get("cited_notes") or [])

        head = (
            f'<div class="wb-imp-sug-title">{_esc(title)}</div>'
            f'<div class="wb-imp-badges">'
            f'<span class="wb-imp-tag advisory">{_esc(_t(lang, "imp_ai"))}</span>'
            f'<span class="wb-imp-tag">{_esc(_t(lang, "imp_conf"))}:'
            f'{_esc(_pw.confidence(s.get("confidence"), lang))}</span></div>'
            f'<div class="wb-imp-why"><span class="wb-imp-k">'
            f'{_esc(_t(lang, "imp_why"))}</span>{_esc(s.get("finding", ""))}</div>'
            f'<div class="wb-imp-why"><span class="wb-imp-k">'
            f'{_esc(_t(lang, "imp_then"))}</span>{_esc(s.get("prediction", ""))}</div>'
            f'<details class="wb-imp-quotes"><summary>'
            f'{_esc(_t(lang, "imp_your_words"))}({n_quotes})</summary>'
            f'<ul class="wb-imp-plainlist">{quotes}</ul></details>')

        hidden = (f'<input type="hidden" name="run" value="{_esc(ctx.name)}">'
                  f'<input type="hidden" name="lang" value="{_esc(lang)}">')
        # 两段话上面已经原样显示过了 —— 编辑框收进折叠区,免得同一段话
        # 在一屏里出现两遍。折叠内容照样随表单提交,预填的仍是 AI 的话。
        words = (
            f'<details class="wb-imp-edit"><summary>'
            f'{_esc(_t(lang, "imp_rewrite"))}</summary>'
            f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_finding"))}'
            f'<textarea name="finding" rows="3" required>'
            f'{_esc(s.get("finding", ""))}</textarea></label>'
            f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_prediction"))}'
            f'<textarea name="prediction" rows="3" required>'
            f'{_esc(s.get("prediction", ""))}</textarea></label></details>')

        if kind == "schema":
            form = (
                f'<form method="post" action="/improve/adopt-schema" '
                f'class="wb-imp-form">{hidden}'
                f'<input type="hidden" name="field" '
                f'value="{_esc(s.get("field", ""))}">'
                f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_new_desc"))}'
                f'<textarea name="description" rows="3" required>'
                f'{_esc(s.get("description", ""))}</textarea></label>'
                f'{words}'
                f'<p class="wb-imp-note-sm">'
                f'{_esc(_t(lang, "imp_adopt_schema_hint"))}</p>'
                f'<button class="wb-btn" type="submit">'
                f'{_esc(_t(lang, "imp_adopt"))}</button></form>')
        elif s.get("action") in ("auto_accept", "absent_expected"):
            cohort = s.get("cohort") or {}
            cohort_fields = "".join(
                f'<input type="hidden" name="c_{_esc(k)}" value="{_esc(str(v))}">'
                for k, v in cohort.items())
            default_id = ("AC-" + str(cohort.get("field", f"C{idx}"))
                          .upper().replace("_", "-"))
            form = (
                f'<form method="post" action="/improve/adopt" '
                f'class="wb-imp-form">{hidden}{cohort_fields}'
                f'<input type="hidden" name="kind" value="{_esc(s["action"])}">'
                f'<input type="hidden" name="cohort_id" '
                f'value="{_esc(default_id)}">{words}'
                f'<p class="wb-imp-note-sm">{_esc(_t(lang, "imp_adopt_hint"))}</p>'
                f'<button class="wb-btn" type="submit">'
                f'{_esc(_t(lang, "imp_adopt"))}</button></form>')
        else:
            # revoke:改进层没有「撤销」这个候选类型 —— 不给假按钮(宪章四)
            form = (f'<p class="wb-imp-note-sm">'
                    f'{_esc(_t(lang, "imp_revoke_manual"))}</p>')

        tech = (f'<details class="wb-imp-tech"><summary>'
                f'{_esc(_t(lang, "imp_tech"))}</summary>'
                f'<code>action={_esc(s["action"])} · '
                f'{_esc(_json_compact(s.get("cohort") or {"field": s.get("field")}))}'
                f'</code></details>')
        return f'<article class="wb-imp-sug">{head}{form}{tech}</article>'

    def _candidates_html(self, lang: str, ctx: RunCtx) -> str:
        """等你拍板的改动。晋升按钮的可用性由 improve.gate_verdict 决定 ——
        与 promote 实际执行的是同一个纯函数,页面不许自己判一遍。"""
        import json as _json

        from . import improve as _improve
        from .harness import load_active

        parts = [f'<h3 class="wb-imp-h">{_esc(_t(lang, "imp_candidates"))}</h3>']
        ws = self.ws
        try:
            active = load_active(ws)
            active_id = active["harness_id"]
        except Exception as exc:  # noqa: BLE001 —— 链坏了要说,不静默
            return "".join(parts) + (f'<p class="wb-imp-empty">'
                                     f'{_esc(str(exc))}</p>')
        cand_dirs = sorted((ws / "harnesses").glob("HAR-*")) \
            if (ws / "harnesses").is_dir() else []
        shown = 0
        for cand in cand_dirs:
            manifest_path = cand / "manifest.json"
            if cand.name == active_id or not manifest_path.exists():
                continue
            shown += 1
            man = _json.loads(manifest_path.read_text(encoding="utf-8"))
            block = [
                f'<div class="wb-imp-sug-title">'
                f'{_esc(self._candidate_title(lang, cand, man, active))}</div>',
                f'<div class="wb-imp-why"><span class="wb-imp-k">'
                f'{_esc(_t(lang, "imp_why"))}</span>'
                f'{_esc("".join(man.get("created_from_findings") or []))}</div>',
                f'<div class="wb-imp-why"><span class="wb-imp-k">'
                f'{_esc(_t(lang, "imp_then"))}</span>'
                f'{_esc(man.get("prediction", ""))}</div>',
            ]
            lineage_ok = man.get("parent_harness_id") == active_id
            eval_path = ws / "improve" / f"eval_{cand.name}.json"
            if eval_path.exists():
                ev = _json.loads(eval_path.read_text(encoding="utf-8"))
                block.append(self._eval_html(lang, ev))
                verdict = _improve.gate_verdict(
                    ev, sealed2_qualified=_improve.sealed2_qualifies(
                        ws, cand.name))
                block.append(self._promote_html(lang, ctx, cand.name, verdict,
                                                lineage_ok=lineage_ok))
            else:
                block.append(f'<p class="wb-imp-empty">'
                             f'{_esc(_t(lang, "imp_eval_none"))}</p>')
                block.append(self._evaluate_form(
                    lang, ctx, cand.name, bool(man.get("schema_changed"))))
            block.append(
                f'<details class="wb-imp-tech"><summary>'
                f'{_esc(_t(lang, "imp_tech"))}</summary>'
                f'<code>{_esc(cand.name)} ← {_esc(man.get("parent_harness_id",""))}'
                f' · {_esc(man.get("provenance",""))}'
                f' · policy={_esc(str(man.get("policy_digest",""))[:12])}'
                f'</code></details>')
            parts.append(f'<article class="wb-imp-cand-box">'
                         + "".join(block) + "</article>")
        if not shown:
            parts.append(f'<p class="wb-imp-empty">'
                         f'{_esc(_t(lang, "imp_no_candidates"))}</p>')
        return "".join(parts)

    def _candidate_title(self, lang: str, cand: Path, man: dict,
                         active: dict) -> str:
        """候选做什么 —— 从政策 diff 反推一句话,而不是印 HAR-0005。"""
        import json as _json

        try:
            pol = _json.loads(
                (cand / "routing_policy.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cand.name
        parent = active["policy"]
        pairs = (("absent_expected_cohorts", "absent_expected"),
                 ("auto_accept_cohorts", "auto_accept"))
        for key, action in pairs:
            old = {c.get("id") for c in parent.get(key) or []}
            for c in pol.get(key) or []:
                if c.get("id") not in old:
                    return _pw.headline(action, _pw.field(c.get("field"), lang),
                                        lang)
        if man.get("schema_changed"):
            return _t(lang, "imp_cand_schema")
        # 与当前规则比不出差别 —— 通常是已经晋升过的旧候选(它加的那条
        # 早就在生效规则里了)。退而取它自己最后加的那条,总比印一个
        # HAR-0002 给 AP 看强
        for key, action in pairs:
            entries = pol.get(key) or []
            if entries:
                return _pw.headline(action,
                                    _pw.field(entries[-1].get("field"), lang),
                                    lang)
        return _t(lang, "imp_cand_unknown")

    def _eval_html(self, lang: str, ev: dict) -> str:
        """试算结果 —— 改善与代价并排,不许只显示改善的那一半。"""
        slots = ev.get("evaluated_slots") or 0

        def load_row(v):
            if v is None:
                return "—"
            return (f"{v:.0%}" if slots == 0
                    else f"{v:.0%}({round(v * slots)}/{slots})")

        rows = [(_t(lang, "imp_load"), load_row(ev.get("review_load_baseline")),
                 load_row(ev.get("review_load_candidate")))]
        if ev.get("safety_status") == "scored":
            rows.append((_t(lang, "imp_silent_absent"),
                         str(ev.get("silent_absent_baseline")),
                         str(ev.get("silent_absent_candidate"))))
            rows.append((_t(lang, "imp_silent_wrong"),
                         str(ev.get("silent_wrong_baseline")),
                         str(ev.get("silent_wrong_candidate"))))
        body = "".join(
            f'<tr><td>{_esc(k)}</td><td class="wb-imp-was">{_esc(b)}</td>'
            f'<td>→</td><td><b>{_esc(c)}</b></td></tr>' for k, b, c in rows)
        note = ("" if ev.get("safety_status") == "scored" else
                f'<p class="wb-imp-empty">{_esc(_t(lang, "imp_unscored"))}</p>')
        return (f'<div class="wb-imp-evalbox">'
                f'<div class="wb-imp-k">{_esc(_t(lang, "imp_eval_h"))}</div>'
                f'<table class="wb-imp-eval">{body}</table>{note}</div>')

    def _evaluate_form(self, lang: str, ctx: RunCtx, cand_id: str,
                       schema_changed: bool) -> str:
        hidden = (f'<input type="hidden" name="run" value="{_esc(ctx.name)}">'
                  f'<input type="hidden" name="lang" value="{_esc(lang)}">'
                  f'<input type="hidden" name="candidate" value="{_esc(cand_id)}">')
        if not schema_changed:
            return (f'<form method="post" action="/improve/evaluate" '
                    f'class="wb-imp-form">{hidden}'
                    f'<button class="wb-btn" type="submit">'
                    f'{_esc(_t(lang, "imp_eval_run"))}</button></form>')
        # schema 候选:必须重抽,会花钱 —— 份数与上限由人填,不给默认一键
        return (f'<form method="post" action="/improve/evaluate" '
                f'class="wb-imp-form">{hidden}'
                f'<input type="hidden" name="reextract" value="1">'
                f'<p class="wb-imp-note-sm">'
                f'{_esc(_t(lang, "imp_reextract_warn"))}</p>'
                f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_sample"))}'
                f'<input name="sample" type="number" min="1" max="200" '
                f'value="20" required></label>'
                f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_budget"))}'
                f'<input name="budget" type="number" min="1" value="600" '
                f'required></label>'
                f'<button class="wb-btn" type="submit">'
                f'{_esc(_t(lang, "imp_eval_reextract"))}</button></form>')

    def _promote_html(self, lang: str, ctx: RunCtx, cand_id: str,
                      verdict: dict, *, lineage_ok: bool = True) -> str:
        if not lineage_ok:
            # promote 自己也会拒(parent 对不上 active)。与其让人填完表单再吃
            # 一个 400,不如在这里说清楚 —— 页面不该给一个注定失败的按钮
            return (f'<div class="wb-imp-gate refuse">'
                    f'{_esc(_t(lang, "imp_lineage_bad"))}</div>')
        if not verdict["ok"]:
            refusals = "".join(f'<li>{_esc(r)}</li>'
                               for r in verdict["refusals"])
            return (f'<div class="wb-imp-gate refuse"><b>'
                    f'{_esc(_t(lang, "imp_gate_no"))}</b>'
                    f'<ul class="wb-imp-plainlist">{refusals}</ul></div>')
        # 宪章四:安全门**没跑**不等于通过。无真值时不许显示「安全检查通过」
        scored = verdict["safety_status"] == "scored"
        return (
            f'<div class="wb-imp-gate {"ok" if scored else "warn"}">'
            f'<b>{_esc(_t(lang, "imp_gate_ok" if scored else "imp_gate_unrun"))}'
            f'</b><div class="wb-imp-note-sm">'
            f'{_esc(verdict["claim_limits"])}</div></div>'
            f'<form method="post" action="/improve/promote" class="wb-imp-form">'
            f'<input type="hidden" name="run" value="{_esc(ctx.name)}">'
            f'<input type="hidden" name="lang" value="{_esc(lang)}">'
            f'<input type="hidden" name="candidate" value="{_esc(cand_id)}">'
            f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_approved_by"))}'
            f'<input name="approved_by" required></label>'
            f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_rationale"))}'
            f'<textarea name="rationale" rows="2" required></textarea></label>'
            f'<label class="wb-imp-lbl">{_esc(_t(lang, "imp_approved_at"))}'
            f'<input name="approved_at" class="wb-imp-now" '
            f'placeholder="2026-08-06T12:00:00Z" required></label>'
            f'<p class="wb-imp-note-sm">{_esc(_t(lang, "imp_promote_hint"))}</p>'
            f'<button class="wb-btn danger" type="submit">'
            f'{_esc(_t(lang, "imp_promote"))}</button></form>')

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
                         ooc=ctx.manifest.get("out_of_calibration", False),
                         keep_params=params)

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
    @staticmethod
    def _approve_html(lang: str, ctx: RunCtx, deliverable: dict) -> str:
        """外发批准区:自动化到 ready_for_approval 为止,最后一步归人。

        表单刻意**不预填署名**,也不给「全部批准」的按钮:一次签名对应
        一份单据。每份单据下先列出「没有人看过的字段」—— 签字的人有权知道
        自己在替多少条策略处置背书(2026-08-09 Northstar 权威链)。
        """
        rows = []
        for doc_id, doc in deliverable["docs"].items():
            status = doc.get("status", "")
            if not (status.startswith("ready_for_approval")
                    or status.startswith("approved_for_export")):
                continue
            unreviewed = doc.get("policy_disposed_fields") or []
            tier1 = doc.get("tier1_policy_disposed_fields") or []
            if unreviewed:
                names = "、".join(_pw.field(f, lang) for f in unreviewed)
                who = (f'<p class="wb-approve-unreviewed">'
                       f'{_esc(_t(lang, "approve_unreviewed", fields=names))}')
                if tier1:
                    key = "、".join(_pw.field(f, lang) for f in tier1)
                    who += (f' <b>'
                            f'{_esc(_t(lang, "approve_unreviewed_tier1", fields=key))}'
                            f'</b>')
                who += "</p>"
            else:
                who = (f'<p class="wb-approve-unreviewed">'
                       f'{_esc(_t(lang, "approve_none_unreviewed"))}</p>')
            caveat_note = (
                f'<p class="wb-label">{_esc(_t(lang, "approve_caveats_kept"))}</p>'
                if doc.get("release_caveats") else "")
            approval = doc.get("approval")
            if approval and not approval.get("stale"):
                state = (f'<p class="wb-approve-done">'
                         f'{_esc(_t(lang, "approve_done", who=approval["approved_by"], when=approval["approved_at"]))}'
                         f'</p>')
                form = ""
            else:
                state = ""
                if approval:
                    state = (f'<p class="wb-approve-stale">'
                             f'{_esc(_t(lang, "approve_stale", who=approval["approved_by"], when=approval["approved_at"]))}'
                             f'</p>')
                form = (
                    f'<form class="wb-form" method="post" action="/approve">'
                    f'<input type="hidden" name="run" value="{_esc(ctx.name)}">'
                    f'<input type="hidden" name="lang" value="{_esc(lang)}">'
                    f'<input type="hidden" name="doc" value="{_esc(doc_id)}">'
                    f'<label>{_esc(_t(lang, "approve_by"))}'
                    f'<input type="text" name="approved_by" required></label>'
                    f'<label>{_esc(_t(lang, "approve_why"))}'
                    f'<textarea name="rationale" rows="2" required></textarea>'
                    f'</label>'
                    f'<button type="submit" class="wb-btn">'
                    f'{_esc(_t(lang, "approve_btn"))}</button></form>')
            rows.append(
                f'<article class="wb-approve-card"><h3>{_esc(doc_id)}</h3>'
                f'<p class="wb-label">{_esc(_t(lang, f"status_{status}"))}</p>'
                f'{who}{caveat_note}{state}{form}</article>')
        if not rows:
            return ""
        return (f'<h2>{_esc(_t(lang, "approve_h"))}</h2>'
                f'<p class="wb-imp-lead">{_esc(_t(lang, "approve_lead"))}</p>'
                + "".join(rows))

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
{self._approve_html(lang, ctx, deliverable)}
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
                         notice=self._notice(lang, params),
                         keep_params=params)

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
        allowed = getattr(self.server, "allowed_hosts", _ALLOWED_HOSTS)
        public = getattr(self.server, "public", False)
        if host is not None:
            if public:
                # 公开绑定:若调用方显式给了白名单则强制;否则交给 Cloud Run 入口层
                if allowed and host not in allowed and not _host_suffix_ok(host, allowed):
                    raise _HttpError(403, f"Host {host!r} 不在公开白名单")
            elif host not in allowed:
                raise _HttpError(403, f"Host {host!r} 不在 loopback 白名单 —— "
                                      f"这通常是 DNS rebinding 的特征,已拒")
        if method == "POST" and getattr(self.server, "read_only", False):
            raise _HttpError(
                403, "read-only demo —— 本实例不接受任何写入。"
                     "裁决账本只在本地可写运行的工作台上追加。")
        if method == "POST":
            origin = self._host_of(self.headers.get("Origin"))
            if origin is None:
                return
            if public:
                # 同页 POST:Origin 主机必须等于 Host(Cloud Run URL 可变)
                if host is not None and origin != host:
                    raise _HttpError(403, f"跨源 POST(Origin {origin!r})已拒 —— "
                                          f"本服务只接受本页发起的写操作")
            elif origin not in allowed:
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

    #: 只读横幅。放在 `_html` 而不是某个页面里 —— 每一页都必须说,
    #: 否则评委可能以为自己刚才真的裁决了什么(宪章六)。
    _READ_ONLY_BANNER = (
        '<div style="background:#7a2e00;color:#fff;padding:8px 14px;'
        'font:600 13px/1.5 system-ui,sans-serif" role="status">'
        'read-only demo · 只读演示 —— 这个实例不接受任何写入。'
        '裁决、采纳、晋升都会被拒(403)。'
        '真实 HITL 只在本地可写运行的工作台上进行。</div>'
    )

    def _html(self, status: int, text: str, cookies=None) -> None:
        if getattr(self.server, "read_only", False):
            marker = "<body>" if "<body>" in text else "<body "
            idx = text.find(marker)
            if idx >= 0:
                cut = text.index(">", idx) + 1
                text = text[:cut] + self._READ_ONLY_BANNER + text[cut:]
        self._send(status, text.encode("utf-8"), "text/html; charset=utf-8", cookies)

    #: 见 `_dispatch`:`/healthz` 在 Cloud Run 外网侧不可用
    _PROBE_PATHS = ("/healthz", "/_health")

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
        # 探针先于 Host 闸 —— Cloud Run / Docker HEALTHCHECK 不该被白名单绊倒。
        # 两条路径:`/healthz` 给容器内 HEALTHCHECK(打 127.0.0.1,不过前端),
        # `/_health` 给外部 —— Google 前端会在到达 Cloud Run 之前吞掉 `/healthz`
        # 并回自己的 404 页(2026-08-07 实测,见 tests 里那条注释)。
        if method == "GET" and path in self._PROBE_PATHS:
            body = json.dumps({"ok": True, "service": "invoiceloop-workbench"}).encode()
            return self._send(200, body, "application/json; charset=utf-8")
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
            if method == "GET" and path == "/improve":
                run = self._require_run(params)
                return self._html(200, self.bench.improve_page(lang, run, params),
                                  set_cookies)
            if method == "GET" and path == "/adjudicate":
                params.setdefault("adjudicator", [self._adjudicator()])
                run = self._require_run(params)
                return self._html(200, self.bench.adjudicate_page(lang, run, params),
                                  set_cookies)
            if method == "GET" and path == "/upload":
                import os
                return self._html(200, self.bench.upload_page(
                    lang, params, has_key=bool(_dws_key())), set_cookies)
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
            if method == "POST" and path == "/approve":
                return self._approve(lang)
            if method == "POST" and path == "/verify":
                return self._verify(lang)
            if method == "POST" and path == "/improve/adopt":
                return self._imp_adopt(lang)
            if method == "POST" and path == "/improve/adopt-schema":
                return self._imp_adopt_schema(lang)
            if method == "POST" and path == "/improve/evaluate":
                return self._imp_evaluate(lang)
            if method == "POST" and path == "/improve/promote":
                return self._imp_promote(lang)
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
        doc = form.get("doc", [""])[0]
        field = form.get("field", [""])[0]
        # review scope 是写权限边界,不是页面过滤。旧标签页或手改 POST
        # 同样不能越过它(2026-08-08 H2 实测留下 1 条样本外裁决)。
        self.bench.require_review_slot(run, doc, field, lang)
        decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rationale = form.get("rationale", [""])[0].strip()
        adjudicator = form.get("adjudicator", [""])[0].strip()
        try:
            if not rationale:
                raise ValueError("rationale 不能为空 —— 把发现的问题或理由写出来")
            if not adjudicator:
                raise ValueError("adjudicator 不能为空 —— 裁决要署名")
            result = adjudicate_and_render(
                run,
                claim_id=form.get("claim_id", [""])[0] or None,
                doc_id=doc,
                field=field,
                decision=form.get("decision", [""])[0],
                corrected_value=form.get("corrected_value", [""])[0] or None,
                rationale=rationale,
                adjudicator=adjudicator,
                decided_at=decided_at,
                supersedes_decision_id=form.get("supersedes", [""])[0] or None,
                reason_code=form.get("reason_code", [""])[0] or None,
                reviewer_confidence=form.get("reviewer_confidence", [""])[0] or None,
                suggestion_seen=form.get("suggestion_seen", [""])[0] or None,
            )
        except ValueError as exc:
            # 校验拒绝 = 一行都没写(append_adjudication 的契约)。以前这里
            # 冒到 _dispatch 变成整页「阻断」,复核者刚打的理由/修正值/署名
            # 全丢 —— 200 槽一轮里这是实打实的成本(2026-08-08 用户实测)。
            return self._decide_rejected(lang, run, form, exc)
        notice = "recorded" if result["panel_refreshed"] else "recorded_stale"
        cookies = [("wb_adjudicator", adjudicator)]
        if form.get("next", [""])[0] == "adjudicate":
            # 裁决页提交:推进到分诊序里的下一个未裁决槽位;没有了就回队列。
            # 裁决本身一字未差 —— 只是落点不同(Gradescope 式流水作业)
            loc = self._next_adjudicate_url(
                run, doc, field, lang, notice)
        else:
            anchor = f"#row-{form.get('doc', [''])[0]}-{form.get('field', [''])[0]}"
            loc = f"/queue?run={run_name}&lang={lang}&notice={notice}{anchor}"
        self._redirect(loc, cookies)

    def _decide_rejected(self, lang: str, run: Path, form: dict,
                         exc: ValueError) -> None:
        """裁决被拒 → 回到**该槽的裁决页**,已填内容原样回填,错误摆在表单旁边。

        400 直接渲染,不 303:重定向会丢掉 POST 体,而把理由塞进 query
        string 等于让它进浏览器历史与日志。队列页提交也落到这里 —— 两条
        路径的裁决语义本来就一样,修不了的地方在同一屏上修完最省事。
        """
        message = _decide_error(lang, form.get("decision", [""])[0],
                                form.get("reason_code", [""])[0], exc)
        values = {k: form.get(k, [""])[0] for k in
                  ("decision", "corrected_value", "rationale",
                   "reason_code", "reviewer_confidence", "adjudicator")}
        params = {"run": [run.name], "doc": form.get("doc", [""]),
                  "field": form.get("field", [""]), "lang": [lang],
                  "adjudicator": [values["adjudicator"]]}
        try:
            page = self.bench.adjudicate_page(lang, run, params,
                                              form_values=values,
                                              form_error=message)
        except _HttpError:
            # 槽位本身就不存在(doc/field 被改过)—— 回填无处可放,
            # 照旧给消息页,不假装还有一个表单可以改
            back = f"/queue?run={run.name}&lang={lang}"
            return self._html(400, self.bench.message_page(
                lang, _t(lang, "error_title"), [_esc(message)], back))
        self._html(400, page)

    def _next_adjudicate_url(self, run: Path, doc: str, field: str,
                             lang: str, notice: str) -> str:
        ctx = RunCtx(run)
        ordered = self.bench.review_order(ctx, lang)
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
        if do_extract and not _dws_key():
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

    def _approve(self, lang: str) -> None:
        """一次署名批准一份单据外发。时间由服务器在点击瞬间盖 UTC 秒戳 ——
        与裁决同一口径:人给决定,机器给时间戳。

        先记账本(权威)再重写投影(deliverable.json),顺序不可逆:
        投影写失败不撤销已经落盘的批准。
        """
        from datetime import datetime, timezone

        from .approve import append_approval
        from .deliver import write_deliverable

        form = self._form()
        run = self._require_run(form)
        lang = form.get("lang", [lang])[0] or lang
        self._last_run = run.name
        doc_id = (form.get("doc", [""])[0] or "").strip()
        if not doc_id:
            raise _HttpError(400, "没说批准哪一份单据")
        append_approval(
            run, doc_id=doc_id,
            approved_by=(form.get("approved_by", [""])[0] or "").strip(),
            rationale=(form.get("rationale", [""])[0] or "").strip(),
            approved_at=datetime.now(timezone.utc).replace(
                microsecond=0).isoformat().replace("+00:00", "Z"))
        try:
            write_deliverable(run)
        except Exception:  # noqa: BLE001 —— 投影重写失败不撤销已落盘的批准
            pass
        self._redirect(f"/deliver?run={run.name}&lang={lang}&notice=approved")

    # ---- 改进循环的四个写操作
    #
    # 分级摩擦是刻意的:adopt / evaluate 写的是**候选**,对 active harness
    # 零影响,所以给按钮;promote 会改变之后每一张发票的路由,所以要求手打
    # 署名 + 理由 + 时间,并且只有 improve.gate_verdict 判定通过才渲染表单。
    # 三个写操作全部落在既有 CLI 的同一批函数上 —— 网页不是第二条路径。

    def _imp_form_run(self, form: dict):
        return self._require_run(form), (form.get("lang", ["zh"])[0] or "zh")

    def _imp_back(self, run_name: str, lang: str, notice: str) -> None:
        self._redirect(f"/improve?run={run_name}&lang={lang}&notice={notice}")

    def _imp_adopt(self, lang: str) -> None:
        """模型草稿 → cohort 候选。propose + evaluate(反事实,零 API)。"""
        from . import improve

        form = self._form()
        run, lang = self._imp_form_run(form)
        cohort = {k[2:]: v[0] for k, v in form.items()
                  if k.startswith("c_") and v and v[0]}
        if not cohort:
            raise _HttpError(400, "草稿没有 cohort 特征 —— 采纳不了")
        kind = form.get("kind", ["auto_accept"])[0]
        if kind == "absent_expected":
            # 类别缺席规则的 ID 由 Python 从 doc_class × field 生成(宪章一:
            # 模型不写 ID),所以这里**不能**把界面上的 cohort_id 递进去 ——
            # 递了就是 propose 的白名单外键,必被拒。
            if not cohort.get("doc_class"):
                raise _HttpError(
                    400, "缺席规则要说清是哪一类单据 —— 不带类别就是"
                         "「所有单据都没有这个字段」,那条规则会静默吞掉"
                         "真有值的槽")
        else:
            cohort_id = (form.get("cohort_id", [""])[0] or "").strip()
            if not cohort_id:
                raise _HttpError(400, "给候选起个名字")
            cohort = {"id": cohort_id, **cohort}
        cand_dir = improve.propose(
            self.bench.ws, cohort=cohort,
            finding=(form.get("finding", [""])[0] or "").strip(),
            prediction=(form.get("prediction", [""])[0] or "").strip(),
            kind=kind)
        improve.evaluate(self.bench.ws, cand_dir.name)
        self._imp_back(run.name, lang, "proposed")

    def _imp_adopt_schema(self, lang: str) -> None:
        """模型草稿 → schema 候选。**不自动评测** —— 评它要花钱,人来点。"""
        from . import improve

        form = self._form()
        run, lang = self._imp_form_run(form)
        improve.propose_schema(
            self.bench.ws,
            field=(form.get("field", [""])[0] or "").strip(),
            description=(form.get("description", [""])[0] or "").strip(),
            finding=(form.get("finding", [""])[0] or "").strip(),
            prediction=(form.get("prediction", [""])[0] or "").strip())
        self._imp_back(run.name, lang, "proposed")

    def _imp_evaluate(self, lang: str) -> None:
        from . import improve

        form = self._form()
        run, lang = self._imp_form_run(form)
        candidate = (form.get("candidate", [""])[0] or "").strip()
        if not candidate:
            raise _HttpError(400, "没给候选 id")
        reextract = bool(form.get("reextract", [""])[0])
        improve.evaluate(
            self.bench.ws, candidate, reextract=reextract,
            sample=int(form.get("sample", ["0"])[0] or 0),
            budget=float(form.get("budget", ["600"])[0] or 600))
        self._imp_back(run.name, lang, "evaluated")

    def _imp_promote(self, lang: str) -> None:
        """唯一改变 active harness 的网页入口。门在 improve.promote 里,
        这里只负责把人打的字原样递进去 —— 不代填署名,不代填时间。"""
        from . import improve

        form = self._form()
        run, lang = self._imp_form_run(form)
        improve.promote(
            self.bench.ws,
            (form.get("candidate", [""])[0] or "").strip(),
            approved_by=(form.get("approved_by", [""])[0] or ""),
            rationale=(form.get("rationale", [""])[0] or ""),
            approved_at=(form.get("approved_at", [""])[0] or ""))
        self._imp_back(run.name, lang, "promoted")

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


def _host_suffix_ok(host: str, allowed: set[str]) -> bool:
    """白名单条目以 `.` 开头时按后缀匹配(如 `.run.app`)。"""
    for entry in allowed:
        if entry.startswith(".") and host.endswith(entry):
            return True
    return False


def resolve_port(port: int | None) -> int:
    """CLI `--port` > 环境 `PORT`(Cloud Run 注入) > 8765。"""
    import os

    if port is not None:
        return int(port)
    env = os.environ.get("PORT")
    if env:
        return int(env)
    return 8765


def make_server(
    workspace: Path,
    port: int,
    *,
    host: str = HOST,
    allowed_hosts: set[str] | None = None,
    read_only: bool = False,
    review_scope: Path | str | None = None,
) -> ThreadingHTTPServer:
    """起工作台 HTTP 服务。

    默认绑 127.0.0.1(loopback)。Cloud Run / Docker 需显式 `host="0.0.0.0"`;
    公开绑定时 Host 闸放宽(可再用 `allowed_hosts` / `.run.app` 后缀收紧)。
    本地评委路径不要公开绑定 —— 要给人看离线结果走 audit bundle。

    `read_only=True` 拒绝**全部** POST。公开演示必须开它:裁决账本是
    「某个人看过并判了」的证词,公网可写等于任何人都能伪造一条人类裁决。
    """
    import os

    workspace = Path(workspace)
    # 主变量与别名同设:评委照 README export 过 INVOICELOOP_CORPUS 的话,
    # 只设别名会被环境里的主变量遮蔽,工作台直接读错根(81 评 P1-1 的产品侧孪生)
    os.environ["INVOICELOOP_CORPUS"] = str(workspace)
    os.environ["INVOICELOOP_DWS_DERISK"] = str(workspace)
    public = host in PUBLIC_BIND_HOSTS
    if public:
        # 空集 = 不按 Host 白名单拦截(入口层是 Cloud Run);显式列表则强制。
        # 始终并上 loopback —— 本地 docker -p 8080:8080 与 HEALTHCHECK 的 Host
        # 是 127.0.0.1,不能被 `.run.app` 白名单误杀。
        hosts = set(allowed_hosts) if allowed_hosts is not None else set()
        if hosts:
            hosts |= set(_ALLOWED_HOSTS)
    else:
        hosts = set(allowed_hosts) if allowed_hosts is not None else set(_ALLOWED_HOSTS)
        if not hosts:
            hosts = set(_ALLOWED_HOSTS)
    # 先读并校验 scope,再占端口;坏 JSON 不该留下一个无人关闭的 socket。
    bench = Workbench(workspace, review_scope=review_scope)
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.bench = bench
    server.public = public
    server.allowed_hosts = hosts
    server.bind_host = host
    server.read_only = read_only
    return server


def cmd_workbench(
    workspace: Path,
    port: int | None = None,
    *,
    host: str = HOST,
    allowed_hosts: list[str] | None = None,
    read_only: bool = False,
    review_scope: Path | None = None,
) -> int:
    bind_port = resolve_port(port)
    allow = set(allowed_hosts) if allowed_hosts else None
    # 环境变量补充白名单(Cloud Run 服务 URL / 自定义域名)
    import os

    extra = os.environ.get("INVOICELOOP_ALLOWED_HOSTS", "").strip()
    if extra:
        allow = (allow or set()) | {h.strip().lower() for h in extra.split(",") if h.strip()}
    read_only = read_only or os.environ.get(
        "INVOICELOOP_READ_ONLY", "") in ("1", "true", "TRUE")
    server = make_server(workspace, bind_port, host=host, allowed_hosts=allow,
                         read_only=read_only, review_scope=review_scope)
    addr_host = "127.0.0.1" if host in PUBLIC_BIND_HOSTS else host
    url = f"http://{addr_host}:{server.server_address[1]}"
    mode = "公开绑定(Cloud Run/容器)" if server.public else "仅本机 loopback"
    if read_only:
        mode += ",只读(POST 一律 403)"
    if server.bench.review_scope is not None:
        scope = server.bench.review_scope
        mode += f",限定复核 {len(scope.slots)} 槽({scope.source.name})"
    print(f"InvoiceLoop 工作台:{url}({mode},Ctrl-C 停止)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
