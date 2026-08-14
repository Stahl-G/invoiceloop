"""release_profile: 窄放行契约不改普查重放,也不把未复核标成正确。"""

from __future__ import annotations

import json
import hashlib

import pytest

from invoiceloop import adjudicate, deliver, ocr, release_profile
from invoiceloop.fields import TIER1
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"
DECIDED = "2026-08-05T00:00:00"


def test_missing_profile_is_census():
    from invoiceloop.fields import FIELDS

    assert release_profile.parse_release_profile({}) is None
    assert release_profile.parse_release_profile(
        {"release_tier1_explicit": True}) is None
    assert release_profile.gating_fields({}) == frozenset(FIELDS)


def test_payment_required_v1_is_frozen():
    p = release_profile.parse_release_profile({
        "release_profile": {"id": "payment_required_v1"},
    })
    assert p["fields"] == frozenset(release_profile.PAYMENT_REQUIRED_V1)
    with pytest.raises(ValueError, match="冻结"):
        release_profile.parse_release_profile({
            "release_profile": {
                "id": "payment_required_v1",
                "fields": ["invoice_number", "amount_due"],
            },
        })


def test_unknown_profile_fails_closed():
    with pytest.raises(ValueError, match="未知"):
        release_profile.parse_release_profile({
            "release_profile": {"id": "trust_the_model_v1"},
        })


def test_census_pending_tier1_blocks_posting():
    assert release_profile.status_blocks_posting(
        "amount_due", "pending_tier1", policy={})
    assert not release_profile.status_blocks_posting(
        "amount_due", "unreviewed_corroborated", policy={})


def test_profile_pending_tier1_does_not_block_payment():
    policy = {"release_profile": {"id": "payment_required_v1"}}
    assert not release_profile.status_blocks_posting(
        "amount_due", "pending_tier1", policy=policy)
    assert release_profile.status_blocks_posting(
        "amount_due", "pending", policy=policy)
    assert not release_profile.status_blocks_posting(
        "total_gross", "pending", policy=policy)
    assert not release_profile.status_blocks_posting(
        "buyer_name", "pending", policy=policy)


def test_profile_reject_only_gates_contract_tier1():
    policy = {"release_profile": {"id": "payment_required_v1"}}
    assert release_profile.reject_blocks_document(
        "amount_due", policy=policy, tier1=TIER1)
    assert not release_profile.reject_blocks_document(
        "total_gross", policy=policy, tier1=TIER1)
    assert release_profile.reject_blocks_document(
        "total_gross", policy={}, tier1=TIER1)


def test_touch_metrics_count_gating_and_qa():
    routes = [
        {"doc_id": "a", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "a", "field": "seller_name", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "a", "field": "amount_due", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "a", "field": "buyer_name", "route": "review",
         "reason_codes": ["UNSUPPORTED"]},
        {"doc_id": "b", "field": "amount_due", "route": "review",
         "reason_codes": ["GATE_FAIL:x"]},
        {"doc_id": "b", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "b", "field": "seller_name", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "c", "field": "total_vat", "route": "review",
         "reason_codes": ["EXPECTED_ABSENT:x", "QA_SAMPLE:x"]},
        {"doc_id": "c", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "c", "field": "seller_name", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
        {"doc_id": "c", "field": "amount_due", "route": "auto_accept",
         "reason_codes": ["CLEAN"]},
    ]
    policy = {"release_profile": {"id": "payment_required_v1"}}
    m = release_profile.document_touch_metrics(routes, policy)
    assert m["zero_touch_docs"] == 1  # a: buyer_name review is outside gate
    assert m["touched_docs"] == 2     # b gating + c QA probe
    assert m["unresolved_release_slots"] == 1  # b amount_due
    assert m["qa_probe_slots"] == 1


@pytest.fixture
def ws(tmp_path, monkeypatch):
    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    words = [("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30), ("Acme", 0.40)]
    (d / "ocr" / f"{DOC}.json").write_text(json.dumps({"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99,
             "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in words]}]}],
    }]}))
    (d / "raw").mkdir()
    data = {"invoice_number": "INV-42", "total_gross": "100.00",
            "seller_name": "Acme", "amount_due": "100.00"}
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
    ledger = json.loads((run_dir / "field_ledger.json").read_text())
    return next(c["claim_id"] for c in ledger["claims"]
                if c["doc_id"] == DOC and c["field"] == field
                and c["drafted_by"] == "dws_understand")


def _decide(run_dir, field, decision, **kw):
    base = dict(claim_id=None, doc_id=DOC, field=field, decision=decision,
                rationale="r", adjudicator="t", decided_at=DECIDED)
    if decision == "accept":
        base["claim_id"] = _claim_id(run_dir, field)
    base.update(kw)
    return adjudicate.append_adjudication(run_dir, **base)


def _promote_profile(run_dir):
    from invoiceloop import harness, improve

    root = run_dir.parent.parent
    hid = "HAR-T-PAY"
    (root / "harnesses" / hid).mkdir(parents=True)
    policy = {
        "harness_id": hid, "version": 99,
        "release_tier1_explicit": True,
        "auto_accept_cohorts": [],
        "release_profile": {"id": "payment_required_v1"},
    }
    path = root / "harnesses" / hid / "routing_policy.json"
    path.write_text(json.dumps(policy))
    builtin_sha = hashlib.sha256(harness._builtin_policy_bytes()).hexdigest()
    improve._append_promotion(root, {
        "promotion_id": "PROM-0001",
        "action": "promote",
        "from_harness_id": "HAR-0001",
        "from_policy_digest": builtin_sha,
        "to_harness_id": hid,
        "to_policy_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
        "evaluation_digest": None,
        "gate": "test_fixture",
        "basis": "evo_replay_only",
        "claim_limits": "测试夹具",
        "approved_by": "test", "approved_at": "2026-08-05T00:00:00",
        "rationale": "测试:payment_required_v1 不挡契约外 pending",
        "rollback_harness_id": "HAR-0001",
    })
    out = root / "runs" / "run-0002"
    pipeline_run([DOC], out, include_vision=False, out_of_calibration=True)
    return out


class TestDeliverHonoursProfile:
    def test_census_still_pending_on_non_payment_fields(self, ws):
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "pending"
        assert "release_contract" not in deliver.build_deliverable(ws)["summary"]

    def test_payment_profile_does_not_wait_on_buyer_or_gross(self, ws):
        out = _promote_profile(ws)
        d = deliver.build_deliverable(out)
        doc = d["docs"][DOC]
        assert doc["fields"]["buyer_name"]["status"] == "pending"
        assert doc["fields"]["total_gross"]["status"] == "pending_tier1"
        assert doc["fields"]["amount_due"]["status"] == "pending_tier1"
        assert doc["fields"]["invoice_number"]["status"] == "pending_tier1"
        assert doc["fields"]["seller_name"]["status"] == "unreviewed_corroborated"
        # 契约内 TIER1 自动放行仍标 pending_tier1,但不挡等人批单
        assert doc["status"] == "ready_for_approval", \
            "付款契约下,契约外 pending 与契约内 pending_tier1 都不该拦住批单"
        rc = d["summary"]["release_contract"]
        assert rc["release_profile_id"] == "payment_required_v1"
        assert rc["zero_touch_docs"] == 1

    def test_unresolved_amount_due_still_blocks(self, ws):
        out = _promote_profile(ws)
        # 把 amount_due 从自动放行改成「需要人、且没人裁」—— 写一条
        # 不存在的裁决做不到;直接确认:空值槽 buyer 不挡,但若 amount_due
        # 被拒则整单 blocked。
        _decide(out, "amount_due", "reject")
        doc = deliver.build_deliverable(out)["docs"][DOC]
        assert doc["status"] == "blocked"
        assert any("amount_due" in r for r in doc["blocking_reasons"])

    def test_reject_gross_does_not_block_payment_profile(self, ws):
        out = _promote_profile(ws)
        _decide(out, "total_gross", "reject")
        doc = deliver.build_deliverable(out)["docs"][DOC]
        assert doc["fields"]["total_gross"]["status"] == "rejected"
        assert doc["status"] == "ready_for_approval", \
            "契约外 TIER1 拒绝留在矩阵上,不挡付款放行"
