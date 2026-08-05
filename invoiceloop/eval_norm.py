"""评测参考规范化 —— 2026-08-05 自 fields.normalise 逐字冻结(v0.2 P0-5)。

与产品侧 fields.normalise 从此分家:

- 产品侧可以被 Improve 候选演化(schema/normalization 是可编辑面);
- **本文件是评测权威的一部分,改进层禁止编辑** —— 否则候选可以靠放宽
  「相等」的定义骗取指标提升(v0.2 公理三:evaluator 在循环之外);
- scripts/heldout_metrics.py 与 scripts/baseline_comparison.py 的偏差口径
  只用这里的函数;改本文件 = 作废全部既有评测数字,必须有书面记录。
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
