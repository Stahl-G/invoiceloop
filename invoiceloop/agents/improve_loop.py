"""ADK Multi-Agent Improve Loop (invoiceloop/agents/improve_loop.py).

Orchestrates 4 distinct Agents/Nodes:
1. MinerAgent: Identifies review patterns from mine_report.json.
2. ProposerAgent: Drafts candidate policy cohorts or schema description diffs.
3. CriticAgent (Adversarial Agent): Evaluates proposed cohorts to ensure true ground-truth
   values are not dropped. Specifically rejects invalid cohorts like `due_date` relaxation
   that save review slots at the cost of dropping genuine due dates.
4. EvaluatorNode: Triggers deterministic `improve.evaluate()`.

Safety Constraint:
- Single-Writer Discipline: Output is written ONLY to `improve/suggestions.json` (as drafts).
- Promotion remains gated by deterministic `Gate 2` and human signature.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from invoiceloop import improve
from .runtime import call_gemini_model, is_replay_mode


class MinerAgent:
    """Agent 1: Scans mine_report.json for high-frequency, un-overturned review patterns."""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)

    def run(self) -> dict[str, Any]:
        report_path = self.workspace / "improve" / "mine_report.json"
        if not report_path.exists():
            improve.mine(self.workspace)
        if not report_path.exists():
            return {"candidates": []}

        report = json.loads(report_path.read_text(encoding="utf-8"))
        low_yield = report.get("low_yield_candidates", [])
        return {
            "candidates": low_yield,
            "buckets": report.get("buckets", {}),
            "total_cohorts": len(report.get("cohorts", [])),
        }


class ProposerAgent:
    """Agent 2: Formulates candidate policy cohorts from miner findings."""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)

    def run(self, miner_output: dict[str, Any]) -> list[dict[str, Any]]:
        proposals = []
        for cand in miner_output.get("candidates", []):
            field = cand.get("field")
            tier = cand.get("tier")
            strength = cand.get("support_strength")
            if field and tier:
                cohort = {"field": field, "tier": tier}
                if strength:
                    cohort["strength"] = strength
                proposals.append({
                    "action": "auto_accept",
                    "cohort": cohort,
                    "finding": f"Reviewed {cand.get('reviewed', 0)} times with 0 corrections.",
                    "prediction": f"Relaxes review requirement for {field} when {strength or 'all'}.",
                })
        return proposals


class CriticAgent:
    """Agent 3 (Adversarial Agent): Evaluates proposed cohorts to protect ground truth.

    Crucial Behavior:
    - Analyzes whether a proposal drops valid values (e.g. `due_date` cohort).
    - If a cohort risks dropping genuine values (like missing 5 true due dates),
      the Critic Agent explicitly rejects the proposal and logs an adversarial objection.
    """

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)

    def evaluate_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        cohort = proposal.get("cohort") or {}
        field = cohort.get("field")

        # Specific adversarial rule: due_date cohorts are prone to dropping true values
        # (reproducing human rejection of due_date auto-accepts that saved 37 slots but lost 5 true due dates)
        if field == "due_date":
            return {
                "accepted": False,
                "reason": (
                    "Adversarial Objection: due_date auto-accept cohort drops genuine due dates "
                    "on un-overturned documents where payment terms vary."
                ),
                "risk_score": "HIGH",
            }

        # LLM / Replay query for nuanced evaluation
        prompt = (
            f"Evaluate this policy relaxation cohort proposal:\n{json.dumps(proposal, indent=2)}\n"
            "Will this cohort risk dropping true invoice values?"
        )
        res = call_gemini_model(
            prompt=prompt,
            system_instruction="You are an adversarial AI auditor protecting financial invoice extraction accuracy.",
            workspace=self.workspace,
            call_id=f"critic_{field}",
        )

        # Check for objection in output
        res_text = res.get("text", "").lower()
        if "reject" in res_text or "high risk" in res_text:
            return {
                "accepted": False,
                "reason": res.get("text"),
                "risk_score": "HIGH",
            }

        return {
            "accepted": True,
            "reason": "Passed adversarial critic check.",
            "risk_score": "LOW",
        }


class EvaluatorNode:
    """Node 4: Triggers deterministic improve.evaluate counterfactual routing."""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)

    def run(self, approved_proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for prop in approved_proposals:
            try:
                cohort = prop.get("cohort")
                if not cohort:
                    continue
                cand_dir = improve.propose(
                    self.workspace,
                    cohort=cohort,
                    finding=prop.get("finding", "ADK Multi-Agent Proposed"),
                    prediction=prop.get("prediction", "ADK Multi-Agent Proposed"),
                )
                cand_id = cand_dir.name
                eval_res = improve.evaluate(self.workspace, cand_id)
                results.append({"candidate_id": cand_id, "evaluation": eval_res})
            except Exception as exc:  # noqa: BLE001
                results.append({"error": str(exc), "proposal": prop})
        return results


def run_adk_improve_loop(workspace: Path | str) -> dict[str, Any]:
    """Runs the 4-stage ADK Multi-Agent Improve Loop."""
    ws = Path(workspace)

    # 1. Miner Agent
    miner = MinerAgent(ws)
    miner_out = miner.run()

    # 2. Proposer Agent
    proposer = ProposerAgent(ws)
    proposals = proposer.run(miner_out)

    # 3. Critic Agent
    critic = CriticAgent(ws)
    approved = []
    rejected = []
    for prop in proposals:
        critic_res = critic.evaluate_proposal(prop)
        if critic_res["accepted"]:
            approved.append(prop)
        else:
            rejected.append({"proposal": prop, "critic": critic_res})

    # 4. Evaluator Node
    evaluator = EvaluatorNode(ws)
    eval_results = evaluator.run(approved) if approved else []

    # Write output to improve/suggestions.json (as drafts)
    suggestions_path = ws / "improve" / "suggestions.json"
    suggestions_path.parent.mkdir(exist_ok=True)
    payload = {
        "advisory": True,
        "source": "ADK_Multi_Agent_Improve_Loop",
        "miner_summary": miner_out.get("buckets", {}),
        "proposals_count": len(proposals),
        "approved_by_critic": len(approved),
        "rejected_by_critic": rejected,
        "evaluations": eval_results,
    }
    suggestions_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return payload
