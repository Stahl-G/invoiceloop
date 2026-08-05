"""routing 层(P0-3)语义钉死:

- HAR-0001(空 cohorts)与 2026-08-05 前 matrix 内联判据逐字节等价;
- cohort 只能放松软触发(warning 级);fail/unsupported/争议/阻断是硬阻断,
  cohort 匹配中了也不许放行(v0.2 §11.2);
- cohort 只引用通用特征(field/tier/strength);
- routing_report 进快照成分;删除它 → 快照对不上。
"""

from __future__ import annotations

import json

from invoiceloop.routing import build_routing_report, policy_digest, route_slots


def _slot(strength="corroborated", verdicts=None, disputed=False,
          slot_blocking=False, doc_blocked=False, field="seller_name"):
    return {"doc_id": "d1", "field": field, "strength": strength,
            "gate_verdicts": verdicts or {},
            "applicability": "label_convention_disputed" if disputed else "matches",
            "slot_blocking": slot_blocking, "doc_blocked": doc_blocked}


HAR1 = {"harness_id": "HAR-0001", "version": 1,
        "release_tier1_explicit": True, "auto_accept_cohorts": []}


def _tier(f):
    from invoiceloop.fields import TIER1

    return "TIER1" if f in TIER1 else "TIER2"


class TestDefaultEquivalence:
    """旧内联判据:unsupported | fail | warning | disputed | blocking → requires。"""

    def _old_requires(self, s):
        return (s["strength"] == "unsupported"
                or any(v == "fail" for v in s["gate_verdicts"].values())
                or any(v == "warning" for v in s["gate_verdicts"].values())
                or s["applicability"] == "label_convention_disputed"
                or s["slot_blocking"] or s["doc_blocked"])

    def test_all_fact_shapes_match(self):
        shapes = [
            _slot(),                                              # clean → auto
            _slot(strength="unsupported"),                        # → review
            _slot(verdicts={"citation_holds": "fail"}),           # → review
            _slot(verdicts={"visual_corroboration": "warning"}),  # → review
            _slot(disputed=True),                                 # → review
            _slot(slot_blocking=True),                            # → review
            _slot(doc_blocked=True),                              # → block
            _slot(verdicts={"a": "fail", "b": "warning"}),        # → review
        ]
        routes = route_slots(shapes, HAR1, tier_of=_tier)
        for s, r in zip(shapes, routes):
            assert self._old_requires(s) == (r["route"] != "auto_accept"), \
                f"{s} → {r} 与旧判据不等价"

    def test_reason_codes_name_the_gate(self):
        (r,) = route_slots([_slot(verdicts={"citation_holds": "fail"})],
                           HAR1, tier_of=_tier)
        assert r["reason_codes"] == ["GATE_FAIL:citation_holds"]
        (r,) = route_slots([_slot(doc_blocked=True)], HAR1, tier_of=_tier)
        assert r["route"] == "block" and r["reason_codes"] == ["INFRA_BLOCKED"]


class TestCohortBoundaries:
    RELAX = {**HAR1, "auto_accept_cohorts": [
        {"id": "C1", "field": "seller_name", "strength": "corroborated"}]}

    def test_cohort_relaxes_warning_only_slot(self):
        s = _slot(field="seller_name",
                  verdicts={"visual_corroboration": "warning"})
        (r,) = route_slots([s], self.RELAX, tier_of=_tier)
        assert r["route"] == "auto_accept"
        assert r["reason_codes"] == ["POLICY_ACCEPT:C1"]

    def test_cohort_cannot_relax_hard_blockers(self):
        for s in (_slot(field="seller_name", verdicts={"citation_holds": "fail"}),
                  _slot(field="seller_name", strength="unsupported"),
                  _slot(field="seller_name", disputed=True),
                  _slot(field="seller_name", slot_blocking=True),
                  _slot(field="seller_name", doc_blocked=True)):
            (r,) = route_slots([s], self.RELAX, tier_of=_tier)
            assert r["route"] != "auto_accept", \
                f"硬阻断不许被 cohort 放行:{s}"

    def test_cohort_feature_mismatch_does_not_relax(self):
        s = _slot(field="buyer_name",  # cohort 只管 seller_name
                  verdicts={"visual_corroboration": "warning"})
        (r,) = route_slots([s], self.RELAX, tier_of=_tier)
        assert r["route"] == "review"


class TestSnapshotIntegration:
    def test_routing_report_enters_snapshot_components(self, tmp_path):
        from invoiceloop.snapshot import compute_review_snapshot

        for name in ("input_manifest.json", "artifact_registry.json",
                     "evidence_span_registry.json", "field_ledger.json",
                     "gate_report.json"):
            (tmp_path / name).write_text("{}")
        without = compute_review_snapshot(tmp_path)
        assert "routing_report.json" not in without["components"], \
            "旧 run(无 routing_report)的成分集不许漂移 —— 旧 id 才能复算"
        (tmp_path / "routing_report.json").write_text("{}")
        with_rr = compute_review_snapshot(tmp_path)
        assert "routing_report.json" in with_rr["components"]
        assert with_rr["review_snapshot_id"] != without["review_snapshot_id"], \
            "有无 routing_report 必须是两个快照身份"

    def test_policy_digest_changes_with_policy(self):
        relaxed = {**HAR1, "auto_accept_cohorts": [
            {"id": "C1", "field": "seller_name", "strength": "corroborated"}]}
        assert policy_digest(HAR1) != policy_digest(relaxed)
        assert policy_digest(HAR1) == policy_digest(dict(HAR1)), "确定性"


class TestDeterministicQaSampler:
    """评审裁决四:hash 抽样,确定性,不破「同输入同字节」。"""

    def _policy(self, rate, **over):
        return {**HAR1,
                "release_tier1_explicit": False,
                "qa": {"seed": "s", "policy_accepted_tier1_rate": rate,
                       "cohort_relax_rate": rate},
                **over}

    def test_same_inputs_same_selection(self):
        from invoiceloop.routing import _qa_hit

        p = self._policy(0.5)
        assert _qa_hit(p, "doc-a", "total_gross", "policy_accepted_tier1") \
            == _qa_hit(p, "doc-a", "total_gross", "policy_accepted_tier1")
        # 不同文档采样结果应有差异(不强求某一具体值,验证确实随输入变化)
        results = {_qa_hit(p, f"doc-{i}", "total_gross",
                           "policy_accepted_tier1") for i in range(20)}
        assert len(results) == 2, "rate 0.5 下 20 个文档应既有中又有不中"

    def test_rate_zero_selects_nothing(self):
        from invoiceloop.routing import _qa_hit

        p = self._policy(0.0)
        assert not any(_qa_hit(p, f"doc-{i}", "total_gross",
                               "policy_accepted_tier1") for i in range(50))

    def test_rate_one_selects_everything(self):
        from invoiceloop.routing import _qa_hit

        p = self._policy(1.0)
        assert all(_qa_hit(p, f"doc-{i}", "total_gross",
                           "policy_accepted_tier1") for i in range(50))

    def test_har0001_selects_nothing(self):
        """HAR-0001:tier1_explicit=true 且 cohorts 为空 —— QA 零命中,
        行为守恒(与旧内联判据逐字节等价)不破。"""
        from invoiceloop.harness import load_active

        policy = load_active()["policy"]
        slots = [_slot(field="total_gross"), _slot(field="seller_name")]
        routes = route_slots(slots, policy, tier_of=_tier)
        assert all(not any(c.startswith("QA_SAMPLE")
                           for c in r["reason_codes"]) for r in routes)

    def test_relaxed_cohort_gets_qa_sampled(self):
        policy = {**self._policy(1.0),
                  "auto_accept_cohorts": [
                      {"id": "C1", "field": "seller_name",
                       "strength": "corroborated"}]}
        s = _slot(field="seller_name",
                  verdicts={"visual_corroboration": "warning"})
        (r,) = route_slots([s], policy, tier_of=_tier)
        assert r["route"] == "review"
        assert "QA_SAMPLE:C1" in r["reason_codes"], \
            "刚晋升的 cohort 首批 20% 抽检 —— rate 1.0 时全部进队列"
