# 16 Class Absence Rules: propose → evaluate → promote All Passed (2026-08-09)

Basis table: [`DOCTYPE_ABSENCE_DEV_2026-08-09.md`](DOCTYPE_ABSENCE_DEV_2026-08-09.md).
Zero API throughout. Resulting harness **HAR-0017**, policy digest
`9b6df44236d1e22d19b760e1b1d786906f88c8d5a7d6ba58e5895982a699c7c7`,
files pinned into `docs/evidence/class_absence_2026-08-09/`.

## Conclusions

Development set 300 documents / 3,000 slots, HAR-0001 → HAR-0017:

| | HAR-0001 | HAR-0017 |
|---|---:|---:|
| human queue | 1,806 (60.2%) | **1,736 (57.9%)** |
| `auto_absent` | 0 | 70 |
| **silent_absent (vs DocILE ground truth)** | 0/0 | **0/70** |
| silent_wrong | 179/1,015 | **179/1,015** |

**−70 slots = −2.33pp, with neither class of silent error rising.** All 16 candidates passed
propose → evaluate → promote; not one was refused by the gate.

## How the numbers reconcile

The rules matched **107** slots (exactly the 107 predicted by `absence_by_class.py`), of which:

- **70** became `auto_absent` — this is the human work saved;
- **29** were sent back to humans by the 20% QA probe — by design; whether an absence holds
  must be observed continuously;
- **8** remain in the queue — these slots have other hard gate failures; absence rules do not
  override `slot_blocking`.

So 107 matches buy 70 slots of net savings. **The probe is not waste; it is the precondition for
this path to exist at all**: a slot wrongly judged absent will never be seen by anyone again;
there is no after-the-fact discovery, only sampling keeps observation alive.

## Promotion lineage (cumulative Δ vs HAR-0001 at each step)

| # | Rule | Δpp | # | Rule | Δpp |
|---|---|---:|---|---|---:|
| HAR-0002 | `AE-purchase_order-seller_vat_id` | −0.40 | HAR-0010 | `AE-contract-due_date` | −1.63 |
| HAR-0003 | `AE-purchase_order-due_date` | −0.63 | HAR-0011 | `AE-receipt-seller_vat_id` | −1.80 |
| HAR-0004 | `AE-confirmation-seller_vat_id` | −0.83 | HAR-0012 | `AE-credit_note-total_vat` | −1.90 |
| HAR-0005 | `AE-confirmation-total_vat` | −0.93 | HAR-0013 | `AE-estimate-due_date` | −2.00 |
| HAR-0006 | `AE-confirmation-due_date` | −1.03 | HAR-0014 | `AE-estimate-seller_vat_id` | −2.07 |
| HAR-0007 | `AE-credit_note-seller_vat_id` | −1.20 | HAR-0015 | `AE-purchase_order-total_net` | −2.17 |
| HAR-0008 | `AE-purchase_order-total_vat` | −1.37 | HAR-0016 | `AE-estimate-total_net` | −2.27 |
| HAR-0009 | `AE-contract-seller_vat_id` | −1.47 | HAR-0017 | `AE-estimate-total_vat` | −2.33 |

`absent_rule_truth_conflicts_candidate` is 0 at every step — this is the ground-truth check
that runs **before** any QA sampling; a rule that would swallow slots with real values is
refused right here, not left to probe luck. The step-by-step record is in
`docs/evidence/class_absence_2026-08-09/promotion_log.json`.

## Recompute

`runs/absence-dev-2026-08-09/runs/` (not in git; under invoiceloop-data):

- `run-0001` — HAR-0001 baseline
- `run-0002` — HAR-0017, the full deterministic pipeline re-run on the same evidence and schema

Both runs' `silent_absent` / `silent_wrong` are recomputed independently from DocILE
annotations, not via `improve`'s scorer. The corpus is `runs/absence-dev-corpus`: raw from the
three workspaces sealed1 / sealed2 / heldout merged into one place + `data` pointing at the
calibration corpus, **containing no promotion records**, so the baseline is necessarily the
in-package HAR-0001.

Re-running `run-0002` (the HAR-0017 arm) requires temporarily mounting the workspace harness
state into the corpus root and **unlinking it the moment the run finishes**:

```bash
ln -sfn ../absence-dev-2026-08-09/improve   runs/absence-dev-corpus/improve
ln -sfn ../absence-dev-2026-08-09/harnesses runs/absence-dev-corpus/harnesses
# … run pipeline …
rm -f runs/absence-dev-corpus/improve runs/absence-dev-corpus/harnesses
```

Unlinking is discipline, not fastidiousness: `pipeline.run`'s active harness comes from the
**corpus root** (`load_active(derisk_root())`), not the output directory. Leave promotion
records hanging on the corpus root long-term, and the next person running the "baseline" does
not get a baseline — the pitfall recorded in this document's last section is exactly this.

## Two caveats

- **This is the development set.** sealed1 / sealed2 / heldout were all read and tuned during
  development. −2.33pp and 0 silent_absent are **not conclusions on unseen data**.
- **SEALED-3 cannot be used to validate this.** That batch was consumed by its one-time
  unsealing (`SEALED3_RESULTS.md` §7), and these 16 rules were inspired precisely by its
  failure. Eligibility requires a separate SEALED-4 draw — see `SEALED4_PROTOCOL.md`.

## Two pitfalls hit along the way (recorded so we don't step in them again)

1. **When first building the development runs, each of the three corpora ran once, and
   sealed2-workspace contained promotion records**, so those 100 documents ran under HAR-0004
   while the other 200 ran under HAR-0001.
   `pipeline.run`'s active harness comes from the **corpus root**
   (`load_active(derisk_root())`), not the output directory. The mixed baseline got all 16
   candidates refused, with identical rejection reasons —
   sixteen different rules producing the same number means the rules are not what is acting.
   It only became meaningful after switching to a merged corpus root without promotion records.
2. The key `improve.gate_verdict` returns is `ok`, not `promotable`. Reading the wrong key
   turns "all passed" into "all refused".
