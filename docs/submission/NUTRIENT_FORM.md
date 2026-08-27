# Nutrient DWS submission draft

> **Draft.** Replace the video placeholder and recheck the final repository state
> before submitting. This document is submission copy, not a new evidence source.

## Project

- **Name:** InvoiceLoop
- **Public repository:** https://github.com/Stahl-G/invoiceloop
- **Video:** `[PASTE THE 2–4 MINUTE DEMO LINK HERE]`

## One-line pitch

InvoiceLoop turns Nutrient DWS extraction into a human-controlled evidence and
approval workflow: the service extracts values and page regions, while InvoiceLoop
freezes the response, checks support relations, exposes uncertainty, and records
the human decision that is required before export.

## What Nutrient DWS does

Nutrient DWS performs the core document operation: extracting invoice fields and
their page grounding from PDF invoices. InvoiceLoop is not a replacement extractor
and does not claim that the extracted value is correct. It makes the DWS output
operationally accountable by preserving the raw response, checking six
deterministic relations, routing unresolved fields to review, and requiring a
named human for adjudication and document approval.

## Judge quickstart

The judge-facing path is documented in [`README.md`](../../README.md) under
“For judges — three commands, zero API cost”. It uses vendored sample documents
and stored responses; it does not call DWS or require an API key:

```bash
git clone https://github.com/Stahl-G/invoiceloop
cd invoiceloop
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m invoiceloop demo --out /tmp/invoiceloop-demo
.venv/bin/python -m invoiceloop workbench --workspace /tmp/invoiceloop-demo --port 8793
# In a second terminal, after reviewing the browser page:
.venv/bin/python -m pytest tests/ -q
```

For the clean-clone validation, run:

```bash
bash scripts/fresh_venv_check.sh
```

That check covers installation, doctor, the zero-API product path, adjudication,
bundle verification, replay, the vendored demo, and the test suite. Research
recomputation is intentionally skipped when the private DocILE calibration archive
is unavailable.

## Demo story for the video

The final video should show these facts on screen, with the real Workbench rather
than a slide-only claim:

1. DWS output enters the pipeline and is frozen before the support checks run.
2. A clean field shows its page evidence and deterministic gates.
3. A risky or unsupported field is sent to the human queue rather than silently
   exported.
4. The human decision, rationale, and approval boundary appear in the ledger and
   delivery projection.
5. `bundle` followed by offline `verify` produces the portable audit artifact.

## Evidence links

- Architecture and authority boundary: [`ADK_INTEGRATION.md`](../ADK_INTEGRATION.md)
  (the same deterministic boundary applies to the DWS review path).
- Valid v2 qualification result, including its negative safety outcome:
  [`QUALIFICATION_NARROW_V2_RESULTS_2026-08-23.md`](../QUALIFICATION_NARROW_V2_RESULTS_2026-08-23.md).
- Contamination and superseding-audit record:
  [`QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md`](../QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md).
- Pre-existing-work and submission-period disclosure:
  [`DISCLOSURE.md`](../../DISCLOSURE.md).

## Claims boundary

The submission must not say that InvoiceLoop improves extraction accuracy, makes
zero-touch payment safe, or generalizes beyond the measured DocILE / Nutrient
setting. The v2 result is a valid negative qualification: HAR-0023 reached
21/200 zero-touch documents (10.5%, 95% Wilson CI 7.0–15.5), but its zero-touch
payment subset contained six wrong comparable values and three unscored
auto-accept slots, so promotion was denied.

## Final checklist

- [ ] Replace the video placeholder with the uploaded 2–4 minute demo.
- [ ] Re-run `scripts/fresh_venv_check.sh` from the submitted commit.
- [ ] Confirm the public repository link and README quickstart still match.
- [ ] Keep all numbers linked to the frozen result documents above; do not
      recompute or broaden them in the form.
