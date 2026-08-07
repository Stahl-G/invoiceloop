"""改进循环的写入边界与降级行为。

流水线是否真的被 ADK Runner 执行,见 `test_agents_adk_pipeline.py`。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop.agents.improve_loop import cohort_key, run_improve_loop
from invoiceloop.agents.runtime import ReplayRecordingMissing
from tests.test_agents_adk_pipeline import ScriptedLlm, _script, _workspace


class TestWriteBoundary:
    """两个生产者不许写同一个文件。"""

    def test_does_not_touch_suggestions_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        ws = _workspace(tmp_path)

        existing = {"advisory": True, "suggestions": [{"field": "test"}]}
        sug = ws / "improve" / "suggestions.json"
        sug.write_text(json.dumps(existing), encoding="utf-8")

        run_improve_loop(ws, model=ScriptedLlm(model="scripted", script=_script()))

        assert json.loads(sug.read_text(encoding="utf-8")) == existing

        report = json.loads(
            (ws / "improve" / "adk_loop_report.json").read_text(encoding="utf-8")
        )
        assert report["advisory"] is True
        assert "promote" not in json.dumps(report).lower().replace(
            "gate 2 and a human signature decide promotion", ""
        )


class TestFailLoud:
    def test_replay_without_a_recording_raises_instead_of_fabricating(
        self, tmp_path, monkeypatch
    ):
        """宪章四:缺录音是阻断,不是「就当模型说了这个」。"""
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        ws = _workspace(tmp_path)

        with pytest.raises(ReplayRecordingMissing):
            run_improve_loop(ws, model=ScriptedLlm(model="scripted", script=_script()))


class TestCohortKey:
    def test_key_is_order_independent(self):
        assert cohort_key({"field": "a", "tier": "T1"}) == cohort_key(
            {"tier": "T1", "field": "a"}
        )

    def test_same_field_different_tier_are_different_keys(self):
        assert cohort_key({"field": "a", "tier": "T1"}) != cohort_key(
            {"field": "a", "tier": "T2"}
        )
