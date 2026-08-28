# InvoiceLoop Architecture v0.1

> **Lineage**: the BriefLoop architecture reference v0.6.1 (`main@47ae439d`). InvoiceLoop
> ports its **sufficiency-of-support stack** (§3.6) to invoice extraction — the cell that
> BriefLoop marks as experimental, and where the semantic-gate section §8.4 states outright
> "not yet delivered".
>
> **Evidence base**: `~/Developer/dws-derisk/`, six rounds of pre-registered experiments,
> 160 DocILE invoices, 320 DWS calls, five vision models. Every number cited in this file
> can be recomputed from that repository with zero API calls.

---

## 0. The Claim

**The correctness of extraction cannot be trusted; support relations can be verified.**

The six rounds of experiments showed: vendor confidence, deterministic checks, dual-mode
disagreement, independent OCR, and the vision reading of five frontier models — **no single
measured signal reliably flags all important extraction errors**. The signals are useful,
but not sufficient — triage can focus human attention on weakly supported rows; it cannot
turn extraction into a verdict.

InvoiceLoop therefore **makes no promise of extracting correctly**. What it promises is:
every field carries a **mechanically verifiable support relation**, plus an honest account
of "on what basis we say this, and where we cannot say for sure".

**Invoices are the best test bed for this.** In a business brief the support relation is
semantic (unverifiable); in an invoice the support relation is **geometric** — whether a
bbox relates to a page region can be verified word by word with independent OCR.

---

## 1. Charter

Inherited from BriefLoop §1.1; only the clauses that apply to this domain are kept.

**One. A field has exactly one writer.**
Python writes control state, evidence registration, claim IDs, freezing, gates, events,
hashes; the model writes field drafts and vision proposals; humans write adjudications and
delivery decisions. Derived projections must not write back over the authoritative record.

**Two. Having a source does not mean being supported; being traceable does not mean being proven.**
A bbox returned by DWS only shows that it "looked there", not that what is there supports
the value. Measured in Round Three: fields sharing a bbox score 79.7% accuracy, fields with
an exclusive bbox 60.6% — **the direction is opposite to intuition**. Support must be
recorded separately by strength, source tier, and applicability; it cannot be crushed into
one score.

**Three. What a machine can enforce is not left to memory.**
Rules that can be enforced by schema, validators, gates, or transaction checks must not
live only in prompts or handoff notes.

**Four. Frozen artifacts cannot be silently rewritten; gaps cannot be hidden.**
A check that cannot run = a high-severity blocking finding, not a skip. A field for which
DWS returned no value is **blocking**, not "payload cost".

**Five. Semantically unresolved conflicts stay explicit and go to human adjudication, not into error rates.**
The page prints `Gross Billings` while the annotation wants `Net Amount Due` — that is a
convention conflict, not an extraction error.

**Six. Say nothing the artifacts cannot prove.**
With traceability only, one must not claim semantic proof or quality improvement. Unmeasured
capabilities are written as "not yet measured".

---

## 2. Single Writer

| Writer | Owns | Must not touch |
|---|---|---|
| **Python control plane** | run state, evidence span registry, claim IDs, frozen ledger, gate verdicts, events, hashes | field values themselves (verify only, never invent) |
| **Model (vision/extraction)** | `field_drafts.json` — **no IDs, no authority** | ledger, IDs, gate results, events |
| **Human** | adjudication records, delivery approvals | inputs of already-frozen runs |

**`field_drafts.json` and `field_ledger.json` are two separate artifacts**, on the same
logic as BriefLoop's `claim_drafts` / `claim_ledger`: the model can only submit drafts;
Python assigns stable IDs and freezes.

> **This clause is not formalism.** Measured in Round Six: one vision model mis-bound 359
> answer rows to other invoices, with 63.1% of the answered content appearing on other
> documents. Had the model been able to submit only drafts, with Python validating the
> binding, **70% of that mis-binding would have been structurally rejected** (118/168, same
> case and denominator as §5.2, pinned line by line by test_binding_regression.py), instead
> of being discovered by after-the-fact OCR forensics.

---

## 3. Four Control Backbones

```
① run state      run_manifest.json → run_state.json → artifact_registry.json → event_log.jsonl
② evidence/claims  dws_response → evidence_span_registry.json → field_claim_graph.json
                → field_drafts.json → [freeze transaction] → field_ledger.json
③ gates          six deterministic gates → gate_report.json(evaluations + findings)
④ adjudication/delivery  adjudication_ledger.jsonl → support_matrix.json → support_panel.html
```

BriefLoop has five backbones; InvoiceLoop needs only four: the memory-and-improvement
backbone (cross-run learning) does not apply to a single-invoice demo.

---

## 4. Data Model

### EvidenceSpan — evidence span
```python
span_id: str            # ES-####, assigned by Python
doc_id: str
page: int
bbox_rel: tuple         # normalised (x0,y0,x1,y1); bridges DWS pixel space and render space
crop_sha256: str        # content hash of the crop image
ocr_text: str           # independent OCR text of this region (DocILE word-level OCR)
printed_label: str      # the label printed next to the value, verbatim, e.g. "Gross Amt:"
source: str             # dws_source_bbox | full_page
```

### FieldClaim — atomic claim
```python
claim_id: str           # FC-####, assigned by Python; drafts must not pre-write it
doc_id: str
field: str              # invoice_number | total_gross | ...
value: str              # the raw text before normalisation
normalised: str         # after normalisation under the pre-registered rules
span_ids: list[str]     # the bound evidence spans
drafted_by: str         # dws_understand | dws_agentic | vision:<model>
```

### The **edges** of the atomic claim graph
The invoice claim graph is more concrete than the brief's: edges are verifiable arithmetic
identities, not semantic associations.
```python
("total_net", "total_vat") --sum--> "total_gross"      # C1
"total_gross" --equals--> "amount_due"                 # C2
"issue_date" --before--> "due_date"                    # C3
```

### SupportRow — one row of the support matrix (four dimensions, not one score)
```python
claim_id: str
support_strength: "corroborated" | "single_source" | "unsupported"
source_tiers: list      # dws_extraction / independent_ocr / vision_reading / arithmetic
applicability: "matches" | "label_convention_disputed" | "out_of_scope"
limitations: list[str]
requires_adjudication: bool
gate_verdicts: dict     # gate_id -> pass | warning | fail | unavailable
```

**The "applicability" dimension exists for convention conflicts.** The evidence can fully
support a value while the dispute is that "Gross on the page" and "gross under EN 16931"
are not the same concept. The six rounds counted these into error rates, conflating two
different things — of Round Five's 20 shared errors, 5 had exactly this shape.

### Runtime criterion for `label_convention_disputed` (no ground truth needed)

Advertising-agency invoices: Gross is the rate-card price and Net is the **amount actually
paid** after the 15% agency commission; under EN 16931 gross is what is actually paid. The
two vocabularies point in opposite directions.

**The criterion uses only three values returned by DWS itself:**

```
amount_due ≈ total_net  AND  amount_due ≠ total_gross
    → applicability = "label_convention_disputed"
```

That is, "the page lands the amount due on the Net side". Measured (60 new documents; 15 of
them have all three values present with gross ≠ net):

| doc | gross | net | due | net/gross |
|---|---|---|---|---|
| 047651e5 | 10,000.00 | 8,500.00 | 8,500.00 | 0.850 |
| 049ae2c3 | 285.00 | 242.25 | 242.25 | 0.850 |
| 05ec7dea | 589.00 | 500.65 | 500.65 | 0.850 |
| 060b4258 | 3,612.00 | 3,070.20 | 3,070.20 | 0.850 |
| 067e90fb | 672.00 | 403.20 | 403.20 | 0.600 |

5 cases detected, of which **4 carry the 0.850 signature of the 15% agency commission**.

**This criterion is computable at runtime** — it needs no ground truth, only the three DWS
return values. A hit marks `requires_adjudication`; `limitations` records both readings,
and it **does not enter the error rate** (Charter clause Five).

### GateFinding
```python
finding_id, gate_id, severity, blocking_level      # per the BriefLoop contract
repair_owner: "human" | "re_extract" | "vision_reread"
recommendation: str
evidence_ref: str                                   # points to a span_id or claim_id
```
Contract invariant: `blocking == (blocking_level == "blocking")`.

---

## 5. Three Control Transactions

### 5.1 Extraction transaction `extract`
Call DWS → **freeze the raw response as an artifact keyed by content hash** → register
evidence spans from `source_bboxes` → render crops and full pages → build the atomic claim
graph.

Output: one `artifact_registry.json` entry + `evidence_span_registry.json` + events.

### 5.2 Freeze transaction `freeze` — the system's critical line of defense
| Step | Writer | Action |
|---|---|---|
| 1 | Model | writes `field_drafts.json`, **without claim_id** |
| 2 | Python | rejects pre-written IDs; rejects rows that cannot bind to registered spans |
| 3 | Python | assigns stable `FC-####` |
| 4 | Python | freezes `field_ledger.json` + sha256, appends an event |

**The binding rule of step 2 (executable, not declarative):**

> A draft row asserts `(doc_id, field, value)`. Python checks whether that `value` appears
> in the independent OCR text of **the entire document with that `doc_id`** (token match
> ≥80% after normalisation). No match → the draft is not talking about this invoice: reject,
> record a `draft_binding_rejected` event, **it never enters the ledger**.
>
> **Afterwards**, record which registered evidence span the value falls inside (or that it
> falls in none) — this determines `support_strength`; it **does not determine acceptance**.

⚠ **It must be document-level, not span-level.** Span-level (requiring the value to fall
inside a DWS-registered bbox) measurably falsely rejects **26–28%** of legitimate answers:

| Vision model | Answers | Document-level rejects | Span-level rejects | Span-level false rejects |
|---|---|---|---|---|
| Kimi K3 | 140 | **14** | 50 | 36 (26%) |
| Opus 5 | 146 | **9** | 50 | 41 (28%) |
| GPT 5.6 SOL | 168 | **118 (70%)** | 138 | 20 (12%) |

The falsely rejected rows are exactly those where "DWS returned no value or boxed the wrong
place, and vision reading found it elsewhere on the page" — **that is the only place vision
reading has incremental value** (Round Six: the ground truth of the escaped true errors was
printed on the page in 8/8 cases). A span-level rule kills the most valuable part of the
system as if it were error.

**The GPT 5.6 SOL mis-binding incident would be rejected by the document-level rule on 118
rows (70%).**

### 5.3 Gate transaction `gate`
Runs after binding to **exact artifact revisions and hashes**. When signatures disagree, the
"refuse to run" lands in two places (wording aligned 2026-08-04: the gates themselves do not
re-verify signatures; refusal happens downstream): before appending an adjudication,
recompute the review_snapshot, and if artifacts were touched after the run, **refuse to
record that adjudication** (snapshot-consistency check in `adjudicate.py`); bundle verify
recomputes the same snapshot id offline and fails if any component was swapped. This is
where recomputability comes from: same input hashes → same adjudications.

Output: `gate_report.json` (evaluations + findings) + events.

---

## 6. Gates (six, deterministic, no model calls)

Per BriefLoop §3.3: deterministic auditing is executed by Python. All six gates **are
already implemented and tested in dws-derisk**.

| gate_id | Checks | Measured in the six rounds |
|---|---|---|
| `arithmetic_consistency` | net+vat=gross, gross=due, date ordering | reproduces the production convention 530/1000 |
| `field_wellformed` | amounts parseable, dates valid, numbers non-empty | — |
| `extraction_present` | whether DWS returned a value | of 359 flagged, 267 missing a value |
| `citation_holds` | whether the value lies in the citation region DWS claims for itself (**independent OCR**) | T1 silent 4.4%→3.1% |
| `cross_mode_agreement` | understand vs agentic | lift 2.40×, **known to be non-independent** |
| `visual_corroboration` | whether full-page vision reading supports it | three models, lift 1.29–1.33 |

**Negative-finding rule (Charter clause Four)**: a gate that cannot run =
`blocking_level: "blocking"`, severity `high`. The 267 `extraction_present` failures are 267
blocking findings, each with a repair route.

**`visual_corroboration` runs on all fields, not only the flagged ones.**
The six rounds' stratification let the most dangerous errors escape: unflagged TIER1 fields
still carry **7.8% true errors**, including 5× (`422,539` vs `83,625`) and 8× (`6467` vs
`800`) amount errors that **pass all six gates** — because they are self-consistent
misreads. And measured on these 8 cases, the ground truth was **printed on the page in
8/8** — vision reading had a chance to stop every one of them.

---

## 7. Triage — a projection of the support matrix, not a separate feature

The support matrix sorted ascending by `support_strength` is the review queue. Measured
(60 new documents, TIER1 fields):

| | Deviation rate |
|---|---|
| flagged by gates | **50.0%** (43/86) |
| not flagged | 11.8% (12/102) |
| **concentration** | **4.2×** |

**Inspecting 46% of fields (86/188) covers 78% of deviations (43/55).**
End to end: deviation 29.3% → 10.6%, with 35.5% manual review; each 1pt of human review
buys 0.52pt of deviation reduction — **1.8×** that of purely deterministic checks.

**Triage does not require any tier to be "trustworthy"**, only that the ordering beats
random — 4.2× already proves that. This turns the 7.8% in §6 from "fatal flaw" into "one
honestly labeled cell".

---

## 8. Calibration and Its Qualifiers

`support_panel` shows each gate's **measured interception rate**, from the six rounds of
pre-registered experiments. Per Charter clause Six, **all three qualifiers must be shown
alongside**:

1. The gates were designed **after seeing Round One data** (self-reported in
   `THRESHOLDS.md §6c B-4`), with an optimism bias.
   ~~Held-out confirmation never executed~~ → **executed on 2026-08-02** (a 100-document
   DocILE hold-out; criteria pre-registered and frozen before execution; H1–H6 all passed;
   triage lift 3.04× > the 1.5 line; the numbers and the deviations from the registered
   predictions, printed as-is, are in the results section of `docs/HELDOUT.md`)
2. The DocILE annotations are themselves disputed — in Round Four, document-by-document
   vision reading found **8 of 14 cases were annotation errors**
3. The calibration set is entirely US radio advertising invoices; the hold-out reproduced
   the triage concentration within DocILE's full type range, and **performance outside
   DocILE remains unknown**

---

## 8b. Known Boundaries

**Tokenisation shreds small amounts into high-frequency tokens.** The binding check splits
on `[a-z0-9]+`; `$0.00` → `['0','00']`, which matches almost any document — such drafts are
accepted no matter which invoice they bind to.

Measured against strict tokenisation (amounts kept whole, only separators stripped): the
mis-bound document loses only **1 row / 168** more, while each of the two legitimate
readers gains 1 extra false reject. **Net benefit is negative, so it stays unchanged.**

But this corpus contains only 1 such case, and **zero-tax invoices are common in the real
distribution**. On a different corpus this failure mode amplifies and needs retesting. It
is recorded here; do not assume it is absent just because the tests are green.

**Both sides must use the same tokeniser.** If the document side additionally collects
"whole-word, punctuation-stripped" tokens, `$5.00` strips to `500` and collides with the
amount 500. Measured: `0486b911` contains exactly two `$5.00` occurrences — enough to flip
a mis-bound `$8,500.00` row from `2/3 reject` to `3/3 accept`. The docstring of
`freeze.normalise_tokens` records this; do not "optimise" it back.

## 9. What Is Claimed and What Is Not

**Claimed**
- Every field carries a mechanically verifiable support relation: evidence spans,
  four-dimensional strength, six gate verdicts, repair routes
- The support matrix can be **recomputed with zero API calls** from saved responses
- The triage ordering is measured on 160 pre-registered documents: 4.2× concentration, 78%
  coverage
- The freeze transaction structurally rejects mis-bound rows (measured: rejects 70% of one
  real incident, 118/168, §5.2)

**Not claimed**
- **No claim that DWS is trustworthy, and no claim of improved extraction quality.** The
  six rounds say the opposite, **and that goes into the demo**
- No claim of semantic correctness — the deliverable is a support matrix, not "this value
  is right"
- No claim of unattended operation — unsupported items are, by design, for humans to look
  at
- No claim of production readiness — 160 documents, English, single vendor, single point
  in time

---

## 10. Explicitly Not Done

These BriefLoop mechanisms are designed for **concurrent multi-agent, long-horizon
resumable runs**. Single-invoice extraction is single-writer, a few seconds, no concurrent
modification — **copying them over is cargo cult**:

optimistic concurrency (`store_revision_conflict`), Unit of Work, replay by request
fingerprint, artifact supersession, repair cycle, finalize render, the cross-run
improvement ledger.

**The three that stay have nothing to do with concurrency**: content-addressed freezing,
draft/freeze separation, negative findings are blocking.

---

## 11. Milestones (the deadline decides how far to go; every tier is independently demoable)

| M | Deliverable | Depends on |
|---|---|---|
| **M0** | `extract` + evidence span registration + claim graph | `extract.py` already exists |
| **M1** | six deterministic gates + `gate_report.json` | all check logic already exists |
| **M2** | `freeze` transaction + binding rejection | newly written, ~150 lines |
| **M3** | four-dimensional support matrix + `support_panel.html` | newly written, the demo's main screen |
| **M4** | human adjudication records + `audit_bundle.zip` | optional |

**M0–M1 is mostly porting existing dws-derisk code.** The genuinely new work is M2 and M3.

---

## 12. Four Settled Decisions (reversible)

Asked four times with no answer; proceeding on the most reasonable defaults so work can
start:

1. **Code location**: `~/Developer/invoiceloop/` (standalone repository, product identity);
   `~/Developer/dws-derisk/` stays a **calibration archive** that InvoiceLoop points to via
   configuration
2. **Panel form**: static HTML, demoable offline, no server needed
3. **Input**: v0 is DocILE only (complete evidence chain, recomputable with zero API
   calls); an upload path comes later, and it must be labeled "not in the calibration set"
4. **Deadline**: unknown → milestones are designed so every tier is independently
   demoable; the deadline only decides which tier we stop at

## 13. H0 Integrity Foundation (2026-08-03, driven by external review)

Mechanisms established after external review found four problems — "freezing not actually
enforced" among them — that would dissolve the core promises (full account:
`docs/H0_INTEGRITY_2026-08-03.md`):

- **Runs are immutable**: a non-empty output directory is always rejected; there is no
  `--force`, and deleting history is not required either; the workspace advances
  generation by generation as `runs/run-NNNN`, and `current.json` is only a rebuildable
  pointer. A rerun whose input fingerprint (content hashes of PDF+OCR+raw+schema+vision
  answers) matches = a replay of the existing run; a half-finished run (no event_log) must
  not be replayed and is left in place as the scene.
- **Review snapshot**: every human adjudication binds to a `review_snapshot_id` (hashes of
  five components: input manifest + artifact registry + evidence spans + frozen ledger +
  gate report), not to the ledger alone. Before appending an adjudication, the snapshot is
  first verified to still match the artifacts on disk; a mismatch blocks.
- **Adjudication chain**: the `claim_id↔doc_id↔field` triple must match exactly; `correct`
  must carry a corrected value, the others must not; a second decision on the same slot
  must explicitly supersede the current tip; current state is a projection of the
  supersession chain, and a broken link is explicitly marked as a conflict; adjudications
  bound to a different snapshot are marked orphan — not projected, but not hidden.
- **The panel is a projection**: rebuildable at any time from the artifacts on disk
  (`render --run`); a render failure does not roll back adjudications already on disk.
- **Machine events deliberately carry no wall clock**: `event_log.jsonl` has only `seq`, no
  timestamps — a determinism trade-off (replaying the same inputs must be byte-identical,
  and a wall clock would break that); time is injected only by humans at adjudication time
  (`decided_at`; in the workbench the server stamps it at click time).
- **Bundles are fully self-contained**: upstream evidence is accepted against the shas
  recorded in input_manifest (swapped/missing = blocking; already absent at run time = goes
  into notes); the vision `answers6.*.tsv` is captured into the run/bundle too, so the
  workbench no longer depends on a mutable external vision directory; `verify` does
  three-layer offline validation (member hashes → snapshot component recomputation →
  adjudication binding).

## 14. H1 Review Workbench (2026-08-03, judge-facing)

Full account: `docs/H1_WORKBENCH_2026-08-03.md`. Form decisions:

- **A loopback web app with zero new dependencies**: stdlib http.server, 127.0.0.1 only;
  server-rendered HTML + progressively enhanced JS (without JS, everything except browser
  upload still works).
- **Humans write adjudications only**: `/decide` passes through the same adjudication
  validation as §13 — the workbench opens no back door; decided_at is stamped by the server
  at click time (the click = the human supplying the time); a second decision on the same
  slot automatically carries the current tip's supersedes in the form, and a stale
  submission = 400.
- **The review queue = the triage ordering, made walkable**: rows = matrix rows (ascending
  support strength); evidence (crop/OCR/printed label) in accordions; four decision
  buttons + corrected value + problem/reason text fields (required, with quick problem
  tags); two-step confirmation.
- **The delivery report is a first-class citizen**: review completeness; the correction
  list (original value → corrected value + reason + signature); the residual-risk statement
  (errors outside the review queue are not zero) shown on the same screen as the §8
  qualifiers.
- **Visual discipline**: DWS/model values = purple (advisory, never green); human
  confirmation = blue; green only for deterministic passes; red = blocking; grey =
  unavailable.
