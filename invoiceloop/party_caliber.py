"""Deterministic party-name suggestions from independent OCR.

Caliber, not extraction: billed-name block vs street, station vs agency.
Suggestions never write the ledger. Ambiguous pages abstain.
"""

from __future__ import annotations

import re
from typing import Any

from .due_date import _lines, _words

CALIBER_VERSION = "broadcast-party-v2"

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
#: v2:``agency`` 进买方标签。广播单上代理与广告主常常并印,读法契约
#: (``agents/invoice_read.py``)把「有代理时买方 = 代理」写在 system prompt 里,
#: 而 v1 只认 ``Advertiser:`` —— 同一张单上两个建议源指向不同主体。
#: 两个标签都在 → 现有的 ``buyer_hits == 1`` 守卫自动弃权,这正是宪章五要的
#: 形状:口径争议保持显式、进人工裁决。**不做**「优先取代理」的方向判定 ——
#: ``docs/DOCTYPE_STAGE_D_2026-08-07.md`` 记着一条预注册方向规则在 80% 杀线上
#: 打了 51.6% 被 KILL,没有新的预注册测量之前不重走那条路。
#: 标签行必须**整行就是标签**(两侧都锚)。只锚右侧的话,任何以标签词结尾的
#: 公司名自己也算一个标签:`Agency:` 后跟 `Smith Media Agency`,名字那行也命中,
#: `_take_name_block` 在捕到名字前就 break、`buyer_hits` 变 2 —— 恰好对真实的
#: 代理名弃权。模块本来就只认「标签独占一行」(`Bill To: ACME` 从来不命中),
#: 左锚是把这条既有假设写实,不是新增收窄。
#: 左锚允许一个礼貌前缀:`PLEASE REMIT TO:` 是纸面上极常见的写法,而
#: `Smith Media Agency` 不是标签 —— 前缀是白名单,不是通配。
_QUALIFIER = r"(?:please\s+)?"
_BUYER_LABEL = re.compile(
    rf"^{_QUALIFIER}"
    r"(?:bill(?:ed)?\s+to|advertiser|agency|customer|client|sold\s+to)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)
_SELLER_LABEL = re.compile(
    rf"^{_QUALIFIER}(?:station|publication|remit\s+to|payee|from)\s*:?\s*$",
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
