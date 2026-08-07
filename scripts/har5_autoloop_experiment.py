"""HAR-0005:88 份「自动进 evo loop」→ 在 SEALED-2 上验证(零 API)。

问题:如果把 88 份未人工文档自动喂进改进循环、不经人裁生成新 harness,
在一个它没被拟合过的封箱集上会怎样?

三个臂(缺席 cohort 全部只在 88 份 SEALED-1 上挖,SEALED-2 只用于验证):

  HAR-0004   当前 active,基线。
  HAR-0005a  **守 Gate 2 的自动挖矿**:枚举 8 个候选字段,只收「静默缺席错
             不上升」的。真值参与,等于给循环一个实验室神谕 + 保留安全门。
  HAR-0005b  **真正无人的自动挖矿**:没有人、也没有真值,循环唯一能看见的
             信号是「抽取器多久返回一次空」。规则:88 份里空值率 ≥20% 的字段
             一律声明预期缺失。这是一个朴素自演化 harness 会做的事。

两条纪律:
- 两个 HAR-0005 **都不进晋升链**。它们是研究臂,`improve promote` 要人签字;
  把真值拟合出来的策略盖成 active 会直接违反宪章六。
- 预测先写死再跑,偏差照登(THRESHOLDS §6f)。

用法:python3 scripts/har5_autoloop_experiment.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop import crossdoc, gates, harness, matrix, routing  # noqa: E402
from invoiceloop.fields import FIELD_KINDS, TIER1  # noqa: E402
from invoiceloop.matrix import derive_document_records, facts_of  # noqa: E402
from invoiceloop.ocr import OcrUnavailable, load_ocr  # noqa: E402
from invoiceloop.safety_metrics import score_routes, truth  # noqa: E402

EMPTY_RATE_THRESHOLD = 0.20  # HAR-0005b 的自动规则,跑之前定死

PREDICTIONS = """预测(跑之前写死):
  HAR-0005a 在 SEALED-2:human_queue 与 HAR-0004 基本持平(±5 槽),
            静默缺席错 3 → 3~4。理由:88 份上守 Gate 2 只挖得出 seller_name,
            值 1 个槽,拟合集上就没头寸,封箱集上更不该有。
  HAR-0005b 在 SEALED-2:human_queue 大幅下降(预测 34%~40%),
            静默缺席错 3/100 → 25~35 区间,缺席错率从 3% 升到 15% 以上。
            理由:88 份上 due_date/total_net/buyer_name 合计省 62 槽、
            赔 14 个静默错(4.4 槽/错),按 SEALED-2 十倍槽数线性外推。
  最想知道的是:88 份上算出的价签,在 SEALED-2 上还准不准。
"""


def _absent(policy):
    return frozenset(c["field"] for c in (policy.get("absent_expected_cohorts") or [])
                     if c.get("field"))


def _with(policy, fields, tag):
    p = copy.deepcopy(policy)
    p.setdefault("absent_expected_cohorts", [])
    p["absent_expected_cohorts"] = list(p["absent_expected_cohorts"]) + [
        {"id": f"{tag}{i}", "field": f} for i, f in enumerate(sorted(fields))]
    return p


# ---------------------------------------------------------------- 挖矿:88 份
def mine_on_88(h4):
    """在 88 份 SEALED-1 未人工文档上挖 cohort。返回 (守门集, 无人集, 明细)。"""
    os.environ["INVOICELOOP_CORPUS"] = str(REPO / "runs" / "sealed1-workspace")
    for m in ("invoiceloop.dws",):
        sys.modules.pop(m, None)
    from invoiceloop.dws import load_response

    hitl = {p.stem for p in (REPO / "runs/hitl-sealed/input/pdfs").glob("*.pdf")}
    ids = json.load(open(REPO / "docs/sealed1_doc_list.json"))["doc_ids"]
    unseen = [d for d in ids if d not in hitl]
    gate = json.load(open(REPO / "runs/sealed1/gate_report.json"))
    claims = json.load(open(REPO / "runs/sealed1/field_ledger.json"))["claims"]
    by_doc = {}
    for c in claims:
        by_doc.setdefault(c["doc_id"], []).append(c)
    und = {d: (load_response(d, "understand").data
               if load_response(d, "understand") else None) for d in ids}

    def arm(absent):
        # 挖矿基线必须是**当前 active harness**,不是包内 HAR-0001 ——
        # 用错基线会改变哪些 cohort 过得了 Gate 2(实测 seller_name 在
        # HAR-0001 基线下代价 1、在 HAR-0004 基线下代价 0)。
        pol = _with({**h4, "absent_expected_cohorts": []}, absent, "M")
        routes = []
        for doc in unseen:
            blk = [f for f in gate["findings"]
                   if f.get("blocking") and f.get("doc_id") == doc
                   and not (f.get("gate_id") == "extraction_present"
                            and f.get("field") in absent)]
            recs = derive_document_records(
                doc, doc_claims=by_doc.get(doc, []), doc_rejections=[],
                gate_evaluations=gate["evaluations"].get(doc, {}),
                doc_blocking_findings=blk, understand_data=und[doc])
            fs = routing.apply_absent_expected([facts_of(r) for r in recs], pol)
            routes.extend(routing.route_slots(
                fs, pol, tier_of=lambda f: "TIER1" if f in TIER1 else "TIER2"))
        return score_routes(routes, truth_of=truth,
                            understand_of=lambda d: und.get(d))

    base_absent = _absent(h4)
    base = arm(base_absent)

    # 1) 守 Gate 2:逐字段试,只收静默缺席错不升的
    gated, detail = set(), []
    for f in FIELD_KINDS:
        if f in base_absent:
            continue
        c = arm(base_absent | {f})
        saved = base["review"] - c["review"]
        cost = c["silent_absent"] - base["silent_absent"]
        detail.append((f, saved, cost))
        if saved > 0 and cost <= 0:
            gated.add(f)

    # 2) 无人:只看空值率,不看真值
    empty = {f: sum(1 for d in unseen
                    if not (und[d] or {}).get(f)) for f in FIELD_KINDS}
    auton = {f for f, n in empty.items()
             if n / len(unseen) >= EMPTY_RATE_THRESHOLD} - base_absent

    print(f"88 份挖矿明细(基线复核 {base['review']}/{base['slots']}, "
          f"静默缺席错 {base['silent_absent']}/{base['absent_hits']}):")
    print(f"  {'字段':<16}{'空值率':>8}{'省下':>7}{'静默错代价':>11}   守Gate2  无人规则")
    for f, saved, cost in sorted(detail, key=lambda x: -x[1]):
        r = empty[f] / len(unseen)
        print(f"  {f:<16}{r:>7.0%}{saved:>7}{cost:>11}"
              f"{'      ✅' if f in gated else '      —'}"
              f"{'       ✅' if f in auton else '       —'}")
    print(f"\n  HAR-0005a 收(守 Gate 2):{sorted(gated) or '空'}")
    print(f"  HAR-0005b 收(空值率≥{EMPTY_RATE_THRESHOLD:.0%},无人无真值):"
          f"{sorted(auton) or '空'}\n")
    return gated, auton


# ------------------------------------------------------------ 验证:SEALED-2
def verify_on_sealed2(arms):
    os.environ["INVOICELOOP_CORPUS"] = str(REPO / "runs" / "sealed2-workspace")
    sys.modules.pop("invoiceloop.dws", None)
    from invoiceloop.dws import load_response

    src = REPO / "runs/sealed2"
    ids = json.load(open(REPO / "docs/sealed2_doc_list.json"))["doc_ids"]
    ledger = json.loads((src / "field_ledger.json").read_text())
    spans = json.loads((src / "evidence_span_registry.json").read_text())
    frozen = json.loads((src / "gate_report.json").read_text())
    rej = []
    reasons = {"draft_binding_rejected": "binding",
               "draft_unknown_field_rejected": "unknown_field",
               "draft_empty_value_rejected": "empty_value",
               "draft_prewritten_id_rejected": "prewritten_claim_id"}
    for line in (src / "event_log.jsonl").read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            if e["event"] in reasons:
                rej.append({"reason": reasons[e["event"]], "doc_id": e["doc_id"],
                            "field": e.get("field"), "value": e.get("value"),
                            "drafted_by": e.get("drafted_by", "unknown")})
    und = {d: load_response(d, "understand") for d in ids}
    agt = {d: load_response(d, "agentic") for d in ids}
    blocked = set()
    for d in ids:
        try:
            load_ocr(d)
        except OcrUnavailable:
            blocked.add(d)
    dups = crossdoc.duplicate_groups(ledger["claims"])
    digest = frozen["input_signature"]["artifact_digest"]

    print(f"{'臂':<12}{'human_queue':>17}{'machine_absent':>15}"
          f"{'静默缺席错':>14}{'静默错值':>13}{'触达':>8}")
    print("-" * 84)
    out = {}
    for hid, pol in arms:
        absent = _absent(pol)
        gate = gates.run_gates(
            ids, understand=und, agentic=agt, vision_answers={},
            ledger_sha256=ledger["sha256"], artifact_digest=digest,
            ocr_blocked=frozenset(blocked), duplicate_groups=dups,
            absent_expected=absent, agentic_optional=frozenset())
        support, rout = matrix.build_matrix(
            ids, understand=und, claims=ledger["claims"], rejections=rej,
            gate_report=gate, vision_answers={}, blocked_docs=frozenset(blocked),
            spans=spans, policy=pol, harness_id=hid)
        s = support["summary"]
        c = score_routes(rout["routes"], truth_of=truth,
                         understand_of=lambda d: und[d].data if und[d] else None)
        touched = len({r["doc_id"] for r in rout["routes"]
                       if r["route"] not in ("auto_accept", "auto_absent")})
        n = s["slots"]
        rate = f"{c['silent_absent']}/{c['absent_hits']}"
        pct = (c["silent_absent"] / c["absent_hits"]) if c["absent_hits"] else 0
        print(f"{hid:<12}{s['human_queue']:>8}/{n} ({s['human_queue']/n:>5.1%})"
              f"{s['machine_absent']:>15}{rate:>10} ({pct:>4.0%})"
              f"{c['silent_wrong']:>8}/{c['value_hits']:<5}{touched:>5}/{len(ids)}")
        out[hid] = (s["human_queue"], c["silent_absent"], c["absent_hits"])
    return out


def main() -> None:
    h4 = json.load(open(REPO / "runs/sealed2-workspace/harnesses"
                        / "HAR-0004/routing_policy.json"))
    print(PREDICTIONS)
    gated, auton = mine_on_88(h4)
    res = verify_on_sealed2([
        ("HAR-0004", h4),
        ("HAR-0005a", _with(h4, gated, "G")),
        ("HAR-0005b", _with(h4, auton, "A")),
    ])
    b, a5 = res["HAR-0004"], res["HAR-0005b"]
    saved = b[0] - a5[0]
    cost = a5[1] - b[1]
    print(f"\n无人臂 HAR-0005b 在 SEALED-2 上的价签:"
          f"省 {saved} 槽,赔 {cost} 个静默缺席错 = "
          f"{saved/cost:.1f} 槽/错" if cost else "")


if __name__ == "__main__":
    main()
