"""分诊路由层(v0.2 设计 §11,P0-3):哪一槽需要人看,策略驱动,版本化。

从 matrix.py 抽出的纯函数。纪律:

- **策略是数据,不是代码**:routing_policy.json 是可替换的 Harness 组件,
  改进层的候选只能编辑它(的 auto_accept_cohorts),不许碰这里的代码;
- **硬阻断不可放松**(v0.2 §11.2):doc 级阻断、槽位阻断、gate fail、
  unsupported、口径争议 —— cohort 匹配再中也不许把它们放出复核;
- **cohort 只能放松软触发**(gate warning 级),且只能引用通用特征
  (field/tier/strength),禁止 doc_id/期望值硬编码(linter 在 improve 侧);
- `routing_report.json` 是 run 的权威工件,进 review_snapshot 成分 ——
  「哪版策略把哪槽送进了队列」必须可离线重算。
"""

from __future__ import annotations

import hashlib
import json

ROUTES = ("auto_accept", "review", "block", "escalate")

#: 软触发:gate warning 级。cohort 只许放松这些;fail/unsupported/阻断/争议
#: 是硬阻断(v0.2 §11.2),cohort 匹配中了也不放行
_SOFT_VERDICTS = ("warning",)


def policy_digest(policy: dict) -> str:
    """策略内容寻址:canonical JSON 的 sha256。"""
    canonical = json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def _verdict_flags(verdicts: dict) -> tuple[list[str], list[str]]:
    fails = sorted(g for g, v in verdicts.items() if v == "fail")
    warns = sorted(g for g, v in verdicts.items() if v == "warning")
    return fails, warns


def _matches_cohort(slot: dict, cohort: dict, tier_of) -> bool:
    """cohort 只许引用通用特征:field / tier / strength。"""
    if cohort.get("field") and cohort["field"] != slot["field"]:
        return False
    if cohort.get("tier") and cohort["tier"] != tier_of(slot["field"]):
        return False
    if cohort.get("strength") and cohort["strength"] != slot["strength"]:
        return False
    return True


def route_slots(slots: list[dict], policy: dict, *, tier_of) -> list[dict]:
    """槽位事实 → 路由决定。输入 slots 的键:

    doc_id, field, strength, gate_verdicts, applicability,
    slot_blocking(bool), doc_blocked(bool)

    输出每槽 {doc_id, field, route, reason_codes}。
    HAR-0001(auto_accept_cohorts 为空)与 matrix 原逻辑逐字节等价:
    requires_adjudication ⟺ route != "auto_accept"。
    """
    cohorts = policy.get("auto_accept_cohorts") or []
    out = []
    for s in slots:
        fails, warns = _verdict_flags(s["gate_verdicts"])
        disputed = s["applicability"] == "label_convention_disputed"
        hard = bool(fails) or s["strength"] == "unsupported" or disputed \
            or s["slot_blocking"]

        if s["doc_blocked"]:
            route, codes = "block", ["INFRA_BLOCKED"]
        elif not hard:
            cohort = next((c for c in cohorts
                           if _matches_cohort(s, c, tier_of)), None)
            if cohort is not None:
                route = "auto_accept"
                codes = [f"POLICY_ACCEPT:{cohort.get('id', '?')}"]
            elif warns:
                route = "review"
                codes = [f"GATE_WARNING:{g}" for g in warns]
            else:
                route, codes = "auto_accept", ["CLEAN"]
        elif s["slot_blocking"]:
            route, codes = "review", ["SLOT_BLOCKING"]
        elif s["strength"] == "unsupported":
            route, codes = "review", ["UNSUPPORTED"]
        elif fails:
            route = "review"
            codes = [f"GATE_FAIL:{g}" for g in fails]
        else:  # disputed
            route, codes = "review", ["LABEL_CONVENTION_DISPUTED"]
        out.append({"doc_id": s["doc_id"], "field": s["field"],
                    "route": route, "reason_codes": codes})
    return out


def build_routing_report(slots: list[dict], policy: dict, *,
                         harness_id: str, tier_of) -> dict:
    """routing_report.json 的内容(确定性工件,进快照成分)。

    policy 全文嵌进报告:deliver/verify 必须能按**本次 run 的策略**重放,
    不是按当前 active 策略(晋升之后旧 run 的说法不许变)。
    """
    return {
        "harness_id": harness_id,
        "policy_digest": policy_digest(policy),
        "policy": policy,
        "routes": route_slots(slots, policy, tier_of=tier_of),
    }
