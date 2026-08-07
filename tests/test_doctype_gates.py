"""阶段 C:doctype 接入门禁 document_checks(非阻断)与交付物 type_trust。"""

from __future__ import annotations

import json

from invoiceloop import doctype, gates
from invoiceloop.deliver import build_deliverable
from invoiceloop.fields import FIELDS
from tests.conftest import make_response
from tests.test_gates import FULL_DATA


def _run(data, *, doc_id="doc-a"):
    u = make_response(doc_id, "understand", data)
    a = make_response(doc_id, "agentic", dict(data))
    return gates.run_gates(
        [doc_id],
        understand={doc_id: u}, agentic={doc_id: a},
        vision_answers={}, ledger_sha256="x", artifact_digest="y",
    )


class TestDocumentChecks:
    def test_no_claim_when_type_absent(self, positioned_corpus):
        report = _run(FULL_DATA)  # FULL_DATA 无 invoice_type
        check = report["document_checks"]["doc-a"]
        assert check["status"] == doctype.NO_CLAIM
        assert not any(f["gate_id"] == "doctype_evidence"
                       for f in report["findings"])

    def test_pass_with_literal_invoice(self, positioned_corpus):
        from invoiceloop import ocr
        path = ocr.ocr_path("doc-a")
        blob = json.loads(path.read_text())
        blob["pages"][0]["blocks"][0]["lines"][0]["words"].append({
            "value": "INVOICE",
            "confidence": 0.99,
            "geometry": [[0.50, 0.05], [0.70, 0.08]],
            "snapped_geometry": [[0.50, 0.05], [0.70, 0.08]],
        })
        path.write_text(json.dumps(blob))
        ocr.load_ocr.cache_clear()
        report = _run({**FULL_DATA, "invoice_type": "Invoice"})
        check = report["document_checks"]["doc-a"]
        assert check["status"] == "pass"
        assert check["doc_class"] == "invoice"
        assert check["evidence"]["phrase"] == "invoice"
        assert not any(f["gate_id"] == "doctype_evidence" and f["blocking"]
                       for f in report["findings"])

    def test_fail_is_non_blocking(self, positioned_corpus):
        """页上无 invoice 字面 → fail finding,但 non-blocking(typedep)。"""
        report = _run({**FULL_DATA, "invoice_type": "invoice"})
        check = report["document_checks"]["doc-a"]
        assert check["status"] == "fail"
        (f,) = [x for x in report["findings"] if x["gate_id"] == "doctype_evidence"]
        assert f["blocking"] is False
        assert f["blocking_level"] == "non-blocking"
        assert f["field"] is None

    def test_evaluations_untouched_by_document_key(self, positioned_corpus):
        """不许把 __document__ 塞进 evaluations —— heldout 展平会坏。"""
        report = _run({**FULL_DATA, "invoice_type": "invoice"})
        assert "__document__" not in report["evaluations"]["doc-a"]
        assert set(report["evaluations"]["doc-a"]) == set(FIELDS)


class TestDeliverTypeTrust:
    def test_untrusted_on_deliverable(self, tmp_path):
        """手搓最小 run 工件 —— 只验 deliver 读 document_checks。"""
        run = tmp_path / "run"
        run.mkdir()
        gate = {
            "findings": [],
            "evaluations": {"doc-a": {f: {} for f in FIELDS}},
            "document_checks": {
                "doc-a": {"gate_id": "doctype_evidence", "status": "fail",
                          "doc_class": "invoice", "raw_type": "invoice",
                          "evidence": None},
            },
            "input_signature": {},
        }
        matrix = {
            "rows": [{
                "doc_id": "doc-a", "field": "invoice_number",
                "value": "INV-1", "claim_id": "FC-1",
                "requires_adjudication": False, "in_human_queue": False,
                "route": "auto_accept", "support_strength": "corroborated",
                "applicability": "applicable",
            }],
            "summary": {},
        }
        ledger = {"sha256": "abc", "claims": [
            {"claim_id": "FC-1", "doc_id": "doc-a", "field": "invoice_number",
             "value": "INV-1", "drafted_by": "dws_understand", "span_ids": []},
        ]}
        routing = {
            "harness_id": "HAR-0001",
            "policy": {"release_tier1_explicit": True},
            "routes": [{"doc_id": "doc-a", "field": "invoice_number",
                        "route": "auto_accept"}],
        }
        (run / "gate_report.json").write_text(json.dumps(gate))
        (run / "support_matrix.json").write_text(json.dumps(matrix))
        (run / "field_ledger.json").write_text(json.dumps(ledger))
        (run / "routing_report.json").write_text(json.dumps(routing))
        (run / "adjudication_ledger.jsonl").write_text("")
        for name, payload in (
            ("input_manifest.json", {"fingerprint": "f", "docs": []}),
            ("artifact_registry.json", []),
            ("evidence_span_registry.json", []),
            ("review_snapshot.json", {"review_snapshot_id": "snap"}),
        ):
            (run / name).write_text(json.dumps(payload))
        deliverable = build_deliverable(run)
        assert deliverable["docs"]["doc-a"]["type_trust"] == "untrusted"
        assert deliverable["docs"]["doc-a"]["doc_class"] == "invoice"

    def test_old_run_without_document_checks(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        gate = {"findings": [], "evaluations": {"doc-a": {f: {} for f in FIELDS}}}
        matrix = {
            "rows": [{
                "doc_id": "doc-a", "field": "buyer_name",
                "value": "Buyer", "claim_id": None,
                "requires_adjudication": True, "in_human_queue": True,
                "route": "review", "support_strength": "unsupported",
                "applicability": "applicable",
            }],
            "summary": {},
        }
        ledger = {"sha256": "abc", "claims": []}
        routing = {"harness_id": "HAR-0001",
                   "policy": {"release_tier1_explicit": True},
                   "routes": [{"doc_id": "doc-a", "field": "buyer_name",
                               "route": "review"}]}
        (run / "gate_report.json").write_text(json.dumps(gate))
        (run / "support_matrix.json").write_text(json.dumps(matrix))
        (run / "field_ledger.json").write_text(json.dumps(ledger))
        (run / "routing_report.json").write_text(json.dumps(routing))
        (run / "adjudication_ledger.jsonl").write_text("")
        for name, payload in (
            ("input_manifest.json", {"fingerprint": "f", "docs": []}),
            ("artifact_registry.json", []),
            ("evidence_span_registry.json", []),
            ("review_snapshot.json", {"review_snapshot_id": "snap"}),
        ):
            (run / name).write_text(json.dumps(payload))
        deliverable = build_deliverable(run)
        assert deliverable["docs"]["doc-a"]["type_trust"] == "unknown"


class TestDoctypeDigest:
    def test_digest_stable_and_in_fingerprint(self, tmp_path, monkeypatch):
        from invoiceloop import snapshot
        from tests.conftest import pin_corpus

        root = tmp_path / "ws"
        (root / "input" / "pdfs").mkdir(parents=True)
        (root / "raw").mkdir()
        (root / "ocr").mkdir()
        pin_corpus(monkeypatch, root)
        m1 = snapshot.build_input_manifest([])
        m2 = snapshot.build_input_manifest([])
        assert m1["doctype_digest"] == doctype.digest()
        assert m1["doctype_digest"] == m2["doctype_digest"]
        assert m1["execution_fingerprint"] == m2["execution_fingerprint"]
