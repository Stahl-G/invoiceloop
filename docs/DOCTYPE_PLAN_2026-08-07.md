# Document Class System: Plan (2026-08-07)

## 0. Two things I got wrong in the proposal, recorded up front

The immediate cause of this plan is two judgments overturned by data. Recorded here so nobody decisions off them again later.

1. **"Type-conditional deterministic checks hit that 22%" — false.** Of the 23 SEALED-2 documents where the three payment fields were zero-touch, 13 had silent wrong values; I examined each: `seller_name` 6, `amount_due` 4, `invoice_number` 3, **zero related to credit-note sign**. The single credit note is not in the zero-touch set.
2. **The "22%" was inflated.** Of the 13, about 5 are DocILE annotation/caliber issues ($0.00 in two, multi-line party names in two, a date segment labeled as an invoice number in one), leaving about 8 real errors → **about 13%**.
   Externally we may only say 13%, and it must carry the caveat "calibers not adjudicated item by item".

What the data actually points to is **party identification (who is the seller)**: 6/13, advertising agency vs radio station inverted.
This is the same class of error as the human-judged `WRONG_FIELD_MAPPING` on `0c56b86a`
(credit note issuer / offset recipient inverted). **Item 3 should become a party-direction check, not a sign check.**

## 1. Established facts (measured, zero API)

- `invoice_type` has always been present in DWS responses; the system has never used it.
- The 8-class controlled vocabulary covers every free-text spelling on both sets, zero failures to map — **but this is in-sample**:
  the vocabulary was frozen after scanning SEALED-2, and five tokens entered the table for that reason (see
  the contamination disclosure in the coverage section of
  `docs/DOCTYPE_EVIDENCE_2026-08-07.md`).
- Literal page evidence for type claims (word-level OCR, word-sequence matching + bbox merging):
  88 docs 81/86 = 94.2%, SEALED-2 90/99 = 90.9% (same in-sample contamination).
- Of the 14 blocked documents, **4 were spot-checked; all are genuine misclassifications**,
  not tokenization artifacts:
  `40532c4e` is actually a new traffic order form (the page says only "billing"),
  `9a529262` is actually a makegood form, `6a6b6a39`/`b45c2725` have no "invoice" wording anywhere on the page.
  **The other 10 have not been adjudicated document by document** — they must not be treated as confirmed.
- Type-level ground-truth absence rates show: the 8 candidate "not applicable" rules **are already covered by existing field-level cohorts**;
  the genuinely new ones are only `due_date ×(order/contract/quote/proforma/confirmation)` and `total_net × quote`,
  about 19–20 slots on SEALED-2 = **≈2pp**, at zero silent-error cost.
- When this plan was drafted, `invoiceloop/doctype.py` was written but not yet wired in; Stages A–C subsequently landed
  (gates freeze `document_checks`, the execution fingerprint includes the vocabulary digest, regression tests exist), and Stage D was scrapped per the preregistered
  criteria. For the 2026-08-08 HITL wiring see Stage F below. Keep this timeline as-is; do not retro-write later capabilities as having existed at the time.

## 2. Why this is hard (four questions that must be answered before touching anything)

### Q1 Where do document-level verdicts live? The current gate_report has no place for them

`gate_report["evaluations"][doc_id][field][gate_id]` is a **field-level three-layer structure**.
The type check is **document-level** and belongs to none of the 10 fields.

The C8 cross-document duplicate-check precedent solves only half the problem: it is a document-set-level check, but it stamps its verdict **back onto
invoice_number, a slot that already exists**. The type check has no such natural home slot.

Candidates:
- (a) `evaluations[doc_id]["__document__"]` — breaks every consumer that iterates evaluations by field
- (b) new top-level `gate_report["document_checks"][doc_id]` — additive, but every consumer has to know about it
- (c) standalone artifact `doctype_report.json` — does not touch gate_report, but escapes the gate transaction's input signature

**To-do**: enumerate every consumer of `gate_report["evaluations"]` (matrix / panel / verify /
audit bundle / improve / heldout) and confirm which option does not break historical artifact replay.
**Criterion**: `test_binding_regression`'s 454 frozen verdicts and the heldout zero diff must still hold.

### Q2 How much does "no evidence → block" **raise** review load? Never measured

Per Charter Four, a check that cannot run does not count as passed. But if a document-level block → `doc_blocked` →
routing gives all 10 slots `block`, then on SEALED-2, 8 docs × 10 slots = **80 slots** go from
an average of 4.7 slots/doc to 10 slots/doc, a **net load increase of about 4pp**.

That may be the correct price (it catches real misjudgments), but it must be **measured before deciding**, not discovered afterward.

Candidate granularities:
- document-level block (strictest, +4pp)
- block only **type-dependent verdicts** (applicability rules don't fire, fall back to field-level defaults) — load unchanged,
  but "the type is untrusted" must be visible on the deliverable
- non-blocking finding + deliverable annotation

**To-do**: run SEALED-2 once per granularity; report load and silent errors.
**Leaning**: the second. It satisfies Charter Four (the check ran; the conclusion is "the type is untrusted") without punishing
fields unrelated to type. But this has to be argued, not assumed by default.

### Q3 Can party direction be checked deterministically? This is item 3's kill line

6/13 of the silent errors are seller misidentifications (agency vs radio station). Can this be judged without a model?

Known usable deterministic signals:
- positions of the label words "Remit to" / "Pay to" / "Bill to" / "Advertiser" / "Agency" / "Station"
  on the page (word-level OCR has geometry)
- which block of the page the extracted `seller_name` value falls in (`evidence_span_registry` has bbox)
- the spatial relation between the two: the seller name should sit near "Remit to"/the letterhead, not near "Agency"

**To-do (prototype, not into the product)**: on SEALED-2's 100 documents, measure whether
"which label word the `seller_name` span is nearest to" agrees with ground truth.
**Criterion**: if this rule's accuracy on the 100 documents is < 80%, **item 3 is void** and the party problem
can only go to "the human queue", not "machine checking". The PARTY prototype failure of 137/151 recorded in CLAUDE.md
is a warning: this road was walked before and did not go through.

### Q4 Can type enter the policy language? How to change the anti-hardcoding allowlist

`_ABSENT_KEYS = ("id","field")` and `suggest._ALLOWED_COHORT_KEYS` are the gatekeeping against
"single-document features entering policy". `doc_class` is a **class**, not a document, so in principle it may enter —
but it is derived from **strings written by the supervised model itself**.

Draft rule: `doc_class` is allowed as a cohort key **if and only if** every document covered by that cohort
passed the type evidence gate. Documents that did not get no type-level relaxation.

**To-do**: confirm this rule can be decided deterministically at the lint layer (lint needs to see gate results;
today it cannot — this is a real coupling problem).

## 3. Staged plan (each stage independently complete; criteria between stages)

### Stage A — vocabulary + evidence (pure functions, pipeline untouched)
- `tests/test_doctype.py`: tokenization boundaries, vocabulary order (`credit_note` must precede `invoice`,
  otherwise "Credit Note against Invoice 12345" is snatched by invoice — before the 2026-08-07 decontamination
  this used the examples "billing discrepancy/credit request", relying on `billing` being on the
  invoice side, and both of those tokens are corpus-derived and deleted; see DOCTYPE_EVIDENCE §vocab decontamination),
  returns None with no evidence, bbox merging for multi-word phrases, `NO_CLAIM` and `UNMAPPED` differ in meaning.
- Produce a `docs/DOCTYPE_EVIDENCE_2026-08-07.md`: coverage on both sets and the list of 13 blocked docs,
  with a zero-API recomputation script.
- **Criterion**: 466 + new tests all green; no existing artifact changed.
- **The output is valuable even if everything stops after this**: 8–9% of the extractor's type claims find no
  literal support on the page, and that is recomputable. **Do not state this as "8% are wrong"** — no literal
  support ≠ misclassification (Charter Six).

### Stage B — answer Q1/Q2 (investigation, no product code)
- Enumerate gate_report consumers; run SEALED-2 once for each of the three blocking granularities.
- **Criterion**: once an option is chosen, historical artifact replay with zero diff must be reproducible.
- **Exit**: if all three granularities net-increase load by > 5pp and recover no silent errors, **Stage C pauses**;
  type enters only the deliverable, not the gates.
- **2026-08-07 conclusions** (see `docs/DOCTYPE_STAGE_B_2026-08-07.md`):
  Q1 → (b) `document_checks`; Q2 → typedep/finding (document-level +4.5pp, not taken);
  **C does not pause**.

### Stage C — wire into the gates (per B's conclusions)
- Wire in per the option B selected; `snapshot` execution fingerprint gains a `doctype_digest` component
  (a changed check = a new run generation; no colliding with old runs).
- **Criterion**: `test_port_fidelity` / `test_binding_regression` / heldout zero diff all pass.
- **2026-08-07 landed**:
  - `gates.run_gates` → `document_checks` + non-blocking `doctype_evidence` finding;
  - `input_signature.doctype_digest` + `execution_fingerprint` includes the digest;
  - `deliverable.docs[*].type_trust` ∈ {evidenced, untrusted, no_claim,
    unmapped, ocr_unavailable, unknown} (old runs = unknown).

### Stage D — party direction prototype (Q3's answer decides whether to do it)
- Run the prototype to measure accuracy first, then decide between machine checking and routing only.
- **Criterion**: ≥80% on 100 documents to enter the product; otherwise register as a negative result and stop.
- **2026-08-07 conclusion** (see `docs/DOCTYPE_STAGE_D_2026-08-07.md`):
  primary metric 49/95 = **51.6%** < 80% → **KILL**; corroborating variants all ≤ 52.5%;
  and it covers only 51/100 documents. **What is KILLed is this frozen label-geometry rule**,
  not "party direction cannot be machine-verified". Party direction gets no machine check; human queue only. Not wired into gates.

### Stage E — type-level applicability matrix (last, worth ≈2pp)
- Only the 6 rules nominated by ground truth, **each signed off by a human** (ground truth can only nominate;
  judging "this class of document has no such concept" is a human matter, Charter Five).
- Requires Q4's allowlist rule to land first.

### Stage F — HITL display wiring (landed 2026-08-08; E still not landed)

The workbench reads only the current run's frozen `gate_report.document_checks`; it does not re-run
`doctype.check_document` when a page is opened:

- `pass`: the right pane shows the controlled class, the literal phrase hit by OCR and the page number; the left pane outlines the
  merged bbox with an independent dotted box. Wording is explicit that "whether a field applies is still a human judgment";
- `fail` / `unmapped` / `ocr_unavailable` / `no_claim`: shows each gap; the model's self-reported type is never drawn as evidence;
- old runs lack the top-level `document_checks` key: show **NOT MEASURED**; today's check must not be backfilled as an old run's
  result at the time;
- no state changes decision buttons, preselects answers, removes queue slots, or writes any run artifact.

What this step solves is "re-identifying every document's class first" and "type evidence buried in the JSON", not
Stage E's class-applicability adjudication. The current auditable boundary is as follows:

| Condition dimension | Current rule | Effect on runs |
|---|---|---|
| `doctype_evidence == pass` | the class may serve as human-readable context | UI copy + bbox only |
| type check not `pass` | the class must not be used to judge field applicability | UI states the gap explicitly |
| `doc_class × field` | **no human-signed rules yet** | everything stays human-judged |

The three US-AP caliber statements already formed are also not disguised as pure doctype rules: "US invoices have no VAT"
still depends on jurisdiction; "single Total maps to amount_due" still depends on page labels/layout; "relative terms do not derive
due_date" is a support-relation rule. Using `doc_class` alone as the key would overgeneralize. For them to enter automatic
policy, each must first acquire machine-checkable conditions, then go through Stage E's human sign-off and QA probes; they must not
smuggle in as button defaults via this HITL display wiring.

## 4. Not doing

- No vision models for type interpretation — the OCR deterministic check already reaches 92–94%; a check that can run
  deterministically should not be swapped for one that needs network access.
- `doc_class` is never written into any automatic release path unless that document's type evidence gate passed.
- The vocabulary is never retuned because results look bad — it froze in Stage A; afterwards it can only extend, criteria cannot change.
- The credit-note sign check is **not done** (measured to hit none of the known silent errors; revisit if credit-note samples grow).

## 5. Relation to the competition

These five stages are **all zero API**, with **no dependency** on the Gemini / Google Cloud mandatory items;
the two tracks can run in parallel. But note: not one mandatory item has been done, and the repo has no remote.
If time allows only one track, fill the mandatory items first — Stage A's output (type claims have 8–9%
with no literal support on the page) is already a presentable finding on its own; no need to wait for the whole system.
**Decontaminate before presenting**, otherwise that percentage is in-sample.

## 6. Vocabulary decisions locked at Stage A kickoff (2026-08-07)

The plan proper awaits three user answers; the working defaults at kickoff, frozen into `doctype.CLASSES` (recomputable in
`docs/DOCTYPE_EVIDENCE_2026-08-07.md`), are:

1. **`proforma` is its own class** (not merged into invoice).
2. **`check` maps to `receipt`** (no new class split).
3. **Q2 leaning**: block only type-dependent verdicts (Stage B measures before deciding; the default is not document-level all-slot block).
4. **Stage order**: finish A first (this file + tests + evidence doc), then B; mandatory items run in parallel and do not block A.

Also: `confirmation`'s match order was moved ahead of `purchase_order` — otherwise
"Order Confirmation" gets snatched by `\border\b` (a Stage A vocabulary-order fix, pinned by a test).
