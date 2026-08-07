"""SEALED-2 同证据换 HAR 消融 —— 修正版:门禁按各臂策略重算(零 API)。

v1(`sealed2_har_ablation.py`)的缺陷:它冻结 `runs/sealed2/gate_report.json`
只重建 routing/matrix。但那份门禁报告是**在 HAR-0004 下产出的** ——
`gates.py:322` 在跑门禁时就把 cohort 字段的 `extraction_present` 改写成
`expected_absent` 并把 finding 降为非阻断,总共 129 槽
(seller_vat_id 85 + total_vat 44)。`matrix.build_matrix` 逐字消费门禁裁决,
从不按本臂 policy 重新推导,所以 HAR-0001 臂继承了 HAR-0004 的改写。

一行证伪:HAR-0001 的 `absent_expected_cohorts` 是 None,而
`routing.py:108` 只在 `extraction_present == "expected_absent"` 时才路由
`auto_absent` —— HAR-0001 的 machine_absent 只能是 0,v1 报了 117。

修正:证据层(响应 / OCR / 冻结账本 / spans)保持冻结,门禁按各臂
`absent_expected` 重跑。正对照:用 HAR-0004 的缺席集重算,必须逐字节
复现冻结的 gate_report —— 对不上就说明还有别的输入没对齐,先停。

用法:python3 scripts/sealed2_har_ablation_v2.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("INVOICELOOP_CORPUS", str(REPO / "runs" / "sealed2-workspace"))

from invoiceloop import crossdoc, dws, gates, harness, matrix  # noqa: E402
from invoiceloop.ocr import OcrUnavailable, load_ocr  # noqa: E402
from invoiceloop.safety_metrics import score_routes, truth  # noqa: E402

SRC = REPO / "runs" / "sealed2"

_EVENT_REASON = {
    "draft_binding_rejected": "binding",
    "draft_unknown_field_rejected": "unknown_field",
    "draft_empty_value_rejected": "empty_value",
    "draft_prewritten_id_rejected": "prewritten_claim_id",
}


def _rejections(run_dir: Path) -> list[dict]:
    out: list[dict] = []
    for line in (run_dir / "event_log.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        reason = _EVENT_REASON.get(e["event"])
        if reason is not None:
            out.append({"reason": reason, "doc_id": e["doc_id"],
                        "field": e.get("field"), "value": e.get("value"),
                        "drafted_by": e.get("drafted_by", "unknown")})
    return out


def _absent_set(policy: dict) -> frozenset[str]:
    return frozenset(c["field"]
                     for c in (policy.get("absent_expected_cohorts") or [])
                     if c.get("field"))


def main() -> None:
    ids = json.load(open(REPO / "docs" / "sealed2_doc_list.json"))["doc_ids"]
    ledger = json.loads((SRC / "field_ledger.json").read_text())
    spans_raw = json.loads((SRC / "evidence_span_registry.json").read_text())
    spans = spans_raw if isinstance(spans_raw, list) else spans_raw["spans"]
    frozen_gate = json.loads((SRC / "gate_report.json").read_text())
    rejections = _rejections(SRC)

    understand = {d: dws.load_response(d, "understand") for d in ids}
    agentic = {d: dws.load_response(d, "agentic") for d in ids}

    ocr_blocked = set()
    for d in ids:
        try:
            load_ocr(d)
        except OcrUnavailable:
            ocr_blocked.add(d)

    dup_groups = crossdoc.duplicate_groups(ledger["claims"])
    artifact_digest = frozen_gate["input_signature"]["artifact_digest"]

    def gate_for(absent: frozenset[str]) -> dict:
        return gates.run_gates(
            ids, understand=understand, agentic=agentic, vision_answers={},
            ledger_sha256=ledger["sha256"], artifact_digest=artifact_digest,
            ocr_blocked=frozenset(ocr_blocked), duplicate_groups=dup_groups,
            absent_expected=absent, agentic_optional=frozenset())

    h1 = harness._builtin_policy()
    h4 = json.load(open(REPO / "runs" / "sealed2-workspace" / "harnesses"
                        / "HAR-0004" / "routing_policy.json"))

    # ---- 正对照:HAR-0004 的缺席集必须复现冻结报告
    ctl = gate_for(_absent_set(h4))
    same = (json.dumps(ctl, sort_keys=True, ensure_ascii=False)
            == json.dumps(frozen_gate, sort_keys=True, ensure_ascii=False))
    print(f"正对照(HAR-0004 缺席集重算 == 冻结 gate_report):"
          f"{'✅ 逐字节一致' if same else '❌ 不一致'}")
    if not same:
        for k in ("evaluations", "findings", "input_signature"):
            a = json.dumps(ctl[k], sort_keys=True, ensure_ascii=False)
            b = json.dumps(frozen_gate[k], sort_keys=True, ensure_ascii=False)
            print(f"   {k}: {'同' if a == b else '异'}")
        print("   输入未对齐,后续臂不可信 —— 停。")
        return

    print(f"\n{'臂':<10} {'human_queue':>14} {'machine_absent':>15} "
          f"{'静默缺席错':>12} {'静默错值':>12} {'文档触达':>9}")
    print("-" * 82)
    for hid, pol in (("HAR-0001", h1), ("HAR-0004", h4)):
        gate = gate_for(_absent_set(pol))
        support, routing = matrix.build_matrix(
            ids, understand=understand, claims=ledger["claims"],
            rejections=rejections, gate_report=gate, vision_answers={},
            blocked_docs=frozenset(ocr_blocked), spans=spans,
            policy=pol, harness_id=hid)
        s = support["summary"]
        cnt = score_routes(routing["routes"], truth_of=truth,
                           understand_of=lambda d: (understand[d].data
                                                    if understand[d] else None))
        touched = len({r["doc_id"] for r in routing["routes"]
                       if r["route"] not in ("auto_accept", "auto_absent")})
        n = s["slots"]
        print(f"{hid:<10} {s['human_queue']:>7}/{n} ({s['human_queue']/n:>5.1%})"
              f" {s['machine_absent']:>15}"
              f" {cnt['silent_absent']:>6}/{cnt['absent_hits']:<5}"
              f" {cnt['silent_wrong']:>6}/{cnt['value_hits']:<5}"
              f" {touched:>6}/{len(ids)}")


if __name__ == "__main__":
    main()
