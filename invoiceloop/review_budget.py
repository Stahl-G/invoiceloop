"""Working-time budget for a HITL run (narrow protocol).

Cap is counted the same way as HITL closeout: adjacent decided_at gaps,
rest intervals > 1h excluded. Absence of the budget file = no cap.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

REST_GAP_SECONDS = 3600
FILENAME = "review_budget.json"


def load_budget(workspace: Path) -> dict[str, Any] | None:
    path = Path(workspace) / FILENAME
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("review_budget 顶层必须是 object")
    return value


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def working_seconds(entries: list[dict]) -> float:
    ordered = sorted(
        (e for e in entries if e.get("decided_at")),
        key=lambda e: e["decided_at"],
    )
    total = 0.0
    prev = None
    for entry in ordered:
        ts = _parse(entry["decided_at"])
        if prev is not None:
            delta = (ts - prev).total_seconds()
            if 0 <= delta <= REST_GAP_SECONDS:
                total += delta
        prev = ts
    return total


def budget_state(workspace: Path, run_dir: Path) -> dict[str, Any] | None:
    """None if this workspace has no cap. Else elapsed/cap/exhausted."""
    budget = load_budget(workspace)
    if not budget:
        return None
    cap_minutes = float(budget.get("cap_minutes") or 0)
    if cap_minutes <= 0:
        return None
    ledger_path = Path(run_dir) / "adjudication_ledger.jsonl"
    entries: list[dict] = []
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    elapsed = working_seconds(entries)
    cap = cap_minutes * 60.0
    return {
        "cap_minutes": cap_minutes,
        "elapsed_seconds": elapsed,
        "remaining_seconds": max(0.0, cap - elapsed),
        "exhausted": elapsed >= cap and len(entries) > 0,
        "n_decisions": len(entries),
    }
