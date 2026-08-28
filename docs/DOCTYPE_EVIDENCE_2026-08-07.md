# Literal Page Evidence for Document Type Claims (2026-08-07, Stage A)

Agreement/plan: `docs/DOCTYPE_PLAN_2026-08-07.md`. Implementation: `invoiceloop/doctype.py`.
Recompute (zero API):

```bash
INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/doctype_evidence.py
INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_evidence.py --sealed2
python3 scripts/doctype_vocab_ablation.py            # per-token ablation
python3 scripts/doctype_vocab_ablation.py --v1-diff  # before/after decontamination comparison
```

> **2026-08-07 update (vocab decontamination, `doctype-v1` → `doctype-v2`).** Not one of this
> document's coverage numbers **changed**; what changed is the vocabulary and the description of
> contamination. The deletion list written in the original "open item 1" had one error; it is
> recorded as-is in the "decontamination" section below.

## Vocabulary freeze (Stage A)

| Decision | Value | Reason |
|---|---|---|
| `proforma` | **its own class** | a proforma differs from invoice in accounting semantics; already in `CLASSES` |
| `check` | **mapped into `receipt`** | no new class split; evidence phrases contain `check` |
| match order | `credit_note` → `proforma` → `confirmation` → `purchase_order` → … → `invoice` | `credit` before `invoice`; `confirmation` before `purchase_order` (otherwise "Order Confirmation" is snatched by `\border\b`) |

Afterwards **only adding classes/phrases is allowed; the direction of the criteria may not change** (plan §4).

## Coverage (model claim → controlled class → OCR literal evidence)

| Set | n | has claim mapped into vocabulary | has literal evidence | evidence rate | blocked for no evidence |
|---|---|---|---|---|---|
| SEALED-1 not-human-reviewed 88 | 88 | 86 | **81** | **94.2%** | 5 (5.8%) |
| SEALED-2 | 100 | 99 | **90** | **90.9%** | 9 (9.1%) |

`unmapped=0` (both sets). `no_claim` means the model returned no `invoice_type`.

> **⚠ This table is in-sample, not a held-out measurement.** The vocabulary was written against
> the free-text spellings of these two sets, so for `unmapped=0` **a constructed component cannot
> be ruled out** — on a set never seen, that number does not hold. The decontamination (next
> section) deleted seven obvious corpus-derived tokens, but that does not and cannot cancel this
> sentence: among the remaining payload tokens, `\bcheck\b` (S1's 'check') and `donation` (S1's
> 'donation received') were still written against the corpus, and deleting them would reclassify 3
> documents. **The undeletable part can only be recorded as-is.**
>
> The only way to turn `unmapped=0` into a measurement is to run once on a set **first seen after
> the vocabulary froze**. That is the next step (see "open item" 1 at the end), not something this
> document can deliver.

**Caliber**: on these two sets, about **8–9% of the extractor's type claims find no literal page
support** (SEALED-2 9/99), **and this percentage carries in-sample contamination**.
"No literal support" is a recomputable support-relation verdict; it does **not equal** "the model
misclassified" — semantic right and wrong is still a human judgment (Charter Six). Nor is it "the
type check can fix payment silent errors"; that is a different matter (see plan §0).

## SEALED-2 blocked list (9)

| doc_id | model claim → class | note |
|---|---|---|
| `39fd2941088a4cd9864d8dbf` | Order Confirmation → confirmation | classification correct; no literal confirm\* on the page |
| `40532c4e2c6a42bca301ea58` | invoice → invoice | spot-checked: actually a traffic order form |
| `45f1811ec4c74141b459f4ea` | pro forma invoice → proforma | no literal proforma on the page |
| `6a6b6a39b9914e72b943c579` | invoice → invoice | spot-checked: no "invoice" wording anywhere on the page |
| `9a52926255a64fd1aa57c5f8` | invoice → invoice | spot-checked: actually a makegood form |
| `b45c2725a2204c03aa5b858a` | invoice → invoice | spot-checked: no "invoice" wording anywhere on the page |
| `b5b4d5fb37b64428958cd7f5` | invoice → invoice | no literal |
| `e12004780d164ee9ba386f5f` | invoice → invoice | no literal |
| `fc7554630cc24a2c8f9db32b` | invoice → invoice | no literal |

## SEALED-1 not-human-reviewed 88 blocked list (5)

`0f1ca104…` / `50bbaa7c…` / `6decf48f…` / `9fadde21…` (all claim invoice, no literal);
`afe032e8…` (claims check → receipt; no receipt/check/received literal).

## Vocab decontamination (`doctype-v1` → `doctype-v2`, 2026-08-07)

Deleted seven tokens that **appeared only in the calibration corpus's free text**:

| Class | Deleted | The string it used to consume | What actually matched that string |
|---|---|---|---|
| `credit_note` | `discrepancy` | S2 'billing discrepancy/credit request' | `credit` |
| `purchase_order` | `worksheet` | S1/S2 'order worksheet' | `\border\b` |
| `purchase_order` | `printout` | S2 'order printout' | `\border\b` |
| `purchase_order` | `traffic` | S2 'new traffic order form' | `\border\b` |
| `contract` | `broadcast` | S1 'broadcast contract' | `contract` |
| `invoice` | `affidavit` | S1 'invoice / affidavit' | `invoice` |
| `invoice` | `billing` | S2 'official billing invoice' ×2 | `invoice` |

**All seven are no-ops.** Measured by per-token ablation + combination verification: deleted
together, SEALED-1 not-human-reviewed 88 and SEALED-2 100 each reclassify **0 documents**; not one
number in this document's coverage table changed.

```bash
python3 scripts/doctype_vocab_ablation.py --v1-diff
#   TOTAL RECLASSIFIED BY THE DE-CONTAMINATION: 0
```

They decide nothing, yet they made the vocabulary look as if tuned against the test set — the
deletion was to strip `unmapped=0` of that illusion, not to change numbers.

### Recorded-as-is correction: the original "open item 1" deletion list was wrong

The original text said the five deleted were `discrepancy` / `printout` / `traffic` /
**`receipt`** / `billing`, and predicted "SEALED-2 becomes ≈91% with evidence + 2 documents
unmapped". Measurement found two errors:

1. **Four of the five are no-ops; deleting them reclassified nothing**; the predicted 2 unmapped
   documents **come entirely from the single token `receipt`**, unrelated to the other four.
2. **`receipt` should not have been deleted.** It is the proper name of the `receipt` class, not
   corpus-derived — anyone writing an accounts-payable vocabulary from common sense would write it
   first. Deleting it turned the two S2 documents whose literal titles are "Receipt" and
   "Transaction Receipt" into `unmapped`.
   **A receipt class that does not recognize "receipt" is not decontamination, it is self-harm.**

At the same time, the original list **omitted** three same-character tokens, `worksheet` /
`broadcast` / `affidavit` (all no-ops, now deleted together), and never mentioned the two that
truly cannot be deleted: `\bcheck\b` and `donation` are S1-derived **and payload** (3 documents
reclassified together).

The conclusion is this methodology: **contamination cannot be eliminated by deleting tokens.**
Everything deletable is a no-op (deleting changes no numbers, only appearances); the ones that
change numbers are precisely the ones that must not be deleted. The only real remedy is one thing —
measure once on a set first seen after the vocabulary froze.

## Decoupling from "22% payment silent errors" (recorded-as-is correction)

Of the 13 silent wrong values on the zero-touch set, **zero are related to credit-note sign**;
party misidentification (`seller_name`) is 6/13.
What the type evidence gate flags is **documents whose type claims find no literal support on the
page**; it does not directly eliminate those 13 amount errors.
Stage D handled party direction and **KILLed** it (51.6% < 80%, see
`docs/DOCTYPE_STAGE_D_2026-08-07.md`); the credit-note sign check is **not done**.

## Stage A boundary

- This stage **does not wire into** gates / routing / fingerprint.
- Tests: `tests/test_doctype.py` (vocabulary order, boundaries, bbox merging, `NO_CLAIM`≠`UNMAPPED`).
- Next step: Stage B answers Q1 (where document-level verdicts land) and Q2 (blocking granularity's effect on load).

## Open items (blocking this document's numbers from any external material)

1. **`unmapped` has never been measured on a held-out set.** Decontamination deleted only no-ops;
   contamination remains (`\bcheck\b` / `donation` are payload and corpus-derived). There is only
   one path to turn `unmapped=0` from construction into measurement: take a batch of documents
   **first seen after the vocabulary froze**, run understand to get `invoice_type`, record the
   `unmapped` rate once, and never go back to change the vocabulary.
   ~~Vocab decontamination~~ done (`doctype-v2`, see the section above); `digest()` has changed →
   runs before and after decontamination are different generations; do not mix them in one computation.
2. Only **4/9** of the blocked list have been examined document by document (the four marked
   "spot-checked" in the table).
   The other 5 are **not adjudicated document by document** and must not be treated as confirmed
   misclassifications.
