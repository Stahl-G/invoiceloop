"""Deterministic party-name suggestions from independent OCR.

Caliber, not extraction: billed-name block vs street, station vs agency.
Suggestions never write the ledger. Ambiguous pages abstain.
"""

from __future__ import annotations

import re
from typing import Any

from .due_date import _lines, _words

CALIBER_VERSION = "broadcast-party-v1"

_STREET = re.compile(
    r"\d+\s+.+\b(?:street|st\.?|avenue|ave\.?|blvd\.?|boulevard|"
    r"road|rd\.?|drive|dr\.?|lane|ln\.?|way|suite|ste\.?|"
    r"floor|fl\.?|p\.?\s*o\.?\s*box)\b",
    re.IGNORECASE,
)
_CITY_ZIP = re.compile(
    r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"
)
_ATTN = re.compile(
    r"\b(?:att(?:ention|n)?\.?|c/o|care\s+of)\b",
    re.IGNORECASE,
)
_BUYER_LABEL = re.compile(
    r"\b(?:bill(?:ed)?\s+to|advertiser|customer|client|sold\s+to)\s*:?\s*$",
    re.IGNORECASE,
)
_SELLER_LABEL = re.compile(
    r"\b(?:station|publication|remit\s+to|payee|from)\s*:?\s*$",
    re.IGNORECASE,
)
_AGENCY = re.compile(r"\b(?:agency|buying\s+time|media\s+services)\b",
                     re.IGNORECASE)


def _line_text(line: dict[str, Any]) -> str:
    return str(line.get("text") or "").strip()


def _is_address_line(text: str) -> bool:
    return bool(_STREET.search(text) or _CITY_ZIP.search(text))


def _take_name_block(lines: list[dict[str, Any]], start: int) -> str | None:
    """Lines after a party label until an address line. Keep Attn."""
    parts: list[str] = []
    for line in lines[start + 1:start + 8]:
        text = _line_text(line)
        if not text:
            if parts:
                break
            continue
        if _is_address_line(text):
            break
        if _BUYER_LABEL.search(text) or _SELLER_LABEL.search(text):
            break
        parts.append(text)
        if len(parts) >= 3:
            break
    if not parts:
        return None
    # Drop trailing agency-only lines for seller suggestions later.
    return " ".join(parts)


def suggest_party_names(ocr: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {field: {value, rule_id, abstain}} for buyer_name / seller_name."""
    lines = _lines(_words(ocr))
    buyer = seller = None
    buyer_hits = seller_hits = 0
    for i, line in enumerate(lines):
        text = _line_text(line)
        if _BUYER_LABEL.search(text):
            buyer_hits += 1
            block = _take_name_block(lines, i)
            if block:
                buyer = block
        if _SELLER_LABEL.search(text):
            seller_hits += 1
            block = _take_name_block(lines, i)
            if block and not _AGENCY.search(block):
                seller = block
    out: dict[str, dict[str, Any]] = {}
    if buyer_hits == 1 and buyer:
        out["buyer_name"] = {
            "value": buyer, "rule_id": "billed-block-keep-attn-strip-street",
            "version": CALIBER_VERSION,
        }
    if seller_hits == 1 and seller:
        out["seller_name"] = {
            "value": seller, "rule_id": "station-or-publication",
            "version": CALIBER_VERSION,
        }
    return out
