# Re-review: `docs/LOOP_GENERALIZATION_2026-08-06.md` (reviewer side, 2026-08-06)

Reviewed commit: `8aacaa4`. Method: independently re-ran the recomputation script +
recomputed the three disputed numbers from the authoritative artifacts + pulled the
ground truth case by case. Conclusions are ordered by strength of evidence.

---

## One: what holds (re-verified; usable for adjudication)

| Claim | How re-verified | Result |
|---|---|---|
| All numbers in the table | Ran `scripts/loop_generalization.py` as-is | **Matches line by line** (63.7/64.4/55.1, 88/88/87, 3/85, 49/272 · 48/266 · 49/266) |
| The 88 documents were never touched by humans | Set difference of the lists + scanned every `adjudication_ledger.jsonl` in the repo | **Holds**: 12+88=100 with zero overlap; `runs/sealed1` has 0 adjudications; the 12 documents with adjudications in `hitl-sealed` have zero intersection with the 88; `evo-workspace` has zero adjudications |
| The review-load definition | Read script line 60 | It uses `route not in (auto_accept, auto_absent)` — **the correct definition** (consistent with `deliver.py:113`); auto_absent is not counted as human |
| The role statement (evolution set, not a sealed set) | Against `SEALED1_RESULTS.md` qualification 4 | Consistent; `SEALED-1` had already demoted itself to a regression/evolution set |

**One attack I had preconceived was falsified; registered as-is**: script lines
29–32 filter out `extraction_present` blocking findings according to HAR-0004's
absent fields when building `facts`, and `facts` is built once and shared by all
three policies — I suspected the baseline was thereby "pre-lightened", diluting or
contaminating the advantage. Measured under both fact bases, HAR-0001 is **exactly
identical** (561/880, reaching 88/88). **The baseline is clean; this attack does
not hold.**

---

## Two: three places that must change (none affects the direction of the conclusion, but each is wording that contradicts the facts)

### 1. "Both cohorts were independently discovered by mine" — half right

Document §method: "seller_vat_id, total_vat, **both independently discovered by
mine from adjudication events**". **The repository's own promotion records refute
that**:

| | Verbatim rationale in the promotion record | Actual source |
|---|---|---|
| `seller_vat_id` (PROM-0002) | "HITL in practice (**run-0002 report**): seller_vat_id 12 slots = 9 confirmed absent + 1 not applicable…" | **hand-written by a human reading the report** |
| `total_vat` (PROM-0003) | "**independently discovered by the mining arm (mine absence_candidates)**: total_vat 9/9 confirmed absent, share 100%" | **mine output** |

Supporting evidence: this review ran `improve.mine` live **before** the reason-code
change landed; at the time it gave `actionable 0 / qualified_for_mining 0 /
absence_candidates []` — when PROM-0002 was written, the mining arm's output was
zero; it cannot have been a mine discovery.

**This one matters, because it is precisely the first acceptance criterion set by
`FEEDBACK_PLANE_2026-08-06.md` §6** ("have the mining arm find, on its own, a rule
already known to humans"). The accurate statement is:

> One was read out of the review report by a human (PROM-0002), one was
> independently discovered by the mining arm (PROM-0003, total_vat 9/9) — the
> mining arm's **first ignition**; the acceptance criterion is met.

This statement is a bit weaker than the original, but it is true, and "first
ignition" is good news on its own; there is no need to count the other one too.

### 2. The nature of the three silent-absence errors is stated wrong

Document §reading 3: "the 3 cases include **one genuine EU VAT number** (DWS
missed the extraction) and **two EIN-format numbers**". Ground truth pulled case
by case:

| Document | Field | DocILE ground truth |
|---|---|---|
| `5da5a0e2…` | seller_vat_id | `94-6036494` — **EIN format** (XX-XXXXXXX), not an EU VAT number |
| `a1481167…` | total_vat | `$0.00 USD` |
| `db2e81c7…` | total_vat | `$0.00 USD` |

**Both halves are reversed**: one EIN and two `$0.00`, not one EU VAT and two EINs.

And once corrected, the nature is completely different — this is what should go
into the adjudication material:

- Two cases are **`total_vat = $0.00`** — the annotation says "the tax amount is
  zero" while the policy says "absent". "Does a tax line explicitly printed as
  $0.00 count as absent" is a **measurement-convention dispute**; per charter rule
  five it should stay explicit and go to human adjudication, **not into the error
  rate**; it is the same family of problems as the paper Gross vs EN 16931 case
  already modeled in `matrix.py`;
- Worse, **the known boundary in `ARCHITECTURE.md §8b` is about exactly `$0.00`**:
  "`$0.00` → `['0','00']`… **zero-tax invoices are common in the real
  distribution**; this failure mode will amplify when the corpus changes". Two of
  the three cases land right on a boundary we had already registered ourselves.

Splitting the report by convention would be more honest: **genuine external
labeling misses 1/85 = 1.2%, with the 2 convention-dispute cases counted
separately**; or keep 3.5% but note that two of the cases are disputes, not errors.
Either stands; **the current "one EU VAT + two EINs" phrasing does not stand**.

### 3. "Consistent with the 3.4% independently estimated on all 100" — no source

`3.4%` appears in exactly one sentence in `docs/` across the whole repo; no file
gives its algorithm or denominator. This is the same class of problem as the
FIELD_COVERAGE.md incident (numbers written to satisfy external scrutiny that
cannot in fact be recomputed). **Either give the recomputation path or delete this
half-sentence** — it carries no weight for the conclusion; deleting it costs
nothing.

---

## Three: one definitional gap (not an error, but people will use it for cross-examination)

The numerator of `55.1%` is `route != auto_accept ∧ != auto_absent` (the deliver
definition). But in the product, `matrix.py:280` still reads
`route != "auto_accept"`, **counting auto_absent as needing adjudication**; in
`workbench.py` the count of `auto_absent` occurrences is **0** — the review queue
still puts these slots in front of humans.

Consequence: for the same run, the analysis document says 55.1% while the
workbench will show a higher number; both numbers are "right" under different
definitions. Recommendations:

1. State explicitly in the document which definition it uses;
2. On the product side, unify the three places, and **name them separately**
   (`human_queue` / `machine_decided`) — this is the same lesson as the R0
   incident where "41% was not R0". **Until they are unified, any outward-facing
   narrative of the form "human load dropped from X to Y" can step on its own
   rake.**

---

## Four: two positive facts that could be added (the document omits them)

1. **`due_date` was also judged by mine to be an absence candidate at 7/7, share
   100%, but was not promoted.** This is the best live evidence that "a candidate
   is a lead, not an authorization" — a human screened out one machine-suggested
   rule. Better written in than left out.
2. **The overturn signal has hit on real data for the first time**:
   `mine_report.overturned_auto_accepts` has one entry — `8c2273ca`'s
   `seller_vat_id`, an `auto_accept` rejected by a human, reason code
   `WRONG_FIELD_MAPPING`, verbatim: "the Fed. I.D. on a US invoice is an EIN, not
   a VAT number". The tightening-direction mechanism is not a design sketch; it
   has rung.

---

## Five: adjudication recommendation

**The main conclusion (same-distribution generalization holds, −9.3pp, cost
measured) can go to adjudication**; I re-verified the evidence chain. Before
sending it, fix the three places in §Two — none of them changes the conclusion,
but each is something an external adjudicator would find with one hands-on check,
and this project's entire persuasive power comes from "the closer you look, the
better it stands".

The attack direction the document anticipated itself (same-distribution vs
cross-distribution) is right and is already honestly stated; that one needs no
change.
