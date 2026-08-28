# SEALED-2 sealed evaluation results (executed 2026-08-06, completed in one pass, numbers recorded as-is)

> ## ⛔ Held-out qualification revoked (2026-08-07)
>
> **The execution record and numbers below all remain valid** — this evaluation
> really did run, and H1–H7 really did all pass. What is revoked is not the
> evaluation but SEALED-2's **status** as an "unseen set".
>
> **And this is not me deciding after the fact to be cautious — it is the
> consequence preregistered in clause 3 of this file's "Sealing discipline"
> triggering itself**: "It is forbidden to mine cohorts from this batch, adjust
> criteria, or treat this batch's numbers as development feedback; results-driven
> rule/code changes = this batch is voided, draw SEALED-3 afresh." The three events
> below each step on that clause:
>
> | When it was broken | How it was broken | Which half of clause 3 it steps on |
> |---|---|---|
> | 2026-08-07 | The discriminative tokens for `doctype.CLASSES` were written modeled on the free-text spellings of S2's `invoice_type` (`docs/DOCTYPE_EVIDENCE_2026-08-07.md` § vocabulary decontamination) | adjusting criteria |
> | 2026-08-07 | The Stage D mainline-direction prototype was scored directly against S2's 93/95 documents and KILLed on that basis (`docs/DOCTYPE_STAGE_D_2026-08-07.md`) | treating this batch's numbers as development feedback |
> | 2026-08-07 | 4 documents on S2's blocking list were viewed page by page | treating this batch's numbers as development feedback |
>
> This is exactly what preregistered criteria are for: **the trigger conditions were
> hard-coded by the past self; the present self does not get a vote.**
>
> **Consequence**: the claim wording "on an unseen sealed set, workload not rising
> and silent errors not rising" **may no longer be used**; its subject no longer
> holds. The revocation lands in the code, not in this document —
> `improve.SEALED_SET_REVOCATIONS`: when `gate_verdict` sees a qualification
> marker, what it gives is the "qualification revoked" wording, basis stays at
> `evo_truth_replay`, and `sealed2_revoked` is nailed into the promotion record.
> **Re-creating a marker file is useless**
> (`tests/test_improve.py::test_sealed2_qualified_wording_is_unreachable`).
>
> To restore the unseen-sealed claim, the only way is a new set **first seen only
> after the vocabulary and policies are frozen** (SEALED-3). SEALED-2 cannot be
> restored by "not looking at it from now on": once a held-out set is broken, it is
> broken permanently.

Protocol: `docs/SEALED2_PROTOCOL.md` (criteria, seed, exclusion pool, and promotion
gates frozen before results).
List: `docs/sealed2_doc_list.json` (drand round 6352483; seed
`b99de6bbc5e0c20707ceda77aae574391266b8d8dd5114bb8227523b680a1e59`;
PRNG context `sealed2-v1`; zero overlap with the 360-document exposure manifest /
SEALED-1 100 / old heldout).

## Execution record

- Dual-mode extraction: resume summary `done=175 / skipped=25 / failed=0`
  (finished with an authorized key after the previous round's keys were exhausted
  with 402); spent_estimate **4,368** credits (6,000 circuit breaker not
  triggered); `runs/sealed2-workspace/extract_summary.json`.
- Primary-arm run: `runs/sealed2` (HAR-0004 = currently active;
  policy_digest `eab9228721f59981…15f9f3`;
  code_revision `9bef179d956812dccd2c3fed6db5d5ccdc96772e`).
- 584 scored slots, 218 discrepancies; head-of-queue discrepancy rate 56.8% vs
  tail 17.8%.
- Routing summary (delivery measure): human_queue **468/1000 (46.8%)**,
  machine_decided 432, machine_absent 100,
  requires_adjudication 568 (including the legacy-compatibility measure).
- audit bundle: `runs/sealed2/audit_bundle.zip` sha256 =
  `91ee9cbc7b276d31f06e911e26e14169da2f3d8f5bd726375eddda76ba42566d`,
  verify members 417, failures=[] (empty adjudication → binding layer per existing
  semantics).
- field_ledger sha256 =
  `92a28fa2e0f3177ccb5072a16d139933825cfda603b3f595cd98f75405490c3c`.

Recompute:

```bash
INVOICELOOP_CORPUS=runs/sealed2-workspace \
  python3 scripts/heldout_metrics.py runs/sealed2 runs/demo
```

## Primary endpoint: H1–H6 (+H7) (HAR-0004; intervals carry over the SEALED-1 / HELDOUT preregistration)

| # | Quantity | Calibration | Old held-out | SEALED-1 | **SEALED-2** | Interval | Verdict |
|---|---|---|---|---|---|---|---|
| H1 | triage lift | 4.10× | 3.04× | 4.03× | **3.19×** | > 1.5 | **PASS** |
| H2 | coverage@46% | 78.1% | 74.3% | 77.3% | **75.2%** | > 55% | **PASS** |
| H3 | review recall | 75.1% | 72.5% | 77.7% | **72.0%** | > 55% | **PASS** |
| H4 | missing rate | 26.8% | 27.9% | 29.3% | **12.8%** | 10–45% | **PASS** |
| H5 | citation failure rate | 15.3% | 14.4% | 15.3% | **13.6%** | < 15% | **PASS** |
| H6 | frozen rejection rate | 18.9% | 34.6% | 36.6% | **34.6%** | 5–35% | **PASS** |
| H7 | operational closed loop | — | — | — | bundle 417 members, verify all pass | — | **PASS** |

**Verdict: H1–H7 all pass.** H1 is about 2.1 times the line. H5/H6 grazed their
lines and failed in SEALED-1; this batch stands back inside the intervals —
**this must not be read as "citation/freezing fixed"**: this batch's harness is
HAR-0004 (with evolution cohorts), and the corpus distribution also differs;
setting SEALED-1's HAR-0001 numbers against them is not a same-arm pairing.

## Promotion qualification (protocol §2 step 7 / §3 P1–P2)

> **2026-08-07: this entire section is void**; it is kept only to leave a record of
> what was originally written. The wording-upgrade path described below **is
> closed**, and the basis value `sealed2_qualified` is unreachable in the code.

This file is the SEALED-2 **baseline freeze point**. From here on, scored promotes
run Gate 2 against this baseline (silent errors not up + review workload not up);
after manual confirmation the qualification markers were placed on disk:

- `runs/hitl-sealed/improve/sealed2_qualified.ok`
- `runs/sealed2-workspace/improve/sealed2_qualified.ok`
- `runs/hitl-evo-b1/improve/sealed2_qualified.ok`

**These three files are still on disk, their contents untouched, all with
`harness_id` = `HAR-0004`.** The revocation **deliberately does not rely on
deleting files**: deletion would not stop the next person from writing a new one,
and it would also erase the fact that "an evaluation really did run once". What
blocks it is `improve.SEALED_SET_REVOCATIONS`. Measured (2026-08-07, against these
three real markers on disk):

```
HAR-0004: marker_names_it=True  basis=evo_replay_only  revoked=True
          "This candidate holds a SEALED-2 qualification marker, but that qualification was revoked on 2026-08-07…"
```

Before the change, the same marker would have raised basis to `sealed2_qualified`.

The `harness_id` in a marker is **the one harness it qualifies** (in this batch,
`HAR-0004`). ~~Only when that very harness is itself promoted does `basis` rise to
`sealed2_qualified`~~ — **now nobody can raise it**; a marker naming this candidate
has the same effect as an old marker naming none: basis stays at
`evo_truth_replay`, claim_limits switches to the "qualification revoked" wording,
and `sealed2_revoked` nails the revocation date and reason into the promotion
record (demotion must not be silent, Charter Four).

> 2026-08-06 correction: the initial implementation only checked whether a marker
> file existed, which turned it into a workspace-level pass. Reproduced in practice
> while running the improvement loop end to end on the workbench: a `due_date`
> absent candidate freshly mined from 12 HITL documents got stamped "passed on the
> SEALED-2 qualification set; the public claim may say workload was reduced on an
> unseen sealed set" — while on the local 12 documents it was `silent_absent 0→0`,
> the same cohort, measured on 88 unseen documents, silently dropped 5 more real
> due dates (`docs/LOOP_GENERALIZATION_2026-08-06.md`, same measure). Now
> `improve.sealed2_qualifies()` requires the marker to name the candidate itself,
> and old markers that name nothing are never upgraded (Charter Six: do not say
> what the artifacts cannot prove). Regression test:
> `tests/test_improve.py::TestPromoteSafetyGate::
> test_sealed2_marker_for_another_harness_does_not_transfer`.

## Sealing discipline (this batch's role)

1. ~~**SEALED-2 is the current sole final held-out / promotion qualification
   set**~~ — **revoked 2026-08-07. There is now not a single final held-out.**
2. SEALED-1, HITL, and the old heldout **must not** be called final held-out again;
3. **Forbidden** to mine cohorts from this batch, adjust criteria, or treat this
   batch's numbers as development feedback; results-driven rule/code changes =
   this batch is voided, draw SEALED-3 afresh — **this clause has been triggered**
   (see the revocation table at the top);
4. Development/evolution continues on SEALED-1's unseen subset and the HITL
   batches.

**Current status, in one sentence**: no set exists that can support claims of the
form "on unseen data…". Until SEALED-3 is drawn, every claim is confined to this
workspace's ground-truth scope.

## Limitations list

1. The primary arm is HAR-0004, not SEALED-1's HAR-0001 — restating ranking
   ability across batches is fine, but comparing workload/rejection rates across
   batches must declare that the arms differ;
2. H4 missing rate 12.8% is markedly lower than the previous batches (~27–29%),
   consistent in direction with machine_absent=100; possibly a distribution or
   policy difference, and no causal decomposition was done;
3. H6 34.6% hugs the upper bound (line 35%), the same-magnitude norm as the old
   held-out/SEALED-1 — not "suppressed";
4. Extraction was completed in two segments (resumed after 402); `failed=0`, but
   the spent figure follows the resume summary;
5. No second arm was run (HAR-0001 control); when a same-evidence policy swap is
   needed, open a new one — do not retro-edit this file.
