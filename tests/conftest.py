"""共享测试装置:定位词的小语料 + 手工构造的 StoredResponse。"""

from __future__ import annotations

import json

import pytest

from invoiceloop import dws, ocr


@pytest.fixture
def clear_ocr_caches():
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def _word(value, x0, y0, x1, y1):
    return {
        "value": value,
        "confidence": 0.99,
        "geometry": [[x0, y0], [x1, y1]],
        "snapped_geometry": [[x0, y0], [x1, y1]],
    }


@pytest.fixture
def positioned_corpus(tmp_path, monkeypatch, clear_ocr_caches):
    """doc-a:三个定位词 —— INV-42 在左上,Total/100.00 在中部同一行。"""
    root = tmp_path / "derisk"
    ocr_dir = root / "data" / "docile" / "ocr"
    ocr_dir.mkdir(parents=True)
    words = [
        _word("INV-42", 0.10, 0.10, 0.20, 0.13),
        _word("Total", 0.10, 0.50, 0.20, 0.53),
        _word("100.00", 0.30, 0.50, 0.45, 0.53),
        _word("Net", 0.10, 0.60, 0.18, 0.63),
        _word("90.00", 0.30, 0.60, 0.43, 0.63),
    ]
    page = {
        "page_idx": 0,
        "dimensions": [1000, 800],
        "orientation": {"value": None, "confidence": None},
        "language": {"value": "en", "confidence": None},
        "blocks": [{
            "geometry": [[0, 0], [1, 1]],
            "artefacts": [],
            "lines": [{"geometry": [[0, 0], [1, 1]], "words": words}],
        }],
    }
    (ocr_dir / "doc-a.json").write_text(json.dumps({"pages": [page]}))
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(root))
    return root


def make_response(doc_id: str, mode: str, data: dict, meta: dict | None = None) -> dws.StoredResponse:
    """手工构造存盘响应;页尺寸固定 1000×1000,bbox 直接写像素。"""
    return dws.StoredResponse(
        doc_id=doc_id, mode=mode, http_status=200,
        data=data, meta=meta or {},
        pages=[{"page": 1, "width": 1000, "height": 1000}],
        path=dws.response_path(doc_id, mode),
    )


def bbox_meta(x0, y0, x1, y1):
    """source_bboxes 形式的 meta(像素坐标)。"""
    return {
        "bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
        "pageIndex": 0, "pageNumber": 1,
        "source_bboxes": [{
            "bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            "block_id": "b1", "pageIndex": 0, "pageNumber": 1,
        }],
    }
