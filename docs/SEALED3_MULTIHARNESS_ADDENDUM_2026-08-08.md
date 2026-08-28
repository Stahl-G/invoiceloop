# SEALED-3 multi-harness unsealing addendum (2026-08-08, frozen before results)

This addendum does not change the primary endpoints, pass lines, or contamination
consequences of `docs/SEALED3_PROTOCOL.md`. While no SEALED-3 run / results exist yet,
it only expands the single unsealing into **a paired multi-arm evaluation on the same
frozen evidence**. The user has explicitly authorized proceeding first with the part that
needs no full human arm; the human adjudication accuracy of the agent-vs-human experiment
will be completed later and is neither an input nor a pass condition of this unsealing.

## 1. Why not "look at one round, then let ADK revise for another round"

SEALED-3 can be opened only once. If round-1 results entered an ADK prompt and a round-2
policy were generated from them, round 2 would already be treating SEALED-3 as
training/development feedback, immediately triggering the void condition in the original
protocol §2. Hence this experiment has only one legal shape:

1. Freeze all arms, summaries, comparison directions, and the scorer first;
2. One batch process reruns the full deterministic pipeline for every arm from the same
   raw/OCR/PDF;
3. No intermediate arm results are read before `batch_complete.json` exists;
4. Scoring happens uniformly only after the batch is complete; results are recorded as-is
   whichever direction they point, and no rule is changed using this batch again.

HAR-0006 / HAR-0007 are candidates **produced by the real Google ADK Runner before
SEALED-3 was unsealed, but never promoted**. This run tests only their frozen policies —
it calls no ADK and lets no agent see SEALED-3. This answers "what would happen if an ADK
candidate were promoted directly", without turning the agent into an actor entitled to
write active state.

HAR-0005 is not in this experiment: it changes the extraction schema, and validating it
requires new DWS calls. Re-routing HAR-0004's already-extracted raw can only measure "the
same result for the same policy", not schema change; calling such a pseudo-experiment a
schema arm would violate the charter rule of not saying what the artifacts cannot prove.

## 2. Frozen batch and single variable

Authoritative machine-readable plan: `docs/sealed3_multiharness_plan.json`, sha256
`9b275801349e3f684b29748a1db50882c6dcaad8ca25df88c6923bcecbf9702e`.
It embeds these constraints:

- List: `docs/sealed3_doc_list.json`, 100 documents, sha256
  `bad85f534fbf7fa5d98bcca9529087b3bd438988c27df56e72fe96c5d8f70439`;
- All arms use the same extraction schema, canonical digest
  `19e7516de0c5f98be6aa5448074ef9c0c35782ba6abad300d0372e0eb9f6452e`;
- `include_vision=false`, `render_crops=false` — no unfrozen image-reading inputs are
  introduced;
- 20 pipeline, gate, normalization, scorer, and runner files are each pinned by sha256;
- Every routing policy is copied into the in-Git evidence directory with both the file
  sha256 and the canonical policy digest pinned; the unsealing does not read the mutable
  candidate files under `runs/adk-real-*`.

`invoiceloop.sealed_batch` only temporarily provides frozen harnesses within the context
of a single `pipeline.run`; the `finally` block must restore the real
`harness.load_active`. It writes no promotion and does not modify
`active_harness.json`, so it is not a second authoritative product writer.

`absent_expected` turns `extraction_present=fail` into `expected_absent` inside
`gates.run_gates`. So here we **cannot** just swap routing on an existing matrix; every
arm must independently rerun artifact → freeze → gates → matrix → deliver from the same
stored evidence.

## 3. Seven arms (six harnesses + one exact repeat)

| arm | harness | role | pre-written comparison |
|---|---|---|---|
| B0 | HAR-0001 | conservative baseline | human-load upper bound; no auto-absent |
| B1 | HAR-0002 | TIER1 exit-rule ablation | vs B0, test removing no-conflict TIER1 forced confirmation |
| B2 | HAR-0003 | seller VAT absence ablation | vs B1, test the seller_vat_id cohort |
| P | HAR-0004 | **original-protocol primary arm / sole qualification arm** | vs B2, test the total_vat cohort; run P1/P2 vs B0 |
| P-repeat | HAR-0004 | exact-repeatability control | all run artifacts should be byte-identical |
| A1 | HAR-0006 | ADK near-placebo | re-adds an existing total_vat cohort; note harness_id reshuffles the QA hash sampling, so it is not a pure placebo |
| A2 | HAR-0007 | ADK due_date candidate | vs P, test due_date absence load reduction and silent-absence risk |

All secondary arms serve only paired description; they **must not** obtain SEALED-3
qualification, nor be promoted because a direction looks good. HAR-0004 remains the
original protocol's primary arm, "the active harness at unsealing".

## 4. Frozen endpoints and comparisons

### 4.1 Original-protocol primary endpoints

Primary arm P still follows the original protocol's H1–H7: H1–H6 call the unmodified
`scripts/heldout_metrics.py` directly; H7 = the primary arm's run completes and the audit
bundle passes offline verify. The original intervals and the "record errors as-is" rule
are unchanged.

### 4.2 Workload (all 1,000 slots, no human adjudication needed)

- `human_queue`: `route ∉ {auto_accept, auto_absent}`;
- `requires_adjudication`: legacy-compatibility measure, including `auto_absent`;
- `decision_load_for_release`: `requires_adjudication ∪ TIER1`;
- document touch: documents with at least one slot in `human_queue` / 100;
- machine_decided / machine_absent reported separately.

These are deterministic routing workloads, not "human adjudication accuracy". The latter
remains **NOT MEASURED** until the full human arm is complete.

### 4.3 Safety (DocILE truth serves only as the common judge)

Every arm uses the same `safety_metrics.score_routes`, reported split out:

- `silent_absent / absent_hits`;
- `silent_wrong / value_hits`;
- scored slots, deviations, and decidable denominators for H1–H6.

DocILE annotations do not constitute a third experimental arm, nor do they replace the
human-experience experiment; they only score all policies by the same rules.

### 4.4 Pre-registered paired directions

- lineage: B1−B0, B2−B1, P−B2;
- qualification gate: P−B0; P1 requires both silent_absent and silent_wrong not to rise,
  P2 requires human_queue not to rise;
- repeatability: P-repeat−P must be all zeros with identical run tree digest;
- ADK controls: A1−P, A2−P.

All multiple comparisons are descriptive effect sizes (slot counts, percentage points,
silent-error counts); no significance filtering, and no picking "the best arm" from them
to write claims.

## 5. Unsealing transaction and failure semantics

The unsealing command must be run only after both this addendum and the runner are
committed, with that commit's full SHA passed as `--expected-head`. The runner also
rejects any tracked-but-uncommitted changes; untracked user files do not enter the code
revision.

```bash
.venv/bin/python scripts/sealed3_multiharness.py \
  --expected-head <full SHA of this addendum's commit>
```

The batch directory must not already exist. The process first writes
`batch_started.json`; each arm writes an independent immutable run;
`batch_complete.json` is written only after all seven arms succeed, input fingerprints
match, upstream artifacts match, and the exact repeat is byte-identical. Any failed step
leaves behind `batch_failed.json` plus partial arms — nothing deleted, no in-place
resumption; that is a greppable negative artifact.

Once the batch is complete, first build the primary arm's audit bundle, then run the
frozen scorer once. The scorer re-verifies every file hash registered at unsealing;
bundles added afterwards may exist, but existing run bytes must not change.

## 6. Post-results discipline

- After this unsealing, SEALED-3 is permanently unusable for unseen evaluation of new
  policies, prompts, doctypes, or gates; any result-inspired change can only go into the
  next version and wait for SEALED-4.
- If the primary arm fails H1, P1, P2, or H7, qualification fails and the numbers are
  recorded as-is; no switching the baseline, deleting arms, or rerunning a seed.
- A1/A2 are not auto-promoted regardless of outcome. The agent only has advisory power;
  promotion still requires deterministic verification, a human signature, and fresh
  unseen evidence.
- No agent-vs-human "human accuracy" is backfilled this time; the 200-slot human arm of
  H2 will be completed and unsealed independently later, not merged into one denominator
  with SEALED-3 results.
