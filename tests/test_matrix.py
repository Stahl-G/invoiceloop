"""支持矩阵:四维、强度按层级数、口径争议运行时判据、分诊排序。"""

from __future__ import annotations

from invoiceloop import matrix
from tests.conftest import make_response


def _claims(doc, field, spans=(), by="dws_understand", value="100.00"):
    return [{"claim_id": "FC-0001", "doc_id": doc, "field": field, "value": value,
             "span_ids": list(spans), "drafted_by": by, "binding_coverage": 1.0}]


def _gates(verdicts):
    return {"findings": [], "evaluations": {"doc-a": {f: dict(verdicts) for f in
            ("invoice_number", "issue_date", "due_date", "seller_name", "buyer_name",
             "seller_vat_id", "total_net", "total_vat", "total_gross", "amount_due")}}}


class TestApplicability:
    DISPUTED = {"total_net": "8,500.00", "total_gross": "10,000.00", "amount_due": "8,500.00"}

    def test_criterion_hits(self):
        assert matrix.label_convention_disputed(self.DISPUTED)

    def test_criterion_misses_when_due_is_gross(self):
        assert not matrix.label_convention_disputed(
            {**self.DISPUTED, "amount_due": "10,000.00"})

    def test_criterion_misses_when_gross_equals_net(self):
        assert not matrix.label_convention_disputed(
            {"total_net": "100", "total_gross": "100", "amount_due": "100"})

    def test_criterion_misses_when_values_missing(self):
        assert not matrix.label_convention_disputed({"total_net": "100"})

    def test_disputed_rows_marked_and_queued_not_errored(self):
        u = make_response("doc-a", "understand", self.DISPUTED)
        claims = [
            {"claim_id": f"FC-000{i}", "doc_id": "doc-a", "field": f,
             "value": self.DISPUTED[f], "span_ids": [], "drafted_by": "dws_understand",
             "binding_coverage": 1.0}
            for i, f in enumerate(("total_net", "total_gross", "amount_due"), 1)
        ]
        report = _gates({})
        out, _routing = matrix.build_matrix(["doc-a"], understand={"doc-a": u}, claims=claims,
                                  rejections=[], gate_report=report, vision_answers={})
        disputed = [r for r in out["rows"] if r["applicability"] == "label_convention_disputed"]
        assert {r["field"] for r in disputed} == {"total_net", "total_gross", "amount_due"}
        assert all(r["requires_adjudication"] for r in disputed)
        assert out["summary"]["applicability_disputed"] == 3
        # 宪章五:争议进人工裁决,summary 里没有任何"错误率"计数它
        assert "errors" not in out["summary"]

    def test_dispute_requires_admitted_values(self):
        """判据收紧:三个值都冻结被拒的文档不标争议 —— 争议要落在绑得上的证据上。"""
        u = make_response("doc-a", "understand", self.DISPUTED)
        out, _routing = matrix.build_matrix(["doc-a"], understand={"doc-a": u}, claims=[],
                                  rejections=[], gate_report=_gates({}), vision_answers={})
        assert all(r["applicability"] == "matches" for r in out["rows"])


class TestBlockingAttachment:
    def test_doc_level_blocking_attaches_to_every_row(self):
        """文档级阻断(如 agentic 缺失)属于这份文档的每一行,不是只挂在某处。"""
        u = make_response("doc-a", "understand", {"total_gross": "100.00"})
        blocking_finding = {
            "finding_id": "GF-0001", "gate_id": "cross_mode_agreement",
            "doc_id": "doc-a", "field": None, "severity": "high",
            "blocking_level": "blocking", "blocking": True,
            "repair_owner": "re_extract", "recommendation": "重跑",
            "evidence_ref": "raw/x", "message": "agentic 不可用",
        }
        report = {"findings": [blocking_finding], "evaluations": _gates({})["evaluations"]}
        out, _routing = matrix.build_matrix(["doc-a"], understand={"doc-a": u},
                                  claims=_claims("doc-a", "total_gross"),
                                  rejections=[], gate_report=report, vision_answers={})
        assert all("GF-0001" in r["blocking_findings"] for r in out["rows"])
        assert all(r["requires_adjudication"] for r in out["rows"])


class TestStrength:
    def _build(self, claims, verdicts, rejections=(), data=None):
        u = make_response("doc-a", "understand", data or {"total_gross": "100.00"})
        out, _routing = matrix.build_matrix(["doc-a"], understand={"doc-a": u}, claims=claims,
                                  rejections=list(rejections), gate_report=_gates(verdicts),
                                  vision_answers={})
        return next(r for r in out["rows"] if r["field"] == "total_gross")

    def test_corroborated_needs_two_independent_tiers(self):
        row = self._build(
            _claims("doc-a", "total_gross", spans=["ES-0001"]),
            {"arithmetic_consistency": "pass"},
        )
        assert row["support_strength"] == "corroborated"
        assert set(row["source_tiers"]) == {"dws_extraction", "independent_ocr", "arithmetic"}

    def test_dws_plus_span_ocr_is_corroborated(self):
        # 值落在引用区 = 独立 OCR 这一层在支持它,和 DWS 抽取合起来就是两层
        row = self._build(_claims("doc-a", "total_gross", spans=["ES-0001"]), {})
        assert row["support_strength"] == "corroborated"
        assert set(row["source_tiers"]) == {"dws_extraction", "independent_ocr"}

    def test_admitted_outside_any_span_is_single_source_not_rejected(self):
        row = self._build(_claims("doc-a", "total_gross"), {})
        assert row["support_strength"] == "single_source"
        assert "value_not_in_cited_span" in row["limitations"]

    def test_no_claim_is_unsupported(self):
        row = self._build([], {"extraction_present": "fail"},
                          data={"total_gross": None})
        assert row["support_strength"] == "unsupported"
        assert row["requires_adjudication"]

    def test_rejected_draft_is_unsupported_and_visible(self):
        row = self._build([], {"extraction_present": "pass"},
                          rejections=[{"reason": "binding", "doc_id": "doc-a",
                                       "field": "total_gross", "value": "9,999.00",
                                       "drafted_by": "dws_understand", "coverage": 0.0}])
        assert row["support_strength"] == "unsupported"
        assert "draft_rejected_at_freeze" in row["limitations"]
        assert row["rejections"][0]["value"] == "9,999.00"

    def test_cited_spans_follow_the_field_not_the_claim(self):
        """DWS 指向的片段按 (doc, field) 归行 —— 与值是否落在里面无关。

        被拒的行没有声明,但复核者要看"DWS 指的地方 OCR 说了什么"(T1 实测)。
        """
        u = make_response("doc-a", "understand", {"total_gross": "9,999.00"})
        spans = [{"span_id": "ES-0007", "doc_id": "doc-a", "field": "total_gross",
                  "ocr_text": "100.00"}]
        out, _routing = matrix.build_matrix(
            ["doc-a"], understand={"doc-a": u}, claims=[],
            rejections=[{"reason": "binding", "doc_id": "doc-a", "field": "total_gross",
                         "value": "9,999.00", "drafted_by": "dws_understand", "coverage": 0.0}],
            gate_report=_gates({}), vision_answers={}, spans=spans)
        row = next(r for r in out["rows"] if r["field"] == "total_gross")
        assert row["span_ids"] == []           # 值没落在任何片段(所以被拒)
        assert row["cited_span_ids"] == ["ES-0007"]  # 但 DWS 指的位置仍在行上

    def test_vision_offer_surfaced_when_dws_value_absent(self):
        claims = _claims("doc-a", "total_gross", by="vision:Opus 5")
        row = self._build(claims, {"extraction_present": "fail"},
                          data={"total_gross": None})
        assert any(x.startswith("vision_offers:Opus 5=") for x in row["limitations"])


class TestTriage:
    def test_rows_sorted_unsupported_first(self):
        u = make_response("doc-a", "understand", {"total_gross": "100.00"})
        claims = _claims("doc-a", "total_gross", spans=["ES-0001"])
        verdicts = {"arithmetic_consistency": "pass"}
        out, _routing = matrix.build_matrix(["doc-a"], understand={"doc-a": u}, claims=claims,
                                  rejections=[], gate_report=_gates(verdicts), vision_answers={})
        ranks = [{"unsupported": 0, "single_source": 1, "corroborated": 2}[r["support_strength"]]
                 for r in out["rows"]]
        assert ranks == sorted(ranks)
