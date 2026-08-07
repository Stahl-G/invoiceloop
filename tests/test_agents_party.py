"""Tests for PartyIdentificationAgent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from invoiceloop.agents.party import PartyIdentificationAgent
from invoiceloop.agents.runtime import AgentCallRecorder


def test_party_identification_agent_offline_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")

    recorder = AgentCallRecorder(tmp_path)
    call_id = "party_acme-001"
    recorder.record(
        call_id,
        {
            "output_text": '{"seller_name": "WARU-AM", "is_agency": true, "confidence": "high"}',
            "output_json": {"seller_name": "WARU-AM", "is_agency": True, "confidence": "high"},
            "model": "gemini-2.5-flash",
        },
    )

    agent = PartyIdentificationAgent(tmp_path)
    res = agent.identify_seller("acme-001", candidate_seller="Regional Reps")

    assert res["doc_id"] == "acme-001"
    assert res["value"] == "WARU-AM"
    assert res["is_agency_flagged"] is True
    assert res["replayed"] is True
