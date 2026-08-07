"""TA 臂:agent 裁决器(docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md §3)。

钉死的性质都来自宪章,不是来自这个实验:
- 宪章一:agent 写草稿,**ID 由 Python 分配**;
- 宪章四:agent 弃权、心码组合非法 —— 如实记录 / 显式失败,不静默修好。
另加一条重放身份:同一段文字配不同的页图,call_id 必须不同,
否则重放会把别的槽的回答端上来。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop.agents import adjudicator as adj


@pytest.fixture
def run_dir(tmp_path):
    """最小但形状真实的 run —— append_adjudication 会校验快照与上游证据,
    拿假快照糊弄它只会测到校验本身(照搬 test_adjudicate.py 的装置)。"""
    import hashlib

    from invoiceloop.snapshot import compute_review_snapshot

    d = tmp_path
    (d / "run_manifest.json").write_text(json.dumps({
        "docs": ["doc-a"], "n_docs": 1, "out_of_calibration": False,
        "layout": "workspace", "derisk_root": str(tmp_path)}), encoding="utf-8")
    for name in ("artifact_registry.json", "evidence_span_registry.json",
                 "field_claim_graph.json", "field_drafts.json"):
        (d / name).write_text("[]", encoding="utf-8")
    # total_vat 无冻结声明 —— confirm_absent / not_applicable 只针对无声明的槽
    (d / "field_ledger.json").write_text(json.dumps({
        "claims": [], "rejections": [], "sha256": "ledger-sha"}), encoding="utf-8")
    (d / "gate_report.json").write_text(json.dumps({"findings": []}), encoding="utf-8")
    row = {"doc_id": "doc-a", "field": "total_vat", "value": "",
           "claim_id": None, "support_strength": "unsupported",
           "source_tiers": [], "applicability": "matches", "limitations": [],
           "gate_verdicts": {}, "span_ids": [], "cited_span_ids": [],
           "rejections": [], "blocking_findings": [],
           "reason_codes": ["UNSUPPORTED"], "route": "review"}
    (d / "support_matrix.json").write_text(json.dumps({
        "rows": [row],
        "summary": {"docs": 1, "slots": 1,
                    "by_strength": {"unsupported": 1, "single_source": 0,
                                    "corroborated": 0},
                    "requires_adjudication": 1, "applicability_disputed": 0,
                    "blocking_findings": 0, "drafts_rejected": 0,
                    "rejected_by_drafter": {}}}), encoding="utf-8")
    (d / "event_log.jsonl").write_text("", encoding="utf-8")
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / "doc-a.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / "doc-a.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
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
    (d / "review_snapshot.json").write_text(
        json.dumps(compute_review_snapshot(d)), encoding="utf-8")
    return d


def _draft(**kw):
    base = dict(decision="confirm_absent", reason_code="CONFIRMED_ABSENT",
                rationale="页面上没有 VAT 行", reviewer_confidence="medium")
    base.update(kw)
    return adj.AdjudicationDraft(**base)


class TestSingleWriter:
    def test_the_draft_schema_carries_no_identifiers(self):
        """宪章一:模型不许写 ID。schema 里压根不该有这些字段。"""
        fields = set(adj.AdjudicationDraft.model_fields)
        for banned in ("decision_id", "seq", "claim_id", "doc_id", "field",
                       "feedback_id", "review_snapshot_id"):
            assert banned not in fields, f"{banned} 不该由模型写"

    def test_python_assigns_the_decision_id(self, run_dir):
        written = adj.record_draft(run_dir, "doc-a|total_vat", _draft(),
                                   model="stub-model", decided_at="2026-08-08T00:00:00Z")
        assert written["decision_id"].startswith("HD-"), \
            "ID 必须是 append_adjudication 分配的"

    def test_adjudicator_names_the_arm_and_the_model(self, run_dir):
        written = adj.record_draft(run_dir, "doc-a|total_vat", _draft(),
                                   model="stub-model", decided_at="2026-08-08T00:00:00Z")
        who = written["adjudicator"]
        assert who.startswith("agent:"), "永远不许与人混淆"
        assert "stub-model" in who, "复算要知道是哪个模型判的"


class TestChartierFour:
    def test_abstain_is_recorded_not_dropped(self, run_dir):
        written = adj.record_draft(
            run_dir, "doc-a|total_vat",
            _draft(decision="abstain", reason_code="AMBIGUOUS_DOCUMENT"),
            model="stub-model", decided_at="2026-08-08T00:00:00Z")
        assert written["decision"] == "abstain"

    def test_illegal_reason_code_combo_raises_instead_of_being_fixed(self, run_dir):
        """心码与决策矛盾 = 错误监督。要么退回,要么炸,不许悄悄改对。"""
        with pytest.raises(ValueError, match="CONFIRMED_ABSENT"):
            adj.record_draft(run_dir, "doc-a|total_vat",
                             _draft(decision="accept"),
                             model="stub-model",
                             decided_at="2026-08-08T00:00:00Z")


class TestReplayIdentity:
    def test_same_text_different_page_image_is_a_different_call(self):
        pack = {"doc_id": "doc-a", "field": "total_vat"}
        a = adj.slot_call_id("m", pack, [b"\x89PNG-page-A"])
        b = adj.slot_call_id("m", pack, [b"\x89PNG-page-B"])
        assert a != b, "图不进 call_id,重放就会端错答案"

    def test_identical_inputs_give_an_identical_call_id(self):
        pack = {"doc_id": "doc-a", "field": "total_vat"}
        assert adj.slot_call_id("m", pack, [b"img"]) == \
            adj.slot_call_id("m", pack, [b"img"])

    def test_image_order_matters(self):
        pack = {"doc_id": "doc-a", "field": "total_vat"}
        assert adj.slot_call_id("m", pack, [b"a", b"b"]) != \
            adj.slot_call_id("m", pack, [b"b", b"a"])


class TestRunArm:
    def test_every_slot_produces_exactly_one_row(self, run_dir):
        calls = []

        def judge(pack, images):
            calls.append(pack["doc_id"])
            return _draft()

        report = adj.run_arm(run_dir, ["doc-a|total_vat"], judge=judge,
                             model="stub-model",
                             decided_at="2026-08-08T00:00:00Z")
        assert report["written"] == 1
        assert calls == ["doc-a"]
        lines = (run_dir / "adjudication_ledger.jsonl").read_text().splitlines()
        assert len(lines) == 1

    def test_a_failing_slot_is_reported_not_swallowed(self, run_dir):
        def judge(pack, images):
            raise RuntimeError("model said no")

        report = adj.run_arm(run_dir, ["doc-a|total_vat"], judge=judge,
                             model="stub-model",
                             decided_at="2026-08-08T00:00:00Z")
        assert report["written"] == 0
        assert report["failed"] == 1
        assert "model said no" in json.dumps(report["failures"])

    def test_the_judge_never_sees_truth(self, run_dir):
        seen = {}

        def judge(pack, images):
            seen.update(pack)
            return _draft()

        adj.run_arm(run_dir, ["doc-a|total_vat"], judge=judge, model="stub-model",
                    decided_at="2026-08-08T00:00:00Z")
        assert not any("truth" in k for k in seen)
