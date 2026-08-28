# Response to the rubric review (78/100, evidence-constrained judge) (2026-08-04)

This review scored commit e8aa56d against the user's prefrozen rubric v0.1, verdict
78/100: "the architectural thinking has award-winning differentiation, but product
value and quantified effect have not caught up with the architectural complexity".
All red-team live tests held (doctor/demo/adjudication/bundle/tampering); no
contested items.

## Fixes in this round

| Review item | Fix | Commit |
|---|---|---|
| P1 no three-way comparison of raw DWS / simple threshold / InvoiceLoop (the biggest gap in rubric item E) | `scripts/baseline_comparison.py` + `docs/BASELINE_COMPARISON.md`: on TIER1, raw DWS silent errors 29.97% → dual-mode agreement 14.95% → InvoiceLoop 8.88%; document-level silent failures 54.5% → 31.5% → 21.1%; deviation-routing recall 82.6%. The three points form a monotone risk–coverage curve; triage is significantly better than the simple baseline at the risky end. Stated on the same screen: exploratory and not preregistered, the product does not auto-release, the residual is not zero; the measurement math is pinned by 4 tests | this round |
| P3 demo gets 1 failed on the judge machine (the OCR-blocked exhibit was hard-coded) | Root cause: whether 046e0c49 gets a text layer extracted by pdftotext depends on the poppler build. Now pinning the invariant "blocked must be explicit" (event + blocking finding as a pair), not "this particular document must be blocked"; the demo note is generated from what actually happened | b98a0ae |
| P4 incomplete version pinning | run_manifest records `code_revision` (git commit; honestly null in non-git environments); vision answers6.*.tsv captured into the run/bundle (parallel session, eb383cc) | b98a0ae + eb383cc |

## Design awaiting the user's nod (P2, +4~6 points)

TIER1 entering the runtime policy + whole-document release/blocking + final
JSON/CSV export after adjudication. Changing the triage definition and introducing
the new concept of "whole-document release" — same weight as C8; design first, then
implement.

**→ Implemented (design approved by the user on 2026-08-04, dc501b0)**: `deliver.py`
is a pure projection, deliverable.json — the final value per slot
(correct→corrected value / accept→claimed value / reject→null / abstain→undecided)
+ whole-document released/pending/blocked; **TIER1 sits at the release layer, not
the triage layer**: corroborated key fields must also be explicitly adjudicated
before release, so the triage definition and the calibration numbers have zero
drift. The workbench delivery page has per-document status and downloads; the
bundle carries the deliverable (optional member; old runs are not blocked); 9 tests
pin it down, including "render refreshes in sync after adjudication" and
"abstention may not release".

## User-decision items (unchanged)

P0 eligibility confirmation in writing (the precondition for deciding whether to
enter), video (the rubric provided a storyboard; live_dws_demo.sh can be recorded
directly), pitch and the heavy-lifting sentence (already drafted by the review;
just adopt it in the Devpost copy), DocILE license check.

## One deduction in the review we disagree with (on record; unchanged)

"The six rounds of experiments proved it cannot be done; that road is closed" was
read by the review as "improving extraction correctness is impossible overall".
The original context is "no single signal can identify all errors" — the
non-claims lists in the README and ARCHITECTURE §9 both take that line. The
document wording was already converged in earlier rounds and is not being changed
again; just be careful in the video voice-over.
