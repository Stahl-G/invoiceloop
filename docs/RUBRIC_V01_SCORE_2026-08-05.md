# Rubric v0.1 Scoring (2026-08-05, evaluated_commit 5567241)

Criteria: `docs/HACKATHON_RUBRIC_v0.1.md` (frozen at 5567241, before this scoring).
**User decision: demo-reel-related sub-items do not count** (12 days to the hackathon start;
no screen recording exists yet) — so I's "2–4 minute end-to-end demo" (3) and "showing both a
clean and a risky case" (1), 4 points in total, are removed from numerator and denominator
alike; G4 checks only repo/setup/DWS heavy-lifting documentation, not video, and therefore does
not trigger the 89-point "incomplete submission" cap. **Score base 96.**

**Result: 86 / 96 (89.6%).** Band: ceiling of Strong contender, brushing the 90 line.

The scorer's self-declared caveat is in the rubric file header's "freeze purity caveat": the
scorer of this round is the same session that froze the rubric, and `CLAUDE.md`'s claims of
results had entered context before the freeze.

---

## I. Qualification gates

| Gate | Verdict | Evidence |
|---|---|---|
| G1 core DWS usage | **PASS** | `invoiceloop/dws_client.py:20` calls `api.nutrient.io/extraction/extract` directly, schema-driven + understand/agentic dual mode; `invoiceloop/samples/raw/*.understand.json` are real response records (`requestId` / `apiVersion 2026-05-25` / `processingTimeMs`); field drafts come **only** from DWS (`field_ledger.json`'s `drafted_by` ∈ {dws_understand, dws_agentic}); DWS's `metadata.bbox` is the input to cropping, regional OCR, and frozen binding (`evidence_span_registry.json`'s `source: "dws_source_bbox"`) |
| G2 evidence integrity | **PASS** | Ground truth is read only in `scripts/{baseline_comparison,heldout_metrics,build_exposure_manifest}.py`; `invoiceloop/` runtime touches zero ground truth (`heldout.py:53` uses annotations only for sampling, `ocr.py:76` only for corpus layout probing). Reverse evidence is ample: H5/H6 missed their bars and were recorded as-is without adjusting criteria (`docs/SEALED1_RESULTS.md:27-28`); after the baseline caliber rewrite the project's own advantage shrank and was still recorded as-is (`docs/BASELINE_COMPARISON.md:82`); 41.8% was rejected by the project itself and re-reported as 61.2%/100%/82.3% (`docs/R0_BASELINE_2026-08-05.md:23-28`) |
| G3 real end-to-end run | **PASS** | Personally run through this time: `demo` → 3 documents 30 slots → review queue → `adjudicate` (produces HD-0001, bound to review_snapshot `9f722f46…`) → `bundle` (48 members) → `verify` all four layers pass; after flipping one byte inside the bundle, `members: false` precisely naming `pages/002e3cf9…-1.png`, the other three layers still true |
| G4 submission completeness (video removed) | **PASS (partial)** | public repo + `README.md:41-98` setup + DWS role documentation all present. Missing a one-sentence English pitch; README entirely Chinese |
| G5 timeline compliance | **REQUIRES_HUMAN_CONFIRMATION** | all 74 commits fall within 2026-08-02 to 08-05; the competition window is 08-17 to 09-03 — **all existing work precedes the window**. The agent does not judge a violation, but this is the single largest structural risk right now and needs a "pre-existing components vs added within the window" disclosure |

---

## II. Sub-scores

| ID | Dimension | Score | Max |
|---|---|---:|---:|
| A | Real problem and project concept | 8 | 10 |
| B | Project progress and end-to-end execution | 11 | 12 |
| C | Deployment and startup feasibility | 4 | 8 |
| D | Nutrient DWS integration depth | 15 | 15 |
| E | Reliability improvement and experimental evidence | 19 | 20 |
| F | Risk routing and Human-in-the-Loop | 13 | 13 |
| G | Audit, provenance, and replayability | 10 | 10 |
| H | Novelty and differentiation | 4 | 5 |
| I | Submission materials (demo reel removed) | 2 | 3 |
| | **Total** | **86** | **96** |

Round proxy: Overall (A+B+C) 23/30; Sponsor (D+E+F+G+H) 61/63; Submission 2/3.

### A. Real problem and project concept 8/10 — `IMPLEMENTED_AND_VERIFIED`

- Clear target outcome **2/2**: `GOAL.md:13` "not to make extraction accurate — six rounds of
  experiments have proven that cannot be done … but to make 'inaccurate' visible, locatable,
  and gradable". Exactly the outcome shape the rubric asks for.
- Match to the challenge theme **2/2**: `README.md:3` "support relations, not correctness";
  `README.md:20` argues why invoice support relations are geometric and mechanically
  verifiable.
- Clear users and workflow **2/3**: there is a "reviewer / adjudicator" role (verdicts recorded
  under name in the ledger), but no AP clerk / finance approver / auditor is named, and nothing
  describes the upstream and downstream of an invoice entering the payment flow. **−1.**
- Clear cost of errors **2/3**: `fields.py:42` "T1 being wrong is fatal" is the tiering basis,
  but nowhere in the repo is there one sentence of "what goes wrong leads to what" — wrong
  payments, duplicate payments, filing problems from a wrong tax ID are all unwritten. **−1.**

### B. Project progress and end-to-end execution 11/12 — `IMPLEMENTED_AND_VERIFIED`

- Complete core pipeline **4/4**: personally run this time; see G3.
- Exception paths **3/3**: three classes of real interception, all reproducible — (a) `046e0c49`
  has no text layer and no tesseract → blocked per Charter Four instead of silently skipped
  (reproduced this time); (b) `docs/LIVE_TEST_2026-08-05.md:76-79` agentic extracted
  seller_vat_id as `58-0391482` (last digit off by one); the frozen binding refused it on the
  spot; (c) `docs/LIVE_TEST_2026-08-05.md:30-34` C8's cross-document duplicate check caught,
  in its first engagement, two documents with the same number but different dates.
- Reproducible runs **3/3**: locally `python3 -m pytest tests/` = **357 passed** (43s, zero
  skips); `scripts/fresh_venv_check.sh` is the judges' gate on a clean venv; `doctor` exits 1
  on any missing piece.
- Happy path **1/2**: **−1.** "A clean invoice successfully completes automated processing"
  does not exist in the product shape — document touch rate is 100% in both arms
  (`docs/SEALED1_RESULTS.md:54`, caveat list item 2), and in this round's demo the three
  documents were all `pending` with zero verdicts. This is a design decision, disclosed, not a
  defect — but this rubric sub-item genuinely has no scoreable instance.

### C. Deployment and startup feasibility 4/8 — weakest item

- Privacy and security **2/2**: `dws_client.py:7,39-41` keys are read only from environment
  variables and never written to disk; `docs/H1_WORKBENCH_2026-08-03.md:69` lists "write
  endpoints without Host/Origin checks can burn credits and forge verdicts" as critical and
  fixed it (Host allowlist + POST Origin 403); all processing on local loopback.
- Deployment and integration path **1/2**: `deliver.py` produces `deliverable.json` (per-field
  status + caveats), shaped for downstream consumption, but not one sentence says how it enters
  an ERP/AP system. **−1.**
- Cost and latency **1/2**: credits are reported precisely (`docs/HELDOUT.md:20`: understand
  mean 19.7/call, agentic 31.5/call; SEALED-1 actual spend 4,953/200 calls). **Latency has
  never been reported**; it appears only as a plan in the v0.2 design. **−1** — but the data
  is actually already on disk; see ROI-2 below.
- Business adoption logic **0/2**: `NOT_FOUND`. Who pays, which human step it replaces, why
  this is not a display-only demo — nothing in the repo addresses any of it. Scored 0 per "do
  not infer feature existence from architecture diagrams".

### D. Nutrient DWS integration depth 15/15 — `IMPLEMENTED_AND_VERIFIED`

- Carries the core operation **5/5**; structured evidence **4/4**: span records carry `page` /
  `bbox_rel` / `ocr_text` (independent OCR of that region) / `printed_label` /
  `source: dws_source_bbox` / `crop_sha256` — DWS's coordinates are used to **crop images and
  cross-validate**, not merely read as strings.
- Output drives decisions **3/3**: understand/agentic dual-mode disagreement is one of the six
  gates; the citation gate judges by DWS bbox; binding refusals have instances (in `FC-0012`'s
  rejections, an agentic draft `83519` with coverage 0.0 was refused).
- Differentiating capability **3/3**: source grounding is used to the hilt. Only the Extraction
  API is used; Viewer/Processor/signing are not — per the rubric's "one API used deeply beats
  three decorative calls", **no deduction**.
- None of the three score-capping conditions triggers: it is not merely PDF→text; results feed
  decisions; swap out DWS and the dual-mode gate and bbox binding fail simultaneously — product
  behavior would change.

### E. Reliability improvement and experimental evidence 19/20 — strongest section

- Held-out design **4/4**: SEALED-1 was seeded with drand round 6350076; the commitment commit
  `979fd37` precedes the draw, the list commit `f3594ce` precedes any DWS call; zero overlap
  with the 260-document exposure list and the old 100-document holdout;
  `heldout.sealed_list(seed)` reproduces the list document-by-document identically
  (`docs/SEALED1_RESULTS.md:4-8`). One notch above what the rubric asks.
- Raw baseline comparison **4/4**: a four-way comparison (raw trusted wholesale / release only
  when a value exists / confidence≥0.95 / dual mode) + InvoiceLoop, and on 2026-08-05 the
  comparison contract was rewritten, fixing the old caliber of "letting opponents borrow
  InvoiceLoop's gates" — after the fix the project's own relative advantage shrank and was
  still recorded as-is.
- Risk—coverage—human load **4/4**: all three in one table
  (`docs/BASELINE_COMPARISON.md` TIER1 285 slots: silent error 8.98% / coverage 58.6% / review
  load 41.4% / routing recall 82.4%), plus 10/20/30/40% budget curves and per-document
  bootstrap CIs.
- Error analysis and ablation **2/2**: the C3 fix and C8's first detection are located
  slot-by-slot; HAR-0001 vs HAR-0002 is a true ablation on the same frozen evidence with only
  the policy swapped (release decision load 82.9%→64.2%, safety metrics not degraded).
- Statistical honesty **2/2**: H5 (15.3% vs bar 15%) and H6 (36.6% vs upper bound 35%) missed
  their bars and were recorded as-is — nothing retired, no criteria adjusted; the four "claims
  not made" are written out explicitly.
- Key-field metrics **3/4**: **−1.** The scoring fields number only 10; the rubric's suggested
  `currency` / `buyer_tax_id` / `purchase_order_number` / `payment_or_bank_details` are all
  absent, and the repo contains not one sentence on why they are not key fields. The field set
  was preregistered and frozen across six rounds, not picked after seeing results (this is the
  cheating surface the rubric cares most about, and it held), but a coverage gap is still a
  gap. The DocILE-caliber wording is correct — the official evaluator was not used, and it has
  never claimed an official benchmark score.

**Pareto determination**: the rubric's condition 1 holds — at the same human budget,
silent error/recall are better; SEALED-1's preregistered paired CI has lower bound > 0 in the
20–40% budget band (+23.8 / +22.2 / +28.4pp). The dominance relation does not hold (coverage
58.6% vs confidence 91.6%), and the project does not claim it either. **The 11/20 cap is not
triggered.**

### F. Risk routing and HITL 13/13 — `IMPLEMENTED_AND_VERIFIED`

- Field importance **4/4**: `fields.py:43-46` TIER1/TIER2; `routing.py:103-109`
  `release_tier1_explicit`; `deliver.py:130` TIER1 without an explicit verdict →
  `pending_tier1`.
- Not confidence-only **3/3**: six deterministic gates (arithmetic identity, date ordering,
  wellformedness, citation binding, dual mode, vision), and the project states plainly that
  confidence "is a coarse-grained grounding score (two levels, 0.95/0.4), **not calibrated
  accuracy**" (`docs/BASELINE_COMPARISON.md:31-33`) — precisely the insight rubric H wants to
  see.
- In-document review experience **3/3**: `workbench.py:19-20,875-913` full-page render + bbox
  overlay (frozen bindings in solid green / DWS citations in dashed purple); queue rows carry
  evidence crops + regional OCR + printed labels.
- Edit approval and rollback **2/2**: append-only verdict ledger with `decision_id` /
  `review_snapshot_id` / `adjudicator` / `rationale` / `supersedes`; abstain = unresolved and
  **may not be released** (`docs/LIVE_TEST_2026-08-05.md:57-59` measured: after 26 verdicts
  everything was still pending; only 12 explicit supersessions released them).
- Preventing review-all **1/1**: HAR-0002 cut release decision load by 18.7pp on the same
  frozen evidence with no safety degradation. **But register the caveat: the document touch
  rate is still 100%; what the system lowers is "how much to look at per document", not "how
  many documents to look at".**

### G. Audit, provenance, and replayability 10/10 — `IMPLEMENTED_AND_VERIFIED`

All five sub-items personally verified: `input_manifest.json` (per pdf/ocr/raw/schema sha256 +
fingerprint + execution_fingerprint) / `routing_report.json` embedding the full policy text and
`policy_digest` (`routing.py:126-138`: replay must follow **this run's policy**; after a
promotion, an old run's story may not change) / the span registry's page+bbox+crop_sha256 /
HD-0001, which I wrote myself / `bundle`+`verify` four layers + a single-byte tamper pinpointed
by the members layer. This is a superset of the ideal field-record shape rubric §G gives.

### H. Novelty and differentiation 4/5

- Not just a wrapper **2/2**; technical insight **1/1** (that confidence has no discriminating
  power is measured, not asserted: in this batch all non-empty DWS values sit in the 0.95
  band).
- Generalizable trust architecture **1/2**: **−1.** `README.md:20` argues explicitly that
  invoices are tractable **precisely because** support relations are geometric, while semantic
  domains (business briefs) cannot be verified — an honest boundary statement, but it also
  means extension to receipts/PO/claims is neither claimed nor demonstrated.

### I. Submission materials 2/3 (demo-reel sub-item already removed)

- Official materials complete **1/2**: repo + setup + DWS documentation present; missing a
  one-sentence English pitch; README entirely Chinese. **−1.**
- Metrics honest and comprehensible **1/1**: full marks on the honesty half. But registered:
  for external judges readability is poor — 24 docs, no one-screen summary, no English.

---

## III. Cap check

| Cap condition | Triggered |
|---|---|
| No real end-to-end run (59) | No — the full chain was personally run this time |
| No held-out / no raw DWS baseline (69) | No — SEALED-1 + four-way baseline |
| No manual exception-handling path (74) | No |
| No verifiable audit trail (84) | No — verify four layers + tamper control |
| Incomplete submission (89) | Not applicable — the video sub-item removed per the user's decision |

`final_score = min(86, ∞) = 86 / 96`.

---

## IV. Highest-ROI next steps

Ordered by "points per unit of effort". **The first four touch no evidence layer; they are
pure documentation.**

| # | Action | Expected score | Basis |
|---|---|---:|---|
| 1 | Add a README section: who pays, which human step it replaces, how `deliverable.json` enters an ERP/AP | **+3** (C business 0→2, deployment 1→2) | currently `NOT_FOUND`, the only 0-point sub-item in the table |
| 2 | Publish latency — **the data is already on disk**; every saved response has `body.metrics.processingTimeMs` | **+1** (C latency 1→2) | computed this round over 721 saved responses: understand median 9.1s / p95 31.6s; agentic median 11.8s / p95 35.5s; both modes serially ≈ **20.9s/doc**. One sentence — "both modes are always called, no dynamic downshift, because dual-mode disagreement is itself a gate signal" — suffices to explain the mode policy |
| 3 | One-sentence English pitch + an English README section | **+1** (I 1→2) | the judges' language |
| 4 | Two sentences for A: name the roles (AP clerk / auditor) + the cost of errors (seller_vat_id wrong → filing problems; total_gross wrong → wrong payment) | **+2** (A 8→10) | the project was actually built for exactly this; it just was never written down |
| 5 | Declare before SEALED-2 why currency / buyer_tax_id / PO / bank details are not in the scoring field set | **+1** (E 19→20) | must be declared **beforehand** — patching it afterward equals the field-picking the rubric names |
| 6 | Run one non-invoice document (receipt/PO), or write the generalization boundary up as a design claim | **+1** (H 4→5) | either suffices; the latter is cheaper and more honest |

Total **+9 → 95/96**, with no need to touch the reliability evidence layer.

**Explicitly not recommended**: manufacturing a zero-touch automatic release for B's "happy
path". The 100% document touch rate is a SEALED-1 caveat recorded as-is; cutting it for 1 point
means trading Charter Six for points. Better to lose the 1 point.

**Takes priority over all of the above**: the G5 timeline disclosure. All 74 commits sit in
08-02 to 08-05, and the competition window starts 08-17. This affects no score in this table,
but it is the one thing that could void the scores wholesale.
