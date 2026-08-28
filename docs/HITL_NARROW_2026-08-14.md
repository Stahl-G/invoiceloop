# HITL narrow-release round results (2026-08-14)

Development-set measurement, no qualification semantics. No claim that
extraction got more accurate. This round is not spliced onto the R1 S1 curve.

Protocol: `docs/HITL_NARROW_PROTOCOL_2026-08-14.md`.
Product contract: `docs/RELEASE_PROFILE_DESIGN_2026-08-14.md`.
The comparison is background only: R1 S1's census 0/20 zero-touch, median
52s/slot. This round's queue is narrower and the system was changed mid-round;
the numbers cannot be spliced.

---

## The four pre-registered points

| Metric | Value |
|---|---|
| 1. Zero-touch document count | **4 / 20** |
| 2. Duration on opened documents (median) | **12.5 s** (16 opened; single-slot intervals recorded as 0; >1h breaks removed) |
| 3. Unresolved payment three-field slots | **0** (no slots still `pending`/`abstain` within the walk scope) |
| 4. Probe silent errors | **0** (of the 8 `QA_SAMPLE` slots, no one overturned `auto_accept` / `auto_absent`) |

Zero-touch ids: `075d4722d308410da3d8e3dd`, `50bbaa7c37374cc584cb06d3`,
`848916b2c5264818be60e1f1`, `d264eaf836b642c6aae03d8b`. For these four, the
payment three fields ∩ queue is empty and there are no QA probes; the walk did
not open them. Unopened ≠ extraction correct. Residuals still follow
ARCHITECTURE §6/§7 with the §8 qualifiers: about 12% not picked out;
unflagged TIER1 still has 7.8% true errors.

Of the 16 opened documents, working time concentrated in two: `31f273ad`
about 25 min, `a39706cb` about 20 min. Most other multi-slot documents were
4–81 s. 4 single-slot documents had interval 0, pulling the median down to
12.5 s. This is not "each document reviewed in 12 seconds".

All 24 walked payment slots have adjudications. `9a359ef4`'s `amount_due` was
rejected (an estimate document; no payable amount on the page), delivery
status **blocked** (1/20). 19 documents `ready_for_approval`, 0 sent out.

8 probes: 6 absence-type probes were human-signed `confirm_absent` (same
direction as expected-absent / absent-evidenced, not an overturn of
auto-accept); 2 `QA_SAMPLE:policy_accepted_tier1` (`total_vat` / `total_net`)
were human-signed `accept`. No one flipped an auto-accept/auto-absent into the
opposite conclusion.

---

## Closeout snapshot (development set)

Walked 32 slots (payment three fields ∩ `in_human_queue` 24 + QA probes 8).
Ledger 33 lines (including one rewrite of `31f273ad invoice_number`).

- Adjudications: accept 15 · correct 10 · confirm_absent 7 · reject 1
- Adjacent-slot median: **30.0 s** (n=30; 2 segments >1h removed as breaks;
  total working gaps about 74 min)
- Suggestions adopted on `agree` slots 10/13 (0.77). 17 lines with empty
  `suggestion_seen` (pre-injection or no suggestion for that slot). 3 agrees
  not adopted: `a39706cb seller_name` (suggested KTVL, adopted the masthead
  concat), `db60e02c invoice_number` (suggestion missing one digit, a 9),
  `96e0f58a seller_name` (suggested a call-sign string, adopted KBOT)

`correct` median 61.5 s, `accept` median 18 s. Changing a value is slower
than approving the original — consistent with "caliber/binding failure"
rather than "a quick glance".

---

## Confounder declaration

This round is **not** a frozen no-pre-read arm:

1. Mid-walk ADK page-reading suggestions (`adk-invoice` / `gemini-3.7-flash`,
   stahl agreed) were injected after the first adjudication. `suggestion_seen`
   before and after in the ledger is not comparable.
2. The protocol text was changed after the first adjudication (the human-time
   gate was installed then removed; stahl: no time limit). By the protocol's
   own freeze sentence, changing a word = the arm is not clean.
3. DocILE annotations were consulted mid-review (`a39706cb vendor_name` =
   Sinclair Broadcast Group). The blind read is void.
4. What is compared with R1 S1 is a different walk (payment 3 + probes vs
   ten-field census), a different suggestion set, a different document list.
   Drawing them as one human-time curve is forbidden.

No promotion obligation. HAR-0023 remains this round's frozen harness;
product active / HAR-0021 untouched.

---

## Artifact shas

| Item | Value |
|---|---|
| Workspace | `runs/hitl-narrow` |
| run | `runs/hitl-narrow/runs/run-0001` |
| Frozen harness | HAR-0023 / `payment_required_v1` |
| List sha256 | `2e3ed7ed8aec8c1c2849aeec96251c6f240ba3f602ef7616db9a53a91c035037` |
| Policy sha256 | `3bb39cb83c3d0785f5b0c487fab6d2fe28823dce76df05557069cca72fc3fbc8` |
| Ledger sha256 | `838d38e06098efe4753fc5f3966a6442ba02403f8ab6fc49f6a35162319e4a6d` |
| Support-matrix sha256 | `f7b24e88dc02fa82279b910e02dd5c90cfa9c1db255aba7dfe7e5aede0f958d2` |
| Closeout snapshot | `runs/hitl-narrow/improve/closeout_run-0001.json` |
