"""输入契约的测试:PDF 从 input/pdfs/ 进,panel 到 output/ 出,
"不在校准集内"必须写在脑门上(§12.3)。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from invoiceloop import ingest, ocr
from invoiceloop.ingest import cmd_ingest, discover, sanitise_doc_id
from invoiceloop.ocr_ingest import ocr_pdf, parse_tesseract_tsv

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "mini-invoice.pdf"
POPPLER = shutil.which("pdftotext") is not None


class TestDocId:
    def test_sanitise_is_deterministic_and_filesafe(self):
        assert sanitise_doc_id("Acme Corp #2024-01.PDF") == "acme-corp-2024-01-pdf"
        assert sanitise_doc_id("发票(1)") == "1"  # 非 ASCII 折叠掉,别为空
        assert sanitise_doc_id("###") != sanitise_doc_id("%%%")  # 空壳退哈希

    def test_discovery_collision_gets_deterministic_suffix(self, tmp_path):
        d = tmp_path / "input" / "pdfs"
        d.mkdir(parents=True)
        # macOS 文件系统大小写不敏感,用 sanitise 后才碰撞的两个名字
        (d / "a-1.pdf").write_bytes(b"x")
        (d / "a 1.pdf").write_bytes(b"y")
        docs = discover(tmp_path)
        assert len(docs) == 2
        assert sorted(docs)[0] == "a-1" and sorted(docs)[1].startswith("a-1-")


class TestLayout:
    def test_workspace_layout_detected_by_input_pdfs(self, tmp_path, monkeypatch):
        (tmp_path / "input" / "pdfs").mkdir(parents=True)
        monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(tmp_path))
        assert ocr.layout() == "workspace"
        assert ocr.ocr_path("d1") == tmp_path / "ocr" / "d1.json"
        assert ocr.pdf_path("d1") == tmp_path / "input" / "pdfs" / "d1.pdf"

    def test_derisk_layout_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(tmp_path))
        assert ocr.layout() == "derisk"
        assert "data/docile" in str(ocr.ocr_path("d1"))


@pytest.mark.skipif(not POPPLER, reason="需要 poppler")
class TestOcrIngest:
    def test_text_layer_words_have_relative_geometry(self, tmp_path):
        payload = ocr_pdf(FIXTURE_PDF, work_dir=tmp_path)
        words = payload["pages"][0]["blocks"][0]["lines"][0]["words"]
        values = {w["value"] for w in words}
        assert {"INV-42", "Total", "100.00", "Gross", "Seller"} <= values
        for w in words:
            (x0, y0), (x1, y1) = w["geometry"]
            assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1

    def test_tesseract_tsv_parser(self):
        tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
               "left\ttop\twidth\theight\tconf\ttext\n"
               "5\t1\t1\t1\t1\t1\t72\t100\t74\t22\t96.5\tINV-42\n"
               "5\t1\t1\t1\t1\t2\t160\t100\t80\t22\t95.0\tTotal\n")
        words = parse_tesseract_tsv(tsv, 1000, 800)
        assert words[0]["value"] == "INV-42"
        assert words[0]["geometry"] == [[0.072, 0.125], [0.146, 0.1525]]
        assert words[0]["confidence"] == pytest.approx(0.965)


@pytest.mark.skipif(not POPPLER, reason="需要 poppler")
class TestWorkspaceContract:
    """全链路:input/pdfs → ingest → fake raw → run --workspace → output。"""

    def _record(self, doc_id, mode, data, meta):
        return {"doc_id": doc_id, "document": f"{doc_id}.pdf", "mode": mode,
                "http_status": 200,
                "body": {"output": {"data": data, "metadata": meta,
                                    "pages": [{"page": 1, "width": 612, "height": 792}]}}}

    @pytest.fixture
    def workspace(self, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        (ws / "input" / "pdfs").mkdir(parents=True)
        shutil.copy(FIXTURE_PDF, ws / "input" / "pdfs" / "acme-001.pdf")
        cmd_ingest(ws, do_extract=False)  # 本地产 OCR,不调 DWS
        doc_id = "acme-001"
        meta = {"invoice_number": {
            "bbox": {"x": 60, "y": 60, "width": 200, "height": 60}, "pageIndex": 0,
            "source_bboxes": [{"bbox": {"x": 60, "y": 60, "width": 200, "height": 60},
                               "block_id": "b1", "pageIndex": 0, "pageNumber": 1}]}}
        data = {"invoice_number": "INV-42", "total_gross": "100.00"}
        (ws / "raw").mkdir()
        for mode in ("understand", "agentic"):
            (ws / "raw" / f"{doc_id}.{mode}.json").write_text(
                json.dumps(self._record(doc_id, mode, data, meta)), encoding="utf-8")
        monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(ws))
        ocr.load_ocr.cache_clear()
        ocr.doc_tokens.cache_clear()
        yield ws, doc_id
        ocr.load_ocr.cache_clear()
        ocr.doc_tokens.cache_clear()

    def test_ingest_produces_independent_ocr(self, workspace):
        ws, doc_id = workspace
        payload = json.loads((ws / "ocr" / f"{doc_id}.json").read_text())
        assert any(w["value"] == "INV-42"
                   for w in payload["pages"][0]["blocks"][0]["lines"][0]["words"])

    def test_run_workspace_end_to_end_with_banner(self, workspace):
        from invoiceloop.pipeline import run

        ws, doc_id = workspace
        paths = run([doc_id], ws / "output", include_vision=False,
                    out_of_calibration=True)
        panel = paths["panel"].read_text(encoding="utf-8")
        assert "输入不在校准集内" in panel, "§12.3:非校准集输入必须声明"
        ledger = json.loads(paths["ledger"].read_text())
        claims = {(c["doc_id"], c["field"]) for c in ledger["claims"]}
        assert (doc_id, "invoice_number") in claims, "INV-42 应当能绑进账本"
        manifest = json.loads(paths["manifest"].read_text())
        assert manifest["out_of_calibration"] is True
        assert manifest["layout"] == "workspace"

    def test_workspace_run_is_deterministic(self, workspace):
        from invoiceloop.pipeline import run

        ws, doc_id = workspace
        a = run([doc_id], ws / "out-a", include_vision=False, out_of_calibration=True)
        b = run([doc_id], ws / "out-b", include_vision=False, out_of_calibration=True)
        assert a["matrix"].read_bytes() == b["matrix"].read_bytes()
        assert a["panel"].read_bytes() == b["panel"].read_bytes()


class TestDwsClient:
    def test_record_shape_matches_archive(self, tmp_path, monkeypatch):
        from invoiceloop import dws_client

        class FakeResponse:
            status_code = 200
            headers = {"x-credits-used": "15", "x-request-id": "req-1"}
            text = "{}"

            def json(self):
                return {"output": {"data": {"invoice_number": "INV-42"}}}

        monkeypatch.setattr(dws_client.requests, "post", lambda *a, **k: FakeResponse())
        record = dws_client.extract_to_raw(
            FIXTURE_PDF, {"type": "object", "properties": {}}, tmp_path,
            doc_id="d1", mode="understand", api_key="test-key")
        assert record["http_status"] == 200
        assert record["credits"] == "15"
        on_disk = json.loads((tmp_path / "d1.understand.json").read_text())
        assert on_disk["body"]["output"]["data"]["invoice_number"] == "INV-42"

        # 与 dws.load_response 的读取契约对得上(同一份 record 形状)
        monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(tmp_path.parent))
        (tmp_path.parent / "raw").mkdir(exist_ok=True)
        shutil.move(str(tmp_path / "d1.understand.json"),
                    str(tmp_path.parent / "raw" / "d1.understand.json"))
        from invoiceloop import dws

        loaded = dws.load_response("d1", "understand")
        assert loaded is not None and loaded.data["invoice_number"] == "INV-42"


@pytest.mark.skipif(not POPPLER, reason="需要 poppler")
def test_garbage_pdf_is_ocr_unavailable_not_a_crash(tmp_path):
    """损坏 PDF 是常态输入:pdftotext/pdftoppm 失败必须退到 OcrUnavailable
    阻断(宪章四),不是 CalledProcessError 半路崩溃。"""
    from invoiceloop.ocr import OcrUnavailable

    garbage = tmp_path / "garbage.pdf"
    garbage.write_bytes(b"%PDF-1.4 this is not a real pdf, just bytes")
    with pytest.raises(OcrUnavailable):
        ocr_pdf(garbage, work_dir=tmp_path)
