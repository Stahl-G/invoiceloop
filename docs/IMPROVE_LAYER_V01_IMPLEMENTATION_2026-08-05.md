# Improve Layer implementation record (2026-08-05, v0.2 narrowed version)

Implementation baseline: `docs/IMPROVE_LAYER_V0.2_DESIGN.md` (the frozen design after
external adjudication).
This file records what the **narrowed version** shipped, what it did not ship, and the
measured numbers.

## Landing map

| v0.2 design item | Status | Evidence |
|---|---|---|
| P0-1 final values come from the frozen ledger | ✅ (prior batch b4ad192) | tests/test_projection_integrity.py |
| P0-2 decision semantics split | ✅ (prior batch b4ad192) | accept/confirm_absent/not_applicable/reject/correct/abstain |
| P0-3 routing standalone | ✅ | `routing.py` + `routing_report.json` (a snapshot component); HAR-0001 is **byte-for-byte equivalent** to the old inline criteria: heldout 100-document rerun (r2 vs r3) with zero row-level differences and H1–H6 identical bit for bit; tests/test_routing.py |
| P0-4 harness enters the fingerprint | ✅ | `input_manifest` includes harness_id + policy_digest; after promotion the same input opens a new run (pinned by test_improve.py) |
| P0-5 normalization separated | ✅ | `eval_norm.py` frozen copy, dedicated to eval scripts; freeze-point consistency test |
| P0-6 policy_accept | ✅ | policy releases with `release_tier1_explicit=false` project as `policy_accepted`, the value still comes from the frozen claim, source=policy:HAR-xxxx |
| FeedbackEvent | ✅ narrowed | `feedback.py` derives from the adjudication ledger + matrix; reason_code optional (minimal reason-code set, humans supply it and the system never fills it in); workbench form has a dropdown |
| Weakness mining | 🟡 downgraded | `improve mine` = deterministic cohort statistics + low-yield candidates flagged; selection-bias warning printed at the top of the report; no automatic attribution |
| Candidate + lint | ✅ | `improve propose`: only adding cohorts allowed, only generic features (field/tier/strength); anything outside the whitelist is rejected |
| Evaluate | ✅ narrowed | `improve evaluate` = counterfactual re-routing (no pipeline rerun, zero API); explicitly draws no safety conclusions (ground-truth evaluation belongs to the sealed protocol) |
| Promotion | ✅ | `improve promote` is the only writer of the active pointer; requires a human name + rationale + ISO timestamp; PROM record + rollback target |
| Sandbox / three processes | ❌ not done (single-person hackathon) | replaced by linter + CLI permission boundaries |
| QA sampler | ❌ not done | randomness entering runs breaks the determinism discipline; needs a seeded design, to be discussed separately |
| escalation/schema candidates | ❌ v0.2/v0.3 material | |
| sealed final eval | ❌ | requires new data + DWS credits |

## R0 measurements (enforcement of design prohibition #16)

`docs/R0_BASELINE_2026-08-05.md`: mandatory field review load **61.2%**,
document touch **100%**, decision_load_for_release **82.3%**.
**The “41%” figure is a TIER1-only counterfactual subset calibre, not R0** — the
external narrative follows the measurements.

## The semantic stance of P0-6 (reply to architecture adjudication one)

HAR-0001 keeps `release_tier1_explicit: true` — “a TIER1 corroboration slot must receive
explicit human adjudication before whole-document release” is a **human-approved
policy** after 78 adjudications (it guards against fake human approval), not
implementation laziness. The judges' ruling asks for automatic policy_accept of
conflict-free TIER1, which swaps “silently entering the deliverable” for “explicitly
entering the deliverable as policy_accept with a policy version” — the honesty gain of
the latter holds, but it must go through full evaluation + promotion as an R1 candidate,
not become the default from day one. PROM records carry `basis: evo_replay_only`: a
promotion without an unseen qualification set is only a demo activation, and the public
calibre must not say “reduces human work on unseen data”.

## Closed-loop demo (all CLI, verified in practice)

```bash
python3 -m invoiceloop improve mine --workspace ws       # 38 events, 14 cohorts
python3 -m invoiceloop improve propose --workspace ws --cohort-id C1 \
  --field seller_name --strength corroborated --finding FIND-001 --prediction "..."
python3 -m invoiceloop improve evaluate --workspace ws --candidate HAR-0002
python3 -m invoiceloop improve promote --workspace ws --candidate HAR-0002 \
  --approved-by <name> --rationale "..." --approved-at 2026-08-17T10:00:00
# afterwards run --workspace automatically opens a new generation (digest changed), bound to HAR-0002
```

The evaluate delta can be 0.0pp (a small workspace has no slots hitting the cohort) —
an honest zero, not a bug. For demos, use a cohort that actually hits in the mine
report.

## Tests

326 all green (new: test_routing 7 + test_improve 7 + test_eval_norm 2 +
policy_accept 1); fresh-venv judge gate: 278 passed, 41 skipped.
