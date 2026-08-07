"""Tests for Gemini GenAI SDK Agent Runtime and Replay Harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from invoiceloop.agents.runtime import (
    AgentCallRecorder,
    ReplayRecordingMissing,
    GeminiCredentialMissing,
    call_gemini_model,
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


class TestCallGeminiModel:
    def test_replay_with_recording(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        rec = AgentCallRecorder(tmp_path)
        rec.record("gemini_test123", {
            "output_text": "test response",
            "output_json": {"key": "value"},
            "model": "gemini-3.6-flash",
        })
        result = call_gemini_model(
            prompt="test", workspace=tmp_path, call_id="gemini_test123"
        )
        assert result["replayed"] is True
        assert result["text"] == "test response"
        assert result["json"] == {"key": "value"}

    def test_replay_raises_on_missing_recording(self, tmp_path, monkeypatch):
        """Replay + no recording → ReplayRecordingMissing, NOT a fake stub (R4)."""
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        with pytest.raises(ReplayRecordingMissing) as exc_info:
            call_gemini_model(
                prompt="test", workspace=tmp_path, call_id="missing_recording"
            )
        assert "missing_recording" in str(exc_info.value)

    def test_no_key_and_not_replay_raises(self, tmp_path, monkeypatch):
        """No API key + not in replay → GeminiCredentialMissing (R4)."""
        monkeypatch.delenv("INVOICELOOP_REPLAY", raising=False)
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with pytest.raises((GeminiCredentialMissing, ImportError)):
            call_gemini_model(
                prompt="test", workspace=tmp_path, call_id="test_no_key"
            )


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
