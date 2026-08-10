#!/usr/bin/env python3
"""Close one HITL round: per-slot human time + suggestion adoption
(docs/HITL_R1R2_PROTOCOL_2026-08-10.md §3).

Reads only the run's adjudication ledger and frozen field ledger.  No API,
no recompute of gates.  All numbers are development-set measurements and
must be reported with that qualifier.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from invoiceloop.fields import FIELD_KINDS, normalise

#: 协议 §3:间隔 > 1h 视为休息,剔除(run-0002 隔夜污染先例,只报中位)
REST_GAP_SECONDS = 3600


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def per_slot_seconds(entries: list[dict]) -> dict:
    """相邻 decided_at 差 → 当前条目的耗时;首条与超休息阈值的剔除。"""
    ordered = sorted(entries, key=lambda e: e["decided_at"])
    durations: list[tuple[dict, float]] = []
    prev = None
    for entry in ordered:
        ts = _parse(entry["decided_at"])
        if prev is not None:
            delta = (ts - prev).total_seconds()
            if 0 <= delta <= REST_GAP_SECONDS:
                durations.append((entry, delta))
        prev = ts

    def _median(rows: list[float]) -> float | None:
        return round(statistics.median(rows), 1) if rows else None

    by_decision: dict[str, dict] = {}
    for entry, delta in durations:
        by_decision.setdefault(entry["decision"], []).append(delta)
    return {
        "n_timed": len(durations),
        "median_seconds": _median([d for _, d in durations]),
        "by_decision": {
            d: {"n": len(v), "median_seconds": _median(v)}
            for d, v in sorted(by_decision.items())},
        "excluded_gaps": len(ordered) - 1 - len(durations),
    }


def suggestion_adoption(entries: list[dict], claims: dict[str, dict]) -> dict:
    """协议 §3:分母 = suggestion_seen 为 agree:<值>;分子 = accept 且声明值
    与建议规范化一致,或 correct 且修正值与建议规范化一致。"""
    denom = numer = 0
    by_state: dict[str, int] = {}
    misses: list[dict] = []
    for entry in entries:
        seen = entry.get("suggestion_seen")
        if not seen:
            continue
        state = seen.split(":", 1)[0]
        by_state[state] = by_state.get(state, 0) + 1
        if state != "agree":
            continue
        denom += 1
        suggested = seen.split(":", 1)[1]
        kind = FIELD_KINDS.get(entry["field"])
        final = None
        if entry["decision"] == "accept" and entry.get("claim_id"):
            claim = claims.get(entry["claim_id"]) or {}
            final = claim.get("value")
        elif entry["decision"] == "correct":
            final = entry.get("corrected_value")
        if final is not None and \
                normalise(str(final), kind) == normalise(suggested, kind):
            numer += 1
        else:
            misses.append({"doc_id": entry["doc_id"], "field": entry["field"],
                           "suggested": suggested, "decision": entry["decision"],
                           "final": final})
    return {
        "agree_slots": denom,
        "adopted": numer,
        "adoption_rate": round(numer / denom, 4) if denom else None,
        "by_state": by_state,
        "misses": misses[:20],
    }


def analyze(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    ledger_path = run_dir / "adjudication_ledger.jsonl"
    entries = [json.loads(x) for x in
               ledger_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    claims = {c["claim_id"]: c for c in json.loads(
        (run_dir / "field_ledger.json").read_text())["claims"]}
    import hashlib

    return {
        "run": str(run_dir),
        "ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "n_decisions": len(entries),
        "timing": per_slot_seconds(entries),
        "suggestions": suggestion_adoption(entries, claims),
        "qualifier": "开发集测量,不带资格语义;人时含学习效应混淆(协议 §4)",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(analyze(args.run), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
