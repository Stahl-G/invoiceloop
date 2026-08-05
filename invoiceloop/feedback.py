"""反馈平面(v0.2 §3.4):从权威工件派生 FeedbackEvent。

裁决账本是权威;反馈事件是**派生的、可重建的数据产品** —— 不反向修改
裁决,不写回任何 run 工件。改进层(mine/propose/evaluate)只消费这里
产出的事件,不直接读裁决账本 —— 这样「反馈被怎么解释」本身也可重算。
"""

from __future__ import annotations

import json
from pathlib import Path

from .fields import TIER1
from .review import load_decisions

#: v0.2 §5.2 的最小 reason code 集。裁决时可选;人给,系统不代填。
REASON_CODES = (
    "WRONG_VALUE", "WRONG_FIELD_MAPPING", "BAD_SOURCE_BINDING",
    "MISSING_EXTRACTION", "NORMALIZATION_ERROR", "ROUTING_FALSE_NEGATIVE",
    "ROUTING_FALSE_POSITIVE", "CONFIRMED_ABSENT", "NOT_APPLICABLE",
    "AMBIGUOUS_DOCUMENT", "PROVIDER_FAILURE", "REVIEWER_PREFERENCE", "OTHER",
)


def compile_events(run_dir: Path) -> list[dict]:
    """一个 run 的裁决 → FeedbackEvent 列表(确定性:同工件同输出)。"""
    run_dir = Path(run_dir)
    decisions = load_decisions(run_dir)
    if not decisions:
        return []
    matrix = json.loads((run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    rows = {(r["doc_id"], r["field"]): r for r in matrix["rows"]}
    routing_path = run_dir / "routing_report.json"
    harness_id = "HAR-0001"
    if routing_path.exists():
        harness_id = json.loads(routing_path.read_text(encoding="utf-8"))["harness_id"]

    events = []
    for i, d in enumerate(decisions, start=1):
        row = rows.get((d["doc_id"], d["field"]), {})
        events.append({
            "feedback_id": f"FB-{i:06d}",
            "decision_id": d["decision_id"],
            "run": run_dir.name,
            "review_snapshot_id": d.get("review_snapshot_id"),
            "harness_id": harness_id,
            "doc_id": d["doc_id"],
            "field": d["field"],
            "tier": "TIER1" if d["field"] in TIER1 else "TIER2",
            "claim_id": d.get("claim_id"),
            "route": row.get("route"),
            "route_reason_codes": row.get("reason_codes", []),
            "support_strength": row.get("support_strength"),
            "human_action": d["decision"],
            "reason_code": d.get("reason_code"),
            "corrected_value": d.get("corrected_value"),
            "adjudicator": d.get("adjudicator"),
            "decided_at": d.get("decided_at"),
            "supersedes_decision_id": d.get("supersedes_decision_id"),
        })
    return events


def compile_workspace(workspace: Path) -> list[dict]:
    """workspace 全部已完成 run(半成品 run 跳过:没有 event_log 的不算)。"""
    out = []
    runs_dir = Path(workspace) / "runs"
    for run_dir in sorted(runs_dir.glob("run-*")):
        if (run_dir / "event_log.jsonl").exists():
            out.extend(compile_events(run_dir))
    return out
