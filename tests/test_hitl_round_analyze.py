"""hitl_round_analyze 的单测:计时口径与建议采纳率(协议 §3 的机械定义)。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hitl_round_analyze as hra  # noqa: E402


def _entry(seq, ts, decision="accept", **kw):
    base = {"seq": seq, "decision_id": f"HD-{seq:04d}", "doc_id": "d",
            "field": "total_gross", "decision": decision,
            "decided_at": ts, "claim_id": "FC-0001"}
    base.update(kw)
    return base


class TestPerSlotSeconds:
    def test_median_and_rest_gap_exclusion(self):
        entries = [
            _entry(1, "2026-08-11T01:00:00+00:00"),
            _entry(2, "2026-08-11T01:00:20+00:00"),
            _entry(3, "2026-08-11T01:00:50+00:00"),
            # 隔夜:间隔 12h,剔除,但不阻断后续计时
            _entry(4, "2026-08-11T13:00:50+00:00"),
            _entry(5, "2026-08-11T13:01:20+00:00"),
        ]
        out = hra.per_slot_seconds(entries)
        assert out["n_timed"] == 3
        assert out["median_seconds"] == 30.0
        assert out["excluded_gaps"] == 1

    def test_by_decision(self):
        entries = [
            _entry(1, "2026-08-11T01:00:00+00:00"),
            _entry(2, "2026-08-11T01:00:20+00:00"),
            _entry(3, "2026-08-11T01:01:26+00:00", decision="correct",
                   corrected_value="9.99"),
        ]
        out = hra.per_slot_seconds(entries)
        assert out["by_decision"]["accept"]["median_seconds"] == 20.0
        assert out["by_decision"]["correct"]["median_seconds"] == 66.0


class TestSuggestionAdoption:
    CLAIMS = {"FC-0001": {"claim_id": "FC-0001", "value": "100.00"},
              "FC-0002": {"claim_id": "FC-0002", "value": "55.00"}}

    def test_rate_and_states(self):
        entries = [
            # 采纳:accept 的声明值与建议规范化一致
            _entry(1, "2026-08-11T01:00:00+00:00",
                   suggestion_seen="agree:$100.00"),
            # 未采纳:声明值不同
            _entry(2, "2026-08-11T01:00:10+00:00", claim_id="FC-0002",
                   suggestion_seen="agree:100.00"),
            # 采纳:correct 修正值 = 建议值
            _entry(3, "2026-08-11T01:00:20+00:00", decision="correct",
                   corrected_value="100.00", suggestion_seen="agree:100"),
            # 不进分母的状态
            _entry(4, "2026-08-11T01:00:30+00:00",
                   suggestion_seen="split"),
            _entry(5, "2026-08-11T01:00:40+00:00",
                   suggestion_seen="agree_rejected:10.00"),
        ]
        out = hra.suggestion_adoption(entries, self.CLAIMS)
        assert out["agree_slots"] == 3
        assert out["adopted"] == 2
        assert out["adoption_rate"] == round(2 / 3, 4)
        assert out["by_state"] == {"agree": 3, "split": 1,
                                   "agree_rejected": 1}
        assert len(out["misses"]) == 1

    def test_empty_denominator(self):
        out = hra.suggestion_adoption([], {})
        assert out["adoption_rate"] is None
