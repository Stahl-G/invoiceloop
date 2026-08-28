# Preregistration: agent adjudication vs human adjudication (2026-08-08, frozen before execution)

**The first commit of this file is the freeze point. If this file is changed after
either arm's results are seen, that arm is void.**

## 0. Question

The improvement loop's mining arm (`improve.mine`) feeds on **human adjudication
events**. To date it has fed on only 346 of them (`runs/hitl-sealed`, 12 documents).

Question: **on the same batch of review slots, can an ADK agent's adjudications
replace human adjudications as mining input? What does it cost?**

This is not about putting automatic adjudication into the product — a model that
proposes and signs off by itself closes supervision over itself (see the same
argument for `invoice_type` in the `invoiceloop/doctype.py` module docstring). This
is **measuring the cost with it as a control arm**; the numbers are recorded
as-is.

## 1. Why mine on SEALED-2 and evaluate on SEALED-1's 88

- SEALED-2's held-out status was revoked on 2026-08-07
  (`docs/SEALED2_RESULTS.md`); it is now a **development set** — mining cohorts on
  it is its legitimate role;
- Its 100 documents have **not one human adjudication**
  (`runs/sealed2/adjudication_ledger.jsonl` = 0 lines); it is a clean empty lot;
- The evaluation set uses SEALED-1's 88 documents never touched by humans —
  **disjoint** from the mining set, and the same set as the 2026-08-06
  generalization experiment, so the numbers compare directly
  (`docs/LOOP_GENERALIZATION_2026-08-06.md`);
- **SEALED-3 does not participate at any point.** This experiment makes zero DWS
  calls.

> ⚠ **Measurement-convention note**: `runs/sealed2` ran **HAR-0004**, which already
> contains the two absence cohorts mined from 12 HITL documents. So this experiment
> measures the **marginal** gain of "one more mining round on top of HAR-0004" and
> **cannot** be compared directly against the 63.7% → 55.1% of 2026-08-06 (which
> started from HAR-0001). The primary comparison is **TA vs H2**, not TA vs
> history.

## 2. Sampling (before any adjudication)

- Pool: the **468** slots with `route == "review"` in
  `runs/sealed2/support_matrix.json`;
- Slot key: `f"{doc_id}|{field}"`;
- Sampling: `random.Random("invoiceloop-arm-v1|" + seed).sample(sorted(keys), 200)`;
- Randomness source: the drand mainnet beacon, **round 6356437**, seed =
  `08b6c717dc07a6628986c48d4ad0c9b784fd53270bc7bb3ce36d233333c6e082`
  (that round's `randomness` verbatim; seed taken UTC 2026-08-08);
- The list is written to `docs/arm_slot_sample.json`, **as a separate commit,
  before any adjudication**.

### Pool composition (recorded before sampling, to preempt later claims of a cherry-picked sample)

| Dimension | Distribution |
|---|---|
| Empty / has value | 157 / 311 |
| support_strength | unsupported 233 · corroborated 226 · single_source 9 |
| Fields | due_date 89 · total_net 65 · total_vat 51 · amount_due 50 · total_gross 50 · buyer_name 46 · seller_name 34 · invoice_number 34 · issue_date 27 · seller_vat_id 22 |
| Contains QA probes | 24 (`QA_SAMPLE:*`) — `mine` excludes them by design; expected to draw about 10 |

Uniformly random, **no stratification**. Stratifying would make people suspect the
strata were chosen to fit the desired result.

## 3. Two arms (the same 200 slots, mutually blind)

| Arm | Adjudicator | Workspace |
|---|---|---|
| **TA** | ADK / Gemini agent | `runs/arm-ta` |
| **H2** | the user personally (workbench) | `runs/arm-h2` |

**The same batch of slots** is the point: only a paired design directly measures
"do the two judge the same slot the same way"; two different batches can only
compare overall distributions.

### What the two arms see must be exactly identical

Each slot gets one slot pack containing:

- Full-page rendered PNG + bbox overlay (`span_ids` frozen binding /
  `cited_span_ids` DWS pointers, the same color discipline as the workbench left
  column); rendering goes through `evidence.render_pages`, zero API;
- Slot facts: `value`, `support_strength`, `source_tiers`, `applicability`,
  `limitations`, `gate_verdicts`, `reason_codes`, `blocking_findings`.

**Neither arm sees**: the DocILE ground truth, the other arm's adjudications, or
this file's prediction section.

### Single writer (charter rule one)

The agent outputs only an **adjudication draft**: `decision` / `reason_code` /
`rationale` / `reviewer_confidence`, **with no IDs whatsoever**. Python calls
`adjudicate.append_adjudication` to assign `decision_id` / `seq` and freeze the
ledger — the same write entry and the same combination-consistency checks as a
human. The `adjudicator` field records `agent:<model>@<version>`, never
confusable with a human.

An agent abstention is recorded honestly as `abstain` and **may not be dropped**
(charter rule four).

## 4. Referee

The DocILE ground truth, with definitions exactly matching `heldout_metrics.truth`.

The ground truth is the **referee**, not an input to either arm — both arms judged
without seeing it.

## 5. Preregistered measures

| # | Quantity |
|---|---|
| M1 | TA vs truth: agreement rate by decision type |
| M2 | H2 vs truth: agreement rate by decision type (**the first time this project measures the human's own error rate**) |
| M3 | TA vs H2: paired agreement rate + 6×6 confusion matrix |
| M4 | The cohorts each arm's `improve.mine` produces (count, type, fields) |
| M5 | Downstream: the post-promotion policies of each arm replayed on the 88 → review load + silent errors, against the HAR-0004 baseline |

M5's promotion decisions follow each arm's own rules: the TA arm's are decided by
the **ADK critic**, the H2 arm's are **signed by a human**.

## 6. Preregistered predictions (locked now; if wrong, recorded as-is)

- **P1** TA can produce a `total_vat`-type `confirm_absent` cohort, but its
  `not_applicable` share of decisions will be **less than half of H2's** — the
  ground truth and the page only ever say "does this one have it"; "this class of
  documents has no such concept" is a judgment the charter reserves for humans
  (rule five).
- **P2** The TA arm's downstream absence silent-error rate is **> 3.5%** (the H
  arm's measured value on 2026-08-06).
- **P3** TA vs H2 agreement **≥ 80%** on `accept`, **< 40%** on
  `not_applicable` / `abstain`.
- **P4** The TA arm has **more** candidates reaching promote via the ADK critic
  than the H2 arm has via human sign-off.

## 7. Voiding conditions

- Changing the agent prompt / criteria / sampling after seeing either arm's
  results → **that arm is void**; redraw with a new drand round;
- The user touching any TA adjudication content before finishing H2 → **H2 is
  void** (anchoring contamination);
- The two arms' slot sets differing → **the whole experiment is void**;
- No conclusion from this experiment may be used to change the product's default
  policy unless it goes through promote with a human signature.

## 8. Blinding discipline (it constrains me, not the code)

The user directed **TA to run first**. So until H2 finishes:

1. Only the TA ledger's **sha256 and entry count** are published — not a single
   adjudication's content;
2. In conversation I may not cite any specific TA adjudication, its decision-type
   distribution, or its field distribution, nor make generalizations like "the
   agent thinks this kind is mostly missing" — that amounts to passing over the
   answer;
3. The H2 workbench pages must not be able to reach any file under `runs/arm-ta`;
4. Once H2 finishes and the ledger is frozen, unseal once, and write
   `docs/ARM_AGENT_VS_HUMAN_RESULTS_*.md`.

Rule 2 is the easiest to break in small talk. If it breaks, record the break
as-is; do not pretend it did not happen.

## 9. Cost

- DWS: **0** (SEALED-2's 200 responses were paid on 2026-08-06 and are saved and
  reusable);
- Gemini: 200 flash calls (one page image + one slot-facts block each);
- Human: the user, 200 slots.
