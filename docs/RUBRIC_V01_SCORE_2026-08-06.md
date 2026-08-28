# Rubric v0.1 Re-scoring (2026-08-06, evaluated_commit `562af0a` = main HEAD)

Criteria unchanged: `docs/HACKATHON_RUBRIC_v0.1.md` (frozen at `5567241`).
Previous round: `docs/RUBRIC_V01_SCORE_2026-08-05.md` (`ad3d655`, 86/96).
The demo-reel sub-item stays removed per the user's decision; score base **96**.

**Result: 93 / 96 (96.9%), +7 over last round.** Band: Submission-ready.

Changes within the window: 10 commits on main (two on 2026-08-05, eight on 08-06);
5 of the 6 ROI actions listed last round have landed.

---

## I. Sub-score changes

| ID | Dimension | Last round | **This round** | Max | Reason for change |
|---|---|---:|---:|---:|---|
| A | Real problem and project concept | 8 | **10** | 10 | README names AP bookkeepers + auditors; four error costs each bound to a field |
| B | Project progress and end-to-end execution | 11 | 11 | 12 | unchanged (see below) |
| C | Deployment and startup feasibility | 4 | **8** | 8 | ERP integration path + measured latency + the replaced human step; all three sub-items completed |
| D | Nutrient DWS integration depth | 15 | 15 | 15 | already full |
| E | Reliability improvement and experimental evidence | 19 | 19 | 20 | deduction reason **changed** (see §III) |
| F | Risk routing and HITL | 13 | 13 | 13 | already full; evidence strength rose markedly (real human-time data) |
| G | Audit, provenance, and replayability | 10 | 10 | 10 | already full |
| H | Novelty and differentiation | 4 | 4 | 5 | cross-document-type generalization still neither claimed nor demonstrated |
| I | Submission materials (demo reel removed) | 2 | **3** | 3 | English pitch + English section + bilingual UI |
| | **Total** | 86 | **93** | 96 | |

Round proxy: Overall (A+B+C) **29/30**; Sponsor (D+E+F+G+H) **61/63**; Submission **3/3**.

---

## II. What I personally verified this round (not read from the README)

| Claim | Verification method | Result |
|---|---|---|
| Tests all green | `python3 -m pytest tests/` @ `562af0a` | **372 passed** (README says 370 — underreported) |
| Full chain still works | demo → adjudicate (HD-0001) → bundle (48 members) → verify | all four layers pass; the matrix summary is **identical field by field** to last round (HAR-0001 default unchanged; "byte equivalence" holds) |
| Workbench | started on port 8791, fetched two pages live | queue page 191KB with search box `name="q"`; adjudication page 200, 3 page-tabs, a bbox-overlay locator block, task rows, `why this is in your queue: gate failed: cross_mode_agreement` |
| Host allowlist | `curl -H 'Host: evil.example'` | **403** |
| All HITL run-0002 numbers | recomputed directly from `runs/hitl-sealed/runs/run-0002/adjudication_ledger.jsonl` | **every one matches**: 123 verdicts / 120 slots / 3 supersessions; accept 67 · correct 24 · confirm_absent 26 · N/A 4 · reject 2; median durations: all 28s, accept 20s, correct 66s, confirm_absent 44s, reject 95s, N/A 90s; fast paths 74/123 = **60.2%**; largest gap 25,088s (the overnight contamination they mention — hence medians only; handled correctly) |
| Latency | `processingTimeMs` independently recomputed over 769 saved responses | understand median 9.1s / p95 30.5s, agentic median 12.0s / p95 32.3s, serial ≈21.1s/doc — consistent with the README's 9.1/11.9/21s |
| Sealed-set baseline 21.91% | `python3 scripts/baseline_comparison.py runs/sealed1 runs/sealed1-workspace` | **fully reproduced**: TIER1 281 slots; confidence threshold 21.91% vs InvoiceLoop 9.62%; coverage 89.3% vs 55.5%; routing recall 35.3% vs 83.3% |
| The improve layer did not jump the gun | grep HAR-0003 / search for promotion records | HAR-0003 is only a **candidate**; no promotion record, no external numbers. The SEALED-1 discipline of "this batch demoted to regression set; formal conclusions await the next batch" **held** |
| absent_expected did not relax hard blocks | read the new cases in `tests/test_routing.py` | pinned: doc blocks still block; QA sampling forces review; with the cohort inactive the verdict is still `fail` |

---

## III. The E deduction reason changed (important)

Last round E's 1-point deduction was "four rubric-suggested fields absent with no explanation".
`docs/FIELD_COVERAGE.md` (2026-08-06) was written precisely for that, at the **right moment**
(before SEALED-2, not patched afterward). But **the file's measured numbers do not
reproduce.**

Recomputation (`~/Developer/dws-derisk/data/docile/annotations/`, 5,680 documents,
the same corpus the file claims; `trainval.json` is likewise 5,680):

| FIELD_COVERAGE.md's claim | This recomputation | Verdict |
|---|---|---|
| currency: 1,054 documents have the annotation key, **non-empty values: zero** | the key appears in **4,000** documents; after the project's own CODE normalization, **126** remain non-empty | **numbers do not match** |
| account_num / bank_num: key present in **52 / 39** documents, **non-empty values: zero** | key appears in **112 / 93** documents; non-empty instances **135 / 105**, samples `10491969`, `052001633` — real account/routing numbers | **"non-empty values: zero" is false** |

Under any train/val subset, neither 1,054 / 52 / 39 nor "zero" reproduces.

**Most likely cause**: currency annotations' `text` is generally the bare symbol `$`
(confirmed sample by sample); CODE normalization collapses it to `None` — so "no judgeable
ground truth" **holds as a conclusion** for currency, but for the reason "what is annotated is
the currency-symbol position, not a currency code", not "non-empty values: zero". Meanwhile
account_num / bank_num have solid judgeable ground truth — just **rare** (112/5,680 ≈ 2%), too
rare to make it into a 100-document sealed set — which by itself is a sufficient and honest
reason for exclusion.

**Handling suggestion**: the conclusion (the four fields stay out of the scoring set) need not
change; change the reasons to the reproducible ones — currency "annotations are symbol
positions; nothing judgeable after normalization"; bank/account "ground truth exists but 2%
coverage cannot enter the sealed set"; buyer_tax_id / PO "DocILE has no such fieldtype" (this
one I verified as true).

**Scoring disposition**: E stays 19/20 with no extra deduction — what is scored is the TIER1
metrics table itself (unchanged, and high quality); this file is supporting material. But it is
registered as `benchmark_integrity_findings`:
**this is the only number in the whole repo I cannot reproduce, and it sits precisely in a file
written to satisfy the rubric.** Per GOAL.md priority 2 (recomputable > complete), this is
worse than losing 1 point.
Ship it unchanged and any judge who actually checks will see what I saw.

### Case closed (evening of 2026-08-06, re-checking `87c448e` / `ca048cd`)

Both have been fixed and **independently re-verified**:

- `FIELD_COVERAGE.md`'s numbers are now recomputable digit for digit. Run as-is per the script
  appended at the end of the file, the output matches the table row by row (currency key 4,000
  / non-empty after CODE normalization 126; account_num 135;
  bank_num 105; customer_tax_id 40). **The `benchmark_integrity_findings` case is closed** —
  the repo no longer contains a number that fails to reproduce.
- `docs/BASELINE_COMPARISON_SEALED1.md` was added; the sealed-set five-way baseline table is in
  docs; every number in it matches this review's own 2026-08-06 run of
  `scripts/baseline_comparison.py` (575 slots / TIER1 281 slots / 21.91% / 9.62% / 55.5% /
  83.3% / CI [30.0,54.1] vs [54.6,74.4]). The README links it (`ca048cd`).

**One error on the review's own side (recorded along with everything else)**: last round I
wrote "buyer_tax_id / PO 'DocILE has no such fieldtype' (**this one I verified as true**')" — I
had not verified it. The probe set at the time was
`{currency_code_amount_due, account_num, bank_num, vendor_tax_id, order_id}`;
the buyer tax ID was never checked. `customer_tax_id` actually exists (38 documents / 40
instances).
**The reviewed party caught the reviewer's unverified assertion**; recorded as-is under the
same yardstick.

**Residue (no change to conclusions; a one-line fix)**: the recomputation script counts
`field_extraction` **instances** while the table labels them "documents". Instances →
documents: account_num 135→**112 documents** (2.0%),
bank_num 105→**93 documents** (1.6%), customer_tax_id 40→**38 documents** (0.67%);
currency has at most one per document, so 4,000 is the same under both. All rarity conclusions
unchanged.

The other half of E's deduction (aligning with last round's caliber): the scoring layer
contains no KILE/LIR line-item metrics (AP/F1); line items are entirely outside the schema —
the relevance of "DocILE-related metrics" is limited to header-field correctness. The wording
remains correct (it has never claimed an official benchmark score).

---

## IV. Notes on unchanged items

- **B happy path 1/2**: the document touch rate is still 100%; HITL run-0002 measured 120/120
  slots all passing through human verdicts. `absent_expected` would create the first real
  zero-touch path, but it is a HAR-0003 **candidate**; the default policy is still HAR-0001.
  Last round's advice stands: **do not fake a path for this 1 point.**
- **H generalizable 1/2**: `FIELD_COVERAGE.md` §product layer and scoring layer explains that
  **fields** are extensible ("freezing, gating, binding, routing, and audit machinery are
  field-agnostic"), but across **document types** (receipts / PO / claims) nothing is claimed
  or demonstrated. This is the last cheap point.
- **G5 timeline**: **retired by user decision, no longer registered as a risk** (2026-08-06).
  This repo has never been uploaded to GitHub; once the competition opens, go with a brand-new
  repo (or build a new document-domain feature in the new repo), with this repo existing as a
  pre-competition research asset. G5 was always `REQUIRES_HUMAN_CONFIRMATION` and never
  affected scores; **93/96 unchanged**.
  The one retained suggestion: in the new repo, honestly label the dws-derisk six-round
  experiments and this repo as "pre-competition prior research" — cited, never passed off as
  in-window work — the same discipline as Charter Six.

---

## IVb. Comparison against the official brief (appended 2026-08-06 after obtaining the original text)

Rubric v0.1 was reverse-derived from the official requirements and frozen first. Checked
against the brief's original text: **the criteria hold in direction; no weights are modified**
(to do so would be after-the-fact tailoring). But two capabilities the brief states explicitly
and this rubric weights separately are registered as **real risks outside the scoring**:

1. **DWS Viewer**: four of the brief's five sparks name Viewer as the human review surface.
   InvoiceLoop uses its own stdlib workbench. Per rubric D's original text ("one API used
   deeply beats three decorative calls") there is **no deduction; D stays 15/15**;
   but the organizer's preference and this rubric's criteria do not coincide here — a risk the
   score does not cover.
2. **Digital signatures**: the brief names "digitally sign the result so its authenticity is
   provable" twice. The current audit bundle's root of trust is the **out-of-band published
   sha256** — `verify`'s own notes say "verify is not its own root of trust".
   That is the single non-cryptographic anchor on the whole audit chain, and DWS happens to
   provide signing.

The brief's positive confirmation of this project's thesis (no points, but it shapes the
narrative choice):
"deterministic, auditable output, with a human in the loop where a guess isn't acceptable" is
nearly point-for-point isomorphic to the ARCHITECTURE §1 charter;
"'almost right' isn't good enough" is exactly GOAL.md's silent-error problem.

## V. Remaining ROI (total +3 → 96/96)

| # | Action | Points | Notes |
|---|---|---:|---|
| 1 | Fix the three numbers in `FIELD_COVERAGE.md` | 0 | **no points, but top priority** — see §III |
| 2 | Write the sealed-set baseline table into docs/ | 0 | the 9.62% vs 21.91% cited at README:126 currently **exists only in script output**; docs/BASELINE_COMPARISON.md is still the old holdout-set table. I reproduced the numbers, but a judge would have to run the script to find them |
| 3 | E: add a KILE line-item metric, or state explicitly "line items out of scope, and why" | +1 | the latter costs almost nothing |
| 4 | H: one design-claim paragraph — this machinery fits any document domain where "support relations are geometric", and why receipts/PO fall inside | +1 | README:20 already has half the argument; completing it is enough |
| 5 | B: wait for HAR-0003 to finish the qualification process before talking zero-touch | +1 | not recommended to rush for points |
