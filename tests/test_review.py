"""裁决投影纯函数:target 稳定、supersession 链确定、v1 旧条目串链、冲突显式。"""

from __future__ import annotations

import json

from invoiceloop.review import load_decisions, project, project_run, target_id_for

SID = "s" * 64
DECIDED = "2026-08-03T10:00:00"


def _run_dir(tmp_path):
    (tmp_path / "review_snapshot.json").write_text(
        json.dumps({"review_snapshot_id": SID, "components": {}}), encoding="utf-8")
    return tmp_path


def _v2(seq, target, decision, supersedes=None):
    return {"seq": seq, "decision_id": f"HD-{seq:04d}", "review_snapshot_id": SID,
            "target_id": target, "claim_id": None, "doc_id": "doc-a",
            "field": "total_gross", "decision": decision, "corrected_value": None,
            "rationale": "r", "adjudicator": "y", "decided_at": DECIDED,
            "supersedes_decision_id": supersedes}


class TestTargetId:
    def test_stable_and_input_sensitive(self):
        a = target_id_for(SID, "doc-a", "total_gross")
        assert a == target_id_for(SID, "doc-a", "total_gross")
        assert a.startswith("T-")
        assert a != target_id_for("t" * 64, "doc-a", "total_gross")
        assert a != target_id_for(SID, "doc-b", "total_gross")
        assert a != target_id_for(SID, "doc-a", "total_net")


class TestProject:
    def test_tip_follows_supersession_chain_not_row_order(self):
        target = target_id_for(SID, "doc-a", "total_gross")
        chain = [_v2(1, target, "accept"),
                 _v2(2, target, "reject", supersedes="HD-0001"),
                 _v2(3, target, "abstain", supersedes="HD-0002")]
        slot = project(list(reversed(chain)))[target]  # 顺序打乱,投影必须一样
        assert slot["tip"]["decision_id"] == "HD-0003"
        assert [e["seq"] for e in slot["history"]] == [1, 2, 3]
        assert not slot["conflict"]

    def test_broken_chain_is_conflict_not_a_guess(self):
        target = target_id_for(SID, "doc-a", "total_gross")
        slot = project([_v2(1, target, "accept"), _v2(2, target, "reject")])[target]
        assert slot["conflict"] is True and slot["tip"] is None

    def test_empty_run_projects_empty(self, tmp_path):
        assert project_run(_run_dir(tmp_path)) == {}


class TestLegacyV1:
    def _write_v1(self, d, lines):
        (d / "adjudication_ledger.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines),
            encoding="utf-8")

    def test_v1_entries_get_synthetic_ids_and_implicit_chain(self, tmp_path):
        d = _run_dir(tmp_path)
        v1a = {"seq": 1, "claim_id": "FC-0001", "doc_id": "doc-a",
               "field": "total_gross", "decision": "accept",
               "corrected_value": None, "rationale": "旧账",
               "adjudicator": "y", "decided_at": "2026-08-02T10:00:00"}
        v1b = {**v1a, "seq": 2, "decision": "correct",
               "corrected_value": "21000.00", "rationale": "旧账改判"}
        self._write_v1(d, [v1a, v1b])
        decisions = load_decisions(d)
        assert all(e["decision_id"].startswith("legacy-") for e in decisions)
        assert all(e["legacy"] for e in decisions)
        assert decisions[1]["supersedes_decision_id"] == decisions[0]["decision_id"], \
            "同槽位的 v1 连续条目按 seq 隐式串链(v1 当时的语义)"
        target = target_id_for(SID, "doc-a", "total_gross")
        slot = project(decisions)[target]
        assert slot["tip"]["decision"] == "correct" and not slot["conflict"]

    def test_v2_decision_can_supersede_legacy_tip(self, tmp_path):
        d = _run_dir(tmp_path)
        v1 = {"seq": 1, "claim_id": None, "doc_id": "doc-a", "field": "total_gross",
              "decision": "accept", "corrected_value": None, "rationale": "旧账",
              "adjudicator": "y", "decided_at": "2026-08-02T10:00:00"}
        self._write_v1(d, [v1])
        legacy_tip = load_decisions(d)[0]["decision_id"]
        target = target_id_for(SID, "doc-a", "total_gross")
        v2 = _v2(2, target, "reject", supersedes=legacy_tip)
        (d / "adjudication_ledger.jsonl").open("a").write(json.dumps(v2) + "\n")
        slot = project_run(d)[target]
        assert slot["tip"]["decision_id"] == "HD-0002" and not slot["conflict"]
