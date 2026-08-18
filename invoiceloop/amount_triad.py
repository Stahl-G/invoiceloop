"""OCR Gross / Commission / Net Due triad. Suggestions only.

Commission is parsed so it is not stuffed into net or due. The human
signs ``amount_due``; gross/net stay on the matrix unless a QA probe
pulls them into the walk.
"""

from __future__ import annotations

import re
from typing import Any

from .due_date import _lines, _words

TRIAD_VERSION = "amount-triad-v2"

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


def _label_spans(text: str) -> list[tuple[int, int, str]]:
    """Non-overlapping label spans; longer match wins at the same start."""
    raw: list[tuple[int, int, str]] = []
    for field, pattern in _LABELS:
        for match in pattern.finditer(text):
            raw.append((match.start(), match.end(), field))
    raw.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    spans: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, field in raw:
        if any(start < other_end and end > other_start
               for other_start, other_end in occupied):
            continue
        spans.append((start, end, field))
        occupied.append((start, end))
    spans.sort()
    return spans


def _bind_line(text: str) -> dict[str, list[str]]:
    """Each label takes the first money token after it and before the next label."""
    spans = _label_spans(text)
    money = [(match.start(), match.group(0)) for match in _MONEY.finditer(text)]
    found: dict[str, list[str]] = {}
    for i, (_, end, field) in enumerate(spans):
        limit = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        token = next((tok for start, tok in money if end <= start < limit), None)
        if token is not None:
            found.setdefault(field, []).append(token)
    return found


def suggest_amount_triad(ocr: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map scored amount fields to an OCR-labelled money token."""
    texts = [str(line.get("text") or "").strip()
             for line in _lines(_words(ocr))]
    found: dict[str, list[str]] = {}
    for i, text in enumerate(texts):
        if not text:
            continue
        bound = _bind_line(text)
        for field, values in bound.items():
            found.setdefault(field, []).extend(values)
        spans = _label_spans(text)
        # A single labelled row with no amount may continue onto the next
        # line only when that line has money and no label of its own.
        if (len(spans) == 1 and spans[0][2] not in bound
                and i + 1 < len(texts)):
            nxt = texts[i + 1]
            nxt_money = _money_on(nxt)
            if nxt_money and not _label_spans(nxt):
                found.setdefault(spans[0][2], []).append(nxt_money)
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
