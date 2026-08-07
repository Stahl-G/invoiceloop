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
        (SEALED-2 阻断集里模型常谎报 invoice —— 那是证据门要抓的。)"""
        assert doctype.classify("new traffic order form") == "purchase_order"

    def test_credit_before_invoice(self):
        """'billing discrepancy/credit request' 必须进 credit_note,不能被 billing 抢走。"""
        assert doctype.classify("billing discrepancy/credit request") == "credit_note"
        assert doctype.classify("Credit Memorandum") == "credit_note"
        assert doctype.classify("credit memo") == "credit_note"

    def test_invoice_billing_alone(self):
        assert doctype.classify("billing") == "invoice"
        assert doctype.classify("Invoice") == "invoice"

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
