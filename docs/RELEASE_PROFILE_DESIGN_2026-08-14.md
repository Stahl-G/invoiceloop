# Release contract `release_profile` (2026-08-14)

HITL R1 terminated before S2's first adjudication, see
[`HITL_R1_TERMINATION_2026-08-14.md`](HITL_R1_TERMINATION_2026-08-14.md).
This file is the next version's product contract, not a patch to that round.

In one sentence: **the deliverable changes from "ten-field full adjudication"
to "narrow release contract + full support matrix + risk spot-checks".**

No claim that extraction got more accurate. No claim that unreviewed slots
are right. The automated-field ratio is not taken as the primary success
metric.

---

## 1. Two questions, answered separately

| Question | Who answers it | Who does not |
|---|---|---|
| What supports this value? Which tier should it be trusted to? | the support matrix (all ten fields present, recomputable with zero API) | the human need not sign off every slot |
| Can this document be paid/posted? | the fields prescribed by `release_profile` + document-level signed approval | routing policy must not grant export permission (`approve.py`, 2026-08-09) |

R1 collapsed the two questions into a single "human queue walked to the end".
At a field automation rate around 50%, the ten-field conjunction's zero-touch
≈ 0 (`scripts/doc_touch_economics.py`). S1 measured 20/20 opened.

---

## 2. `release_profile` (additive, does not modify HAR-0001)

Policy key `release_profile`. **Default = census**: `pending` /
`pending_tier1` / `abstain` on every scored field all block
`ready_for_approval`. The in-package HAR-0001 does not carry this key; SEALED
replays stay byte-identical.

`release_tier1_explicit` is **not turned off**. It continues to forbid
disguising TIER1's automated release as a human `accept` (field status stays
`pending_tier1` or `policy_accepted`, depending on the flag). It no longer
silently equals "all ten TIER1 slots must be human-clicked before anyone may
approve the document".

The frozen product default:

```json
{
  "id": "payment_required_v1",
  "fields": ["invoice_number", "seller_name", "amount_due"]
}
```

The field set is the same one as `doc_touch_economics.py`'s "payment-required
(3)"; the set may change only if the id changes. Optional
`posting_required_v1` = adding `issue_date`, `seller_vat_id`; not made the
default in this version.

Human-signed candidates (`register_policy`) may add this key. A machine
`propose` adding it = lint rejection (the first version only allows adding
cohorts). Promotion still requires `--approved-by` + evaluate. It is **not
allowed** to write it into HAR-0021 and then pretend the second half of R1 is
still being compared.

---

## 3. Field status vs document status

Field level (matrix/panel/deliverable.fields): the honest labels do not
change:

- Undecided in the queue, still `pending`
- TIER1 auto-released with `release_tier1_explicit: true`, still
  `pending_tier1` ("no one signed off the key fields slot by slot", not "the
  machine believes it correct")
- TIER2 auto-released, still `unreviewed_corroborated`

Document level, only when the policy carries a `release_profile`:

- What blocks `ready_for_approval` reduces to `pending` / `abstained` /
  `reject` on contract fields (including TIER2 contract members such as
  `seller_name`), plus ledger-integrity breaks (`accepted_unbound`,
  document-level blocking)
- `pending` / `pending_tier1` on non-contract fields **do not block payment**.
  They stay on the matrix, meaning exactly "not human-reviewed"
- `pending_tier1` on in-contract TIER1 (routing already `auto_accept`) does
  not block `ready_for_approval`. Slot-by-slot signoff is not this document's
  release condition; document-level approval is, and the approval ledger
  already records `tier1_policy_disposed_fields` (2026-08-09 Northstar:
  widening automated release is discussable only after being informed)

The default census path (no profile) keeps today's semantics, including
"`pending_tier1` blocks the whole document".

Export permission unchanged: only `approved_for_export`. The machine goes at
most to `ready_for_approval`.

---

## 4. Human queue (a write boundary, not a display filter)

Routing (`in_human_queue`) does not loosen because of a profile. Hard blocks,
unsupported, gate failures, caliber disputes, QA probes — what belongs in the
queue still enters.

The workbench's default walk scope = **contract fields ∩ human queue**, union
**any probe slot carrying `QA_SAMPLE`** (probes are not waste; they are the
precondition of automated decisions). Non-probe slots outside the contract
remain on the matrix/deliverable pages and do not enter the default walk.

The human looks down from the highest-risk documents within a time budget
(the matrix is already sorted ascending by `support_strength`). After the
budget is spent, unseen non-contract fields keep their unreviewed labels;
unapproved documents stay `ready_for_approval`, not sent out.

The terminated R1 workspace: when `round_status.json` is `terminated`, the
workbench refuses `POST /decide`. That is the round-halt gate, not a profile
mechanism.

---

## 5. Auxiliary line (designed this version, not implemented this version)

Option 2, not blocking Sections 2–4 from landing:

1. **Batch caliber policy** (signed once, not a per-document buyer-name
   edit): how seller/buyer identity blocks are cut; whether NET 30 goes
   through `due_date.py` derivation. The existing `scope.py` governs
   corpus-domain authorization, not field calibers; the caliber policy is a
   separate artifact, prefilled by the suggestion layer, not written to the
   ledger.
2. **The amount triad seen at once**: `total_gross` / `total_net` /
   `amount_due` are one group on the workbench, not three consecutive slots.
   OCR label alignment is a suggestion and does not overwrite drafts.

These two items cut the human time of "caliber adjudications mixed into the
slot queue". Without Section 2, the zero-touch document count still cannot
rise.

---

## 6. What the next round must test (new protocol, no splicing with R1)

Development-set only; run only after pre-registration:

1. How many of the 20 documents need no opening at all (neither contract
   fields ∪ probes are `review`)
2. Actual time spent on each opened document (open→leave, not a
   slot-interval median passing as per-document cost)
3. How many payment-required fields remain unresolved
   (`pending`/`abstain`)
4. How many silent errors the sampled probes catch (humans overturning
   auto_accept / auto_absent)

The "automated-field ratio" is not the primary success metric. R1's 52s/slot
is not drawn further after the contract changes.
