"""冻结事务(ARCHITECTURE.md §5.2)—— 系统的关键防线。

模型只能写 `field_drafts.json`(无 ID、无权威);Python 校验绑定、
分配稳定 `FC-####`、冻结账本。第六轮那次错位事故(359 行答案绑到别的发票)
在这条规则下当场被拒 118/168 行(70%),而不是事后靠 OCR 考古发现。

绑定规则必须是**文档级**的:值要出现在这份发票的独立 OCR 文本里。
片段级(要求值落在 DWS 注册的 bbox 内)实测误伤 26–28% 的合法作答 ——
被误伤的正是 DWS 没返回值或框错位置、而读图在页面别处找到的行,
那是读图唯一有增量价值的地方。§5.2 有那张对照表。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

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

        # 第 2 步(b):空草稿无可绑定 —— 它不是"绑上了",显式拒
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
