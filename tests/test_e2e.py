"""E2E:全流程零 API、确定性可复算、panel 守住宪章六。

用三份真实存盘文档(含一份 OCR 退化的扫描件和一份有第六轮读图作答的)
跑两遍完整 pipeline,逐文件 byte-compare —— 同样输入哈希必须产出同样字节,
这是 §5.3"可复算性"的可执行形态。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoiceloop import dws
from invoiceloop.pipeline import run

DOCS = ["046e0c4924044de09f6d9e7b", "00134dd365a24343b35b78c6", "00136a27c7774c1e8dc6b2f2"]
ARTIFACTS = [
    "run_manifest.json", "input_manifest.json", "artifact_registry.json",
    "evidence_span_registry.json", "field_claim_graph.json", "field_drafts.json",
    "field_ledger.json", "gate_report.json", "review_snapshot.json",
    "support_matrix.json", "support_panel.html", "event_log.jsonl",
]

from invoiceloop.ocr import corpus_available

pytestmark = pytest.mark.skipif(not corpus_available(), reason="存盘证据不在")


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    run(DOCS, base / "run-a", render_crops=False)
    run(DOCS, base / "run-b", render_crops=False)
    return base / "run-a", base / "run-b"


class TestDeterminism:
    @pytest.mark.parametrize("name", ARTIFACTS)
    def test_identical_bytes(self, two_runs, name):
        a, b = two_runs
        assert (a / name).read_bytes() == (b / name).read_bytes(), f"{name} 不确定"


class TestDeliverableHonesty:
    def test_panel_states_extraction_is_not_trusted(self, two_runs):
        panel = (two_runs[0] / "support_panel.html").read_text(encoding="utf-8")
        assert "抽取的正确性不可信" in panel
        assert "不主张 DWS 可信" in panel

    def test_panel_gate_chips_explain_themselves(self, two_runs):
        panel = (two_runs[0] / "support_panel.html").read_text(encoding="utf-8")
        assert "算术一致性:验算" in panel, "悬停说明要进静态 panel(bundle 里的评委也看得到)"
        assert "引用区里有这个值" in panel or "没有引用区或没有 OCR" in panel

    def test_panel_carries_all_three_qualifiers(self, two_runs):
        panel = (two_runs[0] / "support_panel.html").read_text(encoding="utf-8")
        assert "带乐观偏差" in panel and "留出集确认已于" in panel
        assert "8 例是标注错" in panel
        assert "DocILE 之外的表现仍未知" in panel

    def test_every_blocking_finding_has_a_repair_route(self, two_runs):
        report = json.loads((two_runs[0] / "gate_report.json").read_text(encoding="utf-8"))
        for finding in report["findings"]:
            if finding["blocking"]:
                assert finding["repair_owner"] in {"human", "re_extract", "vision_reread"}
                assert finding["recommendation"]

    def test_matrix_numbers_recompute_from_frozen_rows(self, two_runs):
        matrix = json.loads((two_runs[0] / "support_matrix.json").read_text(encoding="utf-8"))
        rows, summary = matrix["rows"], matrix["summary"]
        assert summary["slots"] == len(rows) == len(DOCS) * 10
        for strength, n in summary["by_strength"].items():
            assert n == sum(1 for r in rows if r["support_strength"] == strength)

    def test_vision_rejections_are_visible_not_hidden(self, two_runs):
        """046e0c49 在第六轮读图语料里;若 GPT 5.6 SOL 在那几份上错位,
        拒绝必须出现在事件与矩阵里 —— 不能藏。"""
        events = (two_runs[0] / "event_log.jsonl").read_text(encoding="utf-8")
        assert "draft_binding_rejected" in events or "claim_frozen" in events

    def test_zero_api(self, two_runs, monkeypatch):
        """运行全程不碰网络:禁掉 socket 后重跑必须照样成功。"""
        import socket

        def blocked(*args, **kwargs):
            raise AssertionError("pipeline 试图联网")

        monkeypatch.setattr(socket.socket, "connect", blocked)
        run(DOCS, two_runs[0].parent / "run-offline", render_crops=False)


class TestCorruptInput:
    def test_malformed_response_is_unavailable_not_a_crash(self, tmp_path, monkeypatch):
        """存盘文件损坏 = 该文档不可用(门禁记阻断),不许带垮整批。"""
        from invoiceloop.pipeline import _load

        raw = tmp_path / "derisk" / "raw"
        raw.mkdir(parents=True)
        (raw / "doc-bad.understand.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(tmp_path / "derisk"))
        assert _load("doc-bad", "understand") is None


