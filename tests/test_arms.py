"""对照臂共享装置:槽位抽样 + slot pack(见 docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md)。

两条性质值得钉死:抽样可复算(否则"预注册了名单"是空话),
以及 pack 里**没有真值** —— 真值是裁判,不是任何一臂的输入。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import arms


def _matrix() -> dict:
    """一个 mini support_matrix:6 个 review 槽 + 2 个已自动放行的。"""
    rows = []
    for i in range(6):
        rows.append({
            "doc_id": f"doc{i//2}", "field": ["due_date", "total_vat"][i % 2],
            "value": "" if i % 2 else "2024-01-31",
            "claim_id": None if i % 2 else f"FC-{i:04d}",
            "support_strength": "unsupported" if i % 2 else "corroborated",
            "source_tiers": [], "applicability": "matches",
            "limitations": ["visual_not_measured"],
            "gate_verdicts": {"extraction_present": "fail"},
            "span_ids": [], "cited_span_ids": [],
            "blocking_findings": ["GF-0005"],
            "reason_codes": ["SLOT_BLOCKING"],
            "route": "review",
            # 真值绝不该出现在 pack 里,但 matrix 行里放一个同名键当诱饵
            "truth_value": "SHOULD-NEVER-LEAK",
        })
    rows.append({"doc_id": "doc9", "field": "due_date", "route": "auto_accept"})
    rows.append({"doc_id": "doc9", "field": "total_vat", "route": "auto_absent"})
    return {"rows": rows}


class TestSampleSlots:
    def test_returns_exactly_n_keys_from_the_review_pool_only(self):
        keys = arms.sample_slots(_matrix(), "deadbeef", n=4)
        assert len(keys) == 4
        assert len(set(keys)) == 4, "不许重复"
        assert all(k.startswith("doc0|") or k.startswith("doc1|")
                   or k.startswith("doc2|") for k in keys), \
            "auto_accept / auto_absent 的槽不在池里"

    def test_same_seed_same_sample(self):
        a = arms.sample_slots(_matrix(), "deadbeef", n=4)
        b = arms.sample_slots(_matrix(), "deadbeef", n=4)
        assert a == b, "同种子必须同名单,否则预注册名单毫无意义"

    def test_different_seed_different_sample(self):
        a = arms.sample_slots(_matrix(), "deadbeef", n=4)
        b = arms.sample_slots(_matrix(), "feedface", n=4)
        assert a != b

    def test_row_order_does_not_change_the_sample(self):
        m = _matrix()
        shuffled = {"rows": list(reversed(m["rows"]))}
        assert arms.sample_slots(m, "deadbeef", n=4) == \
            arms.sample_slots(shuffled, "deadbeef", n=4), \
            "抽样前必须排序 —— 否则工件的行序会偷偷决定名单"

    def test_asking_for_more_than_the_pool_raises(self):
        with pytest.raises(ValueError, match="池只有"):
            arms.sample_slots(_matrix(), "deadbeef", n=99)


class TestSlotPack:
    def test_pack_carries_the_facts_a_reviewer_is_shown(self):
        pack = arms.slot_pack(_matrix(), "doc0|due_date")
        for key in ("doc_id", "field", "value", "support_strength",
                    "applicability", "limitations", "gate_verdicts",
                    "reason_codes", "blocking_findings", "span_ids",
                    "cited_span_ids"):
            assert key in pack, f"复核者看得到 {key},agent 也必须看得到"

    def test_pack_never_carries_truth(self):
        """真值是裁判,不是输入。两臂都在看不到真值的情况下判。"""
        pack = arms.slot_pack(_matrix(), "doc0|due_date")
        assert "SHOULD-NEVER-LEAK" not in json.dumps(pack, ensure_ascii=False)
        assert not any("truth" in k for k in pack), \
            "pack 里任何带 truth 的键都是泄题"

    def test_pack_never_carries_a_decision(self):
        """对方臂的裁决更不能进 —— 那是直接抄答案。"""
        pack = arms.slot_pack(_matrix(), "doc0|due_date")
        assert not any(k in pack for k in
                       ("decision", "human_action", "adjudicator", "rationale"))

    def test_both_arms_get_a_byte_identical_pack(self):
        """同一个槽建两次 pack 必须逐字节相同,否则两臂看的不是同一题。"""
        a = arms.slot_pack(_matrix(), "doc0|due_date")
        b = arms.slot_pack(_matrix(), "doc0|due_date")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_unknown_slot_raises_rather_than_returning_empty(self):
        with pytest.raises(KeyError, match="doc404"):
            arms.slot_pack(_matrix(), "doc404|due_date")
