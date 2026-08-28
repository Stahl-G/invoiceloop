# L1 adaptive measured (2026-08-06)

Negative-result registration: dynamic downgrading (understand first, agentic
only for risky documents) **does not pay off on SEALED-1's 88 non-human
documents**, and must not be promoted to the default path.

Recompute:
`INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/adaptive_probe.py`
(zero API; `truth` / `eval_norm` share functions with `safety_metrics`).

## Numbers

| Quantity | Value |
|---|---|
| Non-human documents | 88 |
| `diagnose_risk` judged clean | **4** |
| Judged escalated | 84 |
| Dual-mode DWS calls | 176 |
| Adaptive calls | 172 |
| Savings | **4 calls (2.3%)** |
| `cross_mode=fail` slots lost on clean documents | 7 |
| Of those, judgeable with truth | 4 |
| understand correct against truth on these 4 slots | **0/4 (all wrong)** |

Breakdown of all 142 `cross_mode=fail` slots with truth:

| Who is right | Slots | Share |
|---|---|---|
| understand only right | 29 | 20% |
| agentic only right | 66 | 46% |
| Both wrong | 47 | 33% |

## Conclusions

1. The savings are negligible (2.3%), not a product-level cost lever.
2. On the "clean" documents that skipped agentic, of the lost dual-mode
   disagreement signals, **every one with truth was an understand error** —
   saving cost trades directly into silent errors.
3. Dual-mode disagreement is itself a high-value signal (agentic is clearly
   more accurate on the disagreement subset); it should not be economized
   away, nor auto-released by majority vote of a third reader (both-wrong
   still accounts for 1/3).

## Engineering guardrails

- `ingest --adaptive` stays **opt-in, not recommended**; sealed/heldout paths
  **hard-refuse** on encountering `adaptive.json` (`heldout.cmd_extract`).
- `diagnose_risk` must ignore keys outside `FIELD_KINDS` (real DWS almost
  always returns `invoice_type` etc.; a missing guard → guaranteed KeyError
  crash, see `tests/test_adaptive.py`).

## Not doing

Do not make adaptive the default; do not enable `--adaptive` on
sealed/heldout/demo; do not write "saved a few calls" up as a product selling
point.
