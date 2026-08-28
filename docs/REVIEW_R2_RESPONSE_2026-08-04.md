# Response to the round-two dual review (2026-08-04)

Two reviews arrived the same day, both covering the HEAD after the 65/100 fix batch:

- **Re-review (65 → 81/100)**: spot-checked 10/10 fix claims as real; new findings
  concentrated in "defects introduced by the fixes".
- **Twelve-way new review (82/100)**: all 6 red-team classes passed, but it caught
  one P0 (--crops crashing the batch) and a batch of P1s.

The two reviews' code-side findings, merged and deduplicated, all landed this round,
each with a regression test (259 all green; plus a judge-machine simulation: after
`export INVOICELOOP_CORPUS`, the 240 product tests are all green too).

## Fixes in this round

| Review item | Source | Fix |
|---|---|---|
| `run --crops` crashes the whole batch on a bad PDF (workbench upload follows the same path) | 82 review P0-3, reproduced by two red teams | `render_pages`/`render_crop` return empty for bad files (honoring the existing docstring promise), pipeline records a `pages_unavailable` event instead of going silent; added RENDER_TIMEOUT |
| C3 date gate fails both ways on MM/DD/YYYY | 82 review P1-2 | Reverse-tuple comparison replaced with explicit format determination (ISO/day-first/month-first); ambiguous pairs take their tone from an unambiguous date in the same document, falling back to day-first when undecidable (preregistered behavior does not drift); 7 new tests covering false positives + false negatives in both directions |
| verify: three traceback escapes (snapshot/ledger CRC, zlib.error) | 81 review P1-3 | Deep reads all become structured failures; malformed MANIFEST rows covered too |
| CLI error wrapping half-landed (5 classes including RunExistsError as bare tracebacks) | both reviews P1-2/P1-4 | main() now catches Exception (SystemExit/KeyboardInterrupt are not its subclasses and pass through naturally) |
| workbench vision-suggestion layer offered an "adopt" button for frozen rejected values | 82 review P1-5 (D-dimension deduction) | Suggested values are compared against the row's frozen rejection set with the same normalization rules: on a hit → still displayed + labeled "rejected when frozen at the same value" + **no button**; the contract test pinning our own total_net=10.00 was exactly this case, and the contract test has been re-pinned to the new semantics |
| `.PDF` uppercase extension silently drops documents | 82 review P1-6 | discover compares suffix.lower() (our own breach of charter rule four) |
| Valid JSON that is not an object ([1,2,3]) crashes the batch; malformed TSV rows raise IndexError | 82 review P1-7 | register_artifacts and ingest resume gain isinstance guards; load_vision_answers skips malformed rows |
| ingest summary lies: non-200 counted into extracted (wrong key, "all succeeded") | 82 review P1-8 | extracted counts only 200; non-200 stays saved (refusal evidence belongs in the denominator) but goes into extract_failed |
| `INVOICELOOP_CORPUS` shadows fixtures (29 tests turn red after a judge exports it) | 81 review P1-1 | conftest adds `pin_corpus` setting both the primary variable and the alias; 8 test files switched over uniformly; **the same product-side pattern fixed in two places as well**: make_server and build_audit_bundle also only set the alias before |
| layers.binding reports true for zero-adjudication bundles (vacuous truth) | 81 review P2 | Zero adjudications records None + a note, consistent with the snapshot layer's honest marking |
| pipeline mkdir guard is thread-level TOCTOU | 81 review P2 | O_EXCL claims run_manifest.json: the loser gets RunExistsError, no more FileExistsError streaks or interleaved half-written files (pinned by a concurrency test) |
| decided_at has no format validation ("next week maybe" could enter the ledger) | 82 review P2 | ISO 8601 parsing validation; garbage times are refused entry |
| Adjudication append has no cross-process lock (only threading.Lock) | 82 review P2 | adjudication_ledger.lock flock for a cross-process critical section (Windows degradation documented) |
| subprocess has no timeout (poppler/tesseract) | 82 review P2 | Unified timeout constant for ocr_ingest and evidence rendering |
| doctor does not check pdfinfo | 82 review P2 | Added (the page-size source for crop coordinate conversion) |
| README install section lacks venv guidance (PEP 668 double collision) | 82 review P1-1 | Added two venv lines |

## Honesty-document batch (charter: our own documents meet the bar first)

- **README's "change one byte and it fails" was an overstatement** — a coordinated
  forgery (artifacts + MANIFEST + snapshot + ledger all rewritten) demonstrably
  passes; that is the trust boundary the boundary-pinning tests had long declared.
  The README now says "single-point tampering is caught by the corresponding
  layer; authenticity is anchored in the out-of-band sha256". **The previous
  round's response document claimed this sentence was already changed; it was not —
  that response was inaccurate. This round actually changed it, and the record is
  left here.**
- **ARCHITECTURE 66%/70%, two numbers for the same case** — unified to 70% per the
  boundary-pinning regression (118/168, pinned line by line by
  test_binding_regression.py; DEMO.md's 111 (66%) is the measure of a
  segment-level rule variant, not the document-level rule this system shipped).
- **ARCHITECTURE §5.3 "reject execution if the input signature does not match"** —
  the gates themselves do not re-verify the signature; the actual protection is in
  the snapshot-consistency check at adjudication append and in bundle verify. The
  wording is now aligned with the implementation.
- `.qoder/` (IDE artifacts) and `.DS_Store` moved out of git tracking and into
  gitignore.

## Review items falsified on verification (not fixed; evidence kept)

- **"H6 calibration denominator silently drifted 1604→1305"** (82 review P2):
  repository-wide search: 1305 exists in no file; 1604 appears only in
  docs/HELDOUT.md (247/1604=15.4%, arithmetic self-consistent). No drift to fix.
  Reviews can be wrong too — per the charter, claims that cannot be verified do
  not enter the fix list.

## Evaluated and deferred (reasons stated)

- **Ship an OCR subset with the fixtures so the boundary-pinning regression runs on
  a clean clone** (82 review P1-11): direction endorsed, but the 454-line
  boundary-pinning regression needs DocILE's word-level OCR originals; both bulk
  and licensing need checking; after the hackathon, spin it up as its own "minimal
  publishable subset" project rather than stuffing big files in before the
  submission.
- **Whether the cross-process append lock file enters the snapshot**: no — a lock
  file is not an artifact (same logic as event_log); snapshot components stay
  stable.
- Mixed green-badge signal on C1-failing rows (82 review P2): finding≠verdict is
  the design philosophy, and the panel already has a finding layer; explain it in
  the video voice-over; rendering unchanged.

## Still submission-side work (where the code side cannot help)

Video, English pitch + naming Nutrient, the framing layer (for whom/regulatory
wedge/competitor positioning), compliance disclosure (pre-period tag + DISCLOSURE
file + written pre-kickoff inquiry), history cleanup before going public (author
emails and private paths). Same list as last round; priorities unchanged.
