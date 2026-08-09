# InvoiceLoop

**Verifiable support for invoice extraction — not a claim that the extraction is correct.**

InvoiceLoop is a verification and review layer on top of
[Nutrient DWS](https://www.nutrient.io/) invoice extraction. It does not assert
that an extracted value is right. It makes every extracted value *answerable*:
which region of the page it binds to, what an independent OCR reads in that
region, what six deterministic checks found, and where the machine admits it
does not know.

Fields the machine cannot vouch for go to a focused human queue. Everything —
extraction, checks, routing, human decisions — lands in an append-only,
hash-chained record that verifies offline.

**The deliverable is a support matrix, not a verdict.**

<p align="center">
  <a href="docs/architecture.html">Architecture diagram</a> ·
  <a href="DISCLOSURE.md">Pre-existing work disclosure</a> ·
  <a href="docs/ADK_INTEGRATION.md">Agent layer</a> ·
  <a href="docs/CLOUD_RUN.md">Deployment</a>
</p>

## Quickstart — zero API calls, no external data

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -m invoiceloop doctor            # says what is missing; exit 1 if the product path is incomplete
python3 -m invoiceloop demo --out demo-ws
python3 -m invoiceloop workbench --workspace demo-ws   # http://127.0.0.1:8765
```

The demo ships three DocILE invoices with their DWS responses already on disk.
Nothing calls the network. It ends with two documents `approved_for_export`, one
`approved_for_export_with_caveats` (its OCR was blocked — a document released
while a check could not run must never look as clean as one where every check
passed). The demo's decisions and its approvals are both signed
`demo-fixture (not a human review)`: no person looked at those rows.

System dependency: poppler (`pdftotext` / `pdftoppm`; `brew install poppler`).
tesseract is optional — without it, scanned pages block rather than pass silently.

## Who this is for, and what a wrong field costs

The first user is an **accounts-payable clerk** who today eyeballs each key field
before it goes into the ERP. InvoiceLoop does not replace reading the invoice; it
replaces **confirming the fields the machine can already vouch for**.

| Wrong field | Consequence |
|---|---|
| `total_gross` / `amount_due` | Mispayment — recovering it afterwards costs far more than catching it |
| `invoice_number` wrong or duplicated | Paying the same invoice twice — the cross-document duplicate check exists for this |
| `seller_vat_id` | Tax filing exposure; an audit sends the batch back |
| `seller_name` / `buyer_name` swapped | Payment to the wrong party — harder to unwind than a wrong amount. Observed in practice: an ad agency extracted where the broadcast station was the seller |

The second user is an **auditor**: every value in the delivery answers "why should
I believe this", and the answer recomputes offline.

## What leaves the system

Every run writes `deliverable.json` — one row per field as
`{value, status, source}`, and a per-document status:

- **`approved_for_export` / `approved_for_export_with_caveats`** → downstream
  AP/ERP can post it. **Only a signed human approval reaches this status.**
- **`ready_for_approval` / `ready_for_approval_with_caveats`** → every slot has
  been dealt with, by a person or by the routing policy. This is where
  automation stops. It is *not* postable: no status a machine can reach on its
  own carries posting authority.
- **`pending` / `blocked`** → stays in the queue, never reaches downstream
- `source` traces each value back to a frozen claim, a human decision, or a
  named policy version — so an audit question does not mean re-opening the PDF

Approval is per document, not per field, and it binds to what was approved: the
record in `approve_ledger.jsonl` carries the signature, the reason, the digest of
the values at that moment, and **the list of fields the routing policy released
without anyone reading them** (key fields called out separately). Change a value
afterwards and the approval goes stale — the document drops back to
`ready_for_approval` and someone has to sign again. The stale approval stays in
the ledger; who approved what is audit trail, not clutter.

This split is deliberate. A routing policy is allowed to decide *is this value
trustworthy* — a wrong auto-accept is caught by QA sampling. It is not allowed to
decide *may this invoice be posted*. Before 2026-08-09 it effectively was: a
document whose every slot the policy released reached `released` with no person
ever having looked at it, and this file said `released` was postable. Widening
straight-through then quietly widened posting authority. It no longer does, which
is what makes it safe to keep widening it.

Values come only from the frozen ledger and the adjudication ledger. **The support
matrix is never the value source**, and human adjudication is an overlay on frozen
evidence rather than a rewrite of it: a corrected field keeps the original
extracted claim, the machine's verdict, and the decision that changed it.

Integration is a **single-file contract plus a local service** — no SDK. The
workbench is stdlib `http.server` and drops into any internal network.

## What it does not do

It does not promise accurate extraction. Six pre-registered experiment rounds on
the DocILE corpus, plus a 100-document held-out review, found that **no single
signal** — vendor confidence, arithmetic consistency, dual-mode disagreement,
independent OCR citation, or a frontier model reading the page — identifies every
consequential extraction error.

The vendor agrees on the confidence point. Asked why `confidenceComponents.source`
was `"no-logprobs"` on all 1,066 observations we measured, Nutrient's engineering
confirmed that logprobs are disabled for the current model, and that correctness
signals are "something you'd need to build on top." That is what this is.

## Why invoices, and which invoices

Support relations in a business brief are semantic, and cannot be checked.
Support relations on an invoice are **geometric** — a bounding box against a page
region, verifiable word by word with an independent OCR.

That argument holds where an invoice is a *document*. It does not apply in
jurisdictions that have moved to structured e-invoicing — mainland China's XML
format, Italy's FatturaPA — where the data arrives already parsed and there is
nothing to bind to a page. **This project targets US-style PDF invoices.**

## The improvement loop, and its limits

Review load falls by turning repeated human confirmations into a versioned
routing policy (a *harness*), never by claiming better extraction. A candidate
policy has to survive a deterministic counterfactual replay plus a human
signature before it takes effect.

An agent layer (Google ADK, `gemini-3.6-flash`) proposes and argues about
candidates. It has no authority: it writes advisory reports only, Python
recomputes every candidate, and promotion needs Gate 2 plus a signed human
decision. See [`docs/ADK_INTEGRATION.md`](docs/ADK_INTEGRATION.md), which also
lists what that layer has *not* been shown to do.

## Numbers you can recompute

All from stored evidence — verifying them needs no API calls.

| | |
|---|---|
| Triage lift, SEALED-3 (100 sealed unseen documents) | **3.75x**; H1 passed, but qualification failed because one annotated `seller_vat_id` was silently auto-absented |
| Human queue, paired SEALED-3 replay | **62.4% -> 52.7%** for HAR-0001 -> HAR-0004, with silent-absence count **0 -> 1** |
| Triage lift, SEALED-1 (100 sealed unseen invoices) | **4.03×** against pre-registered thresholds |
| Decision load for release, SEALED-1 | **82.9% → 64.2%** under the promoted HAR-0002 policy |
| TIER1 silent-error rate vs a confidence-threshold baseline | **9.62%** vs **21.91%** at a fixed operating point |
| Test suite | **634 passing, 3 skipped** (`python3 -m pytest tests/ -q`), including a 454-row replay of a round-six misbinding incident and a point-by-point check against the original implementations |

Protocols and results: [`docs/SEALED3_RESULTS.md`](docs/SEALED3_RESULTS.md),
[`docs/SEALED1_RESULTS.md`](docs/SEALED1_RESULTS.md),
[`docs/BASELINE_COMPARISON_SEALED1.md`](docs/BASELINE_COMPARISON_SEALED1.md).

> **SEALED-3 — valid unseen measurement, qualification failed.** Seven frozen
> arms consumed the same 100-document evidence in one non-adaptive batch. The
> primary HAR-0004 arm reduced the human queue by 9.7 percentage points and
> reproduced triage lift at 3.75x, but it silently auto-absented one annotated
> seller tax identifier that HAR-0001 kept in review. The pre-registered P1 gate
> therefore failed. No qualification marker was written. An unpromoted ADK
> `due_date` candidate saved another 3.3 points but added five more silent
> absences, so it was rejected. See the result for the exact paired counts and
> the newly exposed workload-metric defect.

> **On SEALED-2 — held-out status revoked 2026-08-07.** A second sealed
> evaluation exists (`docs/SEALED2_RESULTS.md`, lift 3.19×) and its numbers are
> real, but the batch was subsequently used during development: the document-type
> vocabulary was written by reading its free-text spellings, and a Stage D
> prototype was scored against it. The SEALED-2 protocol pre-registered exactly
> this as a disqualifying event, so the qualification is withdrawn — not as a
> judgement call, but as the pre-registered consequence firing.
>
> The revocation is **enforced in code, not stated in a document**
> (`improve.SEALED_SET_REVOCATIONS`): the `sealed2_qualified` basis is now
> unreachable, and a promotion carrying the old marker records why it was
> refused. The three marker files are deliberately **left on disk, untouched** —
> deleting them would neither stop the next person from writing a new one nor
> preserve the true fact that the evaluation did run. Verified against those live
> markers: the one that names `HAR-0004` now yields the withdrawn wording where
> it previously granted the upgrade.
>
> **Why SEALED-1 is not equally dead.** Its headline result — triage lift 4.03×
> — was measured on 2026-08-03, before any of this existed. A finished
> measurement is not retroactively invalidated by later exposure. What *is* spent
> is SEALED-1's use for **new** held-out measurements: four load-bearing tokens in
> the same vocabulary (`donation`, `\bcheck\b`, `sale`, `rebate`) come from its
> spellings too.
>
> So: SEALED-1's 4.03x remains a past result, while SEALED-3 supports the
> narrower, revision-bound result stated above. **No existing set is available
> for another new held-out measurement**: SEALED-3 was spent by this one-shot
> opening, and any fix inspired by its failures needs SEALED-4.

## Everyday commands

```bash
# Your own invoices: drop PDFs into workspace/input/pdfs/
python3 -m invoiceloop ingest --workspace ws/         # local OCR + DWS extraction (needs DWS_API_KEY)
python3 -m invoiceloop run --workspace ws/ --crops    # → ws/runs/run-NNNN, immutable

# Same input again replays the existing run; changed input opens a new generation.
# Old runs are never rewritten.

python3 -m invoiceloop adjudicate --run ws/runs/run-0001 --doc <doc_id> --field total_gross \
  --claim-id FC-0042 --decision accept --rationale "matches the page" \
  --adjudicator <name> --decided-at 2026-08-02T10:00:00
# Deciding the same field twice requires an explicit --supersedes.

python3 -m invoiceloop render --run ws/runs/run-0001   # rebuild the panel from artifacts (pure projection)
python3 -m invoiceloop bundle --run ws/runs/run-0001   # self-contained: upstream PDF/OCR/raw + every derivative
python3 -m invoiceloop verify ws/runs/run-0001/audit_bundle.zip   # offline; a single-byte edit anywhere is caught

python3 -m pytest tests/
```

Open `demo-ws/runs/run-0001/support_panel.html` — static, offline, no server. The
review queue sorts by support strength, weakest first: the top of the queue is
where the system says it does not know.

## Repository layout

| | |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The design contract. Written in Chinese |
| [`GOAL.md`](GOAL.md) | What to optimise when the design docs run out. Chinese |
| [`DISCLOSURE.md`](DISCLOSURE.md) | What pre-dates the hackathon submission period, and how to check it |
| [`docs/architecture.html`](docs/architecture.html) | Architecture diagram (dark/light, exportable) |
| [`docs/ADK_INTEGRATION.md`](docs/ADK_INTEGRATION.md) | The agent layer, its authority boundary, and its known limits |
| [`docs/CLOUD_RUN.md`](docs/CLOUD_RUN.md) | Deployment, and why the public instance is read-only |
| `docs/*_2026-*.md` | Dated research records — experiment logs, mostly Chinese. See [`docs/README.md`](docs/README.md) for an English index |

**A note on language.** Reader-facing documentation is English. The dated research
records and most code comments are in Chinese, because they are a working
laboratory notebook: they record which hypotheses were falsified and which
assumptions turned out wrong, and translating them risks losing the point they
were written to preserve. `docs/README.md` says in English what each one contains.

## Lineage

The support-sufficiency stack is adapted from BriefLoop architecture reference
v0.6.1 §3.6, where it is marked experimental and its semantic gate is explicitly
"not delivered". InvoiceLoop implements it in a domain where the support relation
is mechanically checkable.

The calibration corpus and six rounds of experiment evidence live in a sibling
archive, `~/Developer/dws-derisk/` — 5,680 DocILE PDFs (Rossum's public invoice
set, MIT-licensed) and 321 stored DWS responses. It is **not required** for the
product path: demo, workbench, run, bundle and verify are all self-contained.
Research tests skip cleanly when it is absent.
