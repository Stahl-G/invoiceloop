"""TA arm: an ADK agent doing the reviewer's job, as a control arm — never a product path.

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md`.

**This does not ship.** A model that both proposes a relaxation and approves it has
closed its own supervision loop — the same argument `doctype.py` makes about
`invoice_type`. What ships is the measurement: how far the agent's adjudications
land from a person's on the *same* slots, and what that costs downstream.

Two charter rules do the load-bearing work here:

**Rule one, single writer.** The agent returns `AdjudicationDraft` and nothing
else — no `decision_id`, no `seq`, no `claim_id`. Python reads `claim_id` off the
frozen support matrix and `adjudicate.append_adjudication` assigns the identity.
The agent goes through the *same* writer a human does, so the same combination
checks apply to it.

**Rule four, a check that could not run is not a pass.** An agent abstention is
written as `abstain`, not dropped; a slot whose call fails is counted in
`failures`, not skipped quietly. A silently short ledger would read as agreement.

Replay identity binds the images. Two slots can carry near-identical text and
differ only in the page picture, so the page bytes go into the call id — leave
them out and replay serves a confident answer about the wrong document.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .. import arms
from ..adjudicate import append_adjudication

#: 决策集与人完全相同(adjudicate.DECISIONS)。agent 不得有专属选项 ——
#: 给它一个人没有的出口,两臂就不可比了。
Decision = Literal["accept", "confirm_absent", "not_applicable",
                   "reject", "correct", "abstain"]

#: 裁决者标识前缀。**永不与人混淆** —— 账本里一眼能分出哪条是机器判的。
AGENT_PREFIX = "agent:"

#: ADK app 名。与 improve 循环分开 —— 两条链的会话不该混在一个 app 下。
ARM_APP = "invoiceloop_arm_ta"

#: 无声明的槽不许带 claim_id(append_adjudication 的语义拆分)
_NO_CLAIM_DECISIONS = ("confirm_absent", "not_applicable")


class AdjudicationDraft(BaseModel):
    """agent 的输出。**没有任何 ID 字段,这是宪章一,不是风格偏好。**"""

    decision: Decision
    reason_code: str = Field(description="feedback.REASON_CODES 之一")
    rationale: str = Field(description="判断依据,写给读账本的人看")
    reviewer_confidence: Literal["high", "medium", "low"]
    corrected_value: str | None = Field(
        default=None, description="仅 decision=correct 时给出")


def adjudicator_id(model: str) -> str:
    return f"{AGENT_PREFIX}{model}"


def slot_call_id(model: str, pack: dict[str, Any], images: list[bytes]) -> str:
    """请求身份 = 模型 ‖ 槽位事实 ‖ **有序**的图像摘要。

    图像顺序进哈希:同一份文档的两页调换,问的就不是同一题了。
    """
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(json.dumps(pack, sort_keys=True, ensure_ascii=False).encode())
    for blob in images:
        h.update(b"|")
        h.update(hashlib.sha256(blob).hexdigest().encode())
    return f"adj_{h.hexdigest()[:16]}"


def record_draft(run_dir: Path, key: str, draft: AdjudicationDraft, *,
                 model: str, decided_at: str) -> dict:
    """草稿 → 冻结账本的一行。ID、claim 绑定、组合校验全在 Python 这侧。

    `claim_id` **从冻结投影里读**,不由 agent 提供 —— 让模型指认自己裁决的是
    哪条声明,等于把绑定交给被监督者。
    """
    run_dir = Path(run_dir)
    matrix = json.loads(
        (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    row = next((r for r in matrix["rows"] if arms.slot_key(r) == key), None)
    if row is None:
        raise KeyError(f"槽位不存在:{key}")
    claim_id = None if draft.decision in _NO_CLAIM_DECISIONS \
        else row.get("claim_id")
    return append_adjudication(
        run_dir,
        claim_id=claim_id,
        doc_id=row["doc_id"],
        field=row["field"],
        decision=draft.decision,
        rationale=draft.rationale,
        adjudicator=adjudicator_id(model),
        decided_at=decided_at,
        corrected_value=draft.corrected_value,
        reason_code=draft.reason_code,
        reviewer_confidence=draft.reviewer_confidence,
    )


#: 给 agent 的任务说明。写法纪律:**与 workbench 给人的信息同构** ——
#: 六个决策中性列出、语义照 adjudicate.py 的定义抄,不暗示哪个该多用,
#: 不提任何期望分布(预注册 §8 就是防这个)。
ADJUDICATOR_SYSTEM = """\
You are adjudicating ONE field slot of one accounts-payable document, the same
task a human reviewer does at this workbench.

You are shown: the value the extractor produced (empty means it produced none),
what the deterministic gates concluded, which regions of the page the value was
bound to, the full page image, and a crop of each bound region.

Choose exactly ONE decision. The semantics are fixed and not interchangeable:

- accept          — the extracted value is correct for this field.
- correct         — a value belongs here but the extracted one is wrong; give
                    corrected_value.
- reject          — the extracted value is wrong and you are not supplying a
                    replacement.
- confirm_absent  — THIS document genuinely does not carry this field.
- not_applicable  — this CLASS of document has no such concept (e.g. a field
                    that only exists for a different document type).
- abstain         — the evidence shown does not let you decide.

confirm_absent and not_applicable are different claims: the first is about this
page, the second is about the kind of document. Do not use one for the other.

reason_code must be one of: WRONG_VALUE, WRONG_FIELD_MAPPING,
BAD_SOURCE_BINDING, MISSING_EXTRACTION, NORMALIZATION_ERROR,
ROUTING_FALSE_NEGATIVE, ROUTING_FALSE_POSITIVE, CONFIRMED_ABSENT,
NOT_APPLICABLE, AMBIGUOUS_DOCUMENT, PROVIDER_FAILURE, REVIEWER_PREFERENCE,
OTHER. It must be consistent with the decision: CONFIRMED_ABSENT only with
confirm_absent, NOT_APPLICABLE only with not_applicable, WRONG_VALUE only with
correct or reject.

rationale: state what on the page led you there, for someone reading the ledger
later. reviewer_confidence: high, medium or low.
"""


def make_adk_judge(*, model: str, workspace: Path):
    """→ judge(pack, images) -> AdjudicationDraft,经真 ADK(LlmAgent + Runner)。

    录放走 `adk_replay.replay_callbacks`:它的请求身份把 `contents` 整份
    (含内联图像字节)哈希进摘要,所以图换了就是另一次调用,重放不会
    张冠李戴。Agent 与 Runner 只建一次,200 槽复用。
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
        name="adjudicator", model=model,
        instruction=ADJUDICATOR_SYSTEM,
        output_schema=AdjudicationDraft,
        output_key="adjudication",
        before_model_callback=before, after_model_callback=after,
    )

    async def _once(pack: dict, images: list[bytes]) -> AdjudicationDraft:
        service = InMemorySessionService()
        session_id = f"slot-{pack['doc_id']}-{pack['field']}"
        await service.create_session(app_name=ARM_APP, user_id="arm-ta",
                                     session_id=session_id, state={})
        runner = Runner(app_name=ARM_APP, agent=agent, session_service=service)
        parts = [types.Part(text=json.dumps(pack, ensure_ascii=False, indent=1))]
        for blob in images:
            parts.append(types.Part.from_bytes(data=blob, mime_type="image/png"))
        async for _ in runner.run_async(
            user_id="arm-ta", session_id=session_id,
            new_message=types.Content(role="user", parts=parts),
        ):
            pass
        session = await service.get_session(
            app_name=ARM_APP, user_id="arm-ta", session_id=session_id)
        raw = dict(session.state).get("adjudication")
        if raw is None:
            raise RuntimeError("ADK 没给出 adjudication —— 不许当成弃权")
        return AdjudicationDraft.model_validate(raw)

    def judge(pack: dict, images: list[bytes]) -> AdjudicationDraft:
        return asyncio.run(_once(pack, images))

    return judge


def run_arm(run_dir: Path, slots: list[str], *,
            judge: Callable[[dict, list[bytes]], AdjudicationDraft],
            model: str, decided_at: str,
            images_for: Callable[[str], list[bytes]] | None = None) -> dict:
    """把 judge 依次喂给每个槽,结果写进账本。

    `judge` 注入而非内建:测试用桩,真跑用 `adk_judge`。失败**计数并留证**,
    不跳过 —— 少写一行在下游读起来就是「两臂在这个槽上一致」。
    """
    run_dir = Path(run_dir)
    matrix = json.loads(
        (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    written, failures = 0, []
    for key in slots:
        try:
            pack = arms.slot_pack(matrix, key)
            images = images_for(key) if images_for else []
            draft = judge(pack, images)
            record_draft(run_dir, key, draft, model=model, decided_at=decided_at)
            written += 1
        except Exception as exc:  # noqa: BLE001 —— 逐槽隔离,一个槽炸不带走整臂
            failures.append({"slot": key, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "slots": len(slots),
        "written": written,
        "failed": len(failures),
        "failures": failures,
        "model": model,
        "adjudicator": adjudicator_id(model),
    }
