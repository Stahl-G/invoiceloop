"""Workspace-level round status (HITL stop / freeze).

Not a snapshot component and not a harness field.  A terminated round is a
human decision recorded next to the workspace so the workbench can refuse
further ``/decide`` writes.  Absence of the file = the round is live.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

FILENAME = "round_status.json"


def load_round_status(workspace: Path) -> dict[str, Any] | None:
    path = Path(workspace) / FILENAME
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"round_status 不可读:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("round_status 顶层必须是 object")
    return value


def is_terminated(workspace: Path) -> bool:
    status = load_round_status(workspace)
    return bool(status) and status.get("status") == "terminated"


def write_round_status(
    workspace: Path,
    payload: Mapping[str, Any],
    *,
    overwrite_terminated: bool = False,
) -> str:
    """Write ``round_status.json``.

    Returns ``\"written\"`` or ``\"preserved_terminated\"``. A terminated
    round is a human freeze; setup reruns must not silently revive it.
    """
    path = Path(workspace) / FILENAME
    if not overwrite_terminated and is_terminated(workspace):
        return "preserved_terminated"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return "written"
