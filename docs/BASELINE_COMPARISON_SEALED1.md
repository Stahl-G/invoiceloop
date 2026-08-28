# SEALED-1 baseline comparison (executed 2026-08-05, sealed set; five-way contract consistent with the rewritten caliber)

Subject: `runs/sealed1` (100 documents sealed via drand, `docs/SEALED1_RESULTS.md`).
Recompute: `INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/baseline_comparison.py runs/sealed1 runs/sealed1-workspace`
(zero API, entirely from stored evidence; the caliber is the same as the rewritten docs/BASELINE_COMPARISON.md:
each system is scored from its own prediction source, wrong/missing values split, fixed tie-break + within-tie-group ranges).

Note: in this batch every DWS non-empty value sits at the 0.95 level, so "confidence threshold" and "release only if value" coincide exactly
(confidence has no discriminating power in this batch; the ordering comparison's opponent is on the weak side — the same caveat as the SEALED1_RESULTS secondary-endpoint note).

### All scored fields (575 slots)

| System | Auto-release coverage | Field silent error rate | of which wrong values | of which released missing | Document silent failure rate | Review load | Deviation routing recall |
|---|---|---|---|---|---|---|---|
| raw DWS (full trust) | 100.0% (575/575) | 40.87% | 28.52% | 12.35% | 92.0% (100/100 whole-document release) | 0.0% | 0.0% |
| raw DWS (release only if value) | 87.7% (504/575) | 32.54% | 32.54% | 0.00% | 86.0% (57/100 whole-document release) | 12.3% | 30.2% |
| Confidence threshold (≥0.95) | 87.7% (504/575) | 32.54% | 32.54% | 0.00% | 86.0% (57/100 whole-document release) | 12.3% | 30.2% |
| Dual-mode agreement | 66.6% (383/575) | 20.10% | 20.10% | 0.00% | 72.2% (18/100 whole-document release) | 33.4% | 67.2% |
| InvoiceLoop triage | 54.3% (312/575) | 18.27% | 18.27% | 0.00% | 75.0% (12/100 whole-document release) | 45.7% | 77.0% |

### TIER1 critical fields only (281 slots, rubric critical fields)

| System | Auto-release coverage | Field silent error rate | of which wrong values | of which released missing | Document silent failure rate | Review load | Deviation routing recall |
|---|---|---|---|---|---|---|---|
| raw DWS (full trust) | 100.0% (281/281) | 30.25% | 19.57% | 10.68% | 51.5% (99/99 whole-document release) | 0.0% | 0.0% |
| raw DWS (release only if value) | 89.3% (251/281) | 21.91% | 21.91% | 0.00% | 40.7% (81/99 whole-document release) | 10.7% | 35.3% |
| Confidence threshold (≥0.95) | 89.3% (251/281) | 21.91% | 21.91% | 0.00% | 40.7% (81/99 whole-document release) | 10.7% | 35.3% |
| Dual-mode agreement | 74.4% (209/281) | 12.92% | 12.92% | 0.00% | 26.8% (56/99 whole-document release) | 25.6% | 68.2% |
| InvoiceLoop triage | 55.5% (156/281) | 9.62% | 9.62% | 0.00% | 23.7% (38/99 whole-document release) | 44.5% | 83.3% |

### Comparison at equal human budget (TIER1 deviation recall, top b% of slots to human)

| Review budget | Confidence ascending | InvoiceLoop triage order |
|---|---|---|
| 10% | 29.4% | 31.1% |
| 20% | 31.8% | 55.6% |
| 30% | 41.2% | 63.3% |
| 40% | 49.4% | 77.8% |
At a 10% budget the cut lands inside a confidence tie group: fixed tie-break 29.4%; full range within the tie group [29.4%, 32.9%], uniform-random expectation 30.2%
At a 20% budget the cut lands inside a confidence tie group: fixed tie-break 31.8%; full range within the tie group [29.4%, 65.9%], uniform-random expectation 38.0%
At a 30% budget the cut lands inside a confidence tie group: fixed tie-break 41.2%; full range within the tie group [29.4%, 98.8%], uniform-random expectation 45.7%
At a 40% budget the cut lands inside a confidence tie group: fixed tie-break 49.4%; full range within the tie group [29.4%, 100.0%], uniform-random expectation 53.4%
At the 30% budget, confidence ascending 95% CI (bootstrap by document, n=1000): [30.0%, 54.1%]
At the 30% budget, InvoiceLoop triage order 95% CI (bootstrap by document, n=1000): [54.6%, 74.4%]

Caliber: exploratory analysis, not pre-registered; each system is scored from its own prediction source (stored raw responses / frozen ledger), deviations not shared; confidence ties broken by a fixed (doc_id, field) tie-break; the InvoiceLoop product itself does not auto-release — this table evaluates the counterfactual quality of the triage signal.
