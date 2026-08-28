# QUALIFICATION_NARROW_2026-08-22 Results (contaminated, qualification promotion revoked, n=200)

> **2026-08-23 supersession:** This round triggered protocol §7's dirty-arm clause; its status is
> `contaminated / blocking`. The original numbers are retained as exploratory measurements; this page's earlier "no blocking" and
> "all four product-capability gates passed" claims are hereby revoked. Authoritative record:
> `docs/QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md`.

Protocol: `docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md` (frozen at `b45f983`, before any API call; modified at `1afe7da` during extraction, frozen bytes restored after `68a2701`)
Run log: `docs/QUALIFICATION_NARROW_LOG_2026-08-23.md`
Data: `docs/evidence/qual-narrow-2026-08-22/arms/doctouch_metrics.json`
Supplementary audit: `docs/evidence/qual-narrow-2026-08-22/analysis-audit-v2/doctouch_audit.v2.json`
Recompute: zero API. All four arms are projected from stored responses; `--doc-list` locks down these 200 documents.

## 0. Blocking status

**Blocked.** The protocol body was modified during extraction, hitting the frozen protocol §7's explicit dirty-arm condition. Restoring the file to its original bytes
cannot undo the contamination transition that has already taken place. This round may not serve as qualification or product-promotion evidence.

The extraction itself is complete: the aggregate audit confirms 200 documents, 400/400 calls, all http 200, 10,491 credits;
each of the four arms tested the full 200 documents, with 0 missing items. These guarantee the descriptive numbers are recomputable, but they cannot override the contamination block.

## 1. How this round differs from the 08-18 round

| | doctouch 2026-08-18 | This round |
|---|---|---|
| n | 660 | 200 |
| Exposure status | **All exposed during development** | **Not a single one touched** |
| Sampling | Everything on disk with a dual-mode response enters | Min-hash take of 200 from the 4,831-document unexposed pool |
| Gate definition | Same | Same |
| Metrics | Same | Same |
| Arm D zero-touch | 10.8% | **12.5%** |

The 08-18 10.8% can serve only as an upper-bound reference. This round's descriptive point estimate is 12.5%, but due to contamination it may not be interpreted as
qualification, nor upgraded to a product capability.

Tiering: strong 106 / weak 60 / none 34.

## 2. Pre-registration comparison

| # | Prediction | Measured | Verdict |
|---|---|---|---|
| P1 | Arm A zero-touch = 0% | 0/200 = **0.0%** | **Holds** |
| P2 | Arm D zero-touch 5–20% | 25/200 = **12.5%** (95% CI 8.6–17.8) | **Holds** |
| P3 | C ≥ D | C 14.5% ≥ D 12.5% | **Holds** |
| P4 | True silent ≤ 3 | **0** across all four arms | **Holds** |
| P5 | All-three-gates fully automatic 15–19% | 34/200 = **17.0%** | **Holds** |
| P6 | Arm D `silent_wrong` ≤ arm B | D 110 ≤ B 111 | **Holds** |

All six predictions hit numerically; the contamination status does not change on that account. **This is not a sentence to claim credit with — three of them were nearly impossible to miss:**

- **P1 is structural**, not a prediction: the census gate routes every document into the human queue, so zero-touch is 0 by definition.
  The protocol itself labeled it "structural anchor." What it proves is that the measurement pipeline is wired correctly, not that the policy works.
- **P4 falls in a range where failure is nearly impossible**: true silent is 0 across all four arms, and each 08-18 arm was also near 0.
  Predicting "≤3" amounts to setting no threshold at all. Next round should switch to a criterion that can actually fail.
- **P6 differs by a single slot**: 110 vs 111, over a denominator of ~660. The direction is right, but this difference discriminates nothing —
  all it can say is "narrow release did not make silent errors more numerous," not "fewer."

The genuinely informative ones are P2, P3, and P5 — all three drew the interval first and only then looked at the numbers, and none of the intervals is wide.

## 3. Four arms × three tiers

| Arm | Gate | Tier | Documents | Zero-touch | Undecided release slots | QA probes | Human-queue slots | True silent | Caliber disputes |
|---|---|---|---|---|---|---|---|---|---|
| A HAR-0001 | census | strong | 106 | 0 (0.0%) | 627 | 0 | 627 | 0 | 0 |
| A HAR-0001 | census | weak | 60 | 0 (0.0%) | 383 | 0 | 383 | 0 | 0 |
| A HAR-0001 | census | none | 34 | 0 (0.0%) | 220 | 0 | 220 | 0 | 0 |
| A HAR-0001 | census | **ALL** | 200 | **0 (0.0%)** | 1230 | 0 | 1230 | 0 | 0 |
| B HAR-0021 | census | strong | 106 | 2 (1.9%) | 481 | 34 | 481 | 0 | 2 |
| B HAR-0021 | census | weak | 60 | 1 (1.7%) | 318 | 11 | 318 | 0 | 0 |
| B HAR-0021 | census | none | 34 | 1 (2.9%) | 176 | 11 | 176 | 0 | 3 |
| B HAR-0021 | census | **ALL** | 200 | **4 (2.0%)** | 975 | 56 | 975 | 0 | 5 |
| C HAR-0021+payment | payment_required_v1 | strong | 106 | 17 (16.0%) | 129 | 34 | 481 | 0 | 2 |
| C HAR-0021+payment | payment_required_v1 | weak | 60 | 9 (15.0%) | 87 | 11 | 318 | 0 | 0 |
| C HAR-0021+payment | payment_required_v1 | none | 34 | 3 (8.8%) | 49 | 11 | 176 | 0 | 3 |
| C HAR-0021+payment | payment_required_v1 | **ALL** | 200 | **29 (14.5%)** | 265 | 56 | 975 | 0 | 5 |
| D HAR-0023 | payment_required_v1 | strong | 106 | 15 (14.2%) | 134 | 48 | 495 | 0 | 2 |
| D HAR-0023 | payment_required_v1 | weak | 60 | 7 (11.7%) | 89 | 16 | 323 | 0 | 0 |
| D HAR-0023 | payment_required_v1 | none | 34 | 3 (8.8%) | 51 | 14 | 179 | 0 | 3 |
| D HAR-0023 | payment_required_v1 | **ALL** | 200 | **25 (12.5%)** | 274 | 78 | 997 | 0 | 5 |

Each arm has 2,000 slots (200 documents × 10 scored fields).

**The C-vs-D gap = the cost of `release_tier1_explicit: false`**: arm D opens 22 more QA probes
(78 vs 56), buying a 2.0-percentage-point drop in zero-touch (12.5% vs 14.5%). The direction P3 predicted.

**Monotone across tiers**: zero-touch declines as broadcast OCR strength declines (strong 14.2% > weak 11.7% > none 8.8%).
The more locatable content a page has, the easier it clears the no-review evidence threshold — consistent with the mechanism's expectation.

## 4. Product-capability promotion revoked

| # | Gate | Result |
|---|---|---|
| 1 | No blocking | **Fail: protocol §7 contamination** |
| 2 | Sample complete (200 per arm, 0 missing) | **Pass** |
| 3 | Original safety gates (P4 **and** P6) | Hold numerically, but the endpoints are insufficient to support the safety of the zero-touch subset |
| 4 | Effect (P2 falls in 5–20%) | **Pass** |

The first hard gate has already failed, so **it is forbidden to write that all four passed, and product capability may not be promoted**. In addition, the post-hoc supplementary audit
found, among the 75 payment-gate slots of arm D's 25 zero-touch documents: of the 71 cross-checkable slots, 12 disagree with the DocILE
annotations (spread over 10 documents), plus 4 auto-accept slots that cannot be cross-checked. The original P6 whole-arm comparison
did not isolate the risk subset that the product sentence refers to.

The only descriptive statement permitted for this round is:

> In a 200-document DocILE exploratory measurement later judged contaminated under its own protocol, HAR-0023's
> routing-time zero-touch was **25/200 (12.5%, 95% Wilson CI 8.6–17.8)**. This result is not
> qualification and supports no claims of safety, accuracy, or product promotion.

The three limitations (ARCHITECTURE §8) stay attached: single corpus (DocILE), single vendor (Nutrient DWS),
single ground-truth caliber (DocILE annotations + truth-caliber-v1 reclassification).

## 5. What this statement does not prove

- **The zero-touch subset is not zero-risk.** Across those 25 documents' 75 payment slots, 12/71 cross-checkable values
  disagree with the DocILE annotations, plus 4 auto-accept slots that cannot be cross-checked. This post-hoc audit does not rewrite
  the pre-registered predictions, but it does prevent dressing up a routing property as a safety conclusion.
- **It is not "extraction got more accurate."** Zero-touch is a **routing-time property**, unrelated to extraction correctness. Within the same batch of responses,
  among slots that were auto-accepted and comparable against ground truth, **roughly 16.6–16.9% of values disagree with the DocILE annotations**
  (A 111/668, B 111/668, C 111/668, D 110/651) — the four arms are nearly identical.
  What narrow release changes is "how many documents a human must open," not "how much the machine gets wrong." This is precisely this project's thesis:
  extraction correctness cannot be trusted; what is verifiable is the support relation.
- **It is not "these three fields are necessarily right."** The original routing only shows these three fields cleared the
  evidence threshold under that policy; the supplementary audit has already shown that this does not equal agreement with the DocILE annotations. The other seven fields still enter
  the support matrix and still enter the human queue.
- **12.5% does not mean "12.5% of labor saved."** It is the **document zero-touch rate**, not a slot count.
  Arm D's human queue still holds 997 slots; what is saved is the 25 documents that need not be opened at all.
- **Single corpus.** DocILE is one corpus. Change the domain, the layout, or the language, and this number does not transfer.
- **n=200 has limited precision.** The 95% interval around 12.5% is 8.6–17.8%, 9 percentage points wide.
  The interval and the point estimate must be stated together.
