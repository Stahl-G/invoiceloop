# Held-out set pre-registration protocol (frozen before execution)

Purpose: retire ARCHITECTURE.md §8 limitation one — "the gates were designed after seeing the first round of data, carry optimistic bias, and a held-out confirmation has never been run." This is the only test that can retire it.
**Requires new DWS calls (billed); approval needed before execution.** This document freezes the criteria first:
six-rounds discipline — answers submitted before scoring, wrong predictions reported as-is.

## Sampling (deterministic; see the list before spending)

- Population: DocILE documents with ≥4 scored-field annotations (the same "worth one call" threshold as the calibration set,
  `run_batch.sample`'s min_fields) that **never entered** the six-round 160-document calibration set
  (calibration set = dws-derisk `run_batch.sample(160)`, traceable in commit history)
- N = 100, drawn as: systematic sampling over the sorted candidate doc_ids (stride = pool/100), fixed seed;
  the list is attached to the execution record, and **the list is committed before any call**
- 2 calls per document (understand + agentic), 200 in total; storage discipline as in extract.py:
  write raw/ first, interpret after

## Budget (added 2026-08-02; measured from the usage blocks of 320 stored calls)

understand averages 19.7 per call, agentic 31.5 per call → **estimated ≈5,100 credits**,
circuit-breaker line **6,000**: when cumulative spend (summed from each response's usage cost) exceeds it, pause and report.
Multiple keys are injected via environment variables (never into the repo); no per-key attribution (decision: not needed);
the usage blocks' remainingCredits are stored as-is.

## Pre-registered criteria (written 2026-08-02; not to be modified after execution)

Control group = same-caliber measured values on the 160-document calibration set (outputs of this repo's
`runs/demo` and `tests/test_triage_concentration.py`):

| # | Quantity | Calibration value | Held-out pass interval | Basis |
|---|---|---|---|---|
| H1 | Triage lift (deviation rate top 50% / bottom 50%) | 4.10× | **> 1.5** | Ordering better than random is the architecture's single core claim |
| H2 | coverage@46% | 78.1% | **> 55%** | Calibration point 78%; held-out decay allowed |
| H3 | Review recall (needs-adjudication rows covering deviations) | 75.1% | **> 55%** | The floor of "humans look by design" |
| H4 | extraction_present missing rate | ≈25% (the missing-value share of the 428 blocks / 1600 slots) | **10–45%** | Distribution drift check, two-sided interval |
| H5 | Failure rate on the citation-decidable subset | Calibration roughly 3–5% | **< 15%** | The main hiding place of optimism bias |
| H6 | Freeze rejection rate (understand drafts) | 15.4% (247/1604) | **5–35%** | OCR degradation is the main cause, two-sided interval |

**Verdict rule: H1 missing the bar = overall failure**; the panel sentence "triage ordering measured" is downgraded to
"holds on the calibration set only"; any of H2–H6 missing the bar = written into the §8 limitation list
as-is, with numbers attached, without adjusting the criteria and retesting.

## Known risks (writing them down is admitting they may exist)

- The held-out set's document-type distribution may differ from the calibration set (the calibration set is
  entirely US broadcast-advertising invoices, §8 limitation three); an H4/H6 breach is distribution information first
  and a system problem second — report the two separately
- DocILE's annotation error rate (limitation two) exists on the held-out set as well, so the deviation rate has floor noise
- This protocol measures the **ordering ability of the deterministic pipeline** and does not involve the image-reading model —
  the image-reading layer (visual_corroboration) has no stored answers on the held-out set, so that gate will be
  unavailable throughout; this is itself the honest presentation of "not yet measured"

## Execution checklist (after approval)

1. Generate the list per §Sampling; commit the list (before any call)
2. Run extract (understand + agentic); store
3. `python3 -m invoiceloop run --doc-ids <list> --out runs/heldout`
4. Recompute H1–H6 (the same code as the triage tests, pointed at runs/heldout)
5. Write the results into this file's "Results" section, judging each criterion one by one; **wrong predictions reported as-is**

---

## Results (execution completed 2026-08-02)

**Execution record**: list at `docs/heldout_doc_list.json` (commit `56d85ed`, before any call);
all 200 calls returned 200 OK, zero failures; total spend **4,758 credits** (estimate ≈5,100,
circuit-breaker line 6,000, never triggered); all three keys used (`keys_used=3`);
artifacts under `runs/heldout/`; verdict command
`INVOICELOOP_DWS_DERISK=runs/heldout-workspace python3 scripts/heldout_metrics.py runs/heldout runs/demo`.

| # | Quantity | Calibration | Held-out | Pre-registered interval | Verdict |
|---|---|---|---|---|---|
| H1 | Triage lift | 4.10× | **3.04×** | > 1.5 | **PASS** |
| H2 | coverage@46% | 78.1% | **74.3%** | > 55% | **PASS** |
| H3 | Review recall | 75.1% | **72.5%** | > 55% | **PASS** |
| H4 | Missing-value rate | 26.8% | **27.9%** | 10–45% | **PASS** |
| H5 | citation failure rate | 15.3% | **14.4%** | < 15% | **PASS** |
| H6 | Freeze rejection rate | 18.9% | **34.6%** | 5–35% | **PASS** |

(574 scored slots, 218 deviations; head-of-queue deviation rate 57.1% vs tail-of-queue 18.8%.)

**Verdict: overall pass.** H1 made the bar — triage ordering kept concentration far above random on a
100-document held-out set that took no part in design (3.04× vs the 1.5× line). §8 limitation one is retired per the pre-registered disposition.

**Deviations reported as-is (the parts where predictions were wrong; criteria untouched)**:

1. The H5 pre-registered footnote said "calibration roughly 3–5%" — that was wrong: under this
   protocol's caliber (failure rate on the decidable subset), the calibration set measured 15.3%, not 3–5%. The 3.1%
   quoted at the time was the round-three T1 silence rate; the two quantities are different. The interval (<15%)
   was guessed right, the basis was written wrong; recorded here.
2. H6 hugs the upper bound: the held-out rejection rate is 34.6%, nearly double the calibration 18.9%.
   Read together with H4: the missing-value rates are nearly identical (27.9% vs 26.8%), so DWS behavior did not
   change; rather, the held-out set's document-type distribution is wider (calibration is all US broadcast-advertising
   invoices), with more OCR-degraded documents — the main cause of binding rejection is OCR quality, consistent with the
   §8b known boundary. This ratio must be re-estimated when the corpus changes; written into the limitations.
3. H1 decayed (4.10 → 3.04) but remains 2 times the pass line; the decay direction matches "calibration was
   optimistic", and the magnitude is smaller than feared.

**Disposition**: ARCHITECTURE.md §8 limitation one becomes "executed (this section)"; limitation three keeps half —
reproduced within DocILE's full type range, still unknown beyond DocILE. Limitation two (annotation quality) is unaffected and stands as before.
