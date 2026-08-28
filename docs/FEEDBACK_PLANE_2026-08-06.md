# Feedback Plane Revision (2026-08-06): Giving the Mining Arm Its First Chance to Fire

The frozen baseline is `IMPROVE_LAYER_V0.2_DESIGN.md`. Per project discipline (**say it first,
give the basis, write it into the document; no silently changing criteria**), this file
registers four changes, one of which **relaxes an existing quality gate** — that gate came in
with question three of the 83 review, and relaxing it must leave a trace.

## 0. The measurement that triggered this revision

After run-0002 of `runs/hitl-sealed` (123 real human verdicts), running `improve mine`:

```
events 75 · actionable 0 · qualified_for_mining 0
cohorts [] · low_yield_candidates [] · absence_candidates []
not_actionable: no_reason_code 69 · low_or_no_confidence 75
```

**The mining arm produced zero and has never once fired.** Meanwhile the `absent_expected`
cohort (PROM-0002) that landed in the same period was **hand-written by a human** after reading
the run-0002 report — its rationale field is a piece of prose quoting the report. In other
words: what was validated end-to-end in the improve loop is harness versioning + promotion +
rollback + QA probes + counterfactual evaluation;
the "learn automatically from human adjudications" arm has never run.

There are two root causes: one, the criteria are too strict; two, **the information was never
brought in at all**.

---

## 1. Confidence exits the qualification gate (a relaxation, must leave a trace)

**Before**: `actionable = reason code ∧ reviewer_confidence ∈ {high, medium} ∧ not abstaining`
**After**: `actionable = reason code ∧ reviewer_confidence ≠ "low" ∧ not abstaining`

**Basis (the asymmetry)**:

- A human **actively** marking "not confident" is real information and should be heeded →
  stays excluded;
- **Unfilled does not mean confident.** run-0002's fill rate was 3/123; treating unfilled as
  unqualified lets one optional field veto the entire arm;
- Self-rated confidence **has never been validated as correlated with correctness**. run-0002
  has a counterexample: the reviewer entered `105528107477215711` without marking low
  confidence (suspicious shape, like an OCR smudge region copied over verbatim);
- The same risk already has **measurement-based** guards: the 20% QA probe on relaxed cohorts
  and the 5% sample check on policy_accepted TIER1. Guarding once more with an unvalidated
  self-rated signal zeroes out every event, at unknown benefit.

**What was not relaxed**: the reason code remains a hard requirement (no code, no supervision
label, and the system never fills one in on anyone's behalf);
the `superseded` and `random_qa` exclusions are unchanged; a mined cohort still must pass
`evaluate`'s counterfactual + human `promote` + QA probe. **The quality gate was never the only
guard — which is exactly why it can be relaxed.**

Caliber change: `mine_report.buckets.not_actionable_reasons`'
`low_or_no_confidence` is renamed `low_confidence`, counting only actively marked lows.
**No published number is retroactively recomputed.**

## 2. Don't ask the same thing twice (UX, not criteria)

The combo table in `adjudicate.py` already stipulates that reason code and verdict are not
independent:
`CONFIRMED_ABSENT ⟺ confirm_absent`, `NOT_APPLICABLE ⟺ not_applicable`.
Asking for a reason code again on those two verdict types makes people re-enter what they just
clicked (run-0002: this class is 30/123 = 24%).

- **Fast-path buttons carry their own reason code**, only where the semantics are one-to-one:
  confirm missing → `CONFIRMED_ABSENT`; adopt the rejected draft → `BAD_SOURCE_BINDING`;
- **accept splits into two buttons**: "confirmed correct" carries no code (the label lexicon
  has no "routing was right", and it constitutes no relaxation evidence); "and this shouldn't
  have been in the queue" → `ROUTING_FALSE_POSITIVE`, the only signal mining low-yield cohorts
  needs. Two buttons, not one new form field;
- **Problem chips follow the same rules**: wrong value → `WRONG_VALUE`; wrong location →
  `BAD_SOURCE_BINDING`; unreadable → `AMBIGUOUS_DOCUMENT`; not on the page →
  `CONFIRMED_ABSENT`; other → `OTHER`;
  **"matches the page" and "caliber conflict" stay blank** — applicability disputes have no
  counterpart in the reason-code set, and stuffing one in would be inventing. When several
  chips are clicked in a row, only the first writes a code; a human-chosen one is never
  overwritten;
- The "adopt DWS value (no claim)" branch **stays blank**: it could be a binding failure or an
  OCR block leaving the gate unavailable; when the machine cannot tell, it does not choose for
  the human.

**This change is forward-looking.** Historical verdicts still have empty `reason_code`
(115/123); run-0002's data cannot unlock it — measured under the new gate, `qualified 0 → 7`
and `cohorts 0 → 5`, not 0 → 117. The first round with real output is the next one.

## 3. The reviewer's own words must be able to come in (filling a gap)

`feedback.py` previously **never carried `rationale` into feedback events** — that mandatory
free text stopped in the adjudication ledger, invisible to the improve layer. Now:

- events carry `rationale` (verbatim, un-parsed);
- `mine` groups them into `notes` by cohort; `absence_candidates` carries them too.

**Discipline: pass through verbatim; the machine extracts no features from it.** Free text →
policy needs a model, and the first line of `gates.py` is "all deterministic, no model calls".
This column is for **the person writing proposals** — the previous cohort was hand-written by a
human reading the report anyway; this only narrows "what to read" from a 123-line ledger to
"what the people in this cohort actually said".

Measured, there is immediate content (runs/hitl-sealed):

- `total_gross`: "matches the page; 2371.95 and $2371.95 should not differ; remember next
  time" — a normalization defect report, previously completely invisible to the harness;
- `seller_vat_id`: "the Fed. I.D. on a US invoice is an EIN, not a VAT number", hanging on a
  slot that was **`route: auto_accept` yet `reject`ed**.

## 4. Overturn signal: auto_accept overturned by a human (tightening, new)

`mine_report.overturned_auto_accepts`: slots routed `auto_*` where the human did
`correct`/`reject`.

**The direction is opposite to the previous two classes** — `low_yield` / `absence` are
relaxation leads; this class is **tightening evidence**, so it does not enter candidates: it is
listed separately, and **reported on a single occurrence, with no frequency threshold**.
Relaxation demands evidence, tightening demands timeliness; the asymmetry is deliberate
(Charter Four: the safe direction first). Overturns caught by the QA probe **count all the
same** — catching this is why the probe exists, and being randomly drawn does not disqualify
them.

## 5. Advisor layer `suggest` (the model reads notes and produces drafts)

**Position**: deliberately **not under** `improve`. The improve control plane's four
subcommands stay fully deterministic and model-free; `suggest` hangs alongside, the same
pattern as `vision` — the model only writes a draft file (`improve/suggestions.json`; no IDs,
no policy, nothing entering the ledger);
whether to adopt is decided by a human in the workbench after reading the verbatim words and
the draft, after which it still goes through `propose → evaluate → promote` and QA probes.
**The difference is entirely in who signs.**

Each draft is validated line by line before being written (`suggest.validate`, a pure
function, no network, unit-testable):

| Criterion | Reason for rejection |
|---|---|
| `action ∈ {auto_accept, absent_expected, revoke}` | other actions not accepted |
| cohort keys ⊆ {field, tier, strength} | a doc_id / expected value appearing = a cohort allowlist that bypasses routing |
| `cites` non-empty and indices within the notes table | **a suggestion without citations is the model's opinion, not something that came from evidence** |
| confidence ∉ {high,medium,low} → downgraded to low | self-invented levels not accepted |

The workbench `/improve` page (**read-only**): tightening signals ranked first, the reviewer's
verbatim words as the body, model drafts tagged `advisory`, hung with the words they cite, and
discarded drafts also shown.
What the bottom of the page offers is **one copyable propose command**, not a button —
the only entry that writes active must be `improve promote` (v0.2 §12);
if one button on a web page could change policy, that human gate would be a sham.

---

## 6. Acceptance criteria for the next round (written before doing)

1. **The mining arm independently finds the `seller_vat_id` absence candidate on its own** —
   have it rediscover a rule a human already hand-wrote. The answer is known; that is the
   cleanest test of whether it is right;
2. The endpoint uses **time**, not slot counts: run-0002 measured seller_vat_id at a median
   90s/slot, 18.6% of all human time, while `total_gross` takes only 14s — slot counts would
   price the two the same;
3. **Mining set and evaluation set separated**: these 12 documents are contaminated by
   run-0002/0003 and can serve only as a regression set;
4. **Change one variable at a time**: run-0003 changed policy and turned on vision for the
   first time simultaneously, so the routing-layer −3 mixed two causes; this time it must not
   happen again;
5. The model drafts' **adoption rate and validation-layer discard rate** must be registered
   honestly — if the discard rate stays high, the advisor layer is fabricating and should be
   retired, not accommodated by tuning the prompt.
