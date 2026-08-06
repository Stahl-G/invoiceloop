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

    def test_reason_decision_combo_is_checked(self, ws):
        """评审裁决六:CONFIRMED_ABSENT 心码不能挂在 accept 上 —— 点错的
        心码会把错误监督喂给 mining。"""
        with pytest.raises(ValueError, match="只能搭配"):
            adjudicate.append_adjudication(
                ws / "runs" / "run-0001",
                claim_id=_claim_id(ws / "runs" / "run-0001", "total_gross"),
                doc_id=DOC, field="total_gross", decision="accept",
                rationale="r", adjudicator="t", decided_at=DECIDED,
                reason_code="CONFIRMED_ABSENT")

    def test_unstated_confidence_stays_actionable(self, ws):
        """2026-08-06 修订:未填把握度不再取消资格。

        原判据要求 high/medium,run-0002 实测填写率 3/123 → 合格事件 0,
        挖掘臂从未点火。不对称:主动标 low 是真信息,未填不等于有把握。
        """
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="r",
            adjudicator="t", decided_at=DECIDED,
            reason_code="ROUTING_FALSE_POSITIVE")  # 没给把握度
        (e,) = improve.compile_workspace(ws)
        assert e["actionable"] is True, \
            "未填把握度的事件仍可作改进标签(合格门只看心码/弃权/主动标低)"

    def test_low_confidence_disqualifies(self, ws):
        """人主动说「没把握」是真信息 —— 这条仍然出局。"""
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="r",
            adjudicator="t", decided_at=DECIDED,
            reason_code="ROUTING_FALSE_POSITIVE", reviewer_confidence="low")
        (e,) = improve.compile_workspace(ws)
        assert e["actionable"] is False
        report = improve.mine(ws)
        assert report["buckets"]["not_actionable_reasons"]["low_confidence"] == 1

    def test_actionable_still_requires_reason_code(self, ws):
        """心码仍是硬要求 —— 没有心码就没有监督标签,不许系统代填。"""
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="r",
            adjudicator="t", decided_at=DECIDED)
        (e,) = improve.compile_workspace(ws)
        assert e["actionable"] is False

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
        assert "status" not in manifest, \
            "manifest 只记出生事实,不当第二权威(高级裁决五)"
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
        assert result["safety_status"] == "unscored", \
            "合成 fixture 无 DocILE 标注 → 不假装过了 Gate 2"
        assert "note" in result and "反事实" in result["note"], \
            "unscored 时仍须声明不给安全性结论"
        assert "不给安全性结论" in result["note"]

        # promote 必须人名+理由+时间
        with pytest.raises(ValueError, match="approved_by"):
            improve.promote(ws, "HAR-0002", approved_by=" ",
                            rationale="r", approved_at=DECIDED)
        record = improve.promote(ws, "HAR-0002", approved_by="y",
                                 rationale="残余风险接受:cohort 仅 TIER2 软触发",
                                 approved_at=DECIDED)
        assert record["to_harness_id"] == "HAR-0002"
        assert record["action"] == "promote"
        assert record["gate"] == "eval_reexecuted"
        assert record["basis"] == "evo_replay_only", \
            "未经未见资格集的晋升必须如实标 demo activation(评审裁决五)"
        assert record["safety_status"] == "unscored"
        assert record["to_policy_digest"]
        assert record["from_policy_digest"]
        pointer = json.loads((ws / "improve" / "active_harness.json").read_text())
        assert pointer["harness_id"] == "HAR-0002"

        # 回滚 = 新 PROM 记录,回到 HAR-0001(包内默认自动物化)
        rb = improve.rollback(ws, to_harness_id="HAR-0001", approved_by="y",
                              rationale="演示回滚", approved_at=DECIDED)
        assert rb["to_harness_id"] == "HAR-0001"
        pointer = json.loads((ws / "improve" / "active_harness.json").read_text())
        assert pointer["harness_id"] == "HAR-0001"
        # 回滚后再晋升回去,供后续新 run 测试
        improve.promote(ws, "HAR-0002", approved_by="y",
                        rationale="回滚演示完毕,复晋升", approved_at=DECIDED)

        # 同输入重跑:输入指纹不变(同一份证据 —— 配对评测靠它证明),
        # 执行指纹必须变(harness 换代不许重放旧 run)—— 两个身份各司其职
        from invoiceloop.snapshot import build_input_manifest, find_run_by_fingerprint

        old_manifest = json.loads((ws / "runs" / "run-0001" / "input_manifest.json")
                                  .read_text())
        new_manifest = build_input_manifest([DOC], include_vision=False)
        assert old_manifest["fingerprint"] == new_manifest["fingerprint"], \
            "同输入 → 同输入指纹(baseline/candidate 配对就靠它证明)"
        assert old_manifest["execution_fingerprint"] \
            != new_manifest["execution_fingerprint"], \
            "harness 换代 → 执行指纹必须变"
        assert find_run_by_fingerprint(
            ws / "runs", new_manifest["execution_fingerprint"]) is None

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


class TestPromoteSafetyGate:
    """Gate 2:scored 时静默错上升必须拒;不升则可 pareto_gated。"""

    def test_silent_absent_rise_refused(self, ws, monkeypatch):
        from invoiceloop.safety_metrics import write_annotation_stub

        # 真值有 seller_vat_id → 候选 auto_absent 会制造 silent_absent
        write_annotation_stub(
            ws, DOC, {"invoice_number": "INV-42", "seller_vat_id": "DE123"})
        pin_corpus(monkeypatch, ws)
        improve.propose(
            ws, cohort={"id": "AE1", "field": "seller_vat_id"},
            finding="FIND-AE", prediction="p", kind="absent_expected")
        result = improve.evaluate(ws, "HAR-0002")
        assert result["safety_status"] == "scored"
        assert result["silent_absent_candidate"] > result["silent_absent_baseline"]
        with pytest.raises(ValueError, match="Gate 2.*silent_absent"):
            improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                            approved_at=DECIDED)

    def test_safe_absent_cohort_pareto_gated(self, ws, monkeypatch):
        from invoiceloop.safety_metrics import write_annotation_stub

        # 真值有 invoice_number(与抽取一致),seller_vat_id 真值缺席 →
        # auto_absent 不增加 silent_absent
        write_annotation_stub(ws, DOC, {"invoice_number": "INV-42"})
        pin_corpus(monkeypatch, ws)
        improve.propose(
            ws, cohort={"id": "AE1", "field": "seller_vat_id"},
            finding="FIND-AE", prediction="p", kind="absent_expected")
        result = improve.evaluate(ws, "HAR-0002")
        assert result["safety_status"] == "scored"
        assert result["silent_absent_candidate"] <= result["silent_absent_baseline"]
        assert result["silent_wrong_candidate"] <= result["silent_wrong_baseline"]
        assert result["review_load_candidate"] <= result["review_load_baseline"]
        record = improve.promote(ws, "HAR-0002", approved_by="y",
                                 rationale="真值本就空,预期缺失安全",
                                 approved_at=DECIDED)
        assert record["gate"] == "pareto_gated"
        assert record["basis"] == "evo_truth_replay"
        assert "未见封箱" in record["claim_limits"] or "SEALED-2" in record[
            "claim_limits"]

    def test_sealed2_marker_upgrades_basis(self, ws, monkeypatch):
        from invoiceloop.safety_metrics import write_annotation_stub

        write_annotation_stub(ws, DOC, {"invoice_number": "INV-42"})
        pin_corpus(monkeypatch, ws)
        (ws / "improve").mkdir(exist_ok=True)
        (ws / "improve" / "sealed2_qualified.ok").write_text("ok\n")
        improve.propose(
            ws, cohort={"id": "AE1", "field": "seller_vat_id"},
            finding="FIND-AE", prediction="p", kind="absent_expected")
        improve.evaluate(ws, "HAR-0002")
        record = improve.promote(ws, "HAR-0002", approved_by="y",
                                 rationale="SEALED-2 资格已挂",
                                 approved_at=DECIDED)
        assert record["basis"] == "sealed2_qualified"
        assert record["gate"] == "pareto_gated"
    """83 评 P0-1 + 高级裁决四的攻击链,逐条钉死。"""

    def _candidate(self, ws):
        improve.propose(ws, cohort={"id": "C1", "field": "seller_name",
                                    "strength": "corroborated"},
                        finding="FIND-1", prediction="review -1 slot")
        return ws / "harnesses" / "HAR-0002" / "routing_policy.json"

    def test_promote_without_eval_refused(self, ws):
        """评审攻击链原样复现:propose → 手改 policy → 跳过 evaluate →
        promote 必须拒。"""
        policy_path = self._candidate(ws)
        policy = json.loads(policy_path.read_text())
        policy["release_tier1_explicit"] = False
        policy_path.write_text(json.dumps(policy, indent=1) + "\n")
        with pytest.raises(ValueError, match="未评测"):
            improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                            approved_at=DECIDED)

    def test_promote_after_policy_tamper_refused(self, ws):
        """evaluate 之后把候选政策再改一个字节(哪怕 lint 仍过),promote
        重算比对必须抓。"""
        policy_path = self._candidate(ws)
        improve.evaluate(ws, "HAR-0002")
        policy = json.loads(policy_path.read_text())
        policy["auto_accept_cohorts"].append(
            {"id": "C2", "field": "buyer_name", "strength": "corroborated"})
        policy_path.write_bytes(
            (json.dumps(policy, indent=1, ensure_ascii=False) + "\n").encode())
        with pytest.raises(ValueError, match="逐字节不符"):
            improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                            approved_at=DECIDED)

    def test_promote_after_input_tamper_refused(self, ws):
        """evaluate 之后往裁决账本追加一条(输入身份变化),promote 必须拒。"""
        self._candidate(ws)
        improve.evaluate(ws, "HAR-0002")
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="r",
            adjudicator="t", decided_at=DECIDED)
        with pytest.raises(ValueError, match="逐字节不符"):
            improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                            approved_at=DECIDED)

    def test_promote_with_zero_coverage_refused(self, ws):
        """零受评槽的空评测不构成晋升依据。"""
        self._candidate(ws)
        improve.evaluate(ws, "HAR-0002")
        # 手搓一个零覆盖 eval(名字骗不过重算,这里直接验零覆盖分支:
        # 先把 runs 改名让重算得到零覆盖,与存盘一致)
        for run in (ws / "runs").glob("run-*"):
            run.rename(run.with_name(run.name.replace("run-", "archived-")))
        improve.evaluate(ws, "HAR-0002")  # 零 run 的 eval,落盘与重算一致
        with pytest.raises(ValueError, match="覆盖为零"):
            improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                            approved_at=DECIDED)

    def test_forged_pointer_refused(self, ws):
        """83 评攻击:伪造 active_harness.json 指向无晋升记录的 harness。"""
        from invoiceloop import harness

        (ws / "harnesses" / "HAR-9999").mkdir(parents=True)
        (ws / "harnesses" / "HAR-9999" / "routing_policy.json").write_text(
            (ws / "harnesses" / "HAR-0002" / "routing_policy.json").read_text()
            if (ws / "harnesses" / "HAR-0002").exists()
            else json.dumps(harness._builtin_policy()))
        (ws / "improve").mkdir(exist_ok=True)
        (ws / "improve" / "active_harness.json").write_text(json.dumps(
            {"harness_id": "HAR-9999", "promotion_id": "PROM-0009"}))
        with pytest.raises(RuntimeError, match="伪造的指针"):
            harness.load_active(ws)

    def test_policy_tamper_after_promote_detected(self, ws):
        """晋升后改政策文件,链重放必须拒(指针与记录都没动也没用)。"""
        from invoiceloop import harness

        self._candidate(ws)
        improve.evaluate(ws, "HAR-0002")
        improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                        approved_at=DECIDED)
        policy_path = ws / "harnesses" / "HAR-0002" / "routing_policy.json"
        policy = json.loads(policy_path.read_text())
        policy["auto_accept_cohorts"].append({"id": "EVIL"})
        policy_path.write_text(json.dumps(policy, indent=1) + "\n")
        with pytest.raises(RuntimeError, match="被改过"):
            harness.load_active(ws)

    def test_hash_chain_gap_detected(self, ws):
        """删掉链中间一条记录,文件名连续性校验必须拒。"""
        from invoiceloop import harness

        self._candidate(ws)
        improve.evaluate(ws, "HAR-0002")
        improve.promote(ws, "HAR-0002", approved_by="y", rationale="r",
                        approved_at=DECIDED)
        improve.rollback(ws, to_harness_id="HAR-0001", approved_by="y",
                         rationale="演示", approved_at=DECIDED)
        (ws / "improve" / "promotions" / "PROM-0001.json").unlink()
        with pytest.raises(RuntimeError, match="不连续"):
            harness.load_active(ws)

    def test_rollback_to_never_active_refused(self, ws):
        """「回滚」到从未活跃过的 harness = 绕门晋升,必须拒。"""
        self._candidate(ws)  # HAR-0002 存在但从未晋升
        with pytest.raises(ValueError, match="从未在晋升链上活跃过"):
            improve.rollback(ws, to_harness_id="HAR-0002", approved_by="y",
                             rationale="伪装回滚", approved_at=DECIDED)


class TestMineQualityGate:
    """83 评问题三:mining 只用合格反馈。"""

    def test_superseded_events_counted_but_not_mined(self, ws):
        run_dir = ws / "runs" / "run-0001"
        first = adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="看错了",
            adjudicator="t", decided_at=DECIDED,
            reason_code="ROUTING_FALSE_POSITIVE", reviewer_confidence="high")
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="correct", rationale="重看后修正",
            adjudicator="t", decided_at="2026-08-05T04:00:00",
            corrected_value="101.00",
            supersedes_decision_id=first["decision_id"],
            reason_code="WRONG_VALUE", reviewer_confidence="high")
        events = improve.compile_workspace(ws)
        by_id = {e["decision_id"]: e for e in events}
        assert by_id[first["decision_id"]]["superseded"] is True
        report = improve.mine(ws)
        assert report["buckets"]["all_events"] == 2
        assert report["buckets"]["superseded"] == 1
        assert report["buckets"]["qualified_for_mining"] == 1, \
            "被顶替的事件留在账本分桶里,但不进 cohort 统计"
        cohorts = {(c["field"]): c for c in report["cohorts"]}
        assert cohorts["total_gross"]["corrected"] == 1
        assert cohorts["total_gross"]["accepted"] == 0, \
            "tip 是 correct,被顶替的 accept 不许进统计"

    def test_non_actionable_events_not_mined(self, ws):
        """质量门仍然咬人 —— 2026-08-06 只换了「不合格」的判据:
        从「没填把握度」改成「没给心码 / 主动标了低把握 / 弃权」。"""
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="r",
            adjudicator="t", decided_at=DECIDED)  # 无心码 → 不可行动
        report = improve.mine(ws)
        assert report["buckets"]["all_events"] == 1
        assert report["buckets"]["qualified_for_mining"] == 0
        assert report["buckets"]["not_actionable_reasons"]["no_reason_code"] == 1
        assert report["cohorts"] == [], \
            "不可行动事件不进 cohort —— 低收益候选不许建在没有监督标签的记录上"

    def test_overturned_auto_accept_is_reported_even_from_a_qa_probe(self, ws):
        """策略自动放行、人推翻 —— 撤销该 cohort 的证据。

        与放松线索不对称:一条就报,不设频次门槛,QA 探针抓到的也算数
        (探针存在的理由就是抓这个)。
        """
        run_dir = ws / "runs" / "run-0001"
        matrix = json.loads((run_dir / "support_matrix.json").read_text("utf-8"))
        row = next(r for r in matrix["rows"] if r["field"] == "total_gross")
        row["route"] = "auto_accept"
        row["reason_codes"] = ["CLEAN", "QA_SAMPLE:policy_accepted_tier1"]
        (run_dir / "support_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="reject",
            rationale="页面上印的是 Fed. I.D.,不是 VAT 号",
            adjudicator="t", decided_at=DECIDED,
            reason_code="WRONG_FIELD_MAPPING")
        report = improve.mine(ws)
        (o,) = report["overturned_auto_accepts"]
        assert o["field"] == "total_gross" and o["human_action"] == "reject"
        assert o["random_qa"] is True, "QA 探针抓到的推翻照样进撤销信号"
        assert o["rationale"].startswith("页面上印的是")
        assert report["low_yield_candidates"] == [], \
            "推翻不是放松线索 —— 不许混进候选"

    def test_reviewed_slot_overturn_is_not_a_revocation_signal(self, ws):
        """route=review 的槽被 correct 是正常工作,不是策略出错。"""
        run_dir = ws / "runs" / "run-0001"
        matrix = json.loads((run_dir / "support_matrix.json").read_text("utf-8"))
        row = next(r for r in matrix["rows"] if r["field"] == "total_gross")
        row["route"] = "review"
        (run_dir / "support_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="correct", corrected_value="1.00",
            rationale="值不对", adjudicator="t", decided_at=DECIDED,
            reason_code="WRONG_VALUE")
        assert improve.mine(ws)["overturned_auto_accepts"] == []

    def test_rationale_reaches_the_cohort_verbatim(self, ws):
        """复核者手打的话必须能被改进层看到 —— 2026-08-06 之前它停在
        裁决账本里,反馈事件根本不带这个字段。原文透传,不解析。"""
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept",
            rationale="页面右下角还有一个小写的 total,DWS 取的是大写那个",
            adjudicator="t", decided_at=DECIDED,
            reason_code="ROUTING_FALSE_POSITIVE")
        (e,) = improve.compile_workspace(ws)
        assert e["rationale"].startswith("页面右下角"), "事件要带原话"
        report = improve.mine(ws)
        (cohort,) = report["cohorts"]
        assert cohort["notes"] == [{
            "doc_id": DOC, "decision": "accept",
            "reason_code": "ROUTING_FALSE_POSITIVE",
            "rationale": "页面右下角还有一个小写的 total,DWS 取的是大写那个",
        }], "原话按 cohort 归堆,一字不改 —— 给写提案的人读"

    def test_low_confidence_events_not_mined(self, ws):
        """主动标「没把握」的记录同样出局 —— 这条是真信息,要听。"""
        run_dir = ws / "runs" / "run-0001"
        adjudicate.append_adjudication(
            run_dir, claim_id=_claim_id(run_dir, "total_gross"), doc_id=DOC,
            field="total_gross", decision="accept", rationale="r",
            adjudicator="t", decided_at=DECIDED,
            reason_code="ROUTING_FALSE_POSITIVE", reviewer_confidence="low")
        report = improve.mine(ws)
        assert report["buckets"]["qualified_for_mining"] == 0
        assert report["cohorts"] == []


class TestAbsentExpectedLoop:
    """预期缺失 cohort 的完整闭环(2026-08-06 HITL 实测驱动):
    人反复 confirm_absent 的字段 → absent_expected cohort → 门禁记
    expected_absent → 路由 auto_absent → 交付 policy_confirmed_absent。"""

    def test_full_loop(self, ws):
        from invoiceloop import deliver

        cand = improve.propose(
            ws, cohort={"id": "AE1", "field": "seller_vat_id"},
            finding="FIND-AE:seller_vat_id 的确认缺失占满队列(美国发票无 VAT)",
            prediction="seller_vat_id 缺值槽出队", kind="absent_expected")
        result = improve.evaluate(ws, "HAR-0002")
        assert result["review_load_candidate"] \
            <= result["review_load_baseline"], "预期缺失只许减负载"
        improve.promote(ws, "HAR-0002", approved_by="y",
                        rationale="人反复确认缺失 = 预期缺失;QA 20% 盯着",
                        approved_at=DECIDED)
        pipeline_run([DOC], ws / "runs" / "run-0002", include_vision=False,
                     out_of_calibration=True)
        gate = json.loads((ws / "runs" / "run-0002" / "gate_report.json")
                          .read_text())
        verdict = gate["evaluations"][DOC]["seller_vat_id"]["extraction_present"]
        assert verdict == "expected_absent", \
            "缺值事实照记(不是 pass),后果从阻断降级"
        finding = next(f for f in gate["findings"]
                       if f["field"] == "seller_vat_id")
        assert finding["blocking"] is False
        routing = json.loads((ws / "runs" / "run-0002" / "routing_report.json")
                             .read_text())
        route = next(r for r in routing["routes"]
                     if r["field"] == "seller_vat_id")
        assert route["route"] in ("auto_absent", "review"), route
        if route["route"] == "review":
            assert "QA_SAMPLE:expected_absent" in route["reason_codes"], \
                "预期缺失进人工只许是 QA 抽检"
        d = deliver.build_deliverable(ws / "runs" / "run-0002")
        slot = d["docs"][DOC]["fields"]["seller_vat_id"]
        if route["route"] == "auto_absent":
            assert slot["status"] == "policy_confirmed_absent"
            assert slot["value"] is None
            assert slot["source"] == "policy:HAR-0002"

    def test_lint_guards_absent_whitelist(self, ws):
        with pytest.raises(ValueError, match="白名单外特征"):
            improve.propose(ws, cohort={"id": "AE1", "field": "seller_vat_id",
                                        "doc_id": "046e0c49"},
                            finding="F", prediction="p", kind="absent_expected")
