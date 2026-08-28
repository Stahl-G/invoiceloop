# Document Type Integration Investigation (Stage B, 2026-08-07)

Plan: `docs/DOCTYPE_PLAN_2026-08-07.md`. This file registers investigation conclusions only; **no product integration lands**.

Recompute:

```bash
INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_block_impact.py
```

## Q1 — Where do document-level verdicts go?

### `evaluations` consumers (exhaustive)

| Consumer | How it reads | If `__document__` is stuffed in |
|---|---|---|
| `matrix.derive_document_records` | `evaluations[doc][field]` | ignores unknown field keys → harmless, but the type verdict is invisible |
| `improve` counterfactual re-routing | same | same |
| `adjudicate` verify semantic layer | same | same |
| `scripts/heldout_metrics.py` H4/H5 | **flattens** `for doc in evaluations.values() for v in doc.values()` | **contaminates missing-value rate / citation denominators** |
| `scripts/adaptive_probe.py` | `.items()` by field | treats `__document__` as a field |
| C8 precedent | stamps back onto the `invoice_number` slot | type has no natural home slot |

### Option verdict

| Option | Verdict |
|---|---|
| (a) `evaluations[doc]["__document__"]` | **No** — breaks heldout_metrics flattening and the probe |
| (b) `gate_report["document_checks"][doc_id]` | **Preferred** — additive; consumers read it explicitly; can enter `input_signature` |
| (c) standalone `doctype_report.json` | workable as a deliverable projection, but the gate transaction signature needs a separately hung digest — two sources of truth |

**Selected (Stage C target): (b)**. `findings` can still hang a parallel `gate_id=doctype_evidence`
(whether it blocks is decided by the Q2 granularity). Historical runs lack the key → consumers must `.get`.

## Q2 — Blocking granularity's effect on SEALED-2 load

Documents with no type literal evidence: **9**.

| Granularity | human_queue | Δpp | Note |
|---|---|---|---|
| baseline HAR-0004 | 468/1000 (46.8%) | — | |
| **document-level all-slot block** | **513/1000 (51.3%)** | **+4.5** | 45 slots newly forced into the queue |
| type-dependent verdicts only / non-blocking finding | 468/1000 | **0** | deliverable marks 9 documents "type untrusted" |

The plan's exit line was "all three >5pp and recovering no silent errors → C pauses".
Document-level **+4.5pp < 5pp** does not trigger the pause line; but what +4.5pp buys is dragging
unrelated fields already machine-released into the queue — **out of proportion to "catching type
misreporting"**.

**Selected granularity: block/downgrade type-dependent verdicts only + non-blocking finding + deliverable visibility.**
The 9 documents' full 10 slots are not `block`ed. Stage C wires in on this basis; if something
stricter is wanted later, open a preregistered measurement.

## Stage C entry conditions

- [x] Q1 option selected: (b) `document_checks`
- [x] Q2 granularity selected: typedep / finding (no net load increase)
- [x] execution fingerprint gains `doctype_digest` (`snapshot.build_input_manifest` + `gates` input_signature)
- [x] all three replay test suites zero diff (`pytest` 489 passed, including binding/port/heldout)

**Stage C has landed** (2026-08-07): `document_checks` + non-blocking finding;
`deliverable.docs[*].type_trust`; SEALED-2 smoke test `40532c4e…` → fail/untrusted,
`086b0b4d…` → pass/`purchase_order`. Next stop, Stage D.

Stage D has run and was **KILLed** (see `docs/DOCTYPE_STAGE_D_2026-08-07.md`).
Next stop, Stage E (applicability matrix); `doc_class` must not substitute for party direction.
