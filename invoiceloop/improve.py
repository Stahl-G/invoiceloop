"""The improvement control plane (v0.2, narrowed): mine → propose → evaluate →
promote / rollback.

Fully deterministic and model-free. A candidate policy has to survive a
counterfactual replay of the frozen evidence and a signed human promotion before
it takes effect; Gate 2 (silent errors must not rise) and Gate 3 (review load
must not rise) are checked by Python, not argued.
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
#: 新预期缺失规则必须精确到受控类别×字段。旧 ``{id, field}`` 条目只在
#: parent 中原样继承时获准重放;任何新候选都不能再写全局缺席。
_ABSENT_KEYS = ("id", "doc_class", "field")
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
    by_class_field: dict[tuple[str, str], dict] = {}
    for e in qualified:
        if e.get("doctype_status") != "pass" or not e.get("doc_class"):
            continue
        key = (e["doc_class"], e["field"])
        f = by_class_field.setdefault(key, {
            "doc_class": e["doc_class"], "field": e["field"],
            "total": 0, "absentish": 0, "notes": []})
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
                       "cohort": {"doc_class": f["doc_class"],
                                  "field": f["field"]}}}
        for f in by_class_field.values()
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

def lint_schema(parent: dict, candidate: dict) -> list[str]:
    """提取 schema diff 审查。只许改已有受评字段的 description 字符串。"""
    violations = []
    if parent.get("type") != candidate.get("type"):
        violations.append("候选改了 schema.type —— 禁止")
    pprops = parent.get("properties") or {}
    cprops = candidate.get("properties") or {}
    if set(pprops) != set(cprops):
        violations.append(
            f"候选增删字段 {sorted(set(pprops) ^ set(cprops))} —— 只许改 description")
        return violations
    for name in sorted(pprops):
        p, c = pprops[name], cprops[name]
        if not isinstance(c, dict):
            violations.append(f"{name}: property 必须是 object")
            continue
        if set(c) - {"type", "description"}:
            violations.append(
                f"{name}: 含白名单外键 {sorted(set(c) - {'type', 'description'})}"
                " —— 只许 type+description")
        if c.get("type") != p.get("type"):
            violations.append(f"{name}: 改了 type —— 禁止")
        if "required" in c or "required" in candidate:
            violations.append(f"{name}: 禁止加 required(会逼抽取器编造)")
        if name not in FIELDS:
            violations.append(f"{name}: 不是受评字段")
        # description 可以变;其余键已在上面拦
        if set(p) - set(c) - {"description"} or set(c) - set(p) - {"description"}:
            extra_p = set(p) - set(c) - {"description"}
            extra_c = set(c) - set(p) - {"description"}
            if extra_p or extra_c:
                violations.append(
                    f"{name}: 键集漂移 parent_only={sorted(extra_p)} "
                    f"cand_only={sorted(extra_c)}")
    if "required" in candidate:
        violations.append("schema 顶层禁止 required")
    return violations


def _names(keys) -> str:
    """键名列表 → 人能读的一串。Python 的 list/tuple repr 直接进报错页面,
    读起来像内部转储(`['strength', 'tier'] —— 只许 ('id', 'field')`)。"""
    return "、".join(sorted(keys))


def refusal_text(violations: list[str], *, subject: str = "这个候选") -> str:
    """违规列表 → 给人看的一段话。列表 repr 不进用户界面。"""
    if len(violations) == 1:
        return f"{subject}没能通过审查:{violations[0]}"
    body = "\n".join(f"· {v}" for v in violations)
    return f"{subject}没能通过审查,有 {len(violations)} 处:\n{body}"


def lint_policy(parent: dict, candidate: dict) -> list[str]:
    """候选策略 diff 审查。返回违规列表(空 = 通过)。只允许给
    auto_accept_cohorts / absent_expected_cohorts 加条目,
    且条目只引用各自白名单内的通用特征。"""
    violations = []
    for key in set(parent) | set(candidate):
        if key in ("auto_accept_cohorts", "absent_expected_cohorts",
                   "absent_evidenced_cohorts", "harness_id", "version"):
            continue  # cohorts 单独查;harness_id/version 是身份字段,必然变
        if key == "qa":
            # 类别缺席规则同时切到 sampler v2:跨 harness 的同一规则必须
            # 命中同一批探针。其余 QA 配置不许借机改动。
            pq, cq = parent.get("qa") or {}, candidate.get("qa") or {}
            changed = {k for k in set(pq) | set(cq)
                       if pq.get(k) != cq.get(k)}
            allowed = {"absent_expected_rate", "absent_evidenced_rate",
                       "sampler_version"}
            if changed - allowed:
                violations.append(
                    f"候选改了 qa 的 {sorted(changed - allowed)}"
                    " —— 类别缺席候选只许设置探针率与 sampler_version")
            continue
        if parent.get(key) != candidate.get(key):
            violations.append(f"候选改了 {key} —— 第一版只允许加 cohorts")
    parent_ids = {c.get("id") for c in parent.get("auto_accept_cohorts", [])}
    for cohort in candidate.get("auto_accept_cohorts", []):
        if set(cohort) - set(_COHORT_KEYS):
            violations.append(
                f"自动放行 cohort 带了 {_names(set(cohort) - set(_COHORT_KEYS))}"
                f",这几个不能进策略;它只认 {_names(_COHORT_KEYS)}")
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
    violations.extend(_absent_structure_violations(parent, candidate))
    return violations


def _absent_structure_violations(parent: dict, candidate: dict) -> list[str]:
    """预期缺失规则的结构约束 —— 机器可判,所以人类署名候选也受它约束。

    `register_policy` 让人有权决定「这条规则该不该生效」,但无权把类别
    缺席写成无条件规则、无权自己编规则 ID、无权关掉 QA 探针。
    `lint_policy` 调用同一个函数,判据只有一份。

    2026-08-09:上一版把这层实现成「筛 lint_policy 输出里含『预期缺失』/
    『sampler_version』的句子」,于是人改 qa 的 policy_accepted_tier1_rate
    也被判成缺席违规(test_carry::test_qa_probes_stay_fresh)。按字符串
    反推判据不是判据。
    """
    from .doctype import CLASSES

    violations: list[str] = []
    absent_parent = {c.get("id"): c
                     for c in parent.get("absent_expected_cohorts", [])}
    new_absent = []
    for cohort in candidate.get("absent_expected_cohorts", []):
        if cohort.get("id") in absent_parent \
                and cohort == absent_parent[cohort.get("id")]:
            continue  # 冻结历史条目原样重放,包括旧 {id, field}
        if set(cohort) - set(_ABSENT_KEYS):
            violations.append(
                f"预期缺失 cohort 带了 {_names(set(cohort) - set(_ABSENT_KEYS))}"
                f" —— 它是类别×字段规则,与证据强度、TIER 无关,所以只认 "
                f"{_names(_ABSENT_KEYS)}。去掉那几个再采纳。")
            continue
        new_absent.append(cohort)
        if not cohort.get("id"):
            violations.append("预期缺失 cohort 缺 id")
        expected_id = f"AE-{cohort.get('doc_class')}-{cohort.get('field')}"
        if cohort.get("id") != expected_id:
            violations.append(
                f"预期缺失 cohort id 必须由 Python 生成 {expected_id!r}")
        if cohort.get("doc_class") not in CLASSES:
            violations.append(
                f"预期缺失 cohort doc_class {cohort.get('doc_class')!r}"
                " 不是受控类别")
        if cohort.get("field") not in FIELDS:
            violations.append(
                f"预期缺失 cohort field {cohort.get('field')!r} 不是受评字段")
    if new_absent:
        qa = candidate.get("qa") or {}
        if float(qa.get("absent_expected_rate", 0.0)) < 0.20:
            violations.append("类别缺席规则必须保留至少 20% 人工探针")
        if qa.get("sampler_version") != 2:
            violations.append("类别缺席规则必须使用 sampler_version=2")

    # ---- 页面证据缺席规则:同样的结构约束,授权来源不同
    from .absence_evidence import LABEL_LEXICON

    evidenced_parent = {c.get("id"): c
                        for c in parent.get("absent_evidenced_cohorts", [])}
    new_evidenced = []
    for cohort in candidate.get("absent_evidenced_cohorts", []):
        if cohort.get("id") in evidenced_parent \
                and cohort == evidenced_parent[cohort.get("id")]:
            continue
        if set(cohort) - {"id", "field"}:
            violations.append(
                f"页面证据缺席 cohort 带了 "
                f"{_names(set(cohort) - {'id', 'field'})} —— 它只认 id 与 "
                f"field;doc_class 属于类别缺席那一类,混写会造出一条谁也"
                f"没评过的杂交规则")
            continue
        new_evidenced.append(cohort)
        expected_id = f"AV-{cohort.get('field')}"
        if cohort.get("id") != expected_id:
            violations.append(
                f"页面证据缺席 cohort id 必须由 Python 生成 {expected_id!r}")
        if cohort.get("field") not in FIELDS:
            violations.append(
                f"页面证据缺席 cohort field {cohort.get('field')!r} 不是受评字段")
        elif cohort.get("field") not in LABEL_LEXICON:
            violations.append(
                f"{cohort.get('field')!r} 没有标签词表 —— 页面上没有可判别的"
                "标签,就没有「页面证明了缺席」这回事")
    if new_evidenced:
        qa = candidate.get("qa") or {}
        if float(qa.get("absent_evidenced_rate", 0.0)) < 0.20:
            violations.append("页面证据缺席规则必须保留至少 20% 人工探针")
        if qa.get("sampler_version") != 2:
            violations.append("页面证据缺席规则必须使用 sampler_version=2")
    return violations


def _scaffold_candidate(workspace: Path, candidate: dict, *,
                        finding: str, prediction: str,
                        provenance: str,
                        schema: dict | None = None) -> Path:
    """写 harnesses/HAR-NNNN/{routing_policy,manifest[,extraction_schema]}.json。"""
    from .harness import load_active, schema_digest

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
    # schema:显式传入或继承 active(保证 cohort 候选也带 schema 文件)
    schema_obj = schema if schema is not None else active["schema"]
    (cand_dir / "extraction_schema.json").write_text(
        json.dumps(schema_obj, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (cand_dir / "manifest.json").write_text(json.dumps({
        "harness_id": cand_id,
        "parent_harness_id": active["harness_id"],
        "provenance": provenance,
        "created_from_findings": [finding],
        "prediction": prediction,
        "policy_digest": policy_digest(candidate),
        "schema_digest": schema_digest(schema_obj),
        "schema_changed": schema is not None and (
            schema_digest(schema) != active.get("schema_digest")),
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return cand_dir


def propose_schema(workspace: Path, *, field: str, description: str,
                   finding: str, prediction: str) -> Path:
    """派生只改一个字段 description 的候选 harness。"""
    from .harness import load_active
    from .ingest import default_extraction_schema

    workspace = Path(workspace)
    active = load_active(workspace)
    parent_schema = json.loads(json.dumps(active.get("schema")
                                          or default_extraction_schema()))
    if field not in FIELDS:
        raise ValueError(f"{field!r} 不是受评字段")
    props = parent_schema.setdefault("properties", {})
    if field not in props:
        raise ValueError(f"{field!r} 不在 parent schema.properties 里")
    props[field] = {**props[field], "description": description}
    violations = lint_schema(active["schema"], parent_schema)
    if violations:
        raise ValueError(refusal_text(violations, subject="这个字段描述改动"))
    # 策略不变,只换 schema
    return _scaffold_candidate(
        workspace, dict(active["policy"]),
        finding=finding, prediction=prediction,
        provenance="human_authored", schema=parent_schema)


def propose_schema_bundle(
    workspace: Path,
    *,
    descriptions: dict[str, str],
    finding: str,
    prediction: str,
) -> Path:
    """Create one human-reviewable candidate changing only field descriptions.

    The bundle shape is intentionally exact: a model may draft text, but it
    cannot choose a subset of fields, add properties, write IDs, or activate a
    harness.  Python assigns the candidate directory and preserves the active
    routing policy byte-for-byte.
    """
    from .harness import load_active

    workspace = Path(workspace)
    active = load_active(workspace)
    parent_schema = json.loads(json.dumps(
        active.get("schema") or default_extraction_schema()))
    props = parent_schema.setdefault("properties", {})
    expected = set(FIELDS)
    supplied = set(descriptions)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        bits = []
        if missing:
            bits.append(f"缺少字段:{'、'.join(missing)}")
        if extra:
            bits.append(f"多出字段:{'、'.join(extra)}")
        raise ValueError("组合 schema 必须逐字段提供十个受评字段描述(" + ";".join(bits) + ")")
    for field, description in descriptions.items():
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{field}: description 不能为空")
        if field not in props:
            raise ValueError(f"{field!r} 不在 parent schema.properties 里")
        props[field] = {**props[field], "description": description.strip()}
    violations = lint_schema(active["schema"], parent_schema)
    if violations:
        raise ValueError(refusal_text(violations, subject="这个组合字段描述改动"))
    return _scaffold_candidate(
        workspace, dict(active["policy"]),
        finding=finding, prediction=prediction,
        provenance="human_authored", schema=parent_schema)


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
        from .doctype import CLASSES

        extra = set(cohort) - {"doc_class", "field"}
        if extra:
            raise ValueError(refusal_text([
                f"预期缺失 cohort 带了 {_names(extra)} —— 模型不写规则 ID,"
                "只许选择 doc_class 与 field"]))
        doc_class = cohort.get("doc_class")
        field_name = cohort.get("field")
        if doc_class not in CLASSES:
            raise ValueError(refusal_text([
                f"预期缺失 cohort doc_class {doc_class!r} 不是受控类别"]))
        if field_name not in FIELDS:
            raise ValueError(refusal_text([
                f"预期缺失 cohort field {field_name!r} 不是受评字段"]))
        cohort = {"id": f"AE-{doc_class}-{field_name}",
                  "doc_class": doc_class, "field": field_name}
        candidate = {**parent,
                     "absent_expected_cohorts":
                     parent.get("absent_expected_cohorts", []) + [cohort]}
        # 预期缺失必须带 QA 探针(缺席是否成立要持续观测)
        qa = dict(candidate.get("qa") or {})
        qa["absent_expected_rate"] = max(
            float(qa.get("absent_expected_rate", 0.0)), 0.20)
        qa["sampler_version"] = 2
        candidate["qa"] = qa
    elif kind == "absent_evidenced":
        from .absence_evidence import LABEL_LEXICON

        extra = set(cohort) - {"field"}
        if extra:
            raise ValueError(refusal_text([
                f"页面证据缺席 cohort 带了 {_names(extra)} —— 它的授权来自"
                "这一份的页面,不是同类文档;doc_class 属于另一类规则,"
                "混写会造出一条谁也没评过的杂交规则。模型也不写规则 ID。"]))
        field_name = cohort.get("field")
        if field_name not in FIELDS:
            raise ValueError(refusal_text([
                f"页面证据缺席 cohort field {field_name!r} 不是受评字段"]))
        if field_name not in LABEL_LEXICON:
            raise ValueError(refusal_text([
                f"{field_name!r} 没有标签词表 —— 这个机制对它无话可说。"
                "页面上没有可判别的标签,就没有「页面证明了缺席」这回事;"
                f"当前有词表的字段:{_names(sorted(LABEL_LEXICON))}"]))
        cohort = {"id": f"AV-{field_name}", "field": field_name}
        candidate = {**parent,
                     "absent_evidenced_cohorts":
                     parent.get("absent_evidenced_cohorts", []) + [cohort]}
        # 与类别缺席同理:缺席是否成立要持续观测,探针不是损耗是前提
        qa = dict(candidate.get("qa") or {})
        qa["absent_evidenced_rate"] = max(
            float(qa.get("absent_evidenced_rate", 0.0)), 0.20)
        qa["sampler_version"] = 2
        candidate["qa"] = qa
    elif kind == "auto_accept":
        candidate = {**parent,
                     "auto_accept_cohorts": parent.get("auto_accept_cohorts", [])
                     + [cohort]}
    else:
        raise ValueError(f"未知 cohort 类型 {kind!r}")
    violations = lint_policy(parent, candidate)
    if violations:
        raise ValueError(refusal_text(violations))
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
    # 人有权决定规则是否该生效,但无权绕过可机器检查的结构/探针约束。
    absent_related = _absent_structure_violations(active["policy"], candidate)
    if absent_related:
        raise ValueError(refusal_text(absent_related))
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

    若 workspace 文档在 DocILE 下有可读标注,额外累计 silent_absent /
    silent_wrong(与 safety_metrics / loop_generalization 同函数),供
    promote Gate 2 使用;无标注则 safety_status=unscored。
    """
    from . import absence_evidence as _absence
    from . import truth_caliber as _caliber
    from .harness import load_active
    from .routing import (
        apply_absent_expected,
        match_absent_rule,
        route_slots,
    )
    from .safety_metrics import (
        SAFETY_NOTE_SCORED,
        SAFETY_NOTE_UNSCORED,
        annotation_record_available,
        annotations_available,
        empty_counts,
        score_routes,
        truth,
    )

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
            raise ValueError(refusal_text(violations))

    runs = sorted((workspace / "runs").glob("run-*"))
    comparisons = []
    all_docs: list[str] = []
    base_route_rows: list[dict] = []
    cand_route_rows: list[dict] = []
    understand_by_doc: dict[str, dict | None] = {}
    absent_intrinsic = {
        "baseline": {"matches": 0, "truth_conflicts": 0,
                     "caliber_disputes": 0,
                     "missing_truth_docs": set()},
        "candidate": {"matches": 0, "truth_conflicts": 0,
                      "caliber_disputes": 0,
                      "missing_truth_docs": set()},
    }
    evidenced_rules = cand_policy.get("absent_evidenced_cohorts") or []
    docs_without_probes: set[str] = set()
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
        facts = []
        for doc in run_manifest.get("docs", []):
            all_docs.append(doc)
            udata = None
            raw_path = raw_root / f"{doc}.understand.json"
            if raw_path.exists():
                body = json.loads(raw_path.read_text(
                    encoding="utf-8")).get("body") or {}
                output = body.get("output") or {}
                data = output.get("data") if isinstance(output, dict) else None
                udata = data if isinstance(data, dict) else None
            understand_by_doc[doc] = udata
            from .matrix import derive_document_records, facts_of

            from .doctype import trusted_class

            document_check = (gate.get("document_checks") or {}).get(doc)
            trusted = trusted_class(document_check)
            raw_status = (document_check or {}).get("status") \
                if isinstance(document_check, dict) else None
            type_facts = {
                "doctype_status": ("pass" if trusted is not None
                                   else "malformed" if raw_status == "pass"
                                   else str(raw_status or "not_measured")),
                "doc_class": trusted,
            }
            # 缺席探针只存在于 2026-08-09 之后跑的 run。旧 gate_report 没有
            # 这一项 —— 那不是「没有标签」,是这批证据判不了(宪章四)。
            probes = (gate.get("absence_probes") or {}).get(doc) or {}
            if evidenced_rules and not probes:
                docs_without_probes.add(doc)
            absence_facts = {
                field_name: (_absence.CORROBORATED
                             if _absence.trusted_absence(probes.get(field_name))
                             else _absence.NOT_MEASURED)
                for field_name in FIELDS
            }
            matched_fields = {
                field_name for field_name in FIELDS
                if match_absent_rule(
                    {**type_facts, "field": field_name,
                     "absence_evidence": absence_facts[field_name]},
                    cand_policy)[0] is not None
            }

            blocking = [
                f for f in gate.get("findings", [])
                if f.get("blocking") and f.get("doc_id") == doc
                and not (f.get("gate_id") == "extraction_present"
                         and f.get("field") in matched_fields)]
            doc_facts = [facts_of(r) for r in derive_document_records(
                doc,
                doc_claims=[c for c in ledger.get("claims", [])
                            if c["doc_id"] == doc],
                doc_rejections=[],
                gate_evaluations=gate.get("evaluations", {}).get(doc, {}),
                doc_blocking_findings=blocking,
                understand_data=udata,
                document_check=document_check,
                absence_probes=probes)]
            facts.extend(doc_facts)
            for label, policy in (("baseline", active["policy"]),
                                  ("candidate", cand_policy)):
                for fact in doc_facts:
                    rule, rule_kind = match_absent_rule(fact, policy)
                    if rule is None:
                        continue
                    if rule_kind == "expected" and rule.get("doc_class") is None:
                        continue  # 旧全局 cohort 只为冻结重放,不进内在核算
                    value = (udata or {}).get(fact["field"])
                    if value is not None and str(value).strip() != "":
                        continue
                    bucket = absent_intrinsic[label]
                    bucket["matches"] += 1
                    if not annotation_record_available(doc):
                        bucket["missing_truth_docs"].add(doc)
                    else:
                        truth_map = truth(doc)
                        if truth_map.get(fact["field"]) is not None:
                            # T1/T2 口径争议不算真值冲突,单列(增补件 A3)
                            if _caliber.caliber_dispute(
                                    doc, fact["field"], truth_map):
                                bucket["caliber_disputes"] += 1
                            else:
                                bucket["truth_conflicts"] += 1
        routing_path = run_dir / "routing_report.json"
        if routing_path.exists():
            stored = json.loads(routing_path.read_text(encoding="utf-8"))
            base_routes = {f"{r['doc_id']}|{r['field']}": r["route"]
                           for r in stored.get("routes", [])}
            for r in stored.get("routes", []):
                base_route_rows.append({
                    "doc_id": r["doc_id"], "field": r["field"],
                    "route": r["route"],
                })
        else:  # 2026-08-05 前的 run 没有 routing_report,用 requires 推
            matrix = json.loads(
                (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
            base_routes = {
                f"{r['doc_id']}|{r['field']}":
                    "review" if r.get("requires_adjudication") else "auto_accept"
                for r in matrix["rows"]
            }
            for r in matrix["rows"]:
                base_route_rows.append({
                    "doc_id": r["doc_id"], "field": r["field"],
                    "route": base_routes[f"{r['doc_id']}|{r['field']}"],
                })
        cand_routes = route_slots(apply_absent_expected(facts, cand_policy),
                                  cand_policy, tier_of=_tier_of)
        cand_route_rows.extend(
            {"doc_id": r["doc_id"], "field": r["field"], "route": r["route"]}
            for r in cand_routes)
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

    scored = bool(all_docs) and annotations_available(all_docs)
    if scored:
        base_counts = score_routes(
            base_route_rows,
            understand_of=lambda d: understand_by_doc.get(d),
            caliber_of=_caliber.caliber_dispute,
        )
        cand_counts = score_routes(
            cand_route_rows,
            understand_of=lambda d: understand_by_doc.get(d),
            caliber_of=_caliber.caliber_dispute,
        )
        safety_note = SAFETY_NOTE_SCORED
    else:
        base_counts = empty_counts()
        cand_counts = empty_counts()
        safety_note = SAFETY_NOTE_UNSCORED

    class_rule_count = sum(
        1 for rule in cand_policy.get("absent_expected_cohorts") or []
        if rule.get("doc_class") is not None)
    # 探针可用性单列。若混进 unscored,一个「这批 run 判不了」会读成
    # 「这条规则没效果」—— 而零变化恰恰是规则被静默禁用时的样子。
    absence_probe_status = (
        "not_applicable" if not evidenced_rules
        else "unavailable" if docs_without_probes
        else "available")
    candidate_intrinsic = absent_intrinsic["candidate"]
    if class_rule_count == 0 and not evidenced_rules:
        absent_truth_status = "not_applicable"
    elif (candidate_intrinsic["matches"] > 0
          and not candidate_intrinsic["missing_truth_docs"]):
        absent_truth_status = "scored"
    else:
        absent_truth_status = "unscored"

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
        "safety_status": "scored" if scored else "unscored",
        # Gate 2 的 QA 前口径:即使危险槽恰好被 20% 探针抽中、最终没有
        # silent_absent,真值冲突仍在这里被机械抓住。
        "class_absent_rule_count": class_rule_count,
        "evidenced_absent_rule_count": len(evidenced_rules),
        "absence_probe_status": absence_probe_status,
        "absence_probe_missing_docs": sorted(docs_without_probes),
        "absent_rule_truth_status": absent_truth_status,
        "absent_rule_matches_baseline":
            absent_intrinsic["baseline"]["matches"],
        "absent_rule_matches_candidate": candidate_intrinsic["matches"],
        "absent_rule_truth_conflicts_baseline": (
            absent_intrinsic["baseline"]["truth_conflicts"]
            if not absent_intrinsic["baseline"]["missing_truth_docs"] else None),
        "absent_rule_truth_conflicts_candidate": (
            candidate_intrinsic["truth_conflicts"]
            if absent_truth_status == "scored" else None),
        "absent_rule_unscored_docs": sorted(
            candidate_intrinsic["missing_truth_docs"]),
        "absent_rule_caliber_disputes_baseline": (
            absent_intrinsic["baseline"]["caliber_disputes"]
            if not absent_intrinsic["baseline"]["missing_truth_docs"] else None),
        "absent_rule_caliber_disputes_candidate": (
            candidate_intrinsic["caliber_disputes"]
            if absent_truth_status == "scored" else None),
        "truth_caliber_version": _caliber.TRUTH_CALIBER_VERSION,
        "silent_absent_baseline":
            base_counts["silent_absent"] if scored else None,
        "silent_absent_candidate":
            cand_counts["silent_absent"] if scored else None,
        "caliber_disputes_baseline":
            base_counts["caliber_disputes"] if scored else None,
        "caliber_disputes_candidate":
            cand_counts["caliber_disputes"] if scored else None,
        "silent_absent_true_baseline":
            base_counts["silent_absent_true"] if scored else None,
        "silent_absent_true_candidate":
            cand_counts["silent_absent_true"] if scored else None,
        "silent_wrong_baseline":
            base_counts["silent_wrong"] if scored else None,
        "silent_wrong_candidate":
            cand_counts["silent_wrong"] if scored else None,
        "absent_hits_baseline":
            base_counts["absent_hits"] if scored else None,
        "absent_hits_candidate":
            cand_counts["absent_hits"] if scored else None,
        "value_hits_baseline":
            base_counts["value_hits"] if scored else None,
        "value_hits_candidate":
            cand_counts["value_hits"] if scored else None,
        "safety_note": safety_note,
        "note": (
            "反事实重路由(不重跑抽取与门禁);"+safety_note
            if scored else
            ("反事实重路由(不重跑抽取与门禁);「被放松槽是否有害」"
             "需要 EVO 语料的真值评测(sealed 协议),本报告不给安全性结论")
        ),
    }


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def evaluate(workspace: Path, candidate_id: str, *,
             reextract: bool = False, sample: int = 0,
             budget: float = 600.0) -> dict:
    """评测并落盘 eval_<candidate>.json。

    默认:反事实重路由(零 API)。
    reextract=True:用候选 schema 对确定性抽样的 N 份重抽(烧 credits),
    basis=reextract_sample —— schema 变更候选必须走这条。
    """
    workspace = Path(workspace)
    if reextract:
        if sample <= 0:
            raise ValueError("reextract 必须给 --sample N(>0)")
        result = _evaluate_reextract(
            workspace, candidate_id, sample_n=sample, budget=budget)
    else:
        result = _compute_evaluation(workspace, candidate_id)
        result["basis"] = (
            "evo_truth_replay" if result.get("safety_status") == "scored"
            else "evo_replay_only")
    out = workspace / "improve" / f"eval_{candidate_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(_canonical(result))
    return result


def _sample_doc_ids(workspace: Path, n: int) -> list[str]:
    """从 workspace runs 里确定性抽 N 份(哈希排序,不用随机数)。"""
    docs: list[str] = []
    for run_dir in sorted((workspace / "runs").glob("run-*")):
        man = run_dir / "run_manifest.json"
        if not man.exists():
            continue
        for doc in json.loads(man.read_text(encoding="utf-8")).get("docs", []):
            if doc not in docs:
                docs.append(doc)
    docs = sorted(docs)
    if len(docs) <= n:
        return docs
    ranked = sorted(
        docs,
        key=lambda d: hashlib.sha256(
            f"schema-eval-v1|{d}|{n}".encode()).hexdigest())
    return ranked[:n]


def _evaluate_reextract(workspace: Path, candidate_id: str, *,
                        sample_n: int, budget: float) -> dict:
    """候选 schema 重抽样本 → 与基线同口径打安全/负载分。"""
    from .dws_client import extract_to_raw
    from .harness import load_active, schema_digest
    from .ocr import pdf_path
    from .routing import (
        apply_absent_expected,
        match_absent_expected,
        route_slots,
    )
    from .safety_metrics import (
        SAFETY_NOTE_SCORED, SAFETY_NOTE_UNSCORED,
        annotations_available, empty_counts, score_routes,
    )
    from . import truth_caliber as _caliber

    workspace = Path(workspace)
    active = load_active(workspace)
    cand_dir = workspace / "harnesses" / candidate_id
    cand_policy = json.loads(
        (cand_dir / "routing_policy.json").read_text(encoding="utf-8"))
    cand_schema = json.loads(
        (cand_dir / "extraction_schema.json").read_text(encoding="utf-8"))
    parent_schema = active["schema"]
    violations = lint_schema(parent_schema, cand_schema)
    if violations:
        raise ValueError(refusal_text(violations, subject="这个字段描述改动"))

    sample_ids = _sample_doc_ids(workspace, sample_n)
    if not sample_ids:
        raise ValueError("workspace 没有任何 run 文档可抽样")

    raw_dir = workspace / "improve" / "candidates" / candidate_id / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    extracted = 0
    understand_by_doc: dict[str, dict | None] = {}
    for doc_id in sample_ids:
        if spent > budget:
            break
        pdf = pdf_path(doc_id)
        if not pdf.exists():
            # workspace 布局:input/pdfs
            alt = workspace / "input" / "pdfs" / f"{doc_id}.pdf"
            pdf = alt if alt.exists() else pdf
        target = raw_dir / f"{doc_id}.understand.json"
        if target.exists():
            record = json.loads(target.read_text(encoding="utf-8"))
        else:
            if not pdf.exists():
                understand_by_doc[doc_id] = None
                continue
            record = extract_to_raw(
                pdf, cand_schema, raw_dir, doc_id=doc_id, mode="understand")
            extracted += 1
            usage = (record.get("body") or {}).get("usage") or {}
            spent += float(
                (usage.get("data_extraction_credits") or {}).get("cost") or 0.0)
        if isinstance(record, dict) and record.get("http_status") == 200:
            body = record.get("body") or {}
            output = body.get("output") or {}
            data = output.get("data") if isinstance(output, dict) else None
            understand_by_doc[doc_id] = data if isinstance(data, dict) else None
        else:
            understand_by_doc[doc_id] = None

    # 基线:用原 run 的 understand;候选:用重抽 understand;同一策略重路由
    from .matrix import derive_document_records, facts_of

    base_rows: list[dict] = []
    cand_rows: list[dict] = []
    # 取最新含这些 doc 的 run 的 gate/ledger
    run_dirs = sorted((workspace / "runs").glob("run-*"), reverse=True)
    ledger_claims: list = []
    gate = {"findings": [], "evaluations": {}}
    old_understand: dict[str, dict | None] = {}
    for run_dir in run_dirs:
        man = json.loads((run_dir / "run_manifest.json").read_text())
        if not set(sample_ids) & set(man.get("docs", [])):
            continue
        ledger_claims = json.loads(
            (run_dir / "field_ledger.json").read_text())["claims"]
        gate = json.loads((run_dir / "gate_report.json").read_text())
        raw_root = Path(man.get("derisk_root") or workspace) / "raw"
        for doc in sample_ids:
            p = raw_root / f"{doc}.understand.json"
            if p.exists():
                body = json.loads(p.read_text()).get("body") or {}
                output = body.get("output") or {}
                data = output.get("data") if isinstance(output, dict) else None
                old_understand[doc] = data if isinstance(data, dict) else None
        break

    for doc in sample_ids:
        for label, udata, sink, policy in (
            ("base", old_understand.get(doc), base_rows, active["policy"]),
            ("cand", understand_by_doc.get(doc), cand_rows, cand_policy),
        ):
            document_check = (gate.get("document_checks") or {}).get(doc)
            from .doctype import trusted_class

            trusted = trusted_class(document_check)
            raw_status = (document_check or {}).get("status") \
                if isinstance(document_check, dict) else None
            type_facts = {
                "doctype_status": ("pass" if trusted is not None
                                   else "malformed" if raw_status == "pass"
                                   else str(raw_status or "not_measured")),
                "doc_class": trusted,
            }
            matched_fields = {
                field_name for field_name in FIELDS
                if match_absent_expected(
                    {**type_facts, "field": field_name}, policy) is not None
            }
            blocking = [f for f in gate.get("findings", [])
                        if f.get("blocking") and f.get("doc_id") == doc
                        and not (f.get("gate_id") == "extraction_present"
                                 and f.get("field") in matched_fields)]
            facts = [facts_of(r) for r in derive_document_records(
                doc,
                doc_claims=[c for c in ledger_claims if c["doc_id"] == doc],
                doc_rejections=[],
                gate_evaluations=gate.get("evaluations", {}).get(doc, {}),
                doc_blocking_findings=blocking,
                understand_data=udata,
                document_check=(gate.get("document_checks") or {}).get(doc))]
            routes = route_slots(
                apply_absent_expected(facts, policy),
                policy, tier_of=_tier_of)
            sink.extend({"doc_id": r["doc_id"], "field": r["field"],
                         "route": r["route"]} for r in routes)

    scored = annotations_available(sample_ids)
    if scored:
        base_counts = score_routes(
            base_rows, understand_of=lambda d: old_understand.get(d),
            caliber_of=_caliber.caliber_dispute)
        cand_counts = score_routes(
            cand_rows, understand_of=lambda d: understand_by_doc.get(d),
            caliber_of=_caliber.caliber_dispute)
        safety_note = SAFETY_NOTE_SCORED
    else:
        base_counts = empty_counts()
        cand_counts = empty_counts()
        safety_note = SAFETY_NOTE_UNSCORED

    auto = ("auto_accept", "auto_absent")
    total = max(len(base_rows), 1)
    return {
        "candidate": candidate_id,
        "baseline_harness": active["harness_id"],
        "basis": "reextract_sample",
        "sample_doc_ids": sample_ids,
        "credits_spent": spent,
        "extracted": extracted,
        "candidate_policy_digest": hashlib.sha256(
            (cand_dir / "routing_policy.json").read_bytes()).hexdigest(),
        "baseline_policy_digest": active["policy_sha256"],
        "candidate_schema_digest": schema_digest(cand_schema),
        "baseline_schema_digest": active.get("schema_digest"),
        "runs": [{"sample": True, "slots": len(base_rows),
                  "baseline_review": sum(1 for r in base_rows
                                         if r["route"] not in auto),
                  "candidate_review": sum(1 for r in cand_rows
                                          if r["route"] not in auto),
                  "relaxed_slots": []}],
        "evaluated_slots": len(base_rows),
        "review_load_baseline":
            sum(1 for r in base_rows if r["route"] not in auto) / total,
        "review_load_candidate":
            sum(1 for r in cand_rows if r["route"] not in auto) / total,
        "delta_pp": (
            sum(1 for r in cand_rows if r["route"] not in auto)
            - sum(1 for r in base_rows if r["route"] not in auto)
        ) / total * 100,
        "safety_status": "scored" if scored else "unscored",
        "silent_absent_baseline":
            base_counts["silent_absent"] if scored else None,
        "silent_absent_candidate":
            cand_counts["silent_absent"] if scored else None,
        "caliber_disputes_baseline":
            base_counts["caliber_disputes"] if scored else None,
        "caliber_disputes_candidate":
            cand_counts["caliber_disputes"] if scored else None,
        "silent_absent_true_baseline":
            base_counts["silent_absent_true"] if scored else None,
        "silent_absent_true_candidate":
            cand_counts["silent_absent_true"] if scored else None,
        "truth_caliber_version": _caliber.TRUTH_CALIBER_VERSION,
        "silent_wrong_baseline":
            base_counts["silent_wrong"] if scored else None,
        "silent_wrong_candidate":
            cand_counts["silent_wrong"] if scored else None,
        "absent_hits_baseline":
            base_counts["absent_hits"] if scored else None,
        "absent_hits_candidate":
            cand_counts["absent_hits"] if scored else None,
        "value_hits_baseline":
            base_counts["value_hits"] if scored else None,
        "value_hits_candidate":
            cand_counts["value_hits"] if scored else None,
        "safety_note": safety_note,
        "note": f"reextract_sample n={len(sample_ids)} spent={spent:.1f}; "
                + safety_note,
    }


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


#: claim_limits 文案表 —— 晋升记录里对外口径的上限,按 (basis, 是否重抽) 取
_CLAIM_LIMITS = {
    ("evo_replay_only", False): (
        "未经未见资格集评测 —— 公开口径仅限「实现了有界改进机制」,"
        "不得声称「在未见数据上减少人工」"
    ),
    ("evo_truth_replay", False): (
        "在本 workspace 已有真值文档上:负载不升且静默错不升;"
        "仍未经未见封箱资格集(SEALED-2)评测 —— "
        "不得声称「在未见数据上减少人工」。"
    ),
    ("reextract_sample", True): (
        "schema 候选经样本重抽评测;公开口径限本样本 + Gate 2 数字,"
        "不得声称未见封箱减负(唯一的封箱资格集 SEALED-2 已撤销)。"
    ),
}

#: (basis, reextract) → 标记在但资格集已撤销时的口径。**与「没跑过」分开写**:
#: SEALED-2 跑过且过了 Gate 2,失效的是那个集的留出性,不是那次评测。
#: 写成「仍未经封箱资格集评测」会暗示「去跑一次就能升」—— 那条路已经关了。
_CLAIM_LIMITS_REVOKED = (
    "本候选持有 SEALED-2 资格标记,但**该资格已于 2026-08-07 撤销**:"
    "SEALED-2 在开发期被反复使用,留出性已破,"
    "「在未见封箱集上……」这句的主语不再成立。"
    "公开口径退回本 workspace 真值范围;"
    "要恢复未见封箱口径,须换一个冻结后才见到的新集(SEALED-3)。"
)

#: 封箱资格集的留出状态。**留出一旦破了就永久破了**,所以这条记在代码里
#: 而不是文档里 —— 口径升级是代码判的,提醒管不住一个重新造出来的标记文件。
#:
#: 撤销 SEALED-2 的理由是可点验的,不是谨慎起见:
#:   - `doctype.CLASSES` 的判别 token 是照着 S2 的 `invoice_type` 自由文本
#:     拼法写的(见 docs/DOCTYPE_EVIDENCE_2026-08-07.md §词表去污);
#:   - 阶段 D 主体方向原型直接对着 S2 的 93/95 份评分并据此 KILL;
#:   - S2 阻断名单里有 4 份被逐页看过。
#: 三条都发生在「资格集」这个身份之下,任何一条都足以让它不再是未见集。
SEALED_SET_REVOCATIONS: dict[str, dict[str, str]] = {
    "SEALED-2": {
        "revoked_on": "2026-08-07",
        "reason": "开发期反复使用:doctype 词表照其自由文本拼法写、"
                  "阶段 D 原型对其评分、阻断名单 4 份逐页看过",
        "recorded_in": "docs/SEALED2_RESULTS.md",
    },
}


def sealed_set_revocation(name: str = "SEALED-2") -> dict[str, str] | None:
    """该封箱集的留出资格是否已被撤销。撤销了就返回撤销记录,否则 None。"""
    rec = SEALED_SET_REVOCATIONS.get(name)
    return dict(rec) if rec else None


def sealed2_qualifies(workspace: Path, candidate_id: str) -> bool:
    """`improve/sealed2_qualified.ok` 是否为**这个候选**背书。

    2026-08-06 修:原实现只看标记文件在不在,于是标记变成了 workspace 级的
    通行证 —— 一个刚从 12 份 HITL 挖出来的新候选,也会被盖上「已在 SEALED-2
    资格集上通过、可对外说在未见封箱集上减负」。实测复现:due_date 缺席
    cohort 在本 workspace 的 12 份上 silent_absent 0→0,而同一条 cohort 在
    88 份未见文档上实测会多出 5 个真实到期日被静默丢掉(见
    docs/LOOP_GENERALIZATION_2026-08-06.md 同口径复算)。标记说的是
    「SEALED-2 跑过一次,资格化的是某个 harness」,不是「本 workspace 以后
    任何候选都算跑过」。

    因此:标记必须点名它资格化的 harness,且必须点到这个候选,才作数。
    没点名的旧标记一律**不**升级口径(宪章六:不说工件证明不了的话)。
    """
    path = Path(workspace) / "improve" / "sealed2_qualified.ok"
    if not path.exists():
        return False
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(body, dict) and body.get("harness_id") == candidate_id


def gate_verdict(evaluation: dict, *, sealed2_qualified: bool = False) -> dict:
    """评测 → `{ok, refusals, gate, basis, claim_limits, safety_status}`。

    **纯函数**(不读盘、不看候选目录),因为它有两个调用方:`promote` 用它
    决定拒不拒,工作台用它在人点晋升**之前**显示同一个判定。两处必须是
    同一份代码 —— 页面上写着「可晋升」而 promote 会拒,或者反过来,
    都是把那道人工闸门变成猜谜。

    ok=False 时 `refusals` 列出全部违反项(promote 只报第一条,页面全列)。
    """
    basis_in = evaluation.get("basis") or "evo_replay_only"
    safety_status = evaluation.get("safety_status") or "unscored"
    scored = safety_status == "scored"
    reextract = basis_in == "reextract_sample"

    refusals: list[str] = []
    if evaluation.get("absence_probe_status") == "unavailable":
        missing = evaluation.get("absence_probe_missing_docs") or []
        refusals.append(
            "Gate 2 拒绝:这批 run 的 gate_report 里没有缺席探针"
            f"({len(missing)} 份文档),页面证据缺席规则一条也匹配不上。"
            "这不是「规则没效果」,是这批证据判不了 —— 用当前代码重跑 run "
            "再评(宪章四:跑不了不是通过)")
    if evaluation.get("evidenced_absent_rule_count", 0) \
            and evaluation.get("absence_probe_status") == "available":
        intrinsic_status = evaluation.get("absent_rule_truth_status")
        if intrinsic_status != "scored":
            refusals.append(
                "Gate 2 拒绝:页面证据缺席规则未取得 QA 前真值评分"
                "(零匹配或标注记录不完整),不能给安全结论")
        elif evaluation.get("absent_rule_truth_conflicts_candidate", 0) > 0:
            refusals.append(
                "Gate 2 拒绝:页面证据缺席规则在 QA 前命中 "
                f"{evaluation['absent_rule_truth_conflicts_candidate']} 个"
                "真值实际存在槽;页面上没印标签不等于真的没有这个字段")
    if evaluation.get("class_absent_rule_count", 0):
        intrinsic_status = evaluation.get("absent_rule_truth_status")
        if intrinsic_status != "scored":
            refusals.append(
                "Gate 2 拒绝:类别缺席规则未取得 QA 前真值评分"
                "(零匹配或标注记录不完整),不能给安全结论")
        elif evaluation.get("absent_rule_truth_conflicts_candidate", 0) > 0:
            refusals.append(
                "Gate 2 拒绝:类别缺席规则在 QA 前命中 "
                f"{evaluation['absent_rule_truth_conflicts_candidate']} 个"
                "真值实际存在槽;探针抽中不能掩盖冲突")
    if scored:
        # P1 只看真静默列(增补件 A3):口径争议单列,不进不等式。
        # 旧 eval 没有 _true 键时回退原口径,保证纯函数对两种输入都成立。
        sa_b = evaluation.get("silent_absent_true_baseline",
                              evaluation["silent_absent_baseline"])
        sa_c = evaluation.get("silent_absent_true_candidate",
                              evaluation["silent_absent_candidate"])
        sw_b = evaluation["silent_wrong_baseline"]
        sw_c = evaluation["silent_wrong_candidate"]
        if sa_c > sa_b:
            refusals.append(
                f"Gate 2 拒绝:真静默 silent_absent {sa_b} → {sa_c}"
                "(上升不许晋升;口径争议已按 truth-caliber-v1 单列)")
        if sw_c > sw_b:
            refusals.append(
                f"Gate 2 拒绝:silent_wrong {sw_b} → {sw_c}(上升不许晋升)")
        if evaluation["review_load_candidate"] > evaluation[
                "review_load_baseline"]:
            refusals.append(
                "Gate 3 拒绝:review_load 上升 —— 安全门通过也不能用更高人工负载换")

    # 资格集撤销后,标记点没点名都不再升级 basis —— 那句口径的主语
    # (「未见封箱集」)已经不成立,与标记本身无关。
    revoked = sealed_set_revocation("SEALED-2") if sealed2_qualified else None

    if reextract:
        gate = "pareto_gated" if scored else "reextract_eval"
        basis = "reextract_sample"
    elif scored:
        gate, basis = "pareto_gated", "evo_truth_replay"
    else:
        gate, basis = "eval_reexecuted", "evo_replay_only"
    return {
        "ok": not refusals,
        "refusals": refusals,
        "gate": gate,
        "basis": basis,
        # 撤销要**看得见**:退级不许静默(宪章四)。持标记的候选拿到的是
        # 「资格被撤销」的文案,不是「从来没跑过」的那句。
        "sealed2_revoked": revoked,
        "claim_limits": (_CLAIM_LIMITS_REVOKED if revoked
                         else _CLAIM_LIMITS[(basis, reextract)]),
        "safety_status": safety_status,
    }


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
    evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
    eval_basis = evaluation.get("basis") or "evo_replay_only"

    # schema 变更候选:反事实重放评测不够格
    from .harness import schema_digest as _schema_digest
    cand_schema_path = cand_dir / "extraction_schema.json"
    if cand_schema_path.exists():
        cand_schema = json.loads(cand_schema_path.read_text(encoding="utf-8"))
        cand_schema_sha = hashlib.sha256(
            cand_schema_path.read_bytes()).hexdigest()
    else:
        cand_schema = active["schema"]
        cand_schema_sha = active["schema_sha256"]
    schema_changed = (
        _schema_digest(cand_schema) != active.get("schema_digest"))
    if schema_changed and eval_basis in (
            "evo_replay_only", "evo_truth_replay"):
        raise ValueError(
            f"schema 有变更但评测 basis={eval_basis} —— "
            f"必须 improve evaluate --reextract(或 sealed2_qualified)")

    if eval_basis == "reextract_sample":
        # 重抽评测:校验样本 raw 仍在、schema digest 对得上(不与反事实重算对拍)
        if evaluation.get("candidate_schema_digest") != _schema_digest(
                cand_schema):
            raise ValueError(
                "reextract eval 的 candidate_schema_digest 与候选 schema 不符"
                " —— 评测后 schema 被改过,重新 evaluate --reextract")
        raw_root = (workspace / "improve" / "candidates" / candidate_id / "raw")
        for doc in evaluation.get("sample_doc_ids") or []:
            if not (raw_root / f"{doc}.understand.json").exists():
                raise ValueError(
                    f"reextract 样本 raw 缺失:{doc} —— 重新 evaluate --reextract")
    else:
        recomputed = _canonical(_compute_evaluation(workspace, candidate_id))
        # 反事实路径的 eval 现在带 basis 字段;重算结果需补同一 basis 再比
        recomputed_obj = json.loads(recomputed)
        recomputed_obj["basis"] = eval_basis
        if _canonical(recomputed_obj) != eval_path.read_bytes():
            # 兼容:旧 eval 无 basis 时允许与无 basis 重算对拍
            if evaluation.get("basis") is None:
                if recomputed != eval_path.read_bytes():
                    raise ValueError(
                        "重算评测与存盘 eval 逐字节不符 —— 评测输入(run 工件/裁决账本/"
                        "政策)在评测后被改动过,或 eval 文件被手改;重新 evaluate")
            else:
                raise ValueError(
                    "重算评测与存盘 eval 逐字节不符 —— 评测输入(run 工件/裁决账本/"
                    "政策)在评测后被改动过,或 eval 文件被手改;重新 evaluate")
    if not evaluation["runs"] or not evaluation["evaluated_slots"]:
        raise ValueError(
            "评测覆盖为零(没有有效 run / 没有受评槽)—— 空评测不构成晋升依据")

    # Gate 2 + Gate 3(弱):有真值则静默错不升、复核负载不升。
    # 判定在 gate_verdict 里(纯函数),工作台的晋升预览调同一个函数 ——
    # 页面说「可晋升」而这里拒,就是把人工闸门做成猜谜
    verdict = gate_verdict(
        evaluation,
        sealed2_qualified=sealed2_qualifies(workspace, candidate_id))
    if verdict["refusals"]:
        raise ValueError(verdict["refusals"][0])
    gate = verdict["gate"]
    basis = verdict["basis"]
    claim_limits = verdict["claim_limits"]
    safety_status = verdict["safety_status"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    absent_related = _absent_structure_violations(active["policy"], cand_policy)
    if absent_related:
        raise ValueError(refusal_text(absent_related))
    if manifest.get("provenance") != "human_authored":
        # 机器提议的候选:cohort 白名单 lint 是硬边界;人类署名候选的
        # 约束是署名 + 上面的评测重算门(一个不少)
        violations = lint_policy(active["policy"], cand_policy)
        if violations:
            raise ValueError(refusal_text(violations))
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
        "to_schema_digest": cand_schema_sha,
        "evaluation_digest": hashlib.sha256(eval_path.read_bytes()).hexdigest(),
        "gate": gate,
        "basis": basis,
        "claim_limits": claim_limits,
        # 候选持有 SEALED-2 标记但资格集已撤销时,把撤销记录钉进晋升记录:
        # 退级理由要留在账本里,不能只活在当时那次 gate_verdict 的返回值里。
        "sealed2_revoked": verdict["sealed2_revoked"],
        "safety_status": safety_status,
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


def mark_sealed2_qualified(workspace: Path, *, harness_id: str,
                           note: str = "") -> Path:
    """人工确认 SEALED-2 评测已过 Gate 2 后,给**具体某个 harness** 挂资格标记。

    **2026-08-07 起这个标记不再升级任何口径。** SEALED-2 的留出资格已撤销
    (`SEALED_SET_REVOCATIONS`),所以 `gate_verdict` 见到标记时给的是
    「资格已撤销」文案,basis 停在 `evo_truth_replay`。

    那为什么函数还留着、还写盘?因为**标记记录的是「那次评测确实跑过」**,
    这件事是真的,不该抹掉;失效的是它当初买到的那句口径。而且真正该钉死的
    性质是「文件在也不升级」—— 让写入口存在、并证明写出来的标记是惰性的,
    比把写入口拆掉更硬:手写一个文件同样绕不过去
    (见 `test_sealed2_qualified_wording_is_unreachable`)。

    `harness_id` 仍是必填:它是这次评测实际跑的那个 harness,标记从不跨候选
    转移。本函数不跑评测、不调 API —— 只落盘标记。
    """
    workspace = Path(workspace)
    if not str(harness_id).strip():
        raise ValueError(
            "mark_sealed2_qualified 必须点名 harness_id —— "
            "「本 workspace 跑过 SEALED-2」不等于「这个候选跑过」")
    improve_dir = workspace / "improve"
    improve_dir.mkdir(parents=True, exist_ok=True)
    path = improve_dir / "sealed2_qualified.ok"
    body = {
        "harness_id": str(harness_id).strip(),
        "marked_at_protocol": "docs/SEALED2_PROTOCOL.md",
        "doc_list": "docs/sealed2_doc_list.json",
        "note": note.strip(),
    }
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path
