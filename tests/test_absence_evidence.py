"""逐份缺席证据探针:页面上有没有印这个字段的标签。

类别条件缺席回答的是「这一类单据通常没有这个字段」——一个统计押注。
本模块回答的是「**这一份**的页面上根本没印过这个字段的标签」——一条证据
主张。后者能进 invoice 类,前者不能(`DOCTYPE_ABSENCE_DEV_2026-08-09.md`
第 2 节:`AE-invoice-seller_vat_id` 省 184 吞 7)。
"""

from __future__ import annotations

import pytest

from invoiceloop import absence_evidence as ae
from invoiceloop.ocr import OcrUnavailable


def _us_invoice_words(doc_id: str):
    """一页假 OCR:美国发票,没有任何税号/税额标签。"""
    yield 0, "INVOICE", ([[0.10, 0.05], [0.30, 0.08]])
    yield 0, "SUBTOTAL", ([[0.10, 0.50], [0.28, 0.53]])
    yield 0, "TOTAL", ([[0.10, 0.60], [0.25, 0.63]])
    yield 0, "AMOUNT", ([[0.40, 0.60], [0.55, 0.63]])


def _eu_invoice_words(doc_id: str):
    """一页假 OCR:印了 VAT 标签的欧洲发票。"""
    yield 0, "INVOICE", ([[0.10, 0.05], [0.30, 0.08]])
    yield 0, "VAT", ([[0.10, 0.40], [0.20, 0.43]])
    yield 0, "NUMBER", ([[0.21, 0.40], [0.38, 0.43]])
    yield 0, "TOTAL", ([[0.10, 0.60], [0.25, 0.63]])


class TestLexicon:
    def test_only_label_bearing_fields_are_in_scope(self):
        """有独特标签的字段才进词表。

        `buyer_name` / `seller_name` 页面上没有可靠标签;`invoice_number` /
        `issue_date` / `total_gross` / `amount_due` 的标签词
        (number / date / total / amount)几乎每张单据都有,探针永远说
        label_present —— 安全但无用。**明写出界,而不是假装能判。**
        """
        assert set(ae.LABEL_LEXICON) == {
            "seller_vat_id", "total_vat", "total_net", "due_date"}

    def test_every_phrase_is_lowercase_tokens(self):
        """短语必须是已切好的小写 token 序列 —— 两侧同一个切词函数。"""
        for field, phrases in ae.LABEL_LEXICON.items():
            assert phrases, f"{field} 词表为空"
            for phrase in phrases:
                assert phrase == phrase.lower()
                assert ae.tokens(phrase) == phrase.split(), \
                    f"{field}: {phrase!r} 不是干净的 token 序列"

    def test_digest_changes_with_the_lexicon(self):
        before = ae.digest()
        assert ae.digest(lexicon={"total_vat": ("vat",)}) != before
        assert ae.digest() == before, "digest 不得有副作用"


class TestProbe:
    def test_no_label_on_page_corroborates_absence(self, monkeypatch):
        monkeypatch.setattr(ae, "iter_words", _us_invoice_words)
        probe = ae.probe_document("d1")["seller_vat_id"]
        assert probe["status"] == ae.CORROBORATED
        assert probe["evidence"] is None
        assert probe["word_count"] == 4
        assert probe["phrases_probed"] == len(ae.LABEL_LEXICON["seller_vat_id"])

    def test_label_on_page_contradicts_absence_with_circleable_evidence(
            self, monkeypatch):
        """页面印着标签而 DWS 没返回值 —— 这不是缺席,是漏抽,必须给人看。

        证据带几何,人才能在整页渲染上圈出来(与 doctype 同一要求)。
        """
        monkeypatch.setattr(ae, "iter_words", _eu_invoice_words)
        probe = ae.probe_document("d1")["seller_vat_id"]
        assert probe["status"] == ae.LABEL_PRESENT
        assert probe["evidence"]["phrase"] == "vat"
        assert probe["evidence"]["page"] == 0
        assert probe["evidence"]["bbox"] == [[0.10, 0.40], [0.20, 0.43]]

    def test_multi_token_phrase_merges_boxes(self, monkeypatch):
        def words(doc_id):
            yield 0, "SALES", ([[0.10, 0.40], [0.22, 0.43]])
            yield 0, "TAX", ([[0.23, 0.40], [0.31, 0.43]])
        monkeypatch.setattr(ae, "iter_words", words)
        probe = ae.probe_document("d1")["total_vat"]
        assert probe["status"] == ae.LABEL_PRESENT
        assert probe["evidence"]["bbox"] == [[0.10, 0.40], [0.31, 0.43]]

    def test_token_sequence_not_substring(self, monkeypatch):
        """'vatican' 不是 'vat' —— 词序列匹配,不是子串包含。

        CLAUDE.md 的搬运陷阱二:`citation_holds` 是 `want in have`,
        照搬会把这条判成命中。
        """
        def words(doc_id):
            yield 0, "VATICAN", ([[0.10, 0.40], [0.30, 0.43]])
        monkeypatch.setattr(ae, "iter_words", words)
        assert ae.probe_document("d1")["seller_vat_id"]["status"] == \
            ae.CORROBORATED

    def test_out_of_scope_field_is_never_corroborated(self, monkeypatch):
        monkeypatch.setattr(ae, "iter_words", _us_invoice_words)
        probe = ae.probe_document("d1")["buyer_name"]
        assert probe["status"] == ae.NO_LEXICON
        assert ae.trusted_absence(probe) is False

    def test_ocr_unavailable_never_corroborates(self, monkeypatch):
        def boom(doc_id):
            raise OcrUnavailable(doc_id)
            yield  # pragma: no cover
        monkeypatch.setattr(ae, "iter_words", boom)
        probes = ae.probe_document("d1")
        assert probes["seller_vat_id"]["status"] == ae.OCR_UNAVAILABLE
        assert all(ae.trusted_absence(p) is False for p in probes.values())

    def test_empty_page_is_not_corroboration(self, monkeypatch):
        """一份 OCR 出零个词,不是「页面上没有标签」,是「没得找」。

        宪章四:检查跑不了不是通过。零词的文档若算 corroborated,
        整批 OCR 退化就会静默变成整批自动缺席。
        """
        monkeypatch.setattr(ae, "iter_words", lambda doc_id: iter(()))
        probe = ae.probe_document("d1")["seller_vat_id"]
        assert probe["word_count"] == 0
        assert ae.trusted_absence(probe) is False

    def test_one_ocr_pass_serves_every_field(self, monkeypatch):
        calls = []

        def counting(doc_id):
            calls.append(doc_id)
            yield from _us_invoice_words(doc_id)
        monkeypatch.setattr(ae, "iter_words", counting)
        probes = ae.probe_document("d1")
        assert len(calls) == 1, "每份文档只许扫一遍词级 OCR"
        assert set(probes) >= set(ae.LABEL_LEXICON)


class TestMonotoneSafety:
    def test_adding_a_token_can_only_withdraw_corroboration(self, monkeypatch):
        """**加词只会减少放行,永远不会造出静默错。**

        这条性质是本机制敢在开发集上定词表的全部理由:拟合压力只有
        在**删词**时才走向不安全的一侧。所以纪律是 ——
        看过结果之后加词随意,删词等于拟合。
        """
        monkeypatch.setattr(ae, "iter_words", _us_invoice_words)
        narrow = {"total_net": ("net",)}
        wide = {"total_net": ("net", "subtotal")}
        assert ae.probe_document("d1", lexicon=narrow)["total_net"]["status"] \
            == ae.CORROBORATED
        assert ae.probe_document("d1", lexicon=wide)["total_net"]["status"] \
            == ae.LABEL_PRESENT

    def test_frozen_lexicon_keeps_the_conservative_due_date_token(self):
        """`due_date` 保留裸 `due`,尽管 'Amount Due' 会让它几乎永不放行。

        窄化成只认 'due date' 会漏掉页面上写 'Due: 3/15' 的那种 —— 那正是
        会变成静默错的一侧。宁可省不到,不可吞掉。
        """
        assert "due" in ae.LABEL_LEXICON["due_date"]


class TestTrustedAbsence:
    def _good(self):
        return {"gate_id": "absence_evidence", "field": "seller_vat_id",
                "status": ae.CORROBORATED, "evidence": None,
                "word_count": 42, "phrases_probed": 9,
                "lexicon_digest": ae.digest()}

    def test_accepts_a_complete_corroboration(self):
        assert ae.trusted_absence(self._good()) is True

    def test_fails_closed_on_anything_malformed(self):
        good = self._good()
        for broken in (
            None,
            "absent_corroborated",
            {**good, "status": ae.LABEL_PRESENT},
            {**good, "status": ae.OCR_UNAVAILABLE},
            {**good, "word_count": 0},
            {**good, "word_count": -1},
            {**good, "word_count": True},
            {**good, "word_count": "42"},
            {**good, "phrases_probed": 0},
            {**good, "evidence": {"phrase": "vat"}},
            {k: v for k, v in good.items() if k != "word_count"},
            {**good, "lexicon_digest": "stale"},
        ):
            assert ae.trusted_absence(broken) is False, broken

    def test_a_different_lexicon_revision_is_not_trusted(self):
        """词表换了版本,旧工件里的 corroborated 不许直接采信。

        改词表 = 换检查。旧 run 的结论属于旧检查,重算才算数。
        """
        stale = {**self._good(),
                 "lexicon_digest": ae.digest(lexicon={"total_vat": ("vat",)})}
        assert ae.trusted_absence(stale) is False
