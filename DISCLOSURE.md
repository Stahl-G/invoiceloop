# Pre-existing work disclosure

The All Things Agentic rules require that entrants "disclose any other pre-existing
code or work incorporated into the Project." This file is that disclosure. It is
written to be checkable: every claim below can be verified against the git history
in this repository, and the commands to do so are at the bottom.

**Submission Period:** 2026-08-03 09:00 PT — 2026-08-31 17:00 PT.

## Short version

This repository was created on **2026-08-01 at 10:24 PT**, roughly 47 hours before
the Submission Period opened. It is not a pre-existing product entering a hackathon;
it is a project that started two days early.

| Commits reachable from `main` | |
|---|---|
| Before 2026-08-03 09:00 PT | **42** |
| During the Submission Period | **93** |

(Counting every branch that ever existed locally, including four commits on an
abandoned side branch that was never merged, the split is 46 / 93. The numbers
above are the ones you can reproduce from this repository, so they are the ones
stated here.)

All three mandatory requirements — Gemini 3.5+, a Google Agent Framework, and a
Google Cloud infrastructure service — were built during the Submission Period, on
2026-08-07. None of them existed before it.

## What pre-dates the Submission Period

A deterministic invoice-review core: take a document, freeze the extraction into an
append-only ledger, run six deterministic gates over it, project the results into a
support matrix, and put the unresolved rows in front of a human.

Modules first written before 2026-08-03 09:00 PT:

```
invoiceloop/freeze.py        invoiceloop/gates.py        invoiceloop/matrix.py
invoiceloop/panel.py         invoiceloop/adjudicate.py   invoiceloop/workbench.py
invoiceloop/pipeline.py      invoiceloop/spans.py        invoiceloop/support.py
invoiceloop/evidence.py      invoiceloop/ocr.py          invoiceloop/ocr_ingest.py
invoiceloop/dws.py           invoiceloop/dws_client.py   invoiceloop/vision_ingest.py
invoiceloop/heldout.py       invoiceloop/ingest.py       invoiceloop/corpus.py
invoiceloop/fields.py        invoiceloop/snapshot.py     invoiceloop/review.py
invoiceloop/demo.py          invoiceloop/doctor.py       invoiceloop/gateinfo.py
invoiceloop/workbench_style.py
```

Also pre-dating the period, and **not in this repository**:

- **`dws-derisk`** — a private calibration archive: 5,680 DocILE PDFs (Rossum's
  public invoice set, MIT-licensed), word-level OCR, and **321 saved Nutrient DWS
  responses**. Six rounds of experiments were run against it before this project
  existed. Several functions here are ports of implementations from that archive:
  the normalisation rules, the C1–C7 consistency checks, the independent OCR
  citation check, the paired-mode disagreement check, and the bbox/crop geometry.
  `tests/test_port_fidelity.py` exists specifically to check those ports against
  the originals point by point.

Nothing in this project re-measures that archive. It is used as frozen evidence:
scoring reads saved responses from disk and never calls the API, which is what makes
every number here recomputable at zero cost.

## What was built during the Submission Period

Everything adaptive, everything agentic, and the accountability boundary between
them and the deterministic core.

Modules that did not exist before 2026-08-03 09:00 PT:

```
invoiceloop/agents/__init__.py       invoiceloop/agents/runtime.py
invoiceloop/agents/improve_loop.py   invoiceloop/agents/adk_replay.py
invoiceloop/harness.py               invoiceloop/improve.py
invoiceloop/routing.py               invoiceloop/suggest.py
invoiceloop/adaptive.py              invoiceloop/carry.py
invoiceloop/feedback.py              invoiceloop/plainwords.py
invoiceloop/safety_metrics.py        invoiceloop/eval_norm.py
invoiceloop/crossdoc.py              invoiceloop/deliver.py
invoiceloop/doctype.py               invoiceloop/subject_direction.py
invoiceloop/env.py                   invoiceloop/seal.py
```

Plus 24 new test files, including every test covering the agent layer, the routing
policy, the improvement loop, the document-type evidence gate and the Cloud Run
deployment.

The three mandatory requirements, all dated 2026-08-07:

| Requirement | What was built | Evidence in repo |
|---|---|---|
| Gemini 3.5+ | Live `gemini-3.6-flash` calls through the improvement loop | `docs/evidence/adk_live_2026-08-07/` |
| Google Agent Framework | `google-adk` 2.6.2 — `Runner.run_async` driving a four-stage `SequentialAgent`, with record/replay bound to request identity at the model boundary | `invoiceloop/agents/`, `docs/ADK_INTEGRATION.md` |
| Google Cloud service | Cloud Run deployment, built by Cloud Build into Artifact Registry, public instance hardened to read-only | `docs/evidence/cloud_run_2026-08-07/` |

## Where the boundary falls, in one sentence

The pre-existing part answers "can this extracted value be shown to be supported by
the page?" The part built during the Submission Period answers "can a model be given
a job in that loop without being given any authority in it?" — and that second
question is the submission.

## Third-party components

- **Nutrient DWS** — document extraction API. Hackathon/evaluation credits granted
  by the vendor. Carries the core extraction; not a decorative call.
- **DocILE** — Rossum's public invoice dataset, MIT-licensed, used as the
  calibration corpus.
- **google-adk**, **google-genai**, **pydantic**, **poppler-utils** — standard
  libraries and tools.
- The demo corpus vendored in `invoiceloop/samples/` is drawn from DocILE.

## Verify this yourself

```bash
# Commits before the Submission Period opened (2026-08-03 09:00 PT = 16:00 UTC)
git log main --until="2026-08-03T16:00:00Z" --date=iso --pretty='%ad %h %s'

# Commits during it
git log main --since="2026-08-03T16:00:00Z" --oneline | wc -l

# When any given module first appeared
git log main --diff-filter=A --date=iso --pretty='%ad %h' -- invoiceloop/agents/
```

If anything in this file turns out to be wrong, the git history is the authority,
not this file.
