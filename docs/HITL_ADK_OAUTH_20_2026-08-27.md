# HITL experiment record: ADK OAuth 20-document standalone run (2026-08-27)

Status: **development set / exploratory results**. This record constitutes no
qualification test, no promotion basis, and no estimate of model extraction
accuracy.

Protocol background: this round reuses the 20-document broadcast corpus and
the `HAR-0023` payment-field scope of
[`HITL_NARROW_PROTOCOL_2026-08-14.md`](HITL_NARROW_PROTOCOL_2026-08-14.md),
but adds an ADK page-reading suggestion layer and performs human adjudication
in the workbench. It is therefore not a clean re-measurement of the original
protocol's pre-registered metrics, and cannot be spliced with the 2026-08-14
human-time or zero-touch numbers.

## 1. Conclusions first

- The ADK suggestion layer completed successfully on this round's 20 documents;
  20/20 with no ADK request failures.
- The narrow-release workbench actually recorded **32 human adjudications**:
  `accept 13`, `correct 11`, `confirm_absent 7`, `reject 1`.
- On the 7 `amount_due` rows satisfying both `label_convention_disputed` and
  `arithmetic_consistency = fail`, the human accepted the original value on
  every one.
- This supports an **applicability / attribution defect** judgment: the
  arithmetic gate computes the ordinary-invoice identity without numerical
  error, but treats "Gross as rate-card price, Net/Due as the amount actually
  payable after commission or discount" as the ordinary-invoice model
  `gross == amount_due`, and displays it at slot level as an arithmetic
  failure.
- This does not support turning off the arithmetic gate, nor the claim that
  "extraction got more accurate". The same batch of human adjudications still
  contains 11 corrections and 1 rejection, showing real extraction / binding
  problems in the queue.

## 2. Experiment identity and boundary

| Item | Record |
|---|---|
| Document pool | `docs/hitl_narrow_doc_list.json`, 20 DocILE broadcast-corpus documents |
| Document list SHA-256 | `20315c0daa606ad098bcce6e91d16b01dcfc635805e9f9049fa6c9336496f25d` |
| Workspace / run | local `/private/tmp/invoiceloop-adk-oauth-20.jqyavx/hitl-clean/runs/run-0001` |
| Harness | `HAR-0023` |
| Input fingerprint | `140726a760d533c72c422c509182b66f729ddf63567c2ecb0b32091c40fccf06` |
| Code revision | `2dfb7b7db3327123eda638dfef1fb55b528fb228-dirty` |
| ADK model | `gemini-3.7-flash` |
| ADK path | Vertex AI / `aiplatform.googleapis.com` / `global` |
| ADK auth | gcloud short-lived OAuth access token, memory-resident only; the token was not written to any artifact |
| Execution | parallel, 4 workers; 8 documents had succeeded earlier, this pass handled 12, 12 succeeded, 0 failed |
| Human identity | `stahl`; single warm reviewer, ADK suggestions visible at adjudication time |

9 key artifacts — the ledgers, approval ledger, ADK readings,
routing/matrix, closeout/mine reports, and the document list — are frozen
into the repo at
[`docs/evidence/hitl-clean-2026-08-27/postwalk/`](evidence/hitl-clean-2026-08-27/postwalk/)
(including `MANIFEST.sha256`). PDFs, OCR, and page-render images remain only
in the local workspace; the §8 hashes locate those external artifacts.
`code_revision` carries `dirty`, so this record cannot be read as a
qualification result on some clean Git commit.

## 3. Machine-side results (before human adjudication)

The numbers below are read / recomputed from this round's `support_matrix.json`
and `gate_report.json`; they describe machine stratification, not ground-truth
accuracy:

| Item | Count |
|---|---:|
| Documents / field slots | 20 / 200 |
| `corroborated` / `single_source` / `unsupported` | 128 / 4 / 68 |
| `requires_adjudication` | 114 |
| Full-matrix `human_queue` | 89 |
| `machine_decided` / `machine_absent` | 86 / 25 |
| `applicability_disputed` | 21 |
| blocking findings | 18 |
| admitted claims / rejected drafts | 269 / 132 |
| rejected drafts: `dws_understand` / `dws_agentic` | 66 / 66 |

`arithmetic_consistency = fail` totals 20 rows: `amount_due 7`,
`total_gross 7`, `total_net 2`, `total_vat 2`, `issue_date 1`, `due_date 1`.
Of these, 16 rows are `label_convention_disputed`.

The narrow workbench did not walk all 89 matrix human-queue entries; it took
out 32 by the payment contract: 24 contract-field entries (`invoice_number`,
`seller_name`, `amount_due`) plus 8 QA probes (`seller_vat_id`, `due_date`,
`total_net`, `total_vat`). So "32 adjudications done" does not mean all 200
fields were human-reviewed.

## 4. Human adjudication results

### 4.1 Totals

| Metric | Result |
|---|---:|
| Ledger adjudication rows | 32 |
| Documents covered | 16 / 20 |
| `accept` | 13 |
| `correct` | 11 |
| `confirm_absent` | 7 |
| `reject` | 1 |
| Adjudications that saw a suggestion | 19 / 32 |
| supersession | 0 |
| Adjudication identity | 32/32 `stahl` |

Human reason-code distribution: `CONFIRMED_ABSENT 7`,
`ROUTING_FALSE_POSITIVE 6`, `WRONG_FIELD_MAPPING 4`, `WRONG_VALUE 3`,
`BAD_SOURCE_BINDING 3`, `OTHER 3`, plus 6 rows with no reason code filled.

The deliverable projection currently stands at: 18 `ready_for_approval`, 1
`approved_for_export`, 1 `blocked`. There is also 1 separate approval record,
which cannot stand for the whole round having been approved or sent out.

One AP-0001 fact must be recorded as-is: the approved `075d4722` is a
**zero-adjudication document** — none of the 32 adjudications falls on it, the
approval record's `policy_disposed_fields` lists all 10 evaluated fields (all
disposed by HAR-0023 policy; no human read any slot), and the approval reason
is `good`. This was a legitimate action in this round (a human signed), but
the combination of zero-touch + a one-word approval reason is weak as a
product signal; recorded on file.

### 4.2 Suggestion adoption and human time (closeout caliber)

| Metric | Value |
|---|---:|
| Timed adjudications (excluded_gaps 2) | 29 |
| Median human time/slot | **112 s** |
| accept / correct / confirm_absent / reject medians | 78.5 / 167.5 / 157.5 / 119 s |
| Slots with a field-level suggestion | 19 / 32 |
| Suggestion state agree / agree_rejected / split | 15 / 3 / 1 |
| Adopted among agree slots | 14 / 15 (0.933) |

Against the 2026-08-14 census walk's median 52 s/slot: this round's narrow
queue is slower per slot, but that round was a ten-field census and this round
contains long-duration correct-type slots (167.5 s). The two rounds'
measurement calibers differ; they cannot be spliced, and per the rule in the
2026-08-14 record they are shown side by side.

### 4.3 Arithmetic gate / caliber-dispute queue

The 7 `amount_due` rows' machine results were all "arithmetic failure +
caliber dispute"; the human results accepted the original value in every case:

| doc_id | Gross | Net / Due | Human result |
|---|---:|---:|---|
| `5c1c7960b46f4dfc9a5a44db` | 1,040.00 | 884.00 | accept |
| `9a359ef4cc4644ae9b5caaa4` | 23,600.00 | 20,060.00 | accept |
| `a39706cb2762474cb3e155b4` | 9,335.00 | 7,934.75 | accept |
| `db60e02cb0074cd5baf3cf01` | 1,472.40 | 1,418.66 | accept |
| `0c7df66268614502b65f4a3f` | 1,125.00 | 956.25 | accept |
| `5a8c7ec3518c4daa978b4eb9` | 780.00 | 663.00 | accept |
| `ba388b327d254ed384f97624` | 2,040.00 | 1,734.00 | accept |

These 7 results cannot by themselves prove auto-release is possible; what
they prove is: under the current narrow queue and this human reviewer's
observation, the `amount_due` values match the page, and the machine's
ordinary-invoice arithmetic interpretation is insufficient to judge them
wrong.

### 4.4 Key case: frozen-binding false positive on thousands-separated amounts (`f47b8ee0...`)

`f47b8ee00eae416c94a083ca`'s three amount slots (`amount_due`, `total_gross`,
`total_net`) were **rejected for the same cause** at the freeze transaction:
DWS returned `1744.20`, the page prints `$1,744.20`. Tokenized by
`[a-z0-9]+`, the value side's tokens are `{1744, 20}`, the document side's
are `{1, 744, 20}`, the intersection is only `{20}`, coverage 0.5 < 0.8, and
all three drafts went `draft_rejected_at_freeze` → `unsupported` → into the
human queue.

- `amount_due` was inside the narrow queue and human-corrected to
  `$1,744.20` (HD-0020,
  `suggestion_seen: agree_rejected:$1,744.20` — the ADK reading also gave
  `$1,744.20`, but the suggestion layer cannot restore a DWS claim rejected
  at the freeze);
- `total_gross` / `total_net` are not payment-contract fields; they remain on
  the support matrix unseen by humans.

This is the in-the-wild shape of a known boundary in
[`ARCHITECTURE.md` §8b](../ARCHITECTURE.md): the tokenizer splits
thousands-separated amounts into high-frequency tokens. §8b previously
recorded "$0.00 split into high-frequency tokens causing **should-reject not
rejected**" (the false-negative direction); this case is the same tokenizer's
**false-positive direction** — a true value rejected merely for its format.
Both directions belong to the family §8b predicted would "amplify on a
different corpus and need retesting". The fix direction is format equivalence
for AMOUNT binding (`1744.20` ≡ `$1,744.20`, keeping the printed original),
not loosening the 0.8 threshold.



## 5. Key case: `0c7df662... / amount_due`

The adjudication is recorded as `HD-0022`:

```text
decision:      accept
value:         $956.25
reason_code:   ROUTING_FALSE_POSITIVE
suggestion:    agree:$956.25
```

The independent OCR of the document's page 2 also reads:

```text
Gross Amount:      $1,125.00
Agency Commission: ($168.75)
Net Amount Due:    $956.25
```

The page relation is:

```text
1,125.00 - 168.75 = 956.25
```

But `dws_understand` returned the inputs:

```text
total_net   = 956.25
total_vat   = 68.75
total_gross = 1,125.00
amount_due  = 956.25
```

So the current gate computes per the ordinary-invoice identity:

```text
C1: 956.25 + 68.75 = 1,025.00 != 1,125.00
C2: 1,125.00 != 956.25
```

`68.75` has no page VAT label or binding support; the support matrix lists
the value as unsupported, and it cannot be used to prove `amount_due` wrong.
The defect here is not floating-point arithmetic, but:

1. generic C2 treats `total_gross == amount_due` as applying to all invoices;
2. arithmetic failure is attributed along feeding fields, so a correct
   `amount_due` also gets fail;
3. `matrix.py` already recognizes `label_convention_disputed`, but
   `routing.py` emits `GATE_FAIL:*` first, masking the caliber dispute and
   the specific identity.

This is a known interpretive defect; the historical record is at
[`ARM_RUN_LOG_2026-08-08.md:184`](ARM_RUN_LOG_2026-08-08.md:184).
Implementation locations:
[`gates.py:74`](../invoiceloop/gates.py#L74),
[`matrix.py:28`](../invoiceloop/matrix.py#L28), and
[`routing.py:253`](../invoiceloop/routing.py#L253).

## 6. Other human signals

This round is not "every enqueue is a false positive":

- 3 `WRONG_VALUE`, 4 `WRONG_FIELD_MAPPING`, 3 `BAD_SOURCE_BINDING` show model
  values or field bindings still produce real problems;
- 7 `CONFIRMED_ABSENT` show "the model returned nothing" and "the page is
  explicitly missing it" need to be separated;
- 1 `reject` shows the page has no corresponding invoice number;
- 6 explicitly used `ROUTING_FALSE_POSITIVE`, including this record's
  arithmetic / caliber cases.

So this round's improvement signals should be split into typed findings:
arithmetic-model applicability, field mapping, page binding, and genuine
absence — not compressed into a single "routing accuracy".

## 7. Reusable conclusions and limitations

Reusable engineering conclusions:

1. Keep the underlying C1/C2 failure records, but bring the identity ID,
   input values, and failing fields to the workbench;
2. For recognized caliber disputes, the UI should present
   `LABEL_CONVENTION_DISPUTED` as the primary explanation and the arithmetic
   failure as context, rather than implying an `amount_due` value error;
3. If the gate's scope of applicability is to change, build a versioned
   billing-model / commission-or-discount semantic contract and add regression
   samples; do not turn off the arithmetic gate globally;
4. This run stays frozen; fixed rules must not be written back as "it passed
   all along";
5. Document-level binding for AMOUNT fields needs **format equivalence**:
   `1744.20` and `$1,744.20` are the same value (the §4.4 case; three
   true-value slots rejected). Equivalence must be done at the binding layer,
   keeping the printed original — not by loosening the 0.8 threshold, which
   would also let in the false-negative family recorded in §8b.

Limitations: the 20 documents are a development set; the human reviewer is a
single warm reviewer; the 32 rows are a narrow queue, not the full 200-slot
matrix; 19 rows saw suggestions with ADK and adjudication co-present; the
code revision carries dirty; this round had no blinding, no independent
ground-truth review, and no qualification semantics. Two further procedural
gaps are recorded as-is: no prewalk evidence-freeze commit was made before
adjudication began (the reading artifacts were on disk before adjudication,
but the "freeze first, adjudicate second" property can only be asserted by
this record, not proven by commit ordering); the `suggest_provenance` freeze
was not run, so the 19 suggestion-bearing adjudication rows have an empty
`suggestion_model` (`suggestion_seen` was recorded by the workbench from the
live TSV) — exact reconciliation of suggestion provenance (the P1 caliber) is
not assessable this round. This record therefore reports no accuracy, no
lift, no safety promotion, and no generalization conclusions.

## 8. Artifact index and hashes

Local external-artifact root:

```text
/private/tmp/invoiceloop-adk-oauth-20.jqyavx/hitl-clean/runs/run-0001
```

| Artifact | SHA-256 |
|---|---|
| `run_manifest.json` | `3c5073e4639a9b8868a5264999dfc94fbed4b4d608883ccbcf03b9f85222cca5` |
| `input_manifest.json` | `8604337e9db917ec36c4079d2b9ec9b24ea56f5a24f35ce5932915ba89fe361a` |
| `oauth_run_metadata.json` | `247851a7dc8ae965b8654d9eab1cc26cf1cbf80063d572004cae88e538a34163` |
| `vision/invoice_read.json` | `e4d009b3ed682d59bfbe471a2ce9cd2f14da916bfe565714936d461d6d96c09d` |
| `adjudication_ledger.jsonl` | `76046cbcb0991681f6a85d2f3c386f6d1e47cb20683195cbcf5cb7797c3b55f0` |
| `approve_ledger.jsonl` | `d221a6a5058f31c37089d3cb51d85685d6a2d72d588fc27c813596bead93bfd0` |
| `support_matrix.json` | `f7b24e88dc02fa82279b910e02dd5c90cfa9c1db255aba7dfe7e5aede0f958d2` |
| `gate_report.json` | `e9a5ea845d5cf10300cb51c1e6638f2312fa95b562f6a15ad96e6d4c8411604e` |
| `routing_report.json` | `cbf358a87b2671d483998a44e122b68257a8fd884d1dfc10b5d6f5e3f6fd69b9` |
| `review_snapshot.json` | `40ca7b947d2bb32fbed7d1cbac2ec8e39412d767cb68696185e7d7fb36714047` |
| `deliverable.json` | `9dc93929e6d856af32c16b723f550fad58bebd72a99beebc64ac2e0b501cffdc` |

review snapshot ID: `24710c22ecf53504464af4ca2655cd8a2b8e18e6c3267c8440abccd30f70694a`.
