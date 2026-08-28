# QUALIFICATION_NARROW_V2_2026-08-23 — contamination-recovery round protocol

> **English translation of
> [`QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md`](QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md),
> source sha256 `08a540b61e7eb8ab9aad0c2d534d48f289d63919831efcd2d18314a2587243dd`.**
> The Chinese original is byte-pinned by the machine decision chain
> (`qualification_decision.json`, plan `MANIFEST.sha256`) and is the sole
> authority; this translation exists for judges and may not reinterpret it.
> Translated 2026-08-28.

This protocol and its list were frozen before any v2 DWS call. v1 was revoked
under its own dirty-arm clause; see
`docs/QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md`. v1's 200 documents
became development-exposed data: they inform this protocol's priors and safety
endpoints but do not enter the v2 pool.

## 1. Two questions; forbidden to blur into one

1. **Workflow effect**: does HAR-0023's routing-time zero-touch rate on new,
   never-exposed documents still land in 5–20%? This is the property "are
   there review slots / QA probes that make a human open the document."
2. **Safety promotion**: on those zero-touch documents' three payment-gate
   fields, is there zero true-silent absence, zero wrong value, and zero
   unscoreable slots under this corpus's truth? Only if this also passes may
   the workflow effect be upgraded to product capability.

First holds + second fails = a valid negative qualification result, not
"almost passed."

## 2. Corpus, exposure registry, and sampling

- context: `qual-narrow-v2`; salt: `invoiceloop-qual-narrow-v2`.
- Base pool: `heldout_pool` minus everything in
  `development_exposure_manifest.json`; then minus SEALED-4's 100 and
  qual-narrow-v1's 200 per the context relations in
  `docs/qualification_exposure_registry.json`; PDF and word-level OCR required.
- v1 historical recompute shows no drift: the v1 pool is still 4,831 and the
  v1 list digest is still
  `22c566997043c5c8185431cb813f84d3eef5a95ca1b2b61bf6182a381fbdb052`.
- v2 pool: **4,631**;
  `pool_sha256=e7265a79aacf57fd4dd9af3d709c7b5963ab71d36a3d17ae762af202ab797fb8`.
- Sampling: take the first 200 by ascending
  `sha256("invoiceloop-qual-narrow-v2|" + doc_id)`, then sort by doc_id.
- v2 list: 200 documents;
  `doc_ids_sha256=50be4e8f4554055c8e0a83cc19ecc20b31319728879dbf6f663218d8b82df853`;
  full JSON bytes
  `sha256=c533ba47d720ae0912425158b8b69fafac8d8b0470dc9475ff1eaee7ab36d614`.
- At freeze, 860 documents had complete dual-mode responses on disk; digest
  `010714561860f1e4b22429f2a31cd17cc18e135e1689d8fbd483c192f6f36ec4`;
  intersection with the v2 list **0**.
- Authoritative list copy:
  `docs/evidence/qual-narrow-v2-2026-08-23/plan/doc_list.json`.
- The sampler / identity control plane was first frozen at `f70fc30`. Pool,
  list digests, and v1/v2 mutual exclusion are all pinned by tests.

The min-hash uses a constant salt rather than drand: before the freeze, no
document in the v2 pool had dual-mode results, so the salt could not sample by
outcome; the trade is that third parties can recompute without trusting a
PRNG version.

## 3. Extraction and identity gates

- 200 documents × `understand + agentic` = 400 DWS calls.
- Budget: **15,000 data-extraction credits**. The budget breaker stays; any
  resume must carry an identical identity.
- workspace: `runs/qual-narrow-v2-2026-08-23/`.
- The only legal command shape:

      python -m invoiceloop qualify extract \
        --workspace runs/qual-narrow-v2-2026-08-23 \
        --round qual-narrow-v2-2026-08-23 \
        --protocol docs/QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md \
        --budget 15000

Before reading a key, loading a client, or issuing an API call, the
deterministic control plane must verify:

1. `plan/MANIFEST.sha256`, the protocol, the frozen list, and the registry
   copies are all committed and equal HEAD;
2. the workspace list is byte-identical to the frozen copy and recomputable
   from the current context / pool;
3. the tracked worktree is clean;
4. if `qualification_run_identity.json` does not exist, raw must be empty; if
   it exists, the identity must match exactly.

The same identity is re-verified before every call during extraction. Any
change to protocol, list, registry, sampler, extractor, or tracked code blocks
immediately; "the change is unrelated to the numbers" is not a self-issued
exemption. After extraction, `scripts/qual_extract_audit.py
--qualification-round ... --qualification-protocol ...` scans all 400
originals, recomputes the run identity, and records per-file hashes and the
raw-tree hash.

Any missing / extra / malformed / misbound / non-200 / identity mismatch in
the aggregate audit = `blocking_level: blocking`. The last resume summary is
not evidence of totals.

## 4. Four arms and a single code identity

| Arm | harness / projection | posting gate | role |
|---|---|---|---|
| A | HAR-0001 | census | structural anchor |
| B | HAR-0021 | census | incumbent routing baseline |
| C | B routes + `payment_required_v1` | payment | posting gate only changes |
| D | HAR-0023 | payment + `release_tier1_explicit:false` | candidate |

A/B/D run the full pipeline; C only projects B's routes.
`scripts/doctouch_arms.py` must be given the v2 `--doc-list` and may only run
from a clean commit. The three arm identities and run manifests must bind the
same code revision and the same policy/schema/list digests; any stale
directory identity blocks immediately.

Each arm must have exactly 200 × 10 = 2,000 unique `(doc_id, field)` routing
slots — none missing, none extra, none duplicated. strong / weak / none strata
are reported as-is; ALL is an aggregate only.

## 5. Pre-registered predictions: misses are published as misses

v1 is contaminated and cannot serve as a qualification; it is already exposed,
so it may serve as a development prior. Based on v1:

| # | Prediction | Nature |
|---|---|---|
| P1 | A zero-touch = 0/200 | structural anchor, not an effect |
| P2 | D zero-touch lands in 5–20% | workflow primary endpoint |
| P3 | C zero-touch ≥ D | D's extra QA probes can only add touches |
| P4 | D whole-arm `silent_wrong` ≤ B | continuity with the old report; not a zero-touch safety gate |
| P5 | D zero-touch payment-subset `silent_wrong` in 8–18, wrong documents 6–14 | v1 was 12 slots / 10 documents; risk expected to reproduce |
| P6 | D zero-touch payment-subset unscoreable auto-accept slots 0–6 | v1 was 4; the gap is listed separately and may not hide in a denominator |
| P7 | all three payment gates fully automatic 15–19% | v1 was 17.0% |

P5 explicitly predicts non-zero, which does not contradict the "must be zero"
promotion line below: this round may well produce a valid, expected
qualification failure. Pre-registration is not wish-making.

Zero-touch rates carry a 95% Wilson interval. Wrong values are scored against
DocILE annotations with the incumbent `eval_normalise`; convention disputes
are listed separately — neither smuggled into silent_absent_true nor
automatically reinterpreted as vendor errors.

## 6. Promotion ruling

Three layers; a later layer may not paper over an earlier one:

### I. Round integrity

- aggregate extraction audit complete and identity-consistent;
- A/B/D share one code identity; routing matrices complete;
- no protocol / list / registry / code contamination.

Fail: the round is void; numbers go only into a contamination record.

### II. Workflow effect reproduction

- P2 holds; P1/P3 serve as pipeline and mechanism checks.

Pass: only "routing-time zero-touch X% measured on this never-exposed DocILE
round" may be stated; still no safe-product-capability claim.

### III. Safety product capability

The D arm's **zero-touch payment subset** simultaneously satisfies:

1. `silent_absent_true == 0`;
2. `silent_wrong == 0`;
3. `unscored_auto_accept_slots == 0`.

Any one non-zero = safety qualification **FAIL**. P4's whole-arm
non-inferiority cannot substitute for these three, because the product claim
points precisely at the documents nobody opened.

Only if I, II, and III all pass may the narrow release be written up as a
safe product capability. Otherwise HAR-0023 is not promoted, the default
census stays, and the results page header states the failure reason directly.

## 7. Ordering versus the ADK human walk

The v2 routing, supplementary safety metrics, results ruling, and evidence
commit come first; only then are 20 documents deterministically drawn from the
v2 human queue for the ADK walk. Before the walk, the proposed artifacts and
provenance map must be frozen and committed; after the first human
adjudication there is no back-reading, no suggestion changes, no protocol
changes.

Even if safety qualification fails, the ADK walk may continue as independent
human-accountability evidence, but the material must state plainly that it
cannot repackage the failed automatic release as a pass.

## 8. Public boundaries

Always attached: single corpus DocILE, single vendor Nutrient DWS, single
truth convention. Do not claim more accurate extraction; do not write the
zero-touch rate as a labor-saving rate; do not present routing support as
value correctness; `NOT MEASURED` and failed items are published as-is.
