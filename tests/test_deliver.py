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


def _claim_id(run_dir, field):
    """槽位的 understand 冻结声明 id(accept 必须指向它,81 评 P0 后)。"""
    ledger = json.loads((run_dir / "field_ledger.json").read_text())
    return next(c["claim_id"] for c in ledger["claims"]
                if c["doc_id"] == DOC and c["field"] == field
                and c["drafted_by"] == "dws_understand")


def _decide(run_dir, field, decision, **kw):
    # 决策语义拆分后:接受声明必须带 claim_id;无声明槽的「页面上没有」
    # 走 confirm_absent —— 两者不许再混用
    base = dict(claim_id=None, doc_id=DOC, field=field, decision=decision,
                rationale="r", adjudicator="t", decided_at=DECIDED)
    if decision == "accept":
        base["claim_id"] = _claim_id(run_dir, field)
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
        # 真实人工负载(81 评 P1):10 槽里 7 个需裁决 + 2 个 TIER1 印证槽
        # = 0.9 —— 与反事实分诊负载(0.7)是两回事,两个数字都要在
        assert d["summary"]["decision_load_for_release"] == 0.9

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
            if f["status"] == "pending_tier1":
                _decide(ws, field, "accept")
            elif f["status"] == "pending":
                # 无声明槽:确认页面上没有(confirm_absent),不再借壳 accept
                _decide(ws, field, "confirm_absent")
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


class TestPolicyAccept:
    """v0.2 P0-6:策略放行必须显式记录为 policy_accept + 策略版本,
    不是伪造一条人工 accept。"""

    def test_policy_accepted_status(self, ws, monkeypatch):  # noqa: F811
        # 在 run 之前写入 active 指针:HAR-0002 关闭 TIER1 显式裁决
        root = ws.parent.parent
        (root / "harnesses" / "HAR-0002").mkdir(parents=True)
        (root / "harnesses" / "HAR-0002" / "routing_policy.json").write_text(
            json.dumps({"harness_id": "HAR-0002", "version": 2,
                        "release_tier1_explicit": False,
                        "auto_accept_cohorts": []}))
        (root / "improve").mkdir()
        (root / "improve" / "active_harness.json").write_text(
            json.dumps({"harness_id": "HAR-0002"}))
        out2 = root / "runs" / "run-0002"
        pipeline_run([DOC], out2, include_vision=False, out_of_calibration=True)
        manifest = json.loads((out2 / "run_manifest.json").read_text())
        assert manifest["harness_id"] == "HAR-0002"
        d = deliver.build_deliverable(out2)
        f = d["docs"][DOC]["fields"]["total_gross"]
        assert f["status"] == "policy_accepted", \
            "策略放行要显式记录,不许伪装成人工 accept"
        assert f["value"] == "100.00", "值仍只来自冻结 claim"
        assert f["source"] == "policy:HAR-0002"
        pending = [k for k, v in d["docs"][DOC]["fields"].items()
                   if v["status"] == "pending"]
        assert pending, "未裁决的需裁决槽仍 pending —— 策略只动了 TIER1 显式规则"
        assert d["docs"][DOC]["status"] == "pending", \
            "还有 pending 槽,整单不许放行"

    def test_release_with_blocking_findings_carries_caveats(self, ws):
        """OCR 受阻的文档全部人裁完毕可以放行,但机检没跑过必须随交付物走。"""
        (ws.parent.parent / "ocr" / f"{DOC}.json").unlink()
        ocr.load_ocr.cache_clear()  # 不清缓存,run-0002 会用 run-0001 读过的 OCR
        ocr.doc_tokens.cache_clear()
        out2 = ws.parent.parent / "runs" / "run-0002"
        pipeline_run([DOC], out2, include_vision=False, out_of_calibration=True)
        d0 = deliver.build_deliverable(out2)
        for field, f in d0["docs"][DOC]["fields"].items():
            if f["status"] in ("pending", "pending_tier1"):
                adjudicate.append_adjudication(
                    out2, claim_id=None, doc_id=DOC, field=field,
                    decision="confirm_absent", rationale="r", adjudicator="t",
                    decided_at=DECIDED)
        doc = deliver.build_deliverable(out2)["docs"][DOC]
        assert doc["status"] == "released_with_caveats", \
            "带文档级阻断的放行是单独一档,不许混进 released"
        assert "independent_ocr" in doc["release_caveats"], \
            "机检没跑过的放行不许看起来和机检全过的放行一样"
