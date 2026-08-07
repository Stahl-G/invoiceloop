# Live Gemini 3.6-flash call (2026-08-07)

Until this run, every test of the agent layer used a scripted model or a stored
recording, so "we integrated Gemini" was not something the artifacts could
support. This directory is the first real call, on the record.

## What ran

```bash
python3 -m invoiceloop agents improve-loop --workspace runs/adk-live
```

`Runner.run_async()` drives `SequentialAgent(improve_pipeline)`. All four stages
execute; the three `LlmAgent` stages each issue one real request.

| | |
|---|---|
| Model | `gemini-3.6-flash` |
| Endpoint | Gemini Developer API via `google-genai` 2.17.0 |
| Framework | `google-adk` 2.6.2 |
| Real requests | 3 (miner / proposer / critic) |
| Wall clock | 15.3s |
| Corpus | The bundled `invoiceloop demo` set — 2 PDFs, 3 adjudications |

## Files

| File | Contents |
|---|---|
| `adk_84e0b5061ee029cc.json` | miner — request identity and response |
| `adk_3d87b1a694adf736.json` | proposer — request identity and response |
| `adk_c43819abc8f3b53a.json` | critic — request identity and response |
| `mine_report.json` | The input to all three |
| `adk_loop_report.json` | The output (advisory only) |

Each recording carries an `identity` block with every component of the request:
`model`, `system_instruction`, `contents`, `response_schema`, `response_mime_type`.
The filename is the first 16 hex of the SHA-256 over exactly those components.

## What the result says

All three models returned empty lists: `{"candidates":[]}` → `{"proposals":[]}` →
`{"verdicts":[]}`.

**That is the right answer, not a failure.** The demo corpus is two documents and
three adjudications — far too little to form any "reviewed repeatedly, never
corrected" pattern, and the deterministic `improve mine` finds no cohorts either.
The models did not invent a rule in order to look useful. Seeing a non-empty loop
requires a workspace with real review history.

## Reproduce with no credentials

Put the three recordings in a workspace's `agent_calls/`, then:

```bash
env -u GEMINI_API_KEY -u GOOGLE_API_KEY \
  INVOICELOOP_REPLAY=1 python3 -m invoiceloop agents improve-loop --workspace <ws>
```

Measured: this runs to completion **with no credentials present at all**, and the
report `diff`s clean against the live one.

## Negative controls, run against these same recordings

| Change | Result |
|---|---|
| `--model gemini-3.5-flash` | `ReplayRecordingMissing: adk_506fd273d67f2ede` — refused |
| `mine_report.events` edited to 999 (so the prompt changes) | `ReplayRecordingMissing: adk_d947a753ce1c78e4` — refused |

The previous hand-written call ids (`critic_{field}`) carried neither the model nor
the prompt in their identity, and would have returned the stale recording in both
cases as if it were this call's answer.

## What still cannot be claimed

- Not that the critic judges *well*. There were no proposals for it to judge here.
  The tests pin the authority boundary and the plumbing — that it receives the
  deterministic counterfactual, and that its output is advisory — not the quality
  of its judgement.
- Not that the loop works on real data. This is a connectivity proof on a demo corpus.
