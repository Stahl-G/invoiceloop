"""真值口径规则 T1/T2(truth-caliber-v1,SEALED-4 增补件 A3)。

两层:合成语料钉死判定逻辑;真语料回归钉死增补件逐条列明的 9 个
开发集案例 —— 它们必须全部被重分类为口径争议,且标签与增补件一致。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import truth_caliber
from invoiceloop.improve import gate_verdict
from invoiceloop.ocr import corpus_available
from invoiceloop.safety_metrics import (
    empty_counts,
    score_routes,
    truth,
    write_annotation_stub,
)
from invoiceloop.truth_caliber import caliber_dispute

from tests.conftest import pin_corpus

# ------------------------------------------------------------ 合成语料装置


def _word(value):
    return {
        "value": value,
        "confidence": 0.99,
        "geometry": [[0.0, 0.0], [0.1, 0.1]],
        "snapped_geometry": [[0.0, 0.0], [0.1, 0.1]],
    }


def _write_ocr(root, doc_id, words):
    ocr_dir = root / "data" / "docile" / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    page = {
        "page_idx": 0,
        "dimensions": [1000, 800],
        "orientation": {"value": None, "confidence": None},
        "language": {"value": "en", "confidence": None},
        "blocks": [{
            "geometry": [[0, 0], [1, 1]],
            "artefacts": [],
            "lines": [{"geometry": [[0, 0], [1, 1]],
                       "words": [_word(w) for w in words]}],
        }],
    }
    (ocr_dir / f"{doc_id}.json").write_text(json.dumps({"pages": [page]}))


@pytest.fixture
def corpus(tmp_path, monkeypatch, clear_ocr_caches):
    pin_corpus(monkeypatch, tmp_path)
    return tmp_path


# ------------------------------------------------------------ 常量与增补件一致


def test_frozen_constants_match_amendment():
    assert truth_caliber.TRUTH_CALIBER_VERSION == "truth-caliber-v1"
    assert truth_caliber.T1_FIELDS == frozenset(
        {"total_net", "total_vat", "total_gross"})
    assert truth_caliber.T2_CONTEXT_TERMS == (
        "transaction", "donation", "authorization", "adjustment")
    assert truth_caliber.T2_WINDOW_WORDS == 12


# ------------------------------------------------------------ T1 单总额


def test_t1_same_amount_two_slots(corpus):
    tmap = {"total_net": "1100.00", "amount_due": "$1100.00"}
    assert caliber_dispute("d1", "total_net", tmap) == "T1"
    assert caliber_dispute("d1", "total_gross", {"total_gross": "1,100.00",
                                                 "amount_due": "1100.00"}) == "T1"


def test_t1_rejects_different_or_missing_amounts(corpus):
    assert caliber_dispute(
        "d1", "total_net", {"total_net": "900.00",
                            "amount_due": "1100.00"}) is None
    assert caliber_dispute("d1", "total_net", {"total_net": "1100.00"}) is None
    # 非金额字段不走 T1
    assert caliber_dispute("d1", "seller_vat_id",
                           {"seller_vat_id": "12-3456789"}) is None


# ------------------------------------------------------------ T2 别名目日期


def test_t2_i_due_equals_issue(corpus):
    _write_ocr(corpus, "d1", ["Date:", "August", "26,", "2020"])
    tmap = {"due_date": "August 26, 2020", "issue_date": "August 26, 2020"}
    assert caliber_dispute("d1", "due_date", tmap) == "T2(i)"


def test_t2_ii_transaction_context(corpus):
    _write_ocr(corpus, "d1",
               ["Transaction", "Sale", "Date", "Time", "12/1/2021",
                "11:05:17", "AM", "CST"])
    tmap = {"due_date": "12/1/2021"}
    assert caliber_dispute("d1", "due_date", tmap) == "T2(ii)"


def test_t2_ii_term_outside_window_fails(corpus):
    # "transaction" 与日期之间隔 13 个词,超出 ±12 窗
    gap = [f"w{i}" for i in range(13)]
    _write_ocr(corpus, "d1", ["transaction"] + gap + ["12/1/2021"])
    assert caliber_dispute("d1", "due_date", {"due_date": "12/1/2021"}) is None


def test_t2_date_not_on_page_fails(corpus):
    _write_ocr(corpus, "d1", ["transaction", "sale", "date", "time"])
    # 真值日期不在页面上:无法建立「别名目日期」,维持真静默
    assert caliber_dispute("d1", "due_date", {"due_date": "12/1/2021"}) is None


def test_t2_no_ocr_stays_silent(corpus):
    # 有标注、无 OCR 文件:判不了,返回 None(宪章四,维持真静默)
    assert caliber_dispute("d-missing", "due_date",
                           {"due_date": "12/1/2021"}) is None


# ------------------------------------------------------------ score_routes 拆分


def test_score_routes_splits_caliber_from_true(corpus):
    _write_ocr(corpus, "d1", ["transaction", "sale", "date", "time",
                              "12/1/2021"])
    write_annotation_stub(corpus, "d1", {"due_date": "12/1/2021"})
    write_annotation_stub(corpus, "d2", {"due_date": "03/04/2022"})
    _write_ocr(corpus, "d2", ["payment", "due", "03/04/2022"])
    routes = [
        {"doc_id": "d1", "field": "due_date", "route": "auto_absent"},
        {"doc_id": "d2", "field": "due_date", "route": "auto_absent"},
    ]
    counts = score_routes(routes, caliber_of=caliber_dispute)
    assert counts["silent_absent"] == 2       # 原口径照登
    assert counts["caliber_disputes"] == 1    # d1:交易时间戳
    assert counts["silent_absent_true"] == 1  # d2:真静默
    # 不给 caliber_of 时全部计真静默(向后兼容)
    legacy = score_routes(routes)
    assert legacy["caliber_disputes"] == 0
    assert legacy["silent_absent_true"] == 2


def test_empty_counts_has_caliber_keys():
    counts = empty_counts()
    assert counts["caliber_disputes"] == 0
    assert counts["silent_absent_true"] == 0


# ------------------------------------------------------------ gate_verdict 用真静默列


def _eval(**over):
    ev = {
        "basis": "evo_truth_replay",
        "safety_status": "scored",
        "absence_probe_status": "not_applicable",
        "class_absent_rule_count": 0,
        "evidenced_absent_rule_count": 0,
        "silent_absent_baseline": 0,
        "silent_absent_candidate": 0,
        "silent_wrong_baseline": 3,
        "silent_wrong_candidate": 3,
        "review_load_baseline": 0.60,
        "review_load_candidate": 0.50,
    }
    ev.update(over)
    return ev


def test_gate_verdict_ignores_caliber_disputes():
    ev = _eval(
        silent_absent_candidate=1,            # 原口径 0 → 1
        caliber_disputes_candidate=1,         # 但那 1 例是口径争议
        silent_absent_true_baseline=0,
        silent_absent_true_candidate=0)
    verdict = gate_verdict(ev)
    assert verdict["ok"], verdict["refusals"]


def test_gate_verdict_refuses_true_silent_rise():
    ev = _eval(
        silent_absent_baseline=1,             # 基线那 1 例全是口径争议
        caliber_disputes_baseline=1,
        silent_absent_true_baseline=0,
        silent_absent_candidate=1,
        caliber_disputes_candidate=0,
        silent_absent_true_candidate=1)       # 候选这 1 例是真静默
    verdict = gate_verdict(ev)
    assert not verdict["ok"]
    assert any("真静默" in r for r in verdict["refusals"])


# ------------------------------------------------------------ 真语料回归:增补件的 9 个案例


@pytest.mark.skipif(not corpus_available(), reason="存盘证据不在")
class TestAmendmentDevCases:
    """增补件 A3 逐条列明的 9 个开发集案例必须全部按预期标签重分类。"""

    T1_CASES = {"f7b199fd711149feaf0044c8": "total_net"}
    T2_CASES = {
        "0c56b86aedd445d8a845a287": "T2(ii)",   # credit adjustment by eft
        "254b7845992547228487acc5": "T2(ii)",   # transaction sale date time
        "878ad70041f840eb923504a3": "T2(ii)",   # receipt 时间戳 + authorization
        "a14811674f9e4b2c99bce2be": "T2(i)",    # donation,due==issue
        "a187ba31eae2481ca20cdc7a": "T2(i)",    # donation,due==issue
        "c8d26800425448f1ae2115d1": "T2(ii)",   # payment information 表
        "cdf65b6accc54facb0d8cf8e": "T2(ii)",   # transaction sale date time
        "db2e81c790384a11bbde5194": "T2(i)",    # donation,due==issue
    }

    def test_t1_case(self):
        for doc_id, field in self.T1_CASES.items():
            assert caliber_dispute(doc_id, field, truth(doc_id)) == "T1"

    def test_t2_cases(self):
        for doc_id, label in self.T2_CASES.items():
            assert caliber_dispute(doc_id, "due_date", truth(doc_id)) == label
