# SEALED-4 sealed evaluation protocol (2026-08-09, frozen before execution)

SEALED-3 was consumed by the one-shot unsealing of 2026-08-08 (`SEALED3_RESULTS.md` §7),
and **the 16 class-absence rules this batch is to examine were inspired precisely by its
failure** — re-examining on it would mean using the same batch of data to both set the
exam and grade it. So another batch is drawn, as the current sole unseen
promotion-qualification set.

## 0. Frozen objects (frozen at this file's first commit)

- Product code: the HEAD at this file's first commit;
- Exclusion pool: `docs/development_exposure_manifest.json` (**already contains
  sealed3-100**, unique 560);
- Sampling implementation: `invoiceloop/heldout.py::sealed_list(..., context="sealed4-v1")`;
- Primary-arm policy: **HAR-0017**, policy digest
  `9b6df44236d1e22d19b760e1b1d786906f88c8d5a7d6ba58e5895982a699c7c7`,
  the file is pinned at `docs/evidence/class_absence_2026-08-09/HAR-0017.routing_policy.json`;
- Baseline policy: in-package **HAR-0001** (`invoiceloop/harnesses/HAR-0001/`).

## 1. Random seed commitment

- Randomness source: drand mainnet beacon (`https://api.drand.sh/public/{round}`);
- **Round for this batch**: `6360483`;
- **Seed (hex)**: `1e3119dd512be9b86f1f1db49687704a3856ae5331f4ced7232258a8aa58cbd7`
  (the verbatim `randomness` field of that round);
- Seed time (UTC): `2026-08-09T03:18:31Z`;
- Sampling = `heldout.sealed_list(seed, context="sealed4-v1")`:
  `random.Random("invoiceloop-sealed4-v1|" + seed).sample(sorted(pool), 100)`,
  pool = ≥4 scored-field annotations ∧ not in the exposure manifest (4,931 documents
  this time);
- The list is written to disk at `docs/sealed4_doc_list.json`; anyone can recompute it
  publicly.

## 1.1 Current status (2026-08-09)

**The list is frozen; extraction has not happened.** Steps 1–4 of §2 are all complete:

| Step | commit |
|---|---|
| Exposure manifest merged with sealed3-100 + this protocol frozen | `175f1e6` |
| drand round and seed written to disk | `2d27558` |
| `docs/sealed4_doc_list.json` written to disk | `d0852b4` |

Step 5 (`sealed extract`, 200 calls, ~5,000 credits by SEALED-3's measured spend) is
**not executed** — budget authorization has not been given. The list does not expire from
sitting there: its unseenness comes from "never touched during development", independent
of when extraction happens. Unsealing is still a separate one-shot decision.

## 1.2 The code pin has expired, the primary arm is pending (2026-08-09, before extraction)

§0 pinned the product code to the HEAD at this file's first commit (`175f1e6`) and the
primary arm to HAR-0017. Afterwards, page-evidence absence landed
(`ABSENCE_EVIDENCE_DEV_2026-08-09.md`): the gate transaction gained an absence probe,
`input_signature` gained `absence_evidence_digest`, and promotion produced
**HAR-0018** (= HAR-0017 + `AV-total_vat`), with the development-set human queue
57.87% → 55.67%.

**This does not trigger §5 voiding.** §5 governs "changes made **after** results
appear"; SEALED-4 has not been extracted or unsealed to this day, and no results exist.
The list itself is also unaffected — sampling depends only on the exposure manifest and
the drand seed, neither of which has moved; `sealed_list` recomputation still matches
document by document (pool 4,931; all 100 identical).

**But the two pins must be reset before extraction:**

| Item | At freeze | Now |
|---|---|---|
| Product code | `175f1e6` | must be re-pinned to the pre-extraction HEAD |
| Primary arm | HAR-0017 | HAR-0017, or **HAR-0018**? |

The primary arm is **a human decision**. Both paths have costs:

- **Examine HAR-0018** (recommended): what gets examined is the current best version and
  the one that would actually ship, −4.53pp versus baseline. `AV-total_vat` likewise
  passes on the blind-tested vocabulary v1 (the "both versions recorded as-is" section
  of that document), so it does not stand only by virtue of after-the-fact vocabulary
  additions.
- **Examine HAR-0017**: consistent with the original protocol, but it is no longer the
  version that would ship; after examining it, validating HAR-0018 would require drawing
  another batch, and the corpus pool loses 100 documents per draw (4,931 remaining now).

Whichever is chosen, the baseline is still in-package HAR-0001, and §3's P1–P3 and §5
stand unchanged. Once decided, **commit first, then extract**; the order must not be
reversed.

## 1.3 Amendment: broadcast scope + truth-caliber rules (2026-08-10)

This section is superseded in full by
[`SEALED4_AMENDMENT_BROADCAST_2026-08-10.md`](SEALED4_AMENDMENT_BROADCAST_2026-08-10.md):
the list scope is switched to the broadcast subpool (original list voided, kept on
disk), the primary arm = the pre-extraction broadcast harness (currently HAR-0019),
truth-caliber rules T1/T2 are added (adopted via stahl), and metrics are reported on the
strong subset with weak in its own column. The parts of §2/§3/§4/§5 not overridden
remain in force, per the crosswalk table in amendment A5.

## 2. Steps

1. Merge SEALED-3's 100 into the exposure manifest → commit;
2. Commit this protocol (**before the round is drawn**), leaving §1's three blanks open;
3. Take a public drand round → fill into §1 → commit;
4. `python3 -m invoiceloop sealed plan --workspace runs/sealed4-workspace
   --context sealed4-v1 --seed <hex> --seed-source "drand round <N>"`
   → copy to `docs/sealed4_doc_list.json` → **commit separately** (before any DWS call);
5. **Only after explicit budget authorization**: `sealed extract` — 200 calls
   (understand + agentic × 100), budget circuit breaker 6000 credits;
6. **Sealed and unread**: after extract completes, record only the ops summary; no `run`,
   no reading raw, no tuning vocabularies or strategies on this batch;
7. Unseal once → `docs/SEALED4_RESULTS.md`, numbers recorded as-is.

## 3. Pre-registered endpoints

The primary endpoints carry over the H1–H7 intervals (`docs/SEALED1_PROTOCOL.md` §3),
with HAR-0017 as the primary arm.

Promotion gate, **baseline = HAR-0001**; the two arms each run one full deterministic
pipeline on the same batch of evidence:

| # | Quantity | Pass line |
|---|---|---|
| P1 | `silent_absent` (against DocILE truth) | **no increase** vs baseline |
| P2 | `silent_wrong` | **no increase** vs baseline |
| P3 | `human_queue` (route ∉ auto_accept/auto_absent) | **decrease** vs baseline |

P1 is listed separately rather than merged with P2 because SEALED-3 died on exactly this
item: the primary arm's `silent_absent` went 0 → 1 while `silent_wrong` stayed flat.
Merging them into one "silent errors do not rise" line would make that failure read like
a near miss, and it is not — a slot misjudged as absent will never be seen by anyone
again; there is no chance of after-the-fact discovery.

### 3.1 Prediction written in stone before results

On the development set (300 documents), the measured HAR-0001 → HAR-0017 change is:
human queue 1,806 → 1,736 (−2.33pp), `auto_absent` 0 → 70, `silent_absent` 0/70,
`silent_wrong` 179/1,015 unchanged (`CLASS_ABSENCE_PROMOTION_2026-08-09.md`).

**Prediction**: on SEALED-4 the human queue drops 1–4pp, `silent_absent` ≤ 2.

This was written to make deviation visible. Deviation itself is **not** a voiding
condition — record it as-is; the real voiding conditions are in §5.

## 4. Claim discipline

- Before unsealing ⇒ only extraction ops may be reported (call counts / failures /
  spend); **must not** claim unseen-set load reduction or qualification;
- If unsealing passes ⇒ it may be said that "on a 100-document sealed set unseen during
  development, the 16 class-absence rules reduced the human queue with neither
  silent-error class rising";
- If unsealing does not pass ⇒ numbers recorded as-is, no qualification marker written,
  no switching the baseline, no deleting rules, no second run;
- SEALED-1 / SEALED-2 / SEALED-3 / the old heldout-100 **may never again** be called
  final held-out.

## 5. Voiding conditions (changing any one of these after results appear = this batch is void)

- Changing HAR-0017's policy (adding/removing rules, changing QA rates, changing the
  sampler version);
- Changing gates, normalization rules, routing code, or the scorer;
- Switching the baseline, the list, or the seed, or redrawing;
- Touching any of the above after seeing this batch's results — SEALED-4 is
  automatically demoted to a regression set, and a new batch must be drawn with a fresh
  seed.

**Once used, it is gone.** If further unseen qualification is needed after this batch, a
SEALED-5 must be drawn; and the corpus pool (4,931 documents) is finite — each draw
removes 100.
