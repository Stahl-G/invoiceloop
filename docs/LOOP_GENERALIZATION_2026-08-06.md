# Loop generalization, measured: experience from one batch of documents applied to another (2026-08-06, for external adjudication)

**Question**: can what the improvement loop learns on one batch of documents be applied to **another batch
never touched by humans** — rather than working only on repeated evidence (carry solves only repeated evidence)?

**Method (zero API, recomputable)**: of SEALED-1's 100 sealed documents, 12 went through complete
human review (`runs/hitl-sealed`, 123 adjudications) and yielded two absent_expected
cohorts (seller_vat_id, total_vat; both discovered independently by mine from adjudication events, promoted
by human signature as HAR-0003/HAR-0004). That policy version is replayed onto the **remaining 88 documents
never human-reviewed**: slot facts are rebuilt from the authoritative artifacts
(field_ledger + gate_report + raw responses) via the single-source-of-truth derive_document_records,
routing is replayed under the policy, and workload and safety are reported separately. Safety is evaluated
against DocILE ground truth.

**Role statement**: SEALED-1 has completed its protocol-assigned final held-out duty and has been demoted to
an evolution/regression set — using it for cohort development and generalization analysis is its legitimate
role; this document is an evolution-set analysis, not a new round of sealed evaluation.

## Numbers (88 never-human-reviewed documents × 10 fields = 880 slots)

**Review-load caliber**: `route not in (auto_accept, auto_absent)` — same definition as
`deliver` / `matrix.in_human_queue` / `safety_metrics`;
**excludes** `auto_absent` (policy-confirmed absence does not count as awaiting human action). Do not confuse
with `requires_adjudication` (a compatibility field that includes auto_absent).

| Policy | Review load | Document touch | auto_absent silent absence errors | auto_accept silent wrong values |
|---|---|---|---|---|
| HAR-0001 (conservative baseline) | 63.7% | 88/88 | — | 49/272 (18.0%) |
| HAR-0002 (TIER1 policy release) | 64.4% | 88/88 | — | 48/266 (18.0%) |
| **HAR-0004** (two absence cohorts) | **55.1%** | **87/88** | 3/85 (**3.5%**) | 49/266 (18.4%) |

(HAR-0002's review load is slightly higher than HAR-0001: the 5% QA sampling of policy_accepted TIER1
returns those slots to the queue — a design cost, not a regression.)

## How to read this

1. **Experience transfer holds and is backed by ground truth**: both cohorts are field-level semantics
   (US invoices have no VAT field / no VAT amount line) and reference no specific document — applied to
   88 unfamiliar documents, review load drops −9.3pp. This is not a repeated-evidence dividend (carry's
   domain); it is cross-document generalization.
2. **"100% document touch" meets its first counterexample**: 87/88 — one document had all 10 slots
   taken over by policy with ground truth unharmed. Under every previous caliber, document touch was 100%.
3. **The cost is measured, not guessed**: of 85 auto_absent slots, 3 actually have ground truth
   (3.5%, consistent with the independent estimate of 3.4% over all 100 documents) — the silent
   under-labeling rate of the absence policy. It is continuously observed by the 20% QA sampling;
   severity note: the 3 cases include one genuine EU VAT number (missed by DWS) and two
   EIN-format numbers (the other side of the dataset caliber dispute).
4. **auto_accept silent wrong values hold flat at 18% across policies**: this is the pre-existing
   risk of the policy_accept fixed operating point (the same order of magnitude as the 17.91% in the earlier
   baseline tables), unrelated to the cohorts, observed by the 5% QA probes. The cohorts
   did not make it better or worse.

## Not claimed

- Not claimed: generalization beyond DocILE (single corpus, single vendor, single point in time;
  the ARCHITECTURE §8 limitations remain in effect on the same screen);
- Not claimed: that 55.1% is the endpoint — the remaining bulk of review load is gate failures and genuinely
  missing values, which needs new cohort types (not the absence kind) to go further;
- Not claimed: that the absence policy is cost-free — the 3.5% silent under-labeling is the actual price,
  already written into the rationale of the promotion record (PROM-0003);
- Not claimed: that carry and this document are the same thing — carry solves repeated evidence; this
  document solves cross-document generalization.

## Recompute

```bash
# The 88-document list = sealed1 list − the 12 documents in runs/hitl-sealed/input/pdfs/
# Method and numbers (source of every table in this document, zero API):
INVOICELOOP_CORPUS=runs/sealed1-workspace python3 <this-analysis-script>
# Inputs: runs/sealed1/{gate_report,field_ledger}.json +
#         runs/sealed1-workspace/raw/*.understand.json +
#         runs/hitl-sealed/harnesses/HAR-0004/routing_policy.json +
#         DocILE annotations (the same caliber as heldout_metrics.truth)
```
