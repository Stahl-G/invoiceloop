# Document-touch pre-registration (2026-08-18, development set, zero API)

**This file is frozen before any number is produced.** The freeze mechanism =
the commit submitting this file precedes the commit producing the results;
both are in the public repo, so the ordering is checkable. Changing this
file's body after seeing the results = this round is void, per the same
discipline as `HITL_R1_AMENDMENT_STAGED_2026-08-11.md`.

## 0. What is being asked

**How many invoices can the narrow release contract (`payment_required_v1`)
leave entirely unopened by humans?**

AP prices by "how many documents were touched". When field-level review load
was pressed from 60.2% to 55.7%, document touch on the 300-document
development set was **300/300 = 100%** (`scripts/doc_touch_economics.py`,
ten-field conjunction; with per-field automation rate p, zero-touch ≈ p^10).
This round measures the document caliber, not the slot caliber.

**Why no human is needed:**
`release_profile.document_touch_metrics()` consumes only routes
(`release_profile.py:127-148`). Zero-touch is a **routing-time property**.
The narrow-release round's 4/20 was computed by routing; what humans do is
timing and probe catch rate, and those two things are in the second round,
not this one.

## 1. Frozen definitions

- **Touch**: the document has any slot where "`route` not in
  `("auto_accept","auto_absent")`" holds and (the field belongs to the
  contract field set **or** the slot carries a `QA_SAMPLE*` reason code).
  **QA probes count as touch** — opening a probe is opening the document.
  Same caliber as the narrow-release round.
- **Zero-touch**: the document does not meet the previous item.
  **Zero-touch ≠ extraction correct**; residual error still follows the
  three §8 qualifiers in `ARCHITECTURE.md`.
- **Contract field set**: `payment_required_v1` = `invoice_number` /
  `seller_name` / `amount_due` (`release_profile.PAYMENT_REQUIRED_V1`).
  Census = all 10 scored fields.
- **Silent error**: `safety_metrics.score_routes`, the same function as
  promotion Gate 2. `silent_absent_true` and `caliber_disputes` in two
  separate columns (truth-caliber-v1).

## 2. Corpus and strata

All documents on disk with **complete dual-mode responses**, `n = 660`. Three
strata per the frozen implementation of `scope.classify_broadcast_ocr`
(verbatim from broadcast-pilot-v1):

| Stratum | n |
|---|---|
| strong (call sign + terminology ≥2 times) | 372 |
| weak (one-sided evidence) | 198 |
| **none (non-broadcast)** | **90** |

The three strata are reported separately, **not merged into one total**. The
none stratum also answers the generalization question: do absence rules mined
on the broadcast corpus still hold when moved to non-broadcast?

## 3. Four arms (A/B separating two variables)

| Arm | Routing policy | Release gate | What it isolates |
|---|---|---|---|
| **A** | HAR-0001 | census (10 fields) | conservative baseline |
| **B** | HAR-0021 | census (10 fields) | what the broadcast harness alone buys on the document caliber |
| **C** | HAR-0021 | payment 3 fields (projection) | what **narrowing the gate alone** buys |
| **D** | HAR-0023 | payment 3 fields | shipping contract (= C + `release_tier1_explicit: false`) |

The C-vs-D difference is exactly the effect of
`release_tier1_explicit: false`. HAR-0021's and HAR-0023's `absent_*_cohorts`
and `qa` are verbatim identical (checked), so this decomposition is clean.

Policy files are taken from committed frozen copies in the repo:
`docs/evidence/absence_v3_2026-08-10/HAR-0021.routing_policy.json`,
`docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json`, and
HAR-0001 takes `harness._builtin_policy()`.

## 4. Which numbers get reported (per arm × per stratum)

1. **Zero-touch document count** (primary endpoint) and share
2. **Unresolved contract-field slot count** on touched documents
3. **QA probe slot count** (how much of the touch was pulled in by probes)
4. `silent_absent_true` / `caliber_disputes` / `silent_wrong` (safety side;
   cutting human review must not lean on more silence)

## 5. Predictions (written up front, misses recorded as-is)

- **A and B both land at ≈ 0% zero-touch**. Ten-field conjunction, decided by
  `doc_touch_economics`' arithmetic.
- **D's zero-touch lands in 20–35%**, i.e. **about seven in ten invoices
  still need opening**. Basis: the narrow-release round's 4/20 = 20%,
  `doc_touch_economics`' three-field caliber 27.7%.
- **D beats C**, the difference coming from `release_tier1_explicit: false`,
  magnitude < 10pp.
- **The none stratum's zero-touch is below the strong stratum's**, and
  `silent_absent_true` in the none stratum **will rise** — absence rules were
  mined on a broadcast corpus with `seller_vat_id` presence 2%, while
  non-broadcast is 16% (measured).

**If D is markedly above 35%**, my prediction is wrong, recorded as-is, and
the first check must be whether probes were not counted as touch.

**The conclusion caliber is also pinned down first:** if D lands inside the
predicted interval, the conclusion reads "the narrow contract lowers
must-open invoices from 100% to about seven in ten — a real drop, but not
'most invoices need no look'". No picking a nicer-sounding phrasing after the
run.

## 6. Conclusions this round **cannot** draw

- **Not a qualification result.** All 660 documents are in
  `development_exposure_manifest.json`, 400 of them on sealed lists.
  Non-broadcast documents neither exposed nor sealed: **0**.
- No human-time measurement, no probe catch rate — those need humans, in the
  second round, under a separate protocol.
- No claim that extraction got more accurate. No human has looked at any
  field of a zero-touch document.
- n(none) = 90, a small sample; directional observation only.

## 7. Execution

Corpus assembled once (reusing the shape of `hitl_round_setup._populate`,
raw sources extended to all workspaces); the four arms run on the same
assembly, zero API:

```bash
python3 scripts/doctouch_arms.py --out runs/doctouch-2026-08-18
```

Results go into `docs/DOCTOUCH_RESULTS_2026-08-18.md`, checked item by item
against this file. The recompute command is recorded along with the results.

## 8. Freeze seal

- This file's commit: before results are produced
- Code state: `main` @ after merging PR #2 (`6905e63`)
- The participating arms' policy-file sha256s are registered with the results
