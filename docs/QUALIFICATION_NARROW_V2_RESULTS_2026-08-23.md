# QUALIFICATION_NARROW_V2_2026-08-23 results (a valid negative qualification round, n=200)

Status: `valid / qualification FAIL / promotion DENIED`

Protocol: `docs/QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md`

Authoritative machine ruling:
`docs/evidence/qual-narrow-v2-2026-08-23/decision/qualification_decision.json`

## 0. Conclusion up front

Integrity passed this round, the workflow effect reproduced, and **the safety
product capability failed**.

- HAR-0023's routing-time zero-touch on 200 new, never-exposed DocILE documents
  was **21/200 = 10.5% (95% Wilson CI 7.0–15.5)**, inside the pre-registered
  5–20% band.
- Those 21 never-opened documents carry 63 payment-gate slots:
  `silent_absent_true=0`, but **6 `silent_wrong`**, plus **3 auto-accept slots
  that could not be scored**.
- Two of protocol §6 III's three zero-tolerance conditions therefore fail.
  HAR-0023 is **not promoted**; the default census stays.

This is a valid negative result — not a contaminated round, and not "almost
passed." The workflow routing property holds; it cannot offset a safety
failure in exactly the subset the claim points at.

## 1. Integrity

| Item | Deterministic result |
|---|---:|
| Frozen list | 200 documents; intersection with v1 / SEALED-4 = 0 |
| DWS calls | 400/400 |
| HTTP 200 | 400 |
| failed / skipped | 0 / 0 |
| DWS credits | 10,374 |
| raw tree SHA-256 | `204727aacb50952123b85729c55cabc85f05da4a4ca0cf507c5fc5089e16d74f` |
| Three-arm matrices | A/B/D at 200 × 10 = 2,000 unique slots each |
| Missing components | 0 |
| Stale-metric drift | 0 |
| Protocol / identity contamination | 0 |

Extraction identity is pinned at `34bb17e676bd5eb5dfe227cdabf761891f79955b`;
the three arms and the safety scorer share pin
`897a47a1f18bba024ef89b14885abd3561e1f0ee`; the final decider is pinned at
`569794fc1be53be294075d816055bd75183f4bab`. The decider verifies
`MANIFEST.sha256` stage by stage and rejects missing components, extra
members, hash drift, differing code revisions, or incomplete matrices.

## 2. Pre-registered predictions vs. measurements

| # | Prediction | Measured | Verdict |
|---|---|---|---|
| P1 | A zero-touch = 0/200 | 0/200 | **held** |
| P2 | D zero-touch 5–20% | 21/200 = **10.5%** | **held** |
| P3 | C zero-touch ≥ D | 23 ≥ 21 | **held** |
| P4 | D whole-arm `silent_wrong` ≤ B | 113 ≤ 116 | **held** |
| P5 | D zero-touch `silent_wrong` 8–18, wrong documents 6–14 | **6** wrong values / 6 wrong documents | **failed**: slot count below the floor; document count in range |
| P6 | D zero-touch unscoreable auto-accept slots 0–6 | 3 | **held** |
| P7 | All three payment gates fully automatic 15–19% | 32/200 = **16.0%** | **held** |

P5's failure is recorded as-is. The actual wrong-value count came in below the
development-prior prediction band, but the safety promotion line is **0**, not
8 — so "fewer than expected" is still a deterministic FAIL.

## 3. Four arms × strata

Strata: strong 107 / weak 60 / none 33. C is the payment-gate projection of
B's routing, not a fourth run.

| Arm | Stratum | Docs | Zero-touch | Released unresolved slots | QA probes | Human-queue slots | Whole-arm true-silent | Whole-arm wrong values |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A HAR-0001 | strong | 107 | 0 (0.0%) | 625 | 0 | 625 | 0 | 77 |
| A HAR-0001 | weak | 60 | 0 (0.0%) | 403 | 0 | 403 | 0 | 23 |
| A HAR-0001 | none | 33 | 0 (0.0%) | 217 | 0 | 217 | 0 | 16 |
| A HAR-0001 | **ALL** | 200 | **0 (0.0%)** | 1245 | 0 | 1245 | 0 | 116 |
| B HAR-0021 | strong | 107 | 2 (1.9%) | 482 | 41 | 482 | 0 | 77 |
| B HAR-0021 | weak | 60 | 0 (0.0%) | 338 | 23 | 338 | 3 | 23 |
| B HAR-0021 | none | 33 | 0 (0.0%) | 181 | 19 | 181 | 1 | 16 |
| B HAR-0021 | **ALL** | 200 | **2 (1.0%)** | 1001 | 83 | 1001 | 4 | 116 |
| C B+payment | strong | 107 | 14 (13.1%) | 133 | 41 | 482 | 0 | 77 |
| C B+payment | weak | 60 | 7 (11.7%) | 96 | 23 | 338 | 3 | 23 |
| C B+payment | none | 33 | 2 (6.1%) | 53 | 19 | 181 | 1 | 16 |
| C B+payment | **ALL** | 200 | **23 (11.5%)** | 282 | 83 | 1001 | 4 | 116 |
| D HAR-0023 | strong | 107 | 13 (12.1%) | 136 | 54 | 495 | 0 | 74 |
| D HAR-0023 | weak | 60 | 6 (10.0%) | 100 | 27 | 342 | 3 | 23 |
| D HAR-0023 | none | 33 | 2 (6.1%) | 53 | 21 | 183 | 1 | 16 |
| D HAR-0023 | **ALL** | 200 | **21 (10.5%)** | 289 | 102 | 1020 | 4 | 113 |

D carries 19 more QA probes than C and 2 fewer zero-touch documents. D's
zero-touch across strong → weak → none is 12.1% → 10.0% → 6.1%, consistent in
direction with the broadcast OCR-support mechanism; it remains a single-corpus,
single-round observation.

## 4. The three safety promotion gates

Looking only at the three payment fields of D's 21 documents that were **never
opened at all**:

| Safety condition | Required | Measured | Verdict |
|---|---:|---:|---|
| `silent_absent_true` | 0 | 0 | **pass** |
| `silent_wrong` | 0 | **6** | **fail** |
| `unscored_auto_accept_slots` | 0 | **3** | **fail** |

The 6 wrong values spread over 6 documents: `amount_due` 3, `seller_name` 3.
Three further documents each have one unscoreable `invoice_number` auto-accept
slot. Unsocreable did not vanish from the denominator, nor was it counted as
"correct"; per the protocol it blocks promotion directly.

Whole-arm P4's 113 ≤ 116 only says D did not raise the wrong-value count on
ALL automatic slots above B. It cannot substitute for this zero-touch
risk-concentrated subset, still less dilute 6 wrong values into a product pass.

## 5. Three-layer ruling

| Layer | Result | Consequence |
|---|---|---|
| I. Round integrity | **PASS** | this round's numbers are valid qualification evidence |
| II. Workflow effect reproduction | **PASS** | permitted to report this round's routing-time zero-touch of 10.5% |
| III. Safety product capability | **FAIL** | promotion of HAR-0023 forbidden |
| Overall ruling | **QUALIFICATION FAIL** | `promotion: denied`; default census unchanged |

Machine reason codes: `zero_touch_silent_wrong_nonzero`,
`zero_touch_unscored_auto_accept_nonzero`.

## 6. Allowed and forbidden public phrasings

Allowed:

> On 200 new, never-exposed DocILE documents that passed the integrity gate,
> HAR-0023 measured routing-time zero-touch of 21/200 (10.5%, 95% Wilson CI
> 7.0–15.5). Its zero-touch payment subset contained 6 wrong values and 3
> unscoreable auto-accept slots; safety qualification therefore failed and
> HAR-0023 was not promoted.

Forbidden:

- "the narrow release is safe" or "product capability passed";
- "extraction accuracy improved";
- presenting 10.5% as a human-time saving rate;
- transferring this round to other corpora, vendors, or truth conventions.

The three qualifiers stay attached at all times: single corpus DocILE, single
vendor Nutrient DWS, single truth convention (DocILE annotations +
truth-caliber-v1).

## 7. Evidence index

- Frozen plan: `docs/evidence/qual-narrow-v2-2026-08-23/plan/`
- Extraction audit: `docs/evidence/qual-narrow-v2-2026-08-23/extract/`
- Four-arm metrics: `docs/evidence/qual-narrow-v2-2026-08-23/arms/`
- Supplementary safety audit: `docs/evidence/qual-narrow-v2-2026-08-23/analysis-audit/`
- Three-arm originals: `source-har-0001/`, `source-har-0021/`, `source-har-0023/`
- Authoritative ruling: `docs/evidence/qual-narrow-v2-2026-08-23/decision/`

The ADK human walk may continue as independent accountability evidence, but it
cannot rewrite this page's automatic-release FAIL.
