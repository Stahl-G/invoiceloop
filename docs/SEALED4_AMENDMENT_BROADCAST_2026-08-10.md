# SEALED-4 amendment: broadcast scope + truth-caliber rules (2026-08-10, frozen before extraction)

A revision to [`SEALED4_PROTOCOL.md`](SEALED4_PROTOCOL.md). The original protocol §1.2
already marked the code pin and the primary arm as "re-pin before extraction"; this
amendment also changes the **list scope**, and adds truth-caliber rules. The legitimacy
basis is the same as the original protocol's: **SEALED-4 has not been extracted or
unsealed to this day; no results exist**; §5 governs "changes made after results appear",
which does not concern this amendment. Once extraction happens, changing a single further
word of this file = this batch is void.

This file is frozen at its first commit. The drand round is left blank, to be filled at
execution (same discipline as the original protocol §1).

## A1. List: scope switched to broadcast, redrawn with a new seed

The original list (`docs/sealed4_doc_list.json`, drand round 6360483) was drawn from the
**all-types pool** (~25% non-invoice, broadcast/general mixed), mismatching the broadcast
harness's optimization target. Handling: **kept on disk, not deleted, with the voiding
reason annotated** (same discipline as SEALED-2's qualification revocation: facts stay on
record, traces are not destroyed).

New list:

1. Subpool = `heldout.sealed_pool()` (4,931 documents, unexposed) filtered
   deterministically by the `broadcast-pilot-v1` scope rules
   (`scripts/broadcast_scope.py::classify_evidence`, FCC call signs + broadcast
   terminology, **zero API**, reads only corpus OCR);
2. Subpool sizes were measured (2026-08-10, before any extraction):
   **strong 2,725 / weak 1,471 / none 735 (not in the list)**, union (strong+weak)
   = **4,196 documents**, list-recomputation anchors:
   - strong digest `d1e79686fe67f389cc08f9deba200aaa21f8c661445d5de738af65bb1f926489`
   - weak digest `72066c8be5e082abd31093a1ca8c60cffdbbf39e449cd575498f440917bbcb16`
   - union digest `78066c41a4bea9fa5f5102ccd5977ae2993297ba5fbb055b04cee810e0ae438c`
   (digest = sha256 of the sorted doc_ids joined line by line; any change to the filter
   rules or the exposure manifest changes them);
3. From the union 4,196, draw 100 using the **new drand round = `6363898`** (committed
   2026-08-10, latest round at commitment 6363858; this commitment precedes that round's
   reveal), seed (hex) =
   `184789911618e785e004bde36a5b02b6bb94e3eeae82d960d593c7fdfb6336b4`
   (the verbatim `randomness` of that round, seed taken 2026-08-10T07:46:05Z),
   PRNG context switched to `sealed4-v2` (`SEALED_CONTEXTS` extended accordingly; the
   code change lands in the implementation commit after this amendment, before the
   reveal);
4. Write the list to `docs/sealed4_doc_list.json` (renaming the old list to
   `sealed4_doc_list_voided_fullpool.json` before overwriting), **committed separately,
   before any DWS call**.

Cost stated as-is: drawing from the union expects ~65 strong + ~35 weak; the primary
metrics are computed only on the strong subset (A4), so statistical power is lower than
100 all-strong documents — the trade-off buys the weak subset being visible as its own
column, not hidden behind a single "broadcast" label.

## A2. Primary arm and code pin

- **Primary arm = the broadcast harness that `improve/active_harness` points to at the
  pre-extraction HEAD.** Currently **HAR-0019** (= HAR-0017 + `AV-total_vat` +
  `AV-seller_vat_id`, policy digest
  `ebaf66ef8ec9542d1dc9d5bd3d829ccab8cebae4cec2083a60b7d7b3bef90fa7`);
  if step 6b / step 2 promotes again, the last promotion before extraction governs, and
  the policy digest is hard-written in the pre-extraction pin commit;
- **Code pin = pre-extraction HEAD. Commit first, extract second; the order must not be
  reversed** (same discipline as the original protocol §1.2);
- **Baseline unchanged**: in-package HAR-0001. The two arms are paired on the same
  evidence; the H1–H7 intervals and P1–P3 pass lines carry over from the original
  protocol §3;
- Absence engine pin: `absence-evidence-v3`, vocabulary digest
  `0a9f3773577e068c4b6a21ed68ead6a8ae37dacc755ce928e9d4051f4af6f92e`;
- Derived-rule pin: `due-date-relative-term-v2`;
- The T1/T2 scoring functions of A3 are product code, frozen together with the code pin.

## A3. Truth-caliber rules (adopted via stahl 2026-08-10, frozen before unsealing)

The two existing caliber rulings govern **project-side** behavior; the DocILE truth side
has divergences of the same family, and the scorer has no third bucket (this problem was
pre-registered at `6dce2e9`). These rules align the two rulings on the truth side:
**the following cases are caliber divergences in the applicability dimension (Charter
Five); they are not counted into `silent_absent` and are listed separately as "caliber
disputes".** P1 judgment uses only the true-silent column; the caliber-dispute column
must not be zeroed out or hidden.

### T1 — single-total documents where truth labels the total into a non-amount_due field

Mechanical definition: for a slot `(doc, F)` with `F ∈ {total_net, total_vat,
total_gross}` judged `silent_absent`, if in the **same document** `truth[F]` and
`truth[amount_due]` are equal as normalized amounts (one amount; truth merely chose a
different slot for it), reclassify as a caliber dispute. Basis: ruling `6dce2e9`
(single-total documents put `Total` into `amount_due`, the other three amount fields
`confirm_absent`) — the project side has long judged this way; the truth side is now
aligned.

Development-set instances (1 document, listed item by item):

| doc_id | truth[F] | truth[amount_due] | page |
|---|---|---|---|
| `f7b199fd711149feaf0044c8` | `total_net` = `1100.00` | `$1100.00` | only one `$1100.00` printed, no net-type label of any kind |

### T2 — truth labels an alias-item date as date_due

Mechanical definition: for a slot `(doc, due_date)` judged `silent_absent`, if
`truth[due_date]` is non-empty, its text appears in the page OCR, and (i) or (ii) holds,
reclassify as a caliber dispute:

- (i) `truth[due_date]` and `truth[issue_date]` normalize to the same string (truth
  labeled the same date as both issue and due);
- (ii) a **±12-word window** around the date's OCR position contains one of the frozen
  word set `{transaction, donation, authorization, adjustment}` (lowercase match) — i.e.
  it is printed in the context of a transaction/receipt timestamp, not a payment-due
  context.

Basis: ruling `95c6b66` (no annotation column for that item on the page →
`confirm_absent`, no inferring from neighboring columns) — derived/transaction timestamps
are not an invoice's due date; the project side has long judged this way, and the truth
side is now aligned. **The word set may only grow, never shrink; adding words after
seeing this batch's results = fitting, and voids the batch.**

Development-set instances (8 documents, listed item by item; page contexts are verbatim
OCR fragments, normalized lowercase):

| doc_id | truth[due_date] | page context (normalized) | hit |
|---|---|---|---|
| `0c56b86aedd445d8a845a287` | `03/27/00` | `credit adjustment by eft 03 27 00` | (ii) adjustment |
| `254b7845992547228487acc5` | `12/1/2021` | `transaction sale date time 12 1 2021 11 05 17 am cst` | (ii) transaction |
| `878ad70041f840eb923504a3` | `10/19/20` | `…belmont street bellaire… 10 19 20 1 53pm ref r293320050009 authorization code 101917` | (ii) authorization |
| `a14811674f9e4b2c99bce2be` | `August 26, 2020` | `donation received payment status completed august 26 2020 at 7 19 45 pm pdt` | (i)+(ii) |
| `a187ba31eae2481ca20cdc7a` | `September 5, 2020` | `donation received payment status completed september 5 2020 at 12 34 35 pm pdt` | (i)+(ii) |
| `c8d26800425448f1ae2115d1` | `26-Jul-2022` | `payment information date lime transaction id transaction type … 26 jul 2022 10 07 33 cdt` | (ii) transaction |
| `cdf65b6accc54facb0d8cf8e` | `9/29/2021` | `transaction sale date time 9 29 2021 8 46 55 am cst` | (ii) transaction |
| `db2e81c790384a11bbde5194` | `August 26, 2020` | `donation received payment status completed august 26 2020 at 7 14 08 pm pdt` | (i)+(ii) |

**Self-stated cost**: T2 lets through slots where "a true due date happens to be printed
next to one of these four words" — trading a bit of silent-detection sensitivity for
caliber consistency. Admitted in writing here; it must not be recast afterward as
cost-free.

## A4. Metric caliber

- The primary endpoints (H1–H7 intervals) and P1–P3 are reported on the **strong
  subset**;
- The **weak subset gets its own column** with the same numbers, not participating in the
  promotion judgment;
- `silent_absent` is reported split into two columns: true-silent / caliber-dispute (A3);
  P1 looks only at the true-silent column.

### A4.1 Prediction written in stone before results (replaces original protocol §3.1)

The original protocol's prediction targeted HAR-0017 (queue down 1–4pp,
`silent_absent ≤ 2`); the primary arm changed, so the prediction is rewritten. On the development set
(300 all-types documents), HAR-0001's human queue goes 60.20% → HAR-0019 50.47%
(−9.73pp); absence rules hit more densely on the broadcast subpool, but SEALED-4's
strong subset is only ~65 documents, so noise is wider.

**Prediction: the strong-subset human queue drops 4–12pp versus baseline; true-silent =
0; caliber disputes 0–3 cases.** Deviation by itself is not a voiding condition — record
it as-is; the voiding conditions are in original protocol §5 + this document's A2/A3.

## A5. Disposition of the original protocol's clauses

| Original protocol | Disposition |
|---|---|
| §0 frozen objects (code `175f1e6`, primary arm HAR-0017) | Replaced by A2 |
| §1 seed (round 6360483) and list | Voided, kept on disk (A1); new round left blank |
| §2 steps | Order unchanged: the list commit precedes every DWS call; extraction needs explicit budget authorization |
| §3 P1–P3 | Carried over, applied to the strong subset; `silent_absent` split per A3 |
| §4 claim discipline | Carried over; the phrase "16 class-absence rules" now reads as "broadcast harness (primary-arm policy content per the pin board)" |
| §5 voiding conditions | Carried over; frozen objects replaced by all the pins listed in A2 + the A3 word set |

## Implementation checklist (all before extraction, one commit per step)

1. ~~This amendment committed~~ **Done**: `04fc8cd`;
2. ~~Code: add `sealed4-v2` to `SEALED_CONTEXTS`, `sealed_list` supports subpool
   filtering (strong+weak) — with tests~~ **Done**: `48d1fcd` (the classifier migrated
   into `invoiceloop.scope` recomputed the 4,931 pool; strong 2,725 / weak 1,471 /
   union 4,196 match the three digests byte for byte, pinned by regression tests);
3. ~~Code: the A3 T1/T2 reclassification functions (shared by SEALED-4 scoring and the
   step-6b development-set re-evaluation) — with tests; the word set is the frozen set
   in the table above~~ **Done**: `0381016`
   (`invoiceloop/truth_caliber.py`, truth-caliber-v1);
4. drand round reveal → fill into A1 → commit;
5. New list written to disk → separate commit (old list renamed and kept on disk);
6. Primary-arm policy digest + code HEAD pin commit;
7. After **explicit budget authorization**, `sealed extract`; sealed and unread, one
   unsealing, `SEALED4_RESULTS.md` with numbers recorded as-is.
