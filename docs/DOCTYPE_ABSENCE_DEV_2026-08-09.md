# Class-Conditional Absence: Development-Set Measurement (2026-08-09)

Results of two zero-API scripts; recompute commands at the end. **All numbers come from the
development corpus**
(`sealed1-workspace`, `sealed2-workspace`, `heldout-workspace`; 300 deduplicated
saved DWS responses). SEALED-3 is not in here and must not be used to validate any conclusion
here — it was consumed by its one-time unsealing (`SEALED3_RESULTS.md` §7).

## Conclusions up front

1. **DocILE ships document-type ground truth**: `metadata.document_type`, present on all 5,680 —
   tax_invoice 3850, order 1440, purchase_order 128, receipt 116,
   sales_order 75, proforma 29, credit_note 24, utility_bill 12, debit_note 6.
   So the correctness of class decisions is **measurable**, not a matter of assertion.
2. **Literal page evidence yields a usable class for 91.7%** (275/300). The other 25 are not
   misjudged; the page just doesn't say — class-conditional rules should never have applied to
   them in the first place.
3. **On the decidable subset, 96.3% agreement with DocILE** (211/219). Most of the 8
   disagreements are not the gate's fault: DocILE says receipt while the page prints INVOICE;
   DocILE says tax_invoice while the page prints Proforma / Confirmation / Estimate.
   **What the AP reviewer sees is the word printed on the page.**
4. **Class conditioning is precisely where the safety comes from, and the numbers show this
   separately**: for the single field `seller_vat_id`, once split by class, half the rules can
   turn on and half absolutely must not.
5. Filtering on silent=0 and saves≥3, **16 candidates are promotable**, saving 107 slots in
   total / 3,000 slots corpus-wide = **human load −3.6pp**, all falling on **non-invoice**
   classes.

## 1. Class decisions vs DocILE

| Gate verdict | Documents | Share |
|---|---:|---:|
| pass (has literal page evidence) | 275 | 91.7% |
| fail (DWS reported a type; none found on the page) | 18 | 6.0% |
| no_claim (DWS reported no type) | 5 | 1.7% |
| unmapped (reported type not in the controlled vocabulary) | 2 | 0.7% |

**On 6.7% of documents DWS self-reported a type that the page offers no way to corroborate.**
This is exactly why `doctype.py` exists: on those 20 documents, taking the self-reported type at
face value lets the supervised model decide for itself whether it gets supervised.

The decidable subset (DocILE type has a counterpart in the controlled vocabulary and the gate
obtained a usable class) is 219 documents, 211 agreeing = **96.3%**. The 8 disagreements are
listed one by one in the output of `scripts/doctype_truth.py`, for example:

- `254b7845…`: DocILE `receipt`, page prints `invoice`, DWS self-reports `sale`
- `a187ba31…`: DocILE `tax_invoice`, page prints `received` (Donation Received)
- `9ab6841f…`: DocILE `tax_invoice`, page prints `estimate`

**DocILE's `order` label does not enter this section**: 65 DocILE-`order` documents scatter on
the page into purchase_order 9, confirmation 6, contract 5, credit_note 3, estimate 19,
invoice 9 — one label covering several document kinds; computing an accuracy against it yields
only a meaningless number.

## 2. The two-sided cost of every "class × field" absence rule

A slot falls into an absence rule's hands only when DWS returns no value. If ground truth is
also absent there → one human review saved; if ground truth **exists** → the slot is auto-judged
absent and **no one will ever see it again**.

### The 16 promotable ones (silent=0, saves≥3)

| Rule | Saves | Share of that class's documents |
|---|---:|---:|
| `AE-purchase_order-seller_vat_id` | 16 | 100.0% |
| `AE-purchase_order-due_date` | 14 | 87.5% |
| `AE-confirmation-seller_vat_id` | 10 | 100.0% |
| `AE-confirmation-total_vat` | 8 | 80.0% |
| `AE-confirmation-due_date` | 7 | 70.0% |
| `AE-credit_note-seller_vat_id` | 7 | 100.0% |
| `AE-purchase_order-total_vat` | 7 | 43.8% |
| `AE-contract-seller_vat_id` | 6 | 100.0% |
| `AE-contract-due_date` | 5 | 83.3% |
| `AE-receipt-seller_vat_id` | 5 | 100.0% |
| `AE-credit_note-total_vat` | 4 | 57.1% |
| `AE-estimate-due_date` | 4 | 100.0% |
| `AE-estimate-seller_vat_id` | 4 | 100.0% |
| `AE-purchase_order-total_net` | 4 | 25.0% |
| `AE-estimate-total_net` | 3 | 75.0% |
| `AE-estimate-total_vat` | 3 | 75.0% |

Total 107 slots / 3,000 slots corpus-wide = **human load −3.6pp**, all on non-invoice classes.

### The absolutely-must-not-turn-on ones (silent > 0), ordered by temptation

| Rule | Saves | Silently swallowed |
|---|---:|---:|
| `AE-invoice-seller_vat_id` | 184 | **7** |
| `AE-invoice-due_date` | 130 | **10** |
| `AE-invoice-total_vat` | 96 | **3** |
| `AE-invoice-total_net` | 55 | **3** |
| `AE-invoice-buyer_name` | 2 | **31** |

The first row is the whole point of this apparatus. Without the class condition,
`seller_vat_id` is a "save 184 slots" rule that looks like the best deal in the table — and it
would swallow 7 tax IDs that really have values. Split the same field by class:
purchase_order / confirmation / credit_note / contract / receipt / estimate — six classes each
silent=0, together saving 48 slots at zero cost; the invoice class stays with humans.

`AE-invoice-due_date` is the same story, and the same affair as the generalization harm recorded
on 2026-08-06 (one due_date absence cohort silently dropped 5 real due dates across 88
unreviewed documents).

## 3. Three caveats, not to be omitted

- **These are development-set numbers.** They decide whether a candidate is worth promoting;
  they are **not a guarantee on unseen data**.
  To say "also holds on unseen data", a separate SEALED-4 draw is required.
- **`credit_note × seller_vat_id` is 0/7 here, while the single silent absence in SEALED-3's
  main arm was exactly a credit note's seller_vat_id**
  (`5a34aacb…`, ground truth `27042768`, `SEALED3_RESULTS.md` §4). Clean on the development set
  does not mean clean on unseen data — this rule lays the gap between the two out on the same page.
- **The `unscored` column means "cannot be computed", not zero.** Documents with no DocILE
  annotation record cannot be treated as having no ground truth; `improve.gate_verdict` will
  refuse candidates for exactly this reason **before** any QA sampling.

## Recompute

```bash
python3 scripts/doctype_truth.py       # class decisions vs DocILE cross-tabulation
python3 scripts/absence_by_class.py    # saves / silent ledger per rule
```

Zero API: reads only saved DWS responses, saved independent OCR, and DocILE annotations.
Neither script accepts a SEALED-3 workspace as default input.
