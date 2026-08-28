# H0 integrity foundation (2026-08-03)

An external code review (against `ff2e26c`) found four problems that would
dissolve the core promises; this round fixed them under the reviewer's
narrowed 14 invariants — **no new gates, no new models, no copying of the
BriefLoop control plane**.

The reviewer's own characterisation: the freeze was not truly enforced
(a re-run silently overwrote → adjudications mis-bound); the audit bundle
could not independently verify upstream evidence; the human loop did not
close (adjudications did not flow back into projections); there was no
installation entry point (a clean clone immediately failed 3 tests).

## The five (plus) commits

| Commit | What it did |
|---|---|
| 909fb6f | Installation layer: pyproject (runtime needs only requests), the `doctor` self-check, clean-clone-safe imports for parity tests, sponsor-neutral README wording |
| 0ef48fe | Immutable runs: a non-empty directory is always refused (no `--force`); the workspace gains per-generation `runs/run-NNNN` plus a `current.json` pointer; same-input-fingerprint replay; `input_manifest.json` + `review_snapshot.json` written to disk |
| 1d0798c | Adjudication v2: binds the full review snapshot (not just the ledger); `claim_id↔doc_id↔field` triple must match exactly; value-less slots get a stable `target_id`; decision semantics frozen (correct must carry a value, the others must not); a second decision must explicitly supersede; the panel becomes a rebuildable projection whose render failure never rolls back an adjudication |
| e943412 | Self-contained bundle (option A): full upstream evidence (PDF/OCR/raw×2) + the extraction schema + scope metadata; the `verify` command's three-layer offline check (member hashes → snapshot-component recompute → adjudication binding) |
| 1133483 | Self-audit hole-fixing: vision answers enter the input fingerprint (otherwise replay would return the old run); the panel overlay escapes labels |
| a044c09 | Inline adversarial-review hardening (6 items — see "self-audit findings" below) |
| Follow-up | research-test guards unified onto `corpus_available()` (guard and data source share one origin) |

## Self-audit findings (the sub-agent gateway returned 503, so an inline
adversarial review stood in; every item carries a test)

Both attempts at an independent sub-agent review were refused by the reasoning
gateway (503 auth_unavailable); an inline dimension-by-dimension attack on our
own implementation was done instead, which found and fixed:

1. **Appending an adjudication did not check that the snapshot still matches
   the on-disk artifacts** — artifacts modified after the run would let an
   adjudication silently bind to a snapshot in name only. A mismatch now
   blocks (`test_append_blocks_when_run_artifacts_were_altered`).
2. **Adjudications bound to a different snapshot were silently invisible** —
   a ledger copied from another run left old decisions out of the chain and
   out of view. They are now marked orphan: not projected (no
   mis-attribution), but explicitly warned about on the panel (history is
   not hidden).
3. **`--docs` truncation happened after the fingerprint** — "the run of the
   first document" would have been replayed as "the run of all documents".
   Truncating to the first 1 document now precedes fingerprinting
   (`test_docs_slice_precedes_fingerprint`).
4. **Replay did not verify completeness** — a half-crashed run (input_manifest
   present, no event_log) would have been replayed as a result. Half-runs are
   now skipped by replay and left in place as the scene of the incident.
5. **The bundle checked upstream evidence only for existence** — a PDF swapped
   after the run would silently enter the package. Acceptance now goes by the
   sha recorded in input_manifest: swapped/missing = blocking; absent already
   at run time = recorded in notes.
6. **Research-test guards and data reads used different sources** — the guard
   checked a hard-coded default path while data reads followed the
   environment variable; the fresh-venv verification script caught 13
   failures on the spot. Unified onto `corpus_available()`.

Known boundary (recorded, not fixed): bundle-zip timestamps make two packagings
byte-different (the in-package MANIFEST and verify are unaffected); the
theoretical window of concurrent CLIs racing for the same run generation is
minimised by `mkdir(exist_ok=False)` — the loser errors out on the spot.

## Key design decisions (why this way)

- **No `--force`, and no requirement to delete history.** Destroying an
  adjudication ledger is not an explicit Human decision. Re-running opens a
  new generation; old generations stay untouched — blocking is not an
  obstacle, it is the product semantics.
- **Adjudications bind `review_snapshot_id`, not just a ledger hash.** The
  snapshot = input manifest + artifact registry + evidence-span registry +
  frozen ledger + gate report, five components. Binding only the ledger means
  the same ledger paired with swapped evidence goes undetected.
- **Current state is projected from the supersession chain, not "the last
  row wins".** v1 legacy entries (the two real-human adjudications from the
  2026-08-02 acceptance round) get synthetic `legacy-<sha8>` ids and are
  chained implicitly by seq — that was v1's semantics at the time; labelled
  honestly, bytes not rewritten. A broken chain (only possible with a
  hand-edited ledger) is marked as a conflict and blocks new adjudications;
  the system does not guess for you.
- **The bundle is either fully self-contained or not shipped.** "Whole-batch
  derivatives + upstream evidence only for adjudicated documents" is fake
  self-containment: the recipient sees conclusions but cannot verify sources.
  Any missing upstream evidence blocks.
- **The panel is a projection; adjudications are the authority.** adjudicate
  fsyncs to disk first, then re-renders; a render failure returns
  `decision_recorded=true, panel_refreshed=false`, and `render --run` can
  rebuild at any time.

## Test mapping (the eight categories the reviewer required)

| Requirement | Test |
|---|---|
| A non-empty run is never overwritten; old bytes fully unchanged | `test_run_immutability.py::test_nonempty_out_dir_is_refused_and_untouched` |
| New input produces a new run | `test_fingerprint_changes_with_input` + `test_allocate_replay_and_new_run` |
| Every snapshot/claim/doc/field mismatch on a decision is refused | `test_adjudicate.py::TestValidation`, seven cases |
| Supersession projection is deterministic | `test_review.py::test_tip_follows_supersession_chain_not_row_order` (shuffled input, same projection) |
| A failed panel refresh loses no decision | `test_render_failure_does_not_rollback_decision` |
| A bundle missing any upstream evidence blocks | `test_missing_upstream_evidence_blocks` |
| Any altered byte fails verify | `TestVerify`, four cases (including "artifact changed AND MANIFEST updated to match" caught by snapshot recompute) |
| A clean clone without dws-derisk still runs the product path | `scripts/fresh_venv_check.sh` (clone → venv → install → doctor → E2E → pytest) |

`fresh_venv_check.sh` was run green on this day: clean clone → install →
doctor → ingest → run → adjudicate → panel projection → bundle → verify →
replay → pytest (129 passed, 40 research tests skipped) = all green.

## Boundaries (what this round does not do)

- No web service — that is H1 (the judge-facing review workbench), per the
  reviewer's section six.
- No blind usability retest — still owed; do it before recording the video.
- No semantic changes to freeze/gates/matrix/fields — regressions are guarded
  by the parity and byte-compare suites.
