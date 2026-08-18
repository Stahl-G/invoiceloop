"""Caliber / amount-triad suggestions and the HITL-narrow doc list."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from invoiceloop.amount_triad import suggest_amount_triad
from invoiceloop.party_caliber import suggest_party_names
from invoiceloop.release_profile import PAYMENT_REQUIRED_V1, parse_release_profile
from invoiceloop.review_budget import budget_state, working_seconds


def _ocr(*lines):
    return {
        "pages": [{
            "page_idx": 0,
            "blocks": [{
                "lines": [
                    {"words": [{"value": value, "geometry": [[0, 0], [1, 1]]}
                               for value in line.split()]}
                    for line in lines
                ]
            }],
        }]
    }


def test_buyer_keeps_attn_drops_street():
    out = suggest_party_names(_ocr(
        "Bill To:",
        "Buying Time Inc.",
        "Attn: Jane Pasheluk",
        "1655 Palm Beach Lakes Blvd",
        "West Palm Beach FL 33401",
    ))
    assert out["buyer_name"]["value"] == "Buying Time Inc. Attn: Jane Pasheluk"


def test_seller_takes_station_not_agency():
    out = suggest_party_names(_ocr(
        "Station:",
        "WXYZ-TV",
        "Remit To:",
        "Some Agency LLC",
    ))
    # two seller labels → abstain rather than pick
    assert "seller_name" not in out


def test_single_station_label():
    out = suggest_party_names(_ocr(
        "Station:",
        "WXYZ-TV",
        "123 Broadcast Drive",
    ))
    assert out["seller_name"]["value"] == "WXYZ-TV"


def test_triad_does_not_put_commission_in_due():
    out = suggest_amount_triad(_ocr(
        "Gross Billings $1,000.00",
        "Agency Commission $150.00",
        "Net Due $850.00",
    ))
    assert out["total_gross"]["value"] == "$1,000.00"
    assert out["amount_due"]["value"] == "$850.00"
    assert "_commission" not in out


def test_triad_does_not_borrow_a_labelled_next_line():
    out = suggest_amount_triad(_ocr(
        "Gross Billings",
        "Agency Commission $150.00",
        "Net Due $850.00",
    ))
    assert "total_gross" not in out
    assert out["amount_due"]["value"] == "$850.00"


def test_triad_borrows_unlabelled_continuation():
    out = suggest_amount_triad(_ocr(
        "Gross Billings",
        "$1,000.00",
        "Net Due $850.00",
    ))
    assert out["total_gross"]["value"] == "$1,000.00"
    assert out["amount_due"]["value"] == "$850.00"


def test_ambiguous_two_gross_labels_abstain():
    out = suggest_amount_triad(_ocr(
        "Gross Billings $1,000.00",
        "Gross $2,000.00",
    ))
    assert "total_gross" not in out


def test_narrow_doc_list_sha_and_exclusions():
    repo = Path(__file__).resolve().parent.parent
    spec = json.loads((repo / "docs" / "hitl_narrow_doc_list.json").read_text())
    joined = "\n".join(spec["doc_ids"])
    assert hashlib.sha256(joined.encode()).hexdigest() == spec["doc_ids_sha256"]
    r1 = set(json.loads((repo / "docs" / "hitl_r1_doc_list.json").read_text())["doc_ids"])
    s4 = set(json.loads((repo / "docs" / "sealed4_doc_list.json").read_text())["doc_ids"])
    ids = set(spec["doc_ids"])
    assert not ids & r1
    assert not ids & s4
    assert spec["n"] == 20 == len(spec["doc_ids"])


def test_har0023_is_payment_profile_not_census():
    repo = Path(__file__).resolve().parent.parent
    pol = json.loads((repo / "docs" / "evidence" / "narrow_v1_2026-08-14"
                      / "HAR-0023.routing_policy.json").read_text())
    profile = parse_release_profile(pol)
    assert profile["id"] == "payment_required_v1"
    assert profile["fields"] == set(PAYMENT_REQUIRED_V1)
    assert pol["release_tier1_explicit"] is False
    assert pol["harness_id"] == "HAR-0023"


def test_budget_exhausts_on_working_gaps(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "review_budget.json").write_text(json.dumps({"cap_minutes": 1}))
    run = tmp_path / "run"
    run.mkdir()
    ledger = [
        {"decided_at": "2026-08-14T00:00:00+00:00", "field": "a"},
        {"decided_at": "2026-08-14T00:00:50+00:00", "field": "b"},
        {"decided_at": "2026-08-14T00:01:10+00:00", "field": "c"},
    ]
    (run / "adjudication_ledger.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in ledger))
    assert working_seconds(ledger) == 70
    state = budget_state(ws, run)
    assert state["exhausted"] is True
    assert state["elapsed_seconds"] == 70


def test_release_walk_orders_weakest_doc_first():
    from invoiceloop.workbench import Workbench

    rows = [
        {"doc_id": "b", "field": "amount_due", "support_strength": "corroborated"},
        {"doc_id": "a", "field": "seller_name", "support_strength": "unsupported"},
        {"doc_id": "a", "field": "amount_due", "support_strength": "corroborated"},
        {"doc_id": "b", "field": "invoice_number", "support_strength": "single_source"},
    ]
    out = Workbench._order_release_walk(rows)
    assert [r["doc_id"] for r in out] == ["a", "a", "b", "b"]
    assert [r["field"] for r in out if r["doc_id"] == "a"] == [
        "seller_name", "amount_due",
    ]
    assert [r["field"] for r in out if r["doc_id"] == "b"] == [
        "invoice_number", "amount_due",
    ]
    assert Workbench._order_release_walk([]) == []


def test_write_round_status_preserves_terminated(tmp_path):
    from invoiceloop.round_status import load_round_status, write_round_status

    ws = tmp_path / "ws"
    ws.mkdir()
    first = write_round_status(ws, {"round": "hitl-narrow", "status": "terminated"})
    assert first == "written"
    again = write_round_status(ws, {"round": "hitl-narrow", "status": "live"})
    assert again == "preserved_terminated"
    assert load_round_status(ws)["status"] == "terminated"


def test_narrow_setup_does_not_inject_derived_into_due_date(tmp_path):
    import importlib.util

    repo = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "hitl_narrow_setup", repo / "scripts" / "hitl_narrow_setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ws = tmp_path / "ws"
    (ws / "ocr").mkdir(parents=True)
    doc = "doc-a"
    (ws / "ocr" / f"{doc}.json").write_text(json.dumps(_ocr(
        "Invoice Date: July 1, 2026", "Payment Terms: Net 30",
        "Gross Billings $1,000.00", "Net Due $850.00",
    )))
    rows = mod._suggestion_rows(ws, [doc])
    assert "derived" not in rows
    assert all(r["field"] != "due_date"
               for bucket in rows.values() for r in bucket)
