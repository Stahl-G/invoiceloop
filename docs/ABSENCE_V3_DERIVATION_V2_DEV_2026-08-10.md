# Engine v3 + Derivation v2: Development-Set Measurement (2026-08-10)

Continues [`ABSENCE_EVIDENCE_DEV_2026-08-09.md`](ABSENCE_EVIDENCE_DEV_2026-08-09.md).
Both mechanism changes **precede this measurement's commits** (the timestamps are the
preregistration):

- `6341052` — derivation rules v2 (`due_date.py`; the clause list is in the code comments);
- `e06488f` — absence engine v3 (`absence_evidence.py`; OCR tolerance of one edit for long
  tokens; same direction as adding words — only matches more, never less).

Zero API throughout: reads only saved DWS responses, independent OCR, DocILE annotations.
Development set =
300 deduplicated documents from the sealed1 / sealed2 / heldout workspaces (SEALED-3 unused; it
was consumed by its one-time unsealing).

## I. Absence engine v3: seller_vat_id crosses the line

`python3 scripts/absence_by_evidence.py` re-run unchanged, engine
`absence-evidence-v3` (vocabulary `0a9f3773577e068c…`; vocabulary contents are **verbatim
identical to v2**; only the matching rule changed):

| field | missing | held | saves (v2) | saves (v3) | silent (v2) | **silent (v3)** |
|---|---:|---:|---:|---:|---:|---:|
| `seller_vat_id` | 266 | 27 → 32 | 238 | 234 | 1 | **0** |
| `total_vat` | 143 | 19 | 124 | 124 | 0 | **0** |
| `total_net` | 80 | 28 | 51 | 51 | 1 | **1** |
| `due_date` | 207 | 115 | 84 | 84 | 8 | **8** |

- v2's last remaining silent (OCR read "Federal" as "federai",
  `5da5a0e2bded40ad8948d5eb`) is caught by fuzzy matching → `held`, back to humans.
  The same fuzzy matching catches 4 more labels elsewhere, saves 238 → 234 —
  **4 fewer slots saved, exactly the cost the safe direction should carry**.
- **`AV-seller_vat_id` crosses the line: 234 saves / 0 silent / 0 unscored, of which 193 slots
  are beyond the reach of the 16 class rules (174 slots in the invoice class).** Promotable
  under the same bar as HAR-0017 (silent=0, unscored=0, saves≥3).
- Recorded as-is: this measurement is **post hoc** — the motivating cases for the mechanism
  change sit in the v2 ledger.
  Same qualification as the v2 word additions: monotone safety can cover the mechanism, not the
  word "blind".
  Eligibility can only come from SEALED-4.

### Promotion (same day; in-gate numbers, a different caliber from the ad-hoc ledger — the in-gate numbers are authoritative)

In the clean workspace `runs/absence-v3-2026-08-10` (containing only the v3 probe run — if old
v2 probes mixed into the same workspace, `_compute_evaluation`'s `docs_without_probes` would
silently disable the rules and misreport probe status), walking propose → evaluate → promote:

- **`AV-seller_vat_id` enters HAR-0019** (`PROM-0018`, signed stahl,
  2026-08-10T05:23:20Z). Numbers recomputed byte-for-byte by the mandatory gate: review load
  55.67% → 50.47% (delta −5.2pp = 156/3000 slots leaving the queue),
  `absent_rule_matches` 212 → 405 (+193),
  `silent_absent` 0→0, `absent_rule_truth_conflicts` 0, probe available.
- Caliber disclosure: the ledger's 234 saves uses the "rule fired" count (missing value + empty
  truth + no page evidence = counted); the in-gate +193 is rule matches under counterfactual
  re-routing, and 156 is the actual queue reduction. The three counters each count their own
  thing; external citations always use the in-gate numbers.
- Artifacts: `docs/evidence/absence_v3_2026-08-10/` (three copies: policy / eval / PROM).

## II. total_net's 1 remaining silent: a single-total caliber dispute, not a vocabulary omission

`f7b199fd711149feaf0044c8` (a 1998 scan, a San Antonio Hispanic Chamber of Commerce membership
invoice):
the page prints only one `$1100.00` (even "Anount Due" is an OCR typo), with **no net-type label
whatsoever**; DocILE labeled that single amount `total_net` (amount_due also labeled $1100.00).

This is exactly the shape of the single-total ruling (commit `6dce2e9`, preregistered
2026-08-08): on single-total documents, Total maps to amount_due and the other three amounts are
confirm_absent. **The page-evidence rule's auto_absent agrees with the project's own caliber and
disagrees with the ground truth's field choice.**
Per Charter Five this is a caliber dispute in the `applicability` dimension, not an extraction
error — but per the 08-09 discipline, until the truth-caliber rule is written into the protocol,
it is **recorded as-is as a silent error, and the rule is not promoted**.

## III. due_date's 8 silents: a caliber dispute in the same family

The one-by-one composition is unchanged (checked on 08-09): ground truth labels dates under
**other names** like "transaction sale date time", "credit adjustment by eft", "donation
received payment status completed" as `date_due`, while the derived-value ruling (commit
`95c6b66`) already stipulates: no annotation column for that name on the page → confirm_absent;
no inferring from neighboring columns.

**total_net×1 + due_date×8 = 9 silents, all falling on the same "project caliber vs DocILE
annotation caliber" seam.** The resolution path is the truth-caliber rule in the SEALED-4
amendment (preregistered, listed item by item, written into the document), not vocabulary
changes — see
[`BROADCAST_HARNESS_DESIGN_2026-08-10.md`](BROADCAST_HARNESS_DESIGN_2026-08-10.md)
§4.4.

## IV. Truth-caliber rules land: all 9 silents reclassified, two rules promoted (same day)

After the truth-caliber rules were adopted (amendment A3, `04fc8cd`), T1/T2 landed in the
scorer, the promotion gate, and the ledger as `truth-caliber-v1` (`0381016`). Re-running the
same ledger, all 9 silents reclassify **with exactly the expected labels** — 1 case T1 + 8 cases
T2 (matching the amendment table row by row, pinned by the `tests/test_truth_caliber.py`
real-corpus regression), true silents at zero:

| field | saves | silent (original caliber) | caliber dispute | true silent |
|---|---:|---:|---:|---:|
| `total_net` | 51 | 1 | 1 (T1) | **0** |
| `due_date` | 84 | 8 | 8 (T2) | **0** |

Walking propose → evaluate → promote one by one (signed stahl):

- **HAR-0020** (`AV-total_net`, PROM-0019, 2026-08-10T06:34:15Z):
  queue −6.03pp (vs the standing routing baseline; marginal −0.83pp vs HAR-0019),
  true silent 0→0, conflicts 0, T1 dispute 1, listed separately;
- **HAR-0021** (`AV-due_date`, PROM-0020, 2026-08-10T06:34:54Z):
  queue 55.67% → **47.73%** (−7.93pp vs the standing baseline); original-caliber silent_absent
  0→5, but all 5 cases are T2 disputes, **true silent 0→0**, conflicts 0.

The broadcast harness now = HAR-0017 + four page-evidence absence rules (total_vat /
seller_vat_id / total_net / due_date); the development-set human queue drops from 60.20%
(HAR-0001) to 47.73%. The SEALED-4 main arm resolves per amendment A2's mechanism to
HAR-0021 ("the last promotion before extraction wins"), policy digest
`bed2a20912c59fd5355873448d2d0f6c5a18545c25e64404d59ddb83b776bbc4`;
artifacts pinned at `docs/evidence/absence_v3_2026-08-10/`.

**A caliber dispute is not a zero-cost pass**: T2 will let through slots whose true due date
happens to be printed next to the word "transaction" (amendment A3 already self-declares this);
the QA probe (absent_evidenced_rate ≥ 0.20) is the standing mechanism watching for exactly
this. Eligibility still can only come from SEALED-4.

## V. Derivation rules v2: trigger rate 8/300 (2.7%), honest but sparse

Running `derive_due_date` (version `due-date-relative-term-v2`) on the same 300 documents:

| Outcome | Documents |
|---|---:|
| computed (days distribution: 30×7, 0×1) | 8 |
| not_computable: no relative payment terms on the page | 201 |
| not_computable: terms present but base date **unlabeled** (page prints a bare "Date") | 53 |
| not_computable: receipt-type terms with no receipt date (honest refusal to compute) | 28 |
| not_computable: EOM/prox end-of-month terms (recognized but not computed) | 6 |
| not_computable: mutually contradictory terms | 4 |

Against ground truth: of the 8 computed, 2 have a ground-truth `date_due`, and **both agree**
(my ad-hoc comparison script judged `2018-07-12` against the ground-truth text `07/12/18` as
disagreeing — a two-digit-year format artifact; checked one by one, same date; the script is not
a scorer, recorded as-is).
The other 6 have no ground-truth date_due, so there is nothing to judge against.

**Conclusion: v2 lifts v1's 2/30 (pilot) to 8/300, but the absolute trigger rate is only 2.7%.**
The biggest blocker is not clause shape; it is the 53 "terms present, bare Date" documents —
treating a bare `Date` as the issue date would be a new caliber rule (it could also be the due
date), and **without preregistration, it is not done**. The derivation layer's contribution to
the queue is limited; due_date's main lever remains on the absence side (Section II); the
schema-side step 2 re-extraction is finished — no measurable benefit, not promoted (Section VI).

## VI. Step 2 re-extraction: the final schema descriptions show no measurable benefit, and the gate is tripped by re-extraction variance (not promoted)

The final 10 descriptions were preregistered in `BROADCAST_SCHEMA_FINAL_2026-08-10.json`
(= main's current `ingest.py::FIELD_DESCRIPTIONS` + seller_vat_id re-pointed at EIN);
candidate HAR-0022 differs from HAR-0021 in only two descriptions, due_date and seller_vat_id.
30 documents re-extracted understand-only (510 credits, 2026-08-10):

| Metric (same 30 documents, baseline HAR-0021) | baseline → candidate |
|---|---:|
| review_load | 64.33% → 64.00% (−0.33pp, 1 slot) |
| silent_wrong | 8 → 11 (**+3**) |
| true silent / caliber dispute (truth-caliber-v1) | 0 → 0 / 0 → 0 |
| value_hits | 87 → 88 (+1) |

**The +3 silent_wrong, located one by one**: `buyer_name`×2, `seller_name`×1 —
**fields whose descriptions changed by not one word**. The DWS understand re-extraction
concatenated the address into the name
(`'Philip Morris USA 120 Park Avenue New York, NY 10017-5592'` vs
ground truth `'Philip Morris USA'`); after normalization they disagree. It is model
non-determinism, not a schema effect. The single route flip (`total_net` review→auto_accept,
value matching ground truth) explains the −0.33pp and the +1 value_hit — same re-extraction
variance.

**The target fields themselves**: seller_vat_id's only ground-truth case (truth `25-1126415`)
is wrong in both arms (base `26415` → cand `Federal ID # 26415`; the label noise is actually
heavier); due_date's only ground-truth case routes to review in both arms (the candidate value
is re-extraction noise `'Due by August 1, 1 1999'`, but it goes to humans, not silent); on
documents without ground truth the candidate more often returns empty for terms like
"NET 30"/"30 Days" — direction consistent with the derivation layer's semantics, but not
scoreable.

**Verdict: not promoted** (2026-08-10, stahl); HAR-0021 stays active;
the SEALED-4 main-arm resolution is unchanged. Evidence: `docs/evidence/absence_v3_2026-08-10/`
(`eval_HAR-0022.json` + `HAR-0022.extraction_schema.json`).

**Methodological finding**: at n=30, the re-extraction gate's silent_wrong comparison is
contaminated by understand variance in **unchanged fields** (this round's +3 is exactly that;
mechanical enforcement would kill wrongly, and waving it through would open a bypass). For
future schema candidates and SEALED-4 design, the implication is: a safe comparison needs
either **paired re-extraction** (the baseline arm re-extracted in the same round, controlling
temporal drift) or a gate that looks only at changed fields; the current single-arm
re-extraction at n=30 is too brittle to adjudicate wording-level schema changes.

## Caveats

- All of these are **development-set** numbers (sealed1/2/heldout all exposed), not conclusions
  on unseen data; eligibility can only come from SEALED-4.
- The engine v3 measurement is post hoc (the motivating cases sit in the v2 ledger);
  `AV-total_vat` remains the only rule that ever passed on a blind version.
- The truth-caliber rules (Sections II and III) were adopted (2026-08-10, stahl) and written
  into the SEALED-4 amendment; T1/T2's adoption likewise **preceded** Section IV's promotions,
  but the shape of the rule text is taken from these 9 cases themselves — the same
  qualification as engine v3: monotone safety can cover the mechanism, not the word "blind".
- Both promotions in Section IV went through the mandatory gate (byte-for-byte recomputation),
  signed stahl; the gap between in-gate numbers and ledger calibers (the 234/193/156 counters)
  is self-declared in Section I.

## Recompute

```bash
python3 scripts/absence_by_evidence.py          # Section I ledger (engine v3 + caliber split)
python3 -m pytest tests/test_absence_evidence.py tests/test_due_date.py \
    tests/test_truth_caliber.py                 # incl. the real-corpus regression on the amendment's 9 cases
```

The derivation trigger rate is an ad-hoc script (zero API; reads only `load_ocr` +
`derive_due_date`), not saved; the format artifact of the comparison caliber is self-declared
in Section IV.
