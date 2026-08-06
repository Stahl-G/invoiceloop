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

import hashlib
import json
from pathlib import Path

from .feedback import compile_workspace
from .fields import FIELDS, TIER1
from .routing import policy_digest

#: cohort 允许的特征键(linter 白名单;其余一律拒)
_COHORT_KEYS = ("id", "field", "tier", "strength")
#: 预期缺失 cohort 的词表更窄:只有 field 有意义(缺失没有 strength)
_ABSENT_KEYS = ("id", "field")
_STRENGTHS = ("unsupported", "single_source", "corroborated")

_SELECTION_BIAS_WARNING = (
    "选择偏差警告:本报告只说明「这些复核没产生修正」,不说「这些复核没价值」"
    "—— 没被抽查不等于没有错(v0.2 §9.4)。任何 cohort 放宽都必须经过 "
    "evaluate 的反事实比较与人工 promote,本报告本身不授权任何改动。"
)


# ---------------------------------------------------------------------- mine

def mine(workspace: Path) -> dict:
    """聚合裁决事件 → cohort 统计。cohort key = field × tier ×
    support_strength × route。找「高频复核、零修正」的候选放松对象。

    反馈质量门(83 评问题三;2026-08-06 修订把握度判据):cohort 统计
    只用**合格事件** —— actionable(心码 ∧ 非弃权 ∧ 未主动标低把握)
    ∧ 未被顶替 ∧ 非 QA 随机探针。
    全量口径并列展示,但低收益候选只从合格集出 —— 否则「放松建议」
    建立在人没把握或已被修正的记录上。
    """
    events = compile_workspace(workspace)
    qualified = [e for e in events
                 if e["actionable"] and not e["superseded"]
                 and not e["random_qa"]]
    buckets = {
        "all_events": len(events),
        "actionable": sum(1 for e in events if e["actionable"]),
        "superseded": sum(1 for e in events if e["superseded"]),
        "random_qa": sum(1 for e in events if e["random_qa"]),
        "qualified_for_mining": len(qualified),
        "not_actionable_reasons": {
            "no_reason_code": sum(1 for e in events if not e["reason_code"]),
            # 只数**主动**标低的;未填不再计入(2026-08-06,见 feedback.py)
            "low_confidence": sum(
                1 for e in events if e["reviewer_confidence"] == "low"),
            "abstain": sum(1 for e in events
                           if e["human_action"] == "abstain"),
        },
    }
    cohorts: dict[tuple, dict] = {}
    for e in qualified:
        key = (e["field"], e["tier"], e.get("support_strength"),
               e.get("route") or "unknown")
        c = cohorts.setdefault(key, {
            "field": e["field"], "tier": e["tier"],
            "support_strength": e.get("support_strength"),
            "route": e.get("route"),
            "reviewed": 0, "accepted": 0, "corrected": 0, "rejected": 0,
            "confirmed_absent": 0, "not_applicable": 0, "abstained": 0,
            "notes": [],
        })
        c["reviewed"] += 1
        # 复核者手打的原话,按 cohort 归堆(2026-08-06)。**原文,不解析**:
        # 这一栏是给写 cohort 提案的人读的 —— 上一条 cohort(absent_expected)
        # 就是人读完 run-0002 报告手写的,这里只是把「读什么」从 123 行账本
        # 收敛到「这个 cohort 里大家究竟说了什么」。机器不从中提取特征。
        note = (e.get("rationale") or "").strip()
        if note:
            c["notes"].append({"doc_id": e["doc_id"],
                               "decision": e["human_action"],
                               "reason_code": e.get("reason_code"),
                               "rationale": note})
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
    # 预期缺失候选(2026-08-06 HITL 实测发现:美国发票无 VAT,
    # seller_vat_id 的 confirm_absent 占了整整一类人工 —— 这类重复
    # 「页面上没有」的确认应该由 absent_expected cohort 接走):
    # 某字段的合格事件里 confirm_absent/not_applicable ≥3 且占 ≥80%
    by_field: dict[str, dict] = {}
    for e in qualified:
        f = by_field.setdefault(e["field"], {"field": e["field"], "total": 0,
                                             "absentish": 0, "notes": []})
        f["total"] += 1
        if e["human_action"] in ("confirm_absent", "not_applicable"):
            f["absentish"] += 1
            note = (e.get("rationale") or "").strip()
            if note:
                # 提案要不要写、怎么写,人读这些原话决定 —— 候选是线索,
                # 不是授权(mine 的选择偏差警告同一条)
                f["notes"].append({"doc_id": e["doc_id"], "rationale": note})
    absence_candidates = [
        {**f, "share": f["absentish"] / f["total"],
         "suggested": {"kind": "absent_expected",
                       "cohort": {"field": f["field"]}}}
        for f in by_field.values()
        if f["absentish"] >= 3 and f["absentish"] / f["total"] >= 0.8
    ]
    # 撤销信号(2026-08-06):被策略自动放行、又被人推翻的槽。
    # **方向与上面两类相反** —— low_yield/absence 是放松的线索,这一类是
    # 收紧的证据,所以不进 candidates,单列。判据只要一条:auto_* 路由 +
    # 人给了 correct/reject。一条就报,不设频次门槛 —— 放松要证据、
    # 收紧要及时,两边不对称是故意的(安全方向优先,宪章四)。
    # 事件已过合格门(非 QA 探针会被排除),所以这里额外把 QA 探针也算上:
    # 抽检抓到的推翻正是探针存在的理由,不能因为它是随机抽的就不算数。
    overturned = [
        {"field": e["field"], "doc_id": e["doc_id"], "route": e.get("route"),
         "human_action": e["human_action"], "reason_code": e.get("reason_code"),
         "rationale": (e.get("rationale") or "").strip(),
         "random_qa": e["random_qa"], "harness_id": e["harness_id"]}
        for e in events
        if str(e.get("route") or "").startswith("auto_")
        and e["human_action"] in ("correct", "reject")
        and not e["superseded"]
    ]
    report = {
        "warning": _SELECTION_BIAS_WARNING,
        "events": len(events),
        "buckets": buckets,
        "cohorts": sorted(cohorts.values(),
                          key=lambda c: (-c["reviewed"], c["field"])),
        "overturned_auto_accepts": sorted(
            overturned, key=lambda o: (o["field"], o["doc_id"])),
        "low_yield_candidates": sorted(low_yield,
                                       key=lambda c: -c["reviewed"]),
        "absence_candidates": sorted(absence_candidates,
                                     key=lambda c: -c["absentish"]),
    }
    out_dir = Path(workspace) / "improve"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "mine_report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


# ------------------------------------------------------------------- propose

def lint_policy(parent: dict, candidate: dict) -> list[str]:
    """候选策略 diff 审查。返回违规列表(空 = 通过)。只允许给
    auto_accept_cohorts / absent_expected_cohorts 加条目,
    且条目只引用各自白名单内的通用特征。"""
    violations = []
    for key in set(parent) | set(candidate):
        if key in ("auto_accept_cohorts", "absent_expected_cohorts",
                   "harness_id", "version"):
            continue  # cohorts 单独查;harness_id/version 是身份字段,必然变
        if key == "qa":
            # 唯一允许的 qa 变化:新增 absent_expected_rate(预期缺失的
            # 抽检探针率)—— 其余键一律不许动
            pq, cq = parent.get("qa") or {}, candidate.get("qa") or {}
            changed = {k for k in set(pq) | set(cq)
                       if pq.get(k) != cq.get(k)}
            if changed - {"absent_expected_rate"}:
                violations.append(
                    f"候选改了 qa 的 {sorted(changed - {'absent_expected_rate'})}"
                    " —— 只许新增 absent_expected_rate")
            continue
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
    absent_parent_ids = {c.get("id")
                         for c in parent.get("absent_expected_cohorts", [])}
    for cohort in candidate.get("absent_expected_cohorts", []):
        if set(cohort) - set(_ABSENT_KEYS):
            violations.append(
                f"预期缺失 cohort 含白名单外特征 "
                f"{sorted(set(cohort) - set(_ABSENT_KEYS))} —— 只许 {_ABSENT_KEYS}")
            continue
        if cohort.get("id") in absent_parent_ids:
            continue
        if not cohort.get("id"):
            violations.append("预期缺失 cohort 缺 id")
        if cohort.get("field") not in FIELDS:
            violations.append(
                f"预期缺失 cohort field {cohort.get('field')!r} 不是受评字段")
    return violations


def _scaffold_candidate(workspace: Path, candidate: dict, *,
                        finding: str, prediction: str,
                        provenance: str) -> Path:
    """写 harnesses/HAR-NNNN/{routing_policy,manifest}.json。返回候选目录。"""
    from .harness import load_active

    workspace = Path(workspace)
    active = load_active(workspace)
    harnesses = workspace / "harnesses"
    existing = sorted(p.name for p in harnesses.glob("HAR-*")) \
        if harnesses.exists() else []
    # 包内 HAR-0001 不在 workspace 里,也算已占用
    seq = max([int(h.split("-")[1]) for h in existing] + [1]) + 1
    cand_id = f"HAR-{seq:04d}"
    cand_dir = harnesses / cand_id
    cand_dir.mkdir(parents=True)
    candidate["harness_id"] = cand_id
    candidate["version"] = active["policy"].get("version", 1) + 1
    (cand_dir / "routing_policy.json").write_text(
        json.dumps(candidate, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (cand_dir / "manifest.json").write_text(json.dumps({
        "harness_id": cand_id,
        "parent_harness_id": active["harness_id"],
        "provenance": provenance,
        "created_from_findings": [finding],
        "prediction": prediction,
        "policy_digest": policy_digest(candidate),
        # manifest 只记出生事实,创建后不可改(高级裁决五):active/rollback
        # 状态全部从 PROM 链投影,这里没有 status 字段 —— 不当第二权威
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return cand_dir


def propose(workspace: Path, *, cohort: dict, finding: str,
            prediction: str, kind: str = "auto_accept") -> Path:
    """从 active 策略派生候选 harness(只加一条 cohort)。返回候选目录。

    kind = "auto_accept"(软触发放松)| "absent_expected"(预期缺失 ——
    人反复 confirm_absent 的字段,缺失本身被政策确认;QA 抽检盯着)。
    """
    from .harness import load_active

    workspace = Path(workspace)
    active = load_active(workspace)
    parent = active["policy"]
    if kind == "absent_expected":
        candidate = {**parent,
                     "absent_expected_cohorts":
                     parent.get("absent_expected_cohorts", []) + [cohort]}
        # 预期缺失必须带 QA 探针(缺席是否成立要持续观测)
        qa = dict(candidate.get("qa") or {})
        qa.setdefault("absent_expected_rate", 0.20)
        candidate["qa"] = qa
    elif kind == "auto_accept":
        candidate = {**parent,
                     "auto_accept_cohorts": parent.get("auto_accept_cohorts", [])
                     + [cohort]}
    else:
        raise ValueError(f"未知 cohort 类型 {kind!r}")
    violations = lint_policy(parent, candidate)
    if violations:
        raise ValueError(f"候选 diff 审查未过:{violations}")
    return _scaffold_candidate(workspace, candidate, finding=finding,
                               prediction=prediction,
                               provenance="machine_proposed")


def register_policy(workspace: Path, *, overrides: dict, finding: str,
                    prediction: str) -> Path:
    """人类署名候选:owner 决策直接给出政策覆盖(如放行规则),不走 cohort
    白名单 —— lint 防的是机器提议越界;人类候选的约束是署名 + promote 的
    评测重算门(两者一个不少)。provenance=human_authored 写进出生事实。"""
    from .harness import load_active

    workspace = Path(workspace)
    active = load_active(workspace)
    candidate = {**active["policy"], **overrides}
    return _scaffold_candidate(workspace, candidate, finding=finding,
                               prediction=prediction,
                               provenance="human_authored")


# ------------------------------------------------------------------ evaluate

def _sha256_file(path: Path) -> str | None:
    import hashlib as _h
    return _h.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _run_input_identity(run_dir: Path) -> dict:
    """一次评测输入 run 的不可变身份(高级裁决四):promote 重算时逐位比对,
    评测后动过任何输入 = 旧 eval 作废。raw understand 也进身份 ——
    槽位事实由它参与推导,换了文件事实就换。"""
    snap_path = run_dir / "review_snapshot.json"
    snap_id = None
    if snap_path.exists():
        snap_id = json.loads(snap_path.read_text(encoding="utf-8")).get(
            "review_snapshot_id")
    raw_sha = None
    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_root = Path(manifest.get("derisk_root") or run_dir.parent.parent) / "raw"
        per_doc = []
        for doc in sorted(manifest.get("docs", [])):
            p = raw_root / f"{doc}.understand.json"
            per_doc.append(f"{doc}:{_sha256_file(p)}")
        raw_sha = hashlib.sha256("\n".join(per_doc).encode()).hexdigest()
    return {
        "run_id": run_dir.name,
        "review_snapshot_id": snap_id,
        "routing_report_sha256": _sha256_file(run_dir / "routing_report.json"),
        "field_ledger_sha256": _sha256_file(run_dir / "field_ledger.json"),
        "gate_report_sha256": _sha256_file(run_dir / "gate_report.json"),
        "raw_understand_sha256": raw_sha,
        "adjudication_ledger_sha256": _sha256_file(
            run_dir / "adjudication_ledger.jsonl"),
    }


def _compute_evaluation(workspace: Path, candidate_id: str) -> dict:
    """反事实重路由(纯函数,不写盘):用候选策略重算已有 run 的路由。

    不重跑 pipeline;零 API、确定性 —— 所以 promote 可以重算并逐字节
    比对存盘 eval,而不是信任一个可编辑的文件(高级裁决四)。
    """
    from .harness import load_active
    from .routing import apply_absent_expected, route_slots

    workspace = Path(workspace)
    active = load_active(workspace)
    cand_policy_path = (workspace / "harnesses" / candidate_id
                        / "routing_policy.json")
    cand_policy_bytes = cand_policy_path.read_bytes()
    cand_policy = json.loads(cand_policy_bytes)
    cand_manifest = json.loads(
        (cand_policy_path.parent / "manifest.json").read_text(encoding="utf-8"))
    if cand_manifest.get("provenance") != "human_authored":
        violations = lint_policy(active["policy"], cand_policy)
        if violations:
            raise ValueError(f"候选 diff 审查未过:{violations}")

    runs = sorted((workspace / "runs").glob("run-*"))
    comparisons = []
    for run_dir in runs:
        if not (run_dir / "event_log.jsonl").exists():
            continue
        # 事实从权威工件重建(field_ledger + gate_report + raw understand),
        # 不从矩阵行取(投影;高级裁决六,与 verify 语义层同一函数)
        run_manifest = json.loads(
            (run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        ledger = json.loads(
            (run_dir / "field_ledger.json").read_text(encoding="utf-8"))
        gate = json.loads(
            (run_dir / "gate_report.json").read_text(encoding="utf-8"))
        raw_root = Path(run_manifest.get("derisk_root") or workspace) / "raw"
        # 预期缺失变换要作用在两层(同一策略语义,run 时由 run_gates 一次完成):
        # verdict fail → expected_absent(apply_absent_expected)+ 对应的
        # blocking finding 撤销(候选策略下它是 info 级非阻断)
        absent_fields = {c.get("field") for c in
                         (cand_policy.get("absent_expected_cohorts") or [])}
        facts = []
        for doc in run_manifest.get("docs", []):
            udata = None
            raw_path = raw_root / f"{doc}.understand.json"
            if raw_path.exists():
                body = json.loads(raw_path.read_text(
                    encoding="utf-8")).get("body") or {}
                output = body.get("output") or {}
                data = output.get("data") if isinstance(output, dict) else None
                udata = data if isinstance(data, dict) else None
            from .matrix import derive_document_records, facts_of

            blocking = [
                f for f in gate.get("findings", [])
                if f.get("blocking") and f.get("doc_id") == doc
                and not (absent_fields
                         and f.get("gate_id") == "extraction_present"
                         and f.get("field") in absent_fields)]
            facts.extend(facts_of(r) for r in derive_document_records(
                doc,
                doc_claims=[c for c in ledger.get("claims", [])
                            if c["doc_id"] == doc],
                doc_rejections=[],
                gate_evaluations=gate.get("evaluations", {}).get(doc, {}),
                doc_blocking_findings=blocking,
                understand_data=udata))
        routing_path = run_dir / "routing_report.json"
        if routing_path.exists():
            stored = json.loads(routing_path.read_text(encoding="utf-8"))
            base_routes = {f"{r['doc_id']}|{r['field']}": r["route"]
                           for r in stored.get("routes", [])}
        else:  # 2026-08-05 前的 run 没有 routing_report,用 requires 推
            matrix = json.loads(
                (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
            base_routes = {
                f"{r['doc_id']}|{r['field']}":
                    "review" if r.get("requires_adjudication") else "auto_accept"
                for r in matrix["rows"]
            }
        cand_routes = route_slots(apply_absent_expected(facts, cand_policy),
                                  cand_policy, tier_of=_tier_of)
        auto = ("auto_accept", "auto_absent")
        relaxed = []
        for r in cand_routes:
            key = r["doc_id"] + "|" + r["field"]
            if base_routes.get(key) not in auto and r["route"] in auto:
                relaxed.append(key)
        comparisons.append({
            **_run_input_identity(run_dir),
            "slots": len(facts),
            "baseline_review": sum(1 for v in base_routes.values()
                                   if v not in auto),
            "candidate_review": sum(1 for r in cand_routes
                                    if r["route"] not in auto),
            "relaxed_slots": sorted(relaxed),
        })
    total_slots = sum(c["slots"] for c in comparisons)
    total_base = sum(c["baseline_review"] for c in comparisons)
    total_cand = sum(c["candidate_review"] for c in comparisons)
    return {
        "candidate": candidate_id,
        "baseline_harness": active["harness_id"],
        # promote 强制门靠这两个 digest 把「评的是这份字节」钉死:
        # 评完改政策 / baseline 换代,旧 eval 一律作废(83 评 P0-1)
        "candidate_policy_digest": hashlib.sha256(cand_policy_bytes).hexdigest(),
        "baseline_policy_digest": active["policy_sha256"],
        "runs": comparisons,
        "evaluated_slots": total_slots,
        "review_load_baseline": total_base / max(total_slots, 1),
        "review_load_candidate": total_cand / max(total_slots, 1),
        "delta_pp": (total_cand - total_base) / max(total_slots, 1) * 100,
        "note": ("反事实重路由(不重跑抽取与门禁);「被放松槽是否有害」"
                 "需要 EVO 语料的真值评测(sealed 协议),本报告不给安全性结论"),
    }


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def evaluate(workspace: Path, candidate_id: str) -> dict:
    """反事实重路由并落盘 eval_<candidate>.json(评测输入身份随文件钉死)。"""
    workspace = Path(workspace)
    result = _compute_evaluation(workspace, candidate_id)
    out = workspace / "improve" / f"eval_{candidate_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(_canonical(result))
    return result


def _tier_of(field: str) -> str:
    return "TIER1" if field in TIER1 else "TIER2"


# ------------------------------------------------------------------- promote

def _append_promotion(workspace: Path, record: dict) -> dict:
    """落 PROM 记录(接哈希链)+ 刷新 active 缓存(唯一写指针的地方)。"""
    improve_dir = workspace / "improve"
    promotions_dir = improve_dir / "promotions"
    promotions_dir.mkdir(parents=True, exist_ok=True)
    previous = sorted(promotions_dir.glob("PROM-*.json"))
    record["previous_promotion_digest"] = hashlib.sha256(
        previous[-1].read_bytes()).hexdigest() if previous else None
    path = promotions_dir / f"{record['promotion_id']}.json"
    path.write_bytes(_canonical(record))
    (improve_dir / "active_harness.json").write_bytes(_canonical({
        "harness_id": record["to_harness_id"],
        "promotion_id": record["promotion_id"],
        "promotion_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
    }))
    return record


def _next_promotion_id(workspace: Path) -> str:
    promotions_dir = workspace / "improve" / "promotions"
    seq = len(list(promotions_dir.glob("PROM-*.json"))) + 1 \
        if promotions_dir.exists() else 1
    return f"PROM-{seq:04d}"


def promote(workspace: Path, candidate_id: str, *, approved_by: str,
            rationale: str, approved_at: str) -> dict:
    """人工晋升:强制门(83 评 P0-1)→ PROM 记录 + active 缓存。

    门是机械的,不是纪律:没评测、评测后改过政策、baseline 已换代、
    lint 不过、谱系对不上 —— 一律拒。「eval-gated」由此从声称变成机制。
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

    from .harness import load_active

    active = load_active(workspace)
    cand_policy_bytes = (cand_dir / "routing_policy.json").read_bytes()
    cand_policy = json.loads(cand_policy_bytes)
    cand_sha = hashlib.sha256(cand_policy_bytes).hexdigest()

    # ---- 强制门(83 评 P0-1 + 高级裁决四):不信存盘 eval 文件,
    # 确定性重算评测并逐字节比对 —— 评测后动过政策、动过任何输入 run
    # (矩阵/账本/门禁报告/裁决账本)、baseline 换代,全部在这里被拒
    eval_path = workspace / "improve" / f"eval_{candidate_id}.json"
    if not eval_path.exists():
        raise ValueError(
            f"没有 eval_{candidate_id}.json —— 未评测的候选不许晋升;"
            f"先 improve evaluate(评测是强制前置,不是建议)")
    recomputed = _canonical(_compute_evaluation(workspace, candidate_id))
    if recomputed != eval_path.read_bytes():
        raise ValueError(
            "重算评测与存盘 eval 逐字节不符 —— 评测输入(run 工件/裁决账本/"
            "政策)在评测后被改动过,或 eval 文件被手改;重新 evaluate")
    evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
    if not evaluation["runs"] or not evaluation["evaluated_slots"]:
        raise ValueError(
            "评测覆盖为零(没有有效 run / 没有受评槽)—— 空评测不构成晋升依据")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("provenance") != "human_authored":
        # 机器提议的候选:cohort 白名单 lint 是硬边界;人类署名候选的
        # 约束是署名 + 上面的评测重算门(一个不少)
        violations = lint_policy(active["policy"], cand_policy)
        if violations:
            raise ValueError(f"候选 diff 审查未过:{violations}")
    # manifest 是出生事实(创建后不可改):身份与谱系必须与文件一致
    if manifest.get("harness_id") != candidate_id:
        raise ValueError("manifest 的 harness_id 与目录名不符 —— 候选身份存疑")
    if manifest.get("parent_harness_id") != active["harness_id"]:
        raise ValueError(
            f"候选谱系对不上:parent={manifest.get('parent_harness_id')},"
            f"当前 active={active['harness_id']} —— 从当前 active 重新 propose")
    if manifest.get("policy_digest") != policy_digest(cand_policy):
        raise ValueError(
            "manifest 出生时的 policy_digest 与当前政策文件不符 —— "
            "候选出生后政策被改过,重新 propose + evaluate")

    record = {
        "promotion_id": _next_promotion_id(workspace),
        "action": "promote",
        "from_harness_id": active["harness_id"],
        "from_policy_digest": active["policy_sha256"],
        "to_harness_id": candidate_id,
        "to_policy_digest": cand_sha,
        "evaluation_digest": hashlib.sha256(eval_path.read_bytes()).hexdigest(),
        "gate": "eval_reexecuted",
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
    return _append_promotion(workspace, record)


def rollback(workspace: Path, *, to_harness_id: str, approved_by: str,
             rationale: str, approved_at: str) -> dict:
    """回滚 = 新的 PROM 记录(append-only;评审裁决七:active 指针只是投影,
    权威是晋升记录链;回滚也必须署名,不许直接改指针)。

    回滚免评测门(gate=rollback_exempt):目标是**已经在链上活跃过**的
    策略(其评测在首次晋升时做过),恢复已知状态不是新风险引入。
    回滚目标是包内默认(HAR-0001)时先把它物化进 workspace harnesses/。
    """
    from datetime import datetime

    from .harness import DEFAULT_HARNESS, _builtin_policy, \
        _builtin_policy_bytes, load_active

    if not approved_by.strip():
        raise ValueError("rollback 必须给 approved_by —— 回滚也是人的决定")
    if not rationale.strip():
        raise ValueError("rollback 必须给 rationale")
    try:
        datetime.fromisoformat(approved_at.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("approved_at 必须是 ISO 8601 时间,由人给出") from None

    workspace = Path(workspace)
    target = workspace / "harnesses" / to_harness_id
    if not target.exists():
        if to_harness_id != DEFAULT_HARNESS:
            raise ValueError(f"回滚目标 {to_harness_id} 不在 workspace harnesses/")
        target.mkdir(parents=True)
        policy = _builtin_policy()
        # 物化必须拷贝包内原始字节(digest 绑的是字节,不是语义 ——
        # 重新序列化会换字节,晋升链回放立即判篡改)
        (target / "routing_policy.json").write_bytes(_builtin_policy_bytes())
        (target / "manifest.json").write_text(json.dumps({
            "harness_id": to_harness_id, "parent_harness_id": None,
            "note": "回滚目标:包内默认策略的物化副本(原始字节)",
            "policy_digest": policy_digest(policy),
        }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    active = load_active(workspace)
    # 豁免资格:目标必须在链上活跃过(或是包内默认起点)——
    # 否则「回滚」就是绕过评测门的晋升
    promotions_dir = workspace / "improve" / "promotions"
    seen = {DEFAULT_HARNESS}
    if promotions_dir.exists():
        for p in sorted(promotions_dir.glob("PROM-*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            seen.add(rec.get("to_harness_id"))
    if to_harness_id not in seen:
        raise ValueError(
            f"{to_harness_id} 从未在晋升链上活跃过 —— 这不是回滚,是晋升,"
            f"走 improve promote(评测门不免)")
    target_bytes = (target / "routing_policy.json").read_bytes()
    record = {
        "promotion_id": _next_promotion_id(workspace),
        "action": "rollback",
        "from_harness_id": active["harness_id"],
        "from_policy_digest": active["policy_sha256"],
        "to_harness_id": to_harness_id,
        "to_policy_digest": hashlib.sha256(target_bytes).hexdigest(),
        "evaluation_digest": None,
        "gate": "rollback_exempt",
        "basis": "evo_replay_only",
        "claim_limits": "回滚到链上活跃过的策略;首次晋升时的评测仍然有效",
        "approved_by": approved_by.strip(),
        "approved_at": approved_at.strip(),
        "rationale": f"ROLLBACK:{rationale.strip()}",
        "rollback_harness_id": active["harness_id"],
    }
    return _append_promotion(workspace, record)
