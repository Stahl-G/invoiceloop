# HITL R1/R2 round protocol (2026-08-10, frozen before Round 1 starts)

Basis: `docs/PHASE01_HITL_SUGGESTION_PLAN_2026-08-10.md` P0-3.
This file freezes on first commit; changing a single character after Round 1's
first adjudication = both rounds are void.

## 1. Corpus

- Pool: dual-mode saved documents from the four workspaces sealed1/2/heldout/sealed3
  ∩ broadcast strong/weak (the existing classification in
  `docs/BROADCAST_PILOT_SCOPE_2026-08-09.json`, not reclassified),
  excluding the 17 `h2_excluded` documents (human-seen in the terminated H2
  experiment; timing impure).
- **sealed4-100 never enters round corpora** — that is the qualification set's
  measurement surface; mining adjudications from it = tuning on the
  qualification set.
- R1/R2 each 100 documents, non-overlapping; seeds and sampling scripts land
  on disk in the same commit as the lists (`runs/hitl-r1/doc_list.json`,
  `runs/hitl-r2/doc_list.json`, each with sha256).
- Zero new DWS calls: only the understand/agentic responses already saved in
  the four workspaces.

## 2. Suggestion sources (frozen for Round 1, all offline deterministic sources)

| tag | Source | Notes |
|---|---|---|
| `derived` | derivation from independent OCR via `due_date.derive_due_date` | fills only slots where derivation succeeds; derivation rule pinned to `due-date-relative-term-v2` |
| `xmode` | the field's value in the saved response of **the other mode** for the same document | understand slots look at agentic and vice versa; cross-mode disagreement is itself an existing signal |

Both sources are deterministic, zero API, recomputable. If the ADK offline
batch succeeds, add the `adk` tag and state the model and date in the round
record; if it fails, the round is unaffected.

## 3. Measurement caliber

- **Human time per slot** = median of adjacent `decided_at` differences;
  intervals > 1h are treated as breaks and removed; report
  accept / correct / confirm_absent / reject quantiles per round
  (same method as run-0002, reporting only medians, not means — the
  overnight-contamination precedent).
- **Suggestion adoption rate**: denominator = slots whose `suggestion_seen` is
  `agree:<value>`; numerator = decisions that are accept with the claimed
  value normalized-equal to the suggestion, or correct with the corrected
  value normalized-equal to the suggestion. `agree_rejected` / `split` /
  `blind` are listed separately and do not enter the denominator.
- **Counterfactual queue rate**: `improve.evaluate`, development set; the
  numbers always carry the "development set" qualifier.
- Timing comparison (manual vs harness) is not in this protocol; separate
  effort.

## 4. Between-round discipline

- Same reviewer (stahl), **change the documents, not the person** — estimate
  "the human got faster" and "the system got better" separately; if they
  cannot be separated (the two rounds are not the same batch of documents),
  record the confounding in the results document as-is rather than
  overclaiming.
- Between the two rounds, only **deterministic** artifacts (gates/absence
  rules/suggestion templates) may be promoted, going through
  mine → human review → `improve.promote --approved-by stahl` →
  `improve.evaluate` counterfactual + the full pytest suite green; only then
  may Round 2 start.
- Forbidden: model weight adjustment, vocabulary deletion, caliber changes,
  touching any sealed set.
- Mid-round caliber rulings are written into the rationale at the time and
  into the results document afterwards; already-adjudicated slots are never
  rewritten (the same discipline as the two precedents, $0.00 / derived
  values).

## 5. Output

`docs/HITL_ROUNDS_R1R2_<date>.md`: three curves, two points each (human time
per slot, suggestion adoption rate, counterfactual queue rate) + confounder
declaration + all shas (lists, ledgers, promotion records).
