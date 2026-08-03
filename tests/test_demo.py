"""demo 命令与去 derisk 化:内嵌语料跑通全流程,语料指针双名。"""

from __future__ import annotations

import json
import shutil
from importlib import resources

import pytest

POPPLER = shutil.which("pdftotext") is not None


def test_corpus_env_alias(monkeypatch, tmp_path):
    from invoiceloop import ocr

    monkeypatch.setenv("INVOICELOOP_CORPUS", str(tmp_path / "new"))
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(tmp_path / "legacy"))
    assert ocr.derisk_root() == tmp_path / "new", "新名优先"
    monkeypatch.delenv("INVOICELOOP_CORPUS")
    assert ocr.derisk_root() == tmp_path / "legacy", "历史别名仍然有效"


def test_samples_are_wellformed():
    src = resources.files("invoiceloop") / "samples"
    docs = {p.name[:-4] for p in (src / "pdfs").iterdir()}
    assert len(docs) == 3, "三份示例发票"
    for raw in (src / "raw").iterdir():
        rec = json.loads(raw.read_bytes())
        assert rec["http_status"] == 200
        assert raw.name.split(".")[0] in docs, "raw 必须属于示例文档之一"
    for tsv in (src / "vision").iterdir():
        lines = tsv.read_bytes().decode().splitlines()
        assert len(lines) > 1, "读图作答不能只剩表头"
        for line in lines[1:]:
            assert line.split("\t")[0] in docs


@pytest.mark.skipif(not POPPLER, reason="需要 poppler")
class TestDemoEndToEnd:
    def test_demo_builds_a_complete_run(self, tmp_path):
        from invoiceloop import ocr
        from invoiceloop.demo import cmd_demo

        ws = tmp_path / "demo-ws"
        cmd_demo(ws)
        try:
            run_dir = ws / "runs" / "run-0001"
            panel = (run_dir / "support_panel.html").read_text(encoding="utf-8")
            assert "输入不在校准集内" in panel
            gate = json.loads((run_dir / "gate_report.json").read_text())
            assert any(f["gate_id"] == "visual_corroboration"
                       for f in gate["findings"]), \
                "046e0c49 的读图门 warning 是 demo 的展品之一"
            events = (run_dir / "event_log.jsonl").read_text()
            assert "doc_blocked" in events, "046e0c49 的 OCR 受阻必须显式,不藏"
            assert json.loads((ws / "runs" / "current.json").read_text()) == \
                {"run": "run-0001"}
        finally:
            ocr.load_ocr.cache_clear()
            ocr.doc_tokens.cache_clear()

    def test_demo_refuses_nonempty_out(self, tmp_path):
        from invoiceloop.demo import cmd_demo

        ws = tmp_path / "demo-ws"
        ws.mkdir()
        (ws / "anything").write_text("x")
        with pytest.raises(SystemExit, match="非空"):
            cmd_demo(ws)

    def test_demo_restores_corpus_env(self, tmp_path, monkeypatch):
        from invoiceloop.demo import cmd_demo

        monkeypatch.setenv("INVOICELOOP_CORPUS", "/original/corpus")
        ws = tmp_path / "demo-ws"
        cmd_demo(ws)
        import os

        assert os.environ["INVOICELOOP_CORPUS"] == "/original/corpus", \
            "库调用不许留下环境副作用"
