from __future__ import annotations

import json

import pytest

from invoiceloop import scope


def test_scope_digest_is_order_independent_for_batch_membership():
    one = scope.build_scope("us_broadcast_ad_billing", ["b", "a"],
                            approved_by="human", approved_at="2026-08-09")
    two = scope.build_scope("us_broadcast_ad_billing", ["a", "b"],
                            approved_by="human", approved_at="2026-08-09")
    assert one == two
    assert one["doc_ids_sha256"] == scope.doc_ids_digest(["a", "b"])


def test_scope_requires_exact_membership_and_domain():
    value = scope.build_scope("us_broadcast_ad_billing", ["a", "b"],
                              approved_by="human", approved_at="2026-08-09")
    assert scope.validate_scope(value, ["b", "a"],
                                required_domain="us_broadcast_ad_billing") == value
    with pytest.raises(ValueError, match="doc_ids_sha256"):
        scope.validate_scope(value, ["a", "c"],
                             required_domain="us_broadcast_ad_billing")
    with pytest.raises(ValueError, match="不符"):
        scope.validate_scope(value, ["a", "b"], required_domain="generic")


def test_missing_workspace_scope_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="domain_scope.json"):
        scope.require_workspace_scope(
            tmp_path, ["a"], "us_broadcast_ad_billing")


def test_workspace_scope_is_json_and_domain_scoped(tmp_path):
    value = scope.build_scope("us_broadcast_ad_billing", ["a"],
                              approved_by="human", approved_at="2026-08-09")
    (tmp_path / scope.SCOPE_FILENAME).write_text(
        json.dumps(value), encoding="utf-8")
    loaded = scope.require_workspace_scope(
        tmp_path, ["a"], "us_broadcast_ad_billing")
    assert loaded["domain"] == "us_broadcast_ad_billing"


class TestBroadcastClassify:
    """broadcast-pilot-v1 选择规则的合成词单测 —— 行为必须与 pilot 冻结
    实现逐字一致(SEALED-4 增补件 A1 的名单复算锚依赖它)。"""

    def test_strong_needs_callsign_and_two_term_occurrences(self):
        out = scope.classify_broadcast_words(
            ["KGO-TV", "Advertiser", "spot", "invoice"])
        assert out["strength"] == "strong"
        assert out["callsigns"] == ["KGO-TV"]
        assert out["keyword_occurrences"] == 2

    def test_weak_is_one_sided_evidence(self):
        callsign_only = scope.classify_broadcast_words(["WABC", "invoice"])
        assert callsign_only["strength"] == "weak"
        terms_only = scope.classify_broadcast_words(
            ["advertiser", "agency", "invoice"])
        assert terms_only["strength"] == "weak"
        # 同一术语出现两次也算两次(occurrences 不是 distinct)
        repeated = scope.classify_broadcast_words(["spot", "spot"])
        assert repeated["strength"] == "weak"

    def test_single_term_occurrence_is_none(self):
        out = scope.classify_broadcast_words(["spot", "invoice"])
        assert out["strength"] == "none"

    def test_callsign_pattern(self):
        assert scope.CALLSIGN.fullmatch("KGO")
        assert scope.CALLSIGN.fullmatch("WABC")
        assert scope.CALLSIGN.fullmatch("KGO-TV")
        assert scope.CALLSIGN.fullmatch("WXYZ-FM")
        assert not scope.CALLSIGN.fullmatch("KABCD")   # 呼号主体至多 3 字母
        assert not scope.CALLSIGN.fullmatch("1ABC")
        assert not scope.CALLSIGN.fullmatch("KGO-TV2")

    def test_matching_is_case_insensitive(self):
        out = scope.classify_broadcast_words(["kgo-tv", "ADVERTISER", "Spot"])
        assert out["strength"] == "strong"

    def test_terms_match_as_substrings(self):
        """冻结实现就是子串计数(lower.count):spotlight 里的 spot 照算。
        不是理想分词,但改它 = 名单不可复算,先钉行为。"""
        out = scope.classify_broadcast_words(["spotlight", "spot"])
        assert out["keyword_occurrences"] == 2
