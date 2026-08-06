"""suggest 顾问层:模型只写草稿,校验层挡住越界的建议。

这里全部是纯函数测试 —— validate 不碰网络,所以模型说什么都能钉死。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import suggest

NOTES = [
    {"doc_id": "d1", "field": "seller_vat_id", "decision": "confirm_absent",
     "reason_code": "CONFIRMED_ABSENT", "rationale": "页面上没有"},
    {"doc_id": "d2", "field": "total_gross", "decision": "reject",
     "reason_code": "WRONG_FIELD_MAPPING", "rationale": "Fed. I.D. 不是 VAT"},
]


def _raw(**over) -> dict:
    s = {"action": "absent_expected", "cohort": {"field": "seller_vat_id"},
         "finding": "f", "prediction": "p", "confidence": "medium",
         "cites": [0]}
    s.update(over)
    return {"suggestions": [s]}


class TestValidate:
    def test_legal_suggestion_survives_with_its_notes(self):
        kept, dropped = suggest.validate(_raw(), NOTES)
        assert dropped == []
        assert kept[0]["action"] == "absent_expected"
        assert kept[0]["cited_notes"] == [NOTES[0]], \
            "被引用的原话要跟着建议走 —— 人是读这个来判断的"

    def test_unknown_action_dropped(self):
        kept, dropped = suggest.validate(_raw(action="delete_gate"), NOTES)
        assert kept == [] and "不在词表" in dropped[0]

    def test_doc_id_in_cohort_dropped(self):
        """单文档特征进策略 = routing 的 cohort 白名单被绕过。"""
        kept, dropped = suggest.validate(
            _raw(cohort={"field": "total_gross", "doc_id": "d2"}), NOTES)
        assert kept == [] and "非白名单键" in dropped[0]

    def test_expected_value_hardcoding_dropped(self):
        kept, dropped = suggest.validate(
            _raw(cohort={"field": "total_gross", "value": "100.00"}), NOTES)
        assert kept == []

    def test_uncited_suggestion_dropped(self):
        kept, dropped = suggest.validate(_raw(cites=[]), NOTES)
        assert kept == [] and "没出处" in dropped[0]

    def test_out_of_range_citation_dropped(self):
        """模型编一个不存在的笔记号 —— 越界即丢,不四舍五入。"""
        kept, dropped = suggest.validate(_raw(cites=[99]), NOTES)
        assert kept == []

    def test_bogus_confidence_falls_back_to_low(self):
        kept, _ = suggest.validate(_raw(confidence="certain"), NOTES)
        assert kept[0]["confidence"] == "low"


class TestSchemaSuggestions:
    """schema_description:模型能提改字段描述,但约束比 cohort 更紧。"""

    def _schema_raw(self, **over) -> dict:
        s = {"action": "schema_description", "field": "due_date",
             "description": "Payment due date, or the date implied by stated "
                            "terms such as Net 30.",
             "finding": "f", "prediction": "p", "confidence": "medium",
             "cites": [1]}
        s.update(over)
        return {"suggestions": [s]}

    def test_schema_suggestion_survives(self):
        kept, dropped = suggest.validate(self._schema_raw(), NOTES)
        assert dropped == []
        assert kept[0]["kind"] == "schema" and kept[0]["field"] == "due_date"
        assert "Net 30" in kept[0]["description"]

    def test_unknown_field_dropped(self):
        """模型编一个字段名 —— schema 只有那十个受评字段。"""
        kept, dropped = suggest.validate(
            self._schema_raw(field="vendor_iban"), NOTES)
        assert kept == [] and "不是受评字段" in dropped[0]

    def test_empty_description_dropped(self):
        kept, dropped = suggest.validate(self._schema_raw(description="  "),
                                         NOTES)
        assert kept == [] and "没给 description" in dropped[0]

    def test_essay_length_description_dropped(self):
        kept, dropped = suggest.validate(
            self._schema_raw(description="x" * 401), NOTES)
        assert kept == [] and "小作文" in dropped[0]

    def test_schema_suggestion_still_needs_a_citation(self):
        """出处这条纪律对两类建议一视同仁。"""
        kept, dropped = suggest.validate(self._schema_raw(cites=[]), NOTES)
        assert kept == [] and "没出处" in dropped[0]

    def test_cohort_suggestion_is_tagged_as_cohort(self):
        kept, _ = suggest.validate(_raw(), NOTES)
        assert kept[0]["kind"] == "cohort", "页面按 kind 分支渲染两种形状"


class TestSuggestIO:
    def test_missing_mine_report_blocks(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="improve mine"):
            suggest.suggest(tmp_path)

    def test_no_notes_writes_an_honest_empty(self, tmp_path):
        (tmp_path / "improve").mkdir()
        (tmp_path / "improve" / "mine_report.json").write_text(
            json.dumps({"cohorts": []}), encoding="utf-8")
        out = suggest.suggest(tmp_path)
        assert out["suggestions"] == [] and out["note_count"] == 0
        assert "不编" in out["reason"]
        written = json.loads(
            (tmp_path / "improve" / "suggestions.json").read_text("utf-8"))
        assert written["advisory"] is True

    def test_missing_key_raises_not_silently_empty(self, tmp_path, monkeypatch):
        """宪章四:跑不了要说,不要压成一个空结果。"""
        monkeypatch.setattr(suggest, "_write", lambda *a, **k: None)
        monkeypatch.setattr("invoiceloop.vision_ingest._credentials",
                            lambda: (None, "https://x", "m"))
        (tmp_path / "improve").mkdir()
        (tmp_path / "improve" / "mine_report.json").write_text(json.dumps({
            "cohorts": [{"field": "seller_vat_id", "tier": "TIER1",
                         "support_strength": "unsupported", "route": "review",
                         "reviewed": 3, "accepted": 0, "corrected": 0,
                         "rejected": 0, "confirmed_absent": 3,
                         "notes": [NOTES[0]]}]}), encoding="utf-8")
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            suggest.suggest(tmp_path)


class TestPacket:
    def test_overturns_are_listed_first_and_citable(self):
        report = {
            "cohorts": [{"field": "a", "tier": "TIER1",
                         "support_strength": "corroborated", "route": "review",
                         "reviewed": 1, "accepted": 1, "corrected": 0,
                         "rejected": 0, "confirmed_absent": 0, "notes": []}],
            "overturned_auto_accepts": [
                {"field": "seller_vat_id", "doc_id": "d9", "route": "auto_accept",
                 "human_action": "reject", "reason_code": "WRONG_FIELD_MAPPING",
                 "rationale": "EIN 不是 VAT", "random_qa": True,
                 "harness_id": "HAR-0003"}],
        }
        text, notes = suggest._packet(report)
        assert "收紧信号,优先看" in text
        assert any(n["rationale"] == "EIN 不是 VAT" for n in notes), \
            "推翻的原话也要可引用 —— 它是最该被读到的一条"
