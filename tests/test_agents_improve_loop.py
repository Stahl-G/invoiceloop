"""Tests for ADK Multi-Agent Improve Loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from invoiceloop.agents.improve_loop import (
    CriticAgent,
    MinerAgent,
    ProposerAgent,
    run_adk_improve_loop,
)


def test_critic_agent_rejects_due_date_cohort(tmp_path):
    critic = CriticAgent(tmp_path)
    proposal = {
        "action": "auto_accept",
        "cohort": {"field": "due_date", "tier": "TIER2", "strength": "corroborated"},
        "finding": "Reviewed 37 times with 0 corrections",
    }
    res = critic.evaluate_proposal(proposal)
    assert res["accepted"] is False
    assert "due_date" in res["reason"]
    assert res["risk_score"] == "HIGH"


def test_proposer_agent_formulates_proposals(tmp_path):
    proposer = ProposerAgent(tmp_path)
    miner_out = {
        "candidates": [
            {"field": "seller_vat_id", "tier": "TIER1", "support_strength": "corroborated", "reviewed": 5}
        ]
    }
    proposals = proposer.run(miner_out)
    assert len(proposals) == 1
    assert proposals[0]["cohort"]["field"] == "seller_vat_id"
    assert proposals[0]["cohort"]["tier"] == "TIER1"


def test_run_adk_improve_loop_persists_suggestions(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")

    improve_dir = tmp_path / "improve"
    improve_dir.mkdir(parents=True)
    (improve_dir / "mine_report.json").write_text(
        json.dumps(
            {
                "buckets": {"actionable": 10},
                "low_yield_candidates": [
                    {"field": "due_date", "tier": "TIER2", "support_strength": "corroborated", "reviewed": 12},
                    {"field": "seller_vat_id", "tier": "TIER1", "support_strength": "corroborated", "reviewed": 8},
                ],
            }
        )
    )

    payload = run_adk_improve_loop(tmp_path)
    assert payload["advisory"] is True
    assert payload["proposals_count"] == 2
    assert payload["rejected_by_critic"] != []

    # Check file output
    out_file = improve_dir / "suggestions.json"
    assert out_file.exists()
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert content["source"] == "ADK_Multi_Agent_Improve_Loop"
