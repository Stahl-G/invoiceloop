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
