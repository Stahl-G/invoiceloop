"""Tests for VisionReaderAgent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from invoiceloop.agents.runtime import AgentCallRecorder
from invoiceloop.agents.vision import VisionReaderAgent


def test_vision_reader_agent_offline_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")

    recorder = AgentCallRecorder(tmp_path)
    call_id = "vision_acme-001_total_gross"
    recorder.record(
        call_id,
        {
            "output_text": '{"suggested_value": "150.00", "confidence": "high", "explanation": "Visible in top right"}',
            "output_json": {"suggested_value": "150.00", "confidence": "high", "explanation": "Visible in top right"},
            "model": "gemini-2.5-flash",
        },
    )

    agent = VisionReaderAgent(tmp_path)
    res = agent.inspect_slot("acme-001", "total_gross", limitation_code="OCR_UNAVAILABLE")

    assert res["doc_id"] == "acme-001"
    assert res["suggested_value"] == "150.00"
    assert res["confidence"] == "high"
    assert res["replayed"] is True
