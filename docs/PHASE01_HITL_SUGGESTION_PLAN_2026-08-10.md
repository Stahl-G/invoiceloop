# Phase 0+1 plan: HITL + offline-suggestion multi-round optimization (2026-08-10)

Goal: **turn "increasingly useful" into three measurable curves**, carried
into the 8/17 opening window:

1. Human time per slot (median seconds, run-0002 caliber: adjacent
   adjudication time differences, overnight intervals excluded)
2. Suggestion adoption rate (adopted / slots where a suggestion is present and
   adoptable)
3. Counterfactual queue rate (development set, `improve.evaluate`, with the
   development-set qualifier)

**Not goals**: zeroing whole documents, driving down silent_wrong, the "the
AI is learning" narrative. All three are vetoed respectively by SEALED-3/4
data, the qualification process, and the charter; this plan touches none of
them.

## 0. Status anchors (verified before work, 2026-08-10)

**Already landed, do not redo:**

- The four UI fixes landed on 2026-08-08
  (`docs/ARM_RUN_LOG_2026-08-08.md` §post-termination):
  required-rationale moved down into `adjudicate.py:128`; highlight box with
  transparent fill + outline + "hide highlight box" + "open unboxed original"
  (`workbench.py:674,792,1902`); form 400 keeps entered content;
  reason codes follow the decision. Phase 0 only does **regression
  confirmation**, no more fixing.
- The slot-level suggestion channel already exists: reads
  `vision/answers6.<tag>.tsv` (`dws.py:101 load_vision_answers`, new readers
  auto-registered by tag), adjudication page `_vision_suggest`
  (`workbench.py:1530`) — reader agreement gives an "adopt" prefill button
  (fills the form only, writes nothing to the ledger), disagreement is laid
  out, all-abstain is shown honestly, and if the same value was
  freeze-rejected before, the adopt button is **not** given. Normalization is
  the same function as the dual-mode gate.
- The rule-level advisor layer already exists: `invoiceloop suggest` →
  `improve/suggestions.json` (`suggest.py`), with the improvement page
  showing adoption / trial evaluation / signed promotion.
- Improvement control plane: `improve.mine` / `improve.evaluate` /
  `improve.promote` (`improve.py:36/921/1377`), signed promotions.
- Human-time-per-slot measurement: ledger `decided_at`; run-0002 already used
  the same analysis method (median 28s, accept 20s / correct 66s).

**Gaps (what Phase 0 must fill):**

| # | Gap | Notes |
|---|---|---|
| G1 | offline suggestion injector | TA-arm/ADK-pilot output is not `answers6.<tag>.tsv` format; need a conversion script that writes the TSV **offline**, so neither demo nor rounds depend on live APIs (decouples deepseek/Gemini quota incidents from the demo) |
| G2 | structured record of suggestion handling | adoption can currently only be inferred from rationale text traces; need an optional field submitted with the form (suggestion presence state: agree/split/blind/none), into a new ledger field — adding a field append-only is legal |
| G3 | timing protocol frozen | the human-time measurement caliber for both rounds (person change/document change/exclusion rules) must be written before the match, otherwise the curves are suspect the moment they appear |
| G4 | round corpus and exposure registry | rounds use broadcast development-pool documents not inside sealed4-100; once used, register into `docs/development_exposure_manifest.json`, excluded from SEALED-5 sampling |

## 1. Phase 0 (pre-match, pure engineering, no qualification actions)

### P0-1 Suggestion injector `scripts/suggest_inject.py`

- Input: any `{doc_id, field, value, note}` table (TA-arm adjudications, ADK
  broadcast pilot output, deterministic derived values all work as sources)
  + target run directory + tag name.
- Output: `<run>/vision/answers6.<tag>.tsv`, going through
  `load_vision_answers`' existing validation; multiple sources = multiple
  tags = multiple readers, and the agree/split/blind UI takes effect
  naturally.
- Suggestion source priority (round one): ① deterministic derivations
  (due_date inference, gate arithmetic) tagged `derived`; ② the ADK pilot
  offline batch (run once, retries allowed, failure does not block the
  round); ③ TA-arm artifacts used only where documents overlap and
  repurposing is noted (H2 is terminated; paired results are never reported —
  this goes into the round record).
- Acceptance: read-only acceptance against `runs/arm-h2` — after injecting a
  synthetic tag, the adjudication page shows suggestion rows, with at least
  one case each of disagreement/abstain/freeze-reject; `pytest tests/` all
  green.

### P0-2 Suggestion-handling record (a small change in two places, not in the frozen surface)

- `workbench.py` `_decide_form`: at render time, write the suggestion state
  (`agree:<value>` / `split` / `blind` / `none`) into hidden input
  `suggestion_seen`.
- `adjudicate.py::append_adjudication`: accept optional
  `suggestion_seen=None`, passed as-is into the ledger entry; default None,
  old ledgers unaffected.
- Acceptance: new tests — one submission with and one without the field,
  byte-level ledger checks; 761 all green.

### P0-3 Timing protocol (half a page, frozen pre-match)

Written into the round workspace's `protocol.md`:

- Same reviewer (stahl), 100 documents per round across two rounds,
  **change the documents, not the person** — estimate "the human got faster"
  and "the system got better" separately; if inseparable, record the
  confounding in the results as-is rather than overclaiming.
- Human time per slot = median of adjacent `decided_at` differences;
  intervals > 1h treated as breaks, removed; report
  accept/correct/confirm_absent quantiles per round.
- Suggestion adoption rate denominator = slots whose `suggestion_seen` is
  agree; numerator = final value normalized-equal to the suggestion with
  decision accept/correct at the same value.
- Between the two rounds, only **deterministic** artifacts (gates/absence
  rules/suggestion templates) may be promoted, passing `improve.evaluate`
  counterfactual + the full test suite; model weights, vocabulary deletion,
  and caliber changes are all forbidden.

### P0-4 Round corpus

- Source: the broadcast development pool (scope pool strong 2725 / weak 1471)
  minus sealed4-100; draw non-overlapping 100-document samples each for
  Round-1/Round-2; lists land on disk in `runs/hitl-r1/doc_list.json`,
  `runs/hitl-r2/doc_list.json`, shas recorded in the round record.
- Extraction: **zero new API** — reuse saved responses; documents missing
  responses are swapped out directly, no top-up sampling.
- Run the pipeline to produce run artifacts → P0-1 injects suggestions →
  `workbench --review-scope` starts the server.
- After the two lists + round adjudications are done, register into
  `docs/development_exposure_manifest.json`; SEALED-5 list generation
  excludes per the manifest (existing mechanism, no code change).

## 2. Phase 1 (first week of the window, two HITL rounds)

### Round 1 (about 3.5–4h human time)

1. Start the workbench on `runs/hitl-r1`; the reviewer walks the entire queue
   under the P0-3 protocol (expected ~470 slots @ 47% queue rate).
2. Close the ledger, record sha256; run the analysis script for:
   human-time-per-slot quantiles, suggestion adoption rate, decision-type
   distribution.
3. `improve.mine` produces candidates → item-by-item human review → promote
   deterministic candidates only: `improve.promote --approved-by stahl`,
   promotion records land on disk.
4. `improve.evaluate` counterfactually validates the post-promotion harness
   (development set) + `pytest tests/` all green; only then may Round 2
   begin.

### Round 2 (about 3.5–4h human time)

5. Same protocol, `runs/hitl-r2` (a new 100), queue produced with the
   post-promotion harness.
6. Close the ledger and run the round analysis, side by side with Round 1:
   three curves, two points each + qualifiers.
7. Produce `docs/HITL_ROUNDS_R1R2_<date>.md`: numbers recorded as-is,
   including the confounder declaration (learning effects) and caliber
   rulings (rules the reviewer fixed mid-round all written into rationale and
   the document).

**Time budget**: Phase 0 about 1.5 days of engineering; Phase 1's two rounds
about 8h human time + 2h analysis.
**Cost**: zero new DWS credits (if the ADK pilot offline batch fails, use
deterministic derivation sources only).

## 3. Discipline (in effect throughout)

- Do not touch the frozen surface: changes to policy/gates/normalization/
  routing/scorer all go through the mine → evaluate → promote signed process,
  never direct edits.
- Touch no sealed set; no tuning on SEALED-3/4; round numbers always carry
  the "development set" qualifier.
- The suggestion layer only prefills the form and never writes to the ledger;
  a suggestion whose same value was freeze-rejected never gets an adopt
  button (existing guard; the injector must not bypass it).
- Never say externally "the AI is learning"; the framing is "human
  adjudications settle into deterministic rules, promoted through frozen
  evaluation".
- Any mid-round caliber ruling (precedents such as \$0.00 and derived values)
  is written into the rationale at the time and into the results document
  afterwards; already-adjudicated slots are never rewritten.
