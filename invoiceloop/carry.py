"""carry —— 同证据裁决携带:人裁过的东西,证据一个字没变,不再问第二次。

动机(2026-08-06 用户实测):换 harness 开新 run 后,复核队列里大量槽位
是「同一份证据,人上一轮已经判过」。重问一遍是纯浪费 —— 但直接跳过
又是伪造人工。携带的规则是机械的、可验证的:

- accept/reject:新 run 的 understand 声明存在,且**值与 span 绑定逐位
  等于**旧声明(值变了、绑定变了、声明没了 —— 都回人);
- correct:新 run 该槽的 DWS 原值与旧 run 相同(人补的值才有意义);
- confirm_absent / not_applicable:新 run 该槽**没有** understand 声明
  (有声明 = 证据变了,回人);
- abstain 永不携带(未决就是未决);
- 每条携带记录带 carried_from_decision_id 溯源 —— 它不是新的人工
  判断,是同一个人对同一份证据的判断的机械搬运,账本里看得清清楚楚。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import adjudicate as adj


def _tips(run_dir: Path) -> dict[tuple[str, str], dict]:
    tips: dict[tuple[str, str], dict] = {}
    ledger = run_dir / "adjudication_ledger.jsonl"
    if not ledger.exists():
        return tips
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            tips[(d["doc_id"], d["field"])] = d
    return tips


def _understand_claims(run_dir: Path) -> dict[tuple[str, str], dict]:
    ledger = json.loads(
        (run_dir / "field_ledger.json").read_text(encoding="utf-8"))
    return {(c["doc_id"], c["field"]): c
            for c in ledger["claims"] if c["drafted_by"] == "dws_understand"}


def _raw_values(run_dir: Path) -> dict[tuple[str, str], object]:
    """每槽的 DWS understand 原值(矩阵行的 value 字段即此)。"""
    matrix = json.loads(
        (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    return {(r["doc_id"], r["field"]): r.get("value") for r in matrix["rows"]}


def _claim_matches(src_claim: dict | None, dst_claim: dict | None) -> bool:
    """携带判据:值与 span 绑定逐位一致。"""
    if src_claim is None or dst_claim is None:
        return False
    return src_claim.get("value") == dst_claim.get("value") \
        and sorted(src_claim.get("span_ids") or []) \
        == sorted(dst_claim.get("span_ids") or [])


def carry_forward(dst_run: Path, *, decided_at: str) -> dict:
    """把同一 workspace 内**更早** run 的裁决按规则携带进 dst_run。

    返回计数报告{carried, skipped_changed, no_prior, skipped_auto}。
    decided_at 由人给(执行 carry 这个动作就是人在给时间,与工作台同纪律)。
    """
    dst_run = Path(dst_run)
    runs_dir = dst_run.parent
    prior = sorted(p for p in runs_dir.glob("run-*")
                   if p.name < dst_run.name
                   and (p / "adjudication_ledger.jsonl").exists())
    # 跨 run 的 tip:按 run 代序,后 run 的覆盖先 run 的(裁决链的时间序)
    tips: dict[tuple[str, str], dict] = {}
    for p in prior:
        tips.update(_tips(p))

    routing = json.loads((dst_run / "routing_report.json").read_text())
    routes = {(r["doc_id"], r["field"]): r["route"] for r in routing["routes"]}
    dst_claims = _understand_claims(dst_run)
    src_claims: dict[tuple[str, str], dict] = {}
    for p in reversed(prior):  # 最近的旧 run 优先
        for k, c in _understand_claims(p).items():
            src_claims.setdefault(k, c)
    src_raw = {k: v for p in reversed(prior)
               for k, v in _raw_values(p).items()}
    dst_raw = _raw_values(dst_run)

    report = {"carried": 0, "skipped_changed": 0, "no_prior": 0,
              "skipped_auto": 0, "kept_qa_fresh": 0, "by_decision": {}}
    for (doc_id, field), route in sorted(routes.items()):
        if route in ("auto_accept", "auto_absent"):
            report["skipped_auto"] += 1
            continue
        codes = next((r["reason_codes"] for r in routing["routes"]
                      if r["doc_id"] == doc_id and r["field"] == field), [])
        if any(str(c).startswith("QA_SAMPLE:") for c in codes):
            # QA 探针要保持新鲜人眼:搬旧裁决进去 = 探针失效。
            # 它们留在队列里,就几槽(2026-08-06 run-0006 实证:全量携带
            # 把 5% 的 policy_accepted 抽检也填了,设计意图被破坏)
            report["kept_qa_fresh"] += 1
            continue
        tip = tips.get((doc_id, field))
        if tip is None:
            report["no_prior"] += 1
            continue
        decision = tip["decision"]
        dst_claim = dst_claims.get((doc_id, field))
        if decision in ("accept", "reject"):
            if not _claim_matches(src_claims.get((doc_id, field)), dst_claim):
                report["skipped_changed"] += 1
                continue
            claim_id = dst_claim["claim_id"]
            corrected = None
        elif decision == "correct":
            if src_raw.get((doc_id, field)) != dst_raw.get((doc_id, field)):
                report["skipped_changed"] += 1
                continue
            claim_id = dst_claim["claim_id"] if dst_claim else None
            corrected = tip.get("corrected_value")
        elif decision in ("confirm_absent", "not_applicable"):
            if dst_claim is not None:
                report["skipped_changed"] += 1  # 证据变了:现在有声明了
                continue
            claim_id = None
            corrected = None
        else:  # abstain:未决不携带
            report["skipped_changed"] += 1
            continue
        reason_code = tip.get("reason_code")
        if reason_code is None and decision == "confirm_absent":
            reason_code = "CONFIRMED_ABSENT"  # combo 表 1:1 蕴含,不是编
        elif reason_code is None and decision == "not_applicable":
            reason_code = "NOT_APPLICABLE"
        adj.append_adjudication(
            dst_run,
            claim_id=claim_id,
            doc_id=doc_id, field=field,
            decision=decision,
            rationale=f"[carried from {tip['decision_id']}] {tip['rationale']}",
            adjudicator=tip["adjudicator"],
            decided_at=decided_at,
            corrected_value=corrected,
            reason_code=reason_code,
            reviewer_confidence=tip.get("reviewer_confidence"),
            carried_from_decision_id=tip["decision_id"],
        )
        report["carried"] += 1
        report["by_decision"][decision] = \
            report["by_decision"].get(decision, 0) + 1
    return report
