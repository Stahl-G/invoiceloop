# Verification round record (2026-08-02) — carrying on the dws-derisk six-rounds discipline

The six-rounds discipline: criteria before data, answers before scoring, wrong predictions reported as-is.
This round is the first verification after InvoiceLoop was built, with two parts: the **held-out
experiment** (does the architecture's empirical claim survive unseen documents) and **human acceptance**
(GOAL.md's falsification endpoint). Details live in their own documents; this one is the master record
and index.

## One. Pre-registration (committed before any call)

- Held-out protocol `docs/HELDOUT.md`: H1–H6 pass intervals frozen; list
  `docs/heldout_doc_list.json` (systematic 100 of a pool of 5,331, commit `56d85ed`)
- Acceptance protocol `docs/TESTING.md` + facilitator kit `docs/TESTING_FACILITATOR.md`

## Two. Held-out experiment: H1–H6 all pass, §8 limitation one retired

100 DocILE documents that took no part in any design; all 200 calls 200 OK, zero failures,
**4,758 credits** (estimate ≈5,100, circuit breaker 6,000 never triggered), three keys auto-rotated in
relay. Artifacts under `runs/heldout/`; the verdict is recomputable:
`INVOICELOOP_DWS_DERISK=runs/heldout-workspace python3 scripts/heldout_metrics.py runs/heldout runs/demo`

| # | Quantity | Calibration | Held-out | Interval | Verdict |
|---|---|---|---|---|---|
| H1 | Triage lift | 4.10× | 3.04× | >1.5 | PASS |
| H2 | coverage@46% | 78.1% | 74.3% | >55% | PASS |
| H3 | Review recall | 75.1% | 72.5% | >55% | PASS |
| H4 | Missing-value rate | 26.8% | 27.9% | 10–45% | PASS |
| H5 | citation failure rate | 15.3% | 14.4% | <15% | PASS |
| H6 | Freeze rejection rate | 18.9% | 34.6% | 5–35% | PASS |

**Prediction misses reported as-is** (criteria untouched, wrong predictions written down): the H5
footnote's "calibration roughly 3–5%" was wrong (same-caliber measurement 15.3%; the round-three quantity
was misquoted); H6 hugs the upper bound, the held-out rejection rate nearly double calibration — a wider
document-type distribution and more OCR degradation, to be re-estimated on a corpus change;
H1 decayed (4.10→3.04) but remains 2 times the line.

**Conclusion: triage ordering beating random is no longer a calibration-set anecdote.** §8 limitation one
becomes "executed"; limitation three halved (reproduced within DocILE's full type range, still unknown
beyond DocILE); limitation two stands as before.

## Three. Human acceptance: pass (warm-subject edition)

Record: `docs/TESTING_RESULTS_2026-08-02.md`. All five tasks passed (the T5 veto line avoided).
**The subject was warm** (had read the build reports); all anchors were swapped for uncontaminated
instances; the naïve-subject re-test is still owed, and the facilitator kit remains usable as-is.

This round's most valuable output is the **presentation defect** the subject caught in a single sentence:
rejected rows had no review evidence ("no source image — a human can't understand it"). Fix: matrix rows
gained `cited_span_ids` (where DWS points, regardless of whether the value falls inside), the panel
renders "DWS points here (for review)", and rows with no cited region get a full-page render; full pages
entered the pipeline and the audit bundle. Three tests stand guard.

Two real-human adjudications entered the ledger (zip 27405 correction, Harry Huge value add); M4's
"machine rejects wrong + human corrects" loop ran for the first time; the first audit_bundle.zip was
produced.

## Four. What this round changed (commit order)

1. Review evidence for rejected rows (cited spans + full page), `f6dbe54`
2. Facilitator-kit T2 wording: "count" changed to "recompute with a command", `48cd976`
3. Held-out execution and verdicts, `1aed211`
4. Acceptance record and the first bundle, `ffd728b`

## Five. Still owed

- Naïve-subject re-test (facilitator kit ready)
- Multi-agent adversarial review (gateway failure; only the builder's self-review exists)
- Rotation recommended for the three DWS keys (they passed through a chat channel)
