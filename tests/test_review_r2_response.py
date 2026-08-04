"""2026-08-04 第二轮双评审(81/100 复审 + 82/100 十二路评审)修复批的回归测试:

- render_pages/render_crop 遇坏 PDF 返回空,不 crash 整批(82 评 P0-3,两路红队复现)
- 合法 JSON 非对象([1,2,3])登记 corrupt,不 AttributeError 崩批(82 评 P1-7)
- CLI 对 RunExistsError 等给干净一句话,不再裸 traceback(双评 P1-2/P1-4)
- verify 深层读取(快照/裁决账本)的 CRC 损坏 → 结构化失败,不裸 traceback(81 评 P1-3)
- 零裁决包的 layers.binding 记 None,不是真空理 True(81 评 P2)
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path

import pytest

from invoiceloop import adjudicate, evidence, ocr

from test_review_response import DOC, ws  # noqa: F401  (复用同形 fixture)


class TestBadPdfRender:
    def test_render_pages_returns_empty_on_garbage_pdf(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"%PDF-1.4 garbage bytes that poppler cannot parse")
        assert evidence.render_pages(bad, tmp_path / "pages") == []

    def test_crops_run_completes_with_corrupt_pdf(self, ws):  # noqa: F811
        """红队 P0-3:以前 --crops 遇坏 PDF 整批崩(check=True 无 try)。"""
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, render_crops=True, include_vision=False, out_of_calibration=True)
        assert (out / "support_matrix.json").exists(), "坏 PDF 不许带崩整批"
        events = [json.loads(line)
                  for line in (out / "event_log.jsonl").read_text().splitlines()]
        if shutil.which("pdftoppm"):
            assert any(e["event"] == "pages_unavailable" and e["doc_id"] == DOC
                       for e in events), "渲染失败要进事件日志,不许静默"

    def test_render_crop_failure_returns_none(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"%PDF-1.4 garbage")
        assert evidence.render_crop(bad, 1, [0.1, 0.1, 0.3, 0.2],
                                    tmp_path / "crop") is None


class TestNonDictJson:
    def test_register_marks_non_object_corrupt(self, ws):  # noqa: F811
        (ws / "raw" / f"{DOC}.agentic.json").write_text("[1, 2, 3]")
        registry = evidence.register_artifacts([DOC])
        agentic = next(e for e in registry if e["mode"] == "agentic")
        assert agentic["corrupt"] is True and agentic["sha256"]

    def test_run_completes_with_non_object_response(self, ws):  # noqa: F811
        from invoiceloop.pipeline import run

        (ws / "raw" / f"{DOC}.agentic.json").write_text("[1, 2, 3]")
        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        report = json.loads((out / "gate_report.json").read_text())
        assert report["evaluations"][DOC]["total_gross"]["cross_mode_agreement"] != "pass"


class TestCliErrorCoverage:
    def test_run_exists_error_is_a_clean_systemexit(self, ws, monkeypatch):  # noqa: F811
        """双评 P1-2/P1-4:RunExistsError 不许再是裸 traceback。"""
        from invoiceloop.__main__ import main

        out = ws / "runs" / "run-0001"
        out.mkdir(parents=True)
        (out / "stale.txt").write_text("x")
        monkeypatch.setattr(sys, "argv", ["invoiceloop", "run", "--out", str(out)])
        with pytest.raises(SystemExit, match="错误"):
            main()


def _flip_member(bundle: Path, member: str) -> None:
    """把 zip 里指定成员的压缩数据末字节翻一下 —— 制造 CRC 级损坏。

    用 ZipInfo.header_offset 定位,不在字节流里搜文件名(成员内容里可能
    也含这个名字,会搜错位置)。"""
    with zipfile.ZipFile(bundle) as zf:
        info = zf.getinfo(member)
    assert info.compress_size > 0, f"{member} 是空成员,无数据可翻"
    data = bytearray(bundle.read_bytes())
    offset = info.header_offset
    assert data[offset:offset + 4] == b"PK\x03\x04"
    name_len, extra_len = struct.unpack_from("<HH", data, offset + 26)
    # 翻压缩数据的第一个字节:翻末字节可能只动到 deflate 尾部 padding,
    # 解压结果不变,CRC 照过,测试白做
    data[offset + 30 + name_len + extra_len] ^= 0xFF
    bundle.write_bytes(bytes(data))


class TestVerifyDeepReads:
    """81 评 P1-3:verify 是交付信任的工具,腐化包必须永远得到结构化 report。"""

    def _bundle(self, ws):  # noqa: F811
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        return adjudicate.build_audit_bundle(out)

    def test_snapshot_member_crc_corruption_is_structured(self, ws):  # noqa: F811
        bundle = self._bundle(ws)
        _flip_member(bundle, "review_snapshot.json")
        report = adjudicate.verify_bundle(bundle)
        assert not report["ok"]
        assert report["layers"]["snapshot"] is False
        assert any("review_snapshot" in f for f in report["failures"])

    def test_ledger_member_crc_corruption_is_structured(self, ws):  # noqa: F811
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        # 空账本(0 字节)没有压缩数据可损坏 —— 先写一条真裁决
        adjudicate.append_adjudication(
            out, claim_id=None, doc_id=DOC, field="total_gross",
            decision="abstain", rationale="r", adjudicator="t",
            decided_at="2026-08-04T00:00:00")
        bundle = adjudicate.build_audit_bundle(out)
        _flip_member(bundle, "adjudication_ledger.jsonl")
        report = adjudicate.verify_bundle(bundle)
        assert not report["ok"]
        assert report["layers"]["binding"] is False
        assert any("adjudication_ledger" in f for f in report["failures"])

    def test_empty_ledger_binding_is_none_not_vacuous_true(self, ws):  # noqa: F811
        """零裁决的包:绑定层记 None(无可绑定对象),不是真空理 True。"""
        bundle = self._bundle(ws)
        report = adjudicate.verify_bundle(bundle)
        assert report["ok"], report["failures"]
        assert report["layers"]["binding"] is None
        assert report["layers"]["snapshot"] is True
        assert any("无裁决可绑定" in n for n in report["notes"])


class TestIngestHonesty:
    """82 评 P1-6/7/8:ingest 的静默丢单与谎报。"""

    def test_uppercase_pdf_extension_is_discovered(self, tmp_path):
        from invoiceloop.ingest import discover

        pdfs = tmp_path / "input" / "pdfs"
        pdfs.mkdir(parents=True)
        (pdfs / "lower.pdf").write_bytes(b"%PDF-1.4 a")
        (pdfs / "UPPER.PDF").write_bytes(b"%PDF-1.4 b")
        (pdfs / "mixed.Pdf").write_bytes(b"%PDF-1.4 c")
        (pdfs / "notapdf.txt").write_text("x")
        docs = discover(tmp_path)
        assert len(docs) == 3, \
            ".PDF/.Pdf 不许被静默丢掉 —— 那正是宪章四要防的静默丢单(82 评 P1-6)"

    def test_resume_skips_non_object_raw_without_crashing(self, ws, capsys):  # noqa: F811
        """合法 JSON 非对象([1,2,3])的存盘:不许 .get 崩批,当作没抽过重试。"""
        import invoiceloop.ingest as ingest_mod

        (ws / "raw" / f"{DOC}.understand.json").write_text("[1, 2, 3]")

        def _fake_extract(pdf, schema, raw_dir, *, doc_id, mode):
            target = raw_dir / f"{doc_id}.{mode}.json"
            target.write_text(json.dumps({"http_status": 200, "body": {}}))
            return {"http_status": 200}

        import invoiceloop.dws_client as client
        orig = client.extract_to_raw
        client.extract_to_raw = _fake_extract
        try:
            summary = ingest_mod.cmd_ingest(ws, do_ocr=False)
        finally:
            client.extract_to_raw = orig
        assert summary["extract_failed"] == []

    def test_non_200_extraction_is_not_counted_as_success(self, ws):  # noqa: F811
        """拿错 key(401):存盘照留(被拒证据),但摘要不许说「全部成功」。"""
        import invoiceloop.dws_client as client
        import invoiceloop.ingest as ingest_mod

        for stale in (ws / "raw").glob("*.json"):  # 清掉 fixture 的 200 存盘,逼出真抽
            stale.unlink()

        def _fake_extract(pdf, schema, raw_dir, *, doc_id, mode):
            target = raw_dir / f"{doc_id}.{mode}.json"
            target.write_text(json.dumps(
                {"http_status": 401, "body": {"error": "bad key"}}))
            return {"http_status": 401, "body": {"error": "bad key"}}

        orig = client.extract_to_raw
        client.extract_to_raw = _fake_extract
        try:
            summary = ingest_mod.cmd_ingest(ws, do_ocr=False)
        finally:
            client.extract_to_raw = orig
        assert summary["extracted"] == 0, "401 不许计入 extracted(82 评 P1-8)"
        assert len(summary["extract_failed"]) == 2
        assert all("401" in f["error"] for f in summary["extract_failed"])


class TestVisionTsvRobustness:
    def test_malformed_tsv_rows_are_skipped(self, ws, monkeypatch):  # noqa: F811
        from invoiceloop import dws

        (ws / "vision").mkdir(exist_ok=True)
        (ws / "vision" / "answers6.A.tsv").write_text(
            "doc\tfield\tvalue\tprinted_label\tnote\n"
            f"{DOC}\ttotal_gross\t100.00\tTotal\t\n"
            "only-one-column\n"
            "\t\t\n"
            f"{DOC}\ttotal_net\t10.00\tNet\t\n", encoding="utf-8")
        answers = dws.load_vision_answers()
        rows = answers[dws.VISION_READERS["A"]]
        assert (DOC, "total_gross") in rows and (DOC, "total_net") in rows
        assert len(rows) == 2, "畸形行跳过,不许 IndexError 崩掉整个 run(82 评 P1-7)"


class TestEnvShadowing:
    """81 评 P1-1:评委照 README export INVOICELOOP_CORPUS 后,产品路径不许被遮蔽。"""

    def test_bundle_ignores_ambient_corpus_env(self, ws, monkeypatch):  # noqa: F811
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        # 评委环境:主变量指向别处 —— bundle 必须仍按 run 时记录的根解析
        monkeypatch.setenv("INVOICELOOP_CORPUS", "/nonexistent/judge-corpus")
        bundle = adjudicate.build_audit_bundle(out)
        report = adjudicate.verify_bundle(bundle)
        assert report["ok"], report["failures"]


class TestDecidedAtValidation:
    def test_garbage_timestamp_rejected(self, ws):  # noqa: F811
        from invoiceloop.pipeline import run

        out = ws / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        with pytest.raises(ValueError, match="ISO 8601"):
            adjudicate.append_adjudication(
                out, claim_id=None, doc_id=DOC, field="total_gross",
                decision="abstain", rationale="r", adjudicator="t",
                decided_at="下礼拜吧")
        entry = adjudicate.append_adjudication(
            out, claim_id=None, doc_id=DOC, field="total_gross",
            decision="abstain", rationale="r", adjudicator="t",
            decided_at="2026-08-04T12:00:00Z")
        assert entry["decision_id"] == "HD-0001", "合法时间照常入账"
        assert (out / "adjudication_ledger.lock").exists(), \
            "跨进程 flock 的锁文件必须存在(82 评 P2:仅进程内锁不够)"


class TestRunDirClaim:
    def test_concurrent_runs_exactly_one_wins(self, ws):  # noqa: F811
        """81 评 P2 TOCTOU:两个进程抢同一 out 目录,输家拿 RunExistsError,
        不是 FileExistsError 裸奔,更不是交错写出半成品。"""
        import threading

        from invoiceloop.pipeline import RunExistsError, run

        out = ws / "runs" / "run-0001"
        barrier = threading.Barrier(2)
        results: list[str] = []

        def racer():
            barrier.wait()
            try:
                run([DOC], out, include_vision=False, out_of_calibration=True)
                results.append("ok")
            except RunExistsError:
                results.append("refused")

        threads = [threading.Thread(target=racer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == ["ok", "refused"]
