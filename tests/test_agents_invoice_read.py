"""Document-level ADK invoice reading: advice only, never the ledger."""

from __future__ import annotations

import json

import pytest

from invoiceloop.agents.invoice_read import (
    InvoiceReading,
    reading_call_id,
    to_suggestion_rows,
)


def test_schema_carries_no_identifiers():
    fields = set(InvoiceReading.model_fields)
    for banned in ("decision_id", "seq", "claim_id", "doc_id", "field",
                   "feedback_id", "review_snapshot_id"):
        assert banned not in fields


def test_katz_style_page_maps_station_to_seller_agency_to_buyer():
    reading = InvoiceReading(
        station_or_publication="Desert Mountain Broadcasting",
        agency="KATZ MEDIA GROUP",
        advertiser="House Freedom Action",
        legal_seller="Desert Mountain Broadcasting",
        remittance_name="KATZ MEDIA GROUP",
        remittance_role="customer_stub",
        seller_name="Desert Mountain Broadcasting",
        buyer_name="KATZ MEDIA GROUP",
        invoice_number="IN-200033454",
        amount_due="$884.00",
        rationale="Station letterhead vs agency bill-to; remit stub repeats customer.",
        confidence="high",
    )
    rows = to_suggestion_rows("5c1c7960", reading, model="gemini-3.7-flash")
    by_field = {r["field"]: r for r in rows}
    assert by_field["seller_name"]["value"] == "Desert Mountain Broadcasting"
    assert by_field["buyer_name"]["value"] == "KATZ MEDIA GROUP"
    assert by_field["amount_due"]["value"] == "$884.00"
    assert "gemini-3.7-flash" in by_field["seller_name"]["note"]
    assert "\t" not in by_field["seller_name"]["note"]
    assert "\n" not in by_field["seller_name"]["note"]


def test_empty_fields_are_not_injected():
    reading = InvoiceReading(
        station_or_publication="WUGO FM 99.7",
        remittance_role="absent",
        seller_name="WUGO FM 99.7",
        rationale="Continued page; no printed amount due.",
        confidence="medium",
    )
    rows = to_suggestion_rows("31f273ad", reading, model="gemini-3.7-flash")
    fields = {r["field"] for r in rows}
    assert fields == {"seller_name"}
    assert all(r["value"] for r in rows)


def test_seller_falls_back_to_station_when_seller_name_blank():
    reading = InvoiceReading(
        station_or_publication="KMBM-FM",
        remittance_role="unknown",
        rationale="Call letters on the station line.",
        confidence="medium",
    )
    rows = to_suggestion_rows("doc-a", reading, model="m")
    assert rows[0]["field"] == "seller_name"
    assert rows[0]["value"] == "KMBM-FM"


def test_images_enter_the_call_id():
    a = reading_call_id("m", "doc-a", [b"page-1"])
    b = reading_call_id("m", "doc-a", [b"page-2"])
    assert a != b
    assert reading_call_id("m", "doc-a", [b"page-1"]) == a


def test_workbench_renders_the_reading_card():
    from invoiceloop.workbench import Workbench

    html = Workbench._invoice_read_card("zh", {
        "station_or_publication": "Desert Mountain Broadcasting",
        "agency": "KATZ MEDIA GROUP",
        "remittance_role": "customer_stub",
        "seller_name": "Desert Mountain Broadcasting",
        "rationale": "Agency is not the seller.",
        "confidence": "high",
        "model": "gemini-3.7-flash",
    })
    assert "wb-invoice-read" in html
    assert "Desert Mountain Broadcasting" in html
    assert "KATZ MEDIA GROUP" in html
    assert "建议" in html


def test_scripted_adk_reader_returns_structured_reading(tmp_path, monkeypatch):
    pytest.importorskip("google.adk", reason="需要 invoiceloop[gemini]")
    from tests.test_agents_adk_pipeline import ScriptedLlm
    from invoiceloop.agents.invoice_read import make_invoice_reader

    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    payload = {
        "station_or_publication": "WUGO FM 99.7",
        "agency": "",
        "advertiser": "BLUE SKY COMMUNICATIONS",
        "legal_seller": "CARTER CO. BRDCSTNG CO, INC",
        "remittance_name": "",
        "remittance_role": "absent",
        "seller_name": "WUGO FM 99.7",
        "buyer_name": "BLUE SKY COMMUNICATIONS",
        "invoice_number": "713-084609",
        "amount_due": "",
        "rationale": "Continued sheet; totals not printed.",
        "confidence": "medium",
    }
    llm = ScriptedLlm(model="scripted", script=[json.dumps(payload)])
    read = make_invoice_reader(model=llm, workspace=tmp_path)
    out = read("31f273ad", [b"\x89PNG"])
    assert out.seller_name == "WUGO FM 99.7"
    assert out.amount_due == ""
    assert "decision_id" not in out.model_dump()
