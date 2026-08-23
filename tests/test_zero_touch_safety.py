"""零触碰主张必须单列那些真正不进人队列的付款字段错误。"""

from __future__ import annotations

from invoiceloop.safety_metrics import score_zero_touch_release


POLICY = {"release_profile": {
    "id": "payment_required_v1",
    "fields": ["invoice_number", "seller_name", "amount_due"],
}}


def test_only_zero_touch_gating_slots_enter_the_release_subset():
    routes = [
        {"doc_id": "d1", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": []},
        {"doc_id": "d1", "field": "seller_name", "route": "auto_accept",
         "reason_codes": []},
        {"doc_id": "d1", "field": "amount_due", "route": "auto_accept",
         "reason_codes": []},
        # d2 有付款字段进复核，所以即使另一个自动字段错了，也不属于零触碰子集。
        {"doc_id": "d2", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": []},
        {"doc_id": "d2", "field": "seller_name", "route": "review",
         "reason_codes": ["UNSUPPORTED"]},
        {"doc_id": "d2", "field": "amount_due", "route": "auto_accept",
         "reason_codes": []},
    ]
    truths = {
        "d1": {"invoice_number": "INV-1", "seller_name": "ACME",
               "amount_due": "$10.00"},
        "d2": {"invoice_number": "INV-2", "seller_name": "BETA",
               "amount_due": "$20.00"},
    }
    values = {
        "d1": {"invoice_number": "INV-1", "seller_name": "WRONG",
               "amount_due": "$10.00"},
        "d2": {"invoice_number": "WRONG", "seller_name": "BETA",
               "amount_due": "$20.00"},
    }

    result = score_zero_touch_release(
        routes, POLICY, truth_of=lambda d: truths[d],
        understand_of=lambda d: values[d])

    assert result["zero_touch_docs"] == 1
    assert result["gating_slots"] == 3
    assert result["value_hits"] == 3
    assert result["silent_wrong"] == 1
    assert result["docs_with_silent_wrong"] == 1
    assert result["silent_wrong_fields"] == {"seller_name": 1}
    assert result["docs_with_release_error_ids"] == ["d1"]
    assert result["unscored_auto_accept_slots"] == 0
    assert result["docs_with_unscored_auto_accept"] == 0


def test_a_review_qa_probe_makes_the_document_touched_even_off_gate():
    routes = [
        {"doc_id": "d1", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": []},
        {"doc_id": "d1", "field": "due_date", "route": "review",
         "reason_codes": ["QA_SAMPLE:test"]},
    ]
    result = score_zero_touch_release(
        routes, POLICY,
        truth_of=lambda _d: {"invoice_number": "INV-1"},
        understand_of=lambda _d: {"invoice_number": "INV-1"})
    assert result["zero_touch_docs"] == 0
    assert result["gating_slots"] == 0


def test_non_comparable_auto_accepts_are_explicit_not_hidden_in_arithmetic():
    routes = [
        {"doc_id": "d1", "field": "invoice_number", "route": "auto_accept",
         "reason_codes": []},
        {"doc_id": "d1", "field": "seller_name", "route": "auto_accept",
         "reason_codes": []},
        {"doc_id": "d1", "field": "amount_due", "route": "auto_accept",
         "reason_codes": []},
    ]
    result = score_zero_touch_release(
        routes, POLICY,
        truth_of=lambda _d: {
            "invoice_number": "INV-1", "seller_name": "ACME",
            "amount_due": "$10.00",
        },
        understand_of=lambda _d: {
            "invoice_number": "INV-1", "amount_due": "$10.00",
        })

    assert result["gating_slots"] == 3
    assert result["value_hits"] == 2
    assert result["unscored_auto_accept_slots"] == 1
    assert result["docs_with_unscored_auto_accept"] == 1
    assert result["docs_with_unscored_auto_accept_ids"] == ["d1"]
    assert result["unscored_auto_accept_fields"] == {"seller_name": 1}
