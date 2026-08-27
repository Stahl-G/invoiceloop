"""Arm U 流水线:七段 SequentialAgent 全程真跑,模型角色全部注入桩(零 API)。

钉的性质(计划书 §3 的验收):
- Runner 真的被调用,七个 stage 都出现在 event_authors 里;
- clerk 行署名 agent:<model>,critic 改判以 supersedes 落账、署名
  agent:critic:<model>;
- 策略闸不放行的单据**根本到不了 approver**;
- 批准只有「策略 + approver 双 yes」才写,署名与 policy_digest 进账本;
- approver 拒绝 = 单据停在 ready_for_approval,如实记录。
"""

from __future__ import annotations

import hashlib
import json

import pytest

pytest.importorskip("pydantic", reason="需要 invoiceloop[gemini]")
pytest.importorskip("google.adk.agents",
                    reason="需要 google-adk(干净 clone 跳过,不假绿)")

from invoiceloop.agents import unattended as un  # noqa: E402
from invoiceloop.agents.adjudicator import AdjudicationDraft  # noqa: E402
from invoiceloop.agents.approver import ReleaseDecision  # noqa: E402
from invoiceloop.agents.critic import CriticDraft  # noqa: E402

QUEUE_FIELDS = ("invoice_number", "seller_vat_id", "total_net",
                "amount_due", "due_date")

_PAGE_WORDS = [
    "INVOICE", "096084", "TOTAL", "DUE", "$1,744.20",
]


@pytest.fixture
def run_dir(tmp_path, monkeypatch, clear_ocr_caches):
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
         "value": "1744.20", "span_ids": [], "drafted_by": "dws_understand",
         "binding_coverage": 1.0},
    ]
    ledger_sha = hashlib.sha256(json.dumps(
        {"claims": claims}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    (d / "field_ledger.json").write_text(json.dumps(
        {"claims": claims, "sha256": ledger_sha}), encoding="utf-8")
    rows = []
    for field in QUEUE_FIELDS:
        claim_id = {"invoice_number": "FC-0001",
                    "amount_due": "FC-0002"}.get(field)
        rows.append({"doc_id": "doc-a", "field": field,
                     "value": {"invoice_number": "096084",
                               "amount_due": "1744.20"}.get(field, ""),
                     "claim_id": claim_id,
                     "support_strength": "single_source" if claim_id
                     else "unsupported",
                     "source_tiers": ["dws_extraction"] if claim_id else [],
                     "applicability": "matches", "limitations": [],
                     "gate_verdicts": {}, "span_ids": [],
                     "cited_span_ids": [], "rejections": [],
                     "blocking_findings": [], "reason_codes": ["UNSUPPORTED"],
                     "route": "review"})
    (d / "support_matrix.json").write_text(json.dumps({
        "rows": rows, "summary": {}}, ), encoding="utf-8")
    (d / "routing_report.json").write_text(json.dumps({
        "harness_id": "HAR-0001",
        "policy": {}, "policy_digest": "p" * 64,
        "routes": [{"doc_id": "doc-a", "field": f, "route": "review",
                    "reason_codes": ["UNSUPPORTED"]}
                   for f in QUEUE_FIELDS]}), encoding="utf-8")
    (d / "gate_report.json").write_text(json.dumps({
        "findings": [], "absence_probes": {"doc-a": {}}}), encoding="utf-8")
    (d / "event_log.jsonl").write_text("", encoding="utf-8")
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / "doc-a.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / "doc-a.json").write_text(json.dumps({"pages": [{
        "page_idx": 0, "dimensions": [1000, 1000],
        "blocks": [{"lines": [{"words": [
            {"value": w, "geometry": [[0.1, 0.1], [0.2, 0.2]]}
            for w in _PAGE_WORDS]}]}]}]}), encoding="utf-8")
    (d / "raw").mkdir()
    for mode in ("understand", "agentic"):
        (d / "raw" / f"doc-a.{mode}.json").write_text(
            json.dumps({"http_status": 200}), encoding="utf-8")
    (d / "calculated_due_dates.json").write_text(json.dumps(
        {"records": {}}), encoding="utf-8")

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
    # clerk/critic 必须看到整页图(缺图 = 没跑,不许裁)
    pages = d / "pages"
    pages.mkdir()
    (pages / "doc-a-1.png").write_bytes(b"\x89PNG fake page 1")
    return d


def _clerk_stub(decision_by_field, corrected=None):
    corrected = corrected or {}

    def clerk(pack, images):
        assert images, "clerk 必须拿到整页图"
        field = pack["field"]
        decision = decision_by_field[field]
        return AdjudicationDraft(
            decision=decision,
            reason_code={"accept": "ROUTING_FALSE_POSITIVE",
                         "correct": "WRONG_VALUE",
                         "confirm_absent": "CONFIRMED_ABSENT"}[decision],
            rationale="stub clerk", reviewer_confidence="medium",
            corrected_value=corrected.get(field))
    return clerk


def _critic_stub(agree=True, evidence="label_absent", decision_override=None):
    def critic(pack, images):
        assert images, "critic 必须拿到整页图"
        proposal = pack.get("clerk_proposal") or {}
        decision = (decision_override or proposal).get(
            "decision", "confirm_absent")
        return CriticDraft(
            agree=agree, decision=decision,
            corrected_value=None,
            absence_evidence=evidence if decision == "confirm_absent"
            else "not_absent",
            rationale="stub critic", release_veto=False)
    return critic


def _approver_stub(release=True):
    def approver(summary):
        assert summary["policy"]["digest"], "approver 必须看到策略摘要"
        return ReleaseDecision(release=release,
                               rationale="stub approver release")
    return approver


def _run(run_dir, **kw):
    kw.setdefault("clerk", _clerk_stub({
        "invoice_number": "accept", "amount_due": "accept",
        "seller_vat_id": "confirm_absent", "total_net": "confirm_absent",
        "due_date": "confirm_absent"}))
    kw.setdefault("critic", _critic_stub())
    kw.setdefault("approver", _approver_stub())
    return un.run_unattended(
        run_dir, model="stub-model", decided_at="2026-08-27T12:00:00Z",
        **kw)


class TestThePipelineRuns:
    def test_all_seven_stages_executed_under_a_real_runner(self, run_dir):
        report = _run(run_dir)
        authors = report["adk"]["event_authors"]
        for stage in ("clerk", "binder", "critic", "binder2", "gate",
                      "approver", "binder3"):
            assert stage in authors, f"{stage} 没跑"
        assert report["adk"]["executed"] is True

    def test_clerk_lines_carry_the_agent_signature(self, run_dir):
        _run(run_dir)
        lines = [json.loads(l) for l in
                 (run_dir / "adjudication_ledger.jsonl").read_text()
                 .splitlines()]
        assert len(lines) == 5
        assert {l["adjudicator"] for l in lines} == {"agent:stub-model"}

    def test_approval_written_only_with_both_yeses(self, run_dir):
        report = _run(run_dir)
        assert report["gate_ready_docs"] == ["doc-a"]
        assert len(report["approvals"]) == 1
        entry = json.loads(
            (run_dir / "approve_ledger.jsonl").read_text())
        assert entry["approved_by"] == \
            "unattended-policy-v2+agent:critic:stub-model"
        assert entry["policy_digest"] == \
            __import__("invoiceloop.unattended_policy",
                       fromlist=["policy_digest"]).policy_digest()
        deliverable = json.loads(
            (run_dir / "deliverable.json").read_text())
        assert deliverable["docs"]["doc-a"]["status"] == \
            "approved_for_export"


class TestDisagreement:
    def test_critic_override_supersedes_with_its_own_signature(self, run_dir):
        report = _run(
            run_dir,
            critic=_critic_stub(agree=False, decision_override={"decision":
                                                                "reject"}))
        lines = [json.loads(l) for l in
                 (run_dir / "adjudication_ledger.jsonl").read_text()
                 .splitlines()]
        by_sig = {}
        for l in lines:
            by_sig.setdefault(l["adjudicator"], []).append(l)
        assert len(by_sig["agent:critic:stub-model"]) == 5
        superseded = [l for l in by_sig["agent:critic:stub-model"]
                      if l.get("supersedes_decision_id")]
        assert len(superseded) == 5, "改判必须显式顶掉 clerk 行"
        # reject 落在关键字段上 → 单据 blocked,连 approver 都不该被问
        assert report["gate_ready_docs"] == []
        assert report["approvals"] == []


class TestPolicyGateFirst:
    def test_a_not_ready_document_never_reaches_the_approver(self, run_dir):
        """clerk 把 TIN 修正成发票号(critic 也同意)→ R6 拦下,approver 零调用。"""
        seen = []

        def approver(summary):
            seen.append(summary["doc_id"])
            return ReleaseDecision(release=True, rationale="x")

        report = _run(
            run_dir,
            clerk=_clerk_stub(
                {"invoice_number": "correct", "amount_due": "accept",
                 "seller_vat_id": "confirm_absent", "total_net":
                     "confirm_absent", "due_date": "confirm_absent"},
                corrected={"invoice_number": "58-0391492"}),
            approver=approver)
        assert seen == [], "策略不过的单据不该消耗 approver 调用"
        assert report["gate_ready_docs"] == []
        codes = [v["code"] for v in
                 report["gate"]["doc-a"]["violations"]]
        assert "ein_as_invoice_number" in codes


class TestApproverRefusal:
    def test_refusal_leaves_the_document_at_ready(self, run_dir):
        report = _run(run_dir, approver=_approver_stub(release=False))
        assert report["approvals"] == []
        assert len(report["approval_refusals"]) == 1
        deliverable = json.loads(
            (run_dir / "deliverable.json").read_text())
        assert deliverable["docs"]["doc-a"]["status"] == \
            "ready_for_approval"


class TestCharterFour:
    def test_a_clerk_failure_blocks_release_instead_of_shortening(self, run_dir):
        """一个槽的模型调用失败 → R1 拦下整单,不批、不缩水、如实记录。"""
        def clerk(pack, images):
            if pack["field"] == "due_date":
                raise RuntimeError("model unavailable")
            return _clerk_stub({
                "invoice_number": "accept", "amount_due": "accept",
                "seller_vat_id": "confirm_absent",
                "total_net": "confirm_absent"})(pack, images)

        report = _run(run_dir, clerk=clerk)
        assert len(report["clerk_failures"]) == 1
        assert report["gate_ready_docs"] == []
        codes = [v["code"] for v in
                 report["gate"]["doc-a"]["violations"]]
        assert "slot_without_tip" in codes

    def test_accept_without_a_frozen_claim_is_recorded_not_crashed(self, run_dir):
        """无冻结声明的槽上 clerk 选了 accept → 记 binding_failure,
        不修答案、不炸整臂(第二轮 live 验收实测的形状)。"""
        def clerk(pack, images):
            stub = _clerk_stub({
                "invoice_number": "accept", "amount_due": "accept",
                "seller_vat_id": "confirm_absent", "total_net": "accept",
                "due_date": "confirm_absent"})
            return stub(pack, images)

        report = _run(run_dir, clerk=clerk)
        # total_net 无冻结声明(FC 只在 invoice_number/amount_due)
        assert any("total_net" in f["slot"]
                   for f in report["clerk_binding_failures"])
        assert report["gate_ready_docs"] == []
        codes = [v["code"] for v in
                 report["gate"]["doc-a"]["violations"]]
        assert "slot_without_tip" in codes
