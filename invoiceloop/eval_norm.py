"""Evaluation-time normalisation — the pre-registered rules, frozen across six
rounds.

Ported from dws-derisk `score.py::normalise` and checked point by point against
the original in `test_port_fidelity`. Kind-dependent: the AMOUNT branch collapses
a value to a single number, the CODE branch strips the whole string. Neither
produces a token sequence — if tokens are what you need, split on `[a-z0-9]+`
yourself, and use the same function on both sides.
"""

from __future__ import annotations

import re
from typing import Any

from .fields import Kind

_LEGAL_SUFFIX = re.compile(
    r"\b(inc|ltd|limited|llc|l\.l\.c|gmbh|corp|corporation|co|company|sa|s\.a"
    r"|bv|b\.v|nv|n\.v|plc|ag|kg|oy|ab|as|aps|srl|spa|pty)\b\.?",
    re.IGNORECASE,
)


def eval_normalise(value: Any, kind: Kind) -> str | None:
    """预注册比较规则(THRESHOLDS.md §5)的评测冻结版,2026-08-05 自
    fields.normalise 逐字拷贝。改这里 = 作废既有评测数字。"""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if kind is Kind.AMOUNT:
        candidates = re.findall(r"[\d][\d.,'’\s]*", text)
        if not candidates:
            return None
        raw = max(candidates, key=len).strip().replace(" ", "")
        raw = raw.replace("'", "").replace("’", "")
        if "," in raw and "." in raw:
            raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            head, _, tail = raw.rpartition(",")
            raw = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else raw.replace(",", "")
        try:
            return f"{float(raw):.2f}"
        except ValueError:
            return None

    if kind is Kind.DATE:
        digits = re.findall(r"\d+", text)
        return "-".join(digits) if digits else None

    if kind is Kind.PARTY:
        stripped = _LEGAL_SUFFIX.sub("", text)
        folded = re.sub(r"[^a-z0-9]", "", stripped.lower())
        return folded[:40] or None

    if kind is Kind.CODE:
        return re.sub(r"[^a-z0-9]", "", text.lower()) or None

    return re.sub(r"\s+", " ", text.lower()).strip(" .,:;") or None
