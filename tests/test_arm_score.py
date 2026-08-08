"""两臂打分:M1/M2(各臂 vs 真值)与 M3(配对一致 + 混淆矩阵)。

预注册:`docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md` §5。

这些用例钉的主要是**不许把三种不同的东西压成对/错**:
`not_applicable` 与 `abstain` 真值管不着;缺席主张只能被真值**否证**,
不能被真值证实;没标注的槽按项目既有口径不计分(heldout_metrics 同样 skip)。
真值函数注入,用例不碰真语料。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import arm_score as sc


def _row(field="total_vat", value="", claim_id=None):
    return {"doc_id": "doc-a", "field": field, "value": value,
            "claim_id": claim_id, "route": "review"}


def _matrix(*rows):
    return {"rows": list(rows)}


def _tip(field="total_vat", decision="confirm_absent", corrected=None):
    return {"doc_id": "doc-a", "field": field, "decision": decision,
            "corrected_value": corrected, "decision_id": "HD-0001"}


class TestTruthVerdict:
    def test_accept_matching_truth_agrees(self):
        v = sc.truth_verdict(_row("total_vat", "19.00", "FC-1"),
                             _tip("total_vat", "accept"),
                             truth_value="19.00")
        assert v == "agree"

    def test_accept_differing_from_truth_disagrees(self):
        v = sc.truth_verdict(_row("total_vat", "19.00", "FC-1"),
                             _tip("total_vat", "accept"),
                             truth_value="21.00")
        assert v == "disagree"

    def test_accept_uses_the_projects_normalisation(self):
        """'$19.00' 与 '19.00' 是同一个值 —— 口径必须与既有打分一致。"""
        v = sc.truth_verdict(_row("total_vat", "$19.00", "FC-1"),
                             _tip("total_vat", "accept"),
                             truth_value="19.00")
        assert v == "agree"

    def test_accept_without_any_annotation_is_not_scored(self):
        """没标注不等于判错。heldout_metrics 对无标注行是 skip,这里同口径。"""
        v = sc.truth_verdict(_row("total_vat", "19.00", "FC-1"),
                             _tip("total_vat", "accept"), truth_value=None)
        assert v == "no_truth"

    def test_confirm_absent_contradicted_by_truth_disagrees(self):
        """真值有值 → 缺席主张被**否证**,这是静默漏标那类错。"""
        v = sc.truth_verdict(_row("total_vat"), _tip("total_vat", "confirm_absent"),
                             truth_value="19.00")
        assert v == "disagree"

    def test_confirm_absent_with_no_annotation_is_unfalsified_not_proven(self):
        """真值没标 ≠ 页面上真没有(标注者可能漏标)。**不许当成证实。**"""
        v = sc.truth_verdict(_row("total_vat"), _tip("total_vat", "confirm_absent"),
                             truth_value=None)
        assert v == "unfalsified", "叫 agree 会让读者以为真值证实了缺席"

    def test_not_applicable_is_unscoreable_never_wrong(self):
        """真值说不出「这类单据没这个概念」—— 宪章五划给人的判断。"""
        for t in (None, "19.00"):
            v = sc.truth_verdict(_row("total_vat"),
                                 _tip("total_vat", "not_applicable"), truth_value=t)
            assert v == "unscoreable_not_applicable", \
                "把它算错,等于用真值裁决一个真值管不着的问题"

    def test_abstain_is_unscoreable(self):
        v = sc.truth_verdict(_row("total_vat"), _tip("total_vat", "abstain"),
                             truth_value="19.00")
        assert v == "unscoreable_abstain"

    def test_correct_is_scored_on_the_corrected_value(self):
        good = sc.truth_verdict(_row("total_vat", "21.00", "FC-1"),
                                _tip("total_vat", "correct", corrected="19.00"),
                                truth_value="19.00")
        bad = sc.truth_verdict(_row("total_vat", "21.00", "FC-1"),
                               _tip("total_vat", "correct", corrected="22.00"),
                               truth_value="19.00")
        assert (good, bad) == ("agree", "disagree")

    def test_reject_agrees_when_the_extracted_value_really_was_wrong(self):
        v = sc.truth_verdict(_row("total_vat", "21.00", "FC-1"),
                             _tip("total_vat", "reject"), truth_value="19.00")
        assert v == "agree"

    def test_reject_disagrees_when_the_extracted_value_was_right(self):
        v = sc.truth_verdict(_row("total_vat", "19.00", "FC-1"),
                             _tip("total_vat", "reject"), truth_value="19.00")
        assert v == "disagree"


class TestPairing:
    def test_only_slots_in_both_arms_are_paired(self):
        ta = {"doc-a|total_vat": _tip("total_vat", "confirm_absent"),
              "doc-a|due_date": _tip("due_date", "abstain")}
        h2 = {"doc-a|total_vat": _tip("total_vat", "confirm_absent"),
              "doc-a|total_net": _tip("total_net", "accept")}
        p = sc.pair(ta, h2)
        assert p["paired_n"] == 1
        assert p["ta_only"] == ["doc-a|due_date"]
        assert p["h2_only"] == ["doc-a|total_net"]

    def test_unpaired_slots_are_named_not_dropped(self):
        """少掉的槽必须点名 —— 静默取交集会让读者以为两臂都判了 200。"""
        ta = {"a|f1": _tip(), "a|f2": _tip()}
        h2 = {"a|f1": _tip()}
        p = sc.pair(ta, h2)
        assert p["paired_n"] == 1
        assert p["ta_only"] == ["a|f2"], "只有 TA 判过的槽必须点名"
        assert p["h2_only"] == []
        assert "a|f2" in json.dumps(p), "掉队的槽键必须出现在报告里"

    def test_agreement_counts_exact_decision_match(self):
        ta = {"a|f1": _tip("f1", "accept"), "a|f2": _tip("f2", "confirm_absent")}
        h2 = {"a|f1": _tip("f1", "accept"), "a|f2": _tip("f2", "not_applicable")}
        p = sc.pair(ta, h2)
        assert p["paired_n"] == 2
        assert p["agreed"] == 1
        assert p["agreement_rate"] == 0.5

    def test_confusion_matrix_is_six_by_six_and_sums_to_paired_n(self):
        ta = {"a|f1": _tip("f1", "accept"), "a|f2": _tip("f2", "confirm_absent")}
        h2 = {"a|f1": _tip("f1", "reject"), "a|f2": _tip("f2", "not_applicable")}
        p = sc.pair(ta, h2)
        m = p["confusion"]
        assert set(m) == set(sc.DECISIONS)
        assert all(set(row) == set(sc.DECISIONS) for row in m.values())
        assert sum(v for row in m.values() for v in row.values()) == p["paired_n"]

    def test_empty_arms_do_not_divide_by_zero(self):
        p = sc.pair({}, {})
        assert p["paired_n"] == 0 and p["agreement_rate"] is None


class TestLoadArm:
    def test_only_the_tip_decision_counts(self, tmp_path):
        """同一槽被改判过 → 只算最终那条(review.project 的链投影)。"""
        run = tmp_path
        rows = [
            {"seq": 1, "decision_id": "HD-0001", "target_id": "T1",
             "doc_id": "doc-a", "field": "total_vat", "decision": "accept",
             "claim_id": "FC-1", "corrected_value": None,
             "review_snapshot_id": "RS-1",
             "supersedes_decision_id": None},
            {"seq": 2, "decision_id": "HD-0002", "target_id": "T1",
             "doc_id": "doc-a", "field": "total_vat", "decision": "reject",
             "claim_id": "FC-1", "corrected_value": None,
             "review_snapshot_id": "RS-1",
             "supersedes_decision_id": "HD-0001"},
        ]
        (run / "review_snapshot.json").write_text(
            json.dumps({"review_snapshot_id": "RS-1"}), encoding="utf-8")
        (run / "adjudication_ledger.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        arm = sc.load_arm(run)
        assert arm["doc-a|total_vat"]["decision"] == "reject"

    def test_missing_ledger_is_an_empty_arm_not_a_crash(self, tmp_path):
        assert sc.load_arm(tmp_path) == {}
