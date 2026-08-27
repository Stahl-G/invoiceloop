"""写集:证明某一趟只动了该动的东西。改了账本却报「干净」是这里唯一要挡的失败。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import writeset  # noqa: E402


def test_a_modified_ledger_shows_up_as_changed(tmp_path):
    """agent 那一趟若碰了 adjudication_ledger.jsonl,P5 必须看得见。"""
    (tmp_path / "vision").mkdir()
    ledger = tmp_path / "adjudication_ledger.jsonl"
    ledger.write_text("{}\n", encoding="utf-8")
    before = writeset.snapshot(tmp_path)
    ledger.write_text("{}\n{}\n", encoding="utf-8")
    (tmp_path / "vision" / "answers6.adk-invoice.tsv").write_text(
        "x\n", encoding="utf-8")
    d = writeset.diff(before, writeset.snapshot(tmp_path))
    assert "adjudication_ledger.jsonl" in d["modified"]
    assert "vision/answers6.adk-invoice.tsv" in d["added"]
    assert [x for x in d["changed"] if not x.startswith("vision/")] == \
        ["adjudication_ledger.jsonl"]


def test_a_deleted_artifact_is_not_silently_clean(tmp_path):
    """只比「现在有什么」会把删除当成没发生。"""
    (tmp_path / "gate_report.json").write_text("{}", encoding="utf-8")
    before = writeset.snapshot(tmp_path)
    (tmp_path / "gate_report.json").unlink()
    assert writeset.diff(before, writeset.snapshot(tmp_path))["removed"] == \
        ["gate_report.json"]
