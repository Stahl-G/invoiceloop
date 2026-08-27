"""Arm U's deterministic release policy — the step no model may skip.

Plan: the 2026-08-27 unattended-arm proposal (``docs/ARM_UNATTENDED.md``).
The one sentence it exists to enforce: **unattended must not mean "one model
judges and approves".** clerk proposes, critic re-reads the page — both are
opinions. Whether a document may be approved is decided here, in pure Python,
reading only frozen run artifacts. No model, no truth, no wall clock.

Every rule below is pinned to a failure that actually happened:

- R3 fake absence — the grokbot clerk confirmed ``seller_vat_id`` absent while
  the gold annotation *is* the Taxpayer ID printed on the page;
- R5 fake presence — the clerk invented ``total_net=110810`` from an hours
  total no invoice carries as net;
- R6 EIN-as-invoice-number — ``58-0391492`` is a TIN, and paying by it is
  paying the wrong identifier;
- R7 terms-as-date — ``Due on Receipt`` is a payment term, not a calendar due
  date;
- R4/R9 two-role consensus + a third yes — "queue is empty" was exactly the
  check that let a wrong clerk line get signed out on 2026-08-27.

Changing a rule means a new POLICY_ID and a new digest; approvals carry the
digest, so old approvals never silently inherit a policy they were not given
under. Tests live in ``tests/test_unattended_policy.py`` — one fixture per
failure above, zero API.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

#: 稳定策略身份。规则文本进摘要:改规则不改 id = 自欺。
#: v2(2026-08-27 第二轮 live 验收后):R5 加金额/日期格式等价;新增 R10。
#: v3(2026-08-28 PR 审查后):R4 把「任一角色草稿缺失」记为无共识
#:(此前缺失静默通过,单角色读过的 TIER1 槽可能放行);R3 对 critic
#: 改判的 confirm_absent 只认页面探针 —— 一个角色不能为自己改判出的
#: 缺席作证(非 TIER1 字段此前存在自我背书路径)。
POLICY_ID = "unattended-policy-v3"

_RULES = (
    "R1 every posting-blocking slot of the document carries an adjudication "
    "tip (review-queue slots plus census pending/pending_tier1/abstained)",
    "R2 the recomputed deliverable status is approvable "
    "(ready_for_approval[_with_caveats]); a blocked or pending document never reaches the approver",
    "R3 every confirm_absent tip carries absence evidence: the page label is "
    "corroborated absent (matrix absence probe) or the critic's "
    "absence_evidence is label_absent/value_absent; cannot_tell and not_absent "
    "count as no evidence. A tip the critic itself overrode into "
    "confirm_absent accepts ONLY page-probe corroboration — a role may not "
    "vouch for its own override",
    "R4 clerk and critic decisions agree on every TIER1 slot (same decision, "
    "same corrected value after strip)",
    "R5 every corrected_value is printed on the page under the frozen binding "
    "standard WITH format equivalence for AMOUNT and DATE kinds: "
    "12/19/99 == 1999-12-19 and $1,744.20 == 1744.20 are the same printed value",
    "R6 an invoice_number corrected_value must not match an EIN/TIN pattern "
    "(dd-ddddddd)",
    "R7 a due_date corrected_value must not be payment-terms prose "
    "(due on receipt and friends)",
    "R8 a correct on field F requires F's label to be printed on the page "
    "(the matrix absence probe for F must not be corroborated-absent)",
    "R9 approval additionally requires the approver role's release==true — "
    "policy pass alone never writes an approval",
    "R10 a confirm_absent on seller_vat_id is a false absence when the page's "
    "independent OCR contains an EIN/TIN-shaped token (dd-ddddddd): a US "
    "Taxpayer ID printed on the page IS the seller tax identifier",
)


def policy_digest() -> str:
    body = POLICY_ID + "\n" + "\n".join(_RULES)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


#: EIN / Taxpayer ID:两位-七位。58-0391492 就长这样。
_EIN_RE = re.compile(r"\d{2}-\d{7}")

#: 付款条款不是日历日。小写匹配,容忍前后缀。
_TERMS_DUE_RE = re.compile(
    r"\b(due\s+on\s+receipt|due\s+upon\s+receipt|payable\s+on\s+receipt)\b")

#: critic 的缺席证据里,这两类算「有证据」;cannot_tell 是显式没把握,
#: not_absent 是反向结论 —— 都不许为 confirm_absent 背书。
_ABSENCE_EVIDENCE_OK = frozenset({"label_absent", "value_absent"})

_VIOLATION_CODES = {
    "R1": "slot_without_tip",
    "R2": "document_not_approvable",
    "R3": "absence_without_evidence",
    "R4": "tier1_clerk_critic_disagreement",
    "R5": "corrected_value_not_on_page",
    "R6": "ein_as_invoice_number",
    "R7": "terms_prose_as_due_date",
    "R8": "correct_on_label_absent_field",
    "R9": "approver_release_missing",
    "R10": "false_absence_ein_on_page",
}


def ein_shaped(value: str | None) -> bool:
    return bool(value) and bool(_EIN_RE.fullmatch(str(value).strip()))


def terms_prose(value: str | None) -> bool:
    return bool(value) and bool(_TERMS_DUE_RE.search(str(value).strip().lower()))


def _page_facts(run_dir: Path, doc_id: str) -> dict:
    """页面事实(只读独立 OCR):金额集、日期键集、页上有无 EIN 形 token。

    金额/日期集给 R5 的格式等价用:值与页面印的是同一个数/同一天,
    只是写法不同(12/19/99 vs 1999-12-19、1744.20 vs $1,744.20)。
    日期键 = date_ymd 归一后 (年%100, 月, 日) —— 两位年与四位年是同一年。
    """
    from .fields import amount, date_parts, date_ymd
    from .ocr import iter_words

    amounts: set[float] = set()
    date_keys: set[tuple] = set()
    has_ein = False
    try:
        for _, word, _geo in iter_words(doc_id):
            a = amount(word)
            if a is not None:
                amounts.add(a)
            parts = date_parts(word)
            if parts is not None:
                ymd = date_ymd(parts)
                # date_ymd 对 (M,D) 碎片返回二元组 —— 那不是"页上印着的
                # 一天",跳过;只收完整 (年,月,日)
                if len(ymd) == 3:
                    date_keys.add((ymd[0] % 100, ymd[1], ymd[2]))
            if _EIN_RE.search(word):
                has_ein = True
    except Exception:  # noqa: BLE001 — OCR 缺失由上层 R5 的 error 分支记录
        pass
    return {"amounts": amounts, "date_keys": date_keys, "has_ein": has_ein}


def value_printed_on_page(value: str, field: str, facts: dict) -> bool | None:
    """R5 的等价判定:冻结 token 绑定之外的 AMOUNT/DATE 写法等价。

    返回 None = 判不了(kind 不适用);True/False = 判定。冻结标准
    (binds_to_document)由调用方先试 —— 这里只是它漏掉的格式对。
    """
    from .fields import FIELD_KINDS, Kind, amount, date_parts, date_ymd

    kind = FIELD_KINDS.get(field)
    if kind == Kind.AMOUNT:
        a = amount(value)
        return a is not None and a in facts["amounts"]
    if kind == Kind.DATE:
        parts = date_parts(value)
        if parts is None:
            return None
        ymd = date_ymd(parts)
        if len(ymd) != 3:
            return False
        return (ymd[0] % 100, ymd[1], ymd[2]) in facts["date_keys"]
    return None


def _slot_tips(run_dir: Path) -> dict[tuple[str, str], dict]:
    """槽位 → 当前 tip 裁决(review 投影;冲突槽位 tip=None,由 R1 挡下)。"""
    from .review import project_run

    tips: dict[tuple[str, str], dict] = {}
    for _target, slot in project_run(run_dir).items():
        entry = slot["tip"]
        if entry is not None:
            tips[(entry["doc_id"], entry["field"])] = entry
    return tips


def audit_document(
    run_dir: Path,
    doc_id: str,
    *,
    queue_keys: list[str],
    clerk_by_slot: Mapping[tuple[str, str], Mapping],
    critic_by_slot: Mapping[tuple[str, str], Mapping],
    deliverable_status: str,
    approvable_statuses: tuple[str, ...],
    approver_release: bool | None = None,
) -> dict:
    """单据能不能批。纯函数:只读盘上工件 + 两个模型角色的**意见**。

    queue_keys:该单据进入复核队列的槽键(doc|field)。
    clerk_by_slot / critic_by_slot:两角色的草稿(无 ID);clerk/critic 的
    decision 字段语义与 adjudicate.DECISIONS 相同。
    approver_release:None = approver 还没跑(预检);False = 拒绝放行。
    """
    from .fields import TIER1
    from .freeze import binds_to_document
    from .ocr import OcrUnavailable

    run_dir = Path(run_dir)
    gate = json.loads(
        (run_dir / "gate_report.json").read_text(encoding="utf-8"))
    probes = (gate.get("absence_probes") or {}).get(doc_id) or {}

    tips = _slot_tips(run_dir)
    page = _page_facts(run_dir, doc_id)
    violations: list[dict] = []

    def violation(rule: str, detail: dict) -> None:
        violations.append({"rule": rule,
                           "code": _VIOLATION_CODES[rule], **detail})

    # ---- R1:队列槽全部有 tip
    doc_queue = [k for k in queue_keys if k.split("|", 1)[0] == doc_id]
    for key in doc_queue:
        slot = tuple(key.split("|", 1))
        if slot not in tips:
            violation("R1", {"slot": key})

    # ---- R2:交付投影可批
    if deliverable_status not in approvable_statuses:
        violation("R2", {"status": deliverable_status})

    for key in doc_queue:
        slot = tuple(key.split("|", 1))
        field = slot[1]
        tip = tips.get(slot)
        if tip is None:
            continue  # R1 已记
        decision = tip.get("decision")
        corrected = tip.get("corrected_value")

        # ---- R3:缺席要有证据
        if decision == "confirm_absent":
            probe = probes.get(field) or {}
            page_corroborated = probe.get("status") == "absent_corroborated"
            critic_ev = (critic_by_slot.get(slot) or {}).get("absence_evidence")
            # v3:critic 自己改判出来的 confirm_absent,证据只认页面探针
            # —— 一个角色不许为自己改判出的缺席作证(PR 审查的自我背书洞)
            override_tip = str(tip.get("adjudicator", "")).startswith(
                "agent:critic:")
            evidence_ok = page_corroborated or (
                critic_ev in _ABSENCE_EVIDENCE_OK and not override_tip)
            if not evidence_ok:
                violation("R3", {
                    "slot": key,
                    "page_probe": probe.get("status"),
                    "critic_absence_evidence": critic_ev,
                    "override_tip": override_tip,
                })
            # ---- R10:页上印着 EIN/TIN,seller_vat_id 的缺席就是假缺席
            if field == "seller_vat_id" and page["has_ein"]:
                violation("R10", {"slot": key,
                                  "page": "ein_shaped_token_printed"})

        # ---- R4:TIER1 上两角色必须一致
        # 缺任何一方的草稿也记违规 —— 「只有一个角色读过」不是共识
        # (缺失 = 该槽没人复核第二遍,恰恰是最该停的单角色放行形态)
        if field in TIER1:
            clerk_d = clerk_by_slot.get(slot) or {}
            critic_d = critic_by_slot.get(slot) or {}
            same = (
                clerk_d.get("decision") == critic_d.get("decision")
                and clerk_d and critic_d
                and (clerk_d.get("corrected_value") or "").strip()
                == (critic_d.get("corrected_value") or "").strip()
            )
            if not same:
                violation("R4", {
                    "slot": key,
                    "clerk": clerk_d.get("decision") or "missing",
                    "critic": critic_d.get("decision") or "missing",
                })

        # ---- R5-R8:修正值的页面根据
        if decision == "correct" and corrected:
            try:
                bound = binds_to_document(doc_id, str(corrected))
            except OcrUnavailable:
                bound = None
                violation("R5", {"slot": key, "corrected_value": corrected,
                                 "error": "ocr_unavailable"})
            else:
                if not bound:
                    equivalence = value_printed_on_page(
                        str(corrected), field, page)
                    bound = bool(equivalence)
                if not bound:
                    violation("R5", {"slot": key,
                                     "corrected_value": corrected})
            if field == "invoice_number" and ein_shaped(corrected):
                violation("R6", {"slot": key, "corrected_value": corrected})
            if field == "due_date" and terms_prose(corrected):
                violation("R7", {"slot": key, "corrected_value": corrected})
            probe = probes.get(field) or {}
            if probe.get("status") == "absent_corroborated":
                violation("R8", {"slot": key, "field": field})

    # ---- R9:approver 的独立 yes
    if approver_release is False:
        violation("R9", {"approver": "release=false"})
    # approver_release None(预检)不记 —— 预检问的是"策略会不会过",
    # 不是"批没批"。binder3 在 release 为真时才写批准,那条路径由
    # approve.append_approval 的可批校验与这里的 R2 共同把门。

    return {
        "doc_id": doc_id,
        "ready": not violations and deliverable_status in approvable_statuses,
        "status": deliverable_status,
        "queue_slots": len(doc_queue),
        "violations": violations,
        "policy_id": POLICY_ID,
        "policy_digest": policy_digest(),
    }
