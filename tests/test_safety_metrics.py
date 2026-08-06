"""safety_metrics 与 loop_generalization / promote Gate 2 同口径。"""

from __future__ import annotations

from invoiceloop.safety_metrics import (
    annotations_available,
    score_routes,
    score_slot,
    write_annotation_stub,
)


def test_score_slot_silent_absent_and_wrong():
    assert score_slot(
        route="auto_absent", field="seller_vat_id",
        truth_value="DE123", understand_value=None,
    )["silent_absent"] is True
    assert score_slot(
        route="auto_absent", field="seller_vat_id",
        truth_value=None, understand_value=None,
    )["silent_absent"] is False
    flags = score_slot(
        route="auto_accept", field="total_gross",
        truth_value="100.00", understand_value="99.00",
    )
    assert flags["silent_wrong"] is True and flags["value_hit"] is True
    flags_ok = score_slot(
        route="auto_accept", field="total_gross",
        truth_value="$100.00", understand_value="100.00",
    )
    assert flags_ok["silent_wrong"] is False


def test_score_routes_aggregates(tmp_path, monkeypatch):
    from tests.conftest import pin_corpus

    write_annotation_stub(tmp_path, "d1", {"total_gross": "100.00"})
    pin_corpus(monkeypatch, tmp_path)
    routes = [
        {"doc_id": "d1", "field": "total_gross", "route": "auto_accept"},
        {"doc_id": "d1", "field": "seller_vat_id", "route": "auto_absent"},
    ]
    counts = score_routes(
        routes,
        understand_of=lambda _d: {"total_gross": "100.00"},
    )
    assert counts["silent_wrong"] == 0
    assert counts["silent_absent"] == 0  # seller_vat_id 无真值
    assert annotations_available(["d1"]) is True
    assert annotations_available(["missing-doc"]) is False
