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
                "046e0c49 的读图门 warning 是 demo 的展品之一(数据决定,与环境无关)"
            # 046e0c49 是否 OCR 受阻取决于本机 poppler 能否从退化扫描件抽出
            # 文字层 —— 两种形态都合法。钉的是不变量:受阻必显式(事件 +
            # 阻断 finding 成对出现),不是「某份文档必须受阻」(78 评 P3)
            blocked_events = [
                json.loads(line) for line in
                (run_dir / "event_log.jsonl").read_text().splitlines()
                if json.loads(line)["event"] == "doc_blocked"]
            for event in blocked_events:
                assert any(f["gate_id"] == "independent_ocr"
                           and f["doc_id"] == event["doc_id"] and f["blocking"]
                           for f in gate["findings"]), \
                    "受阻文档必须有文档级阻断 finding,不藏"
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


@pytest.mark.skipif(not POPPLER, reason="需要 poppler")
class TestDemoReachesTheTerminus:
    """演示必须走到出口。

    出口(`deliverable.json`)从 2026-08-05 起就在代码里,但 demo 语料跑完
    `by_status` 是 `{"pending": 3}` —— 三份文档全部未决。于是公开演示上
    评委看到的永远是一个待办队列,看不到系统交付什么。存在但不可见,
    对读者而言约等于不存在。
    """

    def test_at_least_one_document_reaches_release(self, tmp_path):
        from invoiceloop.demo import cmd_demo

        ws = tmp_path / "ws"
        cmd_demo(ws)
        deliverable = json.loads(
            (ws / "runs" / "run-0001" / "deliverable.json").read_text(encoding="utf-8"))

        released = [d for d, v in deliverable["docs"].items()
                    if v["status"] in ("released", "released_with_caveats")]
        assert released, (
            f"没有任何文档走到出口:{deliverable['summary']['by_status']}")

    def test_seeded_decisions_never_impersonate_a_human_reviewer(self, tmp_path):
        """裁决账本是「某个人看过并判了」的证词。

        演示里的裁决不是人做的,所以署名必须让任何人一眼看出来不是人 ——
        这条比「演示好看」重要。
        """
        from invoiceloop.demo import DEMO_ADJUDICATOR, cmd_demo

        ws = tmp_path / "ws"
        cmd_demo(ws)
        ledger = (ws / "runs" / "run-0001" / "adjudication_ledger.jsonl")
        entries = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]

        assert entries, "没有种子裁决"
        assert "demo" in DEMO_ADJUDICATOR and "fixture" in DEMO_ADJUDICATOR
        for e in entries:
            assert e["adjudicator"] == DEMO_ADJUDICATOR, (
                f"演示裁决署了别的名字:{e['adjudicator']!r}")
            assert "fixture" in e["rationale"].lower(), "理由里必须写明是夹具"
