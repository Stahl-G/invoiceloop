# Response to the 65/100 review (2026-08-04)

An external 10-way review (static/reproduction 3 + code/trust-layer 4 + red-team live 3)
scored InvoiceLoop 65/100: "passing but mediocre; fixing the P0s would put it in the
award-contender band (83–87)". This file is the item-by-item response — fixed,
already fixed in prior commits, and user-decision items, kept in three separate
categories.

## It reviewed an old HEAD: already fixed in prior commits

| Review item | Long since fixed in |
|---|---|
| P0-2 README main demo fails in a clean environment | `demo` command + embedded corpus (eb98143), fresh_venv_check includes a demo stage and fully passes |
| P0-4 dirty PDF crashes the whole ingest batch | ocr_ingest subprocess failures uniformly return OcrUnavailable + regression test (22e5c43) |
| P1 extraction-failed documents invisible (ingest summary discards them) | workbench lists failed ingest documents and reasons on an explicit page (22e5c43 #6) |
| P1 24% of tests fully skip on the judge machine | The review's reading is the design: research tests guard with corpus_available(); fresh-venv 175 pass, 41 skip, product paths unaffected (ade37f5) |

## Fixes in this round (776ded5, each with a regression test)

| Review item | Fix |
|---|---|
| P1 corrupted saved response crashes the whole batch | `register_artifacts` marks corrupt, records sha; `_load` returns None → extraction_present blocking; the run still completes |
| P1 silent document loss (run document set = raw) | Document set = input/pdfs ∪ raw (in CLI/workspace/workbench/demo, all three places); missing raw recorded as a blocking by extraction_present |
| P2 doc_blocked only goes to event_log | `independent_ocr` document-level blocking findings go into gate_report.findings |
| P1 panel footer prints a self-reported hash without recomputing | The footer recomputes the ledger sha and compares; on mismatch shows an explicit ⚠; also adds a "N adjudications at render time" staleness line |
| P2 verify does not report depth / CRC bare traceback | verify returns layers (members/snapshot/binding) + notes: v1 bundles say plainly that they only have member-level checks; even when all three layers pass it must still state "authenticity is anchored in out-of-band hashes"; CRC corruption becomes a structured failure |
| P0-3 coordinated tampering has no external anchor | Fix the claim, not the code: added the boundary-pinning test "a fully consistent forgery passes" (test_fully_consistent_forgery_passes_and_that_is_the_boundary); README/verify notes converge the tamper-resistance claim to "single-point tampering is detectable; the anchor is the out-of-band sha256" |
| P2 CLI bare traceback | main() wraps with SystemExit: "error: <one-line summary>" |
| P2 always-true assertion / M2 scaffolding skip | Removed `or True`; a binding-regression import failure must turn red |
| P1 TESTING_RESULTS adjudication count does not match the artifact | Document 3→2 (consistent with the actual ledger) |
| P1 submission-materials gaps (partial) | LICENSE (MIT), .env.example, README research-test explanation, ARCHITECTURE no-wall-clock tradeoff note |

## Regenerating the v2 artifacts (the main fix for P0-3)

runs/demo is a v1 run from before H0 (no review_snapshot, no adjudication projection
in the panel, bundle with member-level verification only). Regenerated runs/demo-v2
with the current code (160 saved calibration responses, zero API): full v2 artifacts
+ re-stamped bundle + verify on all three layers. The old runs/demo stays untouched
(runs are immutable); the two human adjudications from 2026-08-02 stay in its own
ledger — their snapshot differs from v2 (the gates gained independent_ocr findings);
moving them into v2 would create orphans, which would not be truthful.

## User-decision items (the review also flagged these "cannot be verified offline")

1. **Code freshness (disqualification-grade)**: all 29+ commits predate the 8/17
   start. The response is disclosure + increments, not rebase (that would be fraud
   and detectable). At kickoff, disclose the pre-existing project per Devpost Rules;
   keep evidence of a written inquiry to the organizers. Substantive features after
   H1 can legitimately continue during the hackathon (workbench was created on 8/3;
   the blind re-test and the video happen during the hackathon window).
2. **Public repo and history cleanup**: runs/ historical artifacts, .DS_Store,
   author emails, private absolute paths — clean up once before pushing; recommend
   the new repo carry only a clean history, without changing dates.
3. **Video + blind re-test**: materials are ready (21,900 rejection pairs, Harry
   Huge re-recording, the 046e0c49 swap incident, verify tamper comparison); before
   recording, run one uninformed-participant re-test using TESTING_FACILITATOR.md.
4. **Nutrient in one sentence**: the README already takes the sponsor-neutral line
   ("no single signal can identify all errors → a composition layer"); keep Devpost
   copy the same, do not write "DWS is unreliable".
5. **Three sentences for the F dimension**: the niche customer (audited/regulated
   invoice-processing teams), the entry point (an audit deliverable, not an
   extractor), why the big vendors won't (the trust layer is not an extraction
   selling point and sells no licenses).

## Red-team passing items (the review scored them; unchanged)

Blurry scans all blocked, no fabrication of missing fields, prompt injection has no
consumer, edit-then-revert keeps the supersession chain intact, a 1-byte tamper makes
verify fail immediately, oversized PDF / no poppler / no key degrade gracefully —
all consistent with the implementation; no action.

## New capabilities suggested by the review (backlog, not bugs)

- Cross-document duplicate detection (zero detection for same number, different
  content) — a "cross-invoice verification" selling point; do it after the hackathon.
- Line-item-level reconciliation (the field set has no line items) — just steer the
  demo narrative away from "anomaly detection" phrasing.
- net+vat≠gross non-blocking — design philosophy (a finding is not a verdict);
  say it in the video voice-over.
