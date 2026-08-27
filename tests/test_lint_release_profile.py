"""机器不许 propose 放行契约 —— 改宽 release_profile = 把「谁能免复核」
这个决定从人手里拿走。lint 的白名单哪天放松了,这条会红。"""

from __future__ import annotations

import pytest

from invoiceloop.improve import lint_policy

PARENT = {
    "harness_id": "HAR-0021",
    "version": 1,
    "auto_accept_cohorts": [],
    "absent_expected_cohorts": [],
}


def test_machine_cannot_introduce_a_release_profile():
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2,
                 "release_profile": {"id": "payment_required_v1",
                                     "fields": ["invoice_number",
                                                "seller_name", "amount_due"]}}
    violations = lint_policy(PARENT, candidate)
    assert any("release_profile" in v for v in violations), violations


def test_machine_cannot_widen_an_existing_release_profile():
    parent = {**PARENT, "release_profile": {"id": "payment_required_v1",
                                            "fields": ["invoice_number"]}}
    candidate = {**parent, "harness_id": "HAR-0099", "version": 2,
                 "release_profile": {"id": "payment_required_v1",
                                     "fields": ["invoice_number",
                                                "seller_name"]}}
    violations = lint_policy(parent, candidate)
    assert any("release_profile" in v for v in violations), violations


def test_machine_cannot_flip_tier1_explicit():
    """release_tier1_explicit: false 会把 TIER1 自动接受移出人队列 ——
    与改契约同样是权威转移,同样只能由人做。"""
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2,
                 "release_tier1_explicit": False}
    violations = lint_policy(PARENT, candidate)
    assert any("release_tier1_explicit" in v for v in violations), violations


def test_adding_a_cohort_still_passes():
    """守住的是放行契约,不是把改进循环整个锁死。

    cohort 的 strength 是**支持强度**(unsupported / single_source /
    corroborated),不是广播 OCR 那套 strong / weak / none —— 两个词表长得像,
    混用会被 lint 当成非法值挡回来。
    """
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2,
                 "auto_accept_cohorts": [
                     {"id": "c1", "field": "invoice_number",
                      "tier": "TIER1", "strength": "corroborated"}]}
    assert lint_policy(PARENT, candidate) == []


@pytest.mark.parametrize("key", ["release_profile", "release_tier1_explicit"])
def test_the_violation_says_which_key(key):
    """违规文案要指名道姓 —— 「候选没通过审查」这种话让人查不下去。"""
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2, key: {}}
    assert any(key in v for v in lint_policy(PARENT, candidate))
