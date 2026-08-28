"""Arm U: unattended adjudication and approval as an explicit experimental arm.

Plan: ``docs/ARM_UNATTENDED.md`` (2026-08-27). NOT the product default — the
default path keeps ``approve.py``'s "a machine may never do this" true. This
arm exists for one question: can the kernel take an agent closing the loop
without giving any single model both the judging and the signing? The
2026-08-27 grokbot experiment says a lone clerk leaks errors into exports
when the approver only checks "queue is empty" — so this arm is
**two model roles plus one deterministic policy**:

    Runner.run_async()
      └─ SequentialAgent "unattended_pipeline"        order fixed by ADK
           ├─ clerk   LlmAgent  per slot, page images in → AdjudicationDraft
           ├─ binder  BaseAgent Python: append_adjudication (agent:<model>)
           ├─ critic  LlmAgent  per slot, same images + clerk draft → CriticDraft
           ├─ binder2 BaseAgent Python: disagreements supersede via the
           │                    same writer (agent:critic:<model>)
           ├─ gate    BaseAgent Python: deliverable recompute + unattended_policy
           │                    audit — a document not ready never reaches
           │                    the approver at all
           ├─ approver LlmAgent per ready doc → {release, rationale}
           └─ binder3 BaseAgent Python: policy AND approver both yes →
                        append_approval(policy_digest=…); one yes ≠ release

Why binder/gate are BaseAgents and not tools: a tool runs at model discretion
(ADK_INTEGRATION's lesson — "the counterfactual evaluation must run every
time"). SequentialAgent guarantees the order; the model cannot skip a check.

Signatures in the ledgers stay unambiguous:
``agent:<model>`` (clerk), ``agent:critic:<model>`` (critic override), and
approvals signed ``unattended-policy-v1+agent:critic:<model>`` — never
confusable with a person. Times come from the operator (``--decided-at``);
no artifact reads the wall clock.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from .adjudicator import AdjudicationDraft, make_adk_judge
from .approver import ReleaseDecision, make_approver
from .critic import CriticDraft, critic_id, make_critic

UNATTENDED_APP = "invoiceloop_arm_u_pipeline"

#: clerk/critic 需要整页图 —— 缺图不是"看过了",是没跑(宪章四)。
_IMAGES_REQUIRED = ("clerk", "critic")


def _call_with_retry(fn, *args):
    """瞬时故障(503/429/overloaded,live 实测)重试;耗尽直抛。
    退避 3s/6s/9s —— 429 的配额窗口按分钟计,2s 级退避撞不开(第二轮
    live 验收实测)。"""
    from .runtime import retry_transient

    return retry_transient(lambda: fn(*args), base_delay=3.0)


def _err(exc: BaseException) -> str:
    """失败记录里的异常文本:截断并抹掉凭据形状(PR 审查:某些客户端
    库会把 Authorization 头原样嵌进异常消息)。"""
    import re

    text = f"{type(exc).__name__}: {exc}"
    text = re.sub(r"ya29\.[A-Za-z0-9._-]+", "ya29.<redacted>", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer <redacted>", text)
    text = re.sub(r"AIza[A-Za-z0-9_\-]+", "AIza<redacted>", text)
    return text[:200]

ReasonMapper = Callable[[str], str]

#: Arm U 给 clerk 的事实性补充:accept 的写者语义。不含任何期望答案。
_CLERK_EXTRA_INSTRUCTION = """

One factual constraint of the ledger you are writing into: "accept" is only
legal for a slot whose pack carries a frozen claim (claim_id is not null) —
you are accepting THAT frozen claim. If the slot shows a value but claim_id
is null (the draft never froze), do not pick accept: use correct with the
printed value, reject, or confirm_absent as the page dictates.
"""


def critic_reason_code(decision: str) -> str:
    """critic 改判行的心码:确定性映射,不给模型第二处自由度。"""
    return {
        "accept": "ROUTING_FALSE_POSITIVE",
        "correct": "WRONG_VALUE",
        "reject": "WRONG_VALUE",
        "confirm_absent": "CONFIRMED_ABSENT",
        "not_applicable": "NOT_APPLICABLE",
        "abstain": "AMBIGUOUS_DOCUMENT",
    }[decision]


#: 执行失败字段:任一非空 → CLI 退出码 1(Cloud Run Job 据此报失败)。
#: **approval_refusals 不在其中** —— 策略/approver 拒绝是正常业务结果,
#: 不是执行失败;"没批"永远不许被当成"没跑"。
_FAILURE_FIELDS = (
    "drive_fatal", "gate_error", "deliverable_error",
    "clerk_failures", "clerk_binding_failures",
    "critic_failures", "critic_binding_failures",
    "approver_failures",
)


def failed(report: dict) -> bool:
    """unattended_run 报告里有没有执行失败(宪章四:跑不了 ≠ 通过)。"""
    return any(report.get(field) for field in _FAILURE_FIELDS)


def build_unattended_pipeline(
    run_dir: Path,
    *,
    clerk: Callable[[dict, list[bytes]], AdjudicationDraft],
    critic: Callable[[dict, list[bytes]], CriticDraft],
    approver: Callable[[dict], ReleaseDecision],
    model: str,
    decided_at: str,
) -> Any:
    """七段 SequentialAgent。clerk/critic/approver 一律注入:真跑传
    make_adk_judge / make_critic / make_approver 的产物,测试传桩。

    模型调用一律走 ``asyncio.to_thread``:真 ADK 判官内部用 asyncio.run,
    直接在事件循环里调会炸;线程里各起各的循环,逐槽隔离不变。
    """
    from collections.abc import AsyncGenerator

    from google.adk.agents import BaseAgent, SequentialAgent
    from google.adk.events import Event, EventActions

    run_dir = Path(run_dir)
    matrix = json.loads(
        (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    from .. import arms
    from ..evidence import page_images

    def _pack(key: str) -> dict:
        return arms.slot_pack(matrix, key)

    def _images(doc_id: str) -> list[bytes]:
        return [p.read_bytes()
                for p in page_images(run_dir / "pages", doc_id)]

    class _ClerkNode(BaseAgent):
        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            state = ctx.session.state
            drafts: dict[str, dict] = {}
            failures: list[dict] = []
            for key in state["queue"]:
                doc_id = key.split("|", 1)[0]
                try:
                    images = _images(doc_id)
                    if not images:
                        raise ValueError(f"{doc_id}: 无整页渲染 —— 不许裁")
                    draft = await asyncio.to_thread(
                        _call_with_retry, clerk, _pack(key), images)
                    drafts[key] = draft.model_dump()
                except Exception as exc:  # noqa: BLE001 — 逐槽隔离
                    failures.append({"slot": key,
                                     "error": f"{type(exc).__name__}: {exc}"})
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "clerk_drafts": drafts,
                            "clerk_failures": failures}))

    class _BinderNode(BaseAgent):
        """clerk 草稿 → 账本。ID/claim 绑定仍由 append_adjudication 分配。

        逐槽隔离:一条草稿与写者语义不合(如无冻结声明的槽选了 accept)
        记入 binding_failures,该槽留在无 tip 状态由 R1 挡下 —— 不修模型
        的答案,也不让一行炸掉整臂(宪章四)。"""

        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            from .adjudicator import record_draft

            written = 0
            failures: list[dict] = []
            for key, payload in ctx.session.state["clerk_drafts"].items():
                try:
                    record_draft(run_dir, key, AdjudicationDraft.model_validate(
                        payload), model=model, decided_at=decided_at)
                    written += 1
                except Exception as exc:  # noqa: BLE001 — 逐槽隔离,报告必须写得出
                    failures.append({"slot": key, "error": _err(exc)})
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "clerk_written": written,
                            "clerk_binding_failures": failures}))

    class _CriticNode(BaseAgent):
        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            state = ctx.session.state
            drafts: dict[str, dict] = {}
            failures: list[dict] = []
            for key in state["queue"]:
                doc_id = key.split("|", 1)[0]
                clerk_line = state["clerk_drafts"].get(key)
                try:
                    images = _images(doc_id)
                    if not images:
                        raise ValueError(f"{doc_id}: 无整页渲染 —— 不许复核")
                    pack = {**_pack(key), "clerk_proposal": clerk_line}
                    draft = await asyncio.to_thread(
                        _call_with_retry, critic, pack, images)
                    drafts[key] = draft.model_dump()
                except Exception as exc:  # noqa: BLE001
                    failures.append({"slot": key,
                                     "error": f"{type(exc).__name__}: {exc}"})
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "critic_drafts": drafts,
                            "critic_failures": failures}))

    class _Binder2Node(BaseAgent):
        """clerk 与 critic 不一致 → critic 改判以 supersedes 落账;
        一致 → 保留 clerk 行,不写第二条。跑不了的槽(critic failure)
        不写改判 —— 该槽的缺口由 gate 的 R3/R4 挡下,不静默。"""

        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            from ..adjudicate import append_adjudication
            from ..unattended_policy import _slot_tips
            from .adjudicator import _NO_CLAIM_DECISIONS

            state = ctx.session.state
            tips = _slot_tips(run_dir)
            rows_by_slot = {(r["doc_id"], r["field"]): r
                            for r in matrix["rows"]}
            overrides: list[dict] = []
            failures: list[dict] = []
            for key, payload in state["critic_drafts"].items():
                try:
                    draft = CriticDraft.model_validate(payload)
                    if draft.agree and not draft.release_veto:
                        continue
                    doc_id, field = key.split("|", 1)
                    row = rows_by_slot.get((doc_id, field))
                    if row is None:
                        raise KeyError(f"槽位不在矩阵:{key}")
                    claim_id = (None if draft.decision in _NO_CLAIM_DECISIONS
                                else row.get("claim_id"))
                    tip = tips.get((doc_id, field))
                    entry = append_adjudication(
                        run_dir, claim_id=claim_id, doc_id=doc_id, field=field,
                        decision=draft.decision, rationale=draft.rationale,
                        adjudicator=critic_id(model), decided_at=decided_at,
                        corrected_value=draft.corrected_value,
                        supersedes_decision_id=(tip or {}).get("decision_id"),
                        reason_code=critic_reason_code(draft.decision),
                        reviewer_confidence="medium",
                    )
                except Exception as exc:  # noqa: BLE001 — 逐槽隔离
                    failures.append({"slot": key, "error": _err(exc)})
                    continue
                overrides.append({"slot": key,
                                  "decision_id": entry["decision_id"],
                                  "decision": draft.decision,
                                  "release_veto": draft.release_veto})
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "critic_overrides": overrides,
                            "critic_binding_failures": failures}))

    class _GateNode(BaseAgent):
        """确定性闸:重算交付投影,逐单做策略预检。
        不 ready 的单据根本不会送到 approver —— 「队列空了就签」在这里
        被结构性拒绝(2026-08-27 的实败)。"""

        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            from .. import unattended_policy
            from ..approve import APPROVABLE
            from ..deliver import write_deliverable

            state = ctx.session.state
            try:
                write_deliverable(run_dir)
            except Exception as exc:  # noqa: BLE001 — 交付投影写不出 = 全部不可批
                state["gate_error"] = _err(exc)
                yield Event(author=self.name, invocation_id=ctx.invocation_id,
                            actions=EventActions(state_delta={
                                "gate": {}, "gate_ready_docs": [],
                                "gate_error": _err(exc)}))
                return
            deliverable = json.loads(
                (run_dir / "deliverable.json").read_text(encoding="utf-8"))
            audits = {}
            ready = []
            for doc_id, entry in sorted(deliverable["docs"].items()):
                try:
                    audit = unattended_policy.audit_document(
                        run_dir, doc_id,
                        queue_keys=state["queue"],
                        clerk_by_slot={tuple(k.split("|", 1)): v for k, v
                                       in state["clerk_drafts"].items()},
                        critic_by_slot={tuple(k.split("|", 1)): v for k, v
                                        in state["critic_drafts"].items()},
                        deliverable_status=entry["status"],
                        approvable_statuses=APPROVABLE,
                    )
                except Exception as exc:  # noqa: BLE001 — 单据审计炸 ≠ 整臂死
                    audit = {
                        "doc_id": doc_id, "ready": False,
                        "status": "gate_error",
                        "queue_slots": 0,
                        "violations": [{"rule": "R2",
                                        "code": "document_not_approvable",
                                        "error": _err(exc)}],
                        "policy_id": unattended_policy.POLICY_ID,
                        "policy_digest": unattended_policy.policy_digest(),
                    }
                audits[doc_id] = audit
                if audit["ready"]:
                    ready.append(doc_id)
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "gate": audits, "gate_ready_docs": ready}))

    class _ApproverNode(BaseAgent):
        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            state = ctx.session.state
            decisions: dict[str, dict] = {}
            failures: list[dict] = []
            deliverable = json.loads(
                (run_dir / "deliverable.json").read_text(encoding="utf-8"))
            for doc_id in state["gate_ready_docs"]:
                entry = deliverable["docs"][doc_id]
                vetoes = [o for o in state.get("critic_overrides", [])
                          if o.get("release_veto")
                          and o["slot"].split("|", 1)[0] == doc_id]
                summary = {
                    "doc_id": doc_id,
                    "status": entry["status"],
                    "policy": {"id": state["policy_id"],
                               "digest": state["policy_digest"]},
                    "fields": entry["fields"],
                    "blocking_reasons": entry.get("blocking_reasons") or [],
                    "critic_vetoes": vetoes,
                }
                try:
                    decision = await asyncio.to_thread(
                        _call_with_retry, approver, summary)
                    decisions[doc_id] = decision.model_dump()
                except Exception as exc:  # noqa: BLE001
                    failures.append({"doc": doc_id,
                                     "error": f"{type(exc).__name__}: {exc}"})
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "approver_decisions": decisions,
                            "approver_failures": failures}))

    class _Binder3Node(BaseAgent):
        """策略 + approver 双 yes 才写批准。任一拒绝/失败 = 不批,
        单据停在 ready_for_approval —— 这是诚实失败,不是缺步骤。"""

        async def _run_async_impl(  # type: ignore[override]
                self, ctx) -> AsyncGenerator[Event, None]:
            from .. import unattended_policy
            from ..approve import APPROVABLE, append_approval
            from ..deliver import write_deliverable

            state = ctx.session.state
            approvals: list[dict] = []
            refusals: list[dict] = []
            for doc_id, payload in state["approver_decisions"].items():
                decision = ReleaseDecision.model_validate(payload)
                try:
                    audit = unattended_policy.audit_document(
                        run_dir, doc_id,
                        queue_keys=state["queue"],
                        clerk_by_slot={tuple(k.split("|", 1)): v for k, v
                                       in state["clerk_drafts"].items()},
                        critic_by_slot={tuple(k.split("|", 1)): v for k, v
                                        in state["critic_drafts"].items()},
                        deliverable_status=(state.get("gate", {})
                                            .get(doc_id, {}).get("status")),
                        approvable_statuses=APPROVABLE,
                        approver_release=decision.release,
                    )
                    if not (decision.release and audit["ready"]):
                        refusals.append({
                            "doc_id": doc_id,
                            "approver_release": decision.release,
                            "rationale": decision.rationale,
                            "policy_violations": audit["violations"],
                        })
                        continue
                    entry = append_approval(
                        run_dir, doc_id=doc_id,
                        approved_by=(f"{state['policy_id']}"
                                     f"+{critic_id(state['model'])}"),
                        rationale=decision.rationale,
                        approved_at=state["decided_at"],
                        policy_digest=state["policy_digest"],
                    )
                except Exception as exc:  # noqa: BLE001 — 批准写不进 = 该单不放,如实记
                    refusals.append({
                        "doc_id": doc_id,
                        "approver_release": decision.release,
                        "rationale": decision.rationale,
                        "approval_error": _err(exc),
                    })
                    continue
                approvals.append({"doc_id": doc_id,
                                  "approval_id": entry["approval_id"]})
            try:
                write_deliverable(run_dir)
            except Exception as exc:  # noqa: BLE001 — 批准后投影失败要留痕
                state["deliverable_error"] = _err(exc)
            yield Event(author=self.name, invocation_id=ctx.invocation_id,
                        actions=EventActions(state_delta={
                            "approvals": approvals,
                            "approval_refusals": refusals}))

    return SequentialAgent(
        name="unattended_pipeline",
        sub_agents=[
            _ClerkNode(name="clerk"),
            _BinderNode(name="binder"),
            _CriticNode(name="critic"),
            _Binder2Node(name="binder2"),
            _GateNode(name="gate"),
            _ApproverNode(name="approver"),
            _Binder3Node(name="binder3"),
        ],
    )


async def _drive(pipeline: Any, initial_state: dict) -> tuple[dict, list[str]]:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    service = InMemorySessionService()
    await service.create_session(app_name=UNATTENDED_APP, user_id="arm-u",
                                 session_id="unattended", state=initial_state)
    runner = Runner(app_name=UNATTENDED_APP, agent=pipeline,
                    session_service=service)
    authors: list[str] = []
    async for event in runner.run_async(
        user_id="arm-u", session_id="unattended",
        new_message=types.Content(role="user", parts=[
            types.Part(text="Run the unattended pipeline.")]),
    ):
        if event and event.author:
            authors.append(event.author)
    session = await service.get_session(app_name=UNATTENDED_APP,
                                        user_id="arm-u",
                                        session_id="unattended")
    return dict(session.state), authors


def run_unattended(
    run_dir: Path,
    *,
    model: str,
    decided_at: str,
    clerk: Callable[[dict, list[bytes]], AdjudicationDraft] | None = None,
    critic: Callable[[dict, list[bytes]], CriticDraft] | None = None,
    approver: Callable[[dict], ReleaseDecision] | None = None,
    docs: list[str] | None = None,
) -> dict:
    """跑完整臂并落 ``unattended_run.json`` 报告(机器侧工件,非账本)。

    clerk/critic/approver 缺省时用真 ADK 判官(需要凭证或 INVOICELOOP_REPLAY
    的录音);注入桩则全程零 API —— 测试与本地演练同一条代码路径。
    """
    import asyncio

    from .. import arms, unattended_policy

    run_dir = Path(run_dir)
    workspace = run_dir.parent.parent
    # OCR/绑定按全局 derisk_root() 路由 —— 这条臂的一切页面判断必须读
    # **本 run 工作区**的证据,不许滑到校准档案(pipeline --workspace 同款
    # 行为)。只在形状吻合 <ws>/runs/run-NNNN 时覆盖(PR 审查:--out 直写
    # 目录或嵌套路径下 parent.parent 不是工作区,盖了反而读错根);
    # 显式配了 INVOICELOOP_CORPUS 的调用方同样不被覆盖。
    import os

    if (run_dir.parent.name == "runs"
            and not os.environ.get("INVOICELOOP_CORPUS")):
        os.environ["INVOICELOOP_DWS_DERISK"] = str(workspace)
    matrix = json.loads(
        (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    queue = arms.review_pool(matrix)
    # census 下挡账的槽(pending/pending_tier1/abstained)也归 clerk ——
    # 只走 review 槽会把「印证槽也要显式裁决」的 TIER1 留在 pending,
    # 单据永远到不了 ready(第一轮 live 验收实测)。挡账集按 run 自己的
    # 策略口径取,不按当前 active —— 旧 run 的语义不许随晋升漂移。
    routing_path = run_dir / "routing_report.json"
    routing = json.loads(routing_path.read_text(encoding="utf-8")) \
        if routing_path.exists() else {}
    from ..deliver import build_deliverable
    from ..release_profile import (
        CENSUS_BLOCKING_STATUSES, PROFILE_BLOCKING_STATUSES)

    profile_id = (routing.get("policy") or {}).get("release_profile")
    blocking_statuses = (PROFILE_BLOCKING_STATUSES if profile_id
                         else CENSUS_BLOCKING_STATUSES)
    pre = build_deliverable(run_dir)
    for doc_id, entry in (pre.get("docs") or {}).items():
        for fname, fentry in (entry.get("fields") or {}).items():
            if fentry.get("status") in blocking_statuses:
                queue.append(f"{doc_id}|{fname}")
    queue = sorted(set(queue))
    if docs is not None:
        wanted = set(docs)
        queue = [k for k in queue if k.split("|", 1)[0] in wanted]
    clerk = clerk or make_adk_judge(model=model, workspace=workspace,
                                    extra_instruction=_CLERK_EXTRA_INSTRUCTION)
    critic = critic or make_critic(model=model, workspace=workspace)
    approver = approver or make_approver(model=model, workspace=workspace)

    pipeline = build_unattended_pipeline(
        run_dir, clerk=clerk, critic=critic, approver=approver,
        model=model, decided_at=decided_at)
    # PR 审查:任何节点炸都不许让报告写不出 —— 账本里已有的行是事实,
    # unattended_run.json 是它们唯一的机器侧对照,必须无条件落盘。
    drive_fatal: str | None = None
    try:
        state, authors = asyncio.run(_drive(pipeline, {
            "queue": queue,
            "model": model,
            "decided_at": decided_at,
            "policy_id": unattended_policy.POLICY_ID,
            "policy_digest": unattended_policy.policy_digest(),
        }))
    except Exception as exc:  # noqa: BLE001 — 报告必须写得出
        drive_fatal = _err(exc)
        state, authors = {}, []

    report = {
        "arm": "unattended",
        "advisory": False,
        "run_dir": str(run_dir),
        "model": model,
        "decided_at": decided_at,
        "drive_fatal": drive_fatal,
        "gate_error": state.get("gate_error"),
        "deliverable_error": state.get("deliverable_error"),
        "policy_id": unattended_policy.POLICY_ID,
        "policy_digest": unattended_policy.policy_digest(),
        "queue_slots": len(queue),
        "clerk_written": state.get("clerk_written", 0),
        "clerk_failures": state.get("clerk_failures", []),
        "clerk_binding_failures": state.get("clerk_binding_failures", []),
        "critic_overrides": state.get("critic_overrides", []),
        "critic_failures": state.get("critic_failures", []),
        "critic_binding_failures": state.get("critic_binding_failures", []),
        "gate": state.get("gate", {}),
        "gate_ready_docs": state.get("gate_ready_docs", []),
        "approver_decisions": state.get("approver_decisions", {}),
        "approver_failures": state.get("approver_failures", []),
        "approvals": state.get("approvals", []),
        "approval_refusals": state.get("approval_refusals", []),
        "adk": {
            "executed": True,
            "runner": "google.adk.runners.Runner",
            "pipeline": "SequentialAgent(unattended_pipeline)",
            "event_authors": authors,
        },
        "note": "实验臂,非产品默认:clerk=agent:<model>,改判="
                "agent:critic:<model>,批准=" + unattended_policy.POLICY_ID
                + "+agent:critic:<model>;默认路径的批准仍只有人能签",
    }
    (run_dir / "unattended_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    try:
        from ..panel import render_panel_from_run

        render_panel_from_run(run_dir)
        report["panel_refreshed"] = True
    except Exception as exc:  # noqa: BLE001 — 渲染失败不回滚账本(与裁决同序)
        report["panel_refreshed"] = False
        report["panel_error"] = f"{type(exc).__name__}: {exc}"
        (run_dir / "unattended_run.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
    return report
