# The improvement loop on real review history (2026-08-07)

The previous live run (`../adk_live_2026-08-07/`) was a connectivity proof on the
demo corpus: 2 documents, 3 adjudications, and all three models correctly
returned empty lists because there was nothing to mine. `ADK_INTEGRATION.md`
recorded the gap in plain words: *"Behaviour on a corpus with real review history
is not yet measured."*

This is that measurement. It cost **zero DWS credits** — the review history
already existed on disk.

## What ran

```bash
python3 -m invoiceloop agents improve-loop --workspace runs/adk-real-2026-08-07
```

| | Demo corpus (first live run) | This run |
|---|---|---|
| Documents | 2 | 12 |
| Adjudications | 3 | **346** across 6 runs |
| Mining events | 3 | **195** |
| Mined cohorts | 0 | **9** + 2 absence candidates |
| Proposals | 0 | 2 |

Source workspace is `runs/hitl-sealed`, copied rather than used in place so the
review history is not mutated by a measurement.

## Four defects, none of which the demo corpus could reveal

Because the demo run produced zero proposals, **`improve.propose` was never once
called with a model-authored cohort.** Everything downstream of the proposer was
untested. All four of these surfaced on the first run with real patterns.

### 1. The model may not send an ID, and nobody assigned one

Charter rule 1 says models write no IDs; Python assigns them. The proposer
correctly emitted `{"field": "total_vat", "tier": "TIER1"}` with no `id`. But
`lint_policy` requires a cohort `id`. Both sides were obeying the rule and
nothing connected them:

```
proposals: 2, blocking_evaluations: 2
blocking_reason: "ValueError: 这个候选没能通过审查:cohort 缺 id"
                 (verbatim: "this candidate did not pass review: cohort has no id")
```

Python now derives the id from the cohort's content (`AE-total_vat`), not from a
counter — a counter would make the id depend on how many times the loop had run,
and replay would stop matching.

### 2. The safety-relevant `kind` was never chosen

`improve.propose` takes `kind`, and the evaluator never passed it, so every
proposal defaulted to `auto_accept`. Both real proposals were **absence**
patterns ("all 9 reviews confirmed absent, zero corrections"), which belong to
`absent_expected` — a different rule that **forces a 20% QA probe** so the
absence keeps being checked. `auto_accept` has no probe.

Letting the model pick would hand a safety decision to the model. Python now
derives it from the deterministic mining report: a field in `absence_candidates`
is an absence rule. Absence is a field-level property, so `tier` is stripped —
`_ABSENT_KEYS` rejects it.

### 3. Anything the model invented would have been evaluated

There was no check that a proposed cohort corresponds to something the
deterministic miner actually found. A model could propose a rule with no
supporting review events and the system would scaffold it, run a counterfactual,
and present it for signature. The model now chooses *among* mined cohorts and
cannot introduce one.

### 4. The loop was not idempotent, and that broke replay

Each run scaffolded a fresh candidate (`HAR-0002` → `HAR-0003` → …). The
directory name and policy digest travelled into the critic's prompt, so the
request digest changed on every run and **recording then replaying in the same
workspace raised `ReplayRecordingMissing`**. The bug in #1 had hidden this
completely: `propose` always failed, so no candidate was ever created.

Fixed on both sides — the loop reuses an existing candidate for the same cohort
(matched on policy content, not on id), and the critic's view is an **allowlist**
that excludes bookkeeping fields entirely.

## The measurement that actually mattered: is the critic any good?

With the counterfactuals running, the critic argued against **both** proposals:

> "Relaxing policy for total_vat in TIER1 yields a minimal review load reduction
> of only 1.67 percentage points across 120 slots while **leaving 5 silent wrong
> extractions exposed**." — `risk: HIGH`, `recommend_for_human_review: false`

The number is real. The causation is not:

| | total_vat | due_date |
|---|---|---|
| `silent_absent` baseline → candidate | 0 → 0 | 0 → 0 |
| `silent_wrong` baseline → candidate | **5 → 5** | **5 → 5** |
| `review_load` baseline → candidate | 0.567 → 0.550 | 0.567 → 0.525 |

Those 5 silent wrong extractions happen **with or without the rule**. The
proposal adds none. Both cohorts pass Gate 2 and reduce review load — by the
system's own pre-registered gate they are promotable, and the critic argued
against them by charging a baseline cost to the candidate.

This is the first evidence about critic quality, and on its first real test it
wrote a false causal claim into a report meant for a human.

### The fix was not a longer prompt

The model was being asked to do arithmetic that Python does deterministically.
It now receives `*_delta` fields computed in Python, and the output of
`improve.gate_verdict` — the pre-registered verdict — instead of raw numbers to
compare. Its job is what the gate cannot see: whether the rule is wider than the
evidence supporting it.

After the fix, same corpus, same model:

> "Counterfactual replay demonstrates a 1.67 pp review load reduction **without
> introducing silent errors**. However, total_vat is a critical monetary field,
> and suppressing reviews based on 9 historical samples poses potential risk if
> non-zero tax items appear in future documents." — `risk: MEDIUM`,
> `recommend_for_human_review: true`

`recommended_for_human_review` went 0 → 2, and the objection moved from a false
cost to the real one: **extrapolation width**.

That objection is independently correct. `docs/LOOP_GENERALIZATION_2026-08-06.md`
measured this exact due_date absence cohort, mined from these same 12 documents,
applied to 88 never-reviewed ones: it silently dropped **5 genuine due dates**.
The critic identified the failure mode that was measured on this project a day
earlier, from the sample size alone.

### A fifth defect, found in the same output

The first corrected run still described the rule as applying "across all TIER1
documents". The resolved cohort is field-level with no tier — the real scope is
**all** documents. The critic was seeing both the model's draft cohort and
Python's resolved one, and described the narrower. An advisory written for a
human stated the rule's blast radius smaller than it is, which is the dangerous
direction to be wrong in. The draft is no longer shown; only the resolved cohort
is, along with the model's own `finding` and `prediction`, which are the claims
it is meant to argue with.

## Files

| File | Contents |
|---|---|
| `adk_84d088eb023b1166.json` | miner — request identity and response |
| `adk_53685ce98e3f69a0.json` | proposer |
| `adk_32fe165008f9ed6f.json` | critic |
| `adk_loop_report.json` | the final advisory report |

## Reproduce with no credentials

```bash
env -u GEMINI_API_KEY -u GOOGLE_API_KEY \
  INVOICELOOP_REPLAY=1 python3 -m invoiceloop agents improve-loop \
  --workspace runs/adk-real-2026-08-07
```

Measured: runs to completion with no credentials present, and the report diffs
clean against the live one.

## What still cannot be claimed

- **Not that the critic judges well in general.** This is two proposals on one
  corpus. What it establishes is narrower and more specific: on its first real
  test the critic made a causal error that the artifacts contradicted, and the
  error went away when the arithmetic moved into Python. One corrected run is
  not a quality measurement.
- **Not that these two rules are safe to promote.** Nothing was promoted. Gate 2
  passes and the critic recommends a human look — that is the whole of it.
- **Not that the loop generalises.** The counterfactual is a replay over these
  12 documents. The critic's own objection is precisely that 9 samples may not
  extrapolate, and the 88-document measurement says it was right to worry.
