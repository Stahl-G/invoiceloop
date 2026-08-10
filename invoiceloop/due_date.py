"""Deterministic due-date derivation from page evidence.

The raw ``due_date`` extraction field is intentionally narrow: it represents
an explicitly printed calendar date.  This module owns the separate business
rule output ``calculated_due_date`` for documents that print a relative term,
such as ``Net 30``.

The derivation never uses the DWS ``due_date`` value as an input.  It reads
independent OCR, requires an explicitly labelled base date, and records the
OCR word locations used by the calculation.  If the page says "30 days after
receipt" but does not print a receipt date, the result is not computable; the
module does not substitute the invoice date.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


CALCULATED_FIELD = "calculated_due_date"
DERIVATION_VERSION = "due-date-relative-term-v1"

_DATE_RE = re.compile(
    r"(?<!\d)(?:"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\.\d{1,2}\.\d{2,4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"\d{1,2}(?:,)?\s+\d{2,4}|"
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{2,4}"
    r")(?!\d)",
    re.IGNORECASE,
)

_MONTH_FORMATS = (
    "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
    "%d %B %Y", "%d %b %Y", "%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y",
    "%m/%d/%y", "%m-%d-%y", "%m.%d.%y",
)

_ISSUE_LABEL = re.compile(
    r"\b(?:invoice\s+date|issue\s+date|date\s+issued|date\s+of\s+invoice)\b",
    re.IGNORECASE,
)
_RECEIPT_LABEL = re.compile(
    r"\b(?:receipt\s+date|date\s+received|received\s+date|date\s+of\s+receipt)\b",
    re.IGNORECASE,
)
_TERM_PATTERNS = (
    (
        "issue_date",
        re.compile(
            r"\bnet\s+(?P<days>\d{1,3})\b|"
            r"\b(?P<days_after>\d{1,3})\s+days?\s+"
            r"(?:after|from)\s+(?:the\s+)?(?:invoice\s+date|"
            r"date\s+of\s+(?:the\s+)?invoice|issue\s+date|date\s+issued)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "receipt_date",
        re.compile(
            r"\b(?P<days>\d{1,3})\s+days?\s+"
            r"(?:after|from)\s+(?:the\s+)?(?:receipt|date\s+of\s+receipt)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "receipt_date",
        re.compile(r"\bdue\s+(?:on|upon)\s+receipt\b", re.IGNORECASE),
    ),
)


def _words(ocr: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten DocILE OCR while retaining stable page/line/word references."""
    out: list[dict[str, Any]] = []
    for page in sorted(ocr.get("pages") or [], key=lambda p: p.get("page_idx", 0)):
        page_idx = int(page.get("page_idx", 0))
        for block_idx, block in enumerate(page.get("blocks") or []):
            for line_idx, line in enumerate(block.get("lines") or []):
                for word_idx, word in enumerate(line.get("words") or []):
                    value = str(word.get("value") or "").strip()
                    if not value:
                        continue
                    out.append({
                        "page_idx": page_idx,
                        "block_idx": block_idx,
                        "line_idx": line_idx,
                        "word_idx": word_idx,
                        "value": value,
                        "geometry": word.get("geometry"),
                    })
    return out


def _lines(words: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for word in words:
        key = (word["page_idx"], word["block_idx"], word["line_idx"])
        grouped.setdefault(key, []).append(word)
    result = []
    for key, line_words in sorted(grouped.items()):
        line_words = sorted(line_words, key=lambda w: w["word_idx"])
        result.append({"key": key, "text": " ".join(w["value"] for w in line_words),
                       "words": line_words})
    return result


def _parse_date(text: str) -> date | None:
    candidate = text.strip().replace("  ", " ")
    for fmt in _MONTH_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def _date_candidates(line: dict[str, Any], label: re.Pattern[str]) -> list[tuple[date, dict[str, Any]]]:
    text = line["text"]
    match = label.search(text)
    if not match:
        return []
    candidates: list[tuple[date, dict[str, Any]]] = []
    for date_match in _DATE_RE.finditer(text):
        parsed = _parse_date(date_match.group(0).replace(",", ""))
        if parsed is None:
            continue
        refs = [
            {key: word[key] for key in ("page_idx", "block_idx", "line_idx", "word_idx", "geometry")}
            for word in line["words"]
            if date_match.group(0).lower().replace(",", "") in word["value"].lower().replace(",", "")
        ]
        if not refs:
            refs = [
                {key: word[key] for key in ("page_idx", "block_idx", "line_idx", "word_idx", "geometry")}
                for word in line["words"]
            ]
        candidates.append((parsed, {"label": label.pattern, "text": date_match.group(0), "ocr_word_refs": refs}))
    return candidates


def _first_labelled_date(lines: list[dict[str, Any]], label: re.Pattern[str]) -> tuple[date, dict[str, Any]] | None:
    candidates = [item for line in lines for item in _date_candidates(line, label)]
    if not candidates:
        return None
    # More than one labelled date is ambiguous; do not choose by proximity.
    unique = {item[0] for item in candidates}
    if len(unique) != 1:
        return None
    return candidates[0]


def _term(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for line in lines:
        for base_field, pattern in _TERM_PATTERNS:
            match = pattern.search(line["text"])
            if not match:
                continue
            days_text = match.groupdict().get("days") or match.groupdict().get("days_after")
            matches.append({
                "base_field": base_field,
                "days": int(days_text) if days_text else 0,
                "term_text": match.group(0),
                "ocr_word_refs": [
                    {key: word[key] for key in ("page_idx", "block_idx", "line_idx", "word_idx", "geometry")}
                    for word in line["words"]
                ],
            })
    if not matches:
        return None
    signatures = {(m["base_field"], m["days"], m["term_text"].lower()) for m in matches}
    if len(signatures) != 1:
        return {"ambiguous": True, "matches": matches}
    return matches[0]


def _not_computable(reason: str, *, term: dict[str, Any] | None = None,
                    issue: tuple[date, dict[str, Any]] | None = None,
                    receipt: tuple[date, dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "field": CALCULATED_FIELD,
        "status": "not_computable",
        "value": None,
        "rule_id": DERIVATION_VERSION,
        "formula": None,
        "inputs": {
            "issue_date": issue[0].isoformat() if issue else None,
            "receipt_date": receipt[0].isoformat() if receipt else None,
            "term_text": term.get("term_text") if term and not term.get("ambiguous") else None,
        },
        "source_refs": {
            "issue_date": issue[1] if issue else None,
            "receipt_date": receipt[1] if receipt else None,
            "payment_term": term.get("ocr_word_refs") if term and not term.get("ambiguous") else None,
        },
        "limitations": [reason],
    }


def derive_due_date(ocr: dict[str, Any]) -> dict[str, Any]:
    """Derive a due date from explicit OCR evidence, or record why not.

    Supported formulas are calendar-day offsets from a labelled invoice/issue
    date or a labelled receipt date.  The function returns a JSON-safe dict
    and never raises for a semantic gap.
    """
    lines = _lines(_words(ocr))
    issue = _first_labelled_date(lines, _ISSUE_LABEL)
    receipt = _first_labelled_date(lines, _RECEIPT_LABEL)
    term = _term(lines)
    if term is None:
        return _not_computable("no explicit relative payment term found")
    if term.get("ambiguous"):
        return _not_computable("multiple incompatible relative payment terms found", term=term)
    base_field = term["base_field"]
    base = issue if base_field == "issue_date" else receipt
    if base is None:
        return _not_computable(
            f"payment term requires an explicitly labelled {base_field}; none found",
            term=term, issue=issue, receipt=receipt,
        )
    if base_field == "issue_date" and issue is None:
        return _not_computable("invoice/issue date is not explicitly labelled", term=term)
    days = term["days"]
    value = base[0] + timedelta(days=days)
    return {
        "field": CALCULATED_FIELD,
        "status": "computed",
        "value": value.isoformat(),
        "rule_id": DERIVATION_VERSION,
        "formula": f"{base_field} + {days} calendar days",
        "inputs": {
            "issue_date": issue[0].isoformat() if issue else None,
            "receipt_date": receipt[0].isoformat() if receipt else None,
            "term_text": term["term_text"],
            "base_field": base_field,
            "days": days,
        },
        "source_refs": {
            "issue_date": issue[1] if issue else None,
            "receipt_date": receipt[1] if receipt else None,
            "payment_term": term["ocr_word_refs"],
        },
        "limitations": [
            "derived from page evidence; not a raw DWS due_date claim",
            "calendar-day addition; holidays and business-day conventions are not applied",
        ],
    }


def derive_due_date_file(path: Path | str) -> dict[str, Any]:
    """Read one DocILE/workspace OCR JSON file and derive its due date."""
    import json

    return derive_due_date(json.loads(Path(path).read_text(encoding="utf-8")))


def unavailable_due_date(reason: str = "independent OCR unavailable") -> dict[str, Any]:
    """Create the explicit blocking-shaped result for missing OCR."""
    return _not_computable(reason)
