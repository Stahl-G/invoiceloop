# InvoiceLoop

**Verifiable support for invoice extraction — not a claim that the extraction is correct.**

[Nutrient DWS](https://www.nutrient.io/) extracts values from a PDF. InvoiceLoop
is the evidence, review, and approval layer that makes those values operationally
accountable. It does not decide that an invoice may be posted. It decides what
the machine has finished, what it still does not know, and it leaves posting
authority with a named human.

**The deliverable is a support matrix, not a verdict.**

<p align="center">
  <a href="docs/architecture.html">Architecture diagram</a> ·
  <a href="DISCLOSURE.md">Pre-existing work disclosure</a> ·
  <a href="docs/ADK_INTEGRATION.md">Agent layer</a> ·
  <a href="docs/CLOUD_RUN.md">Deployment</a>
</p>

## What is broken

DWS can return a value and ground it to a page region. Grounding answers "this
string was found somewhere." It does not answer whether that field should be
trusted, posted, or paid.

Vendor confidence on `/extraction/extract` is grounding-only (Nutrient confirmed:
logprobs are off for the current model). Six pre-registered rounds found that
**no single tested signal** — confidence, arithmetic checks, dual-mode
disagreement, independent OCR, or a frontier model reading the page — flags every
consequential extraction error. Signals help. None of them is a verdict.

## What InvoiceLoop adds

Independent OCR against the cited region, six deterministic gates, a frozen
claim ledger the model cannot write, routing into auto-accept / auto-absent /
review / block, append-only human adjudication, and a document-level approval
the machine may never perform. Automation stops at `ready_for_approval`. Only a
signed human approval reaches `approved_for_export`.

An optional [Google ADK](docs/ADK_INTEGRATION.md) loop may propose a tighter
routing policy from review history. It assigns no IDs, writes no ledger, and
cannot promote itself.

Support relations on an invoice are geometric — a bounding box against a page
region, verifiable word by word with independent OCR. That argument does not
apply where invoicing has moved to structured XML (mainland China, Italy's
FatturaPA). **This project targets US-style PDF invoices.**

## Try it — zero API calls, no external data

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -m invoiceloop doctor
python3 -m invoiceloop demo --out demo-ws
python3 -m invoiceloop workbench --workspace demo-ws   # http://127.0.0.1:8765
```

Three DocILE invoices ship with their DWS responses already on disk. Nothing
calls the network. Open the queue: weakest support first. Open a row: page
region, independent OCR, gate findings. The demo's decisions and approvals are
signed `demo-fixture (not a human review)` — no person looked at those rows.

One sample (`046e0c49`) is a degraded scan. Most poppler builds cannot pull a
text layer from it, so OCR blocks and the document carries that caveat into
export; some builds recover text and it flows normally. **Both outcomes are
legal.** What is pinned is the invariant: unavailable evidence is never treated
as a silent pass.

System dependency: poppler (`brew install poppler`). tesseract is optional —
without it, scanned pages block rather than pass silently.

`pip install -e ".[dev,gemini]"` is only for the optional agent tests and the
ADK improvement loop.

## Who this is for, and what a wrong field costs

The first user is an **accounts-payable clerk** who today eyeballs each key field
before it goes into the ERP. InvoiceLoop does not replace reading the invoice; it
replaces **confirming the fields the machine can already vouch for**.

| Wrong field | Consequence |
|---|---|
| `total_gross` / `amount_due` | Mispayment — recovering it afterwards costs far more than catching it |
| `invoice_number` wrong or duplicated | Paying the same invoice twice — the cross-document duplicate check exists for this |
| `seller_vat_id` | Tax filing exposure; an audit sends the batch back |
| `seller_name` / `buyer_name` swapped | Payment to the wrong party. Observed in practice: an ad agency extracted where the broadcast station was the seller |

The second user is an **auditor**: every value in the delivery answers "why should
I believe this", and the answer recomputes offline.

## What leaves the system

Every run writes `deliverable.json` — one row per field as
`{value, status, source}`, and a per-document status:

- **`approved_for_export` / `approved_for_export_with_caveats`** → downstream
  AP/ERP can post it. **Only a signed human approval reaches this status.**
- **`ready_for_approval` / `ready_for_approval_with_caveats`** → every gating
  slot has been dealt with. This is where automation stops. No status a machine
  can reach on its own carries posting authority.
- **`pending` / `blocked`** → stays in the queue, never reaches downstream
- `source` traces each value back to a frozen claim, a human decision, or a
  named policy version

Approval is per document. The record in `approve_ledger.jsonl` carries the
signature, the reason, the digest of the values at that moment, and **the list of
fields the routing policy released without anyone reading them**. Change a value
afterwards and the approval goes stale — the document drops back to
`ready_for_approval` and someone has to sign again. The stale approval stays in
the ledger; who approved what is audit trail, not clutter.

Values come only from the frozen ledger and the adjudication ledger. **The support
matrix is never the value source.**

## Posting is not a ten-field census

A routing policy with no `release_profile` is **census**: every scored field
still `pending`, `pending_tier1`, or `abstained` keeps the document from
`ready_for_approval`. Packaged HAR-0001 stays that way so sealed replay does
not drift.

The product contract since 2026-08-14 is `payment_required_v1`. Posting waits
on `invoice_number`, `seller_name`, and `amount_due`. Other scored fields stay
on the support matrix, labelled unreviewed. A named human still has to approve
the document. The machine still cannot export. Design:
[`docs/RELEASE_PROFILE_DESIGN_2026-08-14.md`](docs/RELEASE_PROFILE_DESIGN_2026-08-14.md).

HITL round 1 tested the older census walk — AI pre-read plus a ten-field queue —
on a development set of 20 documents. All 20 opened; median time 52 seconds per
slot; the pre-registered time estimate was off by about five times. The round
was **pre-registered terminated** before S2's first adjudication. S2–S5 were
not spliced onto the S1 curve. Record:
[`docs/HITL_R1_TERMINATION_2026-08-14.md`](docs/HITL_R1_TERMINATION_2026-08-14.md).

The follow-up walk used the payment contract, on a separate 20-document
development set: 4/20 documents never entered the walk, the three payment
fields had 0 unresolved slots, and 0 QA probes reversed an auto-accept or
auto-absent. Unopened is not correct — residual error still carries the
ARCHITECTURE §8 qualifiers. The arm had confounders (mid-round ADK inject,
protocol edits after the first decision) and is not a qualification result.
Record: [`docs/HITL_NARROW_2026-08-14.md`](docs/HITL_NARROW_2026-08-14.md).

## Evidence

All from stored Nutrient DWS responses — verifying them needs no API calls.
Protocols and dated logs live under [`docs/`](docs/README.md).

| | |
|---|---|
| Triage lift, SEALED-4 (broadcast unseen subset) | Human queue **63.7% → 47.2%** for HAR-0001 → HAR-0021; both silent-error classes did not rise. Qualification **passed** on that broadcast pool only — [`docs/SEALED4_RESULTS.md`](docs/SEALED4_RESULTS.md) |
| Triage lift, SEALED-3 (100 sealed unseen documents) | **3.75x**; H1 passed, but qualification **failed** because one annotated `seller_vat_id` was silently auto-absented |
| Human queue, paired SEALED-3 replay | **62.4% → 52.7%** for HAR-0001 → HAR-0004, silent-absence count **0 → 1** |
| Triage lift, SEALED-1 (100 sealed unseen invoices) | **4.03×** against pre-registered thresholds |
| TIER1 silent-error rate vs a confidence-threshold baseline | **9.62%** vs **21.91%** at a fixed operating point |

> **SEALED-3 — valid unseen measurement, qualification failed.** The primary
> HAR-0004 arm reduced the human queue by 9.7 points and reproduced triage lift,
> but it silently auto-absented one annotated seller tax identifier that HAR-0001
> kept in review. No qualification marker was written.
>
> **SEALED-2 — held-out status revoked 2026-08-07.** The numbers are real; the
> batch was later used during development. Revocation is enforced in
> `improve.SEALED_SET_REVOCATIONS`, not by deleting marker files.
>
> **SEALED-1** remains a past result (measured 2026-08-03). It is spent for *new*
> held-out measurements. **SEALED-4** is the current unseen qualification, and
> only for the broadcast-scoped pool named in that protocol.

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

python3 -m invoiceloop render --run ws/runs/run-0001
python3 -m invoiceloop bundle --run ws/runs/run-0001
python3 -m invoiceloop verify ws/runs/run-0001/audit_bundle.zip

python3 -m pytest tests/                              # product path; research tests skip without the calibration archive
python3 -m pytest tests/test_agents_*.py              # needs pip install -e ".[dev,gemini]"
```

Open `demo-ws/runs/run-0001/support_panel.html` — static, offline, no server.

## Repository layout

| | |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The design contract. Written in Chinese |
| [`GOAL.md`](GOAL.md) | What to optimise when the design docs run out. Chinese |
| [`DISCLOSURE.md`](DISCLOSURE.md) | What pre-dates which submission window, and how to check it |
| [`docs/architecture.html`](docs/architecture.html) | Architecture diagram (dark/light, exportable) |
| [`docs/ADK_INTEGRATION.md`](docs/ADK_INTEGRATION.md) | The agent layer, its authority boundary, and its known limits |
| [`docs/CLOUD_RUN.md`](docs/CLOUD_RUN.md) | Deployment, and why the public instance is read-only |
| `docs/*_2026-*.md` | Dated research records — experiment logs, mostly Chinese. See [`docs/README.md`](docs/README.md) for an English index |

**A note on language.** Reader-facing documentation is English. The dated research
records and most code comments are in Chinese, because they are a working
laboratory notebook. `docs/README.md` says in English what each one contains.

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
