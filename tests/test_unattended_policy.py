"""Arm U 策略:今晚三次真实失败各一条反例,加一条全绿路径。零 API。

规则改动 = 换 policy id。这里的每条夹具都在钉一件事:**单模型说"做完了"
永远不构成批准的根据**(2026-08-27 grokbot 实验的三条失败:假 net、
EIN 当发票号、队列空就签)。
"""

from __future__ import annotations

import hashlib
import json

import pytest

from invoiceloop import unattended_policy as up
from invoiceloop.adjudicate import append_adjudication

QUEUE = ["doc-a|invoice_number", "doc-a|seller_vat_id", "doc-a|total_net",
         "doc-a|amount_due", "doc-a|due_date"]

#: 页面词级 OCR:纸面印着的东西进这里,没印的东西不许进。
#: 基准页不含 EIN —— R10 的夹具自己往页上加。
_PAGE_WORDS = [
    "KTVL", "INVOICE", "096084",           # 发票号是印着的
    "TOTAL", "DUE", "$1,744.20",           # 金额带千分位与符号
    "NET", "AMOUNT", "956.25",
    "12/19/99",                            # 美式日期
    "DUE", "ON", "RECEIPT",
]


def _with_page_word(run_dir, word):
    """夹具里往页面上补一个印着的词(重写 OCR,快照成分不含 OCR 内容)。"""
    path = run_dir / "ocr" / "doc-a.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    words = data["pages"][0]["blocks"][0]["lines"][0]["words"]
    words.append({"value": word, "geometry": [[0.3, 0.3], [0.4, 0.4]]})
    path.write_text(json.dumps(data), encoding="utf-8")
    return run_dir


def _ocr_json(words):
    return {"pages": [{"page_idx": 0, "dimensions": [1000, 1000],
                       "blocks": [{"lines": [{"words": [
                           {"value": w, "geometry": [[0.1, 0.1], [0.2, 0.2]]}
                           for w in words]}]}]}]}


@pytest.fixture
def run_dir(tmp_path, monkeypatch, clear_ocr_caches):
    # policy 的页面判断经全局 derisk_root() 读 OCR —— 钉到夹具工作区;
    # load_ocr 的 lru_cache 只按 doc_id 键控,跨 tmp_path 必须清
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(tmp_path))
    d = tmp_path
    (d / "run_manifest.json").write_text(json.dumps({
        "docs": ["doc-a"], "n_docs": 1, "out_of_calibration": False,
        "layout": "workspace", "derisk_root": str(tmp_path)}), encoding="utf-8")
    for name in ("artifact_registry.json", "evidence_span_registry.json",
                 "field_claim_graph.json", "field_drafts.json"):
        (d / name).write_text("[]", encoding="utf-8")
    claims = [
        {"claim_id": "FC-0001", "doc_id": "doc-a", "field": "invoice_number",
         "value": "096084", "span_ids": [], "drafted_by": "dws_understand",
         "binding_coverage": 1.0},
        {"claim_id": "FC-0002", "doc_id": "doc-a", "field": "amount_due",
         "value": "956.25", "span_ids": [], "drafted_by": "dws_understand",
         "binding_coverage": 1.0},
    ]
    import hashlib as _hl

    ledger_sha = _hl.sha256(json.dumps(
        {"claims": claims}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    (d / "field_ledger.json").write_text(json.dumps(
        {"claims": claims, "sha256": ledger_sha}), encoding="utf-8")
    rows = []
    # invoice_number / amount_due 有冻结声明(accept 必须指认声明);
    # 其余槽无声明(confirm_absent 只针对无声明槽)
    for field in ("invoice_number", "seller_vat_id", "total_net",
                  "amount_due", "due_date"):
        has_claim = field in ("invoice_number", "amount_due")
        rows.append({"doc_id": "doc-a", "field": field,
                     "value": {"invoice_number": "096084",
                               "amount_due": "956.25"}.get(field, ""),
                     "claim_id": "FC-0001" if field == "invoice_number"
                     else ("FC-0002" if field == "amount_due" else None),
                     "support_strength": "single_source" if has_claim
                     else "unsupported",
                     "source_tiers": ["dws_extraction"] if has_claim else [],
                     "applicability": "matches", "limitations": [],
                     "gate_verdicts": {}, "span_ids": [],
                     "cited_span_ids": [], "rejections": [],
                     "blocking_findings": [], "reason_codes": ["UNSUPPORTED"],
                     "route": "review"})
    (d / "support_matrix.json").write_text(json.dumps({
        "rows": rows,
        "summary": {"docs": 1, "slots": len(rows),
                    "by_strength": {"unsupported": len(rows),
                                    "single_source": 0, "corroborated": 0},
                    "requires_adjudication": len(rows),
                    "applicability_disputed": 0, "blocking_findings": 0,
                    "drafts_rejected": 0, "rejected_by_drafter": {}}}),
        encoding="utf-8")
    (d / "gate_report.json").write_text(json.dumps({
        "findings": [],
        # total_net 的标签不在页面上(假 net 那条:工时合计不是 net)
        "absence_probes": {"doc-a": {
            "total_net": {"status": "absent_corroborated"},
            "due_date": {"status": "not_measured"},
        }}}), encoding="utf-8")
    (d / "event_log.jsonl").write_text("", encoding="utf-8")
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / "doc-a.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / "doc-a.json").write_text(
        json.dumps(_ocr_json(_PAGE_WORDS)), encoding="utf-8")
    (d / "raw").mkdir()
    for mode in ("understand", "agentic"):
        (d / "raw" / f"doc-a.{mode}.json").write_text(
            json.dumps({"http_status": 200}), encoding="utf-8")

    def h(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    (d / "input_manifest.json").write_text(json.dumps({
        "fingerprint": "f" * 64,
        "docs": [{"doc_id": "doc-a",
                  "pdf_sha256": h(d / "input" / "pdfs" / "doc-a.pdf"),
                  "ocr_sha256": h(d / "ocr" / "doc-a.json"),
                  "raw_sha256": {m: h(d / "raw" / f"doc-a.{m}.json")
                                 for m in ("understand", "agentic")}}],
    }), encoding="utf-8")
    from invoiceloop.snapshot import compute_review_snapshot

    (d / "review_snapshot.json").write_text(
        json.dumps(compute_review_snapshot(d)), encoding="utf-8")
    return d


def _write(run_dir, field, decision, *, corrected=None, adjudicator="agent:stub"):
    claim = None
    if decision in ("accept", "correct", "reject"):
        claim = {"invoice_number": "FC-0001",
                 "amount_due": "FC-0002"}.get(field)
    return append_adjudication(
        run_dir, claim_id=claim, doc_id="doc-a", field=field,
        decision=decision, rationale="fixture", adjudicator=adjudicator,
        decided_at="2026-08-27T00:00:00Z", corrected_value=corrected,
        reason_code={"accept": "ROUTING_FALSE_POSITIVE",
                     "correct": "WRONG_VALUE", "reject": "WRONG_VALUE",
                     "confirm_absent": "CONFIRMED_ABSENT",
                     "abstain": "AMBIGUOUS_DOCUMENT"}[decision])


def _audit(run_dir, **kw):
    kw.setdefault("queue_keys", QUEUE)
    kw.setdefault("clerk_by_slot", {})
    kw.setdefault("critic_by_slot", {})
    kw.setdefault("deliverable_status", "ready_for_approval")
    kw.setdefault("approvable_statuses",
                  ("ready_for_approval", "ready_for_approval_with_caveats"))
    return up.audit_document(run_dir, "doc-a", **kw)


def test_tier1_critic_missing_is_no_consensus(run_dir):
    """R4(v3):TIER1 槽上 critic 草稿缺失 = 没有共识,不是「无分歧」。
    此前缺失静默通过,单角色读过的 TIER1 槽可能放行(PR 审查 P1)。"""
    _write(run_dir, "amount_due", "accept")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "amount_due"): {"decision": "accept"}},
        critic_by_slot={})  # critic 调用失败,一个草稿都没有
    codes = [v["code"] for v in result["violations"]]
    assert "tier1_clerk_critic_disagreement" in codes, result["violations"]


def test_critic_override_absence_cannot_self_vouch(run_dir):
    """R3(v3):critic 改判出的 confirm_absent,自己的 absence_evidence
    不算证据 —— 只认页面探针(PR 审查的自我背书洞)。"""
    _write(run_dir, "due_date", "confirm_absent",
           adjudicator="agent:critic:stub-model")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "due_date"): {"decision": "correct"}},
        critic_by_slot={("doc-a", "due_date"): {
            "decision": "confirm_absent",
            "absence_evidence": "label_absent"}})
    codes = [v["code"] for v in result["violations"]]
    assert "absence_without_evidence" in codes, result["violations"]


def test_policy_digest_is_validated(run_dir):
    """approve.py:非 64 位十六进制的 policy_digest 一行都不写。"""
    from invoiceloop.approve import append_approval

    with pytest.raises(ValueError, match="policy_digest"):
        append_approval(
            run_dir, doc_id="doc-a", approved_by="unattended-policy-v3+x",
            rationale="x", approved_at="2026-08-28T00:00:00Z",
            policy_digest="not-a-real-digest")


def test_policy_digest_is_stable_and_binds_rule_text():
    assert up.policy_digest() == up.policy_digest()
    assert len(up.policy_digest()) == 64


def test_all_agree_with_evidence_is_ready(run_dir):
    """全绿路径:每槽两角色一致、缺席有证据、修正值印在页上。"""
    for field in ("invoice_number", "amount_due"):
        _write(run_dir, field, "accept")
    for field in ("seller_vat_id", "total_net", "due_date"):
        _write(run_dir, field, "confirm_absent")
    result = _audit(
        run_dir,
        clerk_by_slot={("doc-a", f): {"decision": d} for f, d in (
            ("invoice_number", "accept"), ("amount_due", "accept"),
            ("seller_vat_id", "confirm_absent"),
            ("total_net", "confirm_absent"),
            ("due_date", "confirm_absent"))},
        critic_by_slot={
            ("doc-a", "invoice_number"): {"decision": "accept"},
            ("doc-a", "amount_due"): {"decision": "accept"},
            ("doc-a", "seller_vat_id"): {"decision": "confirm_absent",
                                         "absence_evidence": "label_absent"},
            ("doc-a", "total_net"): {"decision": "confirm_absent",
                                     "absence_evidence": "value_absent"},
            ("doc-a", "due_date"): {"decision": "confirm_absent",
                                    "absence_evidence": "label_absent"},
        },
        approver_release=True)
    assert result["ready"] is True, result["violations"]


def test_fake_net_on_label_absent_field_is_blocked(run_dir):
    """R8:页面根本没有 Net 列,correct 填了页上别的数字(110810 场景)。"""
    _write(run_dir, "total_net", "correct", corrected="956.25")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "total_net"): {"decision": "correct"}},
        critic_by_slot={("doc-a", "total_net"): {"decision": "correct"}})
    codes = [v["code"] for v in result["violations"]]
    assert "correct_on_label_absent_field" in codes, result["violations"]
    assert result["ready"] is False


def test_ein_as_invoice_number_is_blocked_even_when_printed(run_dir):
    """R6:58-0391492 印在页上(绑定通过),但它是 TIN,不是发票号。"""
    _with_page_word(run_dir, "58-0391492")
    _write(run_dir, "invoice_number", "correct", corrected="58-0391492")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "invoice_number"): {"decision": "correct"}},
        critic_by_slot={("doc-a", "invoice_number"): {"decision": "correct"}})
    codes = [v["code"] for v in result["violations"]]
    assert "ein_as_invoice_number" in codes, result["violations"]


def test_printed_ein_voids_a_seller_vat_id_absence(run_dir):
    """R10:页上印着 Taxpayer ID,seller_vat_id 的 confirm_absent 是假缺席
    (2026-08-27 live 验收:两个模型角色同漏,只有确定性规则能补)。"""
    _with_page_word(run_dir, "58-0391492")
    _write(run_dir, "seller_vat_id", "confirm_absent")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "seller_vat_id"): {"decision": "confirm_absent"}},
        critic_by_slot={("doc-a", "seller_vat_id"): {
            "decision": "confirm_absent",
            "absence_evidence": "label_absent"}})
    codes = [v["code"] for v in result["violations"]]
    assert "false_absence_ein_on_page" in codes, result["violations"]


def test_iso_date_and_bare_amount_are_the_printed_value(run_dir):
    """R5 格式等价:1999-12-19 ≡ 页面 12/19/99;1744.20 ≡ 页面 $1,744.20
    (第一轮 live 验收把两者都误判成不在页上)。"""
    _write(run_dir, "due_date", "correct", corrected="1999-12-19")
    _write(run_dir, "amount_due", "correct", corrected="1744.20")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "due_date"): {"decision": "correct"},
        ("doc-a", "amount_due"): {"decision": "correct"}},
        critic_by_slot={
            ("doc-a", "due_date"): {"decision": "correct"},
            ("doc-a", "amount_due"): {"decision": "correct"}})
    codes = [v["code"] for v in result["violations"]]
    assert "corrected_value_not_on_page" not in codes, result["violations"]


def test_absence_without_evidence_is_blocked(run_dir):
    """R3:critic cannot_tell = 没把握 = 无证据;不是缺席的背书。"""
    _write(run_dir, "seller_vat_id", "confirm_absent")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "seller_vat_id"): {"decision": "confirm_absent"}},
        critic_by_slot={("doc-a", "seller_vat_id"): {
            "decision": "confirm_absent",
            "absence_evidence": "cannot_tell"}})
    codes = [v["code"] for v in result["violations"]]
    assert "absence_without_evidence" in codes, result["violations"]


def test_tier1_disagreement_blocks_even_with_a_tip(run_dir):
    """R4:clerk accept、critic reject 的 amount_due 有 tip 也不准批。"""
    _write(run_dir, "amount_due", "accept")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "amount_due"): {"decision": "accept"}},
        critic_by_slot={("doc-a", "amount_due"): {"decision": "reject"}})
    codes = [v["code"] for v in result["violations"]]
    assert "tier1_clerk_critic_disagreement" in codes, result["violations"]


def test_corrected_value_not_on_page_is_fake_presence(run_dir):
    """R5:修正值必须绑定到页面;发明出来的数字过不了。"""
    _write(run_dir, "amount_due", "correct", corrected="999999.00")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "amount_due"): {"decision": "correct"}},
        critic_by_slot={("doc-a", "amount_due"): {"decision": "correct"}})
    codes = [v["code"] for v in result["violations"]]
    assert "corrected_value_not_on_page" in codes, result["violations"]


def test_due_on_receipt_is_terms_not_a_date(run_dir):
    """R7:「Due on Receipt」印在页上、绑定也过,但它不是日历到期日。"""
    _write(run_dir, "due_date", "correct", corrected="Due on Receipt")
    result = _audit(run_dir, clerk_by_slot={
        ("doc-a", "due_date"): {"decision": "correct"}},
        critic_by_slot={("doc-a", "due_date"): {"decision": "correct"}})
    codes = [v["code"] for v in result["violations"]]
    assert "terms_prose_as_due_date" in codes, result["violations"]


def test_unadjudicated_slot_blocks(run_dir):
    """R1:队列空了≠做完了 —— 没有 tip 的槽位本身就是要阻断的。"""
    result = _audit(run_dir)
    codes = [v["code"] for v in result["violations"]]
    assert codes.count("slot_without_tip") == len(QUEUE)
    assert result["ready"] is False


def test_pending_document_never_reaches_ready(run_dir):
    """R2:交付投影还差槽,status 不在可批集合。"""
    result = _audit(run_dir, deliverable_status="pending")
    codes = [v["code"] for v in result["violations"]]
    assert "document_not_approvable" in codes


def test_approver_refusal_is_recorded_as_r9(run_dir):
    """R9:策略全过 + approver 说不,照样不批。"""
    result = _audit(run_dir, approver_release=False)
    codes = [v["code"] for v in result["violations"]]
    assert "approver_release_missing" in codes
