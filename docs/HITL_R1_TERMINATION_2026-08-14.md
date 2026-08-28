# HITL R1 pre-registered termination (2026-08-14)

A **result record** for
[`HITL_R1R2_PROTOCOL_2026-08-10.md`](HITL_R1R2_PROTOCOL_2026-08-10.md) and
[`HITL_R1_AMENDMENT_STAGED_2026-08-11.md`](HITL_R1_AMENDMENT_STAGED_2026-08-11.md),
not a revision of those two frozen texts.

The staged amendment states: changing the amendment's text after the first
adjudication = the round is void. This file does not change a single character
of those two. S1 has human adjudications; S2 was assembled but its ledger has
0 lines. The termination point falls before S2's first adjudication, so
"continuing to splice the S2–S5 curve after changing the system" does not
exist.

Basis: the reviewer (stahl) decided on 2026-08-14 — choose option 3 and stop
S2 immediately; the next version is primarily option 1, secondarily option 2.
The product contract is in
[`RELEASE_PROFILE_DESIGN_2026-08-14.md`](RELEASE_PROFILE_DESIGN_2026-08-14.md).

---

## Termination statement

**HITL R1 is terminated by pre-registered termination before S2's first
adjudication.**

- Reason id: `s1_falsified_census_hypothesis`
- This is not abandoning the experiment. S1 already falsified this round's
  core hypothesis (that a suggestion layer + staged census could turn "every
  document must be opened and every one of the ten fields clicked through"
  into bearable human time).
- Continuing S2–S5 would only prove the same thing more precisely. The
  marginal information is not worth roughly another 3 hours/stage.
- It is **forbidden**, after changing routing, schema, or `release_profile`,
  to join the S2–S5 points onto S1 and draw them as one curve. That is a
  different protocol, a different round.

R2 (the original protocol's second 100) will not be run. Staged amendment B3
already wrote R2 as "if R1 has answered whether human time drops, the reviewer
decides". This round's answer: human time did not drop.

---

## Artifacts (development set, no qualification semantics)

| Item | Value |
|---|---|
| Workspace | `runs/hitl-r1` |
| Frozen harness | HAR-0021 (`release_tier1_explicit: true`, no auto_accept cohort) |
| S1 run | `runs/hitl-r1/runs/run-0002` |
| S1 ledger sha256 | `3991dcb4da1d8ab0e996299ebe51ff0e792975010c4168f72fe7c6601d5eeccb` |
| S1 closeout | `runs/hitl-r1/improve/closeout_run-0002.json` |
| S2 run | `runs/hitl-r1/runs/run-0003` (assembly + API pre-read complete) |
| S2 ledger | 0 lines. Human adjudication never started, and will not start |
| Workspace round-halt marker | `runs/hitl-r1/round_status.json` |
| Product current.json | still points to `run-0003` (last assembly); the workbench write path refuses `/decide` |

S2's 20-document list, HAR-0021 routing, and mimo-v2.5 pre-read suggestions
all remain in run-0003, replayable with zero API. They are not points on any
human-time curve.

---

## What S1 falsified (closeout numbers, development set)

Core hypothesis: "auto-dropping some slots + AI pre-read suggestions" could
bring human time down to a level where a ten-field census is affordable.

Closeout (`closeout_run-0002.json`):

- Slots 200; human queue **92**; `auto_accept` 81; `auto_absent` 27
- **20/20 documents were opened** (zero-touch 0). Field automation rate about
  54% (108/200); after the ten-field conjunction, document counts still touch
  everything — the same arithmetic as `scripts/doc_touch_economics.py`
- 94 adjudications; 90 timed segments, median **52.0 s/slot** (accept 25 ·
  correct 58 · confirm_absent 43.5 · reject 53.5)
- Control arm: hitl-sealed `run-0002` pure human time median **28 s/slot**
  (120 slots). S1 is an "AI pre-read + human confirmation" combination arm
  and must not be read as the system alone slowing down; but the combination
  arm also did **not** bring human time down
- Suggestions: `agree` 32 / `split` 36 / `blind` 16 / `agree_rejected` 10;
  adoption rate 20/32 = 0.625 (denominator contains agree only)
- Decisions skew `correct` (closeout 47/94), not confirmations

The human is mostly handling calibers, not checking numbers printed on the
page. Adjacent intervals by field (latest tip, >1h removed; development-set
supplementary observation, not the closeout caliber): seller name median
156s, VAT id 120s, buyer name 104s, due date 59s; amount slots 24–32s. The
expensive ones are agency/advertiser/NET 30, not Gross.

The staged amendment predicted 30–40 minutes per stage. S1's adjacent
intervals sum to about 3 hours. The estimate was off by about five times,
recorded as-is.

S1 has no promotion. HAR-0021 stays frozen. This is consistent with "human
review is not the schema gold standard", and with "S1 human adjudications do
not enter S2 routing".

---

## S2 assembly facts (not points on a curve)

- 20 new documents, HAR-0021, queue **114** (`auto_accept` 71,
  `auto_absent` 15)
- Still 20/20 would be opened; median 6 fields/document
- API pre-read tag `mimo-v2.5`, written into 114 slots, abstained 60/114
- Ledger 0 lines → the termination does not pollute the human-time denominator

Counterfactual (HAR-0021 routing unchanged, only the caliber of "which slots
count as opened" swapped; development set, not next-round measurement):

| Caliber | S1 zero-touch | S1 queue slots | S2 zero-touch | S2 queue slots |
|---|---|---|---|---|
| Ten-field census | 0/20 | 92 | 0/20 | 114 |
| Payment-required 3 (`invoice_number`, `seller_name`, `amount_due`) | 5/20 | 22 | 3/20 | 27 |
| Posting-required 5 (+ `issue_date`, `seller_vat_id`) | 2/20 | 36 | 2/20 | 41 |

The automated-field ratio is not a success metric. Next round's headline
numbers are zero-touch document count, time per document, unresolved
payment-required fields, and silent errors caught by sampled probes.

---

## The next round is not a sequel to this one

New product contract: `release_profile` (by default the three payment-required
fields gate payment release; the other fields stay on the support matrix,
labeled not human-reviewed; `release_tier1_explicit` is not turned off
globally). Caliber policy and whole-group review of the amount triad are the
auxiliary line, run separately.

The new protocol is written separately, with a separately drawn list, and
records three (actually four) curves separately. The old R1 S1 numbers can be
compared, not spliced.
