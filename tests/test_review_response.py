"""65/100 评审(2026-08-04)修复批的回归测试:

- 损坏存盘响应 → 登记 corrupt 记阻断,不 crash 整批(评审 P1)
- 文档集 = input/pdfs ∪ raw,抽取失败的文档不许隐身(评审 P1)
- OCR 受阻文档 → independent_ocr 阻断发现进 findings(评审 P2)
- panel 页脚的账本哈希重算比对(评审 P1)+ verify 校验深度与 CRC(评审 P2)
- CLI 输入错误给干净一句话(评审 P2)
"""

from __future__ import annotations

import json
import shutil
import struct
import zipfile
from pathlib import Path

import pytest

from invoiceloop import adjudicate, evidence, ocr
from tests.conftest import pin_corpus

DOC = "acme-001"


def _ocr_payload() -> dict:
    return {"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in (("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30))
        ]}]}],
    }]}


def _record(doc_id: str, mode: str) -> dict:
    return {"doc_id": doc_id, "document": f"{doc_id}.pdf", "mode": mode,
            "http_status": 200,
            "body": {"output": {
                "data": {"invoice_number": "INV-42", "total_gross": "100.00"},
                "metadata": {},
                "pages": [{"page": 1, "width": 612, "height": 792}]}}}


@pytest.fixture
def ws(tmp_path, monkeypatch):
    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / f"{DOC}.json").write_text(json.dumps(_ocr_payload()))
    (d / "raw").mkdir()
    for mode in ("understand", "agentic"):
        (d / "raw" / f"{DOC}.{mode}.json").write_text(json.dumps(_record(DOC, mode)))
    pin_corpus(monkeypatch, d)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield d
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


class TestCorruptStoredResponse:
    def test_register_marks_corrupt_instead_of_crashing(self, ws):
        (ws / "raw" / f"{DOC}.agentic.json").write_text("{not json")
        registry = evidence.register_artifacts([DOC])
        agentic = next(e for e in registry if e["mode"] == "agentic")
        assert agentic["corrupt"] is True and "http_status" not in agentic
        assert agentic["sha256"], "字节哈希照登记,可审计"

    def test_run_completes_and_blocks_the_doc(self, ws):
        from invoiceloop.pipeline import run

        (ws / "raw" / f"{DOC}.agentic.json").write_text("{not json")
        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        registry = json.loads((out / "artifact_registry.json").read_text())
        assert any(e.get("corrupt") for e in registry)
        report = json.loads((out / "gate_report.json").read_text())
        per_field = report["evaluations"][DOC]["total_gross"]
        assert per_field["cross_mode_agreement"] != "pass", \
            "一侧响应损坏时双模式不许放行(评审 P1:以前是一个坏文件 crash 整批)"


class TestSilentDocLoss:
    def test_pdf_without_raw_is_blocked_not_invisible(self, ws, monkeypatch):
        """input/pdfs 有、raw 没有的文档:以前是 run 里彻底隐身(评审 P1),
        现在必须出现在矩阵里并带 extraction_present 阻断。"""
        from invoiceloop import dws
        from invoiceloop.ingest import discover
        from invoiceloop.pipeline import run

        (ws / "input" / "pdfs" / "ghost.pdf").write_bytes(b"%PDF-1.4 ghost")
        doc_ids = sorted(set(discover(ws)) | set(dws.stored_docs()))
        assert "ghost" in doc_ids, "抽取失败的文档必须在文档集里"
        out = ws / "runs" / "run-0001"
        run(doc_ids, out, include_vision=False, out_of_calibration=True)
        report = json.loads((out / "gate_report.json").read_text())
        ghost = [f for f in report["findings"] if f["doc_id"] == "ghost"]
        assert any(f["blocking"] for f in ghost), \
            "没有存盘响应的文档必须记阻断,不许从 run 里隐身"


class TestOcrBlockedFinding:
    def test_blocked_doc_enters_findings(self, ws):
        from invoiceloop.pipeline import run

        (ws / "ocr" / f"{DOC}.json").unlink()
        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        report = json.loads((out / "gate_report.json").read_text())
        assert any(f["gate_id"] == "independent_ocr" and f["blocking"]
                   and f["doc_id"] == DOC for f in report["findings"]), \
            "OCR 受阻必须是 findings 里的阻断,不是只在 event_log(评审 P2)"


class TestPanelLedgerRecheck:
    def test_footer_flags_tampered_ledger(self, ws):
        from invoiceloop.panel import render_panel_from_run
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        render_panel_from_run(out)
        assert "与声明一致" in (out / "support_panel.html").read_text()
        ledger = json.loads((out / "field_ledger.json").read_text())
        ledger["claims"][0]["value"] = "999.99"  # 自报 sha 不动,内容改掉
        (out / "field_ledger.json").write_text(json.dumps(ledger))
        render_panel_from_run(out)
        assert "与文件自报不符" in (out / "support_panel.html").read_text(), \
            "页脚只打印自报哈希 = 让被改的账本自证清白(评审 P1)"


class TestVerifyDepth:
    def test_crc_corruption_is_a_structured_failure(self, tmp_path):
        # 造一个成员 CRC 损坏的 zip:合法 zip,翻第一个成员(x.txt)数据的
        # 第一个字节 —— 读它时 zipfile 抛 BadZipFile,必须转成结构化失败
        buf = tmp_path / "bad.zip"
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("x.txt", b"A" * 1000)
            zf.writestr("MANIFEST.sha256", "deadbeef  x.txt\n")
        data = bytearray(buf.read_bytes())
        assert data[:4] == b"PK\x03\x04"
        name_len, extra_len = struct.unpack_from("<HH", data, 26)
        data[30 + name_len + extra_len] ^= 0xFF
        buf.write_bytes(bytes(data))
        report = adjudicate.verify_bundle(buf)
        assert not report["ok"]
        assert any("成员损坏" in f or "哈希不符" in f for f in report["failures"]), \
            "CRC 损坏必须是结构化失败,不是裸 traceback"
        assert report["layers"]["members"] is False


class TestCliErrorUx:
    def test_value_error_becomes_a_clean_systemexit(self, ws, monkeypatch):
        import sys

        from invoiceloop.__main__ import main
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        monkeypatch.setattr(sys, "argv", [
            "invoiceloop", "adjudicate", "--run", str(out),
            "--doc", DOC, "--field", "total_gross", "--claim-id", "FC-9999",
            "--decision", "accept", "--rationale", "r", "--adjudicator", "y",
            "--decided-at", "2026-08-04T00:00:00"])
        with pytest.raises(SystemExit, match="错误"):
            main()
