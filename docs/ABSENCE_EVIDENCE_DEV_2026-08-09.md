# Page-Evidence Absence: Development-Set Measurement and One Promotion (2026-08-09)

The previous document is [`DOCTYPE_ABSENCE_DEV_2026-08-09.md`](DOCTYPE_ABSENCE_DEV_2026-08-09.md)
(class-conditional absence; 16 rules promoted into HAR-0017). This one continues from it: class
rules **cannot enter the invoice class**, and 568/722 of the remaining missing-value slots are
invoice.

Zero API throughout. Resulting harness **HAR-0018**, policy digest
`30797d4e9edda174524a3f45cf4e1744b057d64908c0f2ba60a6dae941241d65`;
vocabulary version `c90cf8df16d82c2d…` (engine `absence-evidence-v2`).
Artifacts pinned at `docs/evidence/absence_evidence_2026-08-09/`.

## Conclusions

Development set 300 documents / 3,000 slots, one full deterministic pipeline run per arm:

| | HAR-0001 | HAR-0017 | **HAR-0018** |
|---|---:|---:|---:|
| human queue | 1,806 (60.20%) | 1,736 (57.87%) | **1,670 (55.67%)** |
| `auto_absent` | 0 | 70 | **136** |
| **silent_absent** | 0/0 | 0/70 | **0/136** |
| silent_wrong | 179/1,015 | 179/1,015 | **179/1,015** |

**Another 66 slots saved on top of the 16 class rules (−2.20pp), −4.53pp vs baseline, with
neither class of silent error rising.**

The HAR-0001 and HAR-0017 figures were **re-run under the new code** and match the morning-of-
2026-08-09 records digit for digit (1,806 / 1,736) — adding the absence probe changed no
existing harness's routing. This is not a side note: the probe is a new check added to the gate
transaction, and had it moved the old arms, the three-arm comparison would no longer be the same
ruler.

## Mechanism: swapping the bet for evidence

The class-conditional rule asks "does this class of document usually have this field" — a
statistical bet over same-class documents. This mechanism asks a different question, **about
this one document**: did the page ever print this field's label?

A slot falls into an absence rule's hands only when DWS returns no value. Then:

- the page prints `VAT` / `Tax` / `MwSt` and the like → this is not absence, it is a **missed
  extraction**; leave it to humans;
- the page has not one tax-amount label → the absence is vouched for by **this sheet of paper**,
  not by same-class documents.

That is why it can enter the invoice class while class rules cannot: `AE-invoice-total_vat`
saves 96 and swallows 3; `AE-invoice-seller_vat_id` saves 184 and swallows 7.

### Monotone safety: why this apparatus dares to fix a vocabulary on the development set

**Adding** a token to the vocabulary can only move a document from "absence holds" to "absence
does not hold"; the reverse is impossible. So a wider vocabulary is strictly safer: **adding
words can never create a silent error; it only forgoes a few saved slots.**
Fitting pressure pushes toward the unsafe side only when **deleting** words. The discipline is
therefore:

> After seeing results, adding words is unconstrained; deleting words equals fitting.

`tests/test_absence_evidence.py::TestMonotoneSafety` pins this direction down.

## Two vocabulary versions, both recorded as-is

**v1 is a blind test** (commit `da5337e`, written before any saves/silent numbers).
**v2 is post hoc**: words added after reading the v1 ledger. Both versions are recorded because
only the v1 column is blind.

| field | missing | held | v1 saves | v1 silent | v2 saves | v2 silent |
|---|---:|---:|---:|---:|---:|---:|
| `total_vat` | 143 | 19 | **124** | **0** | **124** | **0** |
| `seller_vat_id` | 266 | 4 → 27 | 256 | **6** | 238 | **1** |
| `due_date` | 207 | 115 | 84 | **8** | 84 | **8** |
| `total_net` | 80 | 28 | 51 | **1** | 51 | **1** |

What v2 added were **spelling forms** of US tax-ID labels on `seller_vat_id`: v1 collected only
abbreviations (`ein` / `fein` / `tin`), while US invoices actually print "Federal ID". Of the 6
tax IDs v1 missed, 5 sit right after `federal`; the 6th is OCR reading "USt-IdNr" as "ush id
nr". The additions went to the monotone-safe side, at the cost of 18 slots of saves.

**Only `AV-total_vat` passes in both versions**, and it passed in the blind one — that is the
single strong claim in this document.

### The line not crossed

After v2, `seller_vat_id` still has 1 silent left, because OCR read "Federal" as "federai"
(`5da5a0e2bded40ad8948d5eb`). **`federai` was not added to the vocabulary.** That is one OCR
typo on one particular document, not accounts-payable vocabulary; adding it would suppress
exactly that one document. Monotone safety cannot cover per-document fitting.

The 8 `due_date` silents are the same story. Examined one by one, they are dates the page labels
under other names — "transaction sale date time", "credit adjustment by eft", "donation received
payment status completed" — which DocILE labeled `date_due`. That is a caliber dispute (Charter
Five); the ground-truth column cannot settle it. **But this does not save the rule**: register
them as silent errors and refuse the rule.
"Maybe the annotation is wrong" must not be traded for a prettier number.

## Where the 124 hit slots went, reconciled one by one

Of the 143 total_vat missing-value slots, `AV-total_vat` finds page evidence holding for 124.
Those 124 slots:

| Destination | Slots |
|---|---:|
| `auto_absent` — this is the human work saved | **66** |
| sent back to humans by the 20% QA probe (by design) | 17 |
| already taken over by the 16 class rules (class rules judge first) | 16 |
| other hard gate failures (`UNSUPPORTED`, no evidence binding) | 25 |
| **total** | **124** |

66 slots net saved, fully consistent with the queue 1,736 → 1,670.

## Recompute

```bash
python3 scripts/absence_by_evidence.py     # saves / silent ledger per rule
```

The three-arm runs live in `runs/absence-evidence-2026-08-09/` (not in git):
`arms/har0001` baseline, `runs/run-0001` HAR-0017, `arms/har0018` this round.
`silent_absent` / `silent_wrong` are recomputed independently from DocILE annotations, not via
`improve`'s scorer.

Re-running a non-baseline arm requires temporarily mounting the workspace harness state into the
**corpus root** and unlinking it as soon as the run finishes —
`pipeline.run`'s active harness comes from `load_active(derisk_root())`, not the output
directory:

```bash
ln -sfn ../absence-evidence-2026-08-09/improve   runs/absence-dev-corpus/improve
ln -sfn ../absence-evidence-2026-08-09/harnesses runs/absence-dev-corpus/harnesses
# … run pipeline …
rm -f runs/absence-dev-corpus/improve runs/absence-dev-corpus/harnesses
```

## Three caveats

- **This is the development set.** sealed1 / sealed2 / heldout were all read during development.
  −2.20pp and 0 silent_absent are **not conclusions on unseen data**.
- **Vocabulary v2 is post hoc.** The v1 column is the blind test; `AV-total_vat` holding in both
  versions is its only extra reason for credit. Real eligibility takes SEALED-4 and nothing less.
- **SEALED-3 cannot be used to validate this.** That batch was consumed by its one-time
  unsealing (`SEALED3_RESULTS.md` §7).

## Old runs cannot judge these candidates, and they will not pretend they can

The absence probe exists only in runs executed after this change. Old `gate_report`s contain no
`absence_probes`; not one page-evidence rule matches, and the evaluation yields a beautiful
**zero change** — and zero change reads like "this rule had no effect", not like "these
evidence-gated candidates cannot be judged".

`improve.gate_verdict` therefore lists `absence_probe_status` separately: on seeing
`unavailable` it refuses and names the reason (re-run the run, then evaluate). Charter Four:
cannot-run is not pass, and it is not zero.
The regression is pinned at `tests/test_improve.py::TestAbsentEvidencedLoop::
test_a_run_without_probes_is_refused_not_scored_as_no_effect`.
