# Human acceptance protocol (operationalizing GOAL.md's "what done looks like")

GOAL.md says done is falsifiable: an **uninvolved reviewer** can answer four questions. This protocol
turns those four questions into five timed tasks. Subject: someone who took no part in the build
(a colleague, another model, or yourself three months from now). The only materials are the `runs/demo/`
directory (generate first with `python3 -m invoiceloop run --out runs/demo --crops`).

> **Facilitation uses `docs/TESTING_FACILITATOR.md`** (contains the specific anchor documents, the
> answer key, and the recording sheet). This document is the principles; that one is a ready-to-use
> execution kit.

## Discipline

- The subject **may not ask the builder**. Answers must come from the artifacts themselves. One question
  asked = that task fails.
- Record for each task: the answer, the artifact used to find it, elapsed time.
- Pass line: ≥4 of the 5 tasks answered correctly, and no one fundamentally misreads "what this thing
  is promising" (task 5).

## The five tasks

**T1 — Why is this row "unsupported"?** (GOAL question 1)
Point at any row at the head of the matrix. The subject should be able to say: the value was rejected by
the freeze transaction (or DWS returned no value), where the event is, and whether it is missing OCR or a
binding failure.
*Pass: the stated cause is consistent with event_log / limitations.*

**T2 — Recompute this number.** (GOAL question 2)
Give the subject the "drafts rejected by the freeze transaction" number from the panel overview strip.
The subject should be able to count the same number out of `event_log.jsonl` and say how the sha256 of
`field_ledger.json` arises.
*Pass: the numbers match, and the subject says "content addressing — the hash of the claims' canonicalized
serialization".*

**T3 — Where does the system explicitly say it doesn't know?** (GOAL question 3)
The subject should find: unsupported rows, dws_returned_no_value, visual_not_measured (not yet measured),
blocking findings and repair routes.
*Pass: at least two classes pointed out, and the understanding that "doesn't know" is explicitly labeled,
not missing data.*

**T4 — Can this invoice's Gross go straight into the error rate?** (caliber dispute)
Pick a `label_convention_disputed` document (search the queue for "caliber dispute").
*Pass: state the two readings (paper Gross = list price, Net = actual pay after commission deduction;
EN 16931 the other way around), and explain why it goes to human adjudication, not into the error rate.*

**T5 — What is this thing promising?** (GOAL question 4, the item most easily sanded away)
Ask directly: does this demo prove DWS extraction is trustworthy?
*Pass: answer "no — it delivers verifiable support relations and does not promise accurate extraction",
and point to where the panel states this sentence. Answering "yes" = the whole acceptance fails,
and the panel's phrasing must change.*

## Scoring sheet

| Task | Answer correct | Artifact found | Elapsed | Notes |
|---|---|---|---|---|
| T1 | | | | |
| T2 | | | | |
| T3 | | | | |
| T4 | | | | |
| T5 | | | | |

Failure handling: it is not the subject's fault, it is the panel's/artifacts' fault — change the
presentation, then re-test with a new subject.
