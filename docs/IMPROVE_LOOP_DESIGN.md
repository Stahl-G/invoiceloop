# `improve` feedback loop · design proposal (2026-08-05, pending external adjudication)

**Status: superseded by v0.2.** External senior-model adjudication (2026-08-05): direction
correct but HOLD-RECUT — the Tax AI premise was misread, “no learnable knobs” does not
hold, and the first-cut proposal does not match the fitness function. The re-cut frozen
baseline is in `IMPROVE_LAYER_V0.2_DESIGN.md`.
This file is kept as an archive (the full paper trail of proposal → adjudication →
supersession, isomorphic to the project's own discipline).

**Status**: design awaiting adjudication, not implemented. This file is self-contained,
for adjudication by a senior model / external reviewers.
After adjudication, adopted or not, the conclusion is recorded in the “Adjudication
record” section at the end of this file.

## 1. The problem

The essence of “loop engineering” is feedback-improvement. InvoiceLoop's current loop is
**closed within a single run** (extraction → freeze → gates → matrix → human adjudication
→ projection), with no learning across runs. Can we introduce a real feedback loop, like
OpenAI Tax AI / Lilian Weng's self-evolving harness?

## 2. Why this is not the harness's shape (constraint derivation, not a stance)

The premise of Tax-AI-style harness self-improvement: **cheap, trusted, complete
automated evaluators** (tax: statutes are a computable specification, and a reference
implementation yields 100% standard answers). InvoiceLoop fails all three:

1. **The oracle is incomplete.** Invoice deterministic checks (arithmetic / morphology /
   citation) are consistency checks; they can only see “internally contradictory errors”.
   Self-consistent fabrications (100+20=120 with all three values false) pass clean.
   Measured: on the held-out set, 218 discrepancies, and the arithmetic gate produced
   only ~40 findings. Optimizing an evaluator whose recall is below twenty percent =
   Goodhart; what gets learned is self-consistent fabrication.
2. **There are no learnable knobs.** The extractor is a DWS black-box API, no weights, no
   gradients; prompt/schema tuning was rejected firsthand by six rounds of preregistered
   experiments; using a reading model as the oracle was rejected in round six (reader
   silent errors 8.6–15.8%, abstention ~60%).
3. **Ground truth lives in the pixels.** “What is printed on the page” is itself the
   perception task under evaluation; without re-reading the page there is no reference
   implementation, and re-reading the page = a human or a reading model, neither of which
   can be replayed for free.

Conclusion: mechanical checks can only serve as **features**; the human is the only
**oracle**. The loop exists, but the closing point must be the adjudication ledger, not
the model itself.

## 3. Design: a verification-gated feedback loop

```
Human adjudication (ground truth accumulates with every use)
   ↓ aggregate
Candidate improvement proposals (triage ordering / new gate candidates / thresholds) —
always drafts (single-writer discipline)
   ↓ counterfactual measurement
Held-out recomputation: if adopted, how does the risk–coverage curve move
   ↓ preregistered adoption line
Adopt only Pareto improvements; non-adoptions recorded as-is (same discipline as the
six rounds of rejected proposals)
   ↓
Adoption → new calibre → calibration numbers retired / remeasurement declared (no
silent drift)
```

**The fitness function already exists**: the three-way baseline table in
`scripts/baseline_comparison.py` (automation coverage / field silent-error rate /
document silent-failure rate / review load / routing recall).
Whether a candidate change is good is judged not by intuition but by whether the curve
moves.

## 4. The first cut (minimal implementation scope)

`python3 -m invoiceloop improve --workspace ws/`:

1. **Aggregate**: adjudication ledgers of all runs in the workspace → per-field ×
   per-source correction rate / rejection rate / abstention rate (pure statistics, zero
   models);
2. **Propose (draft)**: `improve_proposals.json` — first proposal type:
   **reorder review order within the same support-strength band by historical
   correction rate** (touches ordering only, not `requires_adjudication` — touching it
   invalidates the 4.10×/3.04× calibration numbers);
3. **Counterfactual report**: recompute lift/coverage/recall for that ordering on
   `runs/heldout-r2`, side by side with the status quo; **adoption is a human decision,
   the system only supplies the numbers**.

The outputs are reports and drafts; no runtime behavior changes. Adoption = a human
edits configuration + a new round of preregistered measurement (a new held-out set),
isomorphic to the six-round process.

## 5. Explicitly not done (the negative list written into the proposal)

- No automatic gate-parameter changes, no automatic adoption — proposals are drafts,
  adoption is a human decision;
- No repeated trying on the same held-out set until it looks good (adaptive overfitting
  = the rubric's metric-gaming clause);
- No using reading-model answers as labels (round six already proved their noise level
  cannot certify improvement);
- No claim that “the system is self-improving” — the only external statement is
  “adjudication-data-driven, measurement-gated triage improvement”.

## 6. Known risks (adjudicators, attack these first)

1. **Adaptive overfitting**: if the counterfactual measurement reuses the same held-out
   set repeatedly, it amounts to tuning on the test set. Mitigation: the counterfactual
   is used only to decide “is a new round worth starting”, and adoption must rely on new
   data. Is this mitigation enough?
2. **Small-sample labels**: usage at demo scale yields only a few dozen adjudications;
   the confidence interval on each field's correction rate is extremely wide, and
   proposals may be pure noise. Should there be a minimum-sample threshold (e.g.
   field-level ≥30 adjudications)?
3. **The effect size of an ordering change may be zero**: when the requires_adjudication
   set is unchanged, reordering within a band only affects the order a human looks in,
   and lift/coverage may not move — the proposal chosen for the first cut may prove
   nothing. Should it be swapped for a coarser proposal (e.g. adjusting band
   boundaries)?
4. **Adjudicator drift**: the same person adjudicating inconsistently at different times
   pollutes the labels. Should an adjudicator dimension be recorded and consistency
   checked?
5. **Narrative risk**: the four characters “feedback loop” are easily read as “the model
   improves itself” — if external copy does not converge, it invites rubric G2 (evidence
   integrity) scrutiny.

## 7. Relation to the competition window

If implemented after the competition opens on 8/17, it is at the same time “real
in-competition incremental work” (part of the eligibility-disclosure strategy).
If the adjudicators find the design valuable but think implementation should wait for
the opening, this file is the disclosure material.

## Adjudication record

2026-08-05, external senior model: **HOLD-RECUT**. Three points overturned: ① the key
to Tax AI is not a complete oracle but the engineering path
trace→finding→targeted eval→human ship, and InvoiceLoop already has its foundations;
② “DWS is a black box, therefore no learnable knobs” does not hold —
routing/escalation/schema/normalization are all harness; ③ reordering within a band does
not change the requires set, mismatching the claimed fitness function (coverage / silent
errors / load). Per the adjudication this was re-cut as v0.2 (see
IMPROVE_LAYER_V0.2_DESIGN.md), and this proposal was archived.
