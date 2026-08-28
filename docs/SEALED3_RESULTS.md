# SEALED-3 multi-harness sealed results (2026-08-08, one unsealing, numbers recorded as-is)

Protocol: `docs/SEALED3_PROTOCOL.md`; pre-results addendum and machine plan:
`docs/SEALED3_MULTIHARNESS_ADDENDUM_2026-08-08.md`,
`docs/sealed3_multiharness_plan.json`. Unsealing revision:
`447acf0699d7815fcd69ba8d9922feaf569f65aa`.

## Conclusions first

1. **Ranking ability reproduces**: primary arm HAR-0004 has H1 lift of **3.75×**; H1–H4,
   H6, H7 pass; H5 citation failure rate is **15.35%**, slightly above the `<15%` line — FAIL, recorded as-is.
2. **Human queue drops**: HAR-0004 versus conservative HAR-0001 goes from **624/1000
   (62.4%) down to 527/1000 (52.7%)**, 97 fewer slots (−9.7pp); document touch
   100/100 → 99/100.
3. **But SEALED-3 qualification fails**: P1 requires both silent-error classes not to rise.
   HAR-0004's `silent_absent` is **1**, HAR-0001's is **0**; `silent_wrong` is 59 for both.
   P1 fails on 1 silent absence; P2 passes. **No sealed3_qualified marker is written,
   and it must not be claimed that HAR-0004 has "reduced load with no silent-error increase" on an unseen set.**
4. **The ADK due_date candidate must not be promoted**: HAR-0007 saves another 33 slots
   (−3.3pp), yet has **5 more** silent absences than HAR-0004; automatic promotion would
   silently drop real due dates.
5. **Human adjudication accuracy remains NOT MEASURED**: this run completed only the
   deterministic workload and truth-based safety evaluation with zero human labor, zero
   new DWS, and zero new ADK; the unfinished human arm will be completed separately later.

## 1. Execution and sealing

- The 100 documents × understand/agentic all use the already-stored SEALED-3 evidence;
  this run had **0 DWS calls and 0 ADK calls**.
- The seven arms completed in one batch transaction; no intermediate results were read
  before `batch_complete.json` existed.
- All three batch invariants passed: same input fingerprint, same upstream artifact/ledger/
  spans, and the HAR-0004 exact-repeat arm's run artifacts are byte-identical.
- input fingerprint:
  `63357ff37366c4e8375e9d0a9120ac169e21c761bf2e0bdfe3f3a79041699e9c`.
- batch complete sha256:
  `e54552f5f34a183ccc392bc31878ae15cd6c6588b5848e73e79e58fd6e486eef`.
- metrics sha256:
  `687caa608c00e71850d5f29716d2aa79886af4e7695dd052e281759eaa6ed1f6`.
- Primary-arm field ledger: 1277 claims, in-ledger digest
  `158e8ad3ad83b3c036609b5f4e64924748141c74607a9468e42db9aa5a9be215`.
- Primary-arm audit bundle: 416 members, sha256
  `6b2d4d1ff679598f9861c80b77fa933d54b474c66790c65eff55cdc38497a3c9`;
  members/snapshot/semantics all pass; empty adjudications so binding=None; no DWS
  signature sealing (does not affect the four-layer verify of pre-registered H7).

## 2. Primary endpoints H1–H7 (P = HAR-0004)

| # | Quantity | SEALED-1 | SEALED-2 (qualification later revoked) | **SEALED-3** | Interval | Verdict |
|---|---|---|---|---|---|---|
| H1 | triage lift | 4.03× | 3.19× | **3.75×** | > 1.5 | **PASS** |
| H2 | coverage@46% | 77.3% | 75.2% | **77.33%** | > 55% | **PASS** |
| H3 | legacy requires-caliber review recall | 77.7% | 72.0% | **76.11%** | > 55% | **PASS** |
| H4 | extraction_present missing rate | 29.3% | 12.8% | **16.10%** | 10–45% | **PASS** |
| H5 | citation failure rate on the decidable subset | 15.3% | 13.6% | **15.35%** (62/404) | < 15% | **FAIL (recorded as-is)** |
| H6 | understand frozen rejection rate | 36.6% | 34.6% | **34.41%** (331/962) | 5–35% | **PASS** |
| H7 | run closed loop | PASS | PASS | **bundle verify PASS** | run + verify | **PASS** |

Scored slots 574, deviations 247; deviation rate for the top half of the queue is 67.94%,
for the bottom half 18.12%. H5 again lands on the long-standing ~15% boundary — it must
not be said that citation is fixed; H6 returning to within the interval likewise must not
be read as an extraction-accuracy improvement.

## 3. Multi-harness workload and safety results

`human_queue` is the external-facing human-queue measure: route is not auto_accept/auto_absent.
`silent_absent` and `silent_wrong` use the same DocILE truth scorer; the denominators are
auto_absent hits and auto_accept value hits decidable against truth, respectively.

| arm | human_queue | requires (incl. auto_absent) | document touch | auto_absent | silent_absent | silent_wrong |
|---|---:|---:|---:|---:|---:|---:|
| B0 HAR-0001 | 624 (62.4%) | 624 | 100/100 | 0 | 0/0 | 59/320 |
| B1 HAR-0002 | 632 (63.2%) | 632 | 100/100 | 0 | 0/0 | 57/314 |
| B2 HAR-0003 | 572 (57.2%) | 643 | 100/100 | 71 | **1/71** | 58/306 |
| **P HAR-0004** | **527 (52.7%)** | 633 | **99/100** | 106 | **1/106** | 59/312 |
| A1 HAR-0006 (ADK) | 531 (53.1%) | 632 | 100/100 | 101 | 1/101 | 58/313 |
| A2 HAR-0007 (ADK) | **494 (49.4%)** | 637 | 100/100 | 143 | **6/143** | 59/310 |

The exact-repeat arm P-repeat matches P on all the above numbers and on all run tree bytes.

### Paired differences (candidate − baseline)

| Comparison | Δ human_queue | Δ silent_absent | Δ silent_wrong | Conclusion |
|---|---:|---:|---:|---|
| HAR-0002 − HAR-0001 | +8 (+0.8pp) | 0 | −2 | QA sampling cost makes the queue rise slightly instead |
| HAR-0003 − HAR-0002 | −60 (−6.0pp) | **+1** | +1 | seller VAT cohort reduces load but is not zero-risk |
| HAR-0004 − HAR-0003 | −45 (−4.5pp) | 0 | +1 | total VAT cohort keeps reducing load |
| **HAR-0004 − HAR-0001** | **−97 (−9.7pp)** | **+1** | 0 | **P2 PASS, P1 FAIL** |
| HAR-0006 − HAR-0004 | +4 (+0.4pp) | 0 | −1 | the duplicate cohort has no load-reduction value |
| **HAR-0007 − HAR-0004** | **−33 (−3.3pp)** | **+5** | 0 | **ADK due_date candidate rejected** |

These are **paired effects of whole harnesses** and cannot all be called pure causal
ablations of "changing only one cohort". The reason is that the QA sampler's hash key
includes `harness_id`; when HAR-0003, 0004, 0006, 0007 get new IDs, the 5% / 20% QA slots
are resampled at the same time. HAR-0006's duplicate total_vat cohort adds no new fields
semantically, yet still shows a +4 slot difference — direct evidence of this confound.
The pre-results addendum stated near-placebo only for HAR-0006 and did not extend the same
warning to the three lineage arms; this is an experiment-design omission. No arms are
added post hoc and no seed is changed; recorded as-is as a limitation.

## 4. The one slot where P1 failed

The sole primary-arm silent absence is:

| doc | doctype literal evidence | field | DocILE truth | DWS understand | HAR-0004 consequence |
|---|---|---|---|---|---|
| `5a34aacbc5fc49f3a09c2b06` | `rebate form` → `credit_note`, evidence pass | seller_vat_id | `27042768` | null | `auto_absent` |

This is not a `$0.00` caliber boundary but a non-invoice document that genuinely has a
VAT/tax identifier. It directly refutes the unconditional rule "US invoices usually have
no VAT, so seller_vat_id can be expected to be absent for all documents". More
importantly: **doctype already correctly identifies it as a credit note, but the routing
policy never consumes doctype at all**. This poses a concrete question for the next
version; no answer is patched into the current one: the class can serve as applicability
context / a human-prompt condition, but any automatic absence rule still needs validation
on new data — it cannot be fixed on SEALED-3 and then re-examined on SEALED-3.

The 5 due_date silent absences added by HAR-0007 all have non-empty truth values:

- `3d8745f375c244bd9c9977e6` → `12/23/1999`
- `686fc97705a34f5987ee060b` → `11-23-2020`
- `a593b7950bf941608353fadf` → `11/27/00`
- `ca154b23196b4278ba87a3ec` → `14.03.99`
- `fedd01b20b8c48e096b7ba43` → `September 1, 2020`

So "many US invoices say xx days after" does not support setting due_date globally as
expected-absent; on the contrary, the unseen set shows 5 dates that DWS missed but whose
truth exists would be silently swallowed by that rule. If term derivation is supported
later, it should be an independent, explainable business-rule layer with its own inputs
and an applicability gate, not something disguised as page-span extraction.

## 5. The `decision_load_for_release` metric implementation is broken (new finding, unfixed)

The frozen scorer reads this metric from `deliverable.summary.decision_load_for_release`;
all seven arms return **82.8%**. But the per-field statuses inside the same
`deliverable.json` prove this impossible by themselves: HAR-0004 has 527 `pending`,
367 `policy_accepted`, 106 `policy_confirmed_absent` — the ones requiring human action
should be 527, not 828.

| harness | value reported by summary | recomputed from own field statuses (exploratory audit) |
|---|---:|---:|
| HAR-0001 | 82.8% | 82.8% (624 pending + 204 pending_tier1) |
| HAR-0002 | 82.8% | 63.2% (632 pending) |
| HAR-0003 | 82.8% | 57.2% (572 pending) |
| HAR-0004 | 82.8% | 52.7% (527 pending) |
| HAR-0006 | 82.8% | 53.1% (531 pending) |
| HAR-0007 | 82.8% | 49.4% (494 pending) |

The root cause is that the current `deliver.py` still counts `requires_adjudication ∪ all
TIER1`, ignoring `release_tier1_explicit=false`, and also counts the compatibility
`requires_adjudication=true` on policy-confirmed-absent slots back into human work.
**The pre-registered column is therefore judged uninterpretable, and 82.8% must not be
used to write multi-arm conclusions.** The status recomputation in the table is only an
audit that surfaced the defect; it does not replace the pre-registered endpoint. Neither
code nor tests are changed after these results; the fix goes into the next version, and
SEALED-3 must not be used to validate the fix.

## 6. Descriptive doctype results

The current gates did run doctype on SEALED-3: 100/100 have `document_checks`, of which
83 pass, 9 fail, 4 no_claim, 4 unmapped. 75 are classified invoice; the other 25 are
contract 5, credit_note 2, estimate 3, proforma 1, purchase_order 3, receipt 3, plus 8
with no class.

This reproduces the earlier observation that "about a quarter are not invoices", and also
explains why HITL should not make users redo class identification per document. But
doctype in this version only provides literal evidence and changes no field buttons or
routing; this section is descriptive and does not promote the class model into an
adjudicator.

## 7. Qualification, candidates, and follow-up boundaries

- **HAR-0004: SEALED-3 qualification = FAIL** (P1 silent_absent 0→1);
  no qualification marker is created.
- **HAR-0006: not promoted**; +4 on the human queue versus the primary arm, no
  load-reduction benefit, the difference coming mainly from the harness ID re-shuffling QA.
- **HAR-0007: not promoted**; −33 human slots bought with +5 silent absences — the
  deterministic safety gate should block it.
- **Human adjudication accuracy: NOT MEASURED**; remains a separate human-arm endpoint.
- SEALED-3 has completed its one-shot measurement of revision `447acf0`. From now on,
  doctype-conditional rules, due-date business rules, QA sampler changes, or
  workload-metric fixes inspired by these results may only use development/regression
  data; the next unseen qualification must be a freshly drawn SEALED-4.

The strongest publicly statable sentence from this run: **on the 100-document SEALED-3,
unseen during development, HAR-0004's triage lift is 3.75× and the human queue is 9.7pp
lower than HAR-0001; but 1 new silent absence appeared, so it did not pass the
pre-registered promotion gate.**
