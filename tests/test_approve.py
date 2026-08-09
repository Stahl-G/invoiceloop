"""文档级批准:机器算得出的状态一律不可外发。

2026-08-09 Northstar 评审的核心指控:README 把 `released` 这个**机器可达**
的状态直接写成「downstream AP/ERP can post it」。一份十个槽全被策略放行的
发票,从头到尾没有人看过一眼,也会走到 released —— 于是路由策略的松紧变成
了记账授权的松紧。

修法不是把自动放行关掉(那等于放弃分诊),而是把两件事分开:
- **槽级**处置回答「这个值可信吗」,策略可以代答,QA 抽检兜底;
- **文档级**批准回答「这张单可以入账吗」,只有人能答,一单一次。

所以自动化能到达的最好状态是 ready_for_approval;approved_for_export 只能
由 approve_ledger.jsonl 里一条署名事件产生,并且绑死批准当时的文档摘要 ——
值变了,批准自动失效。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import adjudicate, approve, deliver, ocr
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"
DECIDED = "2026-08-05T00:00:00"
APPROVED = "2026-08-09T00:00:00Z"


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


def _dispose_every_slot(run_dir):
    """把所有需要人裁的槽裁掉,只留策略放行的那个 —— 自动化能到的最好状态。"""
    matrix = json.loads((run_dir / "support_matrix.json").read_text())
    d = deliver.build_deliverable(run_dir)
    for field, entry in d["docs"][DOC]["fields"].items():
        if entry["status"] not in deliver.PENDING_STATUSES:
            continue
        row = next(r for r in matrix["rows"] if r["field"] == field)
        if row.get("claim_id"):
            _decide(run_dir, field, "accept")
        else:
            _decide(run_dir, field, "confirm_absent")
    return deliver.build_deliverable(run_dir)


class TestNoMachineReachablePostableStatus:
    def test_all_slots_disposed_still_only_reaches_ready_for_approval(self, ws):
        d = _dispose_every_slot(ws)
        doc = d["docs"][DOC]
        assert doc["status"] == "ready_for_approval", \
            "槽全部处置完毕是自动化的终点,不是记账授权的起点"
        assert "released" not in doc["status"], \
            "别再用一个机器可达的词暗示「可以入账了」"

    def test_policy_released_slot_names_the_policy_that_released_it(self, ws):
        """未逐个人看的 TIER2 槽是**策略**放行的,来源就该写策略,不是 null。

        写 null 会让它读起来像「没人做过决定」;实际上有决定,是 harness
        做的。权威链要能一路指回那份 policy。
        """
        d = deliver.build_deliverable(ws)
        seller = d["docs"][DOC]["fields"]["seller_name"]
        assert seller["status"] == "unreviewed_corroborated"
        assert seller["source"] == "policy:HAR-0001"

    def test_approval_flips_it_to_approved_for_export(self, ws):
        _dispose_every_slot(ws)
        approve.append_approval(
            ws, doc_id=DOC, approved_by="alice",
            rationale="核对过 PO 与收货单", approved_at=APPROVED)
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "approved_for_export"
        assert doc["approval"]["approved_by"] == "alice"
        assert doc["approval"]["rationale"] == "核对过 PO 与收货单"


class TestTheApproverIsToldWhatNobodyLookedAt:
    """降人工率的正路是**知情批准**,不是禁止策略放行关键字段。

    早先想过把 release_tier1_explicit 设成 register_policy 改不动的键。
    加了文档级批准之后那条禁令就多余了(策略放行多少槽都改变不了「外发
    需要一次署名」),而且它会把 HAR-0002 之后整条 harness 谱系判死 ——
    那个开关的用途正是降人工负载。所以改成:不禁止,但必须让签字的人
    看见自己在替多少条策略处置背书。
    """

    def test_deliverable_names_the_slots_no_person_reviewed(self, ws):
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["policy_disposed_fields"] == ["seller_name"]
        assert doc["tier1_policy_disposed_fields"] == [], \
            "HAR-0001 下 TIER1 一个都不许被策略处置"

    def test_the_approval_record_carries_that_list(self, ws):
        _dispose_every_slot(ws)
        entry = approve.append_approval(
            ws, doc_id=DOC, approved_by="alice", rationale="r",
            approved_at=APPROVED)
        assert entry["policy_disposed_fields"] == ["seller_name"]
        assert entry["tier1_policy_disposed_fields"] == []


class TestApprovalRefusals:
    def test_cannot_approve_a_document_with_a_pending_slot(self, ws):
        with pytest.raises(ValueError, match="还有槽没处置"):
            approve.append_approval(
                ws, doc_id=DOC, approved_by="alice", rationale="先批了再说",
                approved_at=APPROVED)

    def test_cannot_approve_a_blocked_document(self, ws):
        _decide(ws, "total_gross", "reject")
        with pytest.raises(ValueError, match="blocked"):
            approve.append_approval(
                ws, doc_id=DOC, approved_by="alice", rationale="不管它",
                approved_at=APPROVED)

    def test_signature_and_reason_are_both_required(self, ws):
        _dispose_every_slot(ws)
        with pytest.raises(ValueError, match="署名"):
            approve.append_approval(ws, doc_id=DOC, approved_by="  ",
                                    rationale="r", approved_at=APPROVED)
        with pytest.raises(ValueError, match="理由"):
            approve.append_approval(ws, doc_id=DOC, approved_by="alice",
                                    rationale="", approved_at=APPROVED)

    def test_time_must_be_machine_readable(self, ws):
        _dispose_every_slot(ws)
        with pytest.raises(ValueError, match="ISO 8601"):
            approve.append_approval(ws, doc_id=DOC, approved_by="alice",
                                    rationale="r", approved_at="下礼拜吧")

    def test_document_must_belong_to_this_run(self, ws):
        _dispose_every_slot(ws)
        with pytest.raises(ValueError, match="不在本次 run"):
            approve.append_approval(ws, doc_id="not-in-run",
                                    approved_by="alice", rationale="r",
                                    approved_at=APPROVED)


class TestApprovalBindsToWhatWasApproved:
    def test_a_changed_value_makes_the_approval_stale(self, ws):
        """批准绑死批准当时的文档摘要 —— 值改了,批准不跟着走。

        否则「批准」会退化成一次性通行证:批完再改值,改动就搭着上一次
        签名出门了。
        """
        _dispose_every_slot(ws)
        approve.append_approval(ws, doc_id=DOC, approved_by="alice",
                                rationale="r", approved_at=APPROVED)
        assert deliver.build_deliverable(ws)["docs"][DOC]["status"] \
            == "approved_for_export"

        tip = next(x for x in adjudicate.load_decisions(ws)
                   if x["field"] == "total_gross")
        _decide(ws, "total_gross", "correct", corrected_value="101.00",
                supersedes_decision_id=tip["decision_id"])

        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "ready_for_approval", \
            "内容变了就要重新批准,旧签名不许覆盖新值"
        assert doc["approval"]["stale"] is True
        assert doc["approval"]["approved_by"] == "alice", \
            "失效的批准仍要留在工件里 —— 谁批过什么是审计轨迹"

    def test_re_approval_after_a_change_is_accepted(self, ws):
        _dispose_every_slot(ws)
        approve.append_approval(ws, doc_id=DOC, approved_by="alice",
                                rationale="r", approved_at=APPROVED)
        tip = next(x for x in adjudicate.load_decisions(ws)
                   if x["field"] == "total_gross")
        _decide(ws, "total_gross", "correct", corrected_value="101.00",
                supersedes_decision_id=tip["decision_id"])
        approve.append_approval(ws, doc_id=DOC, approved_by="bob",
                                rationale="复核了改动", approved_at=APPROVED)
        doc = deliver.build_deliverable(ws)["docs"][DOC]
        assert doc["status"] == "approved_for_export"
        assert doc["approval"]["approved_by"] == "bob"
        assert len(approve.load_approvals(ws)) == 2, "账本只追加,不覆盖"


class TestCaveatsSurviveApproval:
    def test_a_caveated_document_keeps_saying_so_after_approval(self, ws):
        """机检没跑完这件事,不许被一次人工批准盖掉。

        阻断发现必须是**跑出来的**:直接改 gate_report.json 会被
        review_snapshot 完整性闸挡下(它就该挡),所以从输入造 —— 删掉独立
        OCR 再跑一次。
        """
        (ws.parent.parent / "ocr" / f"{DOC}.json").unlink()
        ocr.load_ocr.cache_clear()
        ocr.doc_tokens.cache_clear()
        out2 = ws.parent.parent / "runs" / "run-0002"
        pipeline_run([DOC], out2, include_vision=False, out_of_calibration=True)
        for field, f in deliver.build_deliverable(out2)["docs"][DOC][
                "fields"].items():
            if f["status"] in deliver.PENDING_STATUSES:
                adjudicate.append_adjudication(
                    out2, claim_id=None, doc_id=DOC, field=field,
                    decision="confirm_absent", rationale="r", adjudicator="t",
                    decided_at=DECIDED)
        before = deliver.build_deliverable(out2)["docs"][DOC]
        assert before["status"] == "ready_for_approval_with_caveats"
        approve.append_approval(out2, doc_id=DOC, approved_by="alice",
                                rationale="接受这个披露", approved_at=APPROVED)
        doc = deliver.build_deliverable(out2)["docs"][DOC]
        assert doc["status"] == "approved_for_export_with_caveats"
        assert doc["release_caveats"] == before["release_caveats"]
        assert "independent_ocr" in doc["release_caveats"], \
            "披露内容本身不许在批准后消失"

    def test_approval_refuses_artifacts_touched_after_the_run(self, ws):
        """在被动过的证据上不记批准 —— 与裁决同一道闸。"""
        _dispose_every_slot(ws)
        ledger = ws / "field_ledger.json"
        body = json.loads(ledger.read_text(encoding="utf-8"))
        body["claims"][0]["value"] = "tampered"
        ledger.write_text(json.dumps(body, ensure_ascii=False),
                          encoding="utf-8")
        with pytest.raises(ValueError, match="被改动过"):
            approve.append_approval(ws, doc_id=DOC, approved_by="alice",
                                    rationale="r", approved_at=APPROVED)


class TestDecisionLoadSummarisesItsOwnStatuses:
    def test_decision_load_counts_slots_no_policy_disposed_of(self, ws):
        """SEALED-3 §5:该指标七个 harness 全报 82.8%,与自身字段状态矛盾。

        根因是它按 `requires_adjudication ∪ 全部 TIER1` 数,压根不看 route ——
        于是它对 harness 完全不敏感,而这正是要拿它做多臂比较的地方。
        新口径:非策略处置的槽占比,直接由同一份 fields 状态复算得出。
        """
        d = deliver.build_deliverable(ws)
        fields = d["docs"][DOC]["fields"]
        want = sum(1 for f in fields.values()
                   if f["status"] not in deliver.POLICY_STATUSES) / len(fields)
        assert d["summary"]["decision_load_for_release"] == want
        assert d["summary"]["policy_disposed_slots"] == 1, \
            "策略处置了几个槽要单独摆出来,不能只给一个比例"

    def test_deciding_a_slot_does_not_change_the_workload_figure(self, ws):
        """它衡量的是「这份策略要人碰几个槽」,不是「还剩几个没碰」。"""
        before = deliver.build_deliverable(ws)["summary"][
            "decision_load_for_release"]
        _decide(ws, "total_gross", "accept")
        after = deliver.build_deliverable(ws)["summary"][
            "decision_load_for_release"]
        assert before == after
