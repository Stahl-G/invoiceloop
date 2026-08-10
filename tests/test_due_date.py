from invoiceloop.due_date import derive_due_date
from invoiceloop.ingest import default_extraction_schema


def _ocr(*lines):
    return {
        "pages": [{
            "page_idx": 0,
            "blocks": [{
                "lines": [
                    {"words": [{"value": value, "geometry": [[0, 0], [1, 1]]}
                               for value in line.split()]}
                    for line in lines
                ]
            }],
        }]
    }


def test_net_30_uses_explicit_invoice_date_and_keeps_provenance():
    result = derive_due_date(_ocr("Invoice Date: 07/01/2026", "Payment Terms: Net 30"))

    assert result["status"] == "computed"
    assert result["value"] == "2026-07-31"
    assert result["formula"] == "issue_date + 30 calendar days"
    assert result["inputs"]["term_text"] == "Net 30"
    assert result["source_refs"]["issue_date"]
    assert result["source_refs"]["payment_term"]


def test_days_after_issue_date_is_computable():
    result = derive_due_date(_ocr(
        "Date Issued: January 15, 2026",
        "Due 45 days after invoice date",
    ))

    assert result["status"] == "computed"
    assert result["value"] == "2026-03-01"


def test_days_after_receipt_requires_a_printed_receipt_date():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026",
        "Payment Terms: 30 days after receipt",
    ))

    assert result["status"] == "not_computable"
    assert result["value"] is None
    assert "receipt" in result["limitations"][0]


def test_days_after_receipt_uses_receipt_date_when_explicit():
    result = derive_due_date(_ocr(
        "Date Received: 07/05/2026",
        "Payment Terms: 30 days after receipt",
    ))

    assert result["status"] == "computed"
    assert result["value"] == "2026-08-04"
    assert result["inputs"]["base_field"] == "receipt_date"


def test_due_on_receipt_is_not_an_absolute_date():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026",
        "Terms: Due on Receipt",
    ))

    assert result["status"] == "not_computable"
    assert result["value"] is None


def test_conflicting_terms_are_not_resolved_by_order():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026",
        "Net 30",
        "Net 45",
    ))

    assert result["status"] == "not_computable"
    assert "incompatible" in result["limitations"][0]


def test_raw_schema_separates_explicit_due_date_from_derived_result():
    description = default_extraction_schema()["properties"]["due_date"]["description"]

    assert "Explicitly printed" in description
    assert "calculated_due_date" in description


# ---- derivation v2:条款形态扩充(清单预注册,先于任何触发率测量)----


def test_hyphenated_net_30_is_computable():
    result = derive_due_date(_ocr("Invoice Date: 07/01/2026", "Terms: Net-30"))

    assert result["status"] == "computed"
    assert result["value"] == "2026-07-31"


def test_discount_shorthand_uses_the_net_part():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026", "Terms: 2/10 n/30"))

    assert result["status"] == "computed"
    assert result["value"] == "2026-07-31"
    assert "n/30" in result["inputs"]["term_text"]


def test_part_number_is_not_a_payment_term():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026", "P/N 30 assembly"))

    assert result["status"] == "not_computable"
    assert "no explicit relative payment term" in result["limitations"][0]


def test_due_in_30_days_is_computable():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026", "Payment due in 30 days"))

    assert result["status"] == "computed"
    assert result["value"] == "2026-07-31"


def test_days_net_word_order_is_computable():
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026", "Terms: 30 days net"))

    assert result["status"] == "computed"
    assert result["value"] == "2026-07-31"


def test_cash_in_advance_is_issue_plus_zero():
    """预付口径规则:发票开出前就应付款,due = issue + 0,公式照登。"""
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026", "Terms: Cash in Advance"))

    assert result["status"] == "computed"
    assert result["value"] == "2026-07-01"
    assert result["formula"] == "issue_date + 0 calendar days"
    assert result["inputs"]["term_text"].lower() == "cash in advance"


def test_end_of_month_term_is_recognised_but_refused():
    """EOM 是「认得但不算」,不许混进「没找到条款」。"""
    result = derive_due_date(_ocr(
        "Invoice Date: 07/01/2026", "Terms: Net 30 EOM"))

    assert result["status"] == "not_computable"
    assert "does not compute" in result["limitations"][0]
    assert result["inputs"]["term_text"] == "Net 30"


def test_advance_term_still_requires_a_labelled_issue_date():
    result = derive_due_date(_ocr("Terms: Cash in Advance"))

    assert result["status"] == "not_computable"
    assert result["value"] is None
