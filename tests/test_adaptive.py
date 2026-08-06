"""L1 adaptive:风险诊断、故意跳过 agentic 不阻断、指纹分量。"""

from __future__ import annotations

import json
from pathlib import Path

from invoiceloop import adaptive, gates
from tests.conftest import make_response, pin_corpus


def test_diagnose_risk_tolerates_extra_dws_keys():
    """真实 DWS 响应含 invoice_type/currency 等非受评键 —— 不得 KeyError。"""
    data = {
        "invoice_number": "INV-1", "issue_date": "2024-01-01",
        "due_date": "2024-01-31", "seller_name": "A", "seller_vat_id": "DE1",
        "buyer_name": "B",
        "total_net": "100.00", "total_vat": "20.00",
        "total_gross": "120.00", "amount_due": "120.00",
        # 真实存盘几乎必有的旁路键(2026-08-06 实测 100/100 含 invoice_type)
        "invoice_type": "INVOICE",
        "currency": "USD",
        "seller_country": "US",
        "buyer_country": "US",
    }
    assert adaptive.diagnose_risk(data) == []


def test_diagnose_risk_clean_vs_missing_tier1():
    clean = {
        "invoice_number": "INV-1", "issue_date": "2024-01-01",
        "due_date": "2024-01-31", "seller_name": "A", "seller_vat_id": "DE1",
        "buyer_name": "B",
        "total_net": "100.00", "total_vat": "20.00",
        "total_gross": "120.00", "amount_due": "120.00",
    }
    assert adaptive.diagnose_risk(clean) == []
    risky = dict(clean)
    risky["amount_due"] = None
    reasons = adaptive.diagnose_risk(risky)
    assert any(r.startswith("tier1_missing:amount_due") for r in reasons)


def test_optional_agentic_skip_does_not_block():
    u = make_response("d1", "understand", {
        "invoice_number": "INV-1", "issue_date": "2024-01-01",
        "due_date": "2024-01-31", "seller_name": "A Co",
        "seller_vat_id": "DE123", "buyer_name": "B Co",
        "total_net": "100.00", "total_vat": "20.00",
        "total_gross": "120.00", "amount_due": "120.00",
    })
    report = gates.run_gates(
        ["d1"],
        understand={"d1": u},
        agentic={"d1": None},
        vision_answers={},
        ledger_sha256="0" * 64,
        artifact_digest="0" * 64,
        agentic_optional=frozenset({"d1"}),
    )
    blocking = [f for f in report["findings"] if f["blocking"]]
    assert not any(f["gate_id"] == "cross_mode_agreement" for f in blocking), \
        "adaptive 故意跳过 agentic 不得整文档阻断"
    assert report["evaluations"]["d1"]["amount_due"]["cross_mode_agreement"] \
        == "unavailable"


def test_missing_agentic_still_blocks_by_default():
    u = make_response("d1", "understand", {"invoice_number": "INV-1"})
    report = gates.run_gates(
        ["d1"],
        understand={"d1": u},
        agentic={"d1": None},
        vision_answers={},
        ledger_sha256="0" * 64,
        artifact_digest="0" * 64,
    )
    assert any(
        f["gate_id"] == "cross_mode_agreement" and f["blocking"]
        for f in report["findings"]
    )


def test_adaptive_ingest_escalates_only_risky(tmp_path, monkeypatch):
    from invoiceloop.ingest import cmd_ingest

    pin_corpus(monkeypatch, tmp_path)
    pdf_dir = tmp_path / "input" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "clean.pdf").write_bytes(b"%PDF-1.4 clean")
    (pdf_dir / "risky.pdf").write_bytes(b"%PDF-1.4 risky")

    calls: list[tuple[str, str]] = []

    def fake_extract(pdf, schema, raw_dir, *, doc_id, mode):
        calls.append((doc_id, mode))
        raw_dir = Path(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        if doc_id == "clean":
            data = {
                "invoice_number": "INV-1", "issue_date": "2024-01-01",
                "due_date": "2024-01-31", "seller_name": "A Co",
                "seller_vat_id": "DE123", "buyer_name": "B Co",
                "total_net": "100.00", "total_vat": "20.00",
                "total_gross": "120.00", "amount_due": "120.00",
            }
        else:
            data = {
                "invoice_number": "INV-2", "issue_date": "2024-01-01",
                "due_date": "2024-01-31", "seller_name": "A Co",
                "seller_vat_id": "DE123", "buyer_name": "B Co",
                "total_net": "100.00", "total_vat": "20.00",
                "total_gross": "120.00",
                # amount_due missing → tier1 risk
            }
        record = {
            "doc_id": doc_id, "document": f"{doc_id}.pdf", "mode": mode,
            "http_status": 200,
            "body": {"output": {"data": data, "metadata": {},
                                "pages": [{"page": 1, "width": 1, "height": 1}]}},
        }
        (raw_dir / f"{doc_id}.{mode}.json").write_text(json.dumps(record))
        return record

    monkeypatch.setattr("invoiceloop.dws_client.extract_to_raw", fake_extract)
    monkeypatch.setattr("invoiceloop.ingest.ocr_pdf",
                        lambda _p: {"pages": []})

    summary = cmd_ingest(tmp_path, adaptive=True, do_ocr=True, do_extract=True)
    assert summary["adaptive"] is True
    assert summary["escalated"] == 1
    assert summary["skipped_clean"] == 1
    assert ("clean", "understand") in calls
    assert ("clean", "agentic") not in calls
    assert ("risky", "understand") in calls
    assert ("risky", "agentic") in calls
    assert (tmp_path / "adaptive.json").exists()
    clean_m = json.loads(
        (tmp_path / "attempts" / "clean" / "manifest.json").read_text())
    assert clean_m["escalated"] is False
    risky_m = json.loads(
        (tmp_path / "attempts" / "risky" / "manifest.json").read_text())
    assert risky_m["escalated"] is True
    policy = adaptive.load_agentic_policy(tmp_path)
    assert policy["clean"] == "optional_skipped"
    assert policy["risky"] == "escalated"
