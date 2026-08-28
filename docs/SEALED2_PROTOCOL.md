# SEALED-2 sealed evaluation protocol (2026-08-06, frozen before execution)

SEALED-1 has completed its final-held-out duty and been demoted to an
evolution/regression set (see `docs/SEALED1_RESULTS.md` limitation 4 and
`docs/LOOP_GENERALIZATION_2026-08-06.md`). This protocol builds another batch of
100 genuinely unseen documents, serving as the promotion qualification set
(PROMOTION-1) and the sole basis for the public "unseen data" claim.

**Key differences from SEALED-1:**
- The exclusion pool already contains all 100 of SEALED-1
  (`docs/development_exposure_manifest.json`);
- The sampling PRNG context is `invoiceloop-sealed2-v1` (not sealed1-v1), to avoid
  stream collision;
- This batch doubles as the promotion qualification set; results-driven rule/code
  changes = this batch is voided.

## 0. What is frozen (frozen at the moment this file is committed)

- Product code: the first commit of this file is the freeze point;
- Exclusion pool: `docs/development_exposure_manifest.json` (must contain the
  sealed1-100);
- Sampling implementation: `invoiceloop/heldout.py::sealed_list(..., context="sealed2-v1")`;
- harness: the active harness locked at evaluation time (digest recorded as-is
  when RESULTS is written).

## 1. Random seed commitment

- Randomness source: drand mainnet beacon (`https://api.drand.sh/public/{round}`);
- **Round for this batch: 6352483**; seed =
  `b99de6bbc5e0c20707ceda77aae574391266b8d8dd5114bb8227523b680a1e59`
  (the literal `randomness` field of that round);
- Sampling = `heldout.sealed_list(seed, context="sealed2-v1")`:
  `random.Random("invoiceloop-sealed2-v1|" + seed).sample(sorted(pool), 100)`,
  pool = documents with ≥4 scored-field annotations ∧ not in the exposure
  manifest;
- List on disk: `docs/sealed2_doc_list.json` (identical to the workspace copy);
  anyone can recompute it publicly.

## 2. Execution order (must not be reordered)

1. Merge SEALED-1's 100 into the exposure manifest and commit;
2. Commit this protocol (**the verifiable order, written into the repo before the
   list draw: protocol and exclusion pool frozen → take the seed → list written to
   disk and committed → only then may extract run**);
3. `python3 -m invoiceloop sealed plan --workspace runs/sealed2-workspace
   --seed <hex> --seed-source "drand round <N>"` → copy to
   `docs/sealed2_doc_list.json` and **commit separately** (before any DWS call);
4. **Only after explicit budget authorization**:
   `python3 -m invoiceloop sealed extract --workspace runs/sealed2-workspace`
   — 200 calls (understand + agentic), budget circuit breaker 6000 credits;
5. `INVOICELOOP_CORPUS=runs/sealed2-workspace python3 -m invoiceloop run
   --out runs/sealed2 --doc-ids <list>`;
6. Evaluate once, results written into `docs/SEALED2_RESULTS.md`, numbers
   recorded as-is;
7. If used as promotion qualification: place `improve/sealed2_qualified.ok` in the
   target workspace (manual confirmation that the SEALED-2 eval has passed Gate 2);
   **the marker must name the `harness_id` it qualifies** — only when that very
   harness is itself promoted does `basis` rise to `sealed2_qualified`; derived
   candidates **do not inherit** it
   (`improve.mark_sealed2_qualified(ws, harness_id=...)`; rationale in the
   2026-08-06 correction in `docs/SEALED2_RESULTS.md`).

Network failures are recovered by checkpoint resume; **results-driven rule/code
changes = this batch is voided, SEALED-2 is automatically demoted to a regression
set**, and a new batch is drawn with a fresh seed.

## 3. Preregistered endpoints

The primary endpoint carries over the H1–H7 intervals from SEALED-1 / HELDOUT (see
`docs/SEALED1_PROTOCOL.md` §3). Promotion gates added on top:

| # | Quantity | Pass |
|---|---|---|
| P1 | Gate 2 silent_absent / silent_wrong relative to baseline | does not rise |
| P2 | field-review workload relative to baseline | does not rise |

## 4. Claim discipline

- SEALED-2 passing ⇒ it becomes permissible to say "the current HEAD holds H1–H6
  magnitudes on a 100-document sealed set unseen during development / workload not
  rising and silent errors not rising";
- SEALED-1, HITL-12, and the old heldout-100 **may none of them** be called final
  held-out any more;
- Before extract has run, promote — even when `pareto_gated` — may use only
  `basis=evo_truth_replay` and must not claim unseen-sealed workload reduction.
