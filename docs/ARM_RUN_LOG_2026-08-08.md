# Controlled-experiment run log (2026-08-08, written down as it happened)

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md` (frozen at `a667b6b`).
Roster: `docs/arm_slot_sample.json` (drand 6356437, frozen at `f648df2`).

**This file's purpose**: to record what **actually happened** in the two arms; the
results document must record these as-is. Without them,
`docs/ARM_AGENT_VS_HUMAN_RESULTS_*.md` would read as if everything went smoothly —
it did not.

## Sample composition (recorded right after sampling, before any adjudication)

| Dimension | Value |
|---|---|
| Pool | the 468 `route == review` slots in `runs/sealed2` (harness HAR-0004) |
| Drawn | 200 slots / 87 documents / all 10 fields |
| Empty slots | 60 |
| QA probes | 5 (`mine` excludes them by design) |
| support_strength | corroborated 101 · unsupported 94 · single_source 5 |
| Have a span to draw a box on | 144; neither kind 56 |
| **DocILE has an annotation for the field** | **113 (56%)** |
| **DocILE has no annotation for the field** | **87 (44%)**, of which 41 slots also got no value from the extractor |

> `seller_vat_id` drew only 4 slots, right at `mine`'s `absentish >= 3` threshold —
> if that cohort does not ignite, it may be **sample size** rather than either
> arm's judgment. Recorded on sampling day, not a reason found after the fact.

## TA arm (agent:gemini-3.6-flash)

Final: **193 adjudicated + 7 write-entry rejections = 200 / 200**.
ledger sha256 `4a7b6f7e52a91e87939426e3fef3d27526fc80389d16bef3daab7f581168be5b`
(that hash is the value at 193 lines; the 7 rejections were never written to the
ledger).

### 1. The 27 failures must be split into two classes; the classification decides whether retrying is allowed

| Class | n | Disposition |
|---|---|---|
| Write-entry rejections (an `accept` on a slot with no claim) | 6 → 1 added later = **7** | **Recorded permanently, no retry.** Retrying means shaking until an answer that passes comes out — tuning on results (preregistration §7) |
| Transport layer (429 spend cap / 5xx) | 21 | Resume-and-retry. What changed is not the prompt / criteria / sampling, only making sure each slot actually gets asked once |

### 2. One interface mistake of mine, recorded as-is, and unfixable within this arm

The workbench's buttons for humans are **trimmed per slot** — slots without a
frozen claim are not shown "accept". Yet the prompt I gave the agent listed all
six decisions every time. So those 7 rejections **contain my interface's share;
they are not purely the agent's judgment failures**.

Changing the prompt after seeing results would void the entire TA arm
(preregistration §7), so this arm stays unchanged. Fixing it means drawing a new
roster and opening a new arm.

### 3. Quota interruption and key switch

- After the first pass finished 173 slots, the Gemini project hit its **monthly
  spend cap**; 116 backoff attempts all hit hard 429s;
- Switched to a new project's key; the error became **prepaid balance of 0** (the
  $300 Cloud trial credit ≠ an AI Studio prepaid balance, and once a project is on
  billing it no longer qualifies for the free tier);
- Ended up going back to the original key (quota had recovered) and finishing the
  21 remaining slots.
- **Switching credentials does not void this arm**: §7's voiding conditions are
  the prompt / criteria / sampling; transport credentials are not among them.
  But this arm was completed across two time windows; recorded here.

## H2 arm (human, reviewer stahl)

**Decision (2026-08-08): do the full 200 slots per the preregistration.** A
redraw stratified by ground-truth presence was considered (it would spend the
human's time on higher-information-density slots) and not adopted.

### A design seam exposed during review (not a defect report — a discovery)

**The page genuinely lacks this field, but the extractor fabricated a value** —
for slots like these, the absence signal **can never reach the absence cohort**.

The chain:
- When a slot has a frozen claim, the write entry refuses `confirm_absent` /
  `not_applicable` (`adjudicate.py:132`: "if the claim is wrong, use reject or
  correct"), so the reviewer can only judge `reject`;
- and `improve.mine`'s `absence_candidates` counts only `confirm_absent` and
  `not_applicable` (`improve.py:113`).

So the information "this field is often absent in this kind of document" reaches
the mining arm only when **the extractor also gave no value**. Of this batch's 200
slots, 60 are empty slots — that is the sole source of the absence cohort; for
slots where the extractor hallucinated a value, the signal falls on the floor.

Hit on 2026-08-08 by the reviewer on `1925d1e1|buyer_name`: the page's `Buyer:`
column is empty, and DWS returned the AE's name from the same line. **This is not
a fill-in error; it is a seam between the vocabulary and the mining criteria.**
This experiment does not change it (changing it would make the arms
incomparable); recorded for discussion.

### Measurement ruling three: single-total documents (set by the reviewer on 2026-08-08, after slot 24, applying to all 200 slots)

**Situation**: the page prints only one `Total` (or an equivalent single total),
with no net / tax-inclusive / amount-due distinction. Example `265763b2…`: one
line `Total $1,160.00` at the bottom of the line-item table, no tax line. Among
this batch's 87 sampled documents, at least 21 have four amount fields the
extractor cannot fully fill.

**Ruling (B2): `Total` goes to `amount_due`; `total_net` / `total_gross` /
`total_vat` take `confirm_absent`.**

**Scale: this ruling governs 76 / 200 slots (38%)** — total_net 29, total_vat 24,
total_gross 23. It is the widest-impact of the three rulings; the consequences
scale proportionally.

**Cost one: the arithmetic gates go completely silent on this kind of document.**
When only `amount_due` has a value, C1 (`net+vat==gross`) and C2 (`gross==due`)
have incomplete inputs and judge `unavailable` (the `None not in (...)` at
[gates.py:86](../invoiceloop/gates.py:86)). But `amount_due` is the TIER1 payment
amount — on this kind of document it will have **no arithmetic cross-validation at
all**; its support reduces to span binding, independent OCR, and dual-mode.

This is a voluntary trade, on the grounds that the other half is worse: when one
number is filled into three slots, C1 checks `1160 == 1160`, the gate shows
"arithmetic: pass" with zero actual information. **A silent check beats a check
that fake-passes** (charter rule four). The ruling chose silence.

**Cost two (preregistered, written before unsealing): M2 will book
measurement-convention disagreements as wrong judgments.** A `confirm_absent`
can only be falsified against the ground truth — if DocILE has annotations for
these slots (annotating the single `Total` into `amount_total_gross` is a quite
likely annotation convention), `arm_score.truth_verdict` will return `disagree`
across the board, and it has **no third bucket** to express "this is an
applicability dispute, not a wrong judgment". CLAUDE.md's hard constraint says
"measurement-convention conflicts do not enter the error rate"; the current
scorer cannot do that.

**So the results document must report three M2 numbers**; the criteria are locked
now, not decided after seeing results:

1. **Count all as wrong**: every `disagree` counts as the human's wrong judgment
   (least favorable measure);
2. **Measurement-convention disagreements listed separately**: slot ∈ {total_net,
   total_gross, total_vat} ∧ judgment = `confirm_absent` ∧ ground truth non-empty
   → goes into the "convention disagreement" bucket, reported separately;
3. **Exclusion**: M2 after dropping those slots entirely.

Report all three; picking only one to tell is not allowed. **Do not modify
`arm_score.py`** — changing the scorer after seeing part of the H2 results is
indistinguishable from tuning on results (preregistration §7).

**Re-check list of already-judged slots** (full scan at slot 24; collapse proxy =
at least two of the document's net/gross/due extraction values are exactly
identical):

| Slot | Current judgment | Collapsed |
|---|---|---|
| `0cac4923…\|total_gross` | correct | yes |
| `132ccb35…\|total_gross` | correct | yes |
| `265763b2…\|total_gross` | accept | yes |
| `61a429b2…\|total_net` | accept | yes |
| `c8d26800…\|total_net` | correct | yes |

Collapse is only a **proxy**, not a criterion: two fields with equal values can
also be a page that prints net and tax-inclusive separately with exactly zero
tax. Whether to supersede depends on **whether that document's page has only one
total column**, decided by the reviewer after re-checking each document. The
other 5 entries (`2b1312db`, `34fe381b`, `a76630d6`, `b45c2725`, `c8146d48`)
proxy negative and are not on the list.

**Unresolved rule crossing**: ruling one says "a `0.00` printed on the page
counts as having a value"; this ruling says "when there is only one total, the
rest are absent". When the page has a `$0.00` somewhere (e.g. an empty line-item
row) but **no tax column**, the two rules give opposite answers. Ruling two's
wording leans toward this ruling taking precedence ("no column on the page
bearing **this field's name** — a line-item cell is not a tax column"), but the
reviewer has not explicitly ruled on this point; total_vat's 24 slots hang here.

### Seam four: doctype never ran in these runs; the reviewer is manually redoing the category judgment for every document

Raised on 2026-08-08 by the reviewer on `e879f9c7…` (page header printed
`ORDER`): "HITL must be wired to doctype, or every single invoice has to be
asked about again". What the verification found is more basic than "not wired":

| Check | Result |
|---|---|
| `grep doctype invoiceloop/workbench.py` | **0 hits** — the workbench never shows document category |
| `document_checks` in `runs/sealed2/gate_report.json` | **the key does not exist at all** |
| Same file, `doctype_evidence` findings | **0 entries** |
| `runs/arm-h2/runs/run-0001`, same check | equally missing (it is a copy of sealed2) |

sealed2's gates ran **before** doctype landed (2026-08-07). So throughout the
review of these 200 slots, the system knew nothing about "is this an invoice".

**Scale measured** (classified by DWS self-reported `invoice_type`,
`doctype.classify`, pure free text, not yet backed by page evidence): of the 87
sampled documents, **20 (23%) are not invoices** — purchase orders 6,
confirmations 6, contracts 2, receipts 2, credit notes 1, pro formas 1, quotes 1,
no type declaration 1. This independently matches the "about one quarter" noted
at the top of `doctype.py`.

**This is exactly the source of the waste the reviewer felt**: the three
measurement rulings are essentially all **category-conditional rules** ("US
invoices have no VAT concept", "single-total documents do not split net and
tax-inclusive"), yet the system neither tells the reviewer the category nor can
it reuse a ruling on the next document of the same kind.

**doctype will not adjudicate on the human's behalf** whether "order-type
documents have a due date" — the charter reserves that for humans (rule five).
What it saves is three other things: re-identifying the category per document,
inconsistent rulings across same-kind documents, and rulings being impossible to
reuse.

Tiering and risk (left until after the experiment):

1. **Show the category + literal page-evidence box.** `doctype.find_evidence`
   already produces merged bboxes that can be boxed directly. Zero authority;
   it only puts already-computed artifacts on the page.
2. **Task wording varies by category.** Judgment still unchanged; what changes is
   how the question is asked.
3. **Decision buttons / prefill vary by category** — starts suggesting the
   answer. **Not doing it.**
4. **Category-level cohorts**: `_ABSENT_KEYS` widened from `("id","field")` to
   carry `doc_class`, so these slots never enter the queue at all. Most time
   saved, most risk; `doctype.py` already argues it must be hard-bound to "the
   type declaration has literal page evidence", and `propose(kind="absent_expected")`
   forces `qa.absent_expected_rate = 0.20`
   ([improve.py:362](../invoiceloop/improve.py:362)); 20% still draws human
   probes.

**None of it during the experiment**: re-running the gates is zero-API (gates
only read saved understand + OCR), but it would change what the reviewer sees,
and the two arms immediately become incomparable.

### Seam two: gate labels said "which layer rejected" but not "which identity, on what numbers"

Hit on 2026-08-08 on `2cf882ed…|amount_due`. All the information the page gave
the reviewer was `gate failed: arithmetic_consistency` and an "arithmetic:
reject" badge — the matrix row carried only
`reason_codes: ["GATE_FAIL:arithmetic_consistency"]`.

But the real causes sat on three other slots of the same document:

| Field | Frozen value | Page |
|---|---|---|
| total_gross | `$1,096.96` | Total Charge reads `$1,096.00` |
| total_vat | `$164.40` | it is an agency commission credit, not tax |
| total_net | `$931.60` | it is a balance, not the net |

So C1 (`net + vat == gross`) fails by 0.96, and C2 (`gross == due`) fails too.
**The gate caught the right thing — what it caught is a neighboring slot's
extraction misbinding.** But the reviewer, on the `amount_due` page, cannot see
C1, cannot see the 0.96, and reasonably read it as "the arithmetic rule needs
changing", about to write it into `rationale` as an improvement lead.

The chain: `_c1_c3`'s finding is **document-level** (`gates.py:297`,
`field=None`), carrying the sentence "C1 failed, involving [total_gross,
total_net, total_vat]"; while the slot row inherits only an argument-less
`GATE_FAIL:<gate_id>` label. Document-level evidence never sank to the
field-level page.

The consequence is more than confusion: through the current channel, this
misdiagnosis would enter `mine_report`'s cohort `notes` verbatim (`improve.py:81`
passes the text through), becoming a proposal lead pointing at a nonexistent
problem.

**Reviewer's ruling (2026-08-08): this is a defect; fix it next version**;
opened as `task_e6febe85` (sink gate labels: `GATE_FAIL` must carry the identity
ID and its inputs). Same disposition as the other two UI defects — **not merged
during the experiment**; what it changes is exactly the evidence the reviewer
sees.

The assistant explained the real cause to the reviewer; recorded in
`runs/arm-h2/advised_slots.json`; M3 must report the numbers with and without
that slot.

### Seam three: C3 is structurally blind to "due date bound to the issue date"

Hit on 2026-08-08 on `f40eef50…|due_date`. That document:

| Field | Frozen value | span_ids | Arithmetic gate | Dual-mode gate |
|---|---|---|---|---|
| issue_date | `June 30, 1999` | `ES-0743, ES-0744` | pass | pass |
| due_date | `June 30, 1999` | `ES-0743, ES-0744` | **pass** | **fail** |

The two slots are bound to **the same pair of spans** — that spot on the page is
`Invoice Date: June 30, 1999`; there is no due-date column at all.

C3's criterion is `date_ymd(issued) > date_ymd(expires)`
([gates.py:96](../invoiceloop/gates.py:96)), strict greater-than. When the two
dates are **equal**, `>` is false and C3 judges pass. In other words, C3 is
**structurally never able to catch** this class of misbinding where the due date
is bound to the issue date; this was not a one-time miss.

What caught it was `cross_mode_agreement` (dual-mode: reject). **The multi-gate
design was validated by measurement here once**: one gate is naturally blind to
a class of misbinding; another gate covers it — precisely the reason for six
gates side by side instead of picking a winner. Worth writing into the delivery
material.

Whether to change C3 to `>=` is a separate matter and **is not touched in this
experiment**: C3 is a preregistered, frozen criterion; changing it would strip
comparability from every existing number. And `>=` would false-positive
legitimate "payment on receipt / same-day due" documents — that judgment needs
evidence, not a symbol.

### The loop cannot handle "deriving the due date from payment terms" (recorded 2026-08-08)

A question raised by the same slot: the page's terms read "Interest will be
charged monthly on invoices unpaid after 30 days from date of receipt". The
reviewer asked whether this rule can enter the loop.

**No, on none of the three layers:**

1. `lint_policy` admits only cohort entries and `qa.absent_expected_rate`
   ([improve.py:240](../invoiceloop/improve.py:240)); it cannot express any
   computation;
2. `propose_schema` can only change field descriptions — that sends the
   **extractor** to derive, and the project's stance is precisely that the
   extractor's derivations cannot be trusted; and schema candidates must go
   through `evaluate --reextract`, burning credits to re-extract
   ([improve.py:1061](../invoiceloop/improve.py:1061));
3. Derivation logic belongs in the code of `gates.py` / `matrix.py`, not on the
   policy plane.

**The harder reason: the input itself is not on the page.** The term's anchor is
*date of receipt*, not the issue date; the page has no receipt date. So the
"issue date + 30 days" derivation cannot even assemble its inputs; the derived
date has neither a span nor a checkable anchor. Per charter rule six, the system
may not assert this value. The business-rules layer may have this rule; the
verification layer may not.

### Two UI defects the reviewer found mid-course

Both have been opened as separate background tasks and **will not be merged
during the experiment** — changing what the reviewer sees mid-course would make
this arm inconsistent before and after.

1. **`rationale`-required inconsistency between UI and write entry**
   (`task_302b518a`). The textarea has `required` and the label says
   "(required)", but `append_adjudication` never validates non-emptiness;
   contrast `improve.promote`, which really validates. The browser blocks; the
   API does not.
2. **The highlight box covers the value under review** (`task_57cd0bbc`). When
   a span's bbox is a flat, wide full-line strip, the `border` sits right on the
   glyphs. **This was "fixed" once on 2026-08-06 without fixing it through** —
   the border was thinned from 3px to 1.5px then, but thinning does not cure
   flat boxes. Workaround: open the unboxed original directly at
   `/files/run-0001/pages/<doc_id>-<page>.png`.

**2026-08-11 addendum (hitl-r1 S1, mid-review of run-0002):**

3. **Only one one-click adopt button when suggested values split.** When the
   frozen layer holds a rejected draft value and the vision suggestions are in a
   split (divergent) state, the adjudication page offers only "adopt the
   rejected draft" as the fast path; the readers' suggested value (which may
   differ from the rejected draft) can only be typed into the correction value.
   Example: slot `91b7c668/seller_vat_id` — rejected draft `94-0036494`, both
   kimi / xmode-a suggest `94-6036494` (diverging from xmode-u), and the page
   has only one button, "✓ original value correct — adopt the rejected draft
   '94-0036494'". Each distinct candidate value should get its own one-click
   adopt button. **Same disposition: not merged during the experiment**; fix
   together with the two above once hitl-r1 fully ends.

### Measurement ruling (set by the reviewer on 2026-08-08, after slot 13, applying to all 200 slots)

Whether a `$0.00` amount is "has a value, and it is zero" or "does not have this
field" is a known dispute in this project (`DOCTYPE_PLAN_2026-08-07.md` §0: of 13
silent errors, two are `$0.00` annotation issues). Per charter rule five, keep it
explicit and route it to human adjudication. **The reviewer's ruling:**

| Page situation | Decision |
|---|---|
| The page prints a `0.00` | counts as **having a value**; the value is `0.00` |
| The page truly lacks this field | `confirm_absent` |
| Genuinely judging the **document category** (e.g. "US invoices have no VAT concept") | `not_applicable` |

**A mid-course corrected version**: the reviewer first drafted "if not printed,
write `not_applicable`", then changed it back to `confirm_absent` after a prompt.
The reason for the change was measurement consequence, not style:
`not_applicable` **cannot be scored** against the ground truth (the ground truth
cannot express category applicability); if all absences went through it, M2
would mostly empty out — and M2 (the reviewer's own error rate) is this project's
never-yet-measured and most distinctive output from these 200 slots. Meanwhile
the agent's `confirm_absent` is scoreable; the two arms would become different
measures.

Worth recording: **this trap does not expose itself**. `improve.mine`'s absence
candidates count `confirm_absent` and `not_applicable` together
(`improve.py:113`); the loop side cannot see the difference; only the scoring
side can.

At ruling time, 13 slots were already judged (`correct` 9 / `accept` 3 /
`confirm_absent` 1); the new rule had not yet applied; no existing adjudications
needed superseding.

The convention rationale must go into `rationale` — that is the only thing
`mine` carries out verbatim.

### Measurement ruling two: derived values (set by the reviewer on 2026-08-08, after slot 19, applying to all 200 slots)

**Situation**: the page has no column bearing the field's name, but another
column's number could conceptually stand in for it (example
`c8146d48…|total_gross`: the page has only `AMOUNT DUE $800.00`, no Total /
Gross column of any kind). The old `$0.00` ruling covered only "printed / not
printed", not "the name is not printed but it can be derived".

**Ruling: take `confirm_absent`. Do not backfill by deriving from another
column.**

The reason aligns with the project's thesis: a backfilled value has **no span
binding** — the column bearing the field's name does not exist on the page, so
once written in, the downstream source is the reviewer, not the page. The
charter's one line — "extraction correctness cannot be trusted; support
relations are verifiable" — lands here on one concrete cell.

**This rule's cost, recorded now, and the results document records it as-is:**
these slots will **never agree** with the ground truth; they can only be
`unfalsified` (the ground truth also lacks the label) or `disagree` (the ground
truth has a value). That is, if DocILE has annotations for these slots, this
ruling will book them as **the human's wrong judgments** rather than exempting
them into `no_truth`. This is a voluntarily borne cost, not an oversight — what
it buys is that absence claims stay falsifiable (same direction as `arm_score`'s
existing measure for absences; see the 2026-08-06 generalization analysis, 3/85
= 3.5%).

The contrast with ruling one is worth recording: there I talked the reviewer out
of `not_applicable` because it is **entirely unscoreable** against the ground
truth and would empty M2; here I did not, because `confirm_absent` is at least
**falsifiable**. The criterion is "can it be falsified", not "is it
conservative".

**Impact on already-judged slots**: full re-check at slot 19; on empty slots
there is exactly one `correct` — `2b1312db…|total_gross → 145658.9` (reason
"value is wrong"). Whether it falls under this rule's derived backfill depends
on whether that document's page has a literal Total / total column; the reviewer
decides after re-checking whether to supersede. The other 18 slots are
unaffected.

## Blinding status

TA is frozen. **Until H2 finishes, no TA adjudication content may appear in
conversation, documents, or any output** (preregistration §8); only structural
quantities and the sha256 are reported. This file follows the same rule.

## Experiment terminated (2026-08-08, after H2 slot 32)

The user explicitly decided the H2 review flow was "too sticky", stopped the H2
arm, and authorized immediately fixing `append_adjudication`'s empty-`rationale`
write entry. Frozen breakpoint:

- `runs/arm-h2/runs/run-0001/adjudication_ledger.jsonl`: 32 lines, 32 current
  tips;
- of these, 31 are within the preregistered 200 slots and 1 is outside the sample
  (`132ccb35754a4c2791fc03d5|total_gross`) — exactly the auditable trace left by
  the workbench navigation escaping the sampling scope; 169 preregistered sample
  slots remain unadjudicated;
- sha256: `0ddabf8f62f71794616009d2d2c3d1a3505c0f38637ce64adbf8f40e159e62b2`.

Consequences recorded as-is: H2 did not complete the preregistered 200 slots;
this TA vs H2 controlled experiment is **terminated, not completed**; the
preregistered paired results may not be reported from these artifacts. The
existing 32 entries are neither changed nor deleted and remain audit artifacts;
from this moment the shared write entry's validation has changed, and later
adjudications may not be spliced back into the original experiment. If the
controlled experiment restarts, it needs a new preregistration and new arms; it
cannot continue writing this run under the guise of the same protocol.

## Workbench fixes after termination (2026-08-08)

The fixes happened after the experiment terminated; nothing is written back and
the H2 above is not rescued. Four friction points exposed by the human process
went into the deterministic control plane:

1. `workbench --review-scope <json>` turns the frozen slot list into a write
   permission boundary, no longer just a static link page. Queue, counters,
   previous/next, and `/decide` share the same allowlist; out-of-sample writes
   from stale tabs or hand-edited URLs return 409. The page persistently shows
   the list name, slot count, and sha256 prefix;
2. A refused submission returns HTTP 400 on the original slot, preserving the
   decision, corrected value, reason, reason code, confidence, and signature;
   combination errors are explained in UI vocabulary. Reason-code options are
   generated from the backend's unique combination table and follow the decision,
   so a human can no longer assemble a combination doomed to fail;
3. `rationale`'s required constraint sinks into `append_adjudication`,
   consistent across all write entries; if an old ledger lacks a reason, carry
   states `skipped_missing_rationale` explicitly rather than forging one;
4. The bbox overlay becomes a transparent fill with an outline outside the box,
   plus "hide highlight boxes" and "open the unboxed original".

The real `runs/arm-h2` read-only acceptance used the preregistered
`docs/arm_slot_sample.json`: the page shows 31/200 with 169 pending review; a
direct GET of a known out-of-sample slot is blocked with 409; after toggling the
hide button `aria-pressed=true`, and on restore the frozen box's computed style
is transparent fill, 1.5px outline, 2px outline-offset. During acceptance
`--read-only` was enabled; the ledger remains the 32 lines above and the same
sha256. Relative-date derivation, doctype cohorts, and cross-field span collision
are not part of this usability fix; nothing was smuggled in.

### Post-termination doctype → HITL wiring

The user pointed out that human review never saw the document category, so
orders, contracts, receipts and the like each had to be re-identified first. The
workbench now read-only reads the new run's frozen `gate_report.document_checks`:
on pass, the right column shows the controlled category and the literal phrase
and the left column circles the merged OCR bbox; on fail, it is explicitly
forbidden to judge field applicability from the model's self-reported type. Old
runs (including this H2) lack that top-level key; the page honestly shows "this
run did not run document type checks" — no re-running, nothing written back.

This is not a doctype cohort: the button set, preselected state, queue
membership, and the `/decide` write entry are all unchanged. `doc_class × field`
still has no human-signed applicability rule; the three US AP conventions each
still depend on jurisdiction, page labels/layout, or support relations, and
cannot be over-generalized from document category alone. Regression tests pin
both sides at once: "category evidence is visible" and "the category may not
adjudicate for the human".

### Review-task wording revision (2026-08-09, recorded on file)

The task-line copy on the queue and single-slot pages changed. Old version:

> Task: check {field} on the page — DWS read "{value}". Is this it? Right or
> wrong?

The new version comes in two forms. Without category evidence:

> Task: DWS read "{value}" as {field}. Please confirm the value really belongs to
> {field}, not merely that it appears on the page.
> Task: DWS gave no {field}. Please check whether the page states it explicitly;
> do not derive it from neighboring fields or payment terms.

When there is literal page category evidence, the prefix "literal page evidence
supports this being a {category}" is added, plus "do not presume absence from
the document category alone".

The reason for the change is that it bakes this round's two already-ruled
conventions into the instructions themselves: a value appearing on the page does
not mean the mapping is right (`WRONG_FIELD_MAPPING`); a missing field may not be
derived from a neighboring column or payment terms (this file's "measurement
ruling two"). The last sentence targets SEALED-3 main arm's only silent absence —
doctype correctly recognized the credit note, and the assumption "this kind of
document has no tax number" swallowed a seller_vat_id that truly had a value
(`SEALED3_RESULTS.md` §4). Category is context, not the answer.

**Impact on this experiment: no new incomparability, because the controlled
experiment is already terminated** (see "H2 early termination" above: the ledger
stopped at 32 lines; the preregistered paired results may not be reported from
these artifacts). The TA arm already ran to completion and is unaffected by the
wording. This entry only makes the boundary clear:

- the 32 adjudications in `runs/arm-h2` were made under the **old wording**;
- all of `runs/arm-ta` is under the old wording;
- any later review is under the new wording; a restarted controlled experiment
  must state in its preregistration which version of the instructions it uses —
  the instructions are part of the experiment's materials, and a change must be
  declared.

Also recording another change from the same batch: the delivery layer now
distinguishes `ready_for_approval` from `approved_for_export`; all slots
dispositioned no longer equals exportable. The workbench delivery page gained an
approval card, but it **does not enter the review queue** and is unrelated to
this experiment's slot-level adjudications.
