# Stage D — Party Direction Prototype (2026-08-07)

## Conclusion

**KILL.** Preregistered primary-metric accuracy **51.6%** (49/95 claims, from 51 documents),
far below the 80% kill line. Item 3 (machine-checking party direction) is **void** — not wired
into `gates` / `routing` / `improve`; seller misidentification stays with the human queue only.

> **Binding correction (2026-08-07, after the first published numbers)**: the first version of
> the script overwrote by `doc_id`, keeping only the last `seller_name` claim, then paired it
> with `spans[doc_id][0]`. On SEALED-2, of the 93 documents with claims, **80 have two claims**
> (dual mode `dws_agentic` / `dws_understand`), and 3 documents have two spans, so the value and
> the position could come from different modes. It now binds strictly by `claim.span_ids`; each
> claim is paired only with the span it names.
>
> | | scoreable | correct | accuracy | 95% CI | verdict |
> |---|---|---|---|---|---|
> | first version (last-claim + `ss[0]`) | 56 | 29 | 51.8% | 39.0–64.3% | FAIL |
> | **corrected (`span_ids` binding)** | **95** | **49** | **51.6%** | **41.7–61.4%** | **FAIL** |
>
> The sample nearly doubled, the point estimate moved 0.2pp, and the upper bound of the interval
> moved further from 80%.
> **The KILL is unaffected, with higher confidence.** All remaining numbers in this document are post-correction.

Recompute:
```bash
INVOICELOOP_CORPUS=runs/sealed2-workspace \
  python3 scripts/subject_direction_proto.py
```

Engine: `subject-direction-v1` · digest prefix `edc49c71a2874d10`
(the full value comes from `subject_direction.digest()`).

## Preregistered rule (no tuning for looks)

From `docs/DOCTYPE_PLAN_2026-08-07.md` Q3:

| Side | Labels |
|---|---|
| seller | `Remit to` / `Pay to` / `Station` |
| buyer | `Bill to` / `Advertiser` / `Agency` |

For a `seller_name` span extracted from `runs/sealed2` (same page), take the label side nearest
by Euclidean distance on the word-level OCR:

- near the seller side → predict the extraction agrees with DocILE `vendor_name`
- near the buyer side → predict it does not

Accuracy = the share where the prediction agrees with the correctness of `eval_normalise(PARTY)`.
**The unit of counting is the claim, not the document** — one document's two extraction modes
each count as one. Scoreability preconditions: a seller span exists, the claim's `span_ids` names
a seller span with `bbox_rel`, both ground truth and extraction exist, and at least one label on
the same page.

## Numbers

| Item | Value |
|---|---|
| documents | 100 |
| with any label on the page | 68 |
| primary metric scoreable (claims) | 95 |
| ↳ documents covered | 51 |
| primary metric correct | 49 |
| **primary-metric accuracy** | **51.6%** (95% CI 41.7–61.4%) |
| kill line | 80% |
| **verdict** | **FAIL** |

Skipped: no seller span 4 · claim bound to no span 14 · no ground truth or extraction 11 ·
no label on the same page 45 · OCR unavailable 0.

**Coverage must be read alongside**: only 51 of the 100 documents produced scoreable claims.
For the other 49 this rule **delivers no verdict at all** — which is not "getting them wrong" —
so even if accuracy met the bar, it would still cover only half the documents.

### Corroborating variants (same vocabulary, polarity unchanged; all FAIL)

| Variant | n | accuracy |
|---|---|---|
| nearest label + max_dist≤0.20 | 40 | 52.5% |
| both sides present on page → the nearer side | 44 | 50.0% |
| ground-truth vendor bbox → is nearest side the seller side (document level) | 59 | 47.5% |

The variants are not a release bypass: they exist to rule out the illusion that "it's just the
distance threshold / missing comparison labels".
All hug coin-flip; none comes near 80%.

## Why this is no surprise

The plan already warned of the PARTY citation prototype failing 137/151. This prototype swapped
in geometric nearest-neighbor and failed the same way: on advertising documents where Agency /
Station / Advertiser / Remit to appear simultaneously, the extracted seller name does not
consistently land on the side it "should" be near; the ground-truth bboxes themselves are nearest
a seller-side label only about half the time — label geometry **cannot localize** the seller.

The agency↔station inversions among the known silent errors (e.g. `503f49c0` Regional
Reps→WARU-AM, `ce6ab66e` Shorr Johnson Magnus→WPGH) would not be reliably caught by this rule.

## Product implications

1. **No** `subject_direction` gate / finding / automatic relaxation.
2. `seller_name` / `buyer_name` misplacement continues to humans; the deliverable claims no
   verifiable direction.
3. Stage E (type-level applicability matrix) is **decoupled** from party direction and can
   proceed per plan; `doc_class` must not be treated as a substitute for party direction.

## Artifacts

| Path | Role |
|---|---|
| `invoiceloop/subject_direction.py` | frozen vocabulary + geometry (marked not-for-product) |
| `scripts/subject_direction_proto.py` | SEALED-2 zero-API recomputation |
| `tests/test_subject_direction.py` | geometry/polarity unit tests |
