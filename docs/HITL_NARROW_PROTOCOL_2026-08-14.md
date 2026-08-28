# HITL narrow-release round (2026-08-14, frozen before the first adjudication)

This round is neither R1's S2–S5 nor the original protocol's R2. R1 was
terminated by pre-registered termination before S2's first adjudication
(`docs/HITL_R1_TERMINATION_2026-08-14.md`). This file freezes on first commit;
changing a single character after this round's first adjudication = this round
is void.

Product contract: `docs/RELEASE_PROFILE_DESIGN_2026-08-14.md`.
Option 1 is primary (the three payment fields gate release, budget capped, no
more ten-field census); option 2 is auxiliary (caliber signed once, suggestion
layer prefill, amount triad viewed on one screen).

No claim that extraction got more accurate. The automated-field ratio is not
taken as the primary success metric.

---

## 1. Corpus

- Pool: the original R2's 100 documents (`docs/hitl_r2_doc_list.json`), i.e.
  the broadcast strong/weak saved documents left over from R1. R1's 100
  documents do not enter this round (already human-seen; timing impure).
- **sealed4-100 never enters**.
- This round: 20 documents, seed `invoiceloop-hitl-narrow-2026-08-14`,
  `random.Random(int(sha256(seed)[:16], 16)).sample(r2, 20)` then sorted.
  List `docs/hitl_narrow_doc_list.json`, frozen in the same commit,
  sha-checked.
- Zero new DWS calls. No API pre-read (R1's combination arm 52s/slot vs
  control 28s; this round does not reuse that arm).

---

## 2. Frozen harness and caliber

- Routing: HAR-0023 = HAR-0021's absence rules
  + `release_profile.id = payment_required_v1`
  (`invoice_number`, `seller_name`, `amount_due`)
  + `release_tier1_explicit: false` (CLEAN TIER1 marked `policy_accepted`,
  with a 5% `policy_accepted_tier1` probe entering the queue).
  Policy file: `docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json`.
  Product active / HAR-0021 untouched.
- Caliber policy signed once, prefilled by the suggestion layer, never
  written to the ledger:
  `docs/evidence/narrow_v1_2026-08-14/caliber_broadcast_v1.json`.
  Buyer = the billing name block (keep Attn, drop the street); seller =
  station/publication; due date = the printed calendar date, otherwise
  derived by `due_date.py`. The human no longer adjusts caliber on each
  document.
- The amount triad (Gross / Commission / Net Due) is aligned by independent
  OCR, with suggestions entering `amount_due` (and the gross/net that map
  uniquely). The workbench shows the triad on one screen at the payment slot;
  the human signs `amount_due`, not three slots.

Suggestion tags (display-only injection after the run, not in the
fingerprint): `caliber`, `triad`, `derived`. No xmode injection (R1's split
was a human-time cost).

---

## 3. Queue

- Walk scope = the three contract fields ∩ `in_human_queue`, union any
  `QA_SAMPLE` probe. The other fields stay on the support matrix with status
  unreviewed.
- Order: by each document's weakest `support_strength` first
  (unsupported → corroborated), then by contract field order. Down from the
  highest-risk documents, not random flipping.
- **No working-time cap.** No `review_budget.json` is written, and `/decide`
  is never refused over human time. Closeout may still record durations from
  adjacent `decided_at` (>1h breaks removed) — that is measurement, not a
  gate. Unapproved documents stay `ready_for_approval`, not sent out.
- Residual risk must be written on the queue page with the §8 qualifiers:
  about 12% not picked out; unflagged TIER1 still has 7.8% true errors.
  Unreviewed ≠ correct.

---

## 4. Measurement (development set, no qualification semantics)

Pre-registered, no cherry-picked reporting:

1. **Zero-touch document count**: documents where no slot of contract fields
   ∪ probes is `review`, / 20
2. **Duration on opened documents**: the interval between that document's
   first and last walked-slot adjudication (>1h breaks removed); unopened
   documents do not enter the denominator
3. **Unresolved payment three-field slots**: slots still `pending`/`abstain`
   within the walk scope
4. **Probe silent errors**: probe slots where the human overturns
   `auto_accept` / `auto_absent`

Control: R1 S1's census 0/20 zero-touch, median 52s/slot, about 3 hours/20
documents. That curve is not spliced.

---

## 5. Output

`docs/HITL_NARROW_<date>.md`: the four points above + confounder declaration
+ list/ledger/harness shas. No promotion obligation. Improvement candidates
are run separately, not inside the human-time budget.
