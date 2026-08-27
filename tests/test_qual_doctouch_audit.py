"""历史资格臂的补充审计必须绑定输入且只允许加指标。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_doctouch_audit  # noqa: E402


def _routes() -> list[dict]:
    return [
        {"doc_id": "d1", "field": "invoice_number", "route": "auto_accept"},
        {"doc_id": "d1", "field": "seller_name", "route": "review"},
        {"doc_id": "d2", "field": "invoice_number", "route": "auto_accept"},
        {"doc_id": "d2", "field": "seller_name", "route": "auto_accept"},
    ]


def test_route_matrix_refuses_missing_extra_or_duplicate_slots():
    qual_doctouch_audit.validate_route_matrix(
        _routes(), ["d1", "d2"], ["invoice_number", "seller_name"])

    with pytest.raises(ValueError, match="重复"):
        qual_doctouch_audit.validate_route_matrix(
            _routes() + [_routes()[0]], ["d1", "d2"],
            ["invoice_number", "seller_name"])
    with pytest.raises(ValueError, match="不完整"):
        qual_doctouch_audit.validate_route_matrix(
            _routes()[:-1], ["d1", "d2"],
            ["invoice_number", "seller_name"])
    with pytest.raises(ValueError, match="名单外"):
        extra = _routes() + [
            {"doc_id": "d3", "field": "invoice_number", "route": "review"},
        ]
        qual_doctouch_audit.validate_route_matrix(
            extra, ["d1", "d2"], ["invoice_number", "seller_name"])


def test_legacy_comparison_allows_new_nested_safety_but_not_changed_numbers():
    old = {"arms": {"D": {"metrics": {"ALL": {
        "docs": 200, "zero_touch_docs": 25, "silent_wrong": 110,
    }}}}}
    new = {"arms": {"D": {"metrics": {"ALL": {
        "docs": 200, "zero_touch_docs": 25, "silent_wrong": 110,
        "zero_touch_release_safety": {"silent_wrong": 12},
    }}}}}
    assert qual_doctouch_audit.legacy_metric_drift(old, new) == []

    new["arms"]["D"]["metrics"]["ALL"]["zero_touch_docs"] = 24
    drift = qual_doctouch_audit.legacy_metric_drift(old, new)
    assert drift == [{
        "path": "arms.D.metrics.ALL.zero_touch_docs",
        "legacy": 25,
        "rescored": 24,
    }]


def test_understand_loader_checks_filename_binding_and_http_status(tmp_path):
    path = tmp_path / "d1.understand.json"
    path.write_text(json.dumps({
        "doc_id": "d1", "mode": "understand", "http_status": 200,
        "body": {"output": {"data": {"invoice_number": "INV-1"}}},
    }), encoding="utf-8")
    assert qual_doctouch_audit.load_understand(path, "d1") == {
        "invoice_number": "INV-1"
    }

    body = json.loads(path.read_text(encoding="utf-8"))
    body["doc_id"] = "d2"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="绑定"):
        qual_doctouch_audit.load_understand(path, "d1")
