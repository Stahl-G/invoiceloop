# QUALIFICATION_NARROW_2026-08-22 — Qualification-Set Confirmation Round Protocol

Frozen at this commit, before any API call. Modifying this body = dirty arm; declare per the HITL-narrow precedent.

Implementation plan: `docs/superpowers/plans/2026-08-22-hackathon-sprint.md`

## 1. What this round answers

The zero-touch rate of the narrow-release contract (`payment_required_v1`) on documents **never touched by this project**.

The limitation sentence set in `docs/DOCTOUCH_RESULTS_2026-08-18.md` §6 is the direct motivation for this round: "Until an unexposed qualification set produces numbers under the same gate definition, 'narrow release reduces the number of documents opened' must not be written up as a product capability." The 660 documents of the 08-18 round were **all exposed during development**; the 10.8% can therefore serve only as an upper-bound reference, not as a product capability.

## 2. Corpus and sampling (recomputable)

- Pool = `heldout_pool` (≥4 scored-field annotations, not among the calibration 160) minus the full `development_exposure_manifest.json` (560), minus `docs/sealed4_doc_list.json` (100), then require both pdf and word-level OCR present.
- Pool size = **4,831**
  `pool_sha256` = `c5232063e6cd03c0979bd8adcc2cd8dfe73b585fe5ca107285221eed03303ce5`
- Sampling = min-hash: take the first 200 in ascending order of `sha256("invoiceloop-qual-narrow-v1|" + doc_id)`, then sort by doc_id. Context `qual-narrow-v1`, implementation `invoiceloop/heldout.py::qual_list`.
- List of 200 documents, copy at `docs/qual_narrow_doc_list.json`, frozen copy at `docs/evidence/qual-narrow-2026-08-22/plan/`
  `doc_ids_sha256` = `22c566997043c5c8185431cb813f84d3eef5a95ca1b2b61bf6182a381fbdb052`
- **At the moment of freezing, 660 documents already had dual-mode responses on disk**
  `dual_mode_on_disk_sha256` = `c1e9372b82876d9d99c2f5431fdfc0f681a0089e3cbaca4eb14a133440a9f7ea`
  Intersection with this round's list = **0** (`cmd_plan_qual` live-checks before writing to disk; a non-zero result raises RuntimeError directly).
- **Why this round's salt can be a constant**: the SEALED rounds used drand because the list had to be unpredictable before results existed. Here, **not one** of the 4,831 pool documents has ever been run, so no salt choice can pick a flattering sample; in exchange, a third party can recompute from the pool and the salt with a four-line script, without having to trust our PRNG version.
- No stratified sampling. The strong / weak / none three tiers are reported by after-the-fact grouping with `classify_broadcast_ocr` (same caliber as doctouch 08-18).

Recompute command (zero API):

    .venv/bin/python -c "
    import hashlib
    from invoiceloop.heldout import qual_pool, doc_ids_line_digest
    salt = 'invoiceloop-qual-narrow-v1'
    pool = qual_pool()
    ids = sorted(sorted(pool, key=lambda d: hashlib.sha256(
        f'{salt}|{d}'.encode()).hexdigest())[:200])
    print('pool', len(pool), doc_ids_line_digest(pool))
    print('ids ', len(ids), doc_ids_line_digest(ids))"

## 3. Extraction (this round's only API spend)

- 200 documents × dual mode (understand + agentic) = 400 calls.
- Driver = `invoiceloop.heldout.cmd_extract` (serial, resumable, key rotation on balance, budget circuit breaker).
- Responses stored under `runs/qual-narrow-2026-08-22/raw/`.
- Failure handling: the function retries network exceptions 2 times with backoff, retries 429 2 times with backoff, rotates keys on 401/402/403; anything still failing is written to `failures` in `extract_summary.json`.
  **Non-empty `failures` = this round is `blocking_level: "blocking"`; the results document states it in its very first sentence — no skipping, no silently shrinking the sample.**
- No concurrency. 400 serial calls ≈ 70–90 minutes; no reason to build a new mechanism for that.

## 4. Four arms and metrics

| Arm | harness | Gate | Notes |
|---|---|---|---|
| A | HAR-0001 | census | Structural anchor; the census gate blocks everything |
| B | HAR-0021 | census | Current policy |
| C | HAR-0021 projection | payment_required_v1 | Same routing, different gate, no rerun |
| D | HAR-0023 | payment_required_v1 + `release_tier1_explicit: false` | Candidate |

- Run: `scripts/doctouch_arms.py --out runs/qual-narrow-2026-08-22/doctouch --doc-list runs/qual-narrow-2026-08-22/doc_list.json`. **`--doc-list` is mandatory** — without it, the 660 already-exposed documents on disk get tested as well, and mixed numbers over 860 documents get written up as "unexposed" results.
- Reusing an arm directory requires checking `arm_identity.json` (policy / schema / list digest); any mismatch is a block.
- Metric definitions unchanged: `release_profile.document_touch_metrics`; primary endpoint = **document zero-touch**.
- The three tiers are reported separately; ALL is only a total. True silent (`silent_absent_true`) and caliber disputes are reported as-is.

## 5. Pre-registered predictions (misses reported as-is)

| # | Prediction | Basis |
|---|---|---|
| P1 | Arm A zero-touch = 0% | Census gate blocks everything; structural anchor |
| P2 | Arm D zero-touch falls in **5–20%** | An honest prior centered on the doctouch measured 10.8%; last round's 20–35% prediction was wrong — do not repeat that way of being wrong |
| P3 | C ≥ D | The QA probes of `release_tier1_explicit: false` only add touches |
| P4 | True silent ≤ 3 | Not higher than each doctouch arm |
| P5 | All-three-gates fully automatic share 15–19% | 17.1% on disk in doctouch; the conjunction mechanism should reproduce it |
| P6 | Arm D `silent_wrong` ≤ arm B | Narrow release only reduces **the number of documents opened**; it must not let more wrong values pass silently. This is this round's safety endpoint, reported separately from P4's true silent |

Zero-touch rates are reported with a 95% Wilson interval under the binomial distribution (n=200, point estimate on the order of ±7 percentage points).
**The interval enters the outward-facing sentence together with the point estimate** — a single percentage from 200 documents looks more precise than it actually is.

## 6. Result semantics and ordering discipline

**Four gates govern the upgrade to "product capability"; only if all four pass may it be written, and P2 is only one of them:**

1. No blocking: `failures` in `extract_summary.json` is empty.
2. Sample complete: each of the four arms tested the full 200 documents; no missing items in `--doc-list`.
3. Safety: both P4 (true silent ≤ 3) and P6 (arm D `silent_wrong` ≤ arm B) hold.
4. Effect: P2 holds.

If any one fails, the numbers are still reported as-is and the wording falls back to the 08-18 limitation sentence. **Hitting predictions and product safety are two different things** — however good the zero-touch rate looks, if arm D lets more wrong values pass silently, that is not a capability but a hazard.

- Order: run the arms first, finish computing the routing metrics over the 200 documents, and only then may a human touch any one of them. The ADK walk set is drawn from these 200 documents, but only after the routing metrics are computed and committed — the walk must not contaminate the routing numbers.
- The two rounds are accounted for independently; numbers are not stitched together.

## 7. Dirty-arm clause

After extraction starts, changing any of the following = dirty arm, declared as-is: the sampling salt or context, the list, the four arms' policy files, the definition of `document_touch_metrics`, or the body of this protocol.
