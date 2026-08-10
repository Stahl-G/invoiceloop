"""suggest_inject 的单测:离线建议 → answers6.<tag>.tsv,追加式、可回读。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from invoiceloop.dws import load_vision_answers

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import suggest_inject  # noqa: E402


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "vision").mkdir()
    return tmp_path


ROWS = [
    {"doc_id": "doc-a", "field": "total_gross", "value": "100.00",
     "printed_label": "Total", "note": "derived"},
    {"doc_id": "doc-a", "field": "due_date", "value": "ABSTAIN"},
    {"doc_id": "doc-b", "field": "total_net", "value": "$72,000.00"},
]


class TestInject:
    def test_writes_header_and_rows(self, ws):
        out = suggest_inject.inject(ws, "ta-arm", ROWS)
        assert out["written"] == 3 and out["dropped"] == []
        text = (ws / "vision" / "answers6.ta-arm.tsv").read_text()
        lines = text.splitlines()
        assert lines[0] == "doc\tfield\tvalue\tprinted_label\tnote"
        assert len(lines) == 4
        assert out["reread_rows"] == 3

    def test_round_trip_through_existing_loader(self, ws):
        suggest_inject.inject(ws, "ta-arm", ROWS)
        answers = load_vision_answers(
            vision_dir=ws / "vision")["ta-arm"]
        assert answers[("doc-a", "total_gross")]["value"] == "100.00"
        assert answers[("doc-a", "due_date")]["value"] == "ABSTAIN"
        assert answers[("doc-b", "total_net")]["printed_label"] == ""

    def test_append_only_never_rewrites(self, ws):
        suggest_inject.inject(ws, "ta-arm", ROWS)
        before = (ws / "vision" / "answers6.ta-arm.tsv").read_bytes()
        conflict = [{"doc_id": "doc-a", "field": "total_gross",
                     "value": "999.00"},
                    {"doc_id": "doc-c", "field": "invoice_number",
                     "value": "INV-1"}]
        out = suggest_inject.inject(ws, "ta-arm", conflict)
        assert out["written"] == 1 and out["skipped_existing"] == 1
        after = (ws / "vision" / "answers6.ta-arm.tsv").read_text()
        assert "999.00" not in after, "已作答的槽位永不被注入器改写"
        assert "doc-c\tinvoice_number\tINV-1" in after

    def test_drops_unknown_field_and_bad_value(self, ws):
        bad = [{"doc_id": "doc-a", "field": "not_a_field", "value": "x"},
               {"doc_id": "", "field": "total_gross", "value": "1.00"},
               {"doc_id": "doc-a", "field": "total_gross",
                "value": "1\t00"}]
        out = suggest_inject.inject(ws, "ta-arm", bad)
        assert out["written"] == 0 and len(out["dropped"]) == 3
        assert not (ws / "vision" / "answers6.ta-arm.tsv").exists()

    def test_rejects_unsafe_tag(self, ws):
        with pytest.raises(SystemExit):
            suggest_inject.inject(ws, "../evil", ROWS)

    def test_registered_tag_rereads_under_display_name(self, ws):
        """tag D 已登记为 kimi-k3:回读校验必须走显示名,不能漏。"""
        out = suggest_inject.inject(ws, "D", ROWS[:1])
        assert out["reread_rows"] == 1


class TestCli:
    def test_jsonl_input_and_exit_code_on_drops(self, ws):
        src = ws / "in.jsonl"
        src.write_text("\n".join(json.dumps(r) for r in ROWS) + "\n"
                       + json.dumps({"doc_id": "x", "field": "bad",
                                     "value": "1"}) + "\n")
        proc = subprocess.run(
            [sys.executable, str(Path(suggest_inject.__file__)),
             "--workspace", str(ws), "--tag", "ta-arm",
             "--input", str(src)],
            capture_output=True, text=True)
        assert proc.returncode == 2, "有 dropped 行必须非零退出"
        out = json.loads(proc.stdout)
        assert out["written"] == 3 and len(out["dropped"]) == 1


class TestRunDirMode:
    """run 后模式:展示型建议写 <run>/vision,不碰 workspace(run 前)目录。"""

    def test_run_dir_mode_writes_into_run_only(self, ws):
        run_dir = ws / "runs" / "run-0001"
        run_dir.mkdir(parents=True)
        out = suggest_inject.inject(ws, "derived", ROWS[:1], run_dir=run_dir)
        assert out["written"] == 1
        assert (run_dir / "vision" / "answers6.derived.tsv").exists()
        assert not (ws / "vision" / "answers6.derived.tsv").exists(), \
            "展示型建议不许混进 run 前输入目录(进去就会成草稿、进指纹)"
