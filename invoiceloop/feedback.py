"""The feedback plane: reason codes and reviewer confidence, so the mining arm has
something to mine.

Both are optional. An unfilled reason code is not filled in on the reviewer's
behalf — the system reports the gap rather than deciding for a person
(charter rule four).
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
    gate_path = run_dir / "gate_report.json"
    document_checks = {}
    if gate_path.exists():
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        raw_checks = gate.get("document_checks")
        document_checks = raw_checks if isinstance(raw_checks, dict) else {}

    events = []
    superseded_ids = {d.get("supersedes_decision_id") for d in decisions
                      if d.get("supersedes_decision_id")}
    for i, d in enumerate(decisions, start=1):
        row = rows.get((d["doc_id"], d["field"]), {})
        reason_codes = row.get("reason_codes", [])
        from .doctype import trusted_class

        check = document_checks.get(d["doc_id"])
        doc_class = trusted_class(check)
        events.append({
            "feedback_id": f"FB-{i:06d}",
            "decision_id": d["decision_id"],
            "run": run_dir.name,
            "review_snapshot_id": d.get("review_snapshot_id"),
            "harness_id": harness_id,
            "doc_id": d["doc_id"],
            "field": d["field"],
            # 类别只有冻结字面证据完整通过时才进入改进特征。模型自报、
            # fail/unmapped/no_claim/旧 run 一律不给 mine 猜。
            "doctype_status": "pass" if doc_class is not None else "untrusted",
            "doc_class": doc_class,
            "tier": "TIER1" if d["field"] in TIER1 else "TIER2",
            "claim_id": d.get("claim_id"),
            "route": row.get("route"),
            "route_reason_codes": reason_codes,
            "support_strength": row.get("support_strength"),
            "human_action": d["decision"],
            # 人手打的那段话(必填项)。2026-08-06 之前它压根没进反馈层 ——
            # 复核者写的每一条观察都停在裁决账本里,改进循环看不见。
            # 纪律:**原文透传,不解析**。它是给写 cohort 提案的人读的,
            # 不是给机器当特征的 —— 自由文本 → 策略需要模型,而模型不许
            # 进确定性路径(gates.py 首行),更不许由它提议放松安全规则。
            "rationale": d.get("rationale"),
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
