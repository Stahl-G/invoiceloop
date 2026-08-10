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
