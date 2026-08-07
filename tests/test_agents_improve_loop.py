"""Tests for Gemini Multi-Agent Improve Loop.

Tests verify:
- Miner reads mine_report.json correctly
- Proposer generates well-formed proposals
- Critic uses structured output (CriticVerdict), NOT hardcoded field rules
- Full loop writes to adk_loop_report.json (NOT suggestions.json)
- Replay-driven critic test with counterfactual evidence
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from invoiceloop.agents.improve_loop import (
    CriticAgent,
    CriticVerdict,
    MinerAgent,
    ProposerAgent,
    run_improve_loop,
)
from invoiceloop.agents.runtime import AgentCallRecorder, ReplayRecordingMissing


def _mine_report(tmp_path: Path, candidates=None):
    """Helper: write a minimal mine_report.json."""
    report = {
        "cohorts": [],
        "buckets": {"zero_corrections": 5},
        "low_yield_candidates": candidates or [],
    }
    (tmp_path / "improve").mkdir(exist_ok=True)
    (tmp_path / "improve" / "mine_report.json").write_text(
        json.dumps(report), encoding="utf-8")
    return report


class TestMinerAgent:
    def test_miner_with_report(self, tmp_path):
        _mine_report(tmp_path, [{"field": "total_vat", "tier": "TIER1",
                                  "support_strength": "unsupported", "reviewed": 9}])
        miner = MinerAgent(tmp_path)
        out = miner.run()
        assert len(out["candidates"]) == 1

    def test_miner_empty(self, tmp_path):
        miner = MinerAgent(tmp_path)
        out = miner.run()
        assert out["candidates"] == []


class TestProposerAgent:
    def test_proposer_generates_proposals(self, tmp_path):
        proposer = ProposerAgent(tmp_path)
        out = proposer.run({"candidates": [
            {"field": "total_vat", "tier": "TIER1", "reviewed": 9},
        ]})
        assert len(out) == 1
        assert out[0]["action"] == "auto_accept"
        assert out[0]["cohort"]["field"] == "total_vat"


class TestCriticAgent:
    """Critic tests use replay recordings — no hardcoded field rules."""

    def test_critic_rejects_risky_counterfactual(self, tmp_path, monkeypatch):
        """Critic given 'saves 37 slots / loses 5 silent errors' → accepted=False.

        This replaces the old test_critic_agent_rejects_due_date_cohort which
        was testing a hardcoded `if field == "due_date"` branch. The new test
        verifies the critic's reaction to NUMBERS, not to field names.
        """
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")

        # Plant a recording with a rejection verdict
        recorder = AgentCallRecorder(tmp_path)
        verdict = CriticVerdict(
            accepted=False,
            risk="HIGH",
            reason="Saves 37 review slots but introduces 5 silent absence errors "
                   "on documents where the field has genuine values.",
            values_at_risk=["due_date on 5 documents"],
        )
        recorder.record("critic_due_date", {
            "output_text": verdict.model_dump_json(),
            "output_json": verdict.model_dump(),
            "model": "gemini-3.6-flash",
        })

        critic = CriticAgent(tmp_path)
        result = critic.evaluate_proposal(
            proposal={
                "action": "auto_accept",
                "cohort": {"field": "due_date", "tier": "TIER2"},
            },
            counterfactual={
                "slots_saved": 37,
                "silent_errors_introduced": 5,
                "fields_at_risk": ["due_date"],
            },
        )
        assert result["accepted"] is False
        assert result["risk_score"] == "HIGH"
        assert len(result["values_at_risk"]) > 0

    def test_critic_accepts_safe_proposal(self, tmp_path, monkeypatch):
        """Critic given safe counterfactual → accepted=True."""
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")

        recorder = AgentCallRecorder(tmp_path)
        verdict = CriticVerdict(
            accepted=True,
            risk="LOW",
            reason="Saves 12 review slots with 0 silent errors.",
            values_at_risk=[],
        )
        recorder.record("critic_total_vat", {
            "output_text": verdict.model_dump_json(),
            "output_json": verdict.model_dump(),
            "model": "gemini-3.6-flash",
        })

        critic = CriticAgent(tmp_path)
        result = critic.evaluate_proposal(
            proposal={
                "action": "auto_accept",
                "cohort": {"field": "total_vat", "tier": "TIER1"},
            },
            counterfactual={
                "slots_saved": 12,
                "silent_errors_introduced": 0,
                "fields_at_risk": [],
            },
        )
        assert result["accepted"] is True
        assert result["risk_score"] == "LOW"

    def test_critic_raises_without_recording(self, tmp_path, monkeypatch):
        """Critic in replay without recording → ReplayRecordingMissing, not fake data."""
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")

        critic = CriticAgent(tmp_path)
        with pytest.raises(ReplayRecordingMissing):
            critic.evaluate_proposal(
                proposal={
                    "action": "auto_accept",
                    "cohort": {"field": "seller_name", "tier": "TIER1"},
                },
            )


class TestCriticVerdict:
    """CriticVerdict schema is well-formed and validates correctly."""

    def test_verdict_round_trip(self):
        v = CriticVerdict(
            accepted=False, risk="HIGH",
            reason="test", values_at_risk=["a", "b"],
        )
        rebuilt = CriticVerdict.model_validate_json(v.model_dump_json())
        assert rebuilt.accepted is False
        assert rebuilt.risk == "HIGH"

    def test_verdict_rejects_invalid_risk(self):
        """Risk must be LOW/MEDIUM/HIGH."""
        with pytest.raises(Exception):
            CriticVerdict(
                accepted=True, risk="EXTREME",
                reason="test", values_at_risk=[],
            )


class TestOutputFile:
    """The loop writes to adk_loop_report.json, NOT suggestions.json."""

    def test_does_not_touch_suggestions_json(self, tmp_path, monkeypatch):
        """R5: running the improve loop must not overwrite suggestions.json."""
        monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")

        # Pre-populate suggestions.json with existing content
        improve_dir = tmp_path / "improve"
        improve_dir.mkdir(parents=True)
        existing = {"advisory": True, "suggestions": [{"field": "test"}]}
        sug_path = improve_dir / "suggestions.json"
        sug_path.write_text(json.dumps(existing), encoding="utf-8")

        # Write mine_report with no candidates → loop runs but produces nothing
        (improve_dir / "mine_report.json").write_text(
            json.dumps({"cohorts": [], "buckets": {}, "low_yield_candidates": []}),
            encoding="utf-8",
        )

        run_improve_loop(tmp_path)

        # suggestions.json must be UNCHANGED
        after = json.loads(sug_path.read_text(encoding="utf-8"))
        assert after == existing

        # adk_loop_report.json should exist instead
        report_path = improve_dir / "adk_loop_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["advisory"] is True
        assert report["source"] == "Gemini_Multi_Agent_Improve_Loop"
