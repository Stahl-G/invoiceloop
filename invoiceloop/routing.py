"""Triage routing (v0.2 design §11, P0-3): which slot needs a human — policy
driven, and versioned.

Extracted from matrix.py as pure functions. The discipline:

- **Policy is data, not code.** routing_policy.json is a replaceable harness
  component; an improvement-layer candidate may edit its auto_accept_cohorts
  and nothing in this file.
- **Hard blocks never relax** (v0.2 §11.2): document-level blocks, slot blocks,
  gate failures, unsupported rows and convention disputes stay in review no
  matter how well a cohort matches.
- **A cohort may only relax soft triggers** (gate warnings), and may only
  reference general features (field / tier / strength). Hardcoding a doc_id or
  an expected value is forbidden; the linter for that lives on the improve side.
- `routing_report.json` is an authoritative run artifact and a review_snapshot
  component — "which policy version put which slot in the queue" must be
  recomputable offline.
"""

from __future__ import annotations

import hashlib
import json

ROUTES = ("auto_accept", "auto_absent", "review", "block", "escalate")

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


def _qa_hit(policy: dict, doc_id: str, field: str, kind: str) -> bool:
    """确定性 QA 抽样(评审裁决四):哈希采样,不是随机数 ——

    同 seed + harness + doc + field 永远同一结果;不受遍历顺序影响;
    seed 与 sampler 版本嵌在 policy 里,verify 可重算,「同输入同字节」不破。
    没有采样器的 review_probability 是虚假的倾向分 —— 这个函数就是它。
    """
    qa = policy.get("qa") or {}
    rate = float(qa.get(f"{kind}_rate", 0.0))
    if rate <= 0.0:
        return False
    key = (f"{qa.get('seed', '')}|{policy.get('harness_id', '')}"
           f"|{doc_id}|{field}|qa-hash-v1")
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < rate


def apply_absent_expected(facts: list[dict], policy: dict) -> list[dict]:
    """把策略的 absent_expected cohort 作用到槽位事实上(extraction_present
    fail → expected_absent)。run 时这是 run_gates 在 gate_report 里直接
    写的;反事实评测(evaluate)拿旧 gate_report 重放时需要同一变换 ——
    两处同一函数,不许各写一份。"""
    fields = {c.get("field")
              for c in (policy.get("absent_expected_cohorts") or [])}
    if not fields:
        return facts
    out = []
    for s in facts:
        if s["field"] in fields \
                and s["gate_verdicts"].get("extraction_present") == "fail":
            s = {**s, "gate_verdicts": {
                **s["gate_verdicts"], "extraction_present": "expected_absent"}}
        out.append(s)
    return out


def route_slots(slots: list[dict], policy: dict, *, tier_of) -> list[dict]:
    """槽位事实 → 路由决定。输入 slots 的键:

    doc_id, field, strength, gate_verdicts, applicability,
    slot_blocking(bool), doc_blocked(bool)

    输出每槽 {doc_id, field, route, reason_codes}。
    HAR-0001(auto_accept_cohorts 为空)与 matrix 原逻辑逐字节等价:
    requires_adjudication ⟺ route != "auto_accept"。
    QA 抽样只命中两类自动放行槽:policy_accepted TIER1(5%)与
    cohort 放松槽(首批 20%)—— HAR-0001 两者皆空,零影响。
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
        elif (s["gate_verdicts"].get("extraction_present") == "expected_absent"
                and not fails and not s["slot_blocking"]):
            # 预期缺失(absent_expected cohort,政策词表第二类):
            # 缺值的事实已在门禁层照记(verdict=expected_absent,非 pass),
            # 这里给的是后果 —— 政策确认缺失,不进人工队列;
            # QA 抽样(默认 20%)盯着「缺席是否真的成立」
            if _qa_hit(policy, s["doc_id"], s["field"], "absent_expected"):
                route = "review"
                codes = [f"EXPECTED_ABSENT:{s['field']}",
                         f"QA_SAMPLE:expected_absent"]
            else:
                route = "auto_absent"
                codes = [f"EXPECTED_ABSENT:{s['field']}"]
        elif not hard:
            cohort = next((c for c in cohorts
                           if _matches_cohort(s, c, tier_of)), None)
            if cohort is not None:
                cid = cohort.get("id", "?")
                if _qa_hit(policy, s["doc_id"], s["field"], "cohort_relax"):
                    route = "review"
                    codes = [f"POLICY_ACCEPT:{cid}", f"QA_SAMPLE:{cid}"]
                else:
                    route = "auto_accept"
                    codes = [f"POLICY_ACCEPT:{cid}"]
            elif warns:
                route = "review"
                codes = [f"GATE_WARNING:{g}" for g in warns]
            elif (not policy.get("release_tier1_explicit", True)
                    and tier_of(s["field"]) == "TIER1"
                    and _qa_hit(policy, s["doc_id"], s["field"],
                                "policy_accepted_tier1")):
                # 策略放行的 TIER1 槽按 5% 抽检进人工队列
                route = "review"
                codes = ["CLEAN", "QA_SAMPLE:policy_accepted_tier1"]
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
