"""共享测试装置:定位词的小语料 + 手工构造的 StoredResponse。"""

from __future__ import annotations

import json

import pytest

from invoiceloop import dws, ocr


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """测试一律不读磁盘上的 `.env` / 旧 vision.env。

    测试在仓库里跑,而仓库根常放着开发者真实的 `.env`。不隔离的话:
    ① 「缺 key 应该报错」这类用例会读到真凭证而假绿(实测发生过);
    ② 用例可能真的打出去、真的花额度。要测文件读取的用例自己 delenv
    这个开关(见 tests/test_env.py 的 no_legacy)。
    """
    from invoiceloop import env as env_mod

    monkeypatch.setenv(env_mod.DISABLE_VAR, "1")


def pin_corpus(monkeypatch, root) -> None:
    """fixture 锁定语料根:主变量与 legacy 别名同设。

    只设别名的话,评委照 README export 的 INVOICELOOP_CORPUS 会把 fixture
    遮蔽掉(ocr.derisk_root 主变量优先),产品测试在评委机上变红(81 评 P1-1)。
    研究测试不用这个 helper —— 它们读环境里的真语料。
    """
    monkeypatch.setenv("INVOICELOOP_CORPUS", str(root))
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(root))


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
    pin_corpus(monkeypatch, root)
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
