"""SEALED-2 同证据、仅换 HAR 重跑矩阵(零 API)。

⚠️ 已作废 —— 用 `scripts/sealed2_har_ablation_v2.py`。

本脚本冻结 `runs/sealed2/gate_report.json` 只重建 routing/matrix,但那份报告
是在 HAR-0004 下产出的:`gates.py:322` 在跑门禁时就把 cohort 字段的
`extraction_present` 改写成 `expected_absent` 并把 finding 降为非阻断
(129 槽:seller_vat_id 85 + total_vat 44)。`matrix.build_matrix` 逐字消费
门禁裁决、从不按本臂 policy 重推,所以非 HAR-0004 的臂全部继承了 HAR-0004
的改写,负载被系统性低估。

证伪:HAR-0001 的 `absent_expected_cohorts` 是 None,而 `routing.py:108`
只在 `expected_absent` 时才路由 auto_absent —— 它的 machine_absent 只能是 0,
本脚本报了 117。修正后 HAR-0001 是 561/1000 (56.1%),不是 444 (44.4%)。

用法(仅供复现该缺陷):
  INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/sealed2_har_ablation.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import dws, evidence, harness, matrix  # noqa: E402
from invoiceloop.deliver import write_deliverable  # noqa: E402
from invoiceloop.panel import render_panel  # noqa: E402
from invoiceloop.safety_metrics import score_routes, truth  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("INVOICELOOP_CORPUS", str(REPO / "runs" / "sealed2-workspace"))

_EVENT_REASON = {
    "draft_binding_rejected": "binding",
    "draft_unknown_field_rejected": "unknown_field",
    "draft_empty_value_rejected": "empty_value",
    "draft_prewritten_id_rejected": "prewritten_claim_id",
}


def _rejections_from_events(run_dir: Path) -> list[dict]:
    out: list[dict] = []
    for line in (run_dir / "event_log.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        reason = _EVENT_REASON.get(e["event"])
        if reason is None:
            continue
        out.append({
            "reason": reason,
            "doc_id": e["doc_id"],
            "field": e.get("field"),
            "value": e.get("value"),
            "drafted_by": e.get("drafted_by", "unknown"),
        })
    return out


def reroute_arm(src: Path, out: Path, *, policy: dict, harness_id: str) -> dict:
    ids = json.load(open(REPO / "docs" / "sealed2_doc_list.json"))["doc_ids"]
    ledger = json.loads((src / "field_ledger.json").read_text())
    gate = json.loads((src / "gate_report.json").read_text())
    spans_raw = json.loads((src / "evidence_span_registry.json").read_text())
    spans = spans_raw if isinstance(spans_raw, list) else spans_raw["spans"]
    rejections = _rejections_from_events(src)
    understand = {d: dws.load_response(d, "understand") for d in ids}
    digest = evidence.digest_registry(
        json.loads((src / "artifact_registry.json").read_text()))

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)

    support, routing = matrix.build_matrix(
        ids,
        understand=understand,
        claims=ledger["claims"],
        rejections=rejections,
        gate_report=gate,
        vision_answers={},
        blocked_docs=frozenset(),
        spans=spans,
        policy=policy,
        harness_id=harness_id,
    )
    (out / "support_matrix.json").write_text(
        json.dumps(support, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "routing_report.json").write_text(
        json.dumps(routing, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    render_panel(out, support=support, gate_report=gate, spans=spans,
                 ledger=ledger, artifact_digest=digest, out_of_calibration=False)
    write_deliverable(out)

    man = json.loads((out / "run_manifest.json").read_text())
    man["harness_id"] = harness_id
    man["ablation"] = {
        "kind": "matrix_only",
        "frozen_from": str(src),
        "ledger_sha256": ledger["sha256"],
        "note": "同冻结 ledger/gate,仅换 routing policy",
    }
    (out / "run_manifest.json").write_text(
        json.dumps(man, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return support["summary"]


def main() -> None:
    src = REPO / "runs" / "sealed2"
    h1 = harness._builtin_policy()
    h4 = json.load(open(REPO / "runs" / "sealed2-workspace"
                         / "harnesses" / "HAR-0004" / "routing_policy.json"))
    arms = (
        ("HAR-0001", h1, REPO / "runs" / "sealed2-har1"),
        ("HAR-0004", h4, REPO / "runs" / "sealed2-har4-rerun"),
    )
    print(f"frozen ledger sha256: {json.loads((src/'field_ledger.json').read_text())['sha256'][:16]}…")
    for hid, pol, out in arms:
        s = reroute_arm(src, out, policy=pol, harness_id=hid)
        print(f"\n{hid} → {out.name}")
        for k in ("human_queue", "machine_absent", "requires_adjudication",
                  "machine_decided"):
            print(f"  {k}: {s[k]}/{s['slots']}")


if __name__ == "__main__":
    main()
