# Broadcast Invoice due_date Rules

This revision separates two concepts:

- `due_date`: DWS extracts only absolute dates printed directly on the page.
- `calculated_due_date`: a derived result the system computes from explicit inputs and payment terms in the independent OCR.

For example, if the page explicitly prints `Invoice Date: 2026-07-01` and `Net 30`, the system records:

```text
calculated_due_date = 2026-07-01 + 30 calendar days = 2026-07-31
```

The derived artifact also stores the formula, the input fields, the payment terms verbatim, and the OCR word positions. It never overwrites the raw `due_date`, nor is the derived result treated as literal evidence from the page.

If the page prints `30 days after receipt` or `Due on Receipt` but there is no explicit receipt date, the result is `not_computable`; the invoice date is never secretly swapped in as the receipt date. Holiday and business-day rules are likewise not in the current version.

## This pilot

The 30-document dual-mode candidate extraction consumed 1,599 credits. The candidate schema brought `silent_wrong` down from 23 to 17, but human review slots rose from 191 to 201 and release decision load rose from 79.67% to 81.00%, so the candidate is not promoted.

This says schema wording can reduce some wrong values, but currently cannot be shown to reduce human workload; the page-rules layer for `calculated_due_date` is retained independently, pending more explicit-terms samples and later measurement.
