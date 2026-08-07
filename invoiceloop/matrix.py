"""M3 support matrix (ARCHITECTURE.md §4 SupportRow, §7 triage).

One row per (doc, field), four dimensions rather than one score:

- support_strength:  corroborated / single_source / unsupported — counted by
  **source tier**, not decided by confidence. dws_extraction counts as one tier
  only: both modes share a front end and are known not to be independent
  (lift 2.40×), so their agreement does not qualify as a second tier.
- source_tiers:      which tiers actually support this row.
- applicability:     convention disputes go through the §4 runtime criterion —
  marked explicitly, routed to a human, and kept out of the error rate
  (charter rule five).
- limitations:       everything the system cannot vouch for, written out
  (charter rule six: what has not been measured says "not yet measured").

Triage = sort ascending by support_strength. Nothing is required to be
"trustworthy"; the ordering only has to beat random — calibration measured 4.2×
concentration, with 46% of fields covering 78% of the deviation.
"""

from __future__ import annotations

from .fields import AMOUNT_FIELDS, FIELDS, FIELD_KINDS, amount, normalise

STRENGTH_RANK = {"unsupported": 0, "single_source": 1, "corroborated": 2}


def label_convention_disputed(data: dict) -> bool:
    """§4 运行时判据:只用 DWS 自己返回的三个值,不需要真值。

    amount_due ≈ total_net 且 amount_due ≠ total_gross(0.02 容差)
    → 页面把应付额落在 Net 一侧:广告代理业 Gross 是刊例价、Net 是扣佣实付,
    与 EN 16931 方向相反。命中即标争议,不进错误率。
    """
    net, gross, due = (amount(data.get(k)) for k in ("total_net", "total_gross", "amount_due"))
    if None in (net, gross, due) or gross == net:
        return False
    return abs(due - net) <= 0.02 and abs(due - gross) > 0.02


def derive_document_records(
    doc_id: str,
    *,
    doc_claims: list[dict],
    doc_rejections: list[dict],
    gate_evaluations: dict,
    doc_blocking_findings: list[dict],
    understand_data: dict | None,
    blocked_doc: bool = False,
    cited_spans: dict[str, list[str]] | None = None,
) -> list[dict]:
    """一份文档全部槽的事实记录 —— **单一事实源**(高级裁决六)。

    三处消费同一函数,不存在投影副本:
    - build_matrix 拿它组支持矩阵行;
    - verify 语义层从包内权威工件(field_ledger + gate_report +
      raw understand)重建它,再重算路由;
    - improve.evaluate 拿它做反事实重路由。

    文档级签名是刻意的:口径争议判据(due≈net≠gross)跨字段,
    要三个金额字段都 admitted 才成立,槽级函数装不下。

    doc_claims/doc_rejections: 冻结账本中该文档的条目;
    gate_evaluations: gate_report.evaluations[doc_id];
    doc_blocking_findings: gate_report.findings 中该文档 blocking=true 的;
    understand_data: raw understand 响应的 output.data(没有则 None);
    blocked_doc: 流水线级阻断(OCR 缺失),只影响 limitations;
    cited_spans: {field: [span_id]} DWS 引用几何(复核上下文,展示用)。
    """
    cited_spans = cited_spans or {}
    claims_by_field: dict[str, list[dict]] = {}
    for c in doc_claims:
        claims_by_field.setdefault(c["field"], []).append(c)
    rejections_by_field: dict[str, list[dict]] = {}
    for r in doc_rejections:
        rejections_by_field.setdefault(r["field"], []).append(r)
    blocking_by_field: dict[str, list[dict]] = {}
    doc_level_blocking: list[dict] = []
    for f in doc_blocking_findings:
        if f["field"] is not None:
            blocking_by_field.setdefault(f["field"], []).append(f)
        else:
            doc_level_blocking.append(f)

    # §4 判据的收紧(改判据,记录在案):三个值不仅要被 DWS 返回,
    # 还必须已通过冻结绑定 —— 争议标注要落在能绑定到页面的证据上,
    # 不能落在冻结事务刚拒掉的值上。判据本身(due≈net 且 ≠gross)不变。
    admitted_amounts = {
        c["field"] for c in doc_claims if c["drafted_by"] == "dws_understand"
    }
    disputed = (
        understand_data is not None
        and {"total_net", "total_gross", "amount_due"} <= admitted_amounts
        and label_convention_disputed(understand_data)
    )

    records: list[dict] = []
    for field_name in FIELDS:
        kind = FIELD_KINDS[field_name]
        gate_verdicts = gate_evaluations.get(field_name, {})
        slot_claims = claims_by_field.get(field_name, [])
        slot_rejections = rejections_by_field.get(field_name, [])

        emitted = next(
            (c for c in slot_claims if c["drafted_by"] == "dws_understand"), None
        )
        value = (emitted["value"] if emitted
                 else (understand_data.get(field_name)
                       if understand_data is not None else None))
        want = normalise(value, kind) if emitted else None

        # ---- 来源层级
        tiers: list[str] = []
        limitations: list[str] = []
        if emitted:
            tiers.append("dws_extraction")
            if emitted["span_ids"]:
                tiers.append("independent_ocr")
            else:
                limitations.append("value_not_in_cited_span")
            corroborating_readers = [
                c["drafted_by"]
                for c in slot_claims
                if c["drafted_by"].startswith("vision:")
                and normalise(c["value"], kind) is not None
                and normalise(c["value"], kind) == want
            ]
            if corroborating_readers:
                tiers.append("vision_reading")
            if gate_verdicts.get("arithmetic_consistency") == "pass":
                tiers.append("arithmetic")
            if not emitted["span_ids"]:
                pass  # 单源不等于错;读图在页面别处找到的行正是这一档
        else:
            if slot_rejections:
                limitations.append("draft_rejected_at_freeze")
            if understand_data is not None and (
                    understand_data.get(field_name) is None
                    or str(understand_data.get(field_name)).strip() == ""):
                limitations.append("dws_returned_no_value")
            # DWS 的值被拒/缺失,而读图在页面上找到了能绑定的值 ——
            # 读图唯一有增量价值的地方,必须显式亮出来(§5.2 的立法理由)
            for c in slot_claims:
                if c["drafted_by"].startswith("vision:"):
                    limitations.append(f"vision_offers:{c['drafted_by'][7:]}={c['value']}")

        # ---- 强度:层级数决定,不是分数
        if not emitted:
            strength = "unsupported"
        elif len(tiers) >= 2:
            strength = "corroborated"
        else:
            strength = "single_source"

        # ---- 适用范围(宪章五:争议显式,进人工裁决,不进错误率)
        applicability = "matches"
        if disputed and field_name in ("total_net", "total_gross", "amount_due"):
            applicability = "label_convention_disputed"
            limitations.append(
                "纸面 Gross=刊例价、Net=扣 15% 佣后实付;EN 16931 方向相反,两种读法都在"
            )

        if gate_verdicts.get("visual_corroboration") == "unavailable":
            limitations.append("visual_not_measured")
        if blocked_doc:
            limitations.append("ocr_unavailable_pipeline_blocked")
        if gate_verdicts.get("citation_holds") == "unavailable" and emitted:
            limitations.append("citation_not_checkable")

        # 文档级阻断(响应缺失、门禁异常)属于这份文档的每一行 ——
        # 基础设施没跑,这份文档上没有任何一行算"查过了"
        blocking_slot = bool(blocking_by_field.get(field_name))
        blocking_doc = bool(doc_level_blocking)
        blocking = blocking_by_field.get(field_name, []) + doc_level_blocking

        records.append({
            "doc_id": doc_id,
            "field": field_name,
            "value": value if (emitted or understand_data is not None) else None,
            "claim_id": emitted["claim_id"] if emitted else None,
            "support_strength": strength,
            "source_tiers": tiers,
            "applicability": applicability,
            "limitations": limitations,
            "requires_adjudication": None,  # 由 routing 层统一填充
            "gate_verdicts": gate_verdicts,
            "span_ids": emitted["span_ids"] if emitted else [],
            "cited_span_ids": cited_spans.get(field_name, []),
            "rejections": slot_rejections,
            "blocking_findings": [f["finding_id"] for f in blocking],
            # 阻断分级随行落盘:verify 要凭行内事实重算 routing
            # (裁决三),光靠 blocking_findings 分不出文档级/槽位级
            "slot_blocking": blocking_slot,
            "doc_blocked": blocking_doc,
        })
    return records


def facts_of(record: dict) -> dict:
    """槽位记录 → 喂给 routing 的六键事实(投影方向唯一,反向不存在)。"""
    return {
        "doc_id": record["doc_id"], "field": record["field"],
        "strength": record["support_strength"],
        "gate_verdicts": record["gate_verdicts"],
        "applicability": record["applicability"],
        "slot_blocking": record["slot_blocking"],
        "doc_blocked": record["doc_blocked"],
    }


def build_matrix(
    doc_ids: list[str],
    *,
    understand: dict,
    claims: list[dict],
    rejections: list[dict],
    gate_report: dict,
    vision_answers: dict,
    blocked_docs: frozenset[str] = frozenset(),
    spans: list[dict] = (),
    policy: dict | None = None,
    harness_id: str = "HAR-0001",
) -> tuple[dict, dict]:
    """从冻结账本 + 门禁报告 + 存盘证据组矩阵。纯函数,零 API,可重算。

    返回 (support_matrix, routing_report)。分诊决定(哪槽要人看)由
    routing.py 按 policy 产出 —— matrix 只消费结果,不再内联判据(P0-3)。
    policy=None 时用包内 HAR-0001(保守默认)。

    blocked_docs: 因 OCR 缺失被流水线整体阻断的文档 —— 行上必须有字,
    不然"这份没查"和"查了没支持"看起来一样(宪章四)。
    spans: 已注册证据片段。行上带两份几何证据,用途不同:
    span_ids(值落在哪,印证)与 cited_span_ids(DWS 指向哪,复核上下文)。
    被拒的行没有声明、没有前者,但后者是人类裁决"值到底在不在页上"的依据 ——
    没有它,被拒的行恰恰是最看不懂的行(人类验收 T1 实测)。
    """
    # 索引:claim / rejection 按 doc;跨文档索引在 derive 函数里按字段重建
    claims_by_doc: dict[str, list[dict]] = {}
    for c in claims:
        claims_by_doc.setdefault(c["doc_id"], []).append(c)
    rejections_by_doc: dict[str, list[dict]] = {}
    for r in rejections:
        rejections_by_doc.setdefault(r["doc_id"], []).append(r)

    blocking_by_doc: dict[str, list[dict]] = {}
    for f in gate_report["findings"]:
        if f["blocking"]:
            blocking_by_doc.setdefault(f["doc_id"], []).append(f)

    cited_by_doc: dict[str, dict[str, list[str]]] = {}
    for s in spans:
        cited_by_doc.setdefault(s["doc_id"], {}).setdefault(
            s["field"], []).append(s["span_id"])

    rows: list[dict] = []
    slot_facts: list[dict] = []  # 与 rows 平行:喂给 routing 的槽位事实
    for doc_id in doc_ids:
        u = understand.get(doc_id)
        records = derive_document_records(
            doc_id,
            doc_claims=claims_by_doc.get(doc_id, []),
            doc_rejections=rejections_by_doc.get(doc_id, []),
            gate_evaluations=gate_report["evaluations"].get(doc_id, {}),
            doc_blocking_findings=blocking_by_doc.get(doc_id, []),
            understand_data=u.data if u is not None else None,
            blocked_doc=doc_id in blocked_docs,
            cited_spans=cited_by_doc.get(doc_id),
        )
        rows.extend(records)
        slot_facts.extend(facts_of(r) for r in records)

    # ---- 分诊路由:策略决定哪槽要人看(P0-3)。requires 与旧内联逻辑
    # 逐字节等价由 routing.HAR-0001 默认策略保证 + heldout 零 diff 钉死
    if policy is None:
        from .harness import load_active

        policy = load_active()["policy"]
    from .routing import build_routing_report
    from .fields import TIER1 as _T1

    routing_report = build_routing_report(
        slot_facts, policy, harness_id=harness_id,
        tier_of=lambda f: "TIER1" if f in _T1 else "TIER2")
    for row, routed in zip(rows, routing_report["routes"]):
        # requires_adjudication:兼容字段(route != auto_accept),含 auto_absent;
        # 历史工件与 improve 旧 run 推断依赖它 —— 勿改语义、勿用于对外口径。
        # in_human_queue:交付/面板口径(route not in auto_accept|auto_absent)。
        row["requires_adjudication"] = routed["route"] != "auto_accept"
        row["in_human_queue"] = routed["route"] not in ("auto_accept", "auto_absent")
        row["route"] = routed["route"]
        row["reason_codes"] = routed["reason_codes"]

    rows.sort(key=lambda r: (
        STRENGTH_RANK[r["support_strength"]],
        not r["in_human_queue"],
        r["doc_id"],
        r["field"],
    ))

    summary = {
        "docs": len(doc_ids),
        "slots": len(rows),
        "by_strength": {
            s: sum(1 for r in rows if r["support_strength"] == s)
            for s in ("unsupported", "single_source", "corroborated")
        },
        # 兼容计数(含 auto_absent);对外叙事用 human_queue
        "requires_adjudication": sum(1 for r in rows if r["requires_adjudication"]),
        "human_queue": sum(1 for r in rows if r["in_human_queue"]),
        "machine_decided": sum(1 for r in rows if r["route"] == "auto_accept"),
        "machine_absent": sum(1 for r in rows if r["route"] == "auto_absent"),
        "applicability_disputed": sum(
            1 for r in rows if r["applicability"] == "label_convention_disputed"
        ),
        "blocking_findings": sum(1 for f in gate_report["findings"] if f["blocking"]),
        "claims_admitted": len(claims),
        "drafts_rejected": len(rejections),
        "rejected_by_drafter": _count_by(rejections, "drafted_by"),
    }
    return {"rows": rows, "summary": summary}, routing_report


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return dict(sorted(out.items()))
