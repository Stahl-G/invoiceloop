"""资格提取聚合审计：断点续跑后的最终证据必须覆盖全部存盘响应。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_extract_audit  # noqa: E402


def _record(doc_id: str, mode: str, *, status: int = 200, cost: float = 3.5) -> dict:
    return {
        "doc_id": doc_id,
        "mode": mode,
        "http_status": status,
        "body": {"usage": {"data_extraction_credits": {"cost": cost}}},
    }


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "qual"
    (ws / "raw").mkdir(parents=True)
    docs = ["a" * 24, "b" * 24]
    (ws / "doc_list.json").write_text(
        json.dumps({"doc_ids": docs}), encoding="utf-8")
    for doc_id in docs:
        for mode in ("understand", "agentic"):
            (ws / "raw" / f"{doc_id}.{mode}.json").write_text(
                json.dumps(_record(doc_id, mode)), encoding="utf-8")
    return ws


def test_audit_counts_the_complete_raw_tree_not_the_last_invocation(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "extract_summary.json").write_text(json.dumps({
        "done": 1, "skipped": 3, "failed": 0,
        "spent_estimate": 3.5,
    }), encoding="utf-8")

    report = qual_extract_audit.audit(ws)

    assert report["complete"] is True
    assert report["expected_calls"] == 4
    assert report["stored_calls"] == 4
    assert report["http_status_counts"] == {"200": 4}
    assert report["total_credits"] == 14.0
    assert len(report["files"]) == 4
    assert len(report["raw_tree_sha256"]) == 64
    assert report["last_invocation_summary"]["done"] == 1


def test_audit_fails_closed_on_missing_extra_or_misbound_records(tmp_path):
    ws = _workspace(tmp_path)
    missing = ws / "raw" / f"{'a' * 24}.agentic.json"
    missing.unlink()
    extra = ws / "raw" / f"{'c' * 24}.understand.json"
    extra.write_text(json.dumps(_record("c" * 24, "understand")), encoding="utf-8")
    wrong = ws / "raw" / f"{'b' * 24}.agentic.json"
    wrong.write_text(json.dumps(_record("b" * 24, "understand")), encoding="utf-8")

    report = qual_extract_audit.audit(ws)

    assert report["complete"] is False
    assert missing.name in report["missing"]
    assert extra.name in report["extra"]
    assert report["binding_errors"]
    assert report["blocking_reasons"]
