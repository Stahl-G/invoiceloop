"""H1–H6 留出集判定(docs/HELDOUT.md 预注册判据的可执行形态)。

用法:
    python3 scripts/heldout_metrics.py runs/heldout [runs/demo]

对照判据(2026-08-02 冻结,执行后不得修改):
    H1 分诊 lift > 1.5            H4 缺值率 10–45%
    H2 coverage@46% > 55%         H5 citation 可判子集失败率 < 15%
    H3 复核召回 > 55%             H6 understand 草稿拒绝率 5–35%
偏差定义与 tests/test_triage_concentration.py 同一口径:真值存在、
口径争议行剔除、无 understand 入账声明或规范化后不等 = 偏差。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop.eval_norm import eval_normalise as normalise
from invoiceloop.fields import FIELD_KINDS
from invoiceloop.safety_metrics import DOCILE_TO_FIELD, truth  # noqa: F401

BANDS = {
    "H1 lift": (1.5, None),
    "H2 coverage@46%": (0.55, None),
    "H3 复核召回": (0.55, None),
    "H4 缺值率": (0.10, 0.45),
    "H5 citation 失败率": (None, 0.15),
    "H6 冻结拒绝率": (0.05, 0.35),
}


def measure(run_dir: Path) -> dict[str, float]:
    run_dir = Path(run_dir)
    matrix = json.loads((run_dir / "support_matrix.json").read_text())
    gates = json.loads((run_dir / "gate_report.json").read_text())
    drafts = json.loads((run_dir / "field_drafts.json").read_text())
    events = [json.loads(x) for x in (run_dir / "event_log.jsonl").read_text().splitlines()]

    scored = []
    for row in matrix["rows"]:
        if row["applicability"] == "label_convention_disputed":
            continue
        t = truth(row["doc_id"]).get(row["field"])
        if t is None:
            continue
        kind = FIELD_KINDS[row["field"]]
        want = normalise(t, kind)
        got = normalise(row["value"], kind) if row["claim_id"] else None
        scored.append({**row, "deviation": not (got is not None and got == want)})

    half = len(scored) // 2
    rate_f = sum(r["deviation"] for r in scored[:half]) / max(len(scored[:half]), 1)
    rate_b = sum(r["deviation"] for r in scored[half:]) / max(len(scored[half:]), 1)
    total_dev = sum(r["deviation"] for r in scored)
    k46 = int(len(scored) * 0.46)
    cov46 = sum(r["deviation"] for r in scored[:k46]) / max(total_dev, 1)
    recall = sum(r["deviation"] for r in scored if r["requires_adjudication"]) / max(total_dev, 1)

    evals = [v for doc in gates["evaluations"].values() for v in doc.values()]
    h4 = sum(1 for v in evals if v.get("extraction_present") == "fail") / max(len(evals), 1)
    cite = [v.get("citation_holds") for v in evals if v.get("citation_holds") in ("pass", "fail")]
    h5 = sum(1 for v in cite if v == "fail") / max(len(cite), 1)
    u_drafts = sum(1 for d in drafts if d["drafted_by"] == "dws_understand")
    u_rej = sum(1 for e in events
                if e["event"].startswith("draft_") and e["event"].endswith("_rejected")
                and e.get("drafted_by") == "dws_understand")
    return {
        "H1 lift": rate_f / rate_b if rate_b else float("inf"),
        "H2 coverage@46%": cov46,
        "H3 复核召回": recall,
        "H4 缺值率": h4,
        "H5 citation 失败率": h5,
        "H6 冻结拒绝率": u_rej / max(u_drafts, 1),
        "_scored": len(scored), "_deviations": total_dev,
        "_front_rate": rate_f, "_back_rate": rate_b,
        "_cite_decidable": len(cite), "_u_drafts": u_drafts, "_u_rejected": u_rej,
    }


def main() -> None:
    heldout = measure(sys.argv[1])
    baseline = measure(sys.argv[2]) if len(sys.argv) > 2 else None
    print(f"{'量':<20}{'留出集':>10}{'校准':>10}  预注册区间      判定")
    for name, (lo, hi) in BANDS.items():
        v = heldout[name]
        ok = (lo is None or v >= lo) and (hi is None or v <= hi)
        base = f"{baseline[name]:>10.3f}" if baseline else f"{'—':>10}"
        band = f"> {lo}" if hi is None else f"< {hi}" if lo is None else f"{lo}–{hi}"
        print(f"{name:<20}{v:>10.3f}{base}  {band:<14}  {'PASS' if ok else 'FAIL'}")
    for key in ("_scored", "_deviations", "_front_rate", "_back_rate",
                "_cite_decidable", "_u_drafts", "_u_rejected"):
        print(f"  {key[1:]}: heldout={heldout[key]}"
              + (f"  calibration={baseline[key]}" if baseline else ""))


if __name__ == "__main__":
    main()
