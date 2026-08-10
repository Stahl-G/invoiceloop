"""Per-document absence evidence: does the page print this field's label at all?

**Why this exists.** Class-conditional absence (`absent_expected_cohorts`) asks
"do documents of this class usually carry this field?" — a statistical bet over a
cohort. Measured 2026-08-09 on the 300-document development corpus
(`DOCTYPE_ABSENCE_DEV_2026-08-09.md` §2), that bet is only safe off the invoice
class: `AE-invoice-seller_vat_id` would save 184 slots and silently swallow **7**
real tax ids, and `AE-invoice-due_date` 130 for **10**. Sixteen non-invoice rules
were promoted at zero measured cost, and they leave **568 of the 722** remaining
missing-value slots untouched, because those 568 are invoices.

This module asks a different question, one about **this document** rather than its
cohort: *is the field's label printed anywhere on the page?* If a US invoice never
prints the word VAT, its missing `seller_vat_id` is not a cohort guess — the page
itself corroborates the absence. If the page does print it, DWS missed something
that is visibly there, and that slot belongs to a human whatever its class is.

That turns a statistical bet into an evidence claim, which is the only kind of
claim this system is allowed to make (charter rule six), and it is the reason the
mechanism may enter the invoice class where cohorts may not.

**The safety property that lets the lexicon be written on development data.**
Adding a token to a lexicon can only move a document from `absent_corroborated`
to `label_present` — never the other way. So a broader lexicon strictly *reduces*
auto-absence and can never create a silent error. The fitting pressure runs the
unsafe direction only when tokens are **removed**. Hence the discipline:

    Adding tokens after seeing results is free. Removing one is fitting.

`tests/test_absence_evidence.py::TestMonotoneSafety` pins that direction.
Engine v3's fuzzy matching is the same direction, by the same argument: allowing
one edit on a long token can only *add* matches, never remove one. The unsafe
direction for v3 would be narrowing (raising the distance budget's threshold or
shrinking it to zero after seeing a ledger) — that is removal, and it is fitting.

**Fails closed everywhere.** No OCR, zero words on the page, a field with no
lexicon, a stale lexicon revision — none of these is a corroboration (charter rule
four: a check that could not run is not a pass). A document whose OCR degraded to
zero words must not silently become "no label found, absent everywhere".

**The matching rule is this module's own.** `citation_holds` is `want in have`
substring containment (CLAUDE.md porting trap two) and would read `VATICAN` as a
VAT label. What is needed is token-sequence matching with merged boxes, so the
label a human is being asked about can be circled on the rendered page — the same
requirement `doctype.find_evidence` has, and the same reason it is not a boolean.
"""

from __future__ import annotations

import hashlib
import json
import re

from .fields import FIELDS
from .ocr import OcrUnavailable, iter_words

#: 探针裁决。命名刻意不用 pass/fail —— 这不是第七道门,而且
#: 「没找到标签」当 pass 讲极易读反。
CORROBORATED = "absent_corroborated"   # 页面上找不到该字段的标签 → 缺席有据
LABEL_PRESENT = "label_present"        # 标签印着而 DWS 没给值 → 漏抽,给人看
NO_LEXICON = "no_lexicon"              # 该字段没有可判别的标签 → 出界
OCR_UNAVAILABLE = "ocr_unavailable"    # 机检跑不了(宪章四)
NOT_MEASURED = "not_measured"          # 旧工件没有这一项 —— 只用于消费侧默认

#: 引擎版本。改匹配规则 → 改 digest → 旧工件的 corroborated 不再被采信。
#:
#: v2(2026-08-09,**看过 v1 台账之后**):`seller_vat_id` 补进美国税号
#: 标签的拼写形式。v1 只收了缩写(ein / fein / tin),而美国发票实际印的是
#: "Federal ID" / "Federal Employee ID";开发集上 v1 漏掉的 6 个税号,
#: 5 个紧跟在 `federal` 后面,第 6 个是 OCR 把 "USt-IdNr" 读成 "ush id nr"。
#: 这是**加词**,走的是单调安全的那一侧:只会少放行,不会造出静默错。
#: 但这一版是事后的 —— v1 的数字才是盲测,两个都要照登
#: (`ABSENCE_EVIDENCE_DEV_2026-08-09.md`)。
#:
#: v3(2026-08-10,**先于任何 v3 测量**):长度 ≥6 的词表 token 允许
#: 编辑距离 ≤1 的模糊匹配,每条短语最多一个模糊 token。动机是 OCR 的
#: 单字符误读 —— v2 台账里 `seller_vat_id` 仅剩的 1 个静默是 "Federal"
#: 被读成 "federai"(`5da5a0e2bded40ad8948d5eb`,照登在
#: `ABSENCE_EVIDENCE_DEV_2026-08-09.md`);当时拒绝了把错字收进词表
#: (那是逐份拟合),模糊匹配是对**这一类**故障的机制回答,不是对那一份的。
#: 方向与加词相同:模糊只会**多**匹配 → 只会少 corroborate → 永不造静默错。
#: 短 token(vat / tax / due / net)不模糊 —— 它们太短,一个编辑就撞上
#: 无关词,而漏报的成本(留给人)远低于误报。
ENGINE = "absence-evidence-v3"

#: **预注册词表(冻结于本文件首次提交,先于任何 saves/silent 测量)。**
#:
#: 只收**有独特标签**的字段。`buyer_name` / `seller_name` 页面上没有可靠标签;
#: `invoice_number` / `issue_date` / `total_gross` / `amount_due` 的标签词
#: (number / date / total / amount)几乎每张单据都印,探针永远说 label_present
#: —— 安全但无用。**明写出界,而不是假装能判。**
#:
#: 收词标准是一般应付账款/税务词汇,不是校准语料里的拼法 —— doctype 词表
#: 2026-08-07 那次去污(七个 DocILE 派生 token)是同一条纪律。
#: 拿不准就**收进来**:收进来只会少放行。
LABEL_LEXICON: dict[str, tuple[str, ...]] = {
    # 卖方税务登记号。VAT 制度国家印 VAT/USt/TVA/IVA/BTW…;
    # 美国印 EIN/TIN;其余是各国登记号缩写。
    "seller_vat_id": (
        "vat", "ust", "ustid", "umsatzsteuer", "steuernummer",
        "tva", "iva", "btw", "moms", "mva", "alv",
        "gst", "gstin", "abn", "acn",
        "tin", "ein", "fein", "taxpayer",
        # v2:美国发票印的是拼出来的标签,不是缩写。`federal` 一条就覆盖
        # "Federal ID" / "Federal Tax ID" / "Federal Employer ID",以及 OCR
        # 把 ID 读成 DD 的那种;`id nr` / `id no` 覆盖 USt-IdNr 一类。
        "federal", "employer", "identification", "id nr", "id no",
        "nip", "cif", "nif", "ico", "dic", "cvr", "kvk",
        "siret", "siren", "cnpj", "cuit", "rfc", "rut", "pan",
        "tax id", "tax no", "tax number", "tax registration",
        "fiscal code", "codice fiscale", "partita iva",
    ),
    # 税额行。`tax` 是这里的正牌标签词,不是噪声。
    "total_vat": (
        "vat", "tax", "taxes", "taxable",
        "mwst", "ust", "tva", "iva", "btw", "moms", "mva", "alv",
        "gst", "hst", "pst", "qst", "igst", "cgst", "sgst",
        "sales tax", "tax amount", "tax total",
    ),
    # 税前小计。
    "total_net": (
        "subtotal", "sub total", "net", "netto", "excl", "excluding",
        "net amount", "net total", "before tax", "taxable",
    ),
    # 到期日。裸 `due` 会被 "Amount Due" / "Balance Due" 命中,于是这条
    # 几乎永不放行 —— **这是刻意的**。窄化成只认 "due date" 会漏掉页面上
    # 写 "Due: 3/15" 的那种,而那正是会变成静默错的一侧。
    # 宁可省不到,不可吞掉;看过结果之后再窄化就是拟合。
    "due_date": (
        "due", "terms", "payable", "maturity", "expiry", "expires",
    ),
}

_WORD = re.compile(r"[a-z0-9]+")

#: 长度阈值:词表 token 达到这个长度才允许模糊匹配(见 ENGINE v3 注释)。
_FUZZY_MIN_LEN = 6


def _levenshtein_at_most_one(a: str, b: str) -> bool:
    """两个 token 的编辑距离 ≤1(替换、插入或删除一个字符)。"""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif not skipped:
            skipped = True
            j += 1
        else:
            return False
    return True


def _phrase_matches(window: list[str], phrase: tuple[str, ...]) -> bool:
    """逐 token 匹配:精确,或词表 token 长度 ≥6 时允许编辑距离 ≤1;
    每条短语最多用一个模糊 token(两个 OCR 错字叠加就不再采信)。"""
    if len(window) != len(phrase):
        return False
    fuzzy_used = False
    for page_tok, lex_tok in zip(window, phrase):
        if page_tok == lex_tok:
            continue
        if fuzzy_used or len(lex_tok) < _FUZZY_MIN_LEN:
            return False
        if not _levenshtein_at_most_one(lex_tok, page_tok):
            return False
        fuzzy_used = True
    return True


def tokens(text: str) -> list[str]:
    """统一切词。词表侧与页面侧**必须用同一个函数**(CLAUDE.md 搬运陷阱一)。"""
    return _WORD.findall(text.lower())


def digest(lexicon: dict[str, tuple[str, ...]] | None = None) -> str:
    """词表 + 引擎版本的内容寻址 —— 改检查 = 新一代,旧结论不许直接采信。"""
    payload = {
        "engine": ENGINE,
        "lexicon": {field: sorted(phrases)
                    for field, phrases in (lexicon or LABEL_LEXICON).items()},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _merge(boxes) -> list[list[float]]:
    """若干词的相对 bbox → 外接矩形 [[x0,y0],[x1,y1]]。"""
    xs0, ys0, xs1, ys1 = [], [], [], []
    for box in boxes:
        (x0, y0), (x1, y1) = box[0], box[1]
        xs0.append(x0); ys0.append(y0); xs1.append(x1); ys1.append(y1)
    return [[min(xs0), min(ys0)], [max(xs1), max(ys1)]]


def _find_label(pages: dict[int, list[tuple[str, tuple]]],
                phrases: tuple[str, ...]) -> dict | None:
    """页面上最早出现的标签;同一位置上取**最长**的那条短语。

    位置优先而非短语优先,是为了让结论与词表的书写顺序无关 —— 顺序敏感的
    匹配会让「加一条短语」悄悄改掉别处的证据几何,那会破坏单调性。
    """
    wanted = sorted((tuple(tokens(p)) for p in phrases), key=len, reverse=True)
    for page_idx in sorted(pages):
        seq = pages[page_idx]
        toks = [t for t, _ in seq]
        for i in range(len(toks)):
            for phrase in wanted:  # 长→短:同位置取最长命中
                n = len(phrase)
                if n and _phrase_matches(toks[i:i + n], phrase):
                    return {
                        "phrase": " ".join(phrase),
                        "page_text": " ".join(toks[i:i + n]),
                        "page": page_idx,
                        "bbox": _merge(b for _, b in seq[i:i + n]),
                        "words": n,
                    }
    return None


def probe_document(doc_id: str, *,
                   lexicon: dict[str, tuple[str, ...]] | None = None,
                   ) -> dict[str, dict]:
    """一份文档 → 每个字段的缺席证据裁决。**词级 OCR 只扫一遍。**

    返回 `{field: {gate_id, field, status, evidence, word_count,
    phrases_probed, lexicon_digest}}`,字段覆盖 FIELDS ∪ 词表键。
    """
    table = LABEL_LEXICON if lexicon is None else lexicon
    lex_digest = digest(lexicon)
    field_names = sorted(set(FIELDS) | set(table))

    def base(field: str, status: str, **extra) -> dict:
        return {"gate_id": "absence_evidence", "field": field,
                "status": status, "evidence": None, "word_count": 0,
                "phrases_probed": len(table.get(field, ())),
                "lexicon_digest": lex_digest, **extra}

    pages: dict[int, list[tuple[str, tuple]]] = {}
    try:
        for page_idx, word, bbox in iter_words(doc_id):
            for tok in tokens(word):
                pages.setdefault(page_idx, []).append((tok, bbox))
    except OcrUnavailable:
        return {f: base(f, OCR_UNAVAILABLE) for f in field_names}

    word_count = sum(len(seq) for seq in pages.values())
    out: dict[str, dict] = {}
    for field in field_names:
        phrases = table.get(field)
        if not phrases:
            out[field] = base(field, NO_LEXICON, word_count=word_count)
            continue
        hit = _find_label(pages, phrases)
        out[field] = base(
            field,
            CORROBORATED if hit is None else LABEL_PRESENT,
            evidence=hit,
            word_count=word_count,
        )
    return out


def trusted_absence(probe: object) -> bool:
    """Return True only for a complete corroboration under the current lexicon.

    Every consumer — routing, counterfactual evaluation, bundle verification,
    presentation — goes through this validator rather than reading ``status``
    directly, so an artifact written by an older lexicon revision, a degraded OCR
    pass, or a hand-edited file fails closed instead of being repaired on read.
    """
    if not isinstance(probe, dict) or probe.get("status") != CORROBORATED:
        return False
    if probe.get("evidence") is not None:
        return False  # 有证据就不是「没找到标签」
    if probe.get("field") not in LABEL_LEXICON:
        return False
    if probe.get("lexicon_digest") != digest():
        return False  # 换过词表 = 换过检查,旧结论重算才算数
    for key in ("word_count", "phrases_probed"):
        value = probe.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return False
    return True
