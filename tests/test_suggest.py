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


class TestProvenance:
    """工件必须如实记录**真正被调用的**模型 —— 顾问层的溯源就靠这一行。"""

    def _ws(self, tmp_path):
        (tmp_path / "improve").mkdir()
        (tmp_path / "improve" / "mine_report.json").write_text(json.dumps({
            "cohorts": [{"field": "seller_vat_id", "tier": "TIER1",
                         "support_strength": "unsupported", "route": "review",
                         "reviewed": 3, "accepted": 0, "corrected": 0,
                         "rejected": 0, "confirmed_absent": 3,
                         "notes": [NOTES[0]]}]}), encoding="utf-8")
        return tmp_path

    def test_recorded_model_is_the_one_actually_called(self, tmp_path,
                                                       monkeypatch):
        """回归:调用走 INVOICELOOP_SUGGEST_MODEL,记录却写 default_model ——
        实测产出的 suggestions.json 标着 deepseek,真正调的是 mimo。"""
        ws = self._ws(tmp_path)
        monkeypatch.setattr("invoiceloop.vision_ingest._credentials",
                            lambda: ("k", "https://x", "default-model"))
        monkeypatch.setenv("INVOICELOOP_SUGGEST_MODEL", "actually-called")
        seen = {}

        def fake_ask(packet, *, key, base_url, model):
            seen["model"] = model
            return {"suggestions": []}

        monkeypatch.setattr(suggest, "_ask", fake_ask)
        out = suggest.suggest(ws)
        assert seen["model"] == "actually-called"
        assert out["model"] == seen["model"], \
            "记录的模型必须就是被调用的那个,不许各算各的"


class TestBudget:
    def test_budget_is_env_overridable_with_a_floor(self, monkeypatch):
        monkeypatch.delenv("INVOICELOOP_SUGGEST_MAX_TOKENS", raising=False)
        assert suggest._budget() == suggest._MAX_TOKENS
        monkeypatch.setenv("INVOICELOOP_SUGGEST_MAX_TOKENS", "50000")
        assert suggest._budget() == 50000
        monkeypatch.setenv("INVOICELOOP_SUGGEST_MAX_TOKENS", "10")
        assert suggest._budget() == 1024, "地板价:给太小等于必然截断"
        monkeypatch.setenv("INVOICELOOP_SUGGEST_MAX_TOKENS", "不是数字")
        assert suggest._budget() == suggest._MAX_TOKENS, "手滑不许把调用打崩"


class TestPerActionCohortShape:
    """回归:absent_expected 是字段级规则,给它配 tier/strength 会被下游拒。

    实测(2026-08-06,用户在工作台点「采纳」时命中):模型给
    absent_expected 配了 tier=TIER1 strength=unsupported,校验层放行,
    improve.lint_policy 拒绝 —— 草稿在构造上就不可能被采纳。
    """

    def _absent(self, cohort) -> dict:
        return {"suggestions": [{
            "action": "absent_expected", "cohort": cohort,
            "finding": "f", "prediction": "p", "confidence": "high",
            "cites": [0]}]}

    def test_tier_and_strength_are_trimmed_not_thrown_away(self):
        kept, dropped = suggest.validate(
            self._absent({"field": "total_vat", "tier": "TIER1",
                          "strength": "unsupported"}), NOTES)
        assert kept, "有出处的建议不该因为多写两个键就被整条扔掉"
        assert kept[0]["cohort"] == {"field": "total_vat"}
        assert dropped and "已剪掉" in dropped[0], "剪了什么要说出来"

    def test_trimmed_cohort_passes_the_downstream_linter(self):
        """校验层放行的东西,improve 的 linter 必须也认 —— 这是本回归的要点。"""
        from invoiceloop.improve import lint_policy

        kept, _ = suggest.validate(
            self._absent({"field": "total_vat", "tier": "TIER1",
                          "strength": "unsupported"}), NOTES)
        parent = {"absent_expected_cohorts": []}
        candidate = {"absent_expected_cohorts": [
            {"id": "AC-X", **kept[0]["cohort"]}]}
        assert lint_policy(parent, candidate) == []

    def test_auto_accept_keeps_tier_and_strength(self):
        kept, dropped = suggest.validate({"suggestions": [{
            "action": "auto_accept",
            "cohort": {"field": "total_gross", "tier": "TIER1",
                       "strength": "corroborated"},
            "finding": "f", "prediction": "p", "confidence": "high",
            "cites": [0]}]}, NOTES)
        assert dropped == [] and kept[0]["cohort"]["tier"] == "TIER1"

    def test_doc_id_is_dropped_whole_never_trimmed(self):
        """单文档特征必须整条丢弃 —— 剪掉再放行等于绕过反硬编码纪律。"""
        kept, dropped = suggest.validate(
            self._absent({"field": "total_vat", "doc_id": "d1"}), NOTES)
        assert kept == [], "不许把 doc_id 剪掉然后把建议留下"
        assert "非白名单键" in dropped[0]


class TestReadableRefusals:
    """报错是给人看的,不是 Python repr 的转储。"""

    def test_key_lists_are_not_python_reprs(self):
        from invoiceloop.improve import lint_policy

        v = lint_policy({"absent_expected_cohorts": []},
                        {"absent_expected_cohorts": [
                            {"id": "X", "field": "total_vat",
                             "tier": "TIER1", "strength": "unsupported"}]})
        assert v and "['" not in v[0] and "('" not in v[0], \
            f"报错里不许出现 list/tuple 字面量:{v[0]!r}"
        assert "strength、tier" in v[0]

    def test_refusal_text_reads_as_a_sentence(self):
        from invoiceloop.improve import refusal_text

        one = refusal_text(["字段不对"])
        assert one == "这个候选没能通过审查:字段不对"
        many = refusal_text(["A", "B"], subject="这个字段描述改动")
        assert "有 2 处" in many and "· A" in many and "['" not in many
