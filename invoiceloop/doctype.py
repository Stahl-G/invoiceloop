"""单据类别:受控词表 + 页面字面证据。

**为什么需要这个模块。** DWS 的 understand 响应一直带 `invoice_type`,这个
系统从来没用过它。实测(2026-08-07,SEALED-1 未人工 88 份 + SEALED-2 100 份):
四分之一左右的文档根本不是发票 —— 订单、报价、合同、确认单、收据、贷项通知、
形式发票。系统把它们每一份都当成一张有 10 个必填字段的发票在问人,而且在
贷项通知单上把 8460.95 CR 当成正数放行(2026-08-07 人工复核 HD-0007,
`ROUTING_FALSE_NEGATIVE`)—— 那是把该收的钱当成该付的钱。

**为什么类型声明必须带证据。** `invoice_type` 是**被监督的那个模型自己写的
自由文本**。一旦策略拿它当条件(「这类单据不用查这些字段」「这类单据要查
符号」),模型只要改一个字符串,就能关掉针对自己的监督。所以类型不是一个
标签,必须和这个项目里其他所有值一个待遇:**绑定到页面上一块具体区域,
带独立 OCR 的字面支撑**。找不到支撑 = 阻断,不是默认成 invoice(宪章四:
跑不了的检查不算通过)。

**为什么用 OCR 而不是读图模型。** 这道检查完全可以确定性地跑在冻结证据上:
零 API、零延迟、可离线重算、能进回归测试。一个能确定性跑的检查不该换成
一个要联网才能跑的。

**匹配规则是本模块自己的,不复用 `citation_holds`。** 后者是 `want in have`
的子串包含(见 CLAUDE.md 的搬运陷阱),拿不到几何。这里要的是**词序列匹配
并合并 bbox** —— 因为证据要能在页面上圈出来给人看,布尔值不够。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from .ocr import OcrUnavailable, iter_words


def digest() -> str:
    """词表 + 匹配规则的内容寻址 —— 进执行指纹(改检查 = 新 run 代)。"""
    payload = {
        "classes": {
            name: {"pattern": pat, "phrases": list(phrases)}
            for name, (pat, phrases) in CLASSES.items()
        },
        "engine": "doctype-v1",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def check_document(doc_id: str, raw_type: str | None) -> dict:
    """一份文档的类型证据检查(纯函数结果,供 gates.document_checks)。

    status:
      - pass:声明映入词表且 OCR 有字面证据
      - fail:声明映入词表但无字面证据(类型不可信)
      - no_claim / unmapped:无可用类型声明
      - ocr_unavailable:机检跑不了(宪章四 —— 由 finding 另记)
    """
    cls = classify(raw_type)
    base = {
        "gate_id": "doctype_evidence",
        "raw_type": None if raw_type is None else str(raw_type),
        "doc_class": cls if cls not in (NO_CLAIM, UNMAPPED) else None,
        "status": cls if cls in (NO_CLAIM, UNMAPPED) else None,
        "evidence": None,
    }
    if cls == NO_CLAIM:
        base["status"] = NO_CLAIM
        return base
    if cls == UNMAPPED:
        base["status"] = UNMAPPED
        return base
    try:
        hit = find_evidence(doc_id, cls)
    except OcrUnavailable:
        base["status"] = "ocr_unavailable"
        return base
    if hit is None:
        base["status"] = "fail"
        return base
    base["status"] = "pass"
    base["evidence"] = hit
    return base

#: 受控词表。键是类,值是 (自由文本判别正则, 页面必须出现的字面证据之一)。
#:
#: 判别正则吃的是模型写的 `invoice_type` 自由文本(实测 24 种拼法);
#: 证据短语吃的是词级 OCR。两者是**不同的东西**,不许合并:前者是模型的
#: 声明,后者是页面的事实,这道门比的就是它们对不对得上。
#:
#: 顺序有意义 —— 先匹配到的类胜出。`credit` 必须排在 `invoice` 前面,
#: 否则 "billing discrepancy/credit request" 会被 billing 抢走。
CLASSES: dict[str, tuple[str, tuple[str, ...]]] = {
    "credit_note": (
        r"credit|rebate|discrepancy|refund",
        ("credit memo", "credit note", "credit memorandum", "credit", "rebate"),
    ),
    "proforma": (
        r"pro\s*-?\s*forma",
        ("proforma", "pro forma"),
    ),
    # confirmation 必须排在 purchase_order 前 —— 否则 "Order Confirmation"
    # 会被 \border\b 抢走。
    "confirmation": (
        r"confirmation|confirm",
        ("confirmation", "confirm"),
    ),
    "purchase_order": (
        r"\border\b|worksheet|printout|traffic",
        ("purchase order", "order"),
    ),
    "estimate": (
        r"estimate|quote|quotation",
        ("estimate", "quotation", "quote"),
    ),
    "contract": (
        r"contract|agreement|broadcast",
        ("contract", "agreement"),
    ),
    "receipt": (
        r"receipt|\bcheck\b|donation",
        ("receipt", "received", "check"),
    ),
    "invoice": (
        r"invoice|voucher|sale|affidavit|billing",
        ("invoice", "bill"),
    ),
}

#: 分类失败的两种,语义不同,不许合并:
#: 模型没给类型 vs 给了但映不进词表 —— 前者是缺口,后者是词表该扩了。
NO_CLAIM = "no_claim"
UNMAPPED = "unmapped"

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    """统一切词。声明侧与页面侧**必须用同一个函数**(CLAUDE.md 搬运陷阱)。"""
    return _WORD.findall(text.lower())


def classify(raw: str | None) -> str:
    """模型写的自由文本 → 受控类。

    返回类名,或 `NO_CLAIM`(模型没给)/ `UNMAPPED`(给了但不认识)。
    映不进词表**不猜**、不回退成 invoice —— 那正是要送人工的信号。
    """
    s = (raw or "").strip().lower()
    if not s:
        return NO_CLAIM
    for name, (pattern, _) in CLASSES.items():
        if re.search(pattern, s):
            return name
    return UNMAPPED


def _merge(boxes: Iterable[tuple]) -> list[list[float]]:
    """若干词的相对 bbox → 外接矩形 [[x0,y0],[x1,y1]]。"""
    xs0, ys0, xs1, ys1 = [], [], [], []
    for b in boxes:
        (x0, y0), (x1, y1) = b[0], b[1]
        xs0.append(x0); ys0.append(y0); xs1.append(x1); ys1.append(y1)
    return [[min(xs0), min(ys0)], [max(xs1), max(ys1)]]


def find_evidence(doc_id: str, doc_class: str) -> dict | None:
    """在词级 OCR 里找该类的字面证据。命中返回带几何的支持关系,否则 None。

    返回 `{phrase, page, bbox, words}` —— bbox 是命中词的外接矩形(相对坐标),
    可直接进 `evidence_span_registry` 或喂 `crop_field` 裁图给人看。
    多个短语命中时取**最早出现**的那个:单据抬头通常在最前面。
    """
    spec = CLASSES.get(doc_class)
    if spec is None:
        return None
    phrases = [_tokens(p) for p in spec[1]]

    # 按页收集 (词, bbox),页内保持文档顺序
    pages: dict[int, list[tuple[str, tuple]]] = {}
    for page_idx, word, bbox in iter_words(doc_id):
        for tok in _tokens(word):
            pages.setdefault(page_idx, []).append((tok, bbox))

    for page_idx in sorted(pages):
        seq = pages[page_idx]
        toks = [t for t, _ in seq]
        for phrase in phrases:
            n = len(phrase)
            for i in range(len(toks) - n + 1):
                if toks[i:i + n] == phrase:
                    return {
                        "phrase": " ".join(phrase),
                        "page": page_idx,
                        "bbox": _merge(b for _, b in seq[i:i + n]),
                        "words": n,
                    }
    return None
