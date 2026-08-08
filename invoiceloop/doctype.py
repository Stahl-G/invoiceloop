"""Document class: a controlled vocabulary plus literal page evidence.

**Why this module exists.** The DWS understand response has always carried
`invoice_type`, and this system never used it. Measured 2026-08-07 across the 88
never-reviewed SEALED-1 documents and the 100 SEALED-2 documents: roughly a
quarter are not invoices at all — purchase orders, quotes, contracts, order
confirmations, receipts, credit notes, pro forma invoices. The system was asking a
human about all ten mandatory invoice fields for every one of them, and on a
credit note it released 8460.95 CR as a positive number (human review HD-0007,
2026-08-07, `ROUTING_FALSE_NEGATIVE`) — treating money owed to you as money you owe.

**Why a type claim must carry evidence.** `invoice_type` is **free text written by
the very model under supervision**. The moment a policy conditions on it ("this
document class need not check these fields", "this class needs a sign check"), the
model can switch off its own supervision by changing one string. So a type is not
a label; it gets the same treatment as every other value here: **bound to a
specific region of the page, with literal support from an independent OCR**. No
support found means blocked, not defaulted to invoice (charter rule four: a check
that could not run is not a pass).

**Why OCR rather than a vision model.** This check runs deterministically on
frozen evidence: zero API, zero latency, recomputable offline, and testable in
regression. A check that can run deterministically should not be traded for one
that needs the network.

**The matching rule is this module's own; `citation_holds` is deliberately not
reused.** That one is `want in have` substring containment (see the porting traps
in CLAUDE.md) and yields no geometry. What is needed here is **token-sequence
matching with merged bounding boxes** — the evidence has to be circleable on the
page for a human, and a boolean is not enough.
"""

from __future__ import annotations

import hashlib
import json
import math
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
        # v2 = 2026-08-07 词表去污(删七个 DocILE 派生 token)。
        # 改版本 → 改 digest → 改执行指纹:去污前后的 run 不同代,不许混算。
        "engine": "doctype-v2",
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
#: 顺序有意义 —— 先匹配到的类胜出。`credit_note` 必须排在 `invoice` 前面
#: ("Credit Note against Invoice 12345" 两类都命中);`confirmation` 必须排在
#: `purchase_order` 前("Order Confirmation" 否则被 `\border\b` 抢走)。
#:
#: **判别 token 只许是一般应付账款词汇,不许是校准语料里的拼法。**
#: 2026-08-07 去污(doctype-v2)删掉七个 DocILE 派生 token ——
#: `discrepancy` / `worksheet` / `printout` / `traffic` / `broadcast` /
#: `affidavit` / `billing`。逐 token 消融实测:七个全是死票,一起删也
#: **零份改判**(S1 未人工 88 与 S2 100 皆 0),因为吃下它们的那些串本来
#: 就含 `credit` / `order` / `contract` / `invoice`。留着的唯一效果是让
#: `unmapped=0` 看起来是测出来的 —— 那是构造出来的。
#: 复算:`python3 scripts/doctype_vocab_ablation.py`
CLASSES: dict[str, tuple[str, tuple[str, ...]]] = {
    "credit_note": (
        r"credit|rebate|refund",
        ("credit memo", "credit note", "credit memorandum", "credit", "rebate"),
    ),
    "proforma": (
        r"pro\s*-?\s*forma",
        ("proforma", "pro forma"),
    ),
    "confirmation": (
        r"confirmation|confirm",
        ("confirmation", "confirm"),
    ),
    "purchase_order": (
        r"\border\b",
        ("purchase order", "order"),
    ),
    "estimate": (
        r"estimate|quote|quotation",
        ("estimate", "quotation", "quote"),
    ),
    "contract": (
        r"contract|agreement",
        ("contract", "agreement"),
    ),
    # `receipt` 留下:它是本类的本名,不是语料派生。去污记录一度把它列进
    # 待删名单 —— 实测删掉会让 S2 里字面写着 "Receipt" / "Transaction
    # Receipt" 的两份变 unmapped。`\bcheck\b` 与 `donation` 确实是 S1 派生
    # 且**载荷**(共 3 份),删不掉,只能照登(见 DOCTYPE_EVIDENCE §去污)。
    "receipt": (
        r"receipt|\bcheck\b|donation",
        ("receipt", "received", "check"),
    ),
    "invoice": (
        r"invoice|voucher|sale",
        ("invoice", "bill"),
    ),
}

#: 分类失败的两种,语义不同,不许合并:
#: 模型没给类型 vs 给了但映不进词表 —— 前者是缺口,后者是词表该扩了。
NO_CLAIM = "no_claim"
UNMAPPED = "unmapped"

_WORD = re.compile(r"[a-z0-9]+")


def trusted_class(check: object) -> str | None:
    """Return a controlled class only for a complete frozen literal hit.

    Consumers must not turn a bare model-authored ``doc_class`` into policy
    input.  This validator is the common trust boundary for routing,
    counterfactual evaluation, bundle verification and presentation: malformed
    old artifacts fail closed instead of being repaired on read.
    """
    if not isinstance(check, dict) or check.get("status") != "pass":
        return None
    doc_class = check.get("doc_class")
    if doc_class not in CLASSES:
        return None
    evidence = check.get("evidence")
    if not isinstance(evidence, dict):
        return None
    phrase = evidence.get("phrase")
    page = evidence.get("page")
    bbox = evidence.get("bbox")
    if not isinstance(phrase, str) or not phrase.strip():
        return None
    if isinstance(page, bool) or not isinstance(page, int) or page < 0:
        return None
    try:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 2:
            return None
        if any(not isinstance(point, (list, tuple)) or len(point) != 2
               for point in bbox):
            return None
        (x0, y0), (x1, y1) = bbox
        coords = tuple(float(v) for v in (x0, y0, x1, y1))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in coords):
        return None
    x0, y0, x1, y1 = coords
    if not (0.0 <= x0 <= x1 <= 1.0 and 0.0 <= y0 <= y1 <= 1.0):
        return None
    return doc_class


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
