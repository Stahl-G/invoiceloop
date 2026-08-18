# InvoiceLoop × Google ADK

**ADK makes agents capable; InvoiceLoop makes their actions accountable.**

This document describes only what actually executes. Every capability named here
can be pointed at a test in `tests/test_agents_adk_pipeline.py`.

> **Correction, 2026-08-07.** An earlier version of this file claimed an Extractor
> Agent, a Vision Inspector Agent, and a Party Identification Agent that
> "inspects spatial OCR neighborhoods", and said the improvement loop was
> "orchestrated using SequentialAgent and LoopAgent". None of that was true:
> - `run_improve_loop` built `_pipeline = build_adk_pipeline(...)` and then never
>   referenced it again — the Runner was never called;
> - the Vision agent received a doc id, a field name and the existing value —
>   **no image of any kind**;
> - the Party agent received the first 40 lines of OCR as **plain text**, with no
>   bounding boxes and no geometry.
>
> Vision and Party are deleted. Extraction has always been DWS; there was never an
> Extractor Agent. The rest of this document describes the execution path.

---

## 1. Where ADK sits, and why only there

```text
   PDF ──► Nutrient DWS extraction ──► field_drafts.json (no IDs)
                                        │
        ═══════════ Trust Kernel — deterministic Python, ADK writes nothing ═══
        Freeze transaction (Python assigns FC IDs) → 6 gates → support matrix
        → routing → adjudication ledger
        ═══════════════════════════════════════════════════════════════════════
                                        │
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  ADK Runner.run_async()                  │
                    │  SequentialAgent "improve_pipeline"      │
                    │                                          │
                    │  LlmAgent  miner     → state.miner       │
                    │  LlmAgent  proposer  → state.proposals   │
                    │  BaseAgent evaluator → state.counterfactual  ← deterministic
                    │  LlmAgent  critic    → state.critic      │
                    └──────────────────┬───────────────────────┘
                                       │  improve/adk_loop_report.json (advisory)
                                       ▼
                     a person reads it → signs → Gate 2 → promote
```

**Why ADK appears only in the improvement loop.** The extraction stage has no
judgement to orchestrate — DWS extracts, Python freezes. The trust kernel is
pinned by three replay suites (`test_binding_regression` replays 454 frozen
line-level determinations from a real misbinding incident, `test_port_fidelity`
checks against the original implementations point by point, and the held-out set
must diff to zero), so putting a non-deterministic scheduler inside it would only
destroy reproducibility.

The improvement loop is the one place with real division of labour: which review
patterns are stable enough to become a rule, how to write a rule that is not too
wide, and whether a proposed rule would silently drop values that are genuinely
on the page.

---

## 2. The four stages

| Stage | Type | State key | Structured output | The judgement it makes |
|---|---|---|---|---|
| `miner` | `LlmAgent` | `miner` | `MinerFindings` | Which review patterns are stable enough to become a rule |
| `proposer` | `LlmAgent` | `proposals` | `ProposalSet` | How to write the rule without making it too wide |
| `evaluator` | `BaseAgent` | `counterfactual` | — | **Deterministic**: `improve.propose` + `improve.evaluate` |
| `critic` | `LlmAgent` | `critic` | `CriticReview` | Argues against the proposal using the counterfactual numbers |

### Why the evaluator is a custom `BaseAgent` and not a tool

A tool is invoked at the model's discretion. A counterfactual that did not run is
not a pass, so the evaluation **must** run every time. `SequentialAgent` executes
its children in order — no model output can skip it.

A failed evaluation is **not swallowed**: it becomes `blocking: true` with a
reason, and that goes to the critic and into the report. The previous version did
`except Exception: pre_evals[field] = {}`, so the critic could nod through a
proposal while holding an empty counterfactual.

Counterfactuals are keyed on the **whole normalised cohort**, not on the field
name. Keying on the field let two cohorts on one field overwrite each other's
evidence, handing the critic the wrong proposal's numbers.

---

## 3. The authority boundary

| Layer | May | May not |
|---|---|---|
| ADK / Gemini | Propose un-ID'd candidates, write an advisory report | Write the ledger, assign IDs, change a gate, declare a pass, promote |
| Python control plane | Assign IDs, freeze, evaluate deterministically, record failures | Invent field values, approve on a human's behalf |
| Human | Accept, reject or edit a candidate; sign a promotion | Rewrite a frozen input |
| Gate 2 / Gate 3 | Decide whether a candidate qualifies for promotion | Relax a rule because of how a model worded something |

**Wording is authority.** The model's output field is
`recommend_for_human_review`, never `accepted`, `approved` or `safe`. The report's
top-level counter is `recommended_for_human_review`, not `approved_by_critic`.
`test_report_says_recommend_never_approved` fails if any of those words return.

**Write boundary.** Only `improve/adk_loop_report.json`.
`improve/suggestions.json` belongs to `suggest.py` — two producers must not write
one file (`test_does_not_touch_suggestions_json`).

---

## 4. Zero-API replay

`invoiceloop/agents/adk_replay.py` hangs off each `LlmAgent`'s
`before_model_callback` / `after_model_callback`. ADK's documentation states that
when the before-callback returns an `LlmResponse`, the model call is skipped — so
in replay mode **not one request leaves the process**, while the Runner,
`SequentialAgent`, state passing and the event stream all execute normally.

A recording is keyed by the **digest of the entire request**:

```
sha256(model ‖ system_instruction ‖ contents ‖ response schema ‖ mime)
```

not by a name the call site made up. The previous version used hand-written call
ids like `critic_{field}` and `party_{doc_id}`, which carried neither the model
nor the prompt nor the schema — so after changing a model or a prompt, the old
recording would still be returned as this call's answer. **This was not
hypothetical**: the deleted `test_agents_party.py` and `test_agents_vision.py`
replayed recordings that said `gemini-2.5-flash` while the runtime default was
already `gemini-3.6-flash`, and the tests passed.

Changing the model, the prompt or the schema now changes the digest →
`ReplayRecordingMissing` → blocked. A missing recording is a blocking failure, not
"assume the model would have said this."

| Test | What it pins |
|---|---|
| `test_replay_serves_the_recording_and_never_calls_the_model` | Zero model calls in replay; byte-identical report |
| `test_replay_refuses_a_recording_made_under_a_different_model` | Change the model → blocked |
| `test_replay_refuses_a_recording_made_under_a_different_prompt` | Change the prompt → blocked |

---

## 5. Structured output

One path only: `LlmAgent(output_schema=<Pydantic model>)`, handed by ADK to
`google-genai`. The unstructured `call_gemini_model` has been **deleted** — it
swallowed JSON parse errors, and nothing a machine consumes may travel that way.

Model: `gemini-3.7-flash` (`runtime.DEFAULT_GEMINI_MODEL`), overridable via
`GEMINI_MODEL`. Missing credentials with replay off raise
`GeminiCredentialMissing` — never a silent downgrade.

ADK builds its own `google-genai` client from the process environment and does not
see InvoiceLoop's `.env` loader, so `export_credential_for_adk` bridges the two and
raises our error (the one that mentions `INVOICELOOP_REPLAY=1`) rather than ADK's
generic one.

---

## 6. Known limits, stated plainly

1. **`SequentialAgent` is deprecated in google-adk 2.6.2**, in favour of
   `Workflow`. `Workflow` is a different graph/edges API, not a drop-in. The code
   still uses `SequentialAgent`; it works, and the tests emit a DeprecationWarning.
2. **The critic's judgement quality has one data point, not a measurement.**
   Run on real review history it made a causal error — charging a baseline silent
   error count to the candidate that did not cause it — and judged correctly once
   the arithmetic moved into Python. Two proposals on one corpus is not a quality
   measurement. See [§6c](#6c-real-review-history-evidence).
3. **The counterfactual is a replay over the same 12 documents** the patterns were
   mined from. The critic's own objection to both proposals was that 9–7 samples
   may not extrapolate. The 88-document measurement in
   `LOOP_GENERALIZATION_2026-08-06.md`, followed by the SEALED-3 result below,
   says it was right to worry.

## 6b. Live-call evidence

First real call completed 2026-08-07: `gemini-3.6-flash`, `google-adk` 2.6.2 with
`google-genai` 2.17.0, three real requests, 15.3s. Recordings, inputs, outputs and
the negative controls are in
[`evidence/adk_live_2026-08-07/`](evidence/adk_live_2026-08-07/README.md).

The result that matters: **replaying with the credentials fully unset reproduces
the live report with a zero diff**, while changing the model or the prompt is
rejected with `ReplayRecordingMissing`.

## 6c. Real review-history evidence

The run above proved connectivity on a corpus with nothing to mine, so the
proposer returned `[]` and **`improve.propose` was never once called with a
model-authored cohort**. Everything downstream of the proposer was untested.

Run again on 195 real review events across 346 adjudications (zero DWS credits —
the history was already on disk), five defects surfaced immediately:

| Defect | Why the demo corpus could not show it |
|---|---|
| The model may not send a cohort `id` (charter 1) and nobody assigned one — every proposal blocked | needs a proposal |
| `kind` never passed, so absence patterns became `auto_accept` and **lost their mandatory QA probe** | needs a proposal |
| No check that a proposed cohort was one the deterministic miner actually found | needs a proposal |
| Not idempotent: a new candidate per run, whose directory name reached the critic's prompt and **broke replay** | needs a candidate to be created |
| The critic charged a baseline silent-error count to the candidate that did not cause it | needs a counterfactual |

Full write-up, before/after critic verdicts, and recordings:
[`evidence/adk_real_2026-08-07/`](evidence/adk_real_2026-08-07/README.md).

The design conclusion worth carrying: the critic's error was not fixed by a
longer prompt. It was asked to compare baseline against candidate itself. Python
now computes the deltas and hands it `improve.gate_verdict` — the pre-registered
deterministic verdict — so the model argues only about what the gate cannot see:
whether a rule is wider than the evidence behind it.

## 6d. Frozen ADK candidates on SEALED-3

Two already-existing, unpromoted ADK candidates were frozen before SEALED-3 was
opened and evaluated alongside the active policy. No ADK call occurred during
the opening, and neither candidate could change active state.

| Candidate | Compared with HAR-0004 | Human queue | Silent absence | Outcome |
|---|---|---:|---:|---|
| HAR-0006, duplicate `total_vat` absence cohort | near-placebo; harness identity still re-randomises QA samples | +4 slots | no change | no workload benefit; do not promote |
| HAR-0007, add `due_date` absence cohort | actual proposed relaxation | -33 slots (-3.3pp) | **+5** | deterministic safety gate rejects promotion |

This is evidence for the authority boundary, not a broad ADK quality score. One
candidate did nothing useful; the other found a real workload reduction but was
unsafe on unseen truth. Letting the agent auto-promote would have silently
dropped five annotated due dates. The full one-shot result, including the
primary arm's own failed qualification gate, is in
[`SEALED3_RESULTS.md`](SEALED3_RESULTS.md).

---

## 7. Reproduce

```bash
python3 -m pytest tests/test_agents_adk_pipeline.py -q
```

Nineteen tests, no network. They skip cleanly if `pip install -e ".[gemini]"` has not
been run.
