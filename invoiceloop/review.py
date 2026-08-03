"""人工裁决的读取侧:加载账本 + supersession 链投影。

纪律:
- 投影是纯函数 —— 同一份 adjudication_ledger.jsonl + 同一个 review_snapshot_id,
  任何机器任何时候投出的 current state 都一样(可重算,GOAL.md 优先级 2)。
- current state 由 supersession 链决定,不许"取最后一行碰运气"。
- v1 旧条目(无 decision_id,2026-08-02 验收轮留下)给合成 id,同槽位的
  旧条目按 seq 隐式串链 —— 那是 v1 当时的语义,如实标注 legacy,不改写字节。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .snapshot import load_or_derive_snapshot


def target_id_for(review_snapshot_id: str, doc_id: str, field: str) -> str:
    """一个字段槽的稳定裁决目标。DWS 没返回值的槽(无 claim)也是它 ——
    人工可以合法补录 missing field,目标不接受任意字符串。"""
    digest = hashlib.sha256(
        f"{review_snapshot_id}|{doc_id}|{field}".encode()
    ).hexdigest()
    return f"T-{digest[:12]}"


def _legacy_id(line: str) -> str:
    return f"legacy-{hashlib.sha256(line.encode()).hexdigest()[:8]}"


def load_decisions(run_dir: Path) -> list[dict]:
    """读 adjudication_ledger.jsonl,按 seq 返回;每条保证有
    decision_id / target_id / review_snapshot_id / supersedes_decision_id。

    v1 旧条目:合成 legacy-<sha8> id;同槽位的连续旧条目按 seq 隐式串链
    (supersedes 指向前一条),这是 v1 的语义,加载时确定性修复,不改文件。

    绑定到其他快照的条目(典型:从另一个 run 目录复制来的账本)= orphan:
    不进链、不投影,但显式标出 —— 历史不藏,也不许错投到这个 run 的槽位上。
    """
    path = Path(run_dir) / "adjudication_ledger.jsonl"
    if not path.exists():
        return []
    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    entries: list[dict] = []
    prev_by_target: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if "decision_id" not in entry:  # v1 旧格式
            entry = {**entry,
                     "decision_id": _legacy_id(line),
                     "target_id": target_id_for(snapshot_id, entry["doc_id"], entry["field"]),
                     "review_snapshot_id": snapshot_id,
                     "legacy": True}
            entry["supersedes_decision_id"] = prev_by_target.get(entry["target_id"])
        if entry["review_snapshot_id"] != snapshot_id:
            entry["orphan"] = True
        entries.append(entry)
        prev_by_target[entry["target_id"]] = entry["decision_id"]
    return entries


def project(decisions: list[dict]) -> dict[str, dict]:
    """target_id → {"tip", "history", "conflict"}。

    tip = 链上没有被任何条目 supersede 的那条;链断了(多条 tip,只可能是
    手工编辑账本造成)= conflict,显式标出,不替人猜哪条算数。
    orphan(绑到别的快照)不进链。
    """
    slots: dict[str, list[dict]] = {}
    for entry in decisions:
        if entry.get("orphan"):
            continue
        slots.setdefault(entry["target_id"], []).append(entry)
    out: dict[str, dict] = {}
    for target, chain in slots.items():
        chain = sorted(chain, key=lambda e: e["seq"])
        superseded = {e.get("supersedes_decision_id") for e in chain} - {None}
        tips = [e for e in chain if e["decision_id"] not in superseded]
        out[target] = {
            "tip": tips[-1] if len(tips) == 1 else None,
            "history": chain,
            "conflict": len(tips) != 1,
        }
    return out


def project_run(run_dir: Path) -> dict[str, dict]:
    """run 目录 → 投影(load + project 的合体,panel 与 append 校验共用)。"""
    return project(load_decisions(run_dir))
