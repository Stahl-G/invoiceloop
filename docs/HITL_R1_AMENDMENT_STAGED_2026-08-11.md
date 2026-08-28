# HITL R1 amendment: staging + AI pre-read (2026-08-11, frozen before the first adjudication)

An amendment to
[`HITL_R1R2_PROTOCOL_2026-08-10.md`](HITL_R1R2_PROTOCOL_2026-08-10.md).
The legitimacy basis is the same as the SEALED-4 amendment: **R1 has zero
adjudications to date** (`runs/hitl-r1/runs/run-0001/adjudication_ledger.jsonl`
is 0 lines), and no round results exist; the original protocol's "changing a
single character after Round 1's first adjudication = both rounds void" holds
in reverse — changing things now destroys nothing. Once the first adjudication
has happened, touching this file again = the round is void.

Origin recorded as-is: the reviewer (stahl) pointed out that a single round of
~495 slots ≈ 4 hours with no intermediate output is an anti-product design,
and demanded staging plus AI sharing the pre-read. Both were adopted, in the
form below.

## B1. R1 split into 5 stages, 20 documents per stage

- R1's 100 documents (list `docs/hitl_r1_doc_list.json` unchanged) are cut
  into 5 segments in the order of seed `invoiceloop-hitl-r1-staged-2026-08-11`;
  segment lists land in `docs/hitl_r1_stages.json`, frozen in the same commit.
- Stage N's run = `runs/hitl-r1/runs/run-000<N+1>` (run-0001's full 100-document
  run is kept as the reference baseline and does not enter the human queue).
- Each stage's closeout immediately yields that stage's point on the three
  curves (human time per slot, suggestion adoption rate, counterfactual queue
  rate); the results document records all 5 points, no cherry-picking.
- Expected human time 30–40 minutes per stage; stages may be a day apart;
  >1h intervals are removed per protocol.

## B2. AI pre-read reader (tag `kimi`)

- Before each stage opens, the agent pre-reads every queued slot of that stage
  one by one, producing `{doc, field, value | ABSTAIN}`, injected via
  `suggest_inject` with tag `kimi` into that stage run's display-only
  suggestion layer.
- **Evidence boundary: read only in-run artifacts (word-level OCR, page
  renders, span registry); never read DocILE annotations / truth / any scorer
  output.** Violation = that stage is void.
- The agent's pre-read is a **suggestion**, on equal footing with vision
  readers: single-writer unchanged, the ledger records only stahl's
  adjudications; `suggestion_seen` records the human's handling of the
  suggestion per protocol.
- When uncertain, ABSTAIN; no guessing (the same rule as the five
  page-reading disciplines).
- The agent's pre-read time is machine cost and does not enter the "human
  time" numerator; but any drop it causes in "human time/slot" must **not**
  be read as "the system alone got faster" — the results document must write
  it as the human time of the "AI pre-read + human confirmation" combination
  arm, and any comparison against run-0002's pure human time (28s median,
  120 slots) carries this qualifier.

## B3. Between-stage promotion

- Stage closeout → `improve.mine` → human review →
  `improve.promote --approved-by stahl` → `improve.evaluate` counterfactual +
  full pytest suite green → the next stage's run uses the promoted harness
  (frozen_harness; the product's active state is untouched).
- No candidate passing review = honestly record "no promotion this stage";
  standards are not lowered to fill a curve.
- R2 (the second 100 documents, original protocol) remains optional: if the
  5-stage curve has already answered "did human time drop", whether R2 runs
  is decided by the reviewer after seeing the stage data.

## B4. What does not change

Corpus rules (§1), measurement caliber (§3), between-round discipline (§4's
deterministic-only, no vocabulary deletion, no touching sealed), the
record-as-is obligation (mid-round caliber rulings written into rationale +
results document).
