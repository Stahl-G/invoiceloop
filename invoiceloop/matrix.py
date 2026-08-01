"""M3 支持矩阵(ARCHITECTURE.md §4 SupportRow / §7 分诊)。

每行一个 (doc, field),四维,不是一个分数:

- support_strength:  corroborated / single_source / unsupported —— 按**来源层级**数,
  不是按置信度拍。dws_extraction 只算一层(双模式共享前端,已知不独立,
  lift 2.40×,agreement 不够格当第二层)。
- source_tiers:      这一行实际有哪些层在支持。
- applicability:     口径争议走 §4 运行时判据,显式标注、进人工裁决、不进错误率(宪章五)。
- limitations:       说不准的地方逐条写出(宪章六:未测量的写"尚未测量")。

分诊 = 按 support_strength 升序排列,不要求任何一档"可信",
只要求排序优于随机(校准:4.2× 集中度,看 46% 字段覆盖 78% 偏差)。
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


def build_matrix(
    doc_ids: list[str],
    *,
    understand: dict,
    claims: list[dict],
    rejections: list[dict],
    gate_report: dict,
    vision_answers: dict,
) -> dict:
    """从冻结账本 + 门禁报告 + 存盘证据组矩阵。纯函数,零 API,可重算。"""
    # 索引:claim / rejection 按 (doc, field, drafted_by)
    claims_by_slot: dict[tuple[str, str], list[dict]] = {}
    for c in claims:
        claims_by_slot.setdefault((c["doc_id"], c["field"]), []).append(c)
    rejections_by_slot: dict[tuple[str, str], list[dict]] = {}
    for r in rejections:
        rejections_by_slot.setdefault((r["doc_id"], r["field"]), []).append(r)

    blocking_by_slot: dict[tuple[str, str], list[dict]] = {}
    blocking_by_doc: dict[str, list[dict]] = {}
    for f in gate_report["findings"]:
        if not f["blocking"]:
            continue
        if f["field"] is not None:
            blocking_by_slot.setdefault((f["doc_id"], f["field"]), []).append(f)
        else:
            blocking_by_doc.setdefault(f["doc_id"], []).append(f)

    rows: list[dict] = []
    for doc_id in doc_ids:
        u = understand.get(doc_id)
        evaluations = gate_report["evaluations"].get(doc_id, {})
        disputed = label_convention_disputed(u.data) if u is not None else False

        for field_name in FIELDS:
            slot = (doc_id, field_name)
            kind = FIELD_KINDS[field_name]
            gate_verdicts = evaluations.get(field_name, {})
            slot_claims = claims_by_slot.get(slot, [])
            slot_rejections = rejections_by_slot.get(slot, [])

            emitted = next(
                (c for c in slot_claims if c["drafted_by"] == "dws_understand"), None
            )
            value = emitted["value"] if emitted else (u.data.get(field_name) if u else None)
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
                if u is not None and (u.data.get(field_name) is None
                                      or str(u.data.get(field_name)).strip() == ""):
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
            if gate_verdicts.get("citation_holds") == "unavailable" and emitted:
                limitations.append("citation_not_checkable")

            blocking = blocking_by_slot.get(slot, []) + (
                blocking_by_doc.get(doc_id, []) if u is None else []
            )
            requires = (
                strength == "unsupported"
                or any(v == "fail" for v in gate_verdicts.values())
                or any(v == "warning" for v in gate_verdicts.values())
                or applicability == "label_convention_disputed"
                or bool(blocking)
            )

            rows.append({
                "doc_id": doc_id,
                "field": field_name,
                "value": value if (emitted or u is not None) else None,
                "claim_id": emitted["claim_id"] if emitted else None,
                "support_strength": strength,
                "source_tiers": tiers,
                "applicability": applicability,
                "limitations": limitations,
                "requires_adjudication": requires,
                "gate_verdicts": gate_verdicts,
                "span_ids": emitted["span_ids"] if emitted else [],
                "rejections": slot_rejections,
                "blocking_findings": [f["finding_id"] for f in blocking],
            })

    rows.sort(key=lambda r: (
        STRENGTH_RANK[r["support_strength"]],
        not r["requires_adjudication"],
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
        "requires_adjudication": sum(1 for r in rows if r["requires_adjudication"]),
        "applicability_disputed": sum(
            1 for r in rows if r["applicability"] == "label_convention_disputed"
        ),
        "blocking_findings": sum(1 for f in gate_report["findings"] if f["blocking"]),
        "claims_admitted": len(claims),
        "drafts_rejected": len(rejections),
        "rejected_by_drafter": _count_by(rejections, "drafted_by"),
    }
    return {"rows": rows, "summary": summary}


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return dict(sorted(out.items()))
