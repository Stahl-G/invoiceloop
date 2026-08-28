# SEALED-3 sealed evaluation protocol (2026-08-07, frozen before execution)

SEALED-2 has been retired with its authorization revoked due to development-time
vocabulary/prototype contamination (it no longer serves as an unseen promotion set;
see `docs/SEALED2_RESULTS.md` and contamination adjudication F). This protocol builds
another batch of 100 genuinely unseen documents, as the current sole candidate for the
final held-out / promotion qualification set.

**Key differences from SEALED-2:**
- The exclusion pool now contains all 200 of SEALED-1 + SEALED-2
  (`docs/development_exposure_manifest.json`, unique≈460);
- The sampling PRNG context is `invoiceloop-sealed3-v1`, avoiding stream collisions;
- **Sealed and unread by default after extraction**: the batch contents must not be mined
  for invoice types/vocabularies/strategies; before an unsealed evaluation, no RESULTS
  may be written and no qualification marker attached.

## 0. Frozen objects (frozen as of this file's commit)

- Product code: this file's first commit is the freeze point;
- Exclusion pool: `docs/development_exposure_manifest.json` (must contain sealed1-100 + sealed2-100);
- Sampling implementation: `invoiceloop/heldout.py::sealed_list(..., context="sealed3-v1")`;
- harness: the active harness locked at unseal-evaluation time (digest recorded as-is in RESULTS).

## 1. Random seed commitment

- Randomness source: drand mainnet beacon (`https://api.drand.sh/public/{round}`);
- **Round for this batch: 6356175**; seed =
  `c3062ff4dfea53a7b36c67ee8f9a95b1180e37bb1999272d6bdb37d8284ad0e9`
  (the verbatim `randomness` field of that round; seed taken UTC 2026-08-07);
- Sampling = `heldout.sealed_list(seed, context="sealed3-v1")`:
  `random.Random("invoiceloop-sealed3-v1|" + seed).sample(sorted(pool), 100)`,
  pool = ≥4 scored-field annotations ∧ not in the exposure manifest;
- The list is written to disk: `docs/sealed3_doc_list.json` (identical to the workspace copy);
  anyone can recompute it publicly.

### Seed on record

- Round: `6356175`
- Seed (hex): `c3062ff4dfea53a7b36c67ee8f9a95b1180e37bb1999272d6bdb37d8284ad0e9`
- Seed time (UTC): `2026-08-07` (`api.drand.sh/public/latest` at protocol freeze)

## 2. Execution order (must not be reordered)

1. Merge SEALED-2's 100 into the exposure manifest and commit;
2. Commit this protocol (**before the list is drawn**);
3. Take a public drand round → fill it into §1 "Seed on record" → commit;
4. `python3 -m invoiceloop sealed plan --workspace runs/sealed3-workspace
   --context sealed3-v1 --seed <hex> --seed-source "drand round <N>"`
   → copy to `docs/sealed3_doc_list.json` and **commit separately** (before any DWS call);
5. **Only after explicit budget authorization**:
   `python3 -m invoiceloop sealed extract --workspace runs/sealed3-workspace`
   — 200 calls (understand + agentic), budget circuit breaker 6000 credits;
6. **Sealed and unread**: after extract completes, record only the ops summary
   (done/failed/spent from `extract_summary.json`); **must not** `run` / unseal-evaluate /
   read raw / tune vocabularies or strategies on this batch,
   unless a separate "unseal" adjudication is opened and RESULTS written;
7. After unsealing: evaluate once → `docs/SEALED3_RESULTS.md`, numbers recorded as-is;
   if used as promotion qualification: name the harness and place `improve/sealed3_qualified.ok`
   (mechanism aligned with S2's harness binding; derived candidates must not inherit it).

Network failures are recovered by resuming from checkpoints; **any result-driven rule/code
change = this batch is void, SEALED-3 is automatically demoted to a regression set**, and a
new batch must be drawn with a fresh seed.

## 3. Pre-registered endpoints

The primary endpoints carry over the H1–H7 intervals of SEALED-1 / HELDOUT
(see `docs/SEALED1_PROTOCOL.md` §3). A promotion gate is added (applies at unseal evaluation):

| # | Quantity | Pass |
|---|---|---|
| P1 | Gate 2 silent_absent / silent_wrong relative to baseline | no increase |
| P2 | field-review load relative to baseline | no increase |

## 4. Claim discipline

- Before SEALED-3 is unsealed ⇒ **must not** claim unseen-sealed load reduction or promotion
  qualification; only extraction ops may be reported (call counts / failures / spend estimate);
- If SEALED-3 passes unsealing ⇒ it may be said that "the current HEAD holds H1–H6 magnitudes
  on a 100-document sealed set unseen during development, with no load increase and no
  silent-error increase";
- SEALED-1, SEALED-2, HITL, and the old heldout-100 **may never again** be called final held-out;
- The `sealed2_qualified` path on SEALED-2 has been de-authorized and must not be revived
  as unseen evidence.
