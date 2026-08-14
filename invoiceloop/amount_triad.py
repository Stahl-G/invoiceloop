"""OCR Gross / Commission / Net Due triad. Suggestions only.

Commission is parsed so it is not stuffed into net or due. The human
signs ``amount_due``; gross/net stay on the matrix unless a QA probe
pulls them into the walk.
"""

from __future__ import annotations

import re
from typing import Any

from .due_date import _lines, _words

TRIAD_VERSION = "amount-triad-v1"

_MONEY = re.compile(
    r"\$?\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\$\d+(?:\.\d{2})?|\d+\.\d{2}"
)

_LABELS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("total_gross", re.compile(
        r"\bgross\s+billings\b|\btotal\s+gross\b|\bgross\s+amount\b|"
        r"\bgross\b(?!\s+due)",
        re.IGNORECASE)),
    ("amount_due", re.compile(
        r"\bnet\s+due\b|\bamount\s+due\b|\btotal\s+due\b|"
        r"\bbalance\s+due\b|\bamount\s+payable\b",
        re.IGNORECASE)),
    ("total_net", re.compile(
        r"\btotal\s+net\b|\bnet\s+amount\b(?!\s+due)",
        re.IGNORECASE)),
    ("_commission", re.compile(
        r"\bagency\s+commission\b|\bcommission\b",
        re.IGNORECASE)),
)


def _money_on(text: str) -> str | None:
    hits = _MONEY.findall(text)
    if not hits:
        return None
    return hits[-1]


def suggest_amount_triad(ocr: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map scored amount fields to an OCR-labelled money token."""
    texts = [str(line.get("text") or "").strip()
             for line in _lines(_words(ocr))]
    found: dict[str, list[str]] = {}
    for i, text in enumerate(texts):
        if not text:
            continue
        money = _money_on(text)
        if money is None and i + 1 < len(texts):
            money = _money_on(texts[i + 1])
        if money is None:
            continue
        for field, pattern in _LABELS:
            if pattern.search(text):
                found.setdefault(field, []).append(money)
    out: dict[str, dict[str, Any]] = {}
    for field in ("total_gross", "amount_due", "total_net"):
        values = found.get(field) or []
        unique = list(dict.fromkeys(values))
        if len(unique) == 1:
            out[field] = {
                "value": unique[0], "rule_id": f"ocr-label:{field}",
                "version": TRIAD_VERSION,
            }
    return out
