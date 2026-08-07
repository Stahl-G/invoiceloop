"""AP 按「碰过几张单」计价 —— 那这个项目在文档口径上到底买到了什么?(零 API)

字段级复核负载 56.1%→46.8% 在按张计价的 AP 里可能一文不值:只要一张单还剩
一个字段要看,人就得把它打开。document-touch 是 10 个字段的**合取**,
每字段自动率 p 时零触达概率 ≈ p^10 —— p=0.53 给出 0.2%,这正是实测的 1/100。
渐进的字段级改进在数学上碰不到这个指标。

本脚本量三件事:
1. 每份单据「要人看几个字段」的分布(不是二值 pending);
2. 零触达单据数,在四种「哪些字段算数」的口径下;
3. 要让零触达上去,每字段自动率得到多少 —— 以及现有证据够不够。

用法:python3 scripts/doc_touch_economics.py
"""
from __future__ import annotations

import collections
import copy
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("INVOICELOOP_CORPUS", str(REPO / "runs" / "sealed2-workspace"))

from invoiceloop import crossdoc, dws, gates, harness, matrix  # noqa: E402
from invoiceloop.fields import TIER1  # noqa: E402
from invoiceloop.ocr import OcrUnavailable, load_ocr  # noqa: E402
from invoiceloop.safety_metrics import score_routes, truth  # noqa: E402

SRC = REPO / "runs" / "sealed2"
AUTO = ("auto_accept", "auto_absent")

#: 四种「一张单要放行,哪些字段必须有交代」的口径。
#: 前两种是本项目现有假设;后两种是真实 AP 的下限 —— 过账只需要能把钱
#: 付对、能对上采购单、能记到正确期间。字段集是**业务决定**,这里只标价。
SCOPES = {
    "全部 10 个字段": None,
    "TIER1(6 个)": set(TIER1),
    "过账必需(5 个)": {"invoice_number", "seller_name", "amount_due",
                        "issue_date", "seller_vat_id"},
    "付款必需(3 个)": {"invoice_number", "seller_name", "amount_due"},
}


def _rejections():
    reasons = {"draft_binding_rejected": "binding",
               "draft_unknown_field_rejected": "unknown_field",
               "draft_empty_value_rejected": "empty_value",
               "draft_prewritten_id_rejected": "prewritten_claim_id"}
    out = []
    for line in (SRC / "event_log.jsonl").read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            if e["event"] in reasons:
                out.append({"reason": reasons[e["event"]], "doc_id": e["doc_id"],
                            "field": e.get("field"), "value": e.get("value"),
                            "drafted_by": e.get("drafted_by", "unknown")})
    return out


def _with(policy, fields, tag):
    p = copy.deepcopy(policy)
    p["absent_expected_cohorts"] = list(p.get("absent_expected_cohorts") or []) + [
        {"id": f"{tag}{i}", "field": f} for i, f in enumerate(sorted(fields))]
    return p


def main() -> None:
    ids = json.load(open(REPO / "docs/sealed2_doc_list.json"))["doc_ids"]
    ledger = json.loads((SRC / "field_ledger.json").read_text())
    spans = json.loads((SRC / "evidence_span_registry.json").read_text())
    frozen = json.loads((SRC / "gate_report.json").read_text())
    rej = _rejections()
    und = {d: dws.load_response(d, "understand") for d in ids}
    agt = {d: dws.load_response(d, "agentic") for d in ids}
    blocked = set()
    for d in ids:
        try:
            load_ocr(d)
        except OcrUnavailable:
            blocked.add(d)
    dups = crossdoc.duplicate_groups(ledger["claims"])
    digest = frozen["input_signature"]["artifact_digest"]

    h1 = harness._builtin_policy()
    h4 = json.load(open(REPO / "runs/sealed2-workspace/harnesses"
                        / "HAR-0004/routing_policy.json"))
    h5b = _with(h4, {"buyer_name", "due_date", "total_net"}, "A")

    def routes_for(pol):
        absent = frozenset(c["field"] for c in
                           (pol.get("absent_expected_cohorts") or []) if c.get("field"))
        gate = gates.run_gates(
            ids, understand=und, agentic=agt, vision_answers={},
            ledger_sha256=ledger["sha256"], artifact_digest=digest,
            ocr_blocked=frozenset(blocked), duplicate_groups=dups,
            absent_expected=absent, agentic_optional=frozenset())
        _, rout = matrix.build_matrix(
            ids, understand=und, claims=ledger["claims"], rejections=rej,
            gate_report=gate, vision_answers={}, blocked_docs=frozenset(blocked),
            spans=spans, policy=pol, harness_id="X")
        return rout["routes"], gate

    arms = (("HAR-0001", h1), ("HAR-0004", h4), ("HAR-0005b", h5b))
    all_routes = {}
    for hid, pol in arms:
        all_routes[hid], _ = routes_for(pol)

    # ---- 1. 每份单据要人看几个字段
    print("每份单据「要人看几个字段」的分布(SEALED-2,100 份):\n")
    print(f"{'要看字段数':<12}" + "".join(f"{h:>12}" for h, _ in arms))
    print("-" * 48)
    hist = {}
    for hid, _ in arms:
        c = collections.Counter()
        per = collections.Counter()
        for r in all_routes[hid]:
            if r["route"] not in AUTO:
                per[r["doc_id"]] += 1
        for d in ids:
            c[per.get(d, 0)] += 1
        hist[hid] = c
    for k in range(0, 11):
        row = "".join(f"{hist[h][k]:>12}" for h, _ in arms)
        if any(hist[h][k] for h, _ in arms):
            print(f"{k:<12}{row}")
    print()
    for hid, _ in arms:
        per = [sum(1 for r in all_routes[hid]
                   if r["doc_id"] == d and r["route"] not in AUTO) for d in ids]
        per.sort()
        print(f"  {hid}: 中位 {per[len(per)//2]}/10 个字段, "
              f"均值 {sum(per)/len(per):.1f}/10")

    # ---- 2. 零触达,按口径
    print("\n\n零触达单据数(该口径内的字段全部机器判定 → 人根本不用打开):\n")
    print(f"{'口径':<20}" + "".join(f"{h:>12}" for h, _ in arms))
    print("-" * 56)
    for label, scope in SCOPES.items():
        cells = []
        for hid, _ in arms:
            touched = {r["doc_id"] for r in all_routes[hid]
                       if r["route"] not in AUTO
                       and (scope is None or r["field"] in scope)}
            cells.append(len(ids) - len(touched))
        print(f"{label:<20}" + "".join(f"{c:>12}" for c in cells))

    # ---- 3. 零触达要多高的每字段自动率
    print("\n\n要把零触达做上去,每字段自动率得多少(合取,10 字段):\n")
    print(f"  {'每字段自动率':<14}{'零触达期望':>12}   现状")
    for p in (0.53, 0.70, 0.80, 0.90, 0.95, 0.99):
        note = ""
        if abs(p - 0.53) < 0.01:
            note = "← HAR-0004 实测 (532/1000)"
        print(f"  {p:>10.0%}    {p**10:>12.1%}   {note}")

    # ---- 4. 天花板:抽取器压根没返回值的槽,任何策略都救不了
    empty = sum(1 for d in ids for f in
                ("invoice_number", "issue_date", "due_date", "seller_name",
                 "seller_vat_id", "buyer_name", "total_net", "total_vat",
                 "total_gross", "amount_due")
                if not (und[d].data if und[d] else {}).get(f))
    docs_with_empty = len({d for d in ids for f in
                           ("invoice_number", "issue_date", "due_date",
                            "seller_name", "seller_vat_id", "buyer_name",
                            "total_net", "total_vat", "total_gross", "amount_due")
                           if not (und[d].data if und[d] else {}).get(f)})
    print(f"\n\n天花板:DWS 返回空的槽 {empty}/1000,分布在 {docs_with_empty}/100 份单据上。")
    print("  只要「空值必须有人交代」,这 %d 份就永远零触达不了 ——" % docs_with_empty)
    print("  除非把空值也自动记为缺失,那就是 HAR-0005b 那条路(实测 7% 静默错)。")


if __name__ == "__main__":
    main()
