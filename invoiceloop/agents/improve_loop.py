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
from invoiceloop.harness import load_active

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


def resolve_cohort(mine_report: dict[str, Any], active_policy: dict[str, Any],
                   proposed: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """模型提的 `{field, tier}` → Python 冻结的 cohort + kind。拒绝时抛 ValueError。

    **为什么这一步必须在 Python 这边**(2026-08-07,在 195 条真复核事件上跑
    ADK 才暴露出来 —— demo 语料上模型返回空列表,这条路径从没被走过):

    1. **ID。** 宪章一:模型不发 ID,Python 分配。模型确实没发,而
       `lint_policy` 要求 cohort 带 id,于是每条提案都以「cohort 缺 id」阻断。
       两边都在守规矩,中间没人接上 —— 实测 2 提案 / 2 阻断。
       ID 由内容推定而不是计数器:同一条 cohort 每次都得同一个 ID,
       否则重放与重跑对不上。
    2. **kind。** 缺席规则强制挂 QA 探针(缺席是否仍成立要持续观测),
       `auto_accept` 不挂。这是个安全选择,不能让模型来做 ——
       所以由确定性挖掘报告推定:字段落在 `absence_candidates` 里就是缺席
       规则。缺席是**字段级**属性,与 TIER 无关,所以 tier 要剥掉。
       字段级缺席当前只有`absent_evidenced`(页面证据缺席)一条路:
       `f6dad7e` 之后全局 `absent_expected` 只剩冻结重放,新规则必须带
       doc_class,而挖掘报告给不出类条件授权。`absent_evidenced` 的 id 由
       `improve.propose` 分配(AV-{field}),这里不写 —— 写了会被拒。
    3. **只能在挖掘报告里选。** 否则「确定性挖掘 → 模型判断」这条链断了:
       模型可以提一条没有任何复核事件支撑的规则,系统照样给它跑反事实、
       照样呈到人面前签字。
    """
    field = (proposed or {}).get("field")
    tier = (proposed or {}).get("tier")
    if not field:
        raise ValueError("提案没给 field")

    absent_fields = {c.get("field")
                     for c in mine_report.get("absence_candidates") or []}
    mined_pairs = {(c.get("field"), c.get("tier"))
                   for section in ("cohorts", "low_yield_candidates")
                   for c in mine_report.get(section) or []}

    # 缺席优先:同一批事件既会进 cohorts 也会进 absence_candidates,
    # 而两者中缺席规则是**更安全**的那条(带 QA 探针)。
    if field in absent_fields:
        kind = "absent_evidenced"
        cohort = {"field": field}
        expected_id = f"AV-{field}"
    elif (field, tier) in mined_pairs:
        kind = "auto_accept"
        cohort = {"id": f"AA-{field}-{tier}", "field": field, "tier": tier}
        expected_id = cohort["id"]
    else:
        raise ValueError(
            f"挖掘报告里没有 field={field!r} tier={tier!r} 这条 cohort —— "
            f"模型只能在确定性挖掘出来的 cohort 中选,不能凭空造一条")

    section = ("absent_evidenced_cohorts" if kind == "absent_evidenced"
               else "auto_accept_cohorts")
    if expected_id in {c.get("id") for c in active_policy.get(section) or []}:
        raise ValueError(
            f"{expected_id} 已在生效政策里 —— 再提一次不是改进,是空转;"
            f"lint 对既有 id 是放行,所以这里要自己拦")
    return cohort, kind


def find_existing_candidate(workspace: Path, active: dict[str, Any],
                            cohort: dict[str, Any], kind: str) -> str | None:
    """已经为**这条** cohort 造过、且父级仍是当前 active 的候选,返回目录名。

    循环跑第二遍不该在 workspace 里再堆一个一模一样的候选。除了脏之外,
    候选目录名与政策摘要都会跟着变,于是**报告本身不可复现** ——
    而「同输入同输出」正是这个系统最不肯让步的性质。

    比的是内容不是 id:政策必须恰好等于「父策略 + 这一条 cohort」。只按 id
    匹配的话,某个碰巧也带了这个 id、却还改了别的东西的候选会被误当成它。
    `harness_id` / `version` 是出生时写进策略的,比较时要剔掉。
    """
    section = ("absent_evidenced_cohorts" if kind == "absent_evidenced"
               else "auto_accept_cohorts")
    if kind == "absent_evidenced":
        # 与 improve.propose 分配的同形:id 在候选政策里已补上
        cohort = {"id": f"AV-{cohort['field']}", "field": cohort["field"]}
    parent = active.get("policy") or {}
    expected = {k: v for k, v in
                {**parent, section: (parent.get(section) or []) + [cohort]}.items()
                if k not in ("harness_id", "version")}

    harnesses = Path(workspace) / "harnesses"
    if not harnesses.exists():
        return None
    for cand_dir in sorted(harnesses.glob("HAR-*")):
        man_p, pol_p = cand_dir / "manifest.json", cand_dir / "routing_policy.json"
        if not (man_p.exists() and pol_p.exists()):
            continue
        man = json.loads(man_p.read_text(encoding="utf-8"))
        if man.get("parent_harness_id") != active.get("harness_id"):
            continue
        if man.get("provenance") != "machine_proposed":
            continue
        pol = json.loads(pol_p.read_text(encoding="utf-8"))
        got = {k: v for k, v in pol.items() if k not in ("harness_id", "version")}
        if got == expected:
            return cand_dir.name
    return None


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
        mine_report = ctx.session.state.get(STATE_MINE_REPORT) or {}
        results: list[dict[str, Any]] = []
        for prop in proposals:
            proposed = prop.get("cohort") or {}
            # key 用**模型提的**那份:解析失败时没有 resolved cohort,
            # 而每条提案在报告里都得有一个稳定的身份。
            entry: dict[str, Any] = {
                "proposed": proposed,
                "cohort": proposed,
                "key": cohort_key(proposed),
                "finding": prop.get("finding", ""),
                "prediction": prop.get("prediction", ""),
            }
            try:
                active = load_active(self.workspace)
                cohort, kind = resolve_cohort(
                    mine_report, active.get("policy") or {}, proposed)
                entry["cohort"] = cohort
                entry["kind"] = kind
                # 同一条 cohort 已经造过候选就复用 —— 循环重跑不该堆重复候选,
                # 也不该让报告里的候选名每跑一次就变一个(见 find_existing_candidate)。
                name = find_existing_candidate(self.workspace, active, cohort, kind)
                if name is None:
                    name = improve.propose(
                        self.workspace,
                        cohort=cohort,
                        finding=prop.get("finding", ""),
                        prediction=prop.get("prediction", ""),
                        kind=kind,
                    ).name
                entry["evaluation"] = improve.evaluate(self.workspace, name)
                entry["blocking"] = False
                entry["candidate"] = name
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


#: Critic 能看到的反事实字段,**白名单**。
#:
#: 用白名单不用黑名单,是因为代价不对称:漏掉一个该藏的字段会静默破坏录放,
#: 而多藏一个字段最多让 Critic 少看点东西。
#:
#: 藏起来的是**记账字段** —— 候选目录名、政策摘要、baseline harness。它们是
#: 账本要的溯源,不是「这条规则安不安全」的判断依据。它们进提示词的代价是
#: 实打实的:循环每跑一次就新造一个候选(HAR-0002 → HAR-0003 → …),目录名和
#: 政策摘要跟着变,提示词跟着变,请求摘要跟着变 —— **同一个 workspace 上录一
#: 次再重放直接 ReplayRecordingMissing**。录放绑定的是整个请求,所以任何与判
#: 断无关却会漂移的东西都不许进提示词。
#: (2026-08-07 发现:此前 propose 恒失败、从不生成候选,这段漂移被掩住了。)
_CRITIC_EVAL_FIELDS = (
    "safety_status", "basis",
    "silent_absent_baseline", "silent_absent_candidate",
    "silent_wrong_baseline", "silent_wrong_candidate",
    "review_load_baseline", "review_load_candidate", "delta_pp",
    "evaluated_slots", "note",
)
#: `finding` / `prediction` 是模型自己写的主张 —— 那正是 Critic 要争论的东西,
#: 所以随解析后的 cohort 一起给它。**原稿 cohort(`proposed`)不给**:
#: 实测(2026-08-07 真数据)模型提 `{field, tier}`,Python 解析成字段级
#: `absent_expected` 并剥掉 tier;两份都进提示词的话,Critic 会照原稿写成
#: 「across all TIER1 documents」—— 而真实范围是**所有**文档,比它写的更宽。
#: 给人看的建议把规则范围写窄了,是往危险的方向错。
#: `key` 也不给:它是**原稿** cohort 的序列化(报告里的条目身份),tier 会从
#: 那里漏回提示词里 —— 上面那段说的漏法,换个字段又来一遍。
_CRITIC_ENTRY_FIELDS = ("cohort", "kind", "blocking", "blocking_reason",
                        "finding", "prediction")


#: 要替 Critic 算好的差值:(基线键, 候选键) → 差值键。
#:
#: 2026-08-07,第一次在真复核历史上跑循环时实测到的失败:Critic 对两条提案都
#: 投反对,理由写「留下 5 个静默错值暴露在外」。`silent_wrong_baseline` 确实
#: 是 5 —— 而 `silent_wrong_candidate` 也是 5,这条规则一个都没多留。它把**基线
#: 数当成了改动的代价**。数字真,因果假,而这份报告是要给人看的。
#:
#: 修法不是把提示词写得更啰嗦,是**别让模型做 Python 能做的减法**。
_CRITIC_DELTAS = (
    ("silent_absent_baseline", "silent_absent_candidate", "silent_absent_delta"),
    ("silent_wrong_baseline", "silent_wrong_candidate", "silent_wrong_delta"),
    ("review_load_baseline", "review_load_candidate", "review_load_delta"),
)


def _critic_view(counterfactual: dict[str, Any]) -> dict[str, Any]:
    results = []
    for entry in counterfactual.get("results") or []:
        view = {k: entry[k] for k in _CRITIC_ENTRY_FIELDS if k in entry}
        ev = entry.get("evaluation")
        if ev is None:
            view["evaluation"] = None
        else:
            shown = {k: ev[k] for k in _CRITIC_EVAL_FIELDS if k in ev}
            for base, cand, out in _CRITIC_DELTAS:
                if base not in ev or cand not in ev:
                    continue
                shown[base], shown[cand] = ev[base], ev[cand]
                # 没评分时两边都是 None:差值写 None,不写 0 ——
                # 「没测」和「测了,没变化」是两回事(宪章四)。
                shown[out] = (None
                              if ev[base] is None or ev[cand] is None
                              else ev[cand] - ev[base])
            view["evaluation"] = shown
            # Gate 2/3 是**预注册的确定性判定**,不该由 Critic 重算。给它结论,
            # 让它去争门禁看不见的东西:规则是不是太宽、哪些值有风险。
            view["gate"] = {
                k: v for k, v in improve.gate_verdict(ev).items()
                if k in ("ok", "refusals", "basis", "safety_status")
            }
        results.append(view)
    return {**counterfactual, "results": results}


def _critic_instruction(ctx: ReadonlyContext) -> str:
    # 提案只出现一次,而且是**解析后**那一份(见 _CRITIC_ENTRY_FIELDS):
    # 原稿与解析结果同时给,Critic 会照原稿描述规则范围,写出比实际更窄的话。
    counterfactual = _critic_view(ctx.state.get(STATE_COUNTERFACTUAL) or {})
    return (
        "You are the adversarial reviewer. For each proposal you are given the "
        "DETERMINISTIC counterfactual: what the rule would have saved and what it "
        "would have silently dropped. Argue against the proposal wherever the "
        "numbers allow it.\n\n"
        "A `blocking: true` entry means the evaluation could not run. A check that "
        "did not run is NOT a pass — recommend against, and say so.\n\n"
        "Read the numbers as deltas. `*_baseline` is what already happens WITHOUT "
        "the rule; only `*_delta` is what the rule costs. A silent error present "
        "in both baseline and candidate is NOT a cost of this proposal, and must "
        "not be cited as one. `gate` is the deterministic pre-registered verdict "
        "on load and silent errors — do not re-derive it. Your job is what the "
        "gate cannot see: is the rule wider than the evidence, and which values "
        "would go unseen if it were wrong.\n\n"
        "You are not approving anything. `recommend_for_human_review` means only "
        "'a human should spend time on this one'.\n\n"
        "Each entry carries the proposal's own `finding` and `prediction` — those "
        "are the claims you are arguing with — next to the cohort as Python "
        "actually resolved it. Describe the rule from the resolved `cohort`, not "
        "from the wording of the finding.\n\n"
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
