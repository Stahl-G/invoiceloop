"""carry(同证据裁决携带)的契约测试。

钉死的规则:
- accept/reject 只在值与 span 绑定逐位一致时携带;
- confirm_absent 只在新 run 该槽仍无声明时携带(有声明 = 证据变了);
- 携带记录带 carried_from_decision_id 溯源;
- auto_* 出队槽、无历史裁决槽、证据变化槽一律不进账本。

fixture 注:total_gross 在 understand=100.00 / agentic=100.01
(双模式分歧 → 在复核队列);invoice_number 双侧一致(corroborated 干净
→ auto_accept 出队)—— 两条路由形状都占住。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoiceloop import adjudicate, ocr
from invoiceloop.carry import carry_forward
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"
WHEN = "2026-08-06T02:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / f"{DOC}.json").write_text(json.dumps({"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in (("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30))]}]}],
    }]}))
    (d / "raw").mkdir()
    for mode, gross in (("understand", "100.00"), ("agentic", "100.01")):
        (d / "raw" / f"{DOC}.{mode}.json").write_text(json.dumps(
            {"doc_id": DOC, "document": f"{DOC}.pdf", "mode": mode,
             "http_status": 200,
             "body": {"output": {"data": {"invoice_number": "INV-42",
                                          "total_gross": gross},
                                 "metadata": {},
                                 "pages": [{"page": 1, "width": 612,
                                            "height": 792}]}}}))
    pin_corpus(monkeypatch, d)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    pipeline_run([DOC], d / "runs" / "run-0001", include_vision=False,
                 out_of_calibration=True)
    yield d
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def _claim_id(run_dir, field):
    ledger = json.loads((run_dir / "field_ledger.json").read_text())
    return next(c["claim_id"] for c in ledger["claims"]
                if c["doc_id"] == DOC and c["field"] == field
                and c["drafted_by"] == "dws_understand")


def _run(ws, name):
    out = ws / "runs" / name
    pipeline_run([DOC], out, include_vision=False, out_of_calibration=True)
    return out


class TestCarry:
    def test_identical_evidence_carries(self, ws):
        r1 = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            r1, claim_id=_claim_id(r1, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="与页面一致",
            adjudicator="stahl", decided_at=WHEN)
        adjudicate.append_adjudication(
            r1, claim_id=None, doc_id=DOC, field="seller_vat_id",
            decision="confirm_absent", rationale="页面上没有",
            adjudicator="stahl", decided_at=WHEN)
        r2 = _run(ws, "run-0002")
        report = carry_forward(r2, decided_at=WHEN)
        assert report["carried"] == 2, report
        entries = [json.loads(x) for x in
                   (r2 / "adjudication_ledger.jsonl").read_text().splitlines()]
        by_field = {e["field"]: e for e in entries}
        assert by_field["total_gross"]["carried_from_decision_id"] == "HD-0001"
        assert by_field["total_gross"]["claim_id"] == _claim_id(r2, "total_gross"), \
            "claim_id 按新 run 账本重新解析,不照搬旧 FC 编号"
        assert by_field["seller_vat_id"]["reason_code"] == "CONFIRMED_ABSENT", \
            "combo 表 1:1 蕴含的心码,不是编数据"
        assert by_field["seller_vat_id"]["adjudicator"] == "stahl"

    def test_new_claim_blocks_absent_carry(self, ws):
        """确认缺失之后新 run 该槽有了声明 = 证据变了,不许携带,回人重看。
        形状:total_gross 有 understand 声明且在队列(双模式分歧),
        旧 run 却挂着一条 confirm_absent(人裁是自由的)。"""
        r1 = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            r1, claim_id=None, doc_id=DOC, field="total_gross",
            decision="confirm_absent", rationale="当时没看到值",
            adjudicator="stahl", decided_at=WHEN)
        r2 = _run(ws, "run-0002")
        report = carry_forward(r2, decided_at=WHEN)
        assert report["carried"] == 0, report
        assert report["skipped_changed"] == 1, \
            "dst 该槽有 understand 声明 = 证据变了,回人重看"
        assert not (r2 / "adjudication_ledger.jsonl").read_text().strip(), \
            "一条都不许进账本"

    def test_auto_slots_and_unknown_slots_untouched(self, ws):
        r2 = _run(ws, "run-0002")
        report = carry_forward(r2, decided_at=WHEN)
        assert report["carried"] == 0
        assert report["no_prior"] > 0
        assert report["skipped_auto"] > 0, "出队槽只计数,不进账本"
        assert not (r2 / "adjudication_ledger.jsonl").read_text().strip(), \
            "一条都不许进账本"

    def test_later_run_overrides_earlier(self, ws):
        """两个旧 run 都有裁决:后 run 的优先(时间序)。"""
        r1 = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            r1, claim_id=_claim_id(r1, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="初判",
            adjudicator="stahl", decided_at=WHEN)
        r2 = _run(ws, "run-0002")
        adjudicate.append_adjudication(
            r2, claim_id=_claim_id(r2, "total_gross"), doc_id=DOC,
            field="total_gross", decision="reject", rationale="改判:复核后发现不对",
            adjudicator="stahl", decided_at="2026-08-06T03:00:00+00:00")
        r3 = _run(ws, "run-0003")
        report = carry_forward(r3, decided_at=WHEN)
        assert report["carried"] == 1, report
        entries = [json.loads(x) for x in
                   (r3 / "adjudication_ledger.jsonl").read_text().splitlines()]
        assert entries[0]["decision"] == "reject", \
            "携带的是最近的裁决,不是最早的那条"
