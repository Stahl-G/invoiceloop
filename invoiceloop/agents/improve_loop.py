"""The improvement loop: a four-stage pipeline genuinely executed by an ADK `Runner`.

    Runner.run_async()
      └─ SequentialAgent "improve_pipeline"
           ├─ LlmAgent  miner      → state["miner"]        which review patterns deserve a rule
           ├─ LlmAgent  proposer   → state["proposals"]    how to write it without going too wide
           ├─ Evaluator (BaseAgent)→ state["counterfactual"]  deterministic, always runs
           └─ LlmAgent  critic     → state["critic"]       would this rule drop real values?

Why the evaluator is a custom `BaseAgent` rather than a tool: a tool is invoked at
the model's discretion. Charter rule four says a check that could not run is not a
pass, so the counterfactual evaluation **must** run every time. `SequentialAgent`
executes its children in order, and no model can skip it.

The model's authority boundary (charter rule one, single writer):
- The model produces **advice**. The field is called `recommend_for_human_review`,
  not `accepted`. It approves nothing, and it does not decide which candidates are
  worth evaluating — every candidate is evaluated deterministically.
- Output goes only to `improve/adk_loop_report.json`; `suggestions.json` belongs
  to suggest.py.
- Promotion is still decided by Gate 2 plus a human signature. This module does
  not touch it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Literal

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.events import Event, EventActions
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from invoiceloop import improve

from .adk_replay import replay_callbacks
from .runtime import _resolve_model, export_credential_for_adk

APP_NAME = "invoiceloop_improve"
PIPELINE_STAGES = ("miner", "proposer", "evaluator", "critic")

#: session state 键 —— 单一来源,指令/节点/报告全部引用这里
STATE_MINE_REPORT = "mine_report"
STATE_MINER = "miner"
STATE_PROPOSALS = "proposals"
STATE_COUNTERFACTUAL = "counterfactual"
STATE_CRITIC = "critic"


# ── 结构化输出契约 ────────────────────────────────────────────────

class MinerCandidate(BaseModel):
    field: str
    tier: str
    reviewed: int
    why: str


class MinerFindings(BaseModel):
    candidates: list[MinerCandidate]


class ProposalCohort(BaseModel):
    field: str
    tier: str


class Proposal(BaseModel):
    action: str
    cohort: ProposalCohort
    finding: str
    prediction: str


class ProposalSet(BaseModel):
    proposals: list[Proposal]


class Verdict(BaseModel):
    """模型的**建议**,不是批准。

    字段名刻意不叫 `accepted` / `approved` / `safe`:模型没有放行权,
    它能说的只有「这条值不值得人看」和「风险在哪」。
    """

    cohort_field: str
    recommend_for_human_review: bool
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str
    values_at_risk: list[str]


class CriticReview(BaseModel):
    verdicts: list[Verdict]


# ── 确定性节点 ────────────────────────────────────────────────────

def cohort_key(cohort: dict[str, Any]) -> str:
    """反事实结果的键 —— 整个 cohort 的规范化形式,不是 field。

    早先版本按 `cohort["field"]` 键控,同一字段的多条 cohort 会互相覆盖,
    Critic 于是拿到别条候选的反事实证据。
    """
    return json.dumps(cohort, sort_keys=True, ensure_ascii=False)


class EvaluatorNode(BaseAgent):
    """对每条提案跑确定性 `improve.propose` + `improve.evaluate`。

    评测失败**不吞** —— 记一条 blocking 结果交给 Critic 与报告。
    早先版本 `except Exception: pre_evals[field] = {}`,Critic 于是拿着
    空反事实照样能给出正面建议。
    """

    workspace: Path

    async def _run_async_impl(
        self, ctx
    ) -> AsyncGenerator[Event, None]:
        proposals = (ctx.session.state.get(STATE_PROPOSALS) or {}).get("proposals", [])
        results: list[dict[str, Any]] = []
        for prop in proposals:
            cohort = prop.get("cohort") or {}
            entry: dict[str, Any] = {"cohort": cohort, "key": cohort_key(cohort)}
            try:
                cand_dir = improve.propose(
                    self.workspace,
                    cohort=cohort,
                    finding=prop.get("finding", ""),
                    prediction=prop.get("prediction", ""),
                )
                entry["evaluation"] = improve.evaluate(self.workspace, cand_dir.name)
                entry["blocking"] = False
                entry["candidate"] = cand_dir.name
            except Exception as exc:  # noqa: BLE001 — 宪章四:跑不了 = 阻断
                entry["blocking"] = True
                entry["blocking_reason"] = f"{type(exc).__name__}: {exc}"
                entry["evaluation"] = None
            results.append(entry)

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta={STATE_COUNTERFACTUAL: {"results": results}}),
        )


# ── 指令 ──────────────────────────────────────────────────────────

def _miner_instruction(ctx: ReadonlyContext) -> str:
    report = ctx.state.get(STATE_MINE_REPORT) or {}
    return (
        "You read a deterministic mining report from an invoice review ledger "
        "and judge which human-review patterns are stable enough to become a "
        "policy rule. You do not decide anything — a deterministic evaluator "
        "and a human do.\n\n"
        f"mine_report.json:\n{json.dumps(report, ensure_ascii=False, indent=1)}\n\n"
        "Return the candidates worth proposing, with a one-line reason each. "
        "Return an empty list if none are."
    )


def _proposer_instruction(ctx: ReadonlyContext) -> str:
    miner = ctx.state.get(STATE_MINER) or {}
    return (
        "You turn mining candidates into draft policy cohorts. A cohort that is "
        "too wide silently drops values that are genuinely on the page — that is "
        "the failure mode you are guarding against.\n\n"
        f"candidates:\n{json.dumps(miner, ensure_ascii=False, indent=1)}\n\n"
        "Return one proposal per candidate. Return an empty list for no candidates."
    )


def _critic_instruction(ctx: ReadonlyContext) -> str:
    proposals = ctx.state.get(STATE_PROPOSALS) or {}
    counterfactual = ctx.state.get(STATE_COUNTERFACTUAL) or {}
    return (
        "You are the adversarial reviewer. For each proposal you are given the "
        "DETERMINISTIC counterfactual: what the rule would have saved and what it "
        "would have silently dropped. Argue against the proposal wherever the "
        "numbers allow it.\n\n"
        "A `blocking: true` entry means the evaluation could not run. A check that "
        "did not run is NOT a pass — recommend against, and say so.\n\n"
        "You are not approving anything. `recommend_for_human_review` means only "
        "'a human should spend time on this one'.\n\n"
        f"proposals:\n{json.dumps(proposals, ensure_ascii=False, indent=1)}\n\n"
        f"counterfactual:\n{json.dumps(counterfactual, ensure_ascii=False, indent=1)}\n\n"
        "Return one verdict per proposal. Return an empty list for no proposals."
    )


def build_pipeline(model: str | BaseLlm, workspace: Path) -> SequentialAgent:
    """四阶段图。顺序由 SequentialAgent 保证,模型无权改。

    每个 LlmAgent 都挂录放回调:重放模式下 before 回调直接返回录音,
    模型调用被 ADK 跳过 —— 图照跑,网络不动(见 `adk_replay`)。
    """
    before, after = replay_callbacks(workspace)

    def _llm(name: str, state_key: str, instruction,
             schema: type[BaseModel]) -> LlmAgent:
        # state_key 与 name 分开写:下游按 state_key 读,`output_key=name`
        # 会让 proposer 写进 state["proposer"] 而 evaluator 读 state["proposals"],
        # 整条链静默断掉(重构时踩过一次,由本目录测试抓到)。
        return LlmAgent(
            name=name, model=model, instruction=instruction,
            output_schema=schema, output_key=state_key,
            before_model_callback=before, after_model_callback=after,
        )

    return SequentialAgent(
        name="improve_pipeline",
        sub_agents=[
            _llm("miner", STATE_MINER, _miner_instruction, MinerFindings),
            _llm("proposer", STATE_PROPOSALS, _proposer_instruction, ProposalSet),
            EvaluatorNode(name="evaluator", workspace=workspace),
            _llm("critic", STATE_CRITIC, _critic_instruction, CriticReview),
        ],
    )


# ── 入口 ──────────────────────────────────────────────────────────

def _load_mine_report(ws: Path) -> dict[str, Any]:
    path = ws / "improve" / "mine_report.json"
    if not path.exists():
        return {"cohorts": [], "buckets": {}, "low_yield_candidates": []}
    return json.loads(path.read_text(encoding="utf-8"))


async def _drive(pipeline: SequentialAgent, ws: Path,
                 mine_report: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    service = InMemorySessionService()
    await service.create_session(
        app_name=APP_NAME, user_id="invoiceloop", session_id="improve",
        state={STATE_MINE_REPORT: mine_report},
    )
    runner = Runner(app_name=APP_NAME, agent=pipeline, session_service=service)
    authors: list[str] = []
    async for event in runner.run_async(
        user_id="invoiceloop", session_id="improve",
        new_message=types.Content(
            role="user", parts=[types.Part(text="run the improve loop")]
        ),
    ):
        if event.author not in authors:
            authors.append(event.author)
    session = await service.get_session(
        app_name=APP_NAME, user_id="invoiceloop", session_id="improve"
    )
    return authors, dict(session.state)


def run_improve_loop(
    workspace: Path | str, *, model: str | BaseLlm | None = None
) -> dict[str, Any]:
    """跑 ADK 流水线,写 `improve/adk_loop_report.json`(纯建议)。

    Args:
        workspace: run workspace.
        model: 模型名或 `BaseLlm` 实例。缺省从 env / `DEFAULT_GEMINI_MODEL` 解析。
    """
    ws = Path(workspace)
    resolved = model if isinstance(model, BaseLlm) else _resolve_model(model, ws)
    if isinstance(resolved, str):
        # ADK 自己建 genai client,读进程环境,不认 invoiceloop 的 .env 加载器。
        # 桥接过去,并且用我们自己的错误 —— ADK 的通用报错不会提到重放模式。
        export_credential_for_adk(ws)
    mine_report = _load_mine_report(ws)

    pipeline = build_pipeline(resolved, ws)
    authors, state = asyncio.run(_drive(pipeline, ws, mine_report))

    counterfactual = (state.get(STATE_COUNTERFACTUAL) or {}).get("results", [])
    blocked = [r for r in counterfactual if r.get("blocking")]
    verdicts = (state.get(STATE_CRITIC) or {}).get("verdicts", [])

    payload = {
        "advisory": True,
        "source": "Gemini_Multi_Agent_Improve_Loop",
        "adk": {
            "executed": True,
            "runner": "google.adk.runners.Runner",
            "app_name": APP_NAME,
            "pipeline": "SequentialAgent(improve_pipeline)",
            "event_authors": authors,
            "state_keys": sorted(k for k in state if not k.startswith("_")),
        },
        "model": resolved if isinstance(resolved, str) else type(resolved).__name__,
        "miner_summary": mine_report.get("buckets", {}),
        "proposals": (state.get(STATE_PROPOSALS) or {}).get("proposals", []),
        "counterfactual": counterfactual,
        "blocking_evaluations": len(blocked),
        "recommendations": verdicts,
        "recommended_for_human_review": sum(
            1 for v in verdicts if v.get("recommend_for_human_review")
        ),
        "authority": (
            "advisory only — the model recommends, Python recomputes, "
            "Gate 2 and a human signature decide promotion"
        ),
    }

    out = ws / "improve" / "adk_loop_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload
