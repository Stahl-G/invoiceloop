"""整单交付层(P2):deliverable.json 投影与放行规则。

钉死的语义(设计 2026-08-04 用户批准):
- correct → 修正值;accept → 声明值;reject → null;abstain → 未决;
- 需裁决未裁决 → pending;**TIER1 印证槽未显式裁决 → pending_tier1**;
  TIER2 印证槽 → unreviewed_corroborated(照出值,如实标注);
- 整单:TIER1 槽被 reject → blocked;任何 pending/abstain → pending;
  其余 released;
- 纯投影:同工件同账本,重算同字节;不进快照成分。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import adjudicate, deliver, ocr
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"
DECIDED = "2026-08-05T00:00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """单文档 workspace:seller_name(TIER2)有值有印证,total_gross(TIER1)有值。"""
    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    words = [("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30), ("Acme", 0.40)]
    (d / "ocr" / f"{DOC}.json").write_text(json.dumps({"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in words]}]}],
    }]}))
    (d / "raw").mkdir()
    data = {"invoice_number": "INV-42", "total_gross": "100.00",
            "seller_name": "Acme"}
    for mode in ("understand", "agentic"):
        (d / "raw" / f"{DOC}.{mode}.json").write_text(json.dumps(
            {"doc_id": DOC, "document": f"{DOC}.pdf", "mode": mode,
             "http_status": 200,
             "body": {"output": {"data": data, "metadata": {},
                                 "pages": [{"page": 1, "width": 612,
                                            "height": 792}]}}}))
    pin_corpus(monkeypatch, d)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    out = d / "runs" / "run-0001"
    pipeline_run([DOC], out, include_vision=False, out_of_calibration=True)
    yield out
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def _decide(run_dir, field, decision, **kw):
    base = dict(claim_id=None, doc_id=DOC, field=field, decision=decision,
                rationale="r", adjudicator="t", decided_at=DECIDED)
    base.update(kw)
    return adjudicate.append_adjudication(run_dir, **base)


class TestProjection:
    def test_fresh_run_statuses(self, ws):
        d = deliver.build_deliverable(ws)
        fields = d["docs"][DOC]["fields"]
        assert fields["total_gross"]["status"] == "pending_tier1", \
            "TIER1 印证槽也必须显式裁决才放行(78 评 P2 的核心)"
        assert fields["invoice_number"]["status"] == "pending_tier1"
        assert fields["seller_name"]["status"] == "unreviewed_corroborated", \
            "TIER2 印证槽照出值并如实标注"
        assert fields["seller_name"]["value"] == "Acme"
        assert fields["buyer_name"]["status"] == "pending", \
            "无值槽需裁决(补录或确认缺失)"
        assert d["docs"][DOC]["status"] == "pending"
        assert (ws / "deliverable.json").exists(), "run 时就生成,如实展示零裁决"

    def test_accept_uses_claim_value(self, ws):
        _decide(ws, "total_gross", "accept")
        d = deliver.build_deliverable(ws)
        f = d["docs"][DOC]["fields"]["total_gross"]
        assert f["value"] == "100.00" and f["status"] == "accepted"
        assert f["source"] == "HD-0001"

    def test_correct_uses_corrected_value(self, ws):
        _decide(ws, "total_gross", "correct", corrected_value="102.00")
        f = deliver.build_deliverable(ws)["docs"][DOC]["fields"]["total_gross"]
        assert f["value"] == "102.00" and f["status"] == "corrected"

    def test_reject_tier1_blocks_the_document(self, ws):
        _decide(ws, "total_gross", "reject")
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "blocked"
        assert any("total_gross" in r for r in doc["blocking_reasons"])

    def test_abstain_keeps_document_pending(self, ws):
        _decide(ws, "total_gross", "abstain")
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "pending", "弃权 = 未决,不许带着放行"

    def test_release_after_full_adjudication(self, ws):
        d0 = deliver.build_deliverable(ws)
        for field, f in d0["docs"][DOC]["fields"].items():
            if f["status"] in ("pending", "pending_tier1"):
                _decide(ws, field, "accept")
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "released"
        seller = doc["fields"]["seller_name"]
        assert seller["status"] == "unreviewed_corroborated", \
            "TIER2 印证槽不拦放行,但标注不许丢"

    def test_deterministic_projection(self, ws):
        assert (deliver.build_deliverable(ws)
                == deliver.build_deliverable(ws))

    def test_render_refreshes_deliverable(self, ws):
        """裁决后 render_panel_from_run 必须同步刷新 deliverable(投影同生命周期)。"""
        from invoiceloop.panel import render_panel_from_run

        before = json.loads((ws / "deliverable.json").read_text())
        assert before["docs"][DOC]["fields"]["total_gross"]["status"] == "pending_tier1"
        _decide(ws, "total_gross", "accept")
        render_panel_from_run(ws)
        after = json.loads((ws / "deliverable.json").read_text())
        assert after["docs"][DOC]["fields"]["total_gross"]["status"] == "accepted"

    def test_bundle_carries_deliverable_when_present(self, ws):
        bundle = adjudicate.build_audit_bundle(ws)
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            assert "deliverable.json" in zf.namelist()
        report = adjudicate.verify_bundle(bundle)
        assert report["ok"], report["failures"]
