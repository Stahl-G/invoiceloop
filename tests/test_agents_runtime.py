"""运行时与录放。

`call_gemini_model`(非结构化)已删除:它会吞掉 JSON 解析错误,
机器消费的结果不许走那条路。只剩 `call_gemini_structured` 一条。
ADK 流水线的录放走 `adk_replay`,按请求摘要绑定,测试在
`test_agents_adk_pipeline.py`。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ADK/GenAI 是可选依赖(`pip install -e ".[gemini]"`)。没装就跳过,
# 不要让整个 tests/ 收集不起来 —— 干净 clone 必须能跑通测试。
pytest.importorskip("google.adk", reason="需要 invoiceloop[gemini]")
from invoiceloop.agents.runtime import (
    AgentCallRecorder,
    ReplayRecordingMissing,
    GeminiCredentialMissing,
    call_gemini_structured,
    is_replay_mode,
)


class TestIsReplayMode:
    """is_replay_mode checks ONLY the explicit INVOICELOOP_REPLAY flag."""

    def test_explicit_replay_env(self, monkeypatch):
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        assert is_replay_mode() is True

    def test_explicit_replay_true_string(self, monkeypatch):
        monkeypatch.setenv("INVOICELOOP_REPLAY", "true")
        assert is_replay_mode() is True

    def test_no_env_means_not_replay(self, monkeypatch):
        monkeypatch.delenv("INVOICELOOP_REPLAY", raising=False)
        assert is_replay_mode() is False

    def test_no_dotenv_is_not_replay(self, monkeypatch):
        """INVOICELOOP_NO_DOTENV disables file loading, NOT a replay flag."""
        monkeypatch.delenv("INVOICELOOP_REPLAY", raising=False)
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        assert is_replay_mode() is False


class TestAgentCallRecorder:
    def test_record_and_load(self, tmp_path):
        rec = AgentCallRecorder(tmp_path)
        rec.record("test_123", {"prompt": "hello", "output_text": "world"})
        loaded = rec.load("test_123")
        assert loaded is not None
        assert loaded["output_text"] == "world"

    def test_load_missing(self, tmp_path):
        rec = AgentCallRecorder(tmp_path)
        assert rec.load("nonexistent") is None

    def test_record_dir_is_agent_calls(self, tmp_path):
        """Recordings go to agent_calls/, NOT raw/ (R7)."""
        rec = AgentCallRecorder(tmp_path)
        d = rec.record_dir()
        assert d.exists()
        assert d == tmp_path / "agent_calls"
        # Verify raw/ was NOT created
        assert not (tmp_path / "raw" / "agents").exists()


class TestCallGeminiStructured:
    def test_replay_with_structured_recording(self, tmp_path, monkeypatch):
        """Structured call in replay mode validates against schema."""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            status: str
            score: int

        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        rec = AgentCallRecorder(tmp_path)
        rec.record("struct_test", {
            "output_text": '{"status": "ok", "score": 42}',
            "output_json": {"status": "ok", "score": 42},
            "model": "gemini-3.6-flash",
        })
        result = call_gemini_structured(
            prompt="test", schema=TestSchema,
            workspace=tmp_path, call_id="struct_test",
        )
        assert result["replayed"] is True
        assert result["parsed"].status == "ok"
        assert result["parsed"].score == 42

    def test_replay_raises_on_missing(self, tmp_path, monkeypatch):
        from pydantic import BaseModel

        class Dummy(BaseModel):
            x: int

        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        with pytest.raises(ReplayRecordingMissing):
            call_gemini_structured(
                prompt="test", schema=Dummy,
                workspace=tmp_path, call_id="missing",
            )


class TestPreferHttpxThroughProxy:
    def test_disables_aiohttp_when_https_proxy_set(self, monkeypatch):
        from google.genai import _api_client as ac
        from invoiceloop.agents.runtime import prefer_httpx_through_proxy

        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
        ac.has_aiohttp = True
        prefer_httpx_through_proxy()
        assert ac.has_aiohttp is False

    def test_leaves_aiohttp_when_no_proxy(self, monkeypatch):
        from google.genai import _api_client as ac
        from invoiceloop.agents.runtime import prefer_httpx_through_proxy

        for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            monkeypatch.delenv(key, raising=False)
        ac.has_aiohttp = True
        prefer_httpx_through_proxy()
        assert ac.has_aiohttp is True
