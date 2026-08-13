"""scripts/hitl_preread_api.py 纯函数部分:队列槽抽取与建议行映射。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from hitl_preread_api import (  # noqa: E402
    exit_status, queue_slots, to_suggestion_rows,
)


def _write_matrix(tmp_path: Path, rows: list[dict]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "support_matrix.json").write_text(
        json.dumps({"rows": rows, "summary": {}}))
    return run_dir


def test_queue_slots_only_human_queue(tmp_path):
    run_dir = _write_matrix(tmp_path, [
        {"doc_id": "a", "field": "total_gross", "in_human_queue": True},
        {"doc_id": "a", "field": "due_date", "in_human_queue": True},
        {"doc_id": "a", "field": "buyer_name", "in_human_queue": False},
        {"doc_id": "b", "field": "issue_date", "in_human_queue": True},
    ])
    assert queue_slots(run_dir) == {
        "a": {"total_gross", "due_date"}, "b": {"issue_date"}}


def test_to_suggestion_rows_filters_to_queue_fields():
    parsed = [
        ["a", "total_gross", "1,234.56", "Gross:", ""],
        ["a", "buyer_name", "ACME", "TO:", ""],  # 不在队列字段里
    ]
    rows = to_suggestion_rows(parsed, {"total_gross"})
    assert rows == [{"doc_id": "a", "field": "total_gross",
                     "value": "1,234.56", "printed_label": "Gross:",
                     "note": ""}]


def test_to_suggestion_rows_abstain_becomes_empty():
    parsed = [["a", "due_date", "ABSTAIN", "NONE", "只印条款"]]
    rows = to_suggestion_rows(parsed, {"due_date"})
    assert rows[0]["value"] == ""
    assert rows[0]["note"] == "只印条款"


def test_to_suggestion_rows_empty_label_defaults_none():
    parsed = [["a", "seller_vat_id", "", "", ""]]
    rows = to_suggestion_rows(parsed, {"seller_vat_id"})
    assert rows[0]["printed_label"] == "NONE"


def test_any_doc_failure_is_nonzero_exit():
    assert exit_status([]) == 0
    assert exit_status([{"doc_id": "a", "error": "无整页渲染"}]) == 1
