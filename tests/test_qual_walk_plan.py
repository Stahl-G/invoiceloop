"""行走集抽样必须与工作台队列同一个谓词 —— 否则会抽到打开后无槽可走的文档。"""

from __future__ import annotations

import sys
from pathlib import Path

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
