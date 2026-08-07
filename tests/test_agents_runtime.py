"""Tests for ADK Agent Runtime and Replay Harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from invoiceloop.agents import AgentCallRecorder, call_gemini_model, is_replay_mode


def test_replay_mode_defaults_to_true_in_tests(monkeypatch):
    """In test environment with INVOICELOOP_NO_DOTENV set, is_replay_mode is True."""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    assert is_replay_mode() is True


def test_agent_call_recorder_record_and_load(tmp_path):
    recorder = AgentCallRecorder(tmp_path)
    call_id = "test_call_001"
    data = {"prompt": "hello", "output_text": "world", "model": "gemini-2.5-flash"}

    saved_path = recorder.record(call_id, data)
    assert saved_path.exists()

    loaded = recorder.load(call_id)
    assert loaded is not None
    assert loaded["output_text"] == "world"


def test_call_gemini_model_uses_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")

    recorder = AgentCallRecorder(tmp_path)
    call_id = "gemini_mock_001"
    recorder.record(
        call_id,
        {
            "output_text": '{"status": "ok", "recommendation": "accept"}',
            "output_json": {"status": "ok", "recommendation": "accept"},
            "model": "gemini-2.5-flash",
        },
    )

    res = call_gemini_model(
        prompt="Analyze due_date cohort",
        workspace=tmp_path,
        call_id=call_id,
    )
    assert res["replayed"] is True
    assert res["json"] == {"status": "ok", "recommendation": "accept"}
