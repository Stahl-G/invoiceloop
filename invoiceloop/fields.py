"""The scored field set and its tiers.

TIER1 is the fields whose consequences are financial or regulatory: totals,
amount due, invoice number, VAT id, the parties. TIER2 is the rest. The split
matters at the exit — a TIER1 slot is not released on corroboration alone.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class Kind(str, Enum):
    AMOUNT = "amount"
    DATE = "date"
    PARTY = "party"
    CODE = "code"
    TEXT = "text"


#: 字段名 -> Kind。十个记分字段(TIER1 ∪ TIER2),kind 与 dws-derisk schema.py 一致。
FIELD_KINDS: dict[str, Kind] = {
    "invoice_number": Kind.CODE,
    "total_gross": Kind.AMOUNT,
    "total_net": Kind.AMOUNT,
    "total_vat": Kind.AMOUNT,
    "amount_due": Kind.AMOUNT,
    "seller_vat_id": Kind.CODE,
    "seller_name": Kind.PARTY,
    "buyer_name": Kind.PARTY,
    "issue_date": Kind.DATE,
    "due_date": Kind.DATE,
}

#: dws-derisk routers.py 的分层:T1 错了是要命的,T2 错了要人工看。
TIER1 = frozenset(
    {"invoice_number", "total_gross", "total_net", "total_vat", "amount_due", "seller_vat_id"}
)
TIER2 = frozenset({"seller_name", "buyer_name", "issue_date", "due_date"})

FIELDS: tuple[str, ...] = tuple(FIELD_KINDS)

#: 金额四字段 —— C1/C2 算术恒等式与 applicability 判据的作用域(ARCHITECTURE.md §4)。
AMOUNT_FIELDS = ("total_net", "total_vat", "total_gross", "amount_due")


_LEGAL_SUFFIX = re.compile(
    r"\b(inc|ltd|limited|llc|l\.l\.c|gmbh|corp|corporation|co|company|sa|s\.a"
    r"|bv|b\.v|nv|n\.v|plc|ag|kg|oy|ab|as|aps|srl|spa|pty)\b\.?",
    re.IGNORECASE,
)


def normalise(value: Any, kind: Kind) -> str | None:
    """预注册比较规则(THRESHOLDS.md §5),逐字搬自 dws-derisk score.py。"""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if kind is Kind.AMOUNT:
        # 取最长数字串:抽取常带货币符号或尾部代码。撇号是瑞士/列支敦士登
        # 千分位,必须留在串内参与"最长"裁决,剥除放在十进制判定之前。
        candidates = re.findall(r"[\d][\d.,'’\s]*", text)
        if not candidates:
            return None
        raw = max(candidates, key=len).strip().replace(" ", "")
        raw = raw.replace("'", "").replace("’", "")
        # 1.234,56(欧式)vs 1,234.56(盎格鲁):最后出现的分隔符是小数点,
        # 按位置判定,不按地区假设 —— 猜错会把匹配变成 100 倍错误。
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
        # 有歧义的两位顺序不在这里解;按有序数字元组比较,比解析成日期更严,
        # 也永远不会把 03/04 静默重解释成四月。
        return "-".join(digits) if digits else None

    if kind is Kind.PARTY:
        stripped = _LEGAL_SUFFIX.sub("", text)
        folded = re.sub(r"[^a-z0-9]", "", stripped.lower())
        # 截断:抽取常把地址 appended 到名字后;比较前导串,不把那算成名字错误。
        return folded[:40] or None

    if kind is Kind.CODE:
        return re.sub(r"[^a-z0-9]", "", text.lower()) or None

    return re.sub(r"\s+", " ", text.lower()).strip(" .,:;") or None


def amount(text: Any) -> float | None:
    """AMOUNT 规范化后转 float;不可解析为 None。"""
    normalised = normalise(text, Kind.AMOUNT)
    return float(normalised) if normalised is not None else None


def date_parts(text: Any) -> tuple[int, ...] | None:
    """日期的数字元组,仅当它像样(C5)。搬自 routers.py::_date_parts。"""

    if text is None:
        return None
    digits = [int(d) for d in re.findall(r"\d+", str(text))]
    if not (2 <= len(digits) <= 3):
        return None
    if any(d > 9999 for d in digits):
        return None
    # 日期总得有个像日/月的数。
    if not any(1 <= d <= 31 for d in digits):
        return None
    return tuple(digits)


def date_ymd(parts: tuple[int, ...], prefer: str | None = None) -> tuple[int, ...]:
    """数字元组 → 可时序比较的 (year, month, day)。

    routers.py 的「反序比较」只对 day-first 成立:ISO (2026,1,15) 反序成
    (15,1,2026),按日先比,01/15 → 02/14 误报;美式 (1,15,2026) 反序成
    (2026,15,1),真反序 02/14 → 01/15 漏报(82 评 P1-2 双向实测)。
    这里显式判定格式:

    - 首元素 > 31:ISO year-first
    - 首元素 > 12:day-first(日不可能 ≤ 12 之外的值)
    - 次元素 > 12:month-first(美式)
    - 日/月均 ≤ 12:格式歧义,靠 prefer(文档级约定,由同文档另一个
      无歧义日期给出);都给不出时回退 day-first —— 预注册行为,
      校准数字不因本次修复漂移
    """
    if len(parts) == 2:
        a, b = parts
        return (a, b) if a > 31 else (b, a)  # (year, month)
    a, b, c = parts
    if a > 31:
        return (a, b, c)
    if a > 12:
        return (c, b, a)
    if b > 12:
        return (c, a, b)
    if prefer == "month":
        return (c, a, b)
    return (c, b, a)


def date_order_prefer(*parts_list: tuple[int, ...] | None) -> str | None:
    """同文档日期的格式约定:任一无歧义的年未日期定调(day-first / month-first)。"""
    for parts in parts_list:
        if parts and len(parts) == 3 and parts[0] <= 31:
            if parts[0] > 12:
                return "day"
            if parts[1] > 12:
                return "month"
    return None

