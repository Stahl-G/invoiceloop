# Scored field-set coverage statement (frozen before SEALED-2, 2026-08-06)

Four of the rubric's suggested critical fields are not in our scored set: currency, buyer_tax_id,
purchase_order_number, payment/bank details. This document declares the reasons for their absence
**before the next sealed evaluation** (a declaration patched in after the fact = cherry-picking fields;
the review adjudication's verbatim warning).

## How the scored fields came to be (not picked by looking at results)

The ten scored fields (invoice_number / issue_date / due_date / seller_name /
seller_vat_id / buyer_name / total_net / total_vat / total_gross /
amount_due) were pre-registered and frozen in dws-derisk **before round one** of the six-rounds
experiments (`run_batch.sample`'s wanted set, traceable in commit history); the selection criterion was
"AP payment-decision dependence + DocILE has annotations to judge against". InvoiceLoop inherited them
verbatim and has never added or removed fields based on any experimental result.

## The facts of the four suggested fields' absence (measured over the full 5,680-document corpus; corrected 2026-08-06 on recompute)

(An external review caught on 2026-08-06: the first edition of this table counted the wrong annotation
key (`value` → should be `text`), making the numbers non-recomputable. Corrected; the recompute script is
at the end of this document.)

| Rubric-suggested field | DocILE counterpart | Measured (5,680 documents) | Conclusion |
|---|---|---|---|
| currency | `currency_code_amount_due` | Key present in 4,000 documents; but the annotation text is usually the bare symbol `$`, collapsing to None under the pre-registered CODE normalization — **only 126 non-empty cases** (EUR/USD etc.) | Conclusion unchanged (no judgeable ground truth); the reason is normalization collapse, not absent annotations |
| buyer_tax_id | `customer_tax_id` | Key in 40 documents, 40 non-empty, but highly concentrated (same value repeated) | Too rare (0.7%); a 100-document sealed set expects <1 case — cannot enter scoring |
| purchase_order_number | (no such fieldtype; `order_id` is an order/contract number, semantically different) | — | No ground-truth source |
| payment / bank details | `account_num` / `bank_num` | Key in 135 / 105 documents, **non-empty 135 / 105** (e.g. `10491969`, `052001633`) | **Ground truth exists but rare (≈2%)** — a 100-document sealed set expects ≈2 cases, supporting no metric; rarity alone is grounds for exclusion |

**Conclusion: the reasons these four fields are not in the scored set are "no judgeable ground truth
(currency, PO)" or "ground truth too rare to make a sealed set (buyer_tax_id, bank details)" —
not "judged unimportant".** The scoring discipline "no ground truth, no error rate" is unchanged:
adding them to the scored set could only produce pseudo-metrics.

## Distinguishing the product layer from the scoring layer

- **Scoring layer** (H-series metrics, baseline tables): only the 10 fields above, for the reasons in the table;
- **Product layer**: the extraction schema is data-driven (`ingest.FIELD_DESCRIPTIONS`);
  for a tenant to add currency/PO/bank fields takes only a schema row + a ground-truth set —
  the freezing, gating, binding, routing, and audit mechanisms are field-agnostic and all carry over;
- **Known related limitation**: `seller_vat_id`'s field semantics are expected-absent on a US corpus
  (2026-08-06 HITL measurement + absent_expected cohort), and there is a systematic wrong-mapping risk of
  Fed. I.D. → seller_vat_id (one measured reject, reason code WRONG_FIELD_MAPPING) — the field's
  description text (EN 16931 caliber) is in tension with US-corpus reality; any revision goes through the
  next batch's qualification process.

## If the corpus changes

On a corpus whose ground truth covers these fields (e.g. European VAT invoices, enterprise AP
data with bank fields), the field set should expand; the way to expand = pre-register the new fields + a
new sealed set, not retroactively amend this statement.

## Recompute script (source of every number in this table)

```python
import json, pathlib
from invoiceloop.eval_norm import eval_normalise as normalise
from invoiceloop.fields import Kind

ann = pathlib.Path("~/Developer/dws-derisk/data/docile/annotations").expanduser()
for ft in ("currency_code_amount_due", "account_num", "bank_num",
           "customer_tax_id"):
    keys = nonnull = 0
    for p in sorted(ann.glob("*.json")):
        for x in json.loads(p.read_text()).get("field_extractions") or []:
            if x.get("fieldtype") == ft:
                keys += 1
                t = x.get("text")          # the annotation value is in text, not value
                if t and str(t).strip() and normalise(t, Kind.CODE) is not None:
                    nonnull += 1
    print(ft, "keys:", keys, "nonnull(CODE):", nonnull)
```
