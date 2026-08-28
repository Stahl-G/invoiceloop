# Four-way baseline comparison (first edition 2026-08-04; rewritten 2026-08-05 per senior adjudication three)

**Question**: when each signal is treated as an "auto-release rule", what shape do silent errors / automation coverage / human load take — and does InvoiceLoop's triage constitute an improvement over raw DWS and simple baselines (review-78 P1; review-81 correction; comparison contract rewritten per senior adjudication three after the 69/83 dual review).

**Recompute**: `python3 scripts/baseline_comparison.py runs/heldout-r3 runs/heldout-workspace`
(zero API, entirely from stored evidence).

## Caliber (read first; charter six)

- **Exploratory, not pre-registered**. What is pre-registered is H1–H6 (docs/HELDOUT.md); this table is an analysis added after review, and its criteria do not carry the H-series' evidentiary meaning.
- **Each system is scored from its own prediction source (2026-08-05 rewrite, senior adjudication three)**: the decision values of the raw systems (full trust / release-only-if-value / confidence / dual-mode) all come from the stored raw responses' `output.data` / `output.metadata`; InvoiceLoop's decision values come from the frozen ledger. Deviations are computed independently from each system's own values, not shared. "Has value" = DWS itself returned a non-empty value, not "passed InvoiceLoop's frozen binding" — the old caliber counted DWS wrong values rejected at freezing as "missing value goes to human" for the other baselines, which amounts to letting the opponents borrow InvoiceLoop's gate.
- **Wrong values and missing values reported separately**: the raw full-trust caliber puts missing values into delivery as well (counting toward its silent errors); the release-only-if-value caliber drives missing values into human review.
- **Confidence ties broken by a fixed (doc_id, field) tie-break**. The old caliber broke ties with queue_idx
  (matrix row order) — that is InvoiceLoop's own triage order; confidence has only 0.95/0.4 as its two main levels and enormous tie groups, and the old "tie" conclusion was partly an artifact of that borrowing
  (see "Differences from the old caliber" below). When a budget cut lands inside a tie group, best/worst/expected are additionally reported.
- **Slot universe** = ground truth exists and it is not a caliber dispute; the dispute criterion reads only the raw understand data itself (an input property shared by all systems). The new universe has 572 slots (old 574; the dispute criterion no longer requires frozen admission, a difference of 2 slots).
- **The InvoiceLoop product itself never auto-releases** — the review queue is adjudicated by humans. This table evaluates the quality of the triage signal under counterfactual auto-release, not a promise about product behavior.
- "Confidence threshold" = understand's field-level confidence ≥ 0.95 plus release only if a value exists.
  Confidence is a coarse-grained discrete grounding score (0.95/0.4 two levels,
  `source=no-logprobs`), **not a calibrated accuracy**.

## All scored fields (572 slots)

| System | Auto-release coverage | Field silent error rate | of which wrong values | of which released missing | Document silent failure rate | Review load | Deviation routing recall |
|---|---|---|---|---|---|---|---|
| raw DWS (full trust) | 100.0% (572/572) | 34.79% | 28.67% | 6.12% | 90.0% (100/100 whole-document release) | 0.0% | 0.0% |
| raw DWS (release only if value) | 93.9% (537/572) | 30.54% | 30.54% | 0.00% | 86.8% (76/100) | 6.1% | 17.6% |
| Confidence threshold (≥0.95) | 93.4% (534/572) | 30.71% | 30.71% | 0.00% | 86.5% (74/100) | 6.6% | 17.6% |
| Dual-mode agreement | 69.6% (398/572) | 18.84% | 18.84% | 0.00% | 77.3% (22/100) | 30.4% | 62.3% |
| InvoiceLoop triage | 58.6% (335/572) | 17.91% | 17.91% | 0.00% | 72.2% (18/100) | 41.4% | 72.4% |

## TIER1 critical fields only (285 slots)

| System | Auto-release coverage | Field silent error rate | of which wrong values | of which released missing | Document silent failure rate | Review load | Deviation routing recall |
|---|---|---|---|---|---|---|---|
| raw DWS (full trust) | 100.0% (285/285) | 26.32% | 18.95% | 7.37% | 50.5% (99/99 whole-document release) | 0.0% | 0.0% |
| raw DWS (release only if value) | 92.6% (264/285) | 20.45% | 20.45% | 0.00% | 41.7% (84/99) | 7.4% | 28.0% |
| Confidence threshold (≥0.95) | 91.6% (261/285) | 20.69% | 20.69% | 0.00% | 41.5% (82/99) | 8.4% | 28.0% |
| Dual-mode agreement | 74.7% (213/285) | 11.27% | 11.27% | 0.00% | 27.3% (55/99) | 25.3% | 68.0% |
| InvoiceLoop triage | 58.6% (167/285) | **8.98%** | 8.98% | 0.00% | **24.3%** (37/99) | 41.4% | **82.4%** |

## Comparison at equal human budget (TIER1 deviation recall, top b% of slots to human)

The confidence systems sort by confidence ascending (fixed doc_id/field tie-break); InvoiceLoop uses the matrix triage order.

| Review budget | Confidence ascending | InvoiceLoop triage order |
|---|---|---|
| 10% | 25.3% | 32.9% |
| 20% | 34.7% | 61.2% |
| 30% | 48.0% | 67.1% |
| 40% | 56.0% | 80.0% |

Full ranges when the budget cut lands inside a confidence tie group (coarse levels → enormous tie groups):

| Budget | Fixed tie-break point estimate | Full range within tie group | Uniform-random expectation |
|---|---|---|---|
| 10% | 25.3% | [24.0%, 33.3%] | 26.0% |
| 20% | 34.7% | [24.0%, 72.0%] | 34.4% |
| 30% | 48.0% | [24.0%, 100.0%] | 42.4% |
| 40% | 56.0% | [24.0%, 100.0%] | 50.8% |

At the 30% budget, 95% CI (bootstrap by document, n=1000, fixed seed):
confidence ascending [35.4%, 58.2%]; InvoiceLoop triage order [58.5%, 76.9%].

## Differences from the old caliber (2026-08-04/05 tables) — all laid out

| Quantity | Old caliber | New caliber | Why it changed |
|---|---|---|---|
| Confidence threshold TIER1 silent errors | 16.10% | 20.69% | The old caliber's confidence_accept required InvoiceLoop frozen admission (gate borrowed); the new caliber looks only at raw value + raw confidence |
| recall@30%: confidence vs triage | 67.4% vs 67.4% ("tie") | 48.0% vs 67.1% | The old caliber broke confidence ties with queue_idx — that is the triage order itself; with a fixed tie-break the gap becomes visible |
| Deviation definition | Shared across all systems (IL caliber) | Per system | Senior adjudication three |

**The correct handling of the old "tie" conclusion**: it was not a bug that got "fixed" but a measurement under the deviation contract; under the new contract the point estimates no longer tie. Note, though, that confidence's within-tie-group ranges are extremely wide
([24%, 100%] at the 30% budget) — the coarse discrete levels mean the true uncertainty of confidence ordering is large, and a difference between single point estimates is not enough to claim a robust win. **The formal paired
comparison is left to the SEALED-1 pre-registered secondary endpoint** (paired recall diff + bootstrap-by-document CI + tie rules frozen in advance). This item remains a claim limit: before
SEALED-1, do not say "the ordering beats confidence".

## How to read this (no exaggeration)

- **At the fixed operating point InvoiceLoop is strongest on the risk side**: TIER1 silent errors 8.98%
  (confidence 20.69%, dual-mode 11.27%), deviation routing recall 82.4% (28.0% / 68.0%).
  But the five points do not dominate one another — InvoiceLoop's review load is also the highest (41.4%).
- **Under a fair contract the confidence-threshold baseline is clearly weaker** (16.10% → 20.69%): its old
  "has value" decision borrowed the frozen binding; standing on its own, it releases more wrong values.
- **The direction of the ordering comparison changed, but its strength is undetermined**: with the fixed tie-break the triage-order point estimate leads
  (67.1% vs 48.0% at 30%, CIs happen not to overlap); yet confidence's within-tie-group
  ranges are extremely wide, so this is not sufficient evidence of a robust win — the SEALED-1 secondary endpoint answers formally.
- **The residual is not zero**: the triage-release band still has 8.98% TIER1 field silent errors — the product
  shape is a "human-adjudicated queue", not an "auto-releaser"; the §8 limitations remain in effect alongside this table.
- **Real human load is reported separately**: docs/R0_BASELINE_2026-08-05.md (61.2% / 100% / 82.3%).

## Not claimed

- Not claimed: that 8.98% is the "true error rate" — it is an observation on the 100-document held-out set under the caliber above;
- Not claimed: that it holds across datasets (distributions beyond DocILE untested, §8 limitation three);
- Not claimed: that the ordering advantage is statistically established — the point estimate leads and the CIs happen not to overlap, but the tie ranges are extremely wide; the formal conclusion awaits the SEALED-1 pre-registered paired analysis;
- Not claimed: that the confidence baseline is useless — it is a legitimate point on the curve, selectable when lower load matters.
