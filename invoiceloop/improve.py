"""改进控制面(v0.2 收窄版):mine → propose → evaluate → promote。

纪律(与裁决同一宪章):
- 全部确定性、零模型 —— mine 是统计,propose 是脚手架,evaluate 是
  反事实重路由,promote 是唯一写 active 指针的入口且必须人名+理由;
- 候选只能给 auto_accept_cohorts 加条目,只许引用通用特征
  (field/tier/strength)—— diff linter 硬性执行;
- 报告只说明「这些复核没产生修正」,不说「这些复核没价值」 ——
  没被抽查不等于没有错(v0.2 §9.4 选择偏差),这句话印在每份 mine 报告头部。
"""

from __future__ import annotations

import json
from pathlib import Path

from .feedback import compile_workspace
from .fields import FIELDS, TIER1
from .routing import policy_digest

#: cohort 允许的特征键(linter 白名单;其余一律拒)
_COHORT_KEYS = ("id", "field", "tier", "strength")
_STRENGTHS = ("unsupported", "single_source", "corroborated")

_SELECTION_BIAS_WARNING = (
    "选择偏差警告:本报告只说明「这些复核没产生修正」,不说「这些复核没价值」"
    "—— 没被抽查不等于没有错(v0.2 §9.4)。任何 cohort 放宽都必须经过 "
    "evaluate 的反事实比较与人工 promote,本报告本身不授权任何改动。"
)


# ---------------------------------------------------------------------- mine

def mine(workspace: Path) -> dict:
    """聚合全部裁决事件 → cohort 统计。cohort key = field × tier ×
    support_strength × route。找「高频复核、零修正」的候选放松对象。"""
    events = compile_workspace(workspace)
    cohorts: dict[tuple, dict] = {}
    for e in events:
        key = (e["field"], e["tier"], e.get("support_strength"),
               e.get("route") or "unknown")
        c = cohorts.setdefault(key, {
            "field": e["field"], "tier": e["tier"],
            "support_strength": e.get("support_strength"),
            "route": e.get("route"),
            "reviewed": 0, "accepted": 0, "corrected": 0, "rejected": 0,
            "confirmed_absent": 0, "not_applicable": 0, "abstained": 0,
        })
        c["reviewed"] += 1
        action = e["human_action"]
        if action == "accept":
            c["accepted"] += 1
        elif action == "correct":
            c["corrected"] += 1
        elif action == "reject":
            c["rejected"] += 1
        elif action == "confirm_absent":
            c["confirmed_absent"] += 1
        elif action == "not_applicable":
            c["not_applicable"] += 1
        elif action == "abstain":
            c["abstained"] += 1
    # 低收益候选:复核 ≥3 次、零修正零拒绝(阈值是探索性默认值,不是安全证明)
    low_yield = [c for c in cohorts.values()
                 if c["reviewed"] >= 3 and c["corrected"] == 0
                 and c["rejected"] == 0]
    report = {
        "warning": _SELECTION_BIAS_WARNING,
        "events": len(events),
        "cohorts": sorted(cohorts.values(),
                          key=lambda c: (-c["reviewed"], c["field"])),
        "low_yield_candidates": sorted(low_yield,
                                       key=lambda c: -c["reviewed"]),
    }
    out_dir = Path(workspace) / "improve"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "mine_report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


# ------------------------------------------------------------------- propose

def lint_policy(parent: dict, candidate: dict) -> list[str]:
    """候选策略 diff 审查。返回违规列表(空 = 通过)。只允许给
    auto_accept_cohorts 加条目,且条目只引用通用特征。"""
    violations = []
    for key in set(parent) | set(candidate):
        if key in ("auto_accept_cohorts", "harness_id", "version"):
            continue  # cohorts 单独查;harness_id/version 是身份字段,必然变
        if parent.get(key) != candidate.get(key):
            violations.append(f"候选改了 {key} —— 第一版只允许加 cohorts")
    parent_ids = {c.get("id") for c in parent.get("auto_accept_cohorts", [])}
    for cohort in candidate.get("auto_accept_cohorts", []):
        if set(cohort) - set(_COHORT_KEYS):
            violations.append(
                f"cohort 含白名单外特征 {sorted(set(cohort) - set(_COHORT_KEYS))}"
                f" —— 只许 {_COHORT_KEYS}")
            continue
        if cohort.get("id") in parent_ids:
            continue  # 既有条目,不动
        if not cohort.get("id"):
            violations.append("cohort 缺 id")
        if cohort.get("field") and cohort["field"] not in FIELDS:
            violations.append(f"cohort field {cohort['field']!r} 不是受评字段")
        if cohort.get("tier") and cohort["tier"] not in ("TIER1", "TIER2"):
            violations.append(f"cohort tier {cohort['tier']!r} 非法")
        if cohort.get("strength") and cohort["strength"] not in _STRENGTHS:
            violations.append(f"cohort strength {cohort['strength']!r} 非法")
    return violations


def propose(workspace: Path, *, cohort: dict, finding: str,
            prediction: str) -> Path:
    """从 active 策略派生候选 harness(只加一条 cohort)。返回候选目录。"""
    from .harness import load_active

    workspace = Path(workspace)
    active = load_active(workspace)
    parent = active["policy"]
    candidate = {**parent,
                 "auto_accept_cohorts": parent.get("auto_accept_cohorts", [])
                 + [cohort]}
    violations = lint_policy(parent, candidate)
    if violations:
        raise ValueError(f"候选 diff 审查未过:{violations}")

    harnesses = workspace / "harnesses"
    existing = sorted(p.name for p in harnesses.glob("HAR-*")) \
        if harnesses.exists() else []
    # 包内 HAR-0001 不在 workspace 里,也算已占用
    seq = max([int(h.split("-")[1]) for h in existing] + [1]) + 1
    cand_id = f"HAR-{seq:04d}"
    cand_dir = harnesses / cand_id
    cand_dir.mkdir(parents=True)
    candidate["harness_id"] = cand_id
    candidate["version"] = parent.get("version", 1) + 1
    (cand_dir / "routing_policy.json").write_text(
        json.dumps(candidate, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (cand_dir / "manifest.json").write_text(json.dumps({
        "harness_id": cand_id,
        "parent_harness_id": active["harness_id"],
        "status": "candidate",
        "created_from_findings": [finding],
        "prediction": prediction,
        "policy_digest": policy_digest(candidate),
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return cand_dir


# ------------------------------------------------------------------ evaluate

def evaluate(workspace: Path, candidate_id: str) -> dict:
    """反事实重路由:用候选策略重算**已有 run** 的路由,与现状并排。

    不重跑 pipeline(矩阵行已带全部槽位事实);零 API、确定性。
    报告:复核负载变化、哪些槽被放松、被放松槽的裁决结果(若已人裁)——
    「这些槽人裁时有没有修正」是候选安全性的直接证据。
    """
    from .harness import load_active
    from .routing import route_slots

    workspace = Path(workspace)
    active = load_active(workspace)
    cand_policy = json.loads(
        (workspace / "harnesses" / candidate_id / "routing_policy.json")
        .read_text(encoding="utf-8"))
    violations = lint_policy(active["policy"], cand_policy)
    if violations:
        raise ValueError(f"候选 diff 审查未过:{violations}")

    runs = sorted((workspace / "runs").glob("run-*"))
    comparisons = []
    for run_dir in runs:
        if not (run_dir / "event_log.jsonl").exists():
            continue
        matrix = json.loads(
            (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
        facts = [{
            "doc_id": r["doc_id"], "field": r["field"],
            "strength": r["support_strength"],
            "gate_verdicts": r["gate_verdicts"],
            "applicability": r["applicability"],
            # 矩阵行不区分槽位/文档级阻断;统一按槽位阻断处理 —— 两者都是
            # 硬阻断,cohort 都放不出去,复核计数一致
            "slot_blocking": bool(r["blocking_findings"]),
            "doc_blocked": False,
        } for r in matrix["rows"]]
        base_routes = {
            r["doc_id"] + "|" + r["field"]:
                r.get("route")  # 2026-08-05 前的 run 没有 route 键,用 requires 推
                or ("review" if r.get("requires_adjudication") else "auto_accept")
            for r in matrix["rows"]
        }
        cand_routes = route_slots(facts, cand_policy, tier_of=_tier_of)
        relaxed = []
        for r in cand_routes:
            key = r["doc_id"] + "|" + r["field"]
            if base_routes.get(key) != "auto_accept" and r["route"] == "auto_accept":
                relaxed.append(key)
        comparisons.append({
            "run": run_dir.name,
            "slots": len(matrix["rows"]),
            "baseline_review": sum(1 for v in base_routes.values()
                                   if v != "auto_accept"),
            "candidate_review": sum(1 for r in cand_routes
                                    if r["route"] != "auto_accept"),
            "relaxed_slots": sorted(relaxed),
        })
    total_slots = sum(c["slots"] for c in comparisons)
    total_base = sum(c["baseline_review"] for c in comparisons)
    total_cand = sum(c["candidate_review"] for c in comparisons)
    result = {
        "candidate": candidate_id,
        "baseline_harness": active["harness_id"],
        "runs": comparisons,
        "review_load_baseline": total_base / max(total_slots, 1),
        "review_load_candidate": total_cand / max(total_slots, 1),
        "delta_pp": (total_cand - total_base) / max(total_slots, 1) * 100,
        "note": ("反事实重路由(不重跑抽取与门禁);「被放松槽是否有害」"
                 "需要 EVO 语料的真值评测(sealed 协议),本报告不给安全性结论"),
    }
    out = workspace / "improve" / f"eval_{candidate_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return result


def _tier_of(field: str) -> str:
    return "TIER1" if field in TIER1 else "TIER2"


# ------------------------------------------------------------------- promote

def promote(workspace: Path, candidate_id: str, *, approved_by: str,
            rationale: str, approved_at: str) -> dict:
    """人工晋升:写 PROM 记录 + active 指针。唯一写 active 的入口。

    时间由人给(与裁决同一纪律:工件不读墙钟)。
    """
    from datetime import datetime

    if not approved_by.strip():
        raise ValueError("promote 必须给 approved_by —— 晋升是人的决定,要署名")
    if not rationale.strip():
        raise ValueError("promote 必须给 rationale —— 接受了什么残余风险要写清")
    try:
        datetime.fromisoformat(approved_at.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("approved_at 必须是 ISO 8601 时间,由人给出") from None

    workspace = Path(workspace)
    cand_dir = workspace / "harnesses" / candidate_id
    manifest_path = cand_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"候选 {candidate_id} 不存在({cand_dir})")
    import hashlib

    from .harness import load_active

    active = load_active(workspace)
    improve_dir = workspace / "improve"
    promotions_dir = improve_dir / "promotions"
    promotions_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(promotions_dir.glob("PROM-*.json"))) + 1
    cand_policy_bytes = (cand_dir / "routing_policy.json").read_bytes()
    eval_path = improve_dir / f"eval_{candidate_id}.json"
    record = {
        "promotion_id": f"PROM-{seq:04d}",
        "from_harness_id": active["harness_id"],
        "to_harness_id": candidate_id,
        "candidate_policy_digest": hashlib.sha256(cand_policy_bytes).hexdigest(),
        "baseline_policy_digest": active["policy_digest"],
        "eval_result_digest": hashlib.sha256(eval_path.read_bytes()).hexdigest()
        if eval_path.exists() else None,
        # 命名诚实(评审裁决五):没有未见资格集(PROMOTION set)的晋升
        # 只是 demo activation;「在未见数据上安全减负」不许这么声称
        "basis": "evo_replay_only",
        "claim_limits": "未经未见资格集评测 —— 公开口径仅限「实现了有界改进机制」,"
                        "不得声称「在未见数据上减少人工」",
        "approved_by": approved_by.strip(),
        "approved_at": approved_at.strip(),
        "rationale": rationale.strip(),
        "rollback_harness_id": active["harness_id"],
    }
    (promotions_dir / f"PROM-{seq:04d}.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "active"
    manifest_path.write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (improve_dir / "active_harness.json").write_text(json.dumps(
        {"harness_id": candidate_id, "promotion_id": record["promotion_id"]},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def rollback(workspace: Path, *, to_harness_id: str, approved_by: str,
             rationale: str, approved_at: str) -> dict:
    """回滚 = 新的 PROM 记录(append-only;评审裁决七:active 指针只是投影,
    权威是晋升记录链;回滚也必须署名,不许直接改指针)。

    回滚目标是包内默认(HAR-0001)时先把它物化进 workspace harnesses/,
    promote 才有候选可读。
    """
    from .harness import DEFAULT_HARNESS, _builtin_policy

    workspace = Path(workspace)
    target = workspace / "harnesses" / to_harness_id
    if not target.exists():
        if to_harness_id != DEFAULT_HARNESS:
            raise ValueError(f"回滚目标 {to_harness_id} 不在 workspace harnesses/")
        target.mkdir(parents=True)
        policy = _builtin_policy()
        (target / "routing_policy.json").write_text(
            json.dumps(policy, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (target / "manifest.json").write_text(json.dumps({
            "harness_id": to_harness_id, "parent_harness_id": None,
            "status": "candidate", "note": "回滚目标:包内默认策略的物化副本",
            "policy_digest": policy_digest(policy),
        }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return promote(workspace, to_harness_id, approved_by=approved_by,
                   rationale=f"ROLLBACK:{rationale}", approved_at=approved_at)
