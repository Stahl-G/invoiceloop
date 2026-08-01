"""评估字段集与预注册规范化规则。

字段集与分层搬自 dws-derisk `routers.py`(TIER1/TIER2);规范化规则逐字搬自
dws-derisk `score.py::normalise` —— 那是 THRESHOLDS.md §5 预注册、六轮冻结的
比较规则。值是否"正确"只相对于比较规则有意义,所以规则与字段定义住在一起,
改它就是改结果,不许静默改。

注意(CLAUDE.md 搬运陷阱之一):`normalise` 是 kind-dependent 的,
AMOUNT 分支把值塌成单值、CODE 分支整串剥 —— 它产不出 token 序列。
绑定用的 token 化在 `ocr.normalise_tokens`,两者不要混用。
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
