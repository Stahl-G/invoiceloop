# Document-touch four-arm results (2026-08-18, development set, zero API)

No qualification semantics. No claim that extraction got more accurate. This
round is spliced neither onto R1 S1 nor onto HITL-narrow 4/20. Zero-touch ≠
extraction correct. Residuals still carry the three §8 qualifiers of
`ARCHITECTURE.md`.

Protocol: `docs/DOCTOUCH_PREREG_2026-08-18.md` (commit `2f4a31c`, 15:55:30,
earlier than any result). Instrument: `scripts/doctouch_arms.py` (commit
`c0b0e49`). Metrics-file mtime: 2026-08-18 16:02:40. The ordering is
checkable.

## 0. What this round can and cannot say

The narrow contract lowers must-open invoices from **100% to about 89%** — a
real drop, but not "most invoices need no opening". Pre-registration §5 said:
if D lands in 20–35%, the conclusion must use the "about seven in ten still
need opening" sentence; measured **10.8%** did not even enter that interval,
so **stretching "about seven in ten" over "about nine in ten" is forbidden**.

This round is **not** a qualification result. All 660 documents are in
`development_exposure_manifest.json`, 400 of them on sealed lists.
Non-broadcast documents neither exposed nor sealed: 0.

## 1. The five pre-registered predictions (misses recorded as-is)

| Prediction | Measured | |
|---|---|---|
| A, B zero-touch ≈ 0% | A 0/660; B 6/660 = 0.9% (strong 6) | roughly right |
| D lands in **20–35%** | **71/660 = 10.8%** (strong 11.0%) | **wrong, too low** |
| D beats C, difference < 10pp | D is **worse than** C (10.8% vs 12.3%) | **direction flipped** |
| none zero-touch below strong | D: none **13.3%** > strong **11.0%** | **direction flipped** |
| none true-silent will rise | 1 per stratum, 3 total; identical for B/C/D | **not unique to none** |

## 2. Four arms × three strata (primary endpoint = document zero-touch)

| Arm | Gate | `release_tier1_explicit` | strong 372 | weak 198 | none 90 | ALL 660 |
|---|---|---|---|---|---|---|
| A HAR-0001 | census 10 | true | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| B HAR-0021 | census 10 | true | 6 (1.6%) | 0 (0.0%) | 0 (0.0%) | **6 (0.9%)** |
| C HAR-0021 projected payment 3 | payment 3 | true | 49 (13.2%) | 19 (9.6%) | 13 (14.4%) | **81 (12.3%)** |
| D HAR-0023 | payment 3 | **false** | 41 (11.0%) | 18 (9.1%) | 12 (13.3%) | **71 (10.8%)** |

The protocol requires the three strata reported separately, not merged into
one. ALL is a total only, not treated as a fourth stratum.

Touch composition (ALL):

| Arm | Unresolved contract slots | QA probe slots | Human-queue slots | True-silent | Caliber disputes | silent_wrong / value_hits |
|---|---|---|---|---|---|---|
| A | 3988 | 0 | 3988 | 0 | 0 | 359/2224 |
| B | 3148 | 218 | 3148 | 3 | 9 | 359/2224 |
| C | 854 | 218 | 3148 | 3 | 9 | 359/2224 |
| D | 889 | 287 | 3217 | 3 | 9 | 357/2175 |

The C-vs-D difference = the TIER1 5% QA introduced by
`release_tier1_explicit: false` (probe slots 218→287). **D being worse than C
on the document caliber is not noise**: the shipping flag carries it in order
"not to fake human accepts", not for performance. True-silent and caliber
disputes did not rise.

Stratum-level detail in `docs/evidence/doctouch_2026-08-18/doctouch_metrics.json`.

## 3. Mechanism: a three-gate conjunction, not a pipeline failure

Automation rates (`auto_accept` or `auto_absent`) of HAR-0023's three gates:

| Field | Automated | Role in the independent conjunction |
|---|---|---|
| `invoice_number` | 400/660 = **60.6%** | |
| `seller_name` | 383/660 = **58.0%** | |
| `amount_due` | 308/660 = **46.7%** | the ceiling |

0.606 × 0.580 × 0.467 = **16.4%**. On disk, all three gates automated for
**113/660 = 17.1%**; the conjunction holds. QA probes pull away another
batch, landing at 10.8%.

"Probes don't count as opening" = **126/660 = 19.1%** (including the 35 CLEAN
gate slots pulled into review by probes). Sharing the value 126 with
"invoice_number always automated" is a coincidence; two rows with the same
value do not contradict each other.

Opening shapes (mutually exclusive, summing to 660):

| Shape | Documents |
|---|---|
| `amount_due` only | 141 |
| `amount_due` + `seller_name` | 79 |
| all three gates need humans | 79 |
| `invoice_number` only | 76 |
| **zero-touch** | **71** |
| `seller_name` only | 67 |
| `amount_due` + `invoice_number` | 53 |
| `invoice_number` + `seller_name` | 52 |
| non-gate QA probes only | 42 |

`amount_due` appears on **352/660 (53.3%)** of the documents that must be
opened. The field-level automation rate 3383/6600 = 51.3% may appear only in
the lab index, not as a product KPI.

## 4. Why documents open: both calibers recorded (erratum)

The adjudication bundle wrote arithmetic gate for **131** of `amount_due`'s
352 documents and dual-mode disagreement for **178** of `seller_name`'s 277
(64%). After recomputation:

### `amount_due` (352 documents in review)

| Caliber | Count | Note |
|---|---|---|
| Routing **first-choice** reason code `GATE_FAIL:arithmetic_consistency` | **131** | matches the adjudication bundle, reproducible |
| `gate_report` `arithmetic_consistency == fail` | **140** | all fall inside these 352; another 79 slots `unavailable` (the identity was not evaluated) |
| the 106 in some adjudication | **not reproducible** | not adopted |

The difference of 9 documents: the gate already `fail`, but routing's
first-choice reason code is not arithmetic because `UNSUPPORTED` got there
first. Routing is if/elif; among hard conditions `slot_blocking` /
`unsupported` precede `GATE_FAIL:*`.

The remaining first-choice reason codes: dual-mode disagreement 53,
UNSUPPORTED 51, SLOT_BLOCKING 50, un-citeable references 43, CLEAN+QA 21,
field_wellformed 3.

### `seller_name` (277 documents in review)

| Caliber | Count | Share of 277 |
|---|---|---|
| Routing first-choice `GATE_FAIL:cross_mode_agreement` | **178** | 64% |
| `gate_report` `cross_mode_agreement == fail` | **242** | **87%** |

The bundle's 64% is the first-choice reason code and holds; the gate caliber
is heavier. The 64-document difference was preempted by `UNSUPPORTED` (47) or
`SLOT_BLOCKING` (17).

The breakdown is frozen in `docs/evidence/doctouch_2026-08-18/open_reasons.json`.

## 5. Counterfactuals (priced, not proposed)

| If | Zero-touch |
|---|---|
| current caliber (QA counts as opening) | 71 (10.8%) |
| probes don't count as opening | 126 (19.1%) |
| `seller_name` always automated | 122 (18.5%) |
| `invoice_number` always automated | 126 (19.1%) |
| `amount_due` always automated | 170 (25.8%) |
| amount_due always automated and QA ignored | 263 (39.8%) |

Even with `amount_due` always automated, we only enter the 20–35% interval
the pre-registration wrote down. Turning off the arithmetic gate would turn
the caliber disputes named in charter five into silent posting; this round
changes no gate.

## 6. Product adjudication (2026-08-18, the intersection of two independent adjudications)

The main KPI stays document zero-touch. `amount_due` / `seller_name` keep
gating payment; QA probes still count as opening;
`release_tier1_explicit: false` stays (D<C recorded as-is). HAR-0023 is
**not promoted** to product active. The default harness remains the census
(HAR-0021); `payment_required_v1` is an optional payment profile / HITL
workbench configuration.

Externally, only this one numbers sentence is permitted, and it must carry
the full qualifiers:

> On the 2026-08-18 zero-API development run (n=660, all previously exposed; not a qualification result), HAR-0023 left 10.8% of documents untouched; about 89% still required opening.

Until an unexposed qualification set produces numbers under the same gate
definition, "narrow release reduces opened documents" may not be written up
as a product capability.

The originally planned human-time second round will not run. The "caliber
dispute / true arithmetic error" split within arithmetic-gate failures cannot
be measured by routing; if it is ever to be measured, a small new protocol
must be written and frozen first — not a full HITL round, and splicing onto
R1 or onto 71/660 is forbidden.

## 7. Recompute

```bash
python3 scripts/doctouch_arms.py --out runs/doctouch-2026-08-18
```

Zero API. One `pipeline.run` each for A/B/D (gates consume policy; you cannot
run once and recompute under a different policy). C is B's routing projected
onto the three payment fields, not rerun.

Policy-file sha256:

| Arm | File | sha256 |
|---|---|---|
| A HAR-0001 | `harness._builtin_policy()` | (digest `395c5650…cf97`) |
| B HAR-0021 | `docs/evidence/absence_v3_2026-08-10/HAR-0021.routing_policy.json` | `bed2a20912c59fd5355873448d2d0f6c5a18545c25e64404d59ddb83b776bbc4` |
| D HAR-0023 | `docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json` | `3bb39cb83c3d0785f5b0c487fab6d2fe28823dce76df05557069cca72fc3fbc8` |

Routing digests: HAR-0021 `25a17132…8c00`; HAR-0023 `001016d6…f112`.
