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
    superseded_ids = {d.get("supersedes_decision_id") for d in decisions
                      if d.get("supersedes_decision_id")}
    for i, d in enumerate(decisions, start=1):
        row = rows.get((d["doc_id"], d["field"]), {})
        reason_codes = row.get("reason_codes", [])
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
            "route_reason_codes": reason_codes,
            "support_strength": row.get("support_strength"),
            "human_action": d["decision"],
            "reason_code": d.get("reason_code"),
            "reviewer_confidence": d.get("reviewer_confidence"),
            # 反馈可用性(v0.2 §5.2;2026-08-06 修订):心码 + 非弃权 +
            # 人没有**主动**标「没把握」。
            #
            # 原判据要求 reviewer_confidence ∈ {high, medium}。run-0002 实测
            # 填写率 3/123,mine 的合格事件 0 —— 整条挖掘臂从未点火。改判据
            # 的依据是不对称性:主动标 low 是真信息;未填**不等于**有把握,
            # 而自评把握度从未被验证与正确率相关(run-0002 反例:被试在未标
            # 低把握的情况下填进形状可疑的税号)。同一个风险已由 QA 探针
            # 测量式守卫(cohort 放松 20%、policy_accepted TIER1 5%),
            # 不靠自评。心码仍是硬要求 —— 没有心码就没有监督标签。
            "actionable": bool(
                d.get("reason_code")
                and d.get("reviewer_confidence") != "low"
                and d["decision"] != "abstain"),
            # 反馈质量门(83 评问题三):被后续裁决顶替的事件不是当前真相;
            # QA 抽查槽是随机探针,不能当「这条路由规则错了」的证据
            "superseded": d["decision_id"] in superseded_ids,
            "random_qa": any(str(c).startswith("QA_SAMPLE:") for c in reason_codes),
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
