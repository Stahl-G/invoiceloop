"""The freeze transaction (ARCHITECTURE.md §5.2) — the system's critical defence.

A model may only write `field_drafts.json`: no IDs, no authority. Python checks
the binding, assigns a stable `FC-####`, and freezes the ledger. The round-six
misbinding incident (359 answers bound to the wrong invoices) was rejected on
the spot under this rule — 118 of 168 rows, 70% — instead of being excavated
from OCR after the fact.

The binding rule has to be **document-level**: the value must appear in this
invoice's independent OCR text. A span-level rule (requiring the value to fall
inside a bbox DWS registered) was measured to reject 26–28% of legitimate
answers — and the ones it rejected were exactly the rows where DWS returned no
value or boxed the wrong region and a vision reader found it elsewhere on the
page, which is the only place vision reading adds anything. §5.2 has the table.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .fields import FIELDS
from .ocr import OcrUnavailable, doc_tokens, normalise_tokens

__all__ = [
    "BINDING_THRESHOLD",
    "OcrUnavailable",
    "normalise_tokens",
    "token_coverage",
    "binds_to_document",
    "binds_to_span",
    "freeze_drafts",
    "FreezeResult",
]

BINDING_THRESHOLD = 0.8


def token_coverage(value: str, haystack_tokens: frozenset[str] | set[str]) -> float:
    """value 的 token 中有多少比例出现在 haystack 里。

    空值(没有任何 token)覆盖率定义为 0.0 —— 一个什么都说不出来的草稿
    无法证明它绑在任何文档上。
    """
    toks = set(normalise_tokens(value))
    if not toks:
        return 0.0
    return len(toks & haystack_tokens) / len(toks)


def binds_to_document(doc_id: str, value: str) -> bool:
    """值是否出现在该 doc 整份文档的独立 OCR 文本中(token 匹配 ≥80%)。

    该 doc 的 OCR 缺失时抛 `OcrUnavailable`(宪章四:阻断,不静默)。
    """
    return token_coverage(value, doc_tokens(doc_id)) >= BINDING_THRESHOLD


def binds_to_span(value: str, span_ocr_text: str) -> bool:
    """值是否落在某个已注册证据片段内 —— 决定 support_strength,不决定接纳。"""
    return token_coverage(value, set(normalise_tokens(span_ocr_text))) >= BINDING_THRESHOLD


@dataclass
class FreezeResult:
    """冻结事务的产出:账本 + 拒绝记录 + 事件。"""

    claims: list[dict] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def ledger(self) -> dict:
        """field_ledger.json 的内容,带内容寻址 sha256(§10 保留:内容寻址冻结)。"""
        body = {"claims": self.claims}
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return {**body, "sha256": digest}


def freeze_drafts(
    drafts: Iterable[Mapping],
    *,
    spans: Sequence[Mapping] = (),
) -> FreezeResult:
    """冻结事务主体。纯函数:文件 IO 不在这层,便于零 API 重算。

    drafts: 模型草稿行,只允许 {doc_id, field, value, drafted_by}。
    spans:  已注册证据片段(至少含 span_id 与 ocr_text),用于记录值落在哪。

    每一步拒绝都记事件,被拒绝的行不进账本(宪章四:缺口不能被隐藏)。
    OCR 缺失时 `OcrUnavailable` 直接向上抛 —— 冻结事务跑不了就是阻断。
    """
    result = FreezeResult()
    seq = 0
    for line_no, draft in enumerate(drafts):
        doc_id = draft.get("doc_id")
        field_name = draft.get("field")
        value = draft.get("value")
        drafted_by = draft.get("drafted_by", "unknown")

        # 第 2 步(a):草稿不得预写 claim_id —— ID 是 Python 的权威
        if draft.get("claim_id") is not None:
            result.rejections.append(
                {
                    "reason": "prewritten_claim_id",
                    "doc_id": doc_id,
                    "field": field_name,
                    "value": value,
                    "drafted_by": drafted_by,
                }
            )
            result.events.append(
                {
                    "event": "draft_prewritten_id_rejected",
                    "doc_id": doc_id,
                    "field": field_name,
                    "value": value,
                    "drafted_by": drafted_by,
                    "line_no": line_no,
                }
            )
            continue

        # 第 2 步(b):字段必须在评估集内 —— schema 能管的规则交给事务(宪章三)。
        # DWS 会返回评估集外的字段,甚至幻觉出 \x06 这样的字段名(实测
        # doc 026b4022);静默丢弃是藏缺口,进账本是污染,显式拒。
        if field_name not in FIELDS:
            result.rejections.append(
                {
                    "reason": "unknown_field",
                    "doc_id": doc_id,
                    "field": field_name,
                    "value": value,
                    "drafted_by": drafted_by,
                }
            )
            result.events.append(
                {
                    "event": "draft_unknown_field_rejected",
                    "doc_id": doc_id,
                    "field": field_name,
                    "drafted_by": drafted_by,
                    "line_no": line_no,
                }
            )
            continue

        # 第 2 步(c):空草稿无可绑定 —— 它不是"绑上了",显式拒
        if value is None or not normalise_tokens(str(value)):
            result.rejections.append(
                {
                    "reason": "empty_value",
                    "doc_id": doc_id,
                    "field": field_name,
                    "value": value,
                    "drafted_by": drafted_by,
                }
            )
            result.events.append(
                {
                    "event": "draft_empty_value_rejected",
                    "doc_id": doc_id,
                    "field": field_name,
                    "drafted_by": drafted_by,
                    "line_no": line_no,
                }
            )
            continue

        # 第 2 步(b):文档级绑定 —— 值必须出现在这份发票的独立 OCR 里
        coverage = token_coverage(str(value), doc_tokens(str(doc_id)))
        if coverage < BINDING_THRESHOLD:
            result.rejections.append(
                {
                    "reason": "binding",
                    "doc_id": doc_id,
                    "field": field_name,
                    "value": value,
                    "drafted_by": drafted_by,
                    "coverage": round(coverage, 4),
                }
            )
            result.events.append(
                {
                    "event": "draft_binding_rejected",
                    "doc_id": doc_id,
                    "field": field_name,
                    "value": value,
                    "drafted_by": drafted_by,
                    "coverage": round(coverage, 4),
                    "line_no": line_no,
                }
            )
            continue

        # 第 3 步:分配稳定 ID;随后记录值落在哪个已注册片段内(决定强度,不决定接纳)
        # 片段匹配必须限在本 doc —— 别的发票的片段里有同样的字,不等于这个值有出处
        seq += 1
        claim_id = f"FC-{seq:04d}"
        containing = [
            span["span_id"]
            for span in spans
            if span.get("doc_id") == doc_id
            and binds_to_span(str(value), str(span.get("ocr_text", "")))
        ]
        result.claims.append(
            {
                "claim_id": claim_id,
                "doc_id": doc_id,
                "field": field_name,
                "value": value,
                "span_ids": containing,
                "drafted_by": drafted_by,
                "binding_coverage": round(coverage, 4),
            }
        )
        result.events.append(
            {
                "event": "claim_frozen",
                "claim_id": claim_id,
                "doc_id": doc_id,
                "field": field_name,
                "line_no": line_no,
            }
        )
    return result
