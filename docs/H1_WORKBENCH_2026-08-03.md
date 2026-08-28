# H1 review workbench (2026-08-03)

After the H0 integrity foundation, the reviewer's designated next unit: the
judge-facing review workbench — a local loopback web application that turns
"upload → extract → review queue → adjudicate → delivery report →
bundle/verify" into an end-to-end experience walkable in 2–4 minutes. The
user's hard requirement: **the human-review step enters problems directly in
the web page** (buttons + input fields, not view-only).

## Shape decisions (pinned)

- **stdlib http.server, zero new dependencies.** No Flask/FastAPI — the
  pyproject runtime still has only requests; a judge's clean clone plus
  `pip install .` installs nothing extra.
- **127.0.0.1 loopback only.** No host parameter; to show someone else, ship
  the audit bundle — this service does not go on the network.
- **Server-rendered HTML + progressively enhanced JS.** With JS off,
  everything except browser upload/validation works; file upload falls back
  to the input contract (put the PDF into `workspace/input/pdfs/`).
- **A person writes adjudications, and only adjudications.** `/decide` passes
  through the same checks as `adjudicate.append_adjudication` (snapshot
  consistency, triple agreement, decision semantics, supersession); the
  workbench opens no back door.
- **decided_at is stamped by the server at click time.** Clicking *is* the
  act of a person supplying the time; an adjudication is human input, not a
  recomputed artifact, and run-artifact determinism is unaffected.
- **Visual discipline borrowed from briefloop-prototypes** (Visual System
  v1): DWS/model values = purple (advisory, never green), human confirmation
  = blue, deterministic pass = green, blocked = red, unavailable = grey.

## How it was built (sub-agent split)

- Test agent: 15 contract tests against the pinned route/form contracts
  (`tests/test_workbench.py`), tests first; collection did not crash while
  the server did not exist yet.
- Visual agent: `invoiceloop/workbench_style.py` against 65 pinned selector
  contracts, token layer borrowed from the prototype, semantic color
  discipline held (human confirmation all blue; green only for deterministic
  pass).
- Main session inline: the server itself
  (`invoiceloop/workbench.py`, routes + actions + pages), zero file overlap.
- Adversarial-review workflow: three dimensions (security & charter /
  adjudication wiring correctness / contract drift), independent discovery +
  point-by-point rebuttal-style verification (results below).

## Caught and fixed during integration self-check

1. `/verify`'s form used `enctype="application/octet-stream"` — the browser
   never attaches file content that way (Python 3.14 has no cgi; no
   multipart hack). Switched to fetching raw bytes, the same path as upload;
   the no-JS fallback is the CLI `verify`.
2. `/decide` redirects dropped the form's language (a Chinese page submitted
   and landed on an English page).
3. `snapshot.build_input_manifest`: when not a single vision file exists
   (workspaces are always so), `--vision/--no-vision` produced two different
   fingerprints and replay broke between CLI and workbench — normalised to
   None (vision files enter the fingerprint only when present).
4. rationale/adjudicator empty strings could bypass HTML required via a raw
   POST and enter the ledger — server-side validation added.
5. The adjudicator cookie was quoted on write but not unquoted on read
   (Chinese names echoed back as percent signs).

## Smoke test (real PDFs + real OCR + crops)

All pages 200, root 303 → /queue; POST /decide (correct, Chinese rationale)
→ 303 → the queue row shows "current adjudication HD-0001 … submitting will
supersede it", delivery report 1/10 + corrections list; evidence crops serve
correctly through /files. The 15 contract tests + the full 184 all green.

## Known boundaries (recorded, not fixed)

- Re-uploading a same-named PDF does not re-OCR/re-extract (resumable-run
  discipline); to re-extract, delete the matching ocr/ and raw/ files first
  (the upload page says so).
- A crop-render failure (corrupt PDF + render_crops) makes /ingest 500 — the
  block is not hidden, the page shows the traceback; the CLI behaves the
  same.
- The last line of defence for concurrent adjudication is the append's
  supersession check: two tabs adjudicating the same slot, the second submit
  gets 400 (stale supersedes) — no silent overwrite.
- i18n is chrome-level bilingual (buttons/labels); evidence content (OCR,
  rationales) stays in its original language.

## Adversarial review results

24 agents (3-dimension discovery + rebuttal-style verification, 909k tokens):
12 findings submitted; after verification **17 items confirmed** (including
the same problem reported twice across dimensions), all fixed, each with a
test:

| # | Severity | Finding → fix |
|---|---|---|
| 1 | critical | Write endpoints had no Host/Origin checks: a cross-site form could burn DWS credits and forge adjudications into the append-only ledger; DNS rebinding could read everything → Host allowlist + POST Origin checks (403) |
| 2 | critical | The long-lived process's OCR lru_cache never cleared: after new OCR, binding used stale cache while the manifest recorded the new sha → both caches explicitly cleared after ingest |
| 3 | major | /decide had no lock: concurrent writes produced duplicate decision_ids (measured 261/300) and verify could not detect them → append holds a lock in the critical section + verify checks decision_id uniqueness |
| 4 | major | Same-name different-content PDF overwrites left old OCR/raw valid: new page images with old evidence, all gates green → content changes auto-invalidate downstream evidence; the response lists invalidated items |
| 5 | major | cmd_ingest's SystemExit pierced all exception handling: clicking process on an empty workspace = dropped connection → converted to a 400 page |
| 6 | major | ingest summary dropped: with some documents failing, documents quietly went missing → failed documents and reasons listed explicitly on the page |
| 7 | major | The `.wb-crop img` selector never matched (the class is on the img): evidence images broke the layout at native resolution → merged into `.wb-crop` |
| 8 | major | With JS off, a correct submit could not carry the corrected value (input permanently disabled) → HTML ships without disabled; JS disables by selection after load; semantics enforced server-side |
| 9 | major | The two-step-confirm armed state did not re-grade: changing the decision after arming made the confirmation text lie → radio change disarms |
| 10 | minor | The 404 page did not escape the request path (the app's only unescaped reflection surface) → escaped |
| 11 | minor | A non-zip upload to /verify → a full-page 500 traceback → verify_bundle gained a built-in BadZipFile failure branch (CLI benefits too) |
| 12 | minor | `.wb-topbar-inner` had no rule: top-bar layout collapsed → rule added |
| 13 | minor | A report-completeness test was always true (the assertion branch always held) → replaced with exact-count assertions |
| 14 | minor | The queue-page rationale XSS test guarded an area with no output → rationale now rendered into the current-adjudication notice (escaped), and the test asserts both escaped presence |

Rebutted as invalid (recorded, unchanged): hand-crafted POSTs missing the run
field (loopback, single user, no trigger path), handler-instance residue
across requests (HTTP/1.0, no keep-alive), three unstyled classes (no
contract to drift), /ingest two-generation races (already guarded by
pipeline's mkdir(exist_ok=False)).

One hole the review did not report, found in passing: a corrupt PDF made
pdftotext/pdftoppm raise CalledProcessError and blow through ingest — now
uniformly degrades to OcrUnavailable blocking (charter rule four).

## User testing (2026-08-03 evening, warm subject, 15 real adjudications)

4 real invoices (3 normal + 1 degraded scan with blocked OCR), 40 slots. The
user independently completed 15 adjudications (8 correct / 6 abstain /
1 accept, including the Harry Huge value backfill), all well-formed (snapshot
binding, no conflicts, no reversals). Bundle of 54 members, verify's three
layers all passed.

The live test caught three real bugs (all fixed + regression tests):

1. **The OCR-blocked document had no full-page images** — `render_pages` was
   gated inside the OCR-ok branch, so every row of a blocked document said
   "no original image" and review ran dry (user's words, HD-0015). Full-page
   rendering depends on neither OCR nor responses; moved ahead to every
   document that has a PDF.
2. **The upload tab link was built as `/upload&lang=zh`** — pick `?`/`&` by
   whether a query string exists; misassembly is a 404; "cannot go back" was
   404/message pages having no navigation — navigation now always points at a
   run that really exists.
3. Quick problem-label concatenation produced ";;" (cosmetic) — strip
   trailing `;` and whitespace before joining.

Also: the run holding those 15 adjudications is bundled and archived;
full-page images for the blocked document require a new run generation (old
runs are immutable; history stays).

## The vision gate's measured answer (2026-08-03, the 046e0c49 role-swap incident)

The user asked "why is vision off by default, and what happens if on." The
answer has two layers.

**Why off by default**: vision answers are a research product of
dws-derisk round six (full-page renders → three frontier models answering →
answers6 tsv), never ported into a live ingest step; workspaces have no
vision/ directory, and the vision gate honestly reports "not measured"
rather than skipping.

**What happens when on (measured on the same workspace)**: copy the
calibration archive's answers6 tsv into ws/vision/ and open a new run
generation (run-0003). Of the 4 documents only 046e0c49 — precisely the
scan whose OCR is blocked and whose other mechanical signals are all dead —
has vision answers; of its 10 slots, 8 have no DWS value (the vision gate
reports not-measured by design), but the 2 slots with values **both raise
warnings — and they are exactly the two fields DWS extracted with buyer and
seller swapped**:

| Field | DWS understand | DWS agentic | Vision A/B/C (unanimous) | User adjudication (made independently) |
|---|---|---|---|---|
| buyer_name | Cumulus-Muskegon - WVIB-FM (wrong) | SHIYA IFA | **SHIYA IFA** | HD-0016 corrected → **SHIYA IFA** |
| seller_name | SHIYA IFA (wrong) | Cumulus-Muskegon - WVIB-FM | **Cumulus-Muskegon - WVIB-FM** | HD-0020 corrected → **Cumulus-Muskegon - WVIB-FM** |

The user's two corrections, made with no machine signal visible (reading the
full page only), match the vision models' answers verbatim; the vision
gate's warnings point at exactly those two swapped fields. This is the best
demonstration of "on an OCR-blocked document, vision is the only surviving
machine signal." But the charter does not move: the vision gate is still a
warning, not a verdict — vision's independence from DWS passed the
pre-registered bar (lift 1.29×/1.33× < 1.5, THRESHOLDS §6g), but the
readers' own silent-error rate of 8.6–15.8% far exceeds the 1% line with a
59–61% abstention rate, so disagreement means "worth a look," not a verdict.
It corroborates and it prompts; it does not adjudicate.

> Erratum (2026-08-03 late, caught by the fidelity review): this section
> first wrote "vision and DWS failure modes are correlated (not independent,
> lift 2.40×)" — wrong. 2.40× is the lift of the dual-mode disagreement;
> vision's independence criterion passed. The warning's true reason is the
> readers' own error and abstention rates. Also: reader C (GPT 5.6 SOL) in
> the table was wholly voided in round six because 63.1% of its content
> appeared on other documents; it enters no verdict and is shown here for
> mechanism demonstration only.

## The vision pre-fill suggestion layer (2026-08-03 late)

The compliant version of the user's proposal "turn vision on by default for
slots needing adjudication; hand to a human when vision finds a problem."
The half you cannot have: vision auto-adjudicating — "vision finds a
problem" has no detector (a vision model is itself an extractor; round six's
118 mis-bound rows were some reader confidently wrong with zero
self-reporting). The half you can have: vision on by default, advising but
never adjudicating — the delivery invariant holds: every emitted value has
either mechanical support or one human click.

- **Suggestion layer (workbench)**: an inline purple advisory block "vision
  suggests: X · n/n readers agree + [adopt suggestion]". Adopting only
  pre-fills the form (accept, or correct + corrected value + rationale
  preset); submitting and signing remain human; when readers disagree the
  values are laid out with no adopt button; unanimous abstention honestly
  shows "vision cannot read it either." Agreement uses the same
  fields.normalise as the dual-mode gate. Test-pinned: after rendering
  suggestions, the adjudication ledger is still empty (pre-fill is form
  state only).
- **vision-ingest**: `python3 -m invoiceloop vision --workspace ws/` — the
  packet spec copied back item by item from vision_eval6.py by a sub-agent
  (DPI 150 full page, the five discipline prompts verbatim, tsv column
  order, the ABSTAIN convention, empty = abstain); one API call per document
  (discipline 5 forbids stitching anyway); tag D = Claude Sonnet 5, needs
  ANTHROPIC_API_KEY, missing key = typed unavailable; resumable runs append
  and never rewrite.
- **answers6 glob fix**: VISION_READERS was a hard-coded ABC list — a new
  reader's tsv would be missed by load_vision_answers and left out of the
  input fingerprint (changed answers, old run still replayed). Now every
  answers6.*.tsv on disk is read fully and hashed fully.

## The vision pipeline goes live (2026-08-03 deep night, kimi-k3 answering on the spot)

Credential-channel saga and conclusion: the token-plan relay is text-only
(probed all models, none support image input); local cliproxy
(127.0.0.1:8317)'s kimi-k3 accepts images — `vision --workspace ws --model
kimi-k3` read all four documents successfully, 14 fields honestly abstained,
zero failures. Three memorable moments from the live answers:

- 046e0c49's buyer/seller: kimi-k3 gave SHIYA IFA (label "Bill To:") and
  Cumulus-Muskegon - WVIB-FM (label "Station:") — three-way independent
  agreement with the user's corrections and with the archived three readers.
- 00136a27 due_date: **ABSTAIN**, the note says "no explicit due date; only
  Payment Terms: 30 Days" — discipline 1 (copy, don't compute) at work;
  whereas the user originally derived 11/30/2020 from issue date + 30 days.
  The model refuses to infer per its discipline; a human may legally reason
  — the best footnote to "that one human click cannot be skipped."
- 003cc916 buyer_name: "Harry Huge, Esq.", label "For", found independently.

From run-0004 on, 40/40 rows carry suggestion blocks (1/1 reader —
single-reader agreement is not corroboration; with multiple readers,
agreement/disagreement becomes the signal).
