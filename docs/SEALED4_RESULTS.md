# SEALED-4 broadcast sealed results (2026-08-10, one unsealing, numbers recorded as-is)

Protocol and amendment: `docs/SEALED4_PROTOCOL.md`; machine plan and list:
`docs/sealed4_plan.json`, `docs/sealed4_doc_list.json`; pin record:
`docs/SEALED4_PIN_2026-08-10.md`. Unsealing revision:
`8defabf0db512d9240f144b7d59a06f094840ce5`.
Scorer protocol version `sealed4-broadcast-v1`; the qualification-judgment set is the
**strong subset** (amendment A4), with the weak subset listed separately, recorded as-is.

## Conclusions first

1. **SEALED-4 qualification passes (broadcast scope, strong subset)**: primary arm
   HAR-0021 versus conservative baseline HAR-0001, human queue **433/680 (63.7%) →
   321/680 (47.2%)**, 112 fewer slots (−16.5pp); both silent-error classes do not rise
   (P1 ✓), the queue drops (P2 ✓), H1–H7 all pass.
2. **True-silent absences 0**: of the primary arm's 149 auto_absent slots, 2 have
   non-empty truth, but all fall under the pre-registered truth-caliber rules
   (truth-caliber-v1) — 1 case T2(ii) (alias-item date), 1 case T1 (single-total slot
   assignment), recorded as-is as caliber disputes, not entering the true-silent column.
   `silent_wrong` 31 → 31 (strong), 35 → 35 (full set), no rise.
3. **Prediction deviation recorded as-is**: amendment A4.1 predicted the strong-subset
   queue down 4–12pp, true-silent 0, caliber disputes 0–3 cases. Actual **−16.5pp,
   beyond the top of the predicted interval**; true-silent 0 ✓, disputes 2 ✓. The
   load-reduction benefit is better than predicted; no explanation offered, recorded
   as-is.
4. **H7 first verify FAIL → fix → re-verify PASS**: the delivery-side bundle verifier
   omitted `absence_probes`, so AV-rule slot routing recomputation mismatched across the
   board (see §5). The fix is not in the frozen surface, batch numbers unchanged, the
   whole process recorded as-is.
5. **Qualification boundary**: this qualification covers only the **broadcast subpool**
   (broadcast-pilot-v1 scope, strong subset). Qualification on the general DocILE pool
   is not established by this batch.

## 1. Execution and sealing

- drand round **6363898** (committed at commit `6a0db9f`; latest round at commitment
  6363858); seed
  `184789911618e785e004bde36a5b02b6bb94e3eeae82d960d593c7fdfb6336b4`.
- List of 100 documents = **68 strong / 32 weak**;
  `docs/sealed4_doc_list.json` sha256
  `e48b5ffae058444ab201467ade62e9f24a30cdfdaf22f568a46d586d913785a8`.
  The old all-pool list is voided, kept on disk at
  `docs/sealed4_doc_list_voided_fullpool.json`.
- Pin commit `8defabf` (#6): primary arm **HAR-0021**, policy file sha
  `bed2a209…`, policy_digest
  `25a1713278eae03d9132f0b16bee830fa716c8fb03752bffc4bf4a0dd08d8c00`;
  baseline **HAR-0001**; three arms B0 / P / P-REPEAT; 25 frozen_files.
- Extraction (#7a): completed in two passes, 200/200 status 200, total spend
  **5,304 credits** (2877 + 2427; the first key ran out mid-run and a 5th key was added
  to resume — facts recorded as-is). Workspace `runs/sealed4-v2-workspace`.
- Unsealing (#7b): `scripts/sealed4_batch.py --expected-head 8defabf…`
  executed once; all three arms passed the three batch invariants;
  `batch_complete.json` sha256
  `b30d3a8941a554db5ee0a013682c91bae2df99ba9c68524f17fb91713be3c988`.
- metrics sha256:
  `7eebf10a1b3dbeda9b92354a10fe4458a1908436f7af84e72cd952ae474ec115`
  (re-scored version after the H7 fix; the first-verify FAIL version
  `c20bc5772d8837d66433fdcce8b4577f86c7d2591763484c47b224e07b9e9006`
  was deleted, see §5).
- Primary-arm field ledger: 1246 claims, in-ledger sha256
  `5b5c0c3d0780409ebea8e8ea1af49b983d84f3d0264fdba42368d0ef9ae69e93`.
- Primary-arm audit bundle: 417 members, sha256
  `48b89f690c6dab77223bb32cfb930915dd649f1efb6558ab01332e13b24b2f25`;
  members/snapshot/semantics all pass; empty adjudications so binding=None; no DWS
  signature sealing (does not affect the four-layer verify of pre-registered H7).

## 2. Primary endpoints H1–H7 (P = HAR-0021, judged on the strong subset)

| # | Quantity | **SEALED-4 strong** | Interval | Verdict |
|---|---|---|---|---|
| H1 | triage lift | **5.08×** | > 1.5 | **PASS** |
| H2 | coverage@46% | **79.11%** | > 55% | **PASS** |
| H3 | legacy requires-caliber review recall | **80.38%** | > 55% | **PASS** |
| H4 | extraction_present missing rate | **12.79%** | 10–45% | **PASS** |
| H5 | citation failure rate on the decidable subset | **12.89%** | < 15% | **PASS** |
| H6 | understand frozen rejection rate | **30.28%** | 5–35% | **PASS** |
| H7 | run closed loop | **bundle verify PASS** (re-verified after the fix, see §5) | run + verify | **PASS** |

H5 falls back inside the interval on a sealed batch for the first time (SEALED-3 was
15.35%, recorded as-is as FAIL); this is an observation on the broadcast subpool — it is
not claimed that citation is fixed on the general pool.

## 3. Workload and safety results (strong / weak / full set)

`human_queue` is the external-facing human-queue measure: route is not
auto_accept/auto_absent. `silent_absent` is the original measure (counted whenever truth
is non-empty); `silent_absent_true` is counted after deducting caliber disputes per
truth-caliber-v1.

| Subset | arm | human_queue | auto_absent | silent_absent | caliber disputes | true-silent | silent_wrong |
|---|---:|---:|---:|---:|---:|---:|---:|
| **strong (680)** | B0 HAR-0001 | 433 (63.7%) | 0 | 0 | 0 | 0 | 31/210 |
| **strong (680)** | **P HAR-0021** | **321 (47.2%)** | 112 | 1 | 1 (T2(ii)) | **0** | 31/210 |
| weak (320) | B0 HAR-0001 | 186 (58.1%) | 0 | 0 | 0 | 0 | 4/114 |
| weak (320) | P HAR-0021 | 149 (46.6%) | 37 | 1 | 1 (T1) | 0 | 4/114 |
| full set (1000) | B0 HAR-0001 | 619 (61.9%) | 0 | 0 | 0 | 0 | 35/324 |
| full set (1000) | P HAR-0021 | 470 (47.0%) | 149 | 2 | 2 | 0 | 35/324 |

The exact-repeat arm P-REPEAT has all paired differences of 0 versus P; the
determinism control passes.

### Paired differences (P − B0, qualification comparison)

| Comparison | Δ human_queue | Δ silent_absent (raw) | Δ true-silent | Δ silent_wrong | Conclusion |
|---|---:|---:|---:|---:|---|
| strong (judgment set) | **−112 (−16.5pp)** | +1 | **0** | 0 | **P1 ✓ P2 ✓** |
| weak (recorded as-is) | −37 (−11.5pp) | +1 | 0 | 0 | listed separately |
| full set (recorded as-is) | −149 (−14.9pp) | +2 | 0 | 0 | listed separately |

## 4. The two caliber-dispute slots (recorded as-is, neither zeroed nor hidden)

| doc | field | DocILE truth | caliber rule | subset |
|---|---|---|---|---|
| `4c355e84b7524a3d8f573bb9` | due_date | `9/22/2021` | T2(ii): the date appears in the page OCR and a ±12-word window contains one of the frozen word set (transaction/donation/authorization/adjustment) — alias-item date | strong |
| `961a7ea0624341f2b83544da` | total_net | `$72,000.00` | T1: normalizes to the same amount as truth[amount_due] — single-total slot assignment | weak |

Both cases were split out of the true-silent column per amendment A3 and listed
separately, recorded as-is. They remain **disputes**, not correct calls; kept explicit
per Charter Five and brought into the human-adjudication field of view.

## 5. H7 first verify FAIL → localize → fix → re-verify PASS (recorded as-is)

- **First verify FAIL**: the first bundle verify after unsealing reported hundreds of
  "routing_report slot X routing does not match policy recomputation" errors.
- **Root cause**: `adjudicate.py::verify_bundle`, when recomputing routes, calls
  `derive_document_records` without passing `absence_probes` (the probes live in
  gate_report.json; runtime matrix.py passes them) → every AV-rule slot recomputes to
  absence_evidence=not_measured → all routings mismatch.
- **Fix**: commit `fbfbe7f`, the verifier passes the probes + a regression test
  (`test_absence_evidenced_routes_recompute_from_bundle`). `adjudicate.py` is **not
  among the 25 frozen_files** — the bundle is a delivery-side check built after
  unsealing, not part of the batch computation; policy/gates/normalization/routing/
  scorer/baseline/list/seed all untouched, batch numbers unchanged.
- **Re-verify PASS**: rebuild the bundle (sha `48b89f…`) → re-score (metrics sha
  `7eebf1…`) → H7 verify ok, failures=[].

## 6. Qualification, candidates, and follow-up boundaries

- **HAR-0021: SEALED-4 qualification = PASS (strong subset, broadcast scope)**.
- Qualification semantics per amendment A4: say only "on a 100-document sample of the
  broadcast subpool unseen during development, HAR-0021 reduces load within the strong
  subset with no rise in true-silent absences". **No extension to the general DocILE
  pool, no extension to the weak subset** (weak is listed separately, recorded as-is;
  it is not the judgment set).
- **Human adjudication accuracy: NOT MEASURED**; remains a separate human-arm endpoint.
- sealed4-100 is not merged into the exposure manifest; that is a setup action for
  SEALED-5 — merging it now would break amendment A1's digest regression test.
- This batch has completed its one-shot measurement of revision `8defabf`. Any rule
  change inspired by these results may only use development/regression data; the next
  unseen qualification is a freshly drawn SEALED-5.

The strongest publicly statable sentence from this run: **on SEALED-4, a 100-document
broadcast-subpool sample unseen during development, within the strong judgment set
(68 documents, 680 slots) HAR-0021 takes the human queue from 63.7% down to 47.2%
(−16.5pp), with neither true-silent absences nor silent_wrong rising, and H1–H7 all
passing; the 2 auto_absent slots with non-empty truth are all pre-registered caliber
disputes, listed separately, recorded as-is.**
