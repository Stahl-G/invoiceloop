# QUALIFICATION_NARROW_2026-08-22 contamination and revocation record

Status: `contaminated`

Blocking level: `blocking`

Decision: this round's qualification / product-capability promotion is revoked;
all numbers are retained as exploratory measurements carrying the contamination
label.

This record does not delete or overwrite the original protocol, the original
results, or the raw artifacts. It is a later, explicit status event and
supersedes the "no blocking findings" / "all four product-capability gates
passed" conclusions of `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md` §0/§4.
HAR-0023 never became the packaged active harness; the default remains census.

Product risk comes first below, then process contamination; both are
independent blockers, and either alone suffices to negate product promotion.

## 1. Product blocker: the zero-touch payment subset still contained wrong values

Pre-registered P6 compared D vs B on **all automatic slots** (`silent_wrong`
110 ≤ 111). It did not isolate the 25 documents that needed **no one to open
them at all** — and the product sentence speaks about exactly those 25.

A zero-API supplementary audit, using the same routing, the same DocILE
annotations, and the same normalisation functions:

| D-arm zero-touch payment subset | Count |
|---|---:|
| zero-touch documents | 25 |
| payment-gate slots | 75 |
| with a value to compare | 71 |
| disagreeing with DocILE annotations | 12 |
| documents containing at least one disagreeing slot | 10 |
| unscoreable auto-accept slots / documents | 4 / 4 |

The 12 disagreeing slots by field: `seller_name` 7, `amount_due` 3,
`invoice_number` 2; the 4 unscoreable slots by field: `invoice_number` 2,
`seller_name` 1, `amount_due` 1.

This is a post-hoc supplementary audit: it cannot masquerade as a new
pre-registered P6 verdict, and it cannot by itself claim a vendor extraction
error rate. What it establishes: the original safety endpoint did not cover
the risk-concentrated region the product claim speaks about, so even absent
protocol contamination the original four gates were insufficient to support a
"safe zero-touch product capability."

## 2. Process blocker: the protocol's own dirty-arm clause had already fired

The frozen protocol §7 states: modifying the protocol text after extraction
begins makes the arm dirty.

- Protocol and list were first frozen at `b45f983`.
- After extraction began, the protocol text was edited in `1afe7da`.
- `68a2701` restored the frozen bytes and moved the fact into the run log.
- Restoring the bytes cannot undo a transition that already happened;
  otherwise the dirty-arm clause survives only as after-the-fact interpretation.

Therefore, regardless of whether the edit affected any number, this round
cannot serve as a qualification, and 12.5% cannot be promoted to product
capability. The original results wrongly treated "the edit did not affect the
numbers" as "no blocking finding," violating the protocol's own precedence.

## 3. The numbers were not deleted, but their meaning is downgraded

The aggregate extraction audit walked the frozen list and the stored originals
rather than trusting the last resumable-run summary:

| Item | Deterministic result |
|---|---:|
| documents | 200 |
| expected / stored calls | 400 / 400 |
| HTTP 200 | 400 |
| DWS credits | 10,491 |
| raw response tree SHA-256 | `2fa28111dba94e95e40f636893d4c1951cf52503bbc40b0f2ecf3e01212ad655` |

The four arms' historical routings were also frozen arm by arm. The
supplementary audit recomputed at scorer commit
`71afebfab167bb08908fdfe6cdbc3d4741486327`; drift on already-reported metrics
was 0. So 25/200 and 12.5% remain the true **descriptive** results of that
historical routing; contamination changes what qualification and public claims
they can carry, not the pretense that the numbers never happened.

## 4. Currently allowed and forbidden phrasings

Allowed:

> In a 200-document DocILE exploratory measurement later judged contaminated
> under its own protocol, HAR-0023's routing-time zero-touch was 25/200 (12.5%,
> 95% Wilson CI 8.6–17.8). This result is not a qualification and supports no
> safety, accuracy, or product-promotion claim.

Forbidden:

- "the qualification round passed" or "all four product-capability gates passed";
- "the narrow release has become a product capability";
- "25 documents needed no opening, therefore the payment fields are
  safe/correct";
- writing 12.5% as saving 12.5% of human labor, or transferring it to other
  corpora, vendors, or truth conventions.

## 5. Recovery path

A new round is required, without reusing these 200 documents:

1. exclude the v1 list via the exposure registry; freeze a new pool, salt,
   200-document list, and protocol;
2. the first DWS call is permitted only after the protocol-freeze commit, and
   the protocol does not change thereafter;
3. aggregate extraction audit, per-arm code identity, and complete routing
   matrices become machine gates;
4. the safety endpoint lands directly on the zero-touch payment subset and
   explicitly blocks on unscoreable slots;
5. only after all evidence is committed may the ADK human-walk set be drawn.

## 6. Evidence index

- Aggregate extraction: `docs/evidence/qual-narrow-2026-08-22/extract-audit/`
- Supplementary audit v2: `docs/evidence/qual-narrow-2026-08-22/analysis-audit-v2/`
- Historical arms: `docs/evidence/qual-narrow-2026-08-22/source-har-0001/`,
  `source-har-0021/`, `source-har-0023/`
- Original run log: `docs/QUALIFICATION_NARROW_LOG_2026-08-23.md`
