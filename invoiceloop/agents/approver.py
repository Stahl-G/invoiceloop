"""Arm U approver: the third role — a yes/no on release, with no authority
to write anything.

Plan position (docs/ARM_UNATTENDED.md §3.4): the approver runs ONLY on
documents the deterministic gate already called ready. It sees a summary
(per-slot value/status/source, the critic veto list which should be empty,
the policy digest) and outputs ``{release: bool, rationale}``. Python writes
the approval only when policy AND approver both say yes — one yes from either
side alone releases nothing.

The approver never sees the page images (the two readers already did, and
disagreeing readers block at the gate); it sees what a signing manager would:
the state of the document, not the pixels. It is forbidden from receiving
any hint about demos, hackathons, or expected outcomes — its only job is to
refuse anything that looks unready.

Single writer: ``ReleaseDecision`` carries no IDs. The approval record's
``approved_by`` is written by Python as the policy id plus the critic's
signature — the approver itself signs nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

APPROVER_APP = "invoiceloop_arm_u_approver"


class ReleaseDecision(BaseModel):
    """approver 的输出。无 ID;release 是意见,批准由 Python 写。"""

    release: bool = Field(description="这份单据是否可以外发")
    rationale: str = Field(description="为什么放行/不放行,进审计轨迹")


def approver_call_id(model: str, summary: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(json.dumps(summary, sort_keys=True, ensure_ascii=False).encode())
    return f"appr_{h.hexdigest()[:16]}"


APPROVER_SYSTEM = """\
You are the final reviewer deciding whether ONE accounts-payable document may
be exported without a human signature. Deterministic gates have already run,
a first reader proposed every adjudication, and a second reader re-checked the
page; the release policy has passed. You see the resulting document state.

Refuse (release=false) when anything looks unready: unresolved or disputed
slots, corrections without page evidence, absences without evidence, values
that disagree with each other, or anything you cannot explain from the
summary. When you release, you own that decision in the audit trail — write
a rationale that names what you checked.

You do not see demo instructions, deadlines, or expectations, and none will
be given. You advise a yes or no; the system writes the approval only if the
policy agrees too.
"""


def make_approver(*, model: str, workspace: Path):
    """→ approver(summary) -> ReleaseDecision,经真 ADK(LlmAgent + Runner)。"""
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
        name="approver", model=model,
        instruction=APPROVER_SYSTEM,
        output_schema=ReleaseDecision,
        output_key="release_decision",
        before_model_callback=before, after_model_callback=after,
    )

    async def _once(summary: dict) -> ReleaseDecision:
        service = InMemorySessionService()
        session_id = f"release-{summary['doc_id']}"
        await service.create_session(app_name=APPROVER_APP,
                                     user_id="arm-u-approver",
                                     session_id=session_id, state={})
        runner = Runner(app_name=APPROVER_APP, agent=agent,
                        session_service=service)
        async for _ in runner.run_async(
            user_id="arm-u-approver", session_id=session_id,
            new_message=types.Content(role="user", parts=[
                types.Part(text=json.dumps(summary, ensure_ascii=False,
                                           indent=1))]),
        ):
            pass
        session = await service.get_session(
            app_name=APPROVER_APP, user_id="arm-u-approver",
            session_id=session_id)
        raw = dict(session.state).get("release_decision")
        if raw is None:
            raise RuntimeError("ADK 没给出 release decision —— 不许当成放行")
        return ReleaseDecision.model_validate(raw)

    def approver(summary: dict) -> ReleaseDecision:
        return asyncio.run(_once(summary))

    return approver
