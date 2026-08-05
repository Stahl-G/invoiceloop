"""Harness 加载:active 指针 → 策略 dict + 内容寻址 digest。

默认 = 包内 HAR-0001(保守起点,与 2026-08-05 前的内联分诊逻辑等价)。
workspace 有 improve/active_harness.json 时以它为准 —— 那是 promotion
的唯一产物(写它只有 `improve promote` 一个入口,必须人名 + 理由)。
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .routing import policy_digest

DEFAULT_HARNESS = "HAR-0001"


def _builtin_policy() -> dict:
    text = (resources.files("invoiceloop")
            / "harnesses" / DEFAULT_HARNESS / "routing_policy.json").read_text()
    return json.loads(text)


def load_active(root: Path | None = None) -> dict:
    """{harness_id, policy, policy_digest}。root = workspace/语料根。"""
    if root is not None:
        pointer = Path(root) / "improve" / "active_harness.json"
        if pointer.exists():
            rec = json.loads(pointer.read_text(encoding="utf-8"))
            policy_path = (Path(root) / "harnesses" / rec["harness_id"]
                           / "routing_policy.json")
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            return {"harness_id": rec["harness_id"], "policy": policy,
                    "policy_digest": policy_digest(policy)}
    policy = _builtin_policy()
    return {"harness_id": DEFAULT_HARNESS, "policy": policy,
            "policy_digest": policy_digest(policy)}
