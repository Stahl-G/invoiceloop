# Broadcast Harness Design Draft (2026-08-10)

> **Status: draft, not implemented, not measured.** This document is design, not results.
> Every "expected gain" in it must first pass a development-set blind test, then a sealed set,
> before it may be written as a number.
>
> **Decision (user, 2026-08-10):** InvoiceLoop's scenario is narrowed to **the US broadcast
> advertising invoices that are the largest class in DocILE**; SEALED-4 still runs, but the main
> arm must be a harness optimized for this scenario, not HAR-0017/0018. This document answers:
> what that harness looks like, how to get to it, and how it enters SEALED-4.

---

## 0. Why the current harness is ill-suited to this scenario (one sentence)

The routing policy's tunable surface is nearly wrung out on the non-invoice classes, while the
broadcast scenario's pain points — **legitimate absence, derived due_date, single total, US tax
IDs, party direction** — all sit in the schema and field-semantics layer, beyond the routing
policy's reach. The optimization lever is applied at the wrong layer.

Evidence: in the broadcast-domain dev replay (194 documents,
`BROADCAST_DEV_REPORT_2026-08-09.json`), **56% of the 1,081 human-queue slots concentrate in
four "naturally absent" fields**:

| Field | review slots | primary trigger | annotation coverage (measured on the full corpus) |
|---|---|---|---|
| due_date | **178** / 194 | extraction_present 140 (missing value) | 13.1% |
| seller_vat_id | 149 / 194 | missing value + no invoice-class absence rule | 11.9% |
| total_vat | 141 / 194 | missing value (only 12 slots caught by AV rules) | 10.7% |
| total_net | 137 / 194 | missing value | 13.9% |

The other big consumers: buyer_name 94 (cross_mode disagreement 75 times), total_gross 113,
amount_due 108.

**Most of the current queue is humans confirming, over and over, that "this field really is not
printed on this page"** — exactly what the page-evidence absence mechanism was designed to take
over, except that so far it takes only total_vat.

## 1. Measured facts (the ground this design stands on, all recomputable)

1. **DocILE annotation field distribution** (measured on all 5,680, 2026-08-10): the top six
   fields cover >80%; `total_net` 13.9%, `date_due` 13.1%, `vendor_tax_id` 11.9%,
   `amount_total_tax` 10.7%; `iban`/`bic` near zero.
   **71.1% of documents have only amount_due + total_gross as their two amounts** (the
   single-total shape), and 74.7% have due==gross.
2. **due_date is not printed on the page**: payment_terms annotations cover 35.9%, date_due
   only 13.1%, and 26% of those are the due==issue "Cash in Advance" annotation convention
   (noise).
   A broadcast invoice's due date is **computed as issue_date + payment terms**, not extracted.
3. **The absence vocabulary's monotone-safety property** (`absence_evidence.py` module
   docstring): adding words only ever releases less and never creates silent errors; deleting
   words is the fitting direction. Vocabulary v1 (blind) / v2 (post hoc) are both recorded
   as-is (`ABSENCE_EVIDENCE_DEV_2026-08-09.md`).
4. **Class-conditional absence cannot enter the invoice class** (measured and sealed shut):
   `AE-invoice-seller_vat_id` saves 184 slots and swallows 7 real tax IDs;
   `AE-invoice-due_date` saves 130 and swallows 10
   (`DOCTYPE_ABSENCE_DEV_2026-08-09.md` §2). Inside the invoice class, only page evidence is
   allowed.
5. **The schema-wording candidate was already shot down once by the pilot**
   (`BROADCAST_PILOT_RESULT_2026-08-10.json`):
   30 paired documents, silent_wrong 23→17, but review 191→201 and release decision load
   79.67%→81.00%, **not promoted**. Changing descriptions alone reduces wrong values, not human
   workload.
6. **The derived due_date module exists but its trigger rate is extremely low**: the
   worktree `93d4ea3` `due_date.py` (v1 rules) computed 2 / not_computable 28 on the pilot's 30
   documents.
   Being conservative is right (refuse to compute without an explicitly labeled base date), but
   v1's clause-pattern coverage is too narrow; as it stands it rescues few slots.
7. **The improve lint hard boundary** (`improve.py::lint_schema` / `lint_policy`):
   schema candidates **may only change the description of existing scored fields** — no adding
   or removing fields, no type changes, no new required; policy candidates may only add cohort
   entries. This boundary decides what in this design can go through the normal promotion flow
   and what needs mechanism changes first.
8. **85% of DocILE's `vendor_tax_id` ground truth is US EINs** (measured on the full set
   2026-08-10: of 760 non-empty annotations, 648 are `NN-NNNNNNN` format, only 3 are VAT-style
   `DE…`, and most of the rest are unhyphenated 9-digit US tax IDs). **This means the
   ground-truth side has all along treated the EIN as this field's value** — an EN
   16931-caliber schema description directly conflicts with the truth: an answer that extracts
   the EIN per the truth is judged `WRONG_FIELD_MAPPING` by the human caliber trained on the
   description (the reject recorded as a known associated caveat in `FIELD_COVERAGE.md`). The
   system is punishing correct answers.
   That caveat clause is corrected per this measurement: what is mismapped is not the extractor,
   it is the field description.

## 2. Design (by layer)

### P0 Scope definition: what counts as a "broadcast invoice"

Reusing the pilot's frozen scope rule (`BROADCAST_PILOT_SCOPE_2026-08-09.json`,
`broadcast-pilot-v1`): **FCC-style callsign + ≥2 broadcast terms = strong (224/400),
one-sided evidence = weak (110), neither = none (66)**. The rule is deterministic, zero-API,
computable over the full corpus.

- **Development set**: the pilot's 194 documents (from exposed documents of sealed1/2/3 +
  heldout). Tuning, vocabulary design, and harness candidate evaluation all happen here,
  zero-API replay as before.
- **Evaluation set**: must come from the **unexposed pool** (currently 4,931 documents),
  filtered by the scope rule first, then extracted.
  See §4 (SEALED-4 revision).
- Handling of weak/none documents: the harness does not reject them (scope is an optimization
  target, not a gate), but metrics are reported only on the strong subset, with weak listed
  separately. This is a caliber declaration, written into the evaluation protocol.

### P1 Schema layer (within what lint allows)

**Principle: schema wording only has to "not induce hallucination"; reducing human work is
P2's job.**

1. **due_date semantic narrowing + derivation layer landing.**
   - The raw `due_date` description changes to extract explicitly only "absolute dates printed
     directly on the page" (the worktree candidate schema's approach; the pilot proved it
     reduces silent_wrong).
   - **Merge worktree `93d4ea3`**: the `due_date.py` derivation layer (`calculated_due_date`)
     enters main, wired into pipeline/deliver/bundle. The raw field is never overwritten by a
     derived value.
   - **Derivation rules v2**: v1 recognizes only "Net N" and two explicit phrasings, computing
     just 2 of 30 documents.
     v2's clause-pattern list (e.g. "2% 10 Net 30", end-of-month terms, the shapes of "on
     receipt") is **written as a preregistered list before any hit-rate measurement**, then
     measured. Adding patterns after seeing results = fitting,
     same discipline as the vocabulary.
2. **seller_vat_id's description moves to the US caliber.** lint forbids changing field names
   and allows only description changes: "Seller US federal tax ID (EIN / Federal ID), or VAT
   identifier where present." Basis: §1.8 — the ground-truth side is 85% EIN; the EN 16931
   caliber description conflicts with the truth and has been measured to induce caliber
   confusion (`FIELD_COVERAGE.md` known associated caveat, reason code
   WRONG_FIELD_MAPPING). **The scoring mapping (`DOCILE_TO_FIELD`) does not move**; the
   correspondence between DocILE `vendor_tax_id` and `seller_vat_id` is unchanged — what
   changes is the description moving toward the truth, not the truth toward the description.
   (For contrast: the pilot's ADK draft **excluded** the EIN — that would make the extractor
   deliberately not extract values the ground truth labels, manufacturing absences for humans
   to handle; part of why it lowered silent_wrong in the pilot is that not extracting means
   not being wrong. Wrong direction; not adopted.)
3. **The four amount fields' descriptions written for the US single-total shape**, e.g.
   total_net: "Subtotal before tax, only if separately printed." The sole aim is to remove the
   incentive to "invent a net". The arithmetic gate's silent handling of single-total documents
   follows the existing ruling (commit `6dce2e9`); the gate is not changed.
4. **Explicitly unchanged: no adding or removing fields.** Getting order_id (broadcast cluster
   coverage 48%, a natural key for AP reconciliation) would be a **mechanism change**
   (lint_schema loosened to allow field additions + a preregistered expansion of the scoring
   field set + new ground-truth sources); per GOAL.md's "build fewer mechanisms" it is a
   separate project, not mixed into this one.

### P2 Absence layer (this design's main lever)

Expand page-evidence absence from 1 rule to three fields in the broadcast scenario. **All go
through `absent_evidenced_cohorts` (page evidence); `absent_expected_cohorts` is untouched
(class bets are measured and sealed shut inside the invoice class, §1.4).**

| Candidate rule | Vocabulary status | Known residual risks (recorded as-is) |
|---|---|---|
| `AV-total_vat` | exists; in use by HAR-0018 | 0/136 silent on dev |
| `AV-seller_vat_id` | v2 vocabulary already contains US spellings (federal/employer/id no…) | 1 silent left on dev (OCR read "Federal" as "federai"); **refusing per-document word fitting, accepting the residual** |
| `AV-total_net` | vocabulary exists (subtotal/net/before tax…) | pending dev blind test; "net" is simultaneously a commission-caliber word on broadcast invoices (0.85 signature); vocabulary design must preregister its handling |
| `AV-due_date` | **deliberately not released** (bare `due` is hit by "Amount Due"; the module docstring says so explicitly) | needs vocabulary v3 redesign, see below |

**due_date vocabulary v3 is the only thing in this design that needs "designing", and it is the
easiest place to step on the fitting red line.**
Discipline (same as the doctype decontamination and vocabularies v1/v2):

1. the v3 vocabulary is **written as a list and committed before any saves/silent measurement**
   (the timestamp is the preregistration);
2. the design source is general accounts-payable vocabulary ("terms", "net 30", "payment due",
   "days", etc.), **not the specific spellings in the dev ledger**;
3. distinguishing "Amount Due"/"Balance Due" from a due date is v3's core problem — the
   candidate solution writes amount-context words (amount/balance/due co-occurrence) as
   exclusion rules rather than relying on deleting words;
4. once written, **blind-test once** on the 194-document dev set, recording saves and silent
   together as-is; silent > 0 means that field is not promoted and the vocabulary stays where
   it is (negative results also go into the document).
5. the existing 8 due_date caliber-dispute silents (`ABSENCE_EVIDENCE_DEV_2026-08-09.md`) are
   unrelated to this vocabulary; recorded as-is and untouched.

### P3 Release layer (conservative, essentially untouched)

- `release_tier1_explicit: true` **stays**. Document-level human-signed approval is a safety
  boundary sealed only on 08-09 (commit `a28587d`); scenario optimization does not touch it.
- No entries are added to `auto_accept_cohorts` for now. The cleanest-looking shapes in the
  broadcast scenario (single total, due==gross, citation passing) are precisely the historical
  hiding place of silent_wrong (six rounds: unflagged TIER1 still had 7.8% true errors).
  **The main lever for saving human work is P2's absence, not release.**
- buyer_name's cross_mode disagreement (94 slots) is not handled this time: there is no safe
  automatic rule, and the preregistered geometric rule for party direction was already killed
  (`DOCTYPE_STAGE_D_2026-08-07.md`); leaving it in the human queue is the honest answer.

### P4 What gets measured

The development-set blind test (194 documents, zero-API replay) reports, per field:
review slot count, auto_absent count, silent_absent (vs truth), silent_wrong (vs truth), and
release decision load. The promotion gate keeps the SEALED-series discipline: **silent_absent
must be listed item by item; >0 means that rule is not promoted**; queue reduction is the
benefit, not the bar.

## 3. Implementation plan (the order has dependencies)

| Step | Action | Verification |
|---|---|---|
| 1 | ~~Merge worktree into main~~ **Done 2026-08-10**: cherry-pick `93d4ea3` (due_date derivation layer + scope + broadcast tooling), `3c0568f`; `808b904` not merged — its doctype-HITL feature main already has its own implementation of (`ec715ba`, 75 doctype exposures in the workbench), and merging would only introduce semantic duplication | `pytest tests/` **687 passed, 3 skipped** (673 before the merge) |
| 2 | ~~Schema description revision (P1.1/1.2/1.3) via `improve propose_schema`'s normal lint + promotion path~~ **Done 2026-08-10, not promoted**: the final 10 descriptions preregistered (`BROADCAST_SCHEMA_FINAL_2026-08-10.json`); HAR-0022 re-extracted 30 documents (510 credits) with review_load −0.33pp, value_hits +1, but silent_wrong 8→11 — the +3 is entirely re-extraction variance in **unchanged name fields** (addresses concatenated into names); no scoreable benefit on the target fields; verdict not promoted (stahl), HAR-0021 stays active | eval + candidate schema pinned into `docs/evidence/absence_v3_2026-08-10/`; the methodological finding recorded in `ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` §6 |
| 3 | ~~Derivation rules v2 clause-list preregistration commit → measure trigger rate on dev~~ **Done**: `6341052`; trigger rate 8/300 (2.7%), 2/2 agreement vs truth, the bottleneck being the 53 "bare Date" documents | Trigger rate and not_computable reason distribution recorded as-is (`ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` §4) |
| 4 | ~~due_date vocabulary v3 preregistration commit → dev blind test~~ **Changed to engine v3 fuzzy matching** (a monotone-safe mechanism, `e06488f`): seller_vat_id 234/0 **crosses the line**; the total_net×1 and due_date×8 silents are all caliber disputes (single-total ruling + derived-value ruling), not vocabulary problems | silent=0 gates the next step (`ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` §1–3) |
| 5 | ~~`AV-seller_vat_id` / `AV-total_net` (/ `AV-due_date`) candidates → dev evaluation → promote one by one, yielding the broadcast harness (HAR-00xx)~~ **Done 2026-08-10**: HAR-0019 (seller_vat_id, `9939adb`), HAR-0020 (total_net), HAR-0021 (due_date) passed the mandatory gate one by one, signed stahl; broadcast harness = **HAR-0021**, dev queue 60.20% → 47.73% | Each: promotion log + policy pinned into `docs/evidence/absence_v3_2026-08-10/` |
| 6 | ~~SEALED-4 protocol revision (§4) → human confirmation → commit~~ **Done 2026-08-10**: `04fc8cd` amendment frozen (broadcast sub-pool union 4,196 measured; T1/T2 truth-caliber rules listed item by item); T1/T2 scoring functions landed with `0381016` | The revision precedes all extraction |
| 7 | Budget authorization → `sealed extract` → one-time unsealing | `SEALED4_RESULTS.md` |

Steps 3–5 are all zero API. Step 2's re-extraction spent 510 credits (2026-08-10); the only
remaining spend is step 7 (~200 calls, circuit breaker at 6,000 credits).

## 4. Relation to SEALED-4 (the protocol must change, and only before extraction)

Both pegs of the current SEALED-4 protocol (`SEALED4_PROTOCOL.md`) no longer fit this design:
the list was drawn from the **all-type pool** (~25% non-invoice, with broadcast/general mixed
in), and the main arm is pegged to HAR-0017/0018 (the general harness). Extraction has not
happened, so revision is legitimate; the moment it happens, everything below is scrapped and
redone. Revision draft (written into the `SEALED4_PROTOCOL.md` amendment):

1. **List redraw**: first filter the 4,931-document unexposed pool deterministically by the
   `broadcast-pilot-v1` scope rule (zero API), yielding the broadcast sub-pool; **a new drand
   round redraws 100 documents**. The old list
   (`sealed4_doc_list.json`) stays on disk, annotated with the reason for voiding — the same
   discipline as the SEALED-2 eligibility revocation: facts recorded as-is, traces not
   destroyed.
2. **Main arm re-pegged**: the broadcast harness produced by step 5; code pin = pre-extraction
   HEAD. **Commit before extracting; the order must not flip**
   (same discipline as the original protocol §1.2).
3. **Baseline unchanged**: the in-package HAR-0001. Both arms paired on the same evidence,
   keeping H1–H7 and P1–P3.
4. **Metric caliber**: the primary metric is reported on the strong subset, weak listed
   separately; how the ground-truth side handles due_date's due==issue annotation convention
   (§1.2, 26%) is **written into the amendment before unsealing**
   (suggestion: annotation rows with due==issue and Cash-in-Advance-type payment_terms do not
   count toward due_date absence judgments; reasons and basis frozen with the amendment).
5. The original protocol §5's freeze list is replaced accordingly: the frozen object changes
   from the HAR-0017 policy to the broadcast harness policy + vocabulary v3 digest + derivation
   rules v2 digest.

**This is a "change the criteria" move, per GOAL.md discipline: say it first (this section),
give the basis (the §0–§1 measurements), write it into the document (the amendment); no silent
changes.**

## 5. Explicitly not doing

- No class-conditional absence rules for the invoice class (measured to swallow truth, §1.4);
- `release_tier1_explicit` untouched; document-level human-signed approval untouched;
- No schema field additions or removals (order_id is a separate project);
- No geometric/model-based party-direction verdicts (the preregistered attempt was killed);
- After seeing results: no adding vocabulary words, no adding derivation patterns, no narrowing
  matching (the fitting red line);
- No document from SEALED-1/2/3 used to validate this design's fixes (they are all fully
  exposed; dev set only).

## 6. Unmeasured claims (against misreading)

- Human adjudication accuracy: **NOT_MEASURED** (the ARM experiment terminated at slot 32);
- The schema wording revision's effect on human workload: the pilot measured an **increase**;
  this design does not claim P1 reduces human work, only that it prevents mismapping;
- The derived due_date's trigger rate: v1 measured 2/30; v2's expected trigger rate **has no
  basis** — only step 3's measurement counts;
- Vocabulary v3's safety: the design property (adding words is monotone-safe) guarantees only
  direction, not that v3's specific wording yields silent=0 — that takes step 4's blind test;
- Bias of the scope rule itself: callsign+terms is a proxy for literal page evidence; what is
  mixed into the 110+66 weak/none documents was only coarsely reviewed in the pilot, never
  annotated document by document.
