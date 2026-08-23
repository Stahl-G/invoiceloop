"""行走集抽样必须与工作台队列同一个谓词 —— 否则会抽到打开后无槽可走的文档。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_walk_plan  # noqa: E402

NARROW = {"release_profile": {"id": "payment_required_v1",
                              "fields": ["invoice_number", "seller_name",
                                         "amount_due"]}}


def test_a_document_whose_only_review_slot_is_non_gating_is_not_eligible():
    """date_due 进不了 payment_required_v1 的行走队列 ——
    抽中它,复核者打开会看到一个空队列。"""
    routes = [{"doc_id": "d1", "field": "date_due", "route": "review",
               "in_human_queue": True, "reason_codes": []}]
    assert qual_walk_plan.eligible(routes, NARROW) == []


def test_a_gating_review_slot_is_eligible():
    routes = [{"doc_id": "d1", "field": "invoice_number", "route": "review",
               "in_human_queue": True, "reason_codes": []}]
    assert qual_walk_plan.eligible(routes, NARROW) == ["d1"]


def test_a_qa_probe_is_eligible_even_on_a_non_gating_field():
    """QA 探针无视闸字段集进队列(document_touch_metrics 也是这么算的)。"""
    routes = [{"doc_id": "d1", "field": "date_due", "route": "review",
               "in_human_queue": True, "reason_codes": ["QA_SAMPLE_ABSENT"]}]
    assert qual_walk_plan.eligible(routes, NARROW) == ["d1"]


def test_census_policy_keeps_every_review_slot():
    """普查策略没有 release_profile,工作台不裁剪队列。"""
    routes = [{"doc_id": "d1", "field": "date_due", "route": "review",
               "in_human_queue": True, "reason_codes": []}]
    assert qual_walk_plan.eligible(routes, {}) == ["d1"]


def test_a_failed_qualification_can_feed_an_independent_walk_but_stays_failed(
        tmp_path):
    routing = tmp_path / "routing.json"
    inputs = tmp_path / "inputs.json"
    decision = tmp_path / "decision.json"
    docs = [f"d{i:03d}" for i in range(200)]
    routing.write_text(json.dumps({
        "harness_id": "HAR-0023", "policy": NARROW,
        "routes": [{"doc_id": doc, "field": "invoice_number",
                    "route": "review", "reason_codes": []}
                   for doc in docs],
    }), encoding="utf-8")
    inputs.write_text(json.dumps({
        "harness_id": "HAR-0023",
        "docs": [{"doc_id": doc} for doc in docs],
    }), encoding="utf-8")
    decision.write_text(json.dumps({
        "round": "qual-v2",
        "integrity": {"passed": True, "source_hashes": {
            "har_0023_routing_report_sha256": hashlib.sha256(
                routing.read_bytes()).hexdigest(),
        }},
        "qualification": {"status": "fail", "promotion": "denied"},
    }), encoding="utf-8")

    payload = qual_walk_plan.build_payload(
        routing_path=routing, input_manifest_path=inputs,
        decision_path=decision, n=20, round_name="walk-v2",
        salt="walk-v2", planner_code_revision="rev")

    assert payload["qualification_status"] == "fail"
    assert payload["qualification_promotion"] == "denied"
    assert payload["eligible_n"] == 200
    assert len(payload["doc_ids"]) == 20


def test_walk_source_must_match_the_routing_hash_in_the_decision(tmp_path):
    routing = tmp_path / "routing.json"
    inputs = tmp_path / "inputs.json"
    decision = tmp_path / "decision.json"
    routing.write_text(json.dumps({"harness_id": "HAR-0023", "routes": []}),
                       encoding="utf-8")
    inputs.write_text(json.dumps({"harness_id": "HAR-0023", "docs": []}),
                      encoding="utf-8")
    decision.write_text(json.dumps({
        "integrity": {"passed": True, "source_hashes": {
            "har_0023_routing_report_sha256": "0" * 64,
        }},
        "qualification": {"status": "fail", "promotion": "denied"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="不是 qualification decision"):
        qual_walk_plan.qualification_binding(routing, inputs, decision)


def test_sampling_salt_is_part_of_the_result():
    docs = [f"d{i:03d}" for i in range(100)]
    assert qual_walk_plan.pick(docs, 20, salt="one") != \
        qual_walk_plan.pick(docs, 20, salt="two")


def test_predicate_matches_the_real_workbench_queue():
    """合成用例钉住逻辑,这条钉住「与生产队列是同一个东西」。

    抽样谓词的全部意义就是复现 workbench._walk_release_profile。两边各写
    一份、哪天改了一边,就会抽到打开后队列为空的文档 —— 而那要走到复核者
    面前才发现。有现成 run 就对拍一次。
    """
    import json

    import pytest

    run = (Path(__file__).resolve().parent.parent
           / "runs" / "hitl-narrow" / "runs" / "run-0001")
    if not (run / "routing_report.json").is_file():
        pytest.skip("没有现成的 narrow run 可对拍")
    from invoiceloop.workbench import RunCtx, Workbench

    report = json.loads((run / "routing_report.json").read_text(encoding="utf-8"))
    mine = set(qual_walk_plan.queue_slots(report["routes"],
                                          report.get("policy") or {}))
    ctx = RunCtx(run)
    theirs = {(r["doc_id"], r["field"]) for r in
              Workbench._walk_release_profile(ctx, Workbench._queue_order(ctx))}
    assert mine == theirs, f"只在抽样器:{sorted(mine - theirs)[:5]};" \
                           f"只在工作台:{sorted(theirs - mine)[:5]}"
