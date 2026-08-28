# Response to the architecture adjudication (of the implementation plan) (2026-08-05)

The review target was the implementation plan I wrote + the b5fe7a0 zip (it did not
see the implementation that landed after the plan). Verdict: direction PASS, plan
CONDITIONAL PASS + eight revisions. Item-by-item status of what landed:

## Implemented per the revisions (this round)

| Revision | What landed |
|---|---|
| Two: separate input/execution identity | `input_manifest.fingerprint` is back to pure input; new `execution_fingerprint` (input + code_revision + harness_id + harness_digest + routing-v1); `find_run_by_fingerprint` works off the execution fingerprint, with legacy fallback automatically opening a new generation; a test pins "same input, same input fingerprint (provable pairing); different harness, different execution fingerprint" |
| Three: verify recomputes routing | matrix rows gain `slot_blocking`/`doc_blocked`; the verify semantics layer adds: digest consistency of the embedded policy + recomputing routes from the in-bundle row facts and comparing slot by slot (a forged routing plus a synchronously recomputed snapshot still cannot pass; pinned by a regression test); deliver's route/requires now come from routing_report (a snapshot component), not from the matrix |
| Four: deterministic QA sampling | `routing._qa_hit`: hash sampling via sha256(seed+harness+doc+field+version), not a random number; policy configured with `policy_accepted_tier1_rate` 5% / `cohort_relax_rate` 20%; both target classes empty for HAR-0001, zero diff does not break; 5 tests (determinism / rate 0 / rate 1 / HAR-0001 zero hits / cohort hit) |
| Five: EVO evaluation is not called promotion | PROM records carry `basis: evo_replay_only` + `claim_limits` (no unseen qualification set = demo activation, public claims restricted); PROMOTION-1 new data + credits is a user decision |
| Six: feedback diagnostics contract | `reviewer_confidence` (high/medium/low) + reason↔decision combination validation (CONFIRMED_ABSENT may not carry accept, etc.); feedback events carry `actionable` (reason code + medium-high confidence + not abstaining); business adjudication and diagnostic labels keep their two layers of semantics |
| Seven: the active pointer is a projection | PROM records bind candidate/baseline policy digest + eval result digest; `improve rollback` command: rollback = a new PROM record (append-only); HAR-0001 materializes automatically in the bundle |
| Eight: operational/safety metric denominators split | The R0 document is split: operational metrics (all slots, no ground truth) 61.2%/100%/82.3%; safety metrics (ground-truth subset) appear only in the three-party baseline document |

## Adjudication item one (P0-6 semantic stance) — a different choice than the review's, recorded on file

The review asked HAR-0001 to policy_accept TIER1 slots with requires=false outright.
We keep `release_tier1_explicit: true` (explicit human adjudication of TIER1
corroboration slots before the document is released): this is the release strategy
the user approved after the 78 review's P2, not implementation laziness. The
policy_accept mechanism is ready (the mechanism itself is not a sham approval — it
explicitly records the policy version); switching TIER1 explicit to policy_accept
is legitimate content for the first R1 candidate, going through full evaluation +
promotion, not a build default. The disagreement between the two positions is
written into the IMPROVE_LAYER_V01_IMPLEMENTATION document.

## Correct per the review but unchanged this round

- Multi-tier adaptive QA sampling (we only do two fixed rates);
- A two-person review workflow (the recording dimension exists; the process is an
  organizational matter);
- Sealed final eval (needs new data + credits; user decision);
- The PROMOTION-1 qualification set (same).

## Eligibility timeline (a review reminder)

Official kickoff 8/17 10:00 PDT = 8/18 00:00 ICT. This batch of code was still
produced before kickoff, so follow the disclosure strategy: after this round's
commit, tag `pre-hackathon-baseline`; increments during the hackathon (any new
features/video/re-test) diff cleanly against that tag.
