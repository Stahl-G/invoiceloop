# SEALED-1 sealed evaluation results (executed 2026-08-05, completed in one pass, numbers recorded as-is)

Protocol: `docs/SEALED1_PROTOCOL.md` (criteria, seed commitment, both arms, and
endpoints all frozen before results).
List: `docs/sealed1_doc_list.json` (drand round 6350076, 2026-08-05T12:35Z;
the commitment commit 979fd37 precedes the reveal; the list commit f3594ce precedes
any DWS call; independent recomputation of `heldout.sealed_list(seed)` matches the
list document by document, with zero overlap with the 260-document exposure
manifest and the old held-out 100).

## Execution record

- 200 DWS calls (understand + agentic × 100 documents): **all 200 OK, zero
  failures**; spent **4,953 credits** (estimate ≈4,758; the 6,000 circuit-breaker
  line was not triggered); 4 keys.
- Primary-arm run: `runs/sealed1` (HAR-0001); second arm: same frozen evidence +
  the matrix rebuilt with only the policy swapped (`runs/sealed1-har2`; the
  frozen-replay ledger sha matches the primary arm bit for bit).
- evidence bundle: `runs/sealed1-evidence.zip` (22MB, raw + both arms' artifacts +
  list + summary) sha256 =
  `fca5f1e209373bb13fc9c31212e05136748b43429db2d937ef25c0b7750dc0ff`.
- **DWS signature sealing (2026-08-06)**: `runs/sealed1/audit_bundle.sealed.zip`
  sha256 = `ad6a698cb6e45ba66f4063b2cf760440b13fa335cd896b64fed6f2b6d4f33132`,
  CAdES b-lt signature (signer `CN=Nutrient DWS API Test Document Signer`, trusted
  timestamp inside the signature). verify passes all five layers
  (members/snapshot/semantics/signature; empty adjudication, hence binding None).
  **The honesty boundary is unchanged**: what the signature pins down is "this
  manifest digest passed through DWS signing at time T and was not altered"; the
  signing principal is Nutrient's test signing certificate, not this project —
  "who built the bundle" is still anchored out-of-band.

## Primary endpoint: H1–H7 (primary arm HAR-0001; pass intervals carry over the old HELDOUT preregistration)

| # | Quantity | Calibration | Old held-out | **SEALED-1** | Interval | Verdict |
|---|---|---|---|---|---|---|
| H1 | triage lift | 4.10× | 3.04× | **4.03×** | > 1.5 | **PASS** |
| H2 | coverage@46% | 78.1% | 74.3% | **77.3%** | > 55% | **PASS** |
| H3 | review recall | 75.1% | 72.5% | **77.7%** | > 55% | **PASS** |
| H4 | missing rate | 26.8% | 27.9% | **29.3%** | 10–45% | **PASS** |
| H5 | citation failure rate | 15.3% | 14.4% | **15.3%** | < 15% | **FAIL (recorded as-is)** |
| H6 | frozen rejection rate | 18.9% | 34.6% | **36.6%** | 5–35% | **FAIL (recorded as-is)** |
| H7 | operational closed loop | — | — | bundle 416 members, verify passes all four layers (empty adjudication → binding=None) | — | **PASS** |

(587 scored slots, 256 discrepancies; head-of-queue discrepancy rate 70.0% vs tail
17.3%.)

**Verdict: H1 meets the bar (4.03×, 2.7 times the line) → overall not a failure;
H5/H6 miss the bar, written into the limitations list per protocol, without
adjusting criteria and retesting:**

- **H5 (15.3% vs line 15%)**: over the line by 0.3pp. Same magnitude as the old
  held-out set (14.4%), not a new regression; the failure rate on the
  citation-decidable subset has long hovered around 14–15%, and this line's basis
  itself came from a mistakenly written "calibration ~3–5%" back then (the old
  protocol already carries the erratum recorded as-is). Honest conclusion: the
  citation gate's decidability-subset failure rate is about 15% — a known boundary,
  not a new finding this time.
- **H6 (36.6% vs upper bound 35%)**: two consecutive batches have stood at the
  bound (old: 34.6%). The direction-consistent explanation is unchanged: frozen
  rejections are driven mainly by binding failures on OCR-degraded documents and
  correlate with the document-type distribution (the calibration set is all US
  radio-advertising invoices, while the two held-out batches have a broader
  distribution). **This means "frozen rejection rate ≈35%" should be treated as the
  norm under this corpus's full type distribution, not as an anomaly**; it directly
  caps the ceiling on automatic release and is the real work surface for the
  improvement layer.
- Distribution comparison: H1 is actually stronger than the old held-out set
  (4.03 vs 3.04), and H2/H3 rebound to near-calibration levels — the previous
  batch's decay did not continue; ranking ability reproduced on a second unseen
  batch.

## Second arm (HAR-0002, user decision: remove mandatory manual confirmation for non-conflicting TIER1; preregistered §3.5)

| Quantity | HAR-0001 | HAR-0002 |
|---|---|---|
| field-review workload (requires) | 63.3% | 64.2% (+0.9pp, the cost of 5% QA sampling) |
| **release-decision workload** | **82.9%** | **64.2%** (−18.7pp) |
| document touch rate | 100/100 | 100/100 (recorded truthfully: every document still has at least one slot requiring review) |
| TIER1 silent-error rate (counterfactual) | 9.62% | 9.46% |
| TIER1 discrepancy-routing recall | 83.3% | 84.4% |

Second-arm H1–H6: H1 4.13× / H2 77.0% / H3 78.1% (H4–H6 are routing-independent,
identical). **No safety degradation observed (paired on the same evidence), and
workload down as expected; a 100% document touch rate is the next improvement
target, not this round's goal.**

## Secondary endpoint: ranking comparison (preregistered paired analysis, TIER1)

| Review budget | Ascending confidence | Triage order | paired diff (95% CI, per-document bootstrap n=1000) |
|---|---|---|---|
| 10% | 29.4% | 31.1% | +1.7pp [−3.1, +17.9] spans zero |
| 20% | 31.8% | 55.6% | **+23.8pp [+10.7, +30.6]** |
| 30% | 41.2% | 63.3% | **+22.2pp [+10.8, +35.2]** |
| 40% | 49.4% | 77.8% | **+28.4pp [+15.0, +43.2]** |

The confidence tie-group span is still extremely wide (at the 30% budget,
[29.4%, 98.8%], against a uniform-random expectation of 45.7%). **Under the
protocol's measure it may be said: under the preregistered fixed tie-break, the
triage order's paired CI lower bound is > 0 across the 20–40% budget range.** But
two caveats must accompany it: (a) this is the fixed-tie-break measure and does not
hold for "the most favorable arrangement within a tie group"; (b) in this batch the
confidence-threshold baseline coincides exactly with "release only when a value is
present" (every non-empty value DWS returned this batch was in the 0.95 band) —
confidence has almost no discriminative power in this batch, so this opponent is on
the weak side.

## Comparison with the old held-out set (why this batch replicates more cleanly)

The old held-out set (3.04×) had decayed relative to calibration (4.10×); SEALED-1
(4.03×) returns to calibration level. The most likely explanation for the
difference: the old batch's list was committed first, but its cases later entered
development (C3/C8); this batch is mechanically sealed. Reading the two batches
together: ranking ability is stable at 3–4×, not single-batch luck.

## Limitations list (additions/updates in this batch)

1. H5/H6 missed their lines — recorded as-is, not retired, no criteria adjusted;
2. Document touch rate is 100% in both arms — "whole-document zero-touch release"
   has not been achieved under this corpus distribution;
3. The confidence opponent is weak in this batch (all non-empty values in the 0.95
   band); the external validity of the ranking-advantage conclusion is limited;
4. This batch is automatically demoted to a regression/evolution set — any change
   inspired by it from now on goes into the next version; formal conclusions wait
   for the next sealed batch.
