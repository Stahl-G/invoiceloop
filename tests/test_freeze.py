"""冻结事务的单元测试:拒绝路径、ID 分配、账本哈希、阻断传播。

绑定回归(454 行真实作答)在 test_binding_regression.py;这里测事务本身:
每一步拒绝都必须显式记事件、不进账本(宪章四),ID 只能由 Python 分配(宪章一)。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import freeze, ocr


@pytest.fixture(autouse=True)
def clear_caches():
    """每个测试用独立的小语料,清掉 lru_cache 防串扰。"""
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


@pytest.fixture
def tiny_corpus(tmp_path, monkeypatch):
    """两份迷你发票的 OCR:doc-a 有 'INV-42' 和 'Total 100.00',doc-b 没有。"""
    root = tmp_path / "derisk"
    ocr_dir = root / "data" / "docile" / "ocr"
    ocr_dir.mkdir(parents=True)

    def page(words):
        return {
            "pages": [
                {
                    "page_idx": 0,
                    "dimensions": [1000, 800],
                    "orientation": {"value": None, "confidence": None},
                    "language": {"value": "en", "confidence": None},
                    "blocks": [
                        {
                            "geometry": [[0, 0], [1, 1]],
                            "artefacts": [],
                            "lines": [
                                {
                                    "geometry": [[0, 0], [1, 1]],
                                    "words": [
                                        {
                                            "value": w,
                                            "confidence": 0.99,
                                            "geometry": [[0, 0], [0.1, 0.1]],
                                            "snapped_geometry": [[0, 0], [0.1, 0.1]],
                                        }
                                        for w in words
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    (ocr_dir / "doc-a.json").write_text(
        json.dumps(page(["INV-42", "Total", "100.00", "Gross", "Amt:"]))
    )
    (ocr_dir / "doc-b.json").write_text(json.dumps(page(["Hello", "World"])))
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(root))
    return root


def test_admitted_rows_get_sequential_python_ids(tiny_corpus):
    result = freeze.freeze_drafts(
        [
            {"doc_id": "doc-a", "field": "invoice_number", "value": "INV-42"},
            {"doc_id": "doc-a", "field": "total_gross", "value": "100.00"},
        ]
    )
    assert [c["claim_id"] for c in result.claims] == ["FC-0001", "FC-0002"]
    assert [e["event"] for e in result.events] == ["claim_frozen", "claim_frozen"]


def test_unbindable_row_is_rejected_with_event_not_in_ledger(tiny_corpus):
    result = freeze.freeze_drafts(
        [
            {"doc_id": "doc-b", "field": "invoice_number", "value": "INV-42"},
            {"doc_id": "doc-b", "field": "seller_name", "value": "Hello World"},
        ]
    )
    assert [c["field"] for c in result.claims] == ["seller_name"]
    rejection = result.rejections[0]
    assert rejection["reason"] == "binding"
    assert rejection["coverage"] == 0.0
    event = result.events[0]
    assert event["event"] == "draft_binding_rejected"
    assert event["field"] == "invoice_number"


def test_prewritten_claim_id_is_rejected(tiny_corpus):
    """宪章一:ID 是 Python 的权威,草稿预写 ID 一律拒。"""
    result = freeze.freeze_drafts(
        [{"doc_id": "doc-a", "field": "invoice_number", "value": "INV-42", "claim_id": "FC-9999"}]
    )
    assert result.claims == []
    assert result.rejections[0]["reason"] == "prewritten_claim_id"
    assert result.events[0]["event"] == "draft_prewritten_id_rejected"


def test_empty_value_cannot_bind(tiny_corpus):
    result = freeze.freeze_drafts(
        [{"doc_id": "doc-a", "field": "invoice_number", "value": "$,.:"}]
    )
    assert result.claims == []
    assert result.rejections[0]["reason"] == "empty_value"
    assert result.events[0]["event"] == "draft_empty_value_rejected"


def test_span_containment_is_recorded_not_gating(tiny_corpus):
    """值落在哪个片段决定 support_strength;不落在任何片段也必须能入账。"""
    spans = [
        {"span_id": "ES-0001", "doc_id": "doc-a", "ocr_text": "Total 100.00"},
        {"span_id": "ES-0002", "doc_id": "doc-a", "ocr_text": "Gross Amt: 100.00"},
    ]
    result = freeze.freeze_drafts(
        [
            {"doc_id": "doc-a", "field": "total_gross", "value": "100.00"},
            {"doc_id": "doc-a", "field": "invoice_number", "value": "INV-42"},
        ],
        spans=spans,
    )
    assert result.claims[0]["span_ids"] == ["ES-0001", "ES-0002"]
    assert result.claims[1]["span_ids"] == []  # 不在任何片段,仍入账


def test_span_from_another_doc_never_counts(tiny_corpus):
    """别的发票的片段里有同样的字,不等于这个值有出处 —— 片段匹配限本 doc。"""
    spans = [{"span_id": "ES-0009", "doc_id": "doc-b", "ocr_text": "Total 100.00"}]
    result = freeze.freeze_drafts(
        [{"doc_id": "doc-a", "field": "total_gross", "value": "100.00"}],
        spans=spans,
    )
    assert result.claims[0]["span_ids"] == []


def test_ledger_carries_stable_content_hash(tiny_corpus):
    drafts = [{"doc_id": "doc-a", "field": "invoice_number", "value": "INV-42"}]
    a = freeze.freeze_drafts(drafts).ledger()
    b = freeze.freeze_drafts(drafts).ledger()
    assert a["sha256"] == b["sha256"]
    assert len(a["sha256"]) == 64


def test_unknown_field_is_rejected_not_silently_dropped(tiny_corpus):
    """DWS 会返回评估集外的字段,甚至幻觉字段名(实测 \x06)—— 显式拒。"""
    result = freeze.freeze_drafts(
        [
            {"doc_id": "doc-a", "field": "currency", "value": "INV-42"},
            {"doc_id": "doc-a", "field": "\x06", "value": "INV-42"},
            {"doc_id": "doc-a", "field": "invoice_number", "value": "INV-42"},
        ]
    )
    assert [c["field"] for c in result.claims] == ["invoice_number"]
    assert [r["reason"] for r in result.rejections] == ["unknown_field", "unknown_field"]
    assert result.events[0]["event"] == "draft_unknown_field_rejected"


def test_missing_ocr_raises_not_silently_rejects(tiny_corpus):
    """宪章四:OCR 缺失是阻断,抛异常,不压成 False 藏进拒绝率。"""
    with pytest.raises(ocr.OcrUnavailable):
        freeze.binds_to_document("doc-ghost", "INV-42")
    with pytest.raises(ocr.OcrUnavailable):
        freeze.freeze_drafts(
            [{"doc_id": "doc-ghost", "field": "invoice_number", "value": "INV-42"}]
        )
