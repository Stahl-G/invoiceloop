"""改进闭环(v0.2 收窄版)端到端钉死:

mine(统计)→ propose(候选 + diff linter)→ evaluate(反事实重路由)
→ promote(人工晋升)→ 新 run 绑新 harness(指纹换代)。

权限纪律:
- lint:cohort 白名单外特征、非受评字段、改动 cohorts 以外的键 → 全拒;
- promote 必须人名 + 理由 + ISO 时间;
- 晋升后同输入开新 run(harness digest 进指纹),不许重放旧 run。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import adjudicate, improve, ocr
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"
DECIDED = "2026-08-05T03:00:00"


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
    data = {"invoice_number": "INV-42", "total_gross": "100.00"}
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


class TestFeedbackAndMine:
    def test_events_derived_from_decisions(self, ws):
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="与页面一致",
            adjudicator="t", decided_at=DECIDED, reason_code="ROUTING_FALSE_POSITIVE")
        events = improve.compile_workspace(ws)
        assert len(events) == 1
        e = events[0]
        assert e["harness_id"] == "HAR-0001"
        assert e["reason_code"] == "ROUTING_FALSE_POSITIVE"
        assert e["tier"] == "TIER1" and e["route"] is not None

    def test_reason_code_must_be_from_minimal_set(self, ws):
        with pytest.raises(ValueError, match="最小心码集"):
            adjudicate.append_adjudication(
                ws / "runs" / "run-0001", claim_id=None, doc_id=DOC,
                field="buyer_name", decision="abstain", rationale="r",
                adjudicator="t", decided_at=DECIDED, reason_code="MADE_UP")

    def test_mine_report_flags_low_yield_cohorts(self, ws):
        run_dir = ws / "runs" / "run-0001"
        # 三个槽各 accept 一次(零修正)→ 对应 cohort 进低收益候选
        for field in ("invoice_number", "total_gross"):
            adjudicate.append_adjudication(
                run_dir, claim_id=_claim_id(run_dir, field), doc_id=DOC,
                field=field, decision="accept", rationale="r", adjudicator="t",
                decided_at=DECIDED)
        for field in ("buyer_name", "due_date", "seller_vat_id"):
            adjudicate.append_adjudication(
                run_dir, claim_id=None, doc_id=DOC, field=field,
                decision="confirm_absent", rationale="页面上没有",
                adjudicator="t", decided_at=DECIDED)
        report = improve.mine(ws)
        assert report["events"] == 5
        assert report["warning"].startswith("选择偏差警告"), \
            "选择偏差警告必须在每份报告头部(不许变成「没修正=没价值」)"
        assert (ws / "improve" / "mine_report.json").exists()


class TestProposeLint:
    def test_whitelist_violation_rejected(self, ws):
        with pytest.raises(ValueError, match="白名单外特征"):
            improve.propose(ws, cohort={"id": "C1", "doc_id": "046e0c49"},
                            finding="FIND-1", prediction="p")

    def test_non_field_rejected(self, ws):
        with pytest.raises(ValueError, match="不是受评字段"):
            improve.propose(ws, cohort={"id": "C1", "field": "made_up_field"},
                            finding="FIND-1", prediction="p")

    def test_legal_cohort_scaffolds_candidate(self, ws):
        cand = improve.propose(
            ws, cohort={"id": "C1", "field": "seller_name",
                        "strength": "corroborated"},
            finding="FIND-1", prediction="review load -2pp,critical +0")
        assert cand.name == "HAR-0002"
        manifest = json.loads((cand / "manifest.json").read_text())
        assert manifest["status"] == "candidate"
        assert manifest["parent_harness_id"] == "HAR-0001"


class TestEvaluatePromote:
    def test_full_loop(self, ws):
        # 候选:放松 seller_name 的 corroborated cohort
        cand = improve.propose(
            ws, cohort={"id": "C1", "field": "seller_name",
                        "strength": "corroborated"},
            finding="FIND-1", prediction="review -1 slot")
        result = improve.evaluate(ws, "HAR-0002")
        assert result["baseline_harness"] == "HAR-0001"
        assert result["candidate"] == "HAR-0002"
        assert "note" in result and "反事实" in result["note"], \
            "evaluate 不许给安全性结论(真值评测是 sealed 协议)"

        # promote 必须人名+理由+时间
        with pytest.raises(ValueError, match="approved_by"):
            improve.promote(ws, "HAR-0002", approved_by=" ",
                            rationale="r", approved_at=DECIDED)
        record = improve.promote(ws, "HAR-0002", approved_by="y",
                                 rationale="残余风险接受:cohort 仅 TIER2 软触发",
                                 approved_at=DECIDED)
        assert record["to_harness_id"] == "HAR-0002"
        pointer = json.loads((ws / "improve" / "active_harness.json").read_text())
        assert pointer["harness_id"] == "HAR-0002"

        # 同输入重跑:指纹含 harness digest,晋升后不许重放 run-0001
        from invoiceloop.snapshot import build_input_manifest, find_run_by_fingerprint

        fp1 = json.loads((ws / "runs" / "run-0001" / "input_manifest.json")
                         .read_text())["fingerprint"]
        fp2 = build_input_manifest([DOC], include_vision=False)["fingerprint"]
        assert fp1 != fp2, "harness 换代必须改指纹"
        assert find_run_by_fingerprint(ws / "runs", fp2) is None

        # 新 run 绑 HAR-0002
        pipeline_run([DOC], ws / "runs" / "run-0002", include_vision=False,
                     out_of_calibration=True)
        routing = json.loads((ws / "runs" / "run-0002" / "routing_report.json")
                             .read_text())
        assert routing["harness_id"] == "HAR-0002"
        manifest = json.loads((ws / "runs" / "run-0002" / "run_manifest.json")
                              .read_text())
        assert manifest["harness_id"] == "HAR-0002", \
            "新 run 必须能回答「哪版 harness 处理的」"
