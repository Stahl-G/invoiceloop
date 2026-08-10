# Documentation index

Reader-facing documentation is in English. The dated files below are a working
laboratory notebook, written in Chinese as the work happened. They record which
hypotheses were falsified and which assumptions turned out wrong; translating them
after the fact risks losing the thing they were written to preserve. This index
says in English what each one contains, so you can decide whether to open it.

## In English

| File | What it is |
|---|---|
| [`ADK_INTEGRATION.md`](ADK_INTEGRATION.md) | The agent layer: what the ADK Runner actually executes, where model authority stops, how zero-API replay binds to request identity, and a section listing what has *not* been shown |
| [`CLOUD_RUN.md`](CLOUD_RUN.md) | Deployment; why the public instance refuses every write; why the GCS path was deleted rather than fixed |
| [`architecture.html`](architecture.html) | Architecture diagram — dark/light, exports to PNG/SVG |
| [`evidence/adk_live_2026-08-07/`](evidence/adk_live_2026-08-07/) | First live `gemini-3.6-flash` call: recordings, inputs, outputs, and the two negative controls proving a stale recording is rejected |
| [`evidence/adk_real_2026-08-07/`](evidence/adk_real_2026-08-07/) | The same loop on 195 real review events instead of a 3-adjudication demo. Five defects the demo corpus structurally could not reveal, including a critic that charged a baseline silent-error count to a candidate that did not cause it |
| [`evidence/cloud_run_2026-08-07/`](evidence/cloud_run_2026-08-07/) | Deployed revision, image digest, IAM policy, remote smoke output |
| [`HACKATHON_RUBRIC_v0.1.md`](HACKATHON_RUBRIC_v0.1.md) | Self-scoring rubric used to review this project against itself |

## Protocols and sealed evaluations

Pre-registered before execution, then reported as measured — including where the
result missed the pre-registered line.

| File | What it is |
|---|---|
| [`SEALED3_RESULTS.html`](SEALED3_RESULTS.html) | A visual, plain-language Chinese explanation of the SEALED-3 result, with an optional local read-aloud summary: 97 fewer human-review slots, one new silent absence, and why the ADK candidate was deterministically rejected |
| `HELDOUT.md` | Held-out protocol, frozen before any API call |
| `SEALED3_PROTOCOL.md` / `SEALED3_MULTIHARNESS_ADDENDUM_2026-08-08.md` / `SEALED3_RESULTS.md` | 100 drand-seeded unseen documents, opened once under six frozen harnesses plus an exact repeat. HAR-0004 cut the human queue 62.4% -> 52.7% and reproduced 3.75x triage lift, but one new silent absence failed the pre-registered qualification gate. The ADK due-date candidate saved another 3.3pp at the cost of five more silent absences |
| `evidence/sealed3_multiharness_2026-08-08/` | Git-frozen routing policies and a compact machine-readable result summary; the full run/bundle stays in the research data directory and is content-addressed from the result |
| `ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` | Engine v3 (one-edit fuzzy) clears seller_vat_id to 234 saves / 0 silent on dev; the remaining total_net×1 and due_date×8 silents are caliber disputes, not lexicon gaps; derivation v2 fires on 8/300 |
| `SEALED1_PROTOCOL.md` / `SEALED1_RESULTS.md` | Historical 100-document sealed result: triage lift 4.03×; decision load 82.9% → 64.2%. Measured 2026-08-03 before later exposure; still valid for that revision, but spent for new measurements |
| `SEALED2_PROTOCOL.md` / `SEALED2_RESULTS.md` | Second sealed batch, lift 3.19×. **Held-out status revoked 2026-08-07** — the protocol's own clause 3 fired. Enforced in `improve.SEALED_SET_REVOCATIONS`, not merely written down |
| `FIELD_COVERAGE.md` | Which fields are scored, frozen before SEALED-2 |
| `BASELINE_COMPARISON_SEALED1.md` | Against a confidence-threshold baseline at a fixed operating point: TIER1 silent error 9.62% vs 21.91% |
| `BASELINE_COMPARISON.md` / `R0_BASELINE_2026-08-05.md` | Earlier baseline work |

## Measurement records

| File | What it is |
|---|---|
| `L1_ADAPTIVE_MEASURED_2026-08-06.md` | Skipping the second extraction mode on "clean" documents saved 2.3% of calls and lost every ground-truthed disagreement slot it skipped (4/4 wrong). The feature exists but is not recommended, and this is why |
| `LOOP_GENERALIZATION_2026-08-06.md` + `REVIEW_…` | Whether a policy mined from one batch transfers to another; and a review that corrected parts of it |
| `HITL_RUN0002_2026-08-06.md` | A real human review session, 12 sampled documents |
| `LIVE_TEST_2026-08-05.md` | Live extraction run notes |
| `VERIFICATION_2026-08-02.md` | Verification round: held-out H1–H6, plus human acceptance testing |
| `TESTING*.md` | Human acceptance protocol, facilitator pack, and results |

## Document-type work (2026-08-07)

| File | What it is |
|---|---|
| `DOCTYPE_PLAN_2026-08-07.md` | The plan, opening with two of the author's own claims that the data falsified |
| `DOCTYPE_EVIDENCE_2026-08-07.md` | Does the model's document-type claim have literal page support? ~91–94%. Also the de-contamination: seven corpus-derived tokens removed after ablation showed all seven decided nothing — and the correction of the removal list, which had named one token that should stay and missed three that should go |
| `DOCTYPE_STAGE_B_2026-08-07.md` | Where a document-level verdict can live without breaking replay |
| `DOCTYPE_STAGE_D_2026-08-07.md` | **A negative result.** A pre-registered label-geometry rule for seller/buyer direction scored 51.6% against an 80% kill line, and was killed. Also records a binding defect found afterwards, and the recomputation that followed |

## Design and review history

| File | What it is |
|---|---|
| `BROADCAST_HARNESS_DESIGN_2026-08-10.md` | Design draft for the broadcast-invoice harness: scope rule, schema/derivation/absence-lexicon layers, and the SEALED-4 amendment path. A design, not a result |
| `IMPROVE_LOOP_DESIGN.md`, `IMPROVE_LAYER_V0.2_DESIGN.md`, `IMPROVE_LAYER_V01_IMPLEMENTATION_2026-08-05.md` | Design and implementation of the improvement loop |
| `FEEDBACK_PLANE_2026-08-06.md` | Adding the feedback signals the mining arm needed to fire at all |
| `H0_INTEGRITY_2026-08-03.md`, `H1_WORKBENCH_2026-08-03.md` | The integrity foundation and the review workbench |
| `REVIEW_*_RESPONSE_*.md` | Responses to external reviews scored 65, 78, 81, 83/69. Each lists what was accepted, what was rejected, and why |
| `RUBRIC_V01_SCORE_2026-08-0[56].md` | Self-scoring against the rubric, twice |
| `STATUS_2026-08-05.md` | Full status ledger prepared for external adjudication |
| `DATASETS.md`, `DWS_SIGN_AND_VIEWER_PLAN.md` | Dataset evaluation; signing and viewer plan |
