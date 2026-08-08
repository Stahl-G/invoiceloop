"""doctype 词表 + 页面字面证据(阶段 A:纯函数,不碰流水线)。"""

from __future__ import annotations

import pytest

from invoiceloop import doctype


class TestClassify:
    def test_no_claim_empty(self):
        assert doctype.classify(None) == doctype.NO_CLAIM
        assert doctype.classify("") == doctype.NO_CLAIM
        assert doctype.classify("   ") == doctype.NO_CLAIM

    def test_unmapped_unknown_string(self):
        assert doctype.classify("makegood form") == doctype.UNMAPPED
        assert doctype.classify("xyzzy document") == doctype.UNMAPPED

    def test_traffic_order_maps_to_purchase_order(self):
        """页面实为 traffic order 时,若模型如实写了,映进 purchase_order。
        (SEALED-2 阻断集里模型常谎报 invoice —— 那是证据门要抓的。)

        走的是通用 `\\border\\b`,**不是** `traffic` —— 去污后该 token 已删,
        这条仍成立,说明它当初就是死票。"""
        assert doctype.classify("new traffic order form") == "purchase_order"

    def test_credit_before_invoice(self):
        """两个类都命中时,`credit_note` 必须先于 `invoice`(匹配顺序)。

        去污前这条用的例子是 'billing discrepancy/credit request',靠的是
        `billing` 在 invoice 侧 —— 那两个 token 都是 S2 派生且已删,例子
        就不再检验顺序了。换成一个**天然同时含两类词**的串。"""
        assert doctype.classify("Credit Note against Invoice 12345") == "credit_note"
        assert doctype.classify("Credit Memorandum") == "credit_note"
        assert doctype.classify("credit memo") == "credit_note"

    def test_bare_billing_is_unmapped_not_guessed_as_invoice(self):
        """裸 'billing' 不是单据类型名 —— 转人工,不猜成 invoice。

        `billing` 当初只因为 S2 里有 'official billing invoice' 才进词表,
        而那个串本来就靠 `invoice` 命中(实测:删 `billing` 零份改判)。
        留着它的唯一效果,是把一个说不清是什么的声明**猜**成发票。"""
        assert doctype.classify("billing") == doctype.UNMAPPED
        assert doctype.classify("official billing invoice") == "invoice"
        assert doctype.classify("Invoice") == "invoice"

    def test_no_docile_jargon_left_in_the_vocabulary(self):
        """七个 DocILE 语料派生 token 不许回来(实测均为死票,删了零改判)。

        它们只在校准语料的自由文本里出现过,不属于任何一般应付账款词表。
        留着会让 `unmapped=0` 看起来是测出来的,其实是构造出来的。"""
        patterns = " ".join(pat for pat, _ in doctype.CLASSES.values())
        for token in ("discrepancy", "worksheet", "printout", "traffic",
                      "broadcast", "affidavit", "billing"):
            assert token not in patterns, f"{token} 又回到词表里了"

    def test_receipt_keeps_its_own_name(self):
        """`receipt` 留下 —— 它是该类的本名,不是语料派生。

        去污记录一度把它列进待删的五个 token。实测:删掉它,SEALED-2 里
        字面写着 'Receipt' / 'Transaction Receipt' 的两份变成 unmapped。
        一个不认识 "receipt" 的 receipt 类不是去污,是自残。"""
        assert doctype.classify("Receipt") == "receipt"
        assert doctype.classify("Transaction Receipt") == "receipt"

    def test_proforma_separate(self):
        """词表冻结:proforma 单独成类,不并进 invoice。"""
        assert doctype.classify("Pro Forma Invoice") == "proforma"
        assert doctype.classify("proforma") == "proforma"

    def test_check_under_receipt(self):
        """词表冻结:check 归 receipt,不拆新类。"""
        assert doctype.classify("check") == "receipt"
        assert doctype.classify("donation receipt") == "receipt"

    def test_order_and_estimate(self):
        assert doctype.classify("Purchase Order") == "purchase_order"
        assert doctype.classify("Media Estimate") == "estimate"
        assert doctype.classify("quotation") == "estimate"

    def test_contract_confirmation(self):
        assert doctype.classify("Broadcast Agreement") == "contract"
        assert doctype.classify("Order Confirmation") == "confirmation"

    def test_trusted_class_requires_complete_frozen_literal_evidence(self):
        good = {
            "status": "pass", "doc_class": "purchase_order",
            "evidence": {
                "phrase": "purchase order", "page": 0,
                "bbox": [[0.1, 0.2], [0.4, 0.3]], "words": 2,
            },
        }
        assert doctype.trusted_class(good) == "purchase_order"

        for broken in (
            {**good, "status": "fail"},
            {**good, "doc_class": "invented"},
            {**good, "evidence": None},
            {**good, "evidence": {**good["evidence"], "phrase": ""}},
            {**good, "evidence": {**good["evidence"], "page": True}},
            {**good, "evidence": {**good["evidence"], "bbox": [[0.4, 0.2], [0.1, 0.3]]}},
            {**good, "evidence": {**good["evidence"], "bbox": [[-0.1, 0.2], [0.4, 0.3]]}},
        ):
            assert doctype.trusted_class(broken) is None


def _fake_words(doc_id: str):
    """一页假 OCR:抬头 CREDIT MEMO,后面有 invoice 字样。"""
    # (page, word, bbox)
    yield 0, "CREDIT", ([[0.1, 0.05], [0.25, 0.08]])
    yield 0, "MEMO", ([[0.26, 0.05], [0.40, 0.08]])
    yield 0, "INVOICE", ([[0.1, 0.50], [0.30, 0.53]])
    yield 0, "TOTAL", ([[0.1, 0.60], [0.25, 0.63]])


class TestFindEvidence:
    def test_unknown_class_returns_none(self):
        assert doctype.find_evidence("any", "not_a_class") is None

    def test_no_evidence_returns_none(self, monkeypatch):
        monkeypatch.setattr(doctype, "iter_words",
                            lambda doc_id: iter(()))
        assert doctype.find_evidence("d1", "invoice") is None

    def test_credit_memo_phrase_and_bbox_merge(self, monkeypatch):
        monkeypatch.setattr(doctype, "iter_words", _fake_words)
        hit = doctype.find_evidence("d1", "credit_note")
        assert hit is not None
        assert hit["phrase"] == "credit memo"
        assert hit["page"] == 0
        assert hit["words"] == 2
        # 外接矩形合并两词
        assert hit["bbox"] == [[0.1, 0.05], [0.40, 0.08]]

    def test_earliest_phrase_wins(self, monkeypatch):
        """多个短语命中时取最早出现 —— 抬头优先。"""
        monkeypatch.setattr(doctype, "iter_words", _fake_words)
        # credit_note 的 phrases 含 credit memo 与 credit;应命中两词短语
        hit = doctype.find_evidence("d1", "credit_note")
        assert hit["phrase"] == "credit memo"

    def test_invoice_still_findable_later(self, monkeypatch):
        monkeypatch.setattr(doctype, "iter_words", _fake_words)
        hit = doctype.find_evidence("d1", "invoice")
        assert hit is not None
        assert hit["phrase"] == "invoice"
        assert hit["bbox"] == [[0.1, 0.50], [0.30, 0.53]]

    def test_token_boundary_no_substring(self, monkeypatch):
        """词序列匹配,不是子串 —— 'invoiced' 不能当 'invoice'。"""
        def words(doc_id):
            yield 0, "INVOICED", ([[0.1, 0.1], [0.3, 0.12]])
        monkeypatch.setattr(doctype, "iter_words", words)
        assert doctype.find_evidence("d1", "invoice") is None

    def test_no_claim_and_unmapped_differ(self):
        assert doctype.NO_CLAIM != doctype.UNMAPPED
        assert doctype.classify(None) == doctype.NO_CLAIM
        assert doctype.classify("xyzzy") == doctype.UNMAPPED
