"""跨文档查重(C8):同号发票的内容冲突与重复提交。

钉死的语义:
- 分组键 (seller, invoice_number) —— 编号空间按卖家独立;
- 同号同卖家,gross/日期不同 → content_conflict;全同 → resubmission;
- finding non-blocking、repair_owner=human、不进错误率(宪章:不是判决);
- 涉案 invoice_number 行盖 fail → 自动进 requires_adjudication(复核队列);
- 缺号/缺卖家不参与查重(缺口已由在场检查记过);
- 取值只用冻结账本,dws_understand 优先(与 matrix 行同口径)。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import crossdoc, gates, ocr
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import make_response, pin_corpus

DOC_A, DOC_B, DOC_C = "doc-a", "doc-b", "doc-c"


def _claim(doc, field, value, by="dws_understand"):
    return {"claim_id": f"FC-{doc}-{field}", "doc_id": doc, "field": field,
            "value": value, "drafted_by": by, "span_ids": []}


def _invoice_claims(doc, number, seller, gross, date):
    return [_claim(doc, "invoice_number", number),
            _claim(doc, "seller_name", seller),
            _claim(doc, "total_gross", gross),
            _claim(doc, "issue_date", date)]


class TestGroups:
    def test_same_number_same_seller_different_content(self):
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-1", "Acme", "250.00", "2026-01-05"))
        groups = crossdoc.duplicate_groups(claims)
        (g,) = groups
        assert g["kind"] == "content_conflict"
        assert {d["doc_id"] for d in g["docs"]} == {DOC_A, DOC_B}

    def test_same_everything_is_resubmission(self):
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-1", "Acme", "100.00", "2026-01-05"))
        (g,) = crossdoc.duplicate_groups(claims)
        assert g["kind"] == "resubmission"

    def test_same_number_different_seller_is_not_a_group(self):
        """编号空间按卖家独立:不同卖家同号放行。"""
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-1", "Globex", "250.00", "2026-02-01"))
        assert crossdoc.duplicate_groups(claims) == []

    def test_single_doc_never_groups(self):
        claims = _invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
        assert crossdoc.duplicate_groups(claims) == []

    def test_missing_number_or_seller_is_skipped(self):
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + [_claim(DOC_B, "total_gross", "100.00")])
        assert crossdoc.duplicate_groups(claims) == []

    def test_understand_value_wins_over_agentic(self):
        """查重取值与 matrix 行同口径:understand 的冻结声明优先。"""
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-1", "Acme", "100.00", "2026-01-05")
                  + [_claim(DOC_B, "total_gross", "999.00", by="dws_agentic")])
        (g,) = crossdoc.duplicate_groups(claims)
        assert g["kind"] == "resubmission", \
            "agentic 的异值不许盖过 understand —— 否则查重口径与 matrix 行分叉"


def _run_gates_with(claims, docs=(DOC_A, DOC_B)):
    understand = {d: make_response(d, "understand", {
        "invoice_number": "INV-1", "issue_date": "2026-01-05",
        "due_date": "2026-02-05", "seller_name": "Acme",
        "seller_vat_id": "X1", "buyer_name": "Buyer",
        "total_net": "90.00", "total_vat": "10.00",
        "total_gross": "100.00", "amount_due": "100.00"}) for d in docs}
    agentic = {d: make_response(d, "agentic", dict(u.data))
               for d, u in understand.items()}
    return gates.run_gates(
        list(docs), understand=understand, agentic=agentic,
        vision_answers={}, ledger_sha256="x", artifact_digest="y",
        duplicate_groups=crossdoc.duplicate_groups(claims))


class TestGateIntegration:
    def test_findings_are_non_blocking_and_human_owned(self):
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-1", "Acme", "250.00", "2026-01-05"))
        report = _run_gates_with(claims)
        hits = [f for f in report["findings"]
                if f["gate_id"] == "cross_document_duplicate"]
        assert len(hits) == 2, "每个涉案文档一条 finding"
        assert all(not f["blocking"] for f in hits), "查重不是阻断 —— 不是判决"
        assert all(f["repair_owner"] == "human" for f in hits)
        assert all(f["blocking"] == (f["blocking_level"] == "blocking")
                   for f in hits), "契约不变量不许破"

    def test_invoice_number_row_gets_fail_and_enters_queue(self):
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-1", "Acme", "250.00", "2026-01-05"))
        report = _run_gates_with(claims)
        for doc in (DOC_A, DOC_B):
            assert report["evaluations"][doc]["invoice_number"][
                "cross_document_duplicate"] == "fail"
        # matrix 的既有规则(fail → requires_adjudication)自动把涉案行送入队列
        from invoiceloop.matrix import build_matrix

        understand = {d: make_response(d, "understand", {
            "invoice_number": "INV-1", "seller_name": "Acme"}) for d in (DOC_A, DOC_B)}
        matrix, _routing = build_matrix(
            [DOC_A, DOC_B], understand=understand, claims=claims, rejections=[],
            gate_report=report, vision_answers={})
        flagged = [r for r in matrix["rows"] if r["field"] == "invoice_number"]
        assert all(r["requires_adjudication"] for r in flagged), \
            "跨文档冲突必须出现在复核队列 —— 它唯一的去处就是人"

    def test_no_group_no_finding_no_verdict(self):
        claims = (_invoice_claims(DOC_A, "INV-1", "Acme", "100.00", "2026-01-05")
                  + _invoice_claims(DOC_B, "INV-2", "Acme", "250.00", "2026-01-05"))
        report = _run_gates_with(claims)
        assert not [f for f in report["findings"]
                    if f["gate_id"] == "cross_document_duplicate"]
        assert "cross_document_duplicate" not in \
            report["evaluations"][DOC_A]["invoice_number"]


@pytest.fixture
def two_doc_ws(tmp_path, monkeypatch):
    """pipeline 集成:两份同号异额的文档走完整 run。"""
    ws = tmp_path / "ws"
    (ws / "input" / "pdfs").mkdir(parents=True)
    (ws / "ocr").mkdir()
    (ws / "raw").mkdir()

    def ocr_payload(extra):
        words = [("INV-1", 0.10), ("Total", 0.20), (extra, 0.30), ("Acme", 0.40)]
        return {"pages": [{
            "page_idx": 0, "dimensions": [612, 792],
            "blocks": [{"lines": [{"words": [
                {"value": v, "confidence": 0.99,
                 "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
                for v, x in words]}]}],
        }]}

    def record(doc, gross):
        return {"doc_id": doc, "document": f"{doc}.pdf", "mode": "understand",
                "http_status": 200,
                "body": {"output": {
                    "data": {"invoice_number": "INV-1", "seller_name": "Acme",
                             "total_gross": gross},
                    "metadata": {},
                    "pages": [{"page": 1, "width": 612, "height": 792}]}}}

    for doc, gross in ((DOC_A, "100.00"), (DOC_B, "250.00")):
        (ws / "input" / "pdfs" / f"{doc}.pdf").write_bytes(b"%PDF-1.4 fake")
        (ws / "ocr" / f"{doc}.json").write_text(json.dumps(ocr_payload(gross)))
        for mode in ("understand", "agentic"):
            (ws / "raw" / f"{doc}.{mode}.json").write_text(
                json.dumps(record(doc, gross)))
    pin_corpus(monkeypatch, ws)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield ws
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


class TestPipelineIntegration:
    def test_full_run_flags_conflict_group(self, two_doc_ws):
        out = two_doc_ws / "runs" / "run-0001"
        pipeline_run([DOC_A, DOC_B], out, include_vision=False,
                     out_of_calibration=True)
        report = json.loads((out / "gate_report.json").read_text())
        hits = [f for f in report["findings"]
                if f["gate_id"] == "cross_document_duplicate"]
        assert len(hits) == 2 and all(not f["blocking"] for f in hits)
        events = [json.loads(line)
                  for line in (out / "event_log.jsonl").read_text().splitlines()]
        assert any(e["event"] == "cross_document_duplicates" for e in events), \
            "冲突组要进事件日志,不许只在 findings 里"
        matrix = json.loads((out / "support_matrix.json").read_text())
        flagged = [r for r in matrix["rows"] if r["field"] == "invoice_number"]
        assert all(r["requires_adjudication"] for r in flagged)
        panel = (out / "support_panel.html").read_text()
        assert "跨文档查重" in panel and "同号不同内容" in panel, \
            "panel 必须有并排对照一节 —— 人要看的就是这两份摆在一起"
