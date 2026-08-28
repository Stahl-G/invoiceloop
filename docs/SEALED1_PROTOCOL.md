# SEALED-1 sealed evaluation protocol (2026-08-05, frozen before execution)

Adjudication decision 69: cases from the old 100-document held-out set entered
development (C3/C8 fixes, drift analysis), so it can serve only as a
regression/evolution set, no longer as final held-out. This protocol builds a
genuinely unseen sealed set. **Key differences from the old HELDOUT.md: the sampling
seed comes from an external randomness source that did not exist until after the code
freeze, so the list was mechanically unpredictable during development (senior
adjudication one); the exclusion pool is the full exposure manifest, not just the two
official lists (senior adjudication two).**

## 0. What is frozen (frozen at the moment this file is committed)

- Product code: the first commit of this file is the freeze point
  (verifiable via `git log --diff-filter=A -- docs/SEALED1_PROTOCOL.md`);
- Evaluation script sha256:
  - `scripts/heldout_metrics.py` = a486e82f…01d804
  - `scripts/baseline_comparison.py` = 5eb34dcb…c865eb
  - `invoiceloop/heldout.py` (sampling/extraction driver) = e5588497…40d4cbf
- Exclusion pool: `docs/development_exposure_manifest.json` (260 documents:
  calibration 160 + old held-out 100 + vendored demo 3, each entry with
  reason/source);
- harness: bundled HAR-0001 (`release_tier1_explicit: true`, zero cohorts).

## 1. Random seed commitment (commit first, reveal later)

- Randomness source: drand mainnet beacon (`https://api.drand.sh/public/{round}`,
  one round every 30 seconds, unpredictable on-chain and publicly verifiable after
  the fact);
- **Committed round: 6350076 = 2026-08-05T12:35:00Z**.
  Revision record: the original commitment was 6350246 (≈14:00Z); the user
  instructed moving it earlier. This revision was committed at ~12:26Z, still
  before round 6350076 was revealed (at commitment time that round's randomness did
  not yet exist), and the freeze commit for the code/scripts/exclusion pool
  (5050dfb) precedes everything — the mechanical property that "the list is
  unpredictable during development" is unchanged; the time gap shrank from ~4 hours
  to ~9 minutes;
- Seed = the literal `randomness` field (hex) of that round; sampling =
  `heldout.sealed_list(seed)`: `random.Random("invoiceloop-sealed1-v1|" +
  seed).sample(sorted(pool), 100)`, pool = documents with ≥4 scored-field
  annotations ∧ not in the exposure manifest;
- Anyone can afterwards recompute the list from the same round + the same code —
  verifiable, not predictable.

## 2. Execution order (must not be reordered)

1. ✅ Fixes 1–5 landed, 345 tests all green, committed;
2. ✅ Exposure manifest generated and committed;
3. This protocol + script hashes committed (**the round is committed first**);
4. After the round is revealed: take randomness → `python3 -m invoiceloop sealed plan
   --workspace runs/sealed1-workspace --seed <hex> --seed-source
   "drand round 6350246"` → **list commit** (before any DWS call);
5. `python3 -m invoiceloop sealed extract --workspace runs/sealed1-workspace`
   — 200 calls (understand + agentic), budget circuit breaker 6000 credits
   (with the old held-out set's measured 4,758 as the reference); keys read only
   from `DWS_API_KEYS` or `~/.config/invoiceloop/heldout.keys`; resume from
   checkpoint; 4xx responses are also evidence;
6. `INVOICELOOP_CORPUS=runs/sealed1-workspace python3 -m invoiceloop run
   --out runs/sealed1 --doc-ids <list>`;
7. Evaluate **once** (see §3), results written into docs/SEALED1_RESULTS.md,
   numbers recorded as-is;
8. Build the evidence bundle (raw + run artifacts + evaluation output + command
   logs), publish the sha256.

Network failures are recovered by the existing checkpoint-resume mechanism;
**results-driven rule/code changes = this batch is voided, SEALED-1 is
automatically demoted to a regression set**, and a new batch is drawn with a fresh
seed.

## 3. Preregistered endpoints (must not be modified after execution)

### Primary endpoint (qualification goal: lift the held-out ceiling)

Reliability and operational closed loop of the current HEAD on an unseen set.
Criteria carry over HELDOUT.md's intervals (control group = the calibration 160's
measured values under the same measure):

| # | Quantity | Pass interval |
|---|---|---|
| H1 | triage lift (front-50% discrepancy rate / back 50%) | > 1.5 |
| H2 | coverage@46% | > 55% |
| H3 | review recall | > 55% |
| H4 | extraction_present missing rate | 10–45% |
| H5 | failure rate on the citation-decidable subset | < 15% |
| H6 | frozen rejection rate | 5–35% |
| H7 (new) | operational closed loop | run completes + bundle passes four-layer verify |

Verdict as in the old protocol: H1 below bar = overall failure; any other below
bar = written truthfully into the limitations list with the numbers attached,
without adjusting criteria and retesting.

### Secondary endpoint (research goal: ranking comparison, **without presupposing an InvoiceLoop win**)

- paired recall difference @ review budgets 10/20/30/40% (triage order vs
  ascending confidence, same batch of slots, same budget, paired difference);
- matched-coverage selective risk: compare silent errors at points where the two
  rankings reach equal coverage;
- per-document bootstrap paired 95% CI (seed fixed at 42);
- tie rule: confidence ties are broken by the fixed (doc_id, field) order, plus
  best/worst/expected is reported when a cut lands inside the same tie group
  (already implemented and frozen in baseline_comparison.py);
- power statement (written down in advance): at the scale of 100 documents × 285
  slots, differences of a few percentage points **may not reach statistical
  significance**; non-significance is not an experimental failure — truthfully
  reporting the point estimate + CI is enough. Whatever the outcome, the code is
  not changed and this batch continues in use.

## 3.5 Second arm (revised 2026-08-05 12:5xZ, preregistered before any results were out)

User decision (2026-08-05): remove mandatory manual confirmation for non-conflicting
TIER1 slots. The decision lands as **HAR-0002** (`release_tier1_explicit: false`,
otherwise identical to HAR-0001), going through the full propose → evaluate →
promote channel.

SEALED-1 gains a second arm: the same batch of sealed raw evidence, the same frozen
code, re-run with only the routing policy swapped to HAR-0002 (zero API calls;
extraction and gates unchanged — routing is a pure function applied after the
evidence is frozen). The two arms are reported paired:

- field-review workload / release-decision workload / document touch rate (effort);
- H1–H6 under the same measure (safety, ground-truth evaluation);
- per-document bootstrap CI of the differences.

This revision was committed after the list was generated and **before any SEALED-1
result was visible**; the primary arm's (HAR-0001) criteria and pass lines are
unchanged to the letter.

## 4. Claim discipline (in force before and after the evaluation)

- SEALED-1 passing ⇒ it becomes permissible to say "the current HEAD holds H1–H6
  magnitudes on a 100-document sealed set unseen during development"; not passing ⇒
  the limitations list is recorded as-is;
- Secondary endpoint, whichever direction ⇒ report only numbers and CIs; "better
  than the confidence ranking" may be said only when the paired CI lower bound
  > 0, and must carry the tie-range caveat;
- This batch does not double as the PROMOTION-1 qualification set (a promotion
  qualification set is a one-shot consumable; a separate batch is required).
