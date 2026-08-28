# Response to the 81/100 review (senior-model adjudication) (2026-08-05)

Reviewed commit b5fe7a0, verdict 81/100 CONDITIONAL PASS + one P0 semantic-integrity
hole + HOLD-RECUT on the improve design. This review actually ran the attack chain
on a copy; it was not a paper review.

## P0-1: the projection treated as the authoritative value (review's live attack; all confirmed real)

Attack: modify only support_matrix.json (not a snapshot component) → accept → the
deliverable emits the poisoned value → all three verify layers pass. After we
reproduced and confirmed it, we fixed it in four layers:

1. **deliver.py value source switched to the frozen ledger**: accepted values come
   from the field_ledger claim; the matrix only supplies the row set and the
   requires flag; an accept pointing at a nonexistent claim → the whole document
   is blocked;
2. **append cross-checks projection ↔ authority**: a matrix row value that
   disagrees with the frozen claim in the same slot → the adjudication is refused
   (an extension of the principle "no adjudication is recorded on evidence that
   has been touched");
3. **verify layer 4 (semantics layer)**: in-bundle projection values cross-checked
   against authority — matrix row values vs frozen claims, deliverable accepted
   values vs claims, correction values vs adjudications, rejected/missing slots
   must not carry values; an attacker who recomputes the MANIFEST still cannot
   pass this layer (pinned by a regression test: members/snapshot both pass,
   semantics catches it);
4. **Regression tests** `tests/test_projection_integrity.py`: one per defense
   layer + one full attack chain, 7 tests.

## P0-2: decision-semantics split (implemented)

`accept` (must carry claim_id) / `confirm_absent` / `not_applicable` / `reject` /
`correct` / `abstain`. Legacy accept projections without a claim map to
confirmed_absent and are flagged legacy; the workbench form offers different
decision sets depending on slot shape (with a claim: accept/reject/correct/abstain;
without a claim: confirm_absent/correct/not_applicable/abstain). "Confirmed absent"
and "human could not tell" are two distinct signals from now on — critical for any
future feedback loop.

Releasing document-level blockings: no new document_override decision type is added
(the object of adjudication is the slot); instead a separate state
`released_with_caveats` — counted separately from normal released, with caveats
listing which machine checks did not run. Disclosure unchanged; the states no
longer mix.

## P1: baseline expansion and number convergence

- **Correcting a factual error**: "DWS gives no field-level confidence" was wrong —
  `output.metadata.<field>.confidence` exists (0.95/0.4, groundingScore,
  no-logprobs). BASELINE_COMPARISON.md has been corrected with the change left on
  record;
- **New confidence-threshold baseline** (≥0.95): TIER1 silent errors 16.10%,
  recall 55.8%;
- **New same-human-budget comparison + per-document bootstrap CI**: the honest
  result — triage order and confidence-ascending order **tie** on recall@budget
  (CIs fully overlap). The document's reading has converged: triage's
  differentiation lies in operating-point safety and verifiability, not in ranking
  quality;
- **Real human load**: deliverable summary adds `decision_load_for_release`
  (requires_adjudication ∪ TIER1), measured 0.83 on the demo — reported side by
  side with the counterfactual triage load 0.42, not hidden;
- Fixed one self-discovered bootstrap bug: after per-document resampling you must
  re-sort by queue_idx, otherwise the CI excludes the point estimate (fixed and
  pinned by a test).

## Step 6: execution identity enters the fingerprint

`build_input_manifest` now folds `code_revision` (git HEAD) into the fingerprint:
if the code/policy changes, the same input no longer replays the old run and a new
generation opens automatically. Non-git environments record null and disclose it
honestly. Docs-only commits also turn the generation — the conservative direction;
better a new run.

## improve design: deferred per the user's instruction

The user decided the improve layer needs more discussion; this round does not
rewrite the design document. The review's HOLD-RECUT points (the Tax AI premise
misread, the editable surface does exist, the fitness function mismatches the
proposal, sealed final eval) are preserved in full in the review record, to be
written back after discussion.

## Pointed out by the review, evaluated by us, left unchanged

- **Fold the whole matrix into snapshot components**: no. The matrix is a
  rebuildable projection; architecturally the snapshot binds only authority. The
  correct fix is a value source rooted in authority + semantic-layer
  cross-validation (done), not promoting the projection to authority.
- **verify fully rebuilds matrix/deliverable for byte comparison**: not for now.
  The semantics layer already covers value-level consistency; a full rebuild
  requires re-running matrix construction inside the bundle (including understand
  response parsing); complexity and payoff do not match; backlog item.

## Numbers

309 passed locally; fresh-venv 259 passed + 41 skipped (corpus guard).
