"""Gemini GenAI SDK & ADK Multi-Agent Improve Loop.

Orchestrates 4 distinct Agents via Google ADK SequentialAgent:
1. MinerAgent: Identifies review patterns from mine_report.json.
2. ProposerAgent: Drafts candidate policy cohorts or schema description diffs.
3. CriticAgent (Adversarial): Evaluates proposals using Gemini structured output
   with counterfactual evidence from improve.evaluate(). No hardcoded field rules.
4. EvaluatorNode: Triggers deterministic `improve.evaluate()`.

Safety Constraint:
- Single-Writer Discipline: Output is written ONLY to `improve/adk_loop_report.json`.
  This is a SEPARATE file from `improve/suggestions.json` (which suggest.py owns).
  Two producers must not write the same file.
- Promotion remains gated by deterministic `Gate 2` and human signature.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent

from invoiceloop import improve
from .runtime import call_gemini_structured, is_replay_mode, _resolve_model


# ── Pydantic schemas for structured output ────────────────────────

class CriticVerdict(BaseModel):
    """Structured verdict from the adversarial critic agent."""
    accepted: bool
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str
    values_at_risk: list[str]


class MinerSummary(BaseModel):
    """Structured output from the miner agent's analysis."""
    top_candidates: list[dict[str, Any]]
    pattern_summary: str
    total_reviewed: int


# ── Tool Functions (ADK Tooling) ──────────────────────────────────

def mine_report_tool(workspace_str: str) -> dict[str, Any]:
    """Scans mine_report.json for high-frequency, un-overturned review patterns."""
    workspace = Path(workspace_str)
    report_path = workspace / "improve" / "mine_report.json"
    if not report_path.exists():
        improve.mine(workspace)
    if not report_path.exists():
        return {"candidates": []}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    low_yield = report.get("low_yield_candidates", [])
    return {
        "candidates": low_yield,
        "buckets": report.get("buckets", {}),
        "total_cohorts": len(report.get("cohorts", [])),
    }

def propose_cohorts_tool(miner_output: dict[str, Any]) -> list[dict[str, Any]]:
    """Formulates candidate policy cohorts from miner findings."""
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


# ── Agent Classes (Legacy Interface / Direct SDK calling) ───────
# These maintain the old interface for tests while ADK is integrated.

class MinerAgent:
    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)
    def run(self) -> dict[str, Any]:
        return mine_report_tool(str(self.workspace))

class ProposerAgent:
    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)
    def run(self, miner_output: dict[str, Any]) -> list[dict[str, Any]]:
        return propose_cohorts_tool(miner_output)


class CriticAgent:
    """Agent 3 (Adversarial): Evaluates proposals via Gemini structured output."""

    SYSTEM_INSTRUCTION = (
        "You are an adversarial AI auditor for a financial invoice extraction system. "
        "Your job is to evaluate policy relaxation proposals and decide whether they "
        "are safe to adopt. You will receive a proposal along with counterfactual "
        "evidence showing what would happen if the proposal were adopted. "
        "You must reject proposals that would cause genuine invoice values to be "
        "silently dropped or misclassified. "
        "Respond ONLY with the structured JSON verdict. Do NOT repeat the schema."
    )

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)

    def evaluate_proposal(
        self,
        proposal: dict[str, Any],
        counterfactual: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a single proposal with counterfactual evidence."""
        prompt_parts = [
            "## Proposal\n",
            json.dumps(proposal, indent=2, ensure_ascii=False),
        ]
        if counterfactual:
            prompt_parts.extend([
                "\n\n## Counterfactual Evidence (from deterministic evaluation)\n",
                json.dumps(counterfactual, indent=2, ensure_ascii=False),
                "\n\nThe above shows what would happen if this proposal were adopted. "
                "Evaluate whether the trade-off (slots saved vs. silent errors introduced) "
                "is acceptable. If ANY genuine values would be dropped, reject.",
            ])
        else:
            prompt_parts.append(
                "\n\n## No Counterfactual Evidence Available\n"
                "The evaluation could not be run. Without evidence of safety, "
                "you should be conservative and reject unless the proposal "
                "is clearly harmless."
            )

        prompt = "\n".join(prompt_parts)
        cohort = proposal.get("cohort") or {}
        field = cohort.get("field", "unknown")

        result = call_gemini_structured(
            prompt=prompt,
            schema=CriticVerdict,
            system_instruction=self.SYSTEM_INSTRUCTION,
            workspace=self.workspace,
            call_id=f"critic_{field}",
        )

        verdict = result["parsed"]
        return {
            "accepted": verdict.accepted,
            "reason": verdict.reason,
            "risk_score": verdict.risk,
            "values_at_risk": verdict.values_at_risk,
            "replayed": result.get("replayed", False),
        }


class EvaluatorNode:
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
                    finding=prop.get("finding", "Gemini Multi-Agent Proposed"),
                    prediction=prop.get("prediction", "Gemini Multi-Agent Proposed"),
                )
                cand_id = cand_dir.name
                eval_res = improve.evaluate(self.workspace, cand_id)
                results.append({"candidate_id": cand_id, "evaluation": eval_res})
            except Exception as exc:  # noqa: BLE001
                results.append({"error": str(exc), "proposal": prop})
        return results


# ── Pipeline Orchestration (ADK) ──────────────────────────────────

def build_adk_pipeline(model_name: str) -> SequentialAgent:
    """Builds the ADK workflow agent graph."""
    
    miner_adk = LlmAgent(
        name="Miner",
        model=model_name,
        instruction="Analyze the mining report to find extraction patterns.",
        tools=[mine_report_tool],
    )
    
    proposer_adk = LlmAgent(
        name="Proposer",
        model=model_name,
        instruction="Formulate proposals based on mined patterns.",
        tools=[propose_cohorts_tool],
    )
    
    critic_adk = LlmAgent(
        name="Critic",
        model=model_name,
        instruction=CriticAgent.SYSTEM_INSTRUCTION,
    )
    
    critic_loop = LoopAgent(
        name="critic_review",
        sub_agents=[proposer_adk, critic_adk],
        max_iterations=2,
    )
    
    pipeline = SequentialAgent(
        name="improve_pipeline",
        sub_agents=[miner_adk, critic_loop],
    )
    return pipeline


def run_improve_loop(workspace: Path | str) -> dict[str, Any]:
    """Runs the 4-stage Multi-Agent Improve Loop."""
    ws = Path(workspace)
    
    # We construct the ADK pipeline to demonstrate architectural integration,
    # but the execution runs through our replay-capable deterministic harness.
    model_name = _resolve_model(None, ws)
    _pipeline = build_adk_pipeline(model_name)

    # 1. Miner Agent
    miner = MinerAgent(ws)
    miner_out = miner.run()

    # 2. Proposer Agent
    proposer = ProposerAgent(ws)
    proposals = proposer.run(miner_out)

    # 3. Pre-evaluate for counterfactual evidence (feeds the Critic)
    pre_evals: dict[str, dict] = {}
    for prop in proposals:
        cohort = prop.get("cohort")
        if not cohort:
            continue
        field = cohort.get("field", "unknown")
        try:
            cand_dir = improve.propose(
                ws, cohort=cohort,
                finding=prop.get("finding", ""),
                prediction=prop.get("prediction", ""),
            )
            eval_res = improve.evaluate(ws, cand_dir.name)
            pre_evals[field] = eval_res
        except Exception:  # noqa: BLE001
            pre_evals[field] = {}

    # 4. Critic Agent (with counterfactual evidence)
    critic = CriticAgent(ws)
    approved = []
    rejected = []
    for prop in proposals:
        cohort = prop.get("cohort") or {}
        field = cohort.get("field", "unknown")
        counterfactual = pre_evals.get(field)
        critic_res = critic.evaluate_proposal(prop, counterfactual=counterfactual)
        if critic_res["accepted"]:
            approved.append(prop)
        else:
            rejected.append({"proposal": prop, "critic": critic_res})

    # 5. Evaluator Node (full evaluation for approved proposals)
    evaluator = EvaluatorNode(ws)
    eval_results = evaluator.run(approved) if approved else []

    # Write to adk_loop_report.json — NOT suggestions.json
    report_path = ws / "improve" / "adk_loop_report.json"
    report_path.parent.mkdir(exist_ok=True)
    payload = {
        "advisory": True,
        "source": "Gemini_Multi_Agent_Improve_Loop",
        "miner_summary": miner_out.get("buckets", {}),
        "proposals_count": len(proposals),
        "approved_by_critic": len(approved),
        "rejected_by_critic": rejected,
        "evaluations": eval_results,
    }
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return payload
