"""不可变 run:非空目录永拒(字节不变)、workspace 代数、同指纹重放。

对应不变量 3/4:不提供 --force,不要求删除历史;输入未变 → 重放既有 run,
输入变化或 --new-run → 新 run-NNNN,旧 run 永远原样保留。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from invoiceloop import ocr
from invoiceloop.pipeline import RunExistsError, run
from tests.conftest import pin_corpus
from invoiceloop.snapshot import (
    allocate_run_dir,
    build_input_manifest,
    find_run_by_fingerprint,
)

DOC = "acme-001"


def _ocr_payload() -> dict:
    words = [
        ("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30), ("Gross", 0.40),
    ]
    return {"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in words
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
def workspace(tmp_path, monkeypatch):
    """产品路径的最小 workspace:手写 OCR(不依赖 poppler)+ 假存盘响应。"""
    ws = tmp_path / "ws"
    (ws / "input" / "pdfs").mkdir(parents=True)
    (ws / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (ws / "ocr").mkdir()
    (ws / "ocr" / f"{DOC}.json").write_text(
        json.dumps(_ocr_payload()), encoding="utf-8")
    (ws / "raw").mkdir()
    for mode in ("understand", "agentic"):
        (ws / "raw" / f"{DOC}.{mode}.json").write_text(
            json.dumps(_record(DOC, mode)), encoding="utf-8")
    pin_corpus(monkeypatch, ws)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield ws
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class TestRefuseOverwrite:
    def test_nonempty_out_dir_is_refused_and_untouched(self, workspace):
        out = workspace / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        before = _tree_bytes(out)
        with pytest.raises(RunExistsError, match="不可变"):
            run([DOC], out, include_vision=False, out_of_calibration=True)
        assert _tree_bytes(out) == before, "被拒的重跑不许改动旧 run 的任何一个字节"

    def test_no_force_flag_exists(self):
        import inspect

        from invoiceloop import __main__

        src = inspect.getsource(__main__)
        assert "--force" not in src, "不变量 3:不提供 --force"
        assert "add_argument" in src  # 确认读到的是真源码


class TestIdentityArtifacts:
    def test_input_manifest_and_snapshot_are_deterministic(self, workspace):
        a = run([DOC], workspace / "runs" / "run-0001",
                include_vision=False, out_of_calibration=True)
        b = run([DOC], workspace / "elsewhere" / "run-0001",
                include_vision=False, out_of_calibration=True)
        for key in ("input_manifest", "review_snapshot"):
            assert a[key].read_bytes() == b[key].read_bytes()
        snap = json.loads(a["review_snapshot"].read_text())
        assert set(snap["components"]) >= {"field_ledger.json", "gate_report.json"}
        assert all(v for v in snap["components"].values()), "成分齐时不许有 null"

    def test_fingerprint_changes_with_input(self, workspace):
        fp1 = build_input_manifest([DOC])["fingerprint"]
        (workspace / "raw" / f"{DOC}.understand.json").write_text(
            json.dumps({**_record(DOC, "understand"), "credits": "15"}))
        fp2 = build_input_manifest([DOC])["fingerprint"]
        assert fp1 != fp2, "输入变了指纹必须变 —— 这是开新 run 的依据"

    def test_fingerprint_covers_vision_answers_only_when_consumed(self, workspace):
        vision = workspace / "vision"
        fp_before = build_input_manifest([DOC], include_vision=True)["fingerprint"]
        vision.mkdir()
        (vision / "answers6.A.tsv").write_text(
            "doc\tfield\tvalue\nacme-001\ttotal_gross\t100.00\n", encoding="utf-8")
        fp_after = build_input_manifest([DOC], include_vision=True)["fingerprint"]
        assert fp_before != fp_after, "读图作答进草稿,必须进指纹,否则重放会返回旧 run"
        fp_nv1 = build_input_manifest([DOC], include_vision=False)["fingerprint"]
        (vision / "answers6.A.tsv").write_text("doc\tfield\tvalue\nx\ty\tz\n",
                                               encoding="utf-8")
        fp_nv2 = build_input_manifest([DOC], include_vision=False)["fingerprint"]
        assert fp_nv1 == fp_nv2, "--no-vision 的 run 不消费读图,指纹不含"


class TestWorkspaceGenerations:
    def _cli(self, monkeypatch, capsys, *argv: str) -> dict:
        from invoiceloop.__main__ import main

        monkeypatch.setattr(sys, "argv", ["invoiceloop", *argv])
        main()
        return json.loads(capsys.readouterr().out)

    def test_allocate_replay_and_new_run(self, workspace, monkeypatch, capsys):
        out1 = self._cli(monkeypatch, capsys, "run", "--workspace", str(workspace),
                         "--no-vision")
        assert Path(out1["run_dir"]).name == "run-0001"

        out2 = self._cli(monkeypatch, capsys, "run", "--workspace", str(workspace),
                         "--no-vision")
        assert out2["replayed"] is True and out2["run_dir"].endswith("run-0001")
        assert not (workspace / "runs" / "run-0002").exists(), "同输入必须重放"

        out3 = self._cli(monkeypatch, capsys, "run", "--workspace", str(workspace),
                         "--no-vision", "--new-run")
        assert Path(out3["run_dir"]).name == "run-0002"
        current = json.loads((workspace / "runs" / "current.json").read_text())
        assert current == {"run": "run-0002"}
        # 旧 run 原样保留,新旧账本各自独立
        assert (workspace / "runs" / "run-0001" / "field_ledger.json").exists()
        assert (workspace / "runs" / "run-0002" / "field_ledger.json").exists()

    def test_allocate_skips_existing(self, tmp_path):
        runs = tmp_path / "runs"
        (runs / "run-0001").mkdir(parents=True)
        (runs / "run-0003").mkdir()
        assert allocate_run_dir(runs).name == "run-0004"

    def test_find_by_fingerprint(self, workspace):
        manifest = build_input_manifest([DOC])
        runs = workspace / "runs"
        (runs / "run-0001").mkdir(parents=True)
        (runs / "run-0001" / "input_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        assert find_run_by_fingerprint(runs, manifest["execution_fingerprint"]) is None, \
            "没有 event_log 的半拉子 run(跑到一半崩了)不许被重放"
        (runs / "run-0001" / "event_log.jsonl").write_text("", encoding="utf-8")
        assert find_run_by_fingerprint(runs, manifest["execution_fingerprint"]) is not None
        assert find_run_by_fingerprint(runs, "0" * 64) is None

    def test_find_by_fingerprint_rejects_changed_snapshot_component(self, workspace):
        out = workspace / "runs" / "run-0001"
        run([DOC], out, include_vision=False, out_of_calibration=True)
        manifest = json.loads((out / "input_manifest.json").read_text())
        assert find_run_by_fingerprint(
            workspace / "runs", manifest["execution_fingerprint"]
        ) == out

        (out / "gate_report.json").write_text(json.dumps({"findings": []}))
        assert find_run_by_fingerprint(
            workspace / "runs", manifest["execution_fingerprint"]
        ) is None, "同输入但快照成分被改过时不得重放"

    def test_docs_slice_precedes_fingerprint(self, workspace, monkeypatch, capsys):
        """--docs 1 的 run 不许被当成「全部文档」的 run 重放(指纹必须在截断后算)。"""
        doc2 = "acme-002"
        (workspace / "input" / "pdfs" / f"{doc2}.pdf").write_bytes(b"%PDF-1.4 fake2")
        (workspace / "ocr" / f"{doc2}.json").write_text(
            json.dumps(_ocr_payload()), encoding="utf-8")
        for mode in ("understand", "agentic"):
            (workspace / "raw" / f"{doc2}.{mode}.json").write_text(
                json.dumps(_record(doc2, mode)), encoding="utf-8")
        out1 = self._cli(monkeypatch, capsys, "run", "--workspace", str(workspace),
                         "--no-vision", "--docs", "1")
        assert Path(out1["run_dir"]).name == "run-0001"
        out2 = self._cli(monkeypatch, capsys, "run", "--workspace", str(workspace),
                         "--no-vision")
        assert "replayed" not in out2, "全部 2 份 ≠ 前 1 份 —— 不许重放"
        assert Path(out2["run_dir"]).name == "run-0002"
        m = json.loads((Path(out2["run_dir"]) / "run_manifest.json").read_text())
        assert m["n_docs"] == 2
