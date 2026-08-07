"""六个门禁的单元测试:裁决、finding 路由、阻断语义、契约不变量。"""

from __future__ import annotations

import pytest

from invoiceloop import gates
from invoiceloop.fields import FIELDS
from tests.conftest import bbox_meta, make_response, pin_corpus

FULL_DATA = {
    "invoice_number": "INV-42",
    "issue_date": "03/01/99",
    "due_date": "04/01/99",
    "seller_name": "Seller Corp",
    "buyer_name": "Buyer Ltd",
    "seller_vat_id": "GB123456789",
    "total_net": "90.00",
    "total_vat": "10.00",
    "total_gross": "100.00",
    "amount_due": "100.00",
}


def run(data, *, meta=None, agentic_data="same", vision=None):
    u = make_response("doc-a", "understand", data, meta or {})
    a = make_response("doc-a", "agentic", agentic_data if agentic_data != "same" else dict(data))
    return gates.run_gates(
        ["doc-a"],
        understand={"doc-a": u}, agentic={"doc-a": a},
        vision_answers=vision or {}, ledger_sha256="x", artifact_digest="y",
    )


def verdicts(report, field):
    return report["evaluations"]["doc-a"][field]


def findings(report, gate_id=None, field=None):
    out = report["findings"]
    if gate_id:
        out = [f for f in out if f["gate_id"] == gate_id]
    if field:
        out = [f for f in out if f["field"] == field]
    return out


class TestContract:
    def test_blocking_invariant(self):
        report = run({f: None for f in FIELDS})
        for f in report["findings"]:
            assert f["blocking"] == (f["blocking_level"] == "blocking")

    def test_input_signature_recorded(self):
        from invoiceloop import doctype
        report = run(FULL_DATA)
        assert report["input_signature"] == {
            "ledger_sha256": "x",
            "artifact_digest": "y",
            "doctype_digest": doctype.digest(),
        }
        assert "document_checks" in report


class TestExtractionPresent:
    def test_missing_value_is_blocking_with_repair_route(self):
        report = run({**FULL_DATA, "total_vat": None})
        assert verdicts(report, "total_vat")["extraction_present"] == "fail"
        (f,) = findings(report, "extraction_present", "total_vat")
        assert f["blocking"] and f["repair_owner"] == "vision_reread"

    def test_understand_response_missing_blocks_the_whole_doc(self):
        report = gates.run_gates(
            ["doc-a"], understand={"doc-a": None}, agentic={"doc-a": None},
            vision_answers={}, ledger_sha256="x", artifact_digest="y",
        )
        assert all(v == "unavailable"
                   for v in verdicts(report, "invoice_number").values())
        (f,) = findings(report, "extraction_present")
        assert f["blocking"] and f["field"] is None


class TestWellformed:
    def test_unparseable_amount_fails_c4(self):
        report = run({**FULL_DATA, "total_gross": "not-a-number"})
        assert verdicts(report, "total_gross")["field_wellformed"] == "fail"
        (f,) = findings(report, "field_wellformed", "total_gross")
        assert f["repair_owner"] == "re_extract" and not f["blocking"]

    def test_implausible_date_fails_c5(self):
        report = run({**FULL_DATA, "issue_date": "no digits here"})
        assert verdicts(report, "issue_date")["field_wellformed"] == "fail"

    def test_invoice_number_needs_alnum(self):
        report = run({**FULL_DATA, "invoice_number": "—"})
        assert verdicts(report, "invoice_number")["field_wellformed"] == "fail"


class TestArithmetic:
    def test_c1_flags_all_feeding_fields_not_a_guessed_culprit(self):
        report = run({**FULL_DATA, "total_vat": "50.00"})
        for field in ("total_net", "total_vat", "total_gross"):
            assert verdicts(report, field)["arithmetic_consistency"] == "fail"
        assert verdicts(report, "amount_due")["arithmetic_consistency"] == "pass"

    def test_c3_date_order(self):
        report = run({**FULL_DATA, "issue_date": "05/01/99", "due_date": "04/01/99"})
        assert verdicts(report, "issue_date")["arithmetic_consistency"] == "fail"
        assert verdicts(report, "due_date")["arithmetic_consistency"] == "fail"

    def test_c3_us_format_no_false_positive(self):
        """82 评 P1-2 实测误报:美式 01/15 → 02/14 合法,旧反序比较误判反序。"""
        report = run({**FULL_DATA, "issue_date": "01/15/2026", "due_date": "02/14/2026"})
        assert verdicts(report, "issue_date")["arithmetic_consistency"] == "pass"

    def test_c3_us_format_catches_real_inversion(self):
        """漏报半边:美式真反序 02/14 → 01/15 必须抓(假发票六门全过的路)。"""
        report = run({**FULL_DATA, "issue_date": "02/14/2026", "due_date": "01/15/2026"})
        assert verdicts(report, "issue_date")["arithmetic_consistency"] == "fail"
        assert verdicts(report, "due_date")["arithmetic_consistency"] == "fail"

    def test_c3_iso_format(self):
        ok = run({**FULL_DATA, "issue_date": "2026-01-15", "due_date": "2026-02-14"})
        assert verdicts(ok, "issue_date")["arithmetic_consistency"] == "pass"
        bad = run({**FULL_DATA, "issue_date": "2026-02-14", "due_date": "2026-01-15"})
        assert verdicts(bad, "issue_date")["arithmetic_consistency"] == "fail"

    def test_c3_day_first_format(self):
        ok = run({**FULL_DATA, "issue_date": "15.01.2026", "due_date": "14.02.2026"})
        assert verdicts(ok, "issue_date")["arithmetic_consistency"] == "pass"
        bad = run({**FULL_DATA, "issue_date": "14.02.2026", "due_date": "15.01.2026"})
        assert verdicts(bad, "issue_date")["arithmetic_consistency"] == "fail"

    def test_c3_ambiguous_pair_uses_unambiguous_sibling(self):
        """01/15 无歧义定调美式 → 歧义的 01/05 按月/日读:1/5 < 1/15 真反序。"""
        report = run({**FULL_DATA, "issue_date": "01/15/2026", "due_date": "01/05/2026"})
        assert verdicts(report, "issue_date")["arithmetic_consistency"] == "fail"

    def test_c3_both_ambiguous_keeps_preregistered_day_first(self):
        """双歧义回退 day-first(预注册):05/06 = 6月5日 → 06/05 = 5月6日 是反序。"""
        report = run({**FULL_DATA, "issue_date": "05/06/2026", "due_date": "06/05/2026"})
        assert verdicts(report, "issue_date")["arithmetic_consistency"] == "fail"
        ok = run({**FULL_DATA, "issue_date": "06/05/2026", "due_date": "05/06/2026"})
        assert verdicts(ok, "issue_date")["arithmetic_consistency"] == "pass"

    def test_unevaluated_when_inputs_missing(self):
        report = run({**FULL_DATA, "total_net": None})
        # C1 缺输入评不了;C2 仍评了 gross/due
        assert verdicts(report, "total_net")["arithmetic_consistency"] == "unavailable"
        assert verdicts(report, "total_gross")["arithmetic_consistency"] == "pass"
        assert verdicts(report, "invoice_number")["arithmetic_consistency"] == "unavailable"


class TestCitation:
    def test_party_fields_are_not_checkable_no_finding(self, positioned_corpus):
        report = run(FULL_DATA)
        assert verdicts(report, "seller_name")["citation_holds"] == "unavailable"
        assert findings(report, "citation_holds", "seller_name") == []

    def test_value_in_cited_region_passes(self, positioned_corpus):
        meta = {"total_gross": bbox_meta(300, 500, 450, 530)}
        report = run(FULL_DATA, meta=meta)
        assert verdicts(report, "total_gross")["citation_holds"] == "pass"

    def test_value_outside_cited_region_fails(self, positioned_corpus):
        meta = {"total_gross": bbox_meta(300, 500, 450, 530)}
        report = run({**FULL_DATA, "total_gross": "200.00"}, meta=meta)
        assert verdicts(report, "total_gross")["citation_holds"] == "fail"
        (f,) = findings(report, "citation_holds", "total_gross")
        assert f["repair_owner"] == "vision_reread" and not f["blocking"]

    def test_missing_ocr_is_blocking_not_silent(self, clear_ocr_caches, tmp_path, monkeypatch):
        pin_corpus(monkeypatch, tmp_path)  # 没有 OCR 文件
        meta = {"total_gross": bbox_meta(300, 500, 450, 530)}
        report = run(FULL_DATA, meta=meta)
        assert verdicts(report, "total_gross")["citation_holds"] == "unavailable"
        (f,) = findings(report, "citation_holds", "total_gross")
        assert f["blocking"]


class TestCrossMode:
    def test_both_absent_counts_as_agreement(self):
        data = {**FULL_DATA, "seller_vat_id": None}
        report = run(data)
        assert verdicts(report, "seller_vat_id")["cross_mode_agreement"] == "pass"

    def test_disagreement_fails_and_routes_to_human(self):
        report = run(FULL_DATA, agentic_data={**FULL_DATA, "total_gross": "101.00"})
        assert verdicts(report, "total_gross")["cross_mode_agreement"] == "fail"
        (f,) = findings(report, "cross_mode_agreement", "total_gross")
        assert f["repair_owner"] == "human"


class TestVisual:
    def test_no_value_means_nothing_to_corroborate(self):
        report = run({**FULL_DATA, "total_gross": None},
                     vision={"Kimi K3": {("doc-a", "total_gross"): {"value": "100.00"}}})
        assert verdicts(report, "total_gross")["visual_corroboration"] == "unavailable"

    def test_no_readers_is_unavailable_not_a_finding(self):
        report = run(FULL_DATA)
        assert verdicts(report, "total_gross")["visual_corroboration"] == "unavailable"
        assert findings(report, "visual_corroboration") == []

    def test_reader_corroboration_passes(self):
        vision = {"Kimi K3": {("doc-a", "total_gross"): {"value": "100.00"}}}
        report = run(FULL_DATA, vision=vision)
        assert verdicts(report, "total_gross")["visual_corroboration"] == "pass"

    def test_reader_disagreement_is_warning_not_fail(self):
        vision = {"Kimi K3": {("doc-a", "total_gross"): {"value": "999.00"}}}
        report = run(FULL_DATA, vision=vision)
        assert verdicts(report, "total_gross")["visual_corroboration"] == "warning"

    def test_abstain_is_not_an_attempt(self):
        vision = {"Kimi K3": {("doc-a", "total_gross"): {"value": "ABSTAIN"}}}
        report = run(FULL_DATA, vision=vision)
        assert verdicts(report, "total_gross")["visual_corroboration"] == "unavailable"


class TestGateError:
    def test_a_gate_crashing_on_one_doc_blocks_that_doc_not_the_batch(self, positioned_corpus):
        """门禁自己被坏数据打崩:这份文档记阻断,其他文档照常评。"""
        broken_meta = {"total_gross": {"bbox": {"x": "not-a-number", "y": 0,
                                                "width": 1, "height": 1},
                                       "source_bboxes": [{"bbox": {"x": "x", "y": 0,
                                                                   "width": 1, "height": 1},
                                                          "pageIndex": 0}]}}
        u = make_response("doc-a", "understand", FULL_DATA, broken_meta)
        a = make_response("doc-a", "agentic", dict(FULL_DATA))
        report = gates.run_gates(
            ["doc-a"], understand={"doc-a": u}, agentic={"doc-a": a},
            vision_answers={}, ledger_sha256="x", artifact_digest="y",
        )
        (f,) = findings(report, "gate_error")
        assert f["blocking"] and f["doc_id"] == "doc-a"
        assert all(v == "unavailable"
                   for v in verdicts(report, "invoice_number").values())
