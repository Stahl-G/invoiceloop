"""vision-ingest:packet 规格保真、tsv 格式、断点续跑、缺 key 不藏。"""

from __future__ import annotations

import json
import shutil

import pytest

from invoiceloop.vision_ingest import _parse_rows, cmd_vision

FIXTURE_PDF = __import__("pathlib").Path(__file__).parent / "fixtures" / "mini-invoice.pdf"
POPPLER = shutil.which("pdftoppm") is not None

DOC = "acme-001"


@pytest.fixture
def ws(tmp_path):
    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, d / "input" / "pdfs" / f"{DOC}.pdf")
    return d


class FakeResp:
    status_code = 200

    def __init__(self, text):
        self._text = text

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


def _post_with(text):
    calls = []

    def post(url, **kw):
        calls.append(kw)
        return FakeResp(text)

    return post, calls


class TestParseRows:
    def test_all_ten_fields_always_present_and_doc_filled(self):
        rows = _parse_rows("total_gross\t$8,500.00\tGross Amt:\t\n"
                           "invoice_number\tINV-42\tInvoice #\t", DOC)
        assert len(rows) == 10, "没答的字段补空值行(空=弃权,不藏漏答)"
        by_field = {r[1]: r for r in rows}
        assert by_field["total_gross"][2] == "$8,500.00"
        assert by_field["total_gross"][0] == DOC
        assert by_field["seller_name"][2] == "", "漏答 = 空值"

    def test_prose_around_rows_is_dropped(self):
        rows = _parse_rows("好的,我读完了。\ntotal_gross\t100.00\tTotal\t\n希望对你有帮助!", DOC)
        assert sum(1 for r in rows if r[2]) == 1


@pytest.mark.skipif(not POPPLER, reason="需要 poppler")
class TestCmdVision:
    def test_writes_spec_shaped_tsv_and_resumes(self, ws):
        post, calls = _post_with("total_gross\t100.00\tTotal\t\n"
                                 "invoice_number\tABSTAIN\t\t糊了\n")
        summary = cmd_vision(ws, api_key="k", _post=post)
        assert summary["read"] == 1 and len(calls) == 1
        tsv = (ws / "vision" / "answers6.D.tsv").read_text()
        lines = tsv.splitlines()
        assert lines[0] == "doc\tfield\tvalue\tprinted_label\tnote"
        assert len(lines) == 11, "表头 + 10 字段行"
        assert f"{DOC}\ttotal_gross\t100.00\tTotal" in tsv
        assert f"{DOC}\tinvoice_number\tABSTAIN" in tsv
        assert summary["abstained_fields"] == 9, "1 个 ABSTAIN + 8 个空值"

        # 断点续跑:已有该文档的行 → 不再调 API
        summary2 = cmd_vision(ws, api_key="k", _post=post)
        assert summary2["skipped"] == 1 and len(calls) == 1

        # 与 dws.load_vision_answers 的读取契约对得上
        from invoiceloop import dws, ocr
        import os

        os.environ["INVOICELOOP_CORPUS"] = str(ws)
        try:
            answers = dws.load_vision_answers()
            assert answers["kimi-k3"][(DOC, "total_gross")]["value"] == "100.00"
        finally:
            del os.environ["INVOICELOOP_CORPUS"]

    def test_missing_key_is_typed_unavailable(self, ws, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        monkeypatch.setattr("invoiceloop.vision_ingest.VISION_ENV",
                            ws / "no-such-file.env")
        with pytest.raises(SystemExit, match="ANTHROPIC"):
            cmd_vision(ws)

    def test_failed_doc_is_recorded_not_fatal(self, ws):
        def boom(url, **kw):
            raise RuntimeError("connection reset")

        summary = cmd_vision(ws, api_key="k", _post=boom)
        assert summary["read"] == 0 and len(summary["failed"]) == 1

    def test_prompt_keeps_the_five_disciplines(self, ws):
        post, calls = _post_with("total_gross\t1\tT\t")
        cmd_vision(ws, api_key="k", _post=post)
        prompt = calls[0]["json"]["messages"][0]["content"][-1]["text"]
        for needle in ("抄,不要算,不要推", "ABSTAIN", "不要联网检索",
                       "printed_label", "合计"):
            assert needle in prompt
        assert "1 页" in prompt
