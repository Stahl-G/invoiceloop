# Response to the dual review (83/100 and 69/100) + senior adjudication (2026-08-05)

Review target: commit 4ce8728 (the state ledger). The two scores diverge sharply —
83 (engineering-increment view, no capping mechanism) and 69 (raw 77, but "no valid
final held-out" triggers a hard cap at 69). **The root of the disagreement is two
different rulers, not one side being wrong**: the 83 review looks at control-plane
engineering, the 69 review at evidence validity (held-out contamination +
submission materials). We checked both sides' claims against the code, item by
item — **all real** (nothing rebuttable this round; the verification record is
below).

## Disagreement diagnosis (why 83 vs 69 happened)

| | 83 review | 69 review |
|---|---|---|
| Framework | Incremental scoring, no ceiling | rubric + hard cap (no valid held-out → 69) |
| Main attack surface | Improve control-plane authority chain | Evidence validity (held-out contamination) + baseline contract |
| Shared conclusion | Engineering is mature, but "eval-gated" is not true to its name; no positive loop seen on data |

## Item-by-item verification and fixes (fixes 1–5, commit 3fa6184)

**The 83 review's four adversarial claims — all reproduced, all fixed:**

1. **promote can bypass evaluate** (improve.py old lines 268-276: a missing eval
   records None and still promotes) → Fix 1: a hard promote gate. **Hardened per
   senior adjudication item four**: rather than checking a file, promote
   **deterministically recomputes evaluate and compares byte-for-byte against the
   saved copy** — if the evaluation inputs (per run: snapshot id + routing/ledger/
   gate/adjudication/raw, five sha256 ways) were touched after evaluation, the
   recompute forks and is refused. Zero-coverage evaluations may not promote.
2. **active_harness.json is the real authority** (forge the pointer and you swap
   the harness) → Fix 2: active is replayed from the PROM **hash chain**
   (adjudication item five: consecutive filenames, record IDs matching filenames,
   the previous_promotion_digest chain, policy digest matching on both from/to
   sides); the pointer is just a cache, and any mismatch fails closed. The
   manifest is immutable after birth and no longer has a status field (no second
   authority).
3. **mine does not filter for actionable** (actionable was only computed in
   feedback.py and never consumed) → Fix 3: events are marked superseded (only the
   adjudication-chain tip counts) and random_qa; mine reports by bucket
   (all/actionable/superseded/random_qa/non-actionable reasons), and cohort
   statistics use only qualified events.
4. **Coordinated tampering passes the four verify layers** (alter matrix facts +
   routing_report + recompute the snapshot → all pass, because the semantics layer
   takes facts from the projection) → Fix 4: `matrix.derive_document_records` is
   the single source of truth (**document-level signature**, adjudication item
   six: the criteria for measurement-convention disputes span fields and do not
   fit at slot level), shared by build_matrix / the verify semantics layer /
   improve.evaluate in all three places; verify rebuilds facts from
   field_ledger + gate_report + raw
   understand, compares the three-way slot sets (missing rows / extra rows also
   count as tampering) + cross-checks matrix rows vs the authoritative rebuild +
   compares routing slot by slot including reason codes. **Behavior-conservation
   proof**: HEAD code and the refactored code each run the 100 held-out documents;
   support_matrix / routing_report / gate_report / field_ledger are **byte-for-byte
   identical** (r5-pre vs r4).

**The 69 review's two judgment points:**

5. **Baseline contract asymmetry** (raw DWS's missing values count as its silent
   errors while other systems' missing values go to humans; confidence borrows
   InvoiceLoop's value_present and queue_idx) → Fix 5: evaluator rewritten
   (adjudication item three): each of the five systems is scored from its own
   prediction source (raw saved responses vs the frozen ledger), wrong-value and
   missing-value reported separately, confidence ties broken deterministically by
   the fixed (doc_id, field) tie-break + best/worst/expected reported per entry
   cohort.
6. **Held-out contamination** (the C3/C8/drift-analysis cases came from those 100
   documents — we recorded this ourselves in the LIVE_TEST document) → the
   methodological verdict stands. Disposition: the old 100 is demoted to a
   regression/evolution set; SEALED-1 is truly sealed (next section).

## New numbers under a fair contract (baseline re-measurement, TIER1)

| System | Silent error rate (old → new) |
|---|---|
| raw DWS (trust everything) | 29.97% → 26.32% (of which missing-value release is 7.37pp) |
| Confidence threshold | 16.10% → **20.69%** (the old measure borrowed the frozen gate) |
| Dual-mode agreement | 14.95% → 11.27% |
| InvoiceLoop | 8.98% → 8.98% (unchanged — it always used its own ledger) |

Same-budget ranking (recall@30%): old "67.4% vs 67.4% tie" → new **48.0% vs 67.1%**
(CI [35.4,58.2] vs [58.5,76.9]). The old "tie" was partly an artifact of the two
borrowings (value_present borrowed the gate, queue_idx borrowed the ordering).

**Honesty boundary (consistent with the adjudication; not dressed up as a win)**:
the confidence entry-cohort range is extremely wide (at the 30% budget, [24%, 100%],
with a uniform-random expectation of 42.4%) — a two-level coarse confidence means
the real uncertainty of its ordering is large; a point-estimate lead + CIs that
happen not to overlap does **not** equal a robust win. The formal conclusion is
left to SEALED-1's preregistered secondary endpoint (paired diff + paired CI). The
"tie" is retained in BASELINE_COMPARISON.md's measurement-convention difference
table as a historical measurement, with a full account of how the two borrowings
produced it.

## SEALED-1 (truly sealed, per adjudication items one and two, commit 83c7204 + 5050dfb)

- Exclusion pool = `docs/development_exposure_manifest.json` (260 documents, each
  with reason/source: calibration 160 + old held-out 100 + vendored demo 3);
- Seed = **drand beacon round 6350246** (≈ 2026-08-05T14:00Z, the protocol commit
  at ~10:15Z — that round's randomness did not yet exist at commitment time, and
  anyone can recompute the list afterwards);
- Order: code/scripts/manifest/protocol frozen as a commit first (script sha256
  enters the protocol) → the draw → the list committed to disk → only then may DWS
  be called (200 calls, circuit breaker at 6000);
- Preregistered endpoints: primary = H1–H6 reuse the intervals + H7 running the
  closed loop (lifts the 69 cap); secondary = paired ranking comparison
  (10/20/30/40% budgets, paired CI, tie rules frozen in advance), **no
  presupposition that InvoiceLoop wins**; 100 documents may be underpowered; stated
  in advance that non-significance is not failure;
- Result-driven changes = this batch is voided and demoted to the regression set.

## Where this round's reviews were wrong

Nowhere. Every technical claim in both reviews held up under code verification
(unlike earlier rounds — errors like "the H6 denominator is 1305" or "DWS gives no
confidence" did not appear this round). The only remaining positional disagreement
is still explicit human adjudication of TIER1 (a release strategy the user
approved; change it through the R1 candidate process, not as a build default).
