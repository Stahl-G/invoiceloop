"""Arm U critic: a second model role that re-reads the page and challenges
the clerk — advice only, never a decision of record on its own.

Plan position (docs/ARM_UNATTENDED.md): unattended must not mean "one model
judges and approves". The clerk reads the page and drafts; this agent reads
the **same page images** plus the clerk's draft and either agrees or offers a
different reading. Python decides which line is written (and whether the two
roles' disagreement blocks release — unattended_policy R4).

Single-writer rules, same as adjudicator.py: the critic returns ``CriticDraft``
and nothing else — no IDs, no ledger writes. ``release_veto`` is an opinion
the *policy* consumes, not an action.

Why the critic must see the page images rather than the clerk's summary:
2026-08-27's real failure had the clerk invent ``total_net=110810`` from an
hours total. A critic reading only the clerk's words has nothing to catch
that with; a critic reading the page does.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

#: 与 clerk(adjudicator)分开的 ADK app 名 —— 两条角色的会话不许混,
#: 混了就是同一个被告在给自己的判决当陪审团。
CRITIC_APP = "invoiceloop_arm_u_critic"

#: 裁决器标识:clerk 是 agent:<model>,critic 永远多一层角色前缀,
#: 账本里一眼分得出这条是复核改判,不是初裁。
CRITIC_PREFIX = "agent:critic:"


class CriticDraft(BaseModel):
    """critic 的输出。**没有 ID 字段,宪章一。**"""

    agree: bool = Field(description="clerk 的这行裁决你是否同意")
    decision: Literal["accept", "confirm_absent", "not_applicable",
                      "reject", "correct", "abstain"] = Field(
        description="你自己对这一槽的裁决(agree=true 时与 clerk 相同)")
    corrected_value: str | None = Field(
        default=None, description="仅你自己的 decision=correct 时给出")
    absence_evidence: Literal["label_absent", "value_absent", "not_absent",
                              "cannot_tell"] = Field(
        description="label_absent=页面连标签都没印;value_absent=有标签没值;"
                    "not_absent=页面上有这个字段;cannot_tell=看不清/没把握")
    rationale: str
    release_veto: bool = Field(
        default=False,
        description="这一槽的存在让你认为该单据不该无人放行时为 true"
                    "(意见;策略消费它,不直接执行)")


def critic_id(model: str) -> str:
    return f"{CRITIC_PREFIX}{model}"


def critic_call_id(model: str, pack: dict[str, Any],
                   images: list[bytes]) -> str:
    """请求身份 = 模型 ‖ 槽位+clerk 草稿 ‖ 有序图像摘要(与 adjudicator 同式)。"""
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(json.dumps(pack, sort_keys=True, ensure_ascii=False).encode())
    for blob in images:
        h.update(b"|")
        h.update(hashlib.sha256(blob).hexdigest().encode())
    return f"crit_{h.hexdigest()[:16]}"


CRITIC_SYSTEM = """\
You are the second reader on ONE field slot of an accounts-payable document.
A first reader (the clerk) already proposed an adjudication. Your job is to
catch the clerk's mistakes, not to rubber-stamp them.

You are shown: the same page image(s) the clerk saw, the extracted value and
gate results, and the clerk's proposed decision with its rationale.

Respond with:

- agree: whether you concur with the clerk's decision exactly.
- decision: YOUR OWN decision under the same six-choice semantics
  (accept / correct / reject / confirm_absent / not_applicable / abstain).
  If you agree, repeat the clerk's decision.
- corrected_value: only when your own decision is correct.
- absence_evidence: what the PAGE shows for this field — label_absent (the
  label is not printed at all), value_absent (label printed, no value),
  not_absent (the field is present on the page), or cannot_tell.
  A confirm_absent with "cannot_tell" here is worthless — say what you see.
- rationale: name the blocks on the page you used.
- release_veto: true only when something about this slot means the document
  must not be released without a human.

Known traps, all from measured failures — check each one against the page:

- A Taxpayer ID / EIN (dd-ddddddd) is a tax identifier, never an
  invoice_number.
- "Due on Receipt" is a payment term, not a calendar due_date.
- An hours total or subtotal column is not total_net unless the page labels
  it Net.
- A printed 0.00 is a present value, not an absence.
- A single total on the page belongs in amount_due, not manufactured into
  net/vat.

You advise. You do not decide, approve, or release anything.
"""


def make_critic(*, model: str, workspace: Path):
    """→ critic(pack, images) -> CriticDraft,经真 ADK(LlmAgent + Runner)。

    与 adjudicator.make_adk_judge 同构:Agent 只建一次,逐槽换 session;
    录放走 replay_callbacks —— 请求身份含整份 contents(含图像字节),
    换图即换调用,重放不会张冠李戴。
    """
    import asyncio

    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from .adk_replay import replay_callbacks
    from .runtime import export_credential_for_adk

    export_credential_for_adk(workspace)
    before, after = replay_callbacks(workspace)
    agent = LlmAgent(
        name="critic", model=model,
        instruction=CRITIC_SYSTEM,
        output_schema=CriticDraft,
        output_key="critique",
        before_model_callback=before, after_model_callback=after,
    )

    async def _once(pack: dict, images: list[bytes]) -> CriticDraft:
        service = InMemorySessionService()
        session_id = f"critique-{pack['doc_id']}-{pack['field']}"
        await service.create_session(app_name=CRITIC_APP, user_id="arm-u-critic",
                                     session_id=session_id, state={})
        runner = Runner(app_name=CRITIC_APP, agent=agent,
                        session_service=service)
        parts = [types.Part(text=json.dumps(pack, ensure_ascii=False, indent=1))]
        for blob in images:
            parts.append(types.Part.from_bytes(data=blob, mime_type="image/png"))
        async for _ in runner.run_async(
            user_id="arm-u-critic", session_id=session_id,
            new_message=types.Content(role="user", parts=parts),
        ):
            pass
        session = await service.get_session(
            app_name=CRITIC_APP, user_id="arm-u-critic", session_id=session_id)
        raw = dict(session.state).get("critique")
        if raw is None:
            raise RuntimeError("ADK 没给出 critique —— 不许当成弃权")
        return CriticDraft.model_validate(raw)

    def critic(pack: dict, images: list[bytes]) -> CriticDraft:
        return asyncio.run(_once(pack, images))

    return critic
