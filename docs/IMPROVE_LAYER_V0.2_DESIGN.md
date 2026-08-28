# InvoiceLoop Improve Layer v0.2 Edition Design

**Subtitle: Evidence-Bound, Eval-Gated, Human-Promoted Harness Improvement**  
**Status: proposed to freeze as the implementation baseline**  
**Evaluation repo: `b5fe7a0368ab7ef473edf8faebf061daa1ea847c`**  
**Date: 2026-08-05**

---

## 0. Adjudication summary

### 0.1 The chosen approach

We choose the **Guarded Improvement Control Plane** (a controlled plane for guarded
improvement):

```text
real usage and human review
→ structured feedback events
→ repeated failures / ineffective-review patterns
→ bounded Harness Candidate
→ Targeted Eval + Regression Eval + Promotion Eval
→ human-approved promotion
→ new Harness version affects future runs
```

It is none of these:

- “humans finish fixing the current invoice and that counts as closing the loop”;
- “re-sorting by historical correction rate”;
- “an agent auto-edits the whole repo and ships it directly”;
- “tuning repeatedly on the same batch of DocILE until it looks good”.

### 0.2 Product claim

> **InvoiceLoop starts conservative, then turns every reviewed invoice into evidence for safely reviewing fewer fields next time.**

In Chinese:

> **InvoiceLoop starts from a conservative policy, turning every human review into evaluation evidence for the next Harness version, gradually reducing human review without increasing critical silent errors.**

### 0.3 The core experiment

Starting from the corrected, real R0 baseline, the goal is to take:

```text
TIER1 mandatory field review load
approx. 41% → ≤30%
```

while also satisfying:

```text
critical-field generalized silent risk no worse than R0
critical-error routing recall does not significantly decrease
actual reviewer minutes per invoice decrease
audit and binding invariants all pass
```

**30% is a product goal, not a constant of natural science.** The real research
conclusion is that the risk–coverage frontier moves down and to the left, not that it
happens to cross 30%.

### 0.4 External naming

Before implementation, and while only development-set results exist:

> feedback-driven, eval-gated harness improvement

After completing at least one round of “feedback → candidate → qualification eval on
unseen data → human promotion → future runs use the new version”:

> human-steered self-improving harness

Without a fresh sealed evaluation, claiming autonomous self-improvement is forbidden.

---

# 1. Why the current design must be re-cut

The existing `docs/IMPROVE_LOOP_DESIGN.md` has the right discipline, but its first cut
cannot support the goal.

## 1.1 The parts that are correct

The existing design already insists on:

- proposals are not authority;
- no automatic gate changes, no automatic releases;
- human adjudication is an important feedback source;
- risk–coverage evaluation is required;
- the same held-out set cannot be used repeatedly;
- reading-model answers cannot be treated as ground truth.

All of these are kept.

## 1.2 What must be overturned

### A. “Tax AI depends on a complete automated oracle” is not accurate

The key to Tax AI is not a complete tax reference implementation, but:

```text
expert corrections
→ complete product traces
→ distinguishing real failures from workflow noise
→ repeated patterns become targeted eval
→ bounded engineering tasks
→ targeted + regression validation
→ humans own architecture and release
```

InvoiceLoop already has most of the trace foundation Tax AI needs; what is missing is
the second half of the loop from adjudications to findings, evals, and candidate
versions.

### B. “DWS is a black box, so there are no learnable knobs” does not hold

Even without being able to modify DWS weights, InvoiceLoop can still improve:

- extraction schema;
- routing policy;
- warning / blocker classification;
- required / absent / not-applicable semantics;
- understand→agentic escalation strategy;
- review priority;
- field playbook;
- normalization and mapping;
- policy profiles per document type.

These are all Harness, not model weights.

### C. “Reordering within a band” cannot bring 41% down to 30%

If the `requires_adjudication` set is unchanged, reordering only changes the order a
human looks in:

```text
review load unchanged
automation coverage unchanged
silent failure unchanged
```

It is only suited to optimizing:

```text
critical error recall@fixed human budget
precision@k
time-to-first-critical-error
reviewer minutes to find 80% critical errors
```

So the first cut must allow a **restricted routing policy candidate** to change which
soft risks reach humans, while hard blockers stay frozen.

### D. Counting only human adjudications has severe selection bias

The current policy determines which fields a human can see. If we look only at reviewed
fields:

- auto-accepted regions carry no labels;
- “never corrected” may simply mean “never sampled”;
- the system would wrongly learn the current policy's blind spots.

Therefore randomized/stratified QA spot-checks must be added, and the probability of
each field being reviewed must be recorded.

### E. Harness identity has not yet entered execution identity

The fingerprint of the current `snapshot.build_input_manifest()` mainly binds PDFs, OCR,
DWS responses, schema, and vision inputs, but when routing / escalation policies change
in the future, the same input must form a different execution identity.

Otherwise a new Harness could replay an old run, with no way to prove which policy
version handled which invoice.

---

# 2. Four non-negotiable design axioms

## Axiom One: Feedback is evidence, not permission

A human correction is evidence, not authorization to automatically modify production
policy.

## Axiom Two: Proposal is not policy

The agent can only generate candidates; the active harness can only be designated by an
explicit promotion record.

## Axiom Three: Evaluator stays outside the loop

Candidates must not modify or read:

- private ground truth;
- sealed eval sets;
- the eval scorer;
- critical-field definitions;
- the safety gate;
- promotion rules.

## Axiom Four: Review reduction is not improvement unless risk is preserved

Any candidate that lowers the human rate through the following means counts as failed:

- renaming errors as `not_applicable`;
- deleting fields;
- loosening evaluator normalization;
- hiding warnings;
- running expensive models on all documents without reporting cost;
- looking good only on the development set;
- trading TIER1 silent errors for coverage.

---

# 3. Overall software architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                      EVALUATION AUTHORITY                    │
│ private labels · frozen scorers · sealed sets · promotion   │
│ rules · integrity tests                                     │
│ (read-only to candidates; cannot be modified by candidates)  │
└──────────────────────────┬───────────────────────────────────┘
                           │ qualification result
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                IMPROVEMENT CONTROL PLANE                     │
│ feedback compiler → weakness miner → finding → proposer      │
│ → candidate sandbox → eval orchestrator → promotion manager │
└───────────────┬───────────────────────────────┬──────────────┘
                │ read-only traces              │ candidate diff
                ▼                               ▼
┌─────────────────────────────┐      ┌──────────────────────────┐
│       FEEDBACK PLANE        │      │ VERSIONED HARNESS PLANE  │
│ review events · QA events   │      │ routing · escalation     │
│ reason codes · actionability│      │ schema · field playbooks │
│ reviewer confidence         │      │ immutable versions/digest│
└───────────────┬─────────────┘      └─────────────┬────────────┘
                │ derived from                     │ selected by
                ▼                                  ▼
┌──────────────────────────────────────────────────────────────┐
│                       RUNTIME PLANE                          │
│ DWS → freeze → gates → routing → review → deliverable       │
│ every run binds exact harness_id + execution_fingerprint    │
└──────────────────────────┬───────────────────────────────────┘
                           │ immutable evidence
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                         TRUST KERNEL                         │
│ raw responses · artifact registry · evidence spans · field  │
│ ledger · review snapshot · adjudication ledger · bundle     │
│ verifier                                                    │
│                (Improve is always read-only)                 │
└──────────────────────────────────────────────────────────────┘
```

## 3.1 Trust Kernel

Keep and strengthen what exists:

- `input_manifest.json`
- `artifact_registry.json`
- `evidence_span_registry.json`
- `field_ledger.json`
- `gate_report.json`
- `review_snapshot.json`
- `adjudication_ledger.jsonl`
- bundle manifest / verifier

The Improve Layer has read-only access to all of the above.

## 3.2 Runtime Plane

Runtime uses one promoted Harness version and produces:

- extraction results;
- frozen claims;
- deterministic gates;
- `routing_report.json`;
- support matrix;
- the human queue;
- deliverable.

## 3.3 Versioned Harness Plane

The first Harness version consists of pure configuration files:

```text
harnesses/
  HAR-0001/
    manifest.json
    extraction_schema.json
    routing_policy.yaml
    escalation_policy.yaml
    review_priority.yaml
    field_playbooks/
      amount_due.yaml
      total_gross.yaml
      seller_tax_id.yaml
```

Every Harness is immutable. A new version must create a new directory; old versions are
never overwritten.

## 3.4 Feedback Plane

The human adjudication ledger remains the authority. The Feedback Plane is a
rebuildable data product derived from the authoritative artifacts; it never writes
adjudications back.

## 3.5 Improvement Control Plane

Responsible for:

```text
compile → mine → propose → lint → evaluate → qualify → promote
```

Not responsible for:

- rewriting production evidence;
- directly deciding invoice ground truth;
- automatic release;
- modifying the evaluator.

## 3.6 Evaluation Authority

This is the Improve Layer's external constitution, including:

- private labels;
- dataset splits;
- scorer;
- promotion gates;
- integrity / regression suites;
- query budget;
- final sealed evaluation.

---

# 4. Implementation preconditions in the current repo (P0)

The Improve Layer is built on the premises that feedback is correct, versions are
attributable, and delivered values are trustworthy. The following must be completed
first, and it does not count as a “learning gain” toward 41%→30%.

## P0-1 Final values can only come from the frozen authority

The current `accept` path in `deliver.py` takes `row["value"]` from
`support_matrix.json` directly. Architecturally the matrix is a projection and should
not be the final-value authority.

Fix:

```text
accept_claim → must have a claim_id
final value → read from the corresponding claim in field_ledger
correct → read from the human corrected_value
```

bundle verify must verify:

```text
accepted final value == frozen claim value
corrected final value == adjudication corrected_value
```

## P0-2 Split human decision semantics apart

From the current:

```text
accept / reject / correct / abstain
```

upgrade to:

```text
accept_claim       confirm an existing claim; must have a claim_id
correct            a human supplies a new value
reject_claim       reject an existing claim
confirm_absent     confirm the field is truly absent from the page
not_applicable     the field does not apply to this kind of document
abstain            even the human cannot decide; stays unresolved
```

Otherwise the Improve Layer cannot distinguish:

- missing extraction values;
- legitimate absence;
- field not applicable;
- human cannot see clearly.

## P0-3 Add an independent routing authority

Extract out of `matrix.py`:

```text
invoiceloop/routing.py
```

producing:

```json
{
  "doc_id": "...",
  "field": "amount_due",
  "claim_id": "FC-0012",
  "route": "auto_accept | review | block | escalate",
  "reason_codes": ["..."],
  "harness_id": "HAR-0001",
  "policy_digest": "...",
  "review_probability": 1.0
}
```

`support_matrix.json` remains a display projection; `deliverable.json` is rebuilt from
the frozen ledger, the routing report, and human adjudications.

## P0-4 The Harness must enter the execution fingerprint

Add:

```text
execution_fingerprint = hash(
  input_fingerprint,
  code_revision,
  harness_id,
  extraction_schema_digest,
  routing_policy_digest,
  escalation_policy_digest,
  normalization_version,
  gate_version
)
```

The same PDF under a different Harness must open a new run; old runs must not be
replayed.

## P0-5 Separate product normalization from eval normalization

```text
invoiceloop/product_normalization.py  # can serve as a candidate evolution surface
invoiceloop/eval/reference_normalization.py  # frozen, not editable
```

Otherwise a candidate could raise its score by loosening the definition of “equal”.

## P0-6 Remove fake human approval for conflict-free TIER1

System auto-release must be recorded as:

```text
policy_accept
```

rather than generating or requiring a human `accept`.

Only once this is done can 41.1% count as the real mandatory field review load rather
than a counterfactual triage rate.

---

# 5. Core data contracts

## 5.1 HarnessManifest

```json
{
  "harness_id": "HAR-0003",
  "parent_harness_id": "HAR-0002",
  "status": "candidate",
  "created_from_findings": ["FIND-0012"],
  "components": {
    "routing_policy.yaml": "sha256:...",
    "escalation_policy.yaml": "sha256:...",
    "extraction_schema.json": "sha256:..."
  },
  "code_revision": "...",
  "schema_version": 1
}
```

## 5.2 FeedbackEvent

A FeedbackEvent must bind the original adjudication and the Harness then in effect:

```json
{
  "feedback_id": "FB-000042",
  "decision_id": "HD-0031",
  "run_id": "run-0017",
  "review_snapshot_id": "...",
  "execution_fingerprint": "...",
  "harness_id": "HAR-0001",

  "doc_id": "...",
  "field": "amount_due",
  "tier": "TIER1",
  "claim_id": "FC-0012",
  "predicted_value": "850.00",
  "final_value": "1000.00",

  "human_action": "correct",
  "reason_code": "WRONG_FIELD_MAPPING",
  "error_stage": "semantic_mapping",
  "severity": "critical",
  "reviewer_confidence": "high",
  "actionable": true,

  "route_reason_codes": ["LABEL_CONVENTION", "SINGLE_SOURCE"],
  "review_probability": 1.0,
  "evidence_refs": ["ES-0012", "ES-0014"]
}
```

### Minimal reason-code set

```text
WRONG_VALUE
WRONG_FIELD_MAPPING
BAD_SOURCE_BINDING
MISSING_EXTRACTION
NORMALIZATION_ERROR
ROUTING_FALSE_NEGATIVE
ROUTING_FALSE_POSITIVE
CONFIRMED_ABSENT
NOT_APPLICABLE
AMBIGUOUS_DOCUMENT
PROVIDER_FAILURE
REVIEWER_PREFERENCE
```

### Feedback usability

Only events meeting the following can enter improvement labels directly:

```text
reviewer_confidence = high/medium
AND actionability = true
AND action != abstain
AND no reviewer conflict
```

`REVIEWER_PREFERENCE` and `AMBIGUOUS_DOCUMENT` must not be used as negative samples for
auto-release rules.

## 5.3 Finding

```yaml
finding_id: FIND-AMOUNT-DUE-0012
status: confirmed
scope:
  field: amount_due
  tier: TIER1
  cohort_expression:
    support_strength: corroborated
    cross_mode_agreement: pass
    citation_holds: pass
    warning_subset: [visual_corroboration_unavailable]
observations:
  reviewed: 43
  corrected_critical: 0
  accepted_unchanged: 40
  abstained: 3
  randomized_qa_cases: 8
hypothesis:
  component: routing_policy
  statement: >
    This warning cohort creates low-yield reviews and may be eligible
    for policy acceptance when no hard blocker is present.
preserve:
  - arithmetic failures remain review
  - citation failures remain review
  - label-convention disputes remain review
prediction:
  review_load_delta_pp: -4.0
  critical_silent_error_delta: 0
  dws_credit_delta: 0
```

## 5.4 CandidateManifest

```yaml
candidate_id: CAND-0012-A
parent_harness_id: HAR-0001
finding_ids: [FIND-AMOUNT-DUE-0012]
component: routing_policy
editable_files:
  - harness/routing_policy.yaml
forbidden_files_digest: sha256:...
max_diff_lines: 80
prediction_contract:
  review_load_delta_pp: [-6.0, -2.0]
  critical_silent_errors_added: 0
resource_budget:
  extra_dws_credits_per_invoice: 0
  extra_latency_ms: 0
eval_plan_id: EP-0012
```

## 5.5 EvalResult

Results must record baseline and candidate together and bind dataset fingerprints:

```json
{
  "candidate_id": "CAND-0012-A",
  "baseline_harness_id": "HAR-0001",
  "dataset_fingerprints": {
    "targeted": "...",
    "regression": "...",
    "promotion": "..."
  },
  "integrity": "PASS",
  "metrics": {
    "baseline": {},
    "candidate": {},
    "paired_delta": {}
  },
  "qualification": "PASS",
  "failure_reasons": []
}
```

## 5.6 PromotionRecord

```json
{
  "promotion_id": "PROM-0004",
  "candidate_id": "CAND-0012-A",
  "from_harness_id": "HAR-0001",
  "to_harness_id": "HAR-0002",
  "decision": "promote",
  "approved_by": "...",
  "approved_at": "...",
  "rationale": "...",
  "rollback_harness_id": "HAR-0001"
}
```

---

# 6. State machines

## 6.1 Finding

```text
draft
→ confirmed_actionable
→ candidate_opened
→ resolved | rejected | deferred
```

Vague or not actionable:

```text
draft → non_actionable
```

## 6.2 Candidate

```text
draft
→ lint_passed
→ targeted_passed
→ regression_passed
→ promotion_qualified
→ promoted | rejected | deferred
```

A failure at any stage stops the process; there is no automatic “fix until it passes”.
A new attempt must use a new candidate ID.

## 6.3 Harness

```text
candidate → qualified → active → retired
```

Only one active pointer is allowed, while all historical versions are retained
permanently.

---

# 7. Editable surfaces and implementation tiers

## 7.1 v0.1: configuration-level Harness Evolution (hackathon mainline)

Only edits to:

```text
routing_policy.yaml
review_priority.yaml
field_playbooks/*.yaml
```

The first candidate type must be:

> **Cohort-based routing relaxation: move a set of low-yield soft risks from mandatory
> review to policy_accept.**

Candidate rules may reference only generic features:

- field / tier;
- support strength;
- gate verdict vector;
- warning reason codes;
- DWS confidence bucket;
- document family / layout family (a minimum sample is required);
- provider mode status.

Referencing these is forbidden:

- doc ID;
- benchmark row number;
- ground-truth value;
- specific test file names;
- hard-coding a single vendor name, unless it is explicitly a product-level vendor
  policy and human-approved.

## 7.2 v0.2: runtime escalation strategy

Opens:

```text
escalation_policy.yaml
```

Allows:

```text
understand
→ preliminary gates
→ call agentic only for boundary-risk fields/documents
→ re-gate
→ human only if still conflicting
```

Such candidates must run paired live DWS evaluation, because frozen old responses cannot
evaluate a new call sequence.

## 7.3 v0.3: Extraction Schema Candidate

Opens:

```text
extraction_schema.json
```

Must:

- one candidate changes only one or a few field descriptions;
- paired live extraction;
- retain all raw responses;
- report credits and provider drift;
- do not modify the eval normalizer.

## 7.4 Not opened for now: arbitrary Python self-modification

During the hackathon the agent may not freely edit:

```text
freeze.py
snapshot.py
adjudicate.py
review.py
deliver.py
bundle verifier
eval scorer
```

If code-level candidates are opened later, they may write only into the separate:

```text
invoiceloop/harness_plugins/
```

and must pass an import allowlist, static checks, and a sandbox.

---

# 8. Permissions and sandboxing

## 8.1 Three-process isolation

### Proposer

May read:

- the Finding pack;
- redacted/necessary traces;
- public architecture documents;
- allowlisted harness files;
- targeted development cases.

May write:

- allowlisted files in the candidate worktree;
- `proposal.yaml`;
- `prediction.md`.

May not read:

- promotion/final labels;
- private scorer internals;
- active credentials.

May not write:

- production workspace;
- trust kernel;
- git main branch;
- active harness pointer.

### Evaluator

May read:

- baseline/candidate Harness;
- frozen source inputs;
- private ground truth;
- scorer.

May write:

- immutable `eval_result.json`.

May not write:

- candidate diff;
- active harness;
- production evidence.

### Promoter

Must be an explicit human command; reads the EvalResult, writes the PromotionRecord and
the active pointer.

## 8.2 Candidate Diff Linter

Automatically rejects:

- modifying paths outside the allowlist;
- modifying eval/ground truth;
- adding network calls;
- adding dependencies;
- raising budget ceilings;
- the presence of DocILE doc IDs;
- the presence of hard-coded expected values;
- diffs exceeding the preset size;
- modifying multiple components at once;
- deleting logs, tests, or failure cases.

## 8.3 Data privacy

Before production invoices or human rationales are sent to an external proposer model:

- explicit authorization must be obtained;
- context must be minimized;
- structured features / crops must be preferred over whole invoices;
- sensitive fields such as bank accounts, tax IDs, and addresses must be redacted;
- the model, provider, and sent artifacts must be recorded in the candidate trace.

---

# 9. Feedback quality: preventing “learning mistakes from human data”

## 9.1 Two-layer feedback

Every human action is split into:

1. **business adjudication**: the final value or status;
2. **diagnostic label**: why the system needs improving.

The business adjudication must be completed; for diagnostic labels, prefer one-click
reason codes to reduce the extra human burden.

The agent may suggest reason codes, but a human must confirm them; they must never be
written into truth on their own.

## 9.2 Reviewer confidence

```text
high     page evidence is clear
medium   inferred but fairly certain
low      relies on business judgment or the page is ambiguous
```

Automatic policy relaxation uses only high/medium feedback without conflicts.

## 9.3 Two-person review

A second person reviews at least the following samples:

- all candidate-only critical errors;
- `not_applicable`;
- `confirm_absent`;
- a fixed proportion of policy-accepted QA samples;
- reviewer confidence=low.

## 9.4 Randomized QA and selection bias

Every auto-accepted field records:

```text
review_probability
```

Recommended:

```text
normal auto-accept: 5% stratified random QA
new layout / new vendor / provider drift: 10%–20%
cohorts hit by a freshly promoted policy: 20% QA for the first batch, decreasing once stable
```

Stratify at least by:

- TIER1/TIER2;
- field;
- document family;
- support strength;
- policy cohort;
- old vs new layout.

**Unreviewed does not mean correct.** The Weakness Miner must not treat auto-accepted
slots without feedback as negative examples.

---

# 10. Weakness Mining

## 10.1 Do not feed all raw traces directly

Build a layered Experience Pack:

```text
Level 0: overall metrics and drift
Level 1: cohort statistics
Level 2: representative review rows
Level 3: specific source / crop / gate / claim traces
```

This maps to:

- component observability: makes explicit which component is changeable;
- experience observability: compresses long trajectories into drillable evidence;
- decision observability: every change carries a verifiable prediction.

## 10.2 Cohort key

The first version can use:

```text
field
× tier
× support_strength
× gate verdict vector
× warning reason set
× DWS confidence bucket
× document family
× harness_id
```

## 10.3 Statistics

```text
reviewed_count
accept_unchanged_count
critical_correction_count
noncritical_correction_count
reject_count
confirm_absent_count
not_applicable_count
abstain_count
random_qa_count
review_seconds
```

## 10.4 Minimum-sample discipline

Do not mistake “n≥30” for proof of safety. Even 30 zero-error observations leave a wide
upper bound on the true error rate.

Rules:

- n<30: may only propose “collect more evidence”, never auto-release;
- n≥30: generating an exploratory candidate is allowed;
- promotion is decided by an independent promotion eval;
- no external claims of absolute error-rate guarantees.

## 10.5 Findings must carry a preservation set

Beyond “what to fix”, every finding must also state:

- which successful behaviors must not break;
- which hard blockers are never relaxed;
- which costs are expected to be affected;
- which subgroups may regress.

---

# 11. Routing policy design

The current `matrix.py` turns “any warning” uniformly into
`requires_adjudication=True`. The recommendation is an explicit, versioned policy
instead.

## 11.1 Four routes

```text
auto_accept  satisfies the current Harness's auto-release contract
review       requires human resolution
block        foundational evidence missing, or an unreleasable risk exists
escalate     run extra machine steps first, then re-evaluate
```

## 11.2 Hard blockers (relaxation forbidden in Improve v0.1)

At least:

- document-level OCR / extraction infrastructure unavailable;
- frozen binding failure;
- TIER1 citation fail;
- TIER1 arithmetic fail;
- two competing claims;
- label convention dispute;
- cross-document duplicate/conflict;
- required TIER1 missing without confirm_absent/not_applicable;
- bank or payment-information anomalies (when added in the future);
- bundle / snapshot integrity fail.

## 11.3 Soft review triggers (open for candidates to study)

For example:

- visual corroboration unavailable;
- certain single-source TIER2 fields;
- not participating in identities, making arithmetic unavailable;
- known legitimate absence;
- format warnings that do not affect amounts/payment;
- specific gate combinations that QA has confirmed to be low-yield.

## 11.4 Candidates touch only soft triggers

A first-version candidate cannot remove a hard blocker; it can only take one
well-defined cohort's:

```text
review → auto_accept
```

or:

```text
review → escalate
```

Every change must carry a reason code and a policy digest.

---

# 12. Evaluation goals and metrics

## 12.1 Do not optimize a single composite score

Use lexicographic order:

```text
1. Integrity
2. Critical safety
3. Human workload
4. Cost and latency
```

Human workload must never override safety failures.

## 12.2 Headline metrics

### Mandatory field review load

```text
scored fields requiring human handling / all scored fields
```

41.1%→30% must explicitly refer to this calibre.

### Document touch rate

```text
documents with at least one mandatory field / all documents
```

### Human actions per invoice

```text
valid human-submitted adjudication actions / documents
```

### Reviewer minutes per invoice

Real timing, not a proxy from field counts.

## 12.3 Safety metrics

### Critical selective risk

```text
TIER1 fields auto-accepted but wrong
/ TIER1 fields auto-accepted
```

### Critical generalized silent risk

```text
TIER1 fields auto-accepted but wrong
/ all labeled TIER1 fields
```

The latter is not misled by changes in the accepted denominator and is suited as the
primary safety metric.

### Critical routing recall

```text
critical errors routed to human/blocked
/ all critical errors
```

### Critical document silent failure

```text
released documents still containing at least one critical error
/ all released documents
```

## 12.4 Full-curve metrics

Do not look only at the two operating points 41% and 30%. At minimum plot:

```text
x = review load
 y = generalized critical silent risk
```

and report:

- critical error recall@10/20/30/40% review budget;
- risk–coverage curve;
- AUGRC or an equivalent mean undetected-risk metric.

## 12.5 Cost metrics

```text
DWS credits per invoice
API calls per invoice
P50/P95 latency
storage bytes
reviewer minutes
```

---

# 13. Datasets and anti-overfitting protocol

## 13.1 The identity of the existing 100

The existing 100 have already been used for result analysis and solution design, so
from the start of the Improve project they should be renamed:

```text
EVOLUTION / DEVELOPMENT CORPUS
```

They can no longer serve as the final held-out set.

## 13.2 Four classes of data

### EVO

Fully visible, used for:

- mining;
- finding;
- targeted eval;
- candidate development.

### REGRESSION

Held by the evaluator. Contains:

- known critical failures;
- clean negative controls;
- integrity attacks;
- irrelevant fields and other layouts.

It can be run repeatedly but must not be modified by the proposer.

### PROMOTION-k

Freshly drawn each round and hidden from the proposer. Only qualification results and
aggregate metrics are returned, never all per-sample answers.

Once used it is “burned” and cannot serve as the promotion set again next round.

### FINAL SEALED

Run exactly once after all rounds, for the final external results.

## 13.3 Query budget

Each round:

- at most 3 candidates;
- at most one PROMOTION query per candidate;
- failures cannot be patched indefinitely on the same promotion set;
- all queries are written to `evaluation_access_ledger.jsonl`.

## 13.4 Paired evaluation

Baseline and Candidate must run on exactly the same documents.

Downstream routing candidates: use the same frozen DWS responses to isolate provider
drift.

schema/escalation candidates: use paired live calls, recording call order, request
schema, credits, and raw responses.

## 13.5 Statistical uncertainty

- bootstrap at the document level; multiple fields of the same invoice are not
  independent samples;
- fix and record random seeds;
- report 95% bootstrap intervals;
- report exact numerators/denominators for small samples;
- never write “no new errors observed” as “risk proven absent”.

---

# 14. Experiment sequence: 41% → 30%

## R-1: semantics and integrity preparation

Complete all of P0; not counted as an Improve gain.

Acceptance:

- `policy_accept` separated from human decisions;
- accept values come from the ledger;
- absent / N/A / abstain separated;
- routing report versioned;
- Harness enters the execution fingerprint;
- bundle semantic verify;
- reviewer time / QA sampling recordable.

## R0: freeze the real baseline

Freeze:

```text
code revision
HAR-0001 digest
TIER1 field set
hard blockers
metrics/scorers
data split fingerprints
candidate query budget
```

Report:

- field review load;
- document touch rate;
- actions/doc;
- minutes/doc;
- critical generalized/selected risk;
- routing recall;
- DWS credits.

Only when remeasurement lands around 41% may we tell the outside story “41→30”.

## R1: eliminate worthless soft reviews

Goal: find

```text
reviewed
but mostly accept unchanged / confirm_absent
and randomized QA found no critical misses
```

Candidates:

```text
specific soft-warning cohorts
review → policy_accept
```

Requirements:

- do not touch hard blockers;
- one cohort per candidate;
- target + negative control;
- no new critical silent errors on the promotion set.

## R2: risk buckets and review budget policy

Building on R1's new feedback, construct conservative risk buckets:

```text
field × support × gates × warning set × document family
```

Do not trust point estimates directly; derive risk upper bounds/strata from sample size
and uncertainty.

Goal:

```text
maximize critical error recall under a 30% review budget
```

Candidates may adjust:

- which soft triggers force mandatory review;
- priority;
- QA sampling rate.

## R3: machine escalation in place of humans

Goal: move a portion of boundary fields from:

```text
review
```

to:

```text
escalate to agentic / focused extraction
→ re-gate
→ review only if unresolved
```

The added DWS credits and the saved human minutes must both be reported, proving this
is not “trading unlimited API for human labor”.

## Final: one-shot sealed evaluation

Final table:

| Version | Field review load | Document touch | Critical generalized silent risk | Critical routing recall | Minutes/doc | Credits/doc |
|---|---:|---:|---:|---:|---:|---:|
| R0 | measured | measured | measured | measured | measured | measured |
| R1 | measured | measured | measured | measured | measured | measured |
| R2 | measured | measured | measured | measured | measured | measured |
| R3 | measured | measured | measured | measured | measured | measured |
| Sealed final | measured | measured | measured | measured | measured | measured |

Pre-filling later numbers is forbidden.

---

# 15. Promotion Gates

## Gate 0: permissions and integrity

All of these must pass:

- forbidden files unchanged;
- trust kernel tests all green;
- bundle semantic verify all green;
- candidate diff within the allowlist;
- no doc ID / expected value hard-coding;
- execution fingerprint changes correctly.

## Gate 1: Must-Catch Regression

The following known critical cases must not move from review/block to auto_accept:

- citation fail;
- arithmetic fail;
- binding reject;
- label convention dispute;
- duplicate/conflict;
- missing required TIER1;
- document-level infrastructure blocked.

## Gate 2: Safety Non-Inferiority

On the same promotion docs:

```text
candidate critical generalized silent errors
≤ baseline critical generalized silent errors
```

Additionally:

- no new candidate-only document failures with severity=critical;
- report the paired document bootstrap delta;
- no obvious red flags in subgroups.

This is a conservative, hackathon-grade threshold, not a statistical guarantee of
permanent safety.

## Gate 3: Workload Benefit

Suggested per-round engineering threshold:

```text
field review load drops by at least 2.5 percentage points
OR reviewer minutes drop by at least 10%
```

This number is a preregistered engineering threshold, not a law of nature.

## Gate 4: Resource Budget

- DWS credits within the candidate manifest cap;
- P95 latency within the cap;
- no undisclosed new providers;
- no lowering QA sampling to manufacture a drop in the human rate.

## Gate 5: Human Promotion

The human sees:

- the finding;
- exact diff;
- predicted vs actual delta;
- target/regression/promotion results;
- added risks;
- rollback target.

then chooses:

```text
promote / reject / defer
```

---

# 16. Shadow, canary, and rollback

## 16.1 Shadow

The candidate first produces counterfactual routes for new invoices without touching
the real workflow:

```text
the active policy decides actual review
the candidate policy only records shadow decisions
```

This provides evidence from new distributions.

## 16.2 Canary

After promotion, apply first to a small fraction of low-risk cohorts, with QA sampling
raised.

## 16.3 Automatic rollback triggers

The active pointer may be rolled back to the previous version automatically, but the
Harness itself must not be auto-repaired. Triggers include:

- QA finds a candidate-only critical error;
- provider response drift exceeds the threshold;
- document touch / latency anomalies;
- integrity test failure;
- the share of new layouts suddenly rises.

All rollbacks are written to the append-only promotion ledger.

---

# 17. Provider Drift

Live tests in the current repo have already observed DWS output drift on the same batch
of PDFs at different times, so “policy improvement” and “provider change” must be
separated.

## 17.1 Replay Eval

Suited to:

- routing policy;
- review priority;
- warning taxonomy;
- downstream mapping.

Uses exactly the same raw DWS responses; results are deterministic.

## 17.2 Live Paired Eval

Suited to:

- extraction schema;
- mode selection;
- escalation policy.

Requirements:

- pair baseline/candidate on the same documents;
- freeze all raw requests and responses;
- report provider error / missing / confidence distribution;
- call order randomized or interleaved;
- never write provider drift up as candidate improvement.

## 17.3 Safe Mode

When drift triggers:

```text
pause new policy relaxations
raise the QA sample
fall back to the most recent safe harness
allow the human rate to exceed 30%
```

30% is the target under normal distribution, not a hard budget cap.

---

# 18. Explicit prohibitions

1. Agent-initiated promotion or release is forbidden.
2. Modifying the Trust Kernel is forbidden.
3. Modifying ground truth, scorers, the critical field set, or promotion rules is
   forbidden.
4. Letting the proposer read promotion/final labels is forbidden.
5. Repeated tuning on the same sealed set is forbidden.
6. Overwriting a failed candidate is forbidden; every attempt must use a new ID.
7. Deleting failed results, negative findings, or rollback records is forbidden.
8. Treating unreviewed fields as correct is forbidden.
9. Treating every human `accept` as noise-free ground truth is forbidden.
10. Using a reading model / DWS confidence as ground truth is forbidden.
11. Reducing review rate via `not_applicable`, field deletion, or loosened
    normalization is forbidden.
12. Rules hard-coding doc IDs, benchmark indices, or expected values are forbidden.
13. One candidate modifying multiple Harness components is forbidden.
14. Undisclosed increases in API calls, budget, latency, or providers are forbidden.
15. Changing QA sampling to flatter the human-review rate is forbidden.
16. Calling 41.1% a document review rate is forbidden unless remeasurement actually
    shows that.
17. Calling development-set improvements generalization is forbidden.
18. Writing “zero new observed errors” as “proof of zero risk” is forbidden.
19. Claiming “the system has self-improved” before a complete promoted cycle is
    forbidden.
20. Letting the system pass a known blocker to hit the 30% hard budget is forbidden.

---

# 19. Proposed code structure

```text
invoiceloop/
  harness.py                 # load immutable HarnessManifest
  routing.py                 # pure function: ledger+gates+policy → RoutingReport
  execution.py               # execution_fingerprint
  feedback.py                # adjudication → FeedbackEvent
  qa_sampler.py              # stratified random QA / propensity

  improve/
    models.py                # Finding/Candidate/Eval/Promotion schemas
    compile.py               # generate Experience Pack
    mine.py                  # deterministic weakness mining
    propose.py               # agent task pack / candidate manifest
    lint.py                  # diff allowlist / anti-cheat
    sandbox.py               # worktree and permissions
    metrics.py               # risk–coverage, human, cost
    evaluate.py              # targeted/regression/promotion
    promote.py               # human-only promotion
    report.py                # before/after + prediction audit

harnesses/
  HAR-0001/
  HAR-0002/

workspace/
  improve/
    feedback/events.jsonl
    findings/FIND-*/
    candidates/CAND-*/
    evaluations/EVAL-*/
    promotions/PROM-*.json
    improvement_ledger.jsonl
    active_harness.json
    evaluation_access_ledger.jsonl
```

Keep the project's existing filesystem, immutable directories, and append-only style;
there is no need to introduce a database for the hackathon.

---

# 20. CLI contract

```bash
# rebuild feedback events from authoritative runs and adjudications
python -m invoiceloop feedback compile --workspace ws

# deterministic statistics and finding drafts
python -m invoiceloop improve mine --workspace ws

# a human confirms a finding as actionable
python -m invoiceloop improve confirm-finding \
  --finding FIND-0012 --reviewer Stahl

# the agent proposes candidates only within allowlisted Harness components
python -m invoiceloop improve propose \
  --finding FIND-0012 --component routing_policy

# lint + targeted + regression
python -m invoiceloop improve evaluate \
  --candidate CAND-0012-A --stage regression

# one promotion-set query
python -m invoiceloop improve qualify \
  --candidate CAND-0012-A

# only a human can execute this
python -m invoiceloop improve promote \
  --candidate CAND-0012-A \
  --approved-by Stahl \
  --rationale "..."

# show the full 41%→X% trajectory
python -m invoiceloop improve report --workspace ws
```

---

# 21. Tests that must be added

## Trust / identity

- Harness digest changes → execution fingerprint must change;
- same input + different Harness must not replay an old run;
- accept_claim must take the ledger value;
- matrix tampering must not change the deliverable;
- semantic verify catches mis-bound final values;
- `confirm_absent/not_applicable/abstain` project differently.

## Improve permissions

- candidate modifies a forbidden path → reject;
- candidate contains doc ID / expected value → reject;
- candidate modifies the scorer → reject;
- candidate adds network calls/dependencies/budget → reject;
- candidate diffs multiple components → reject.

## Eval integrity

- the proposer cannot read private labels;
- promotion queries are counted in the access ledger;
- a consumed promotion set cannot be reused;
- baseline/candidate document sets must be exactly identical;
- metric bootstrap seeds recorded;
- field-level metrics must not be mistaken for document-level metrics.

## Improvement semantics

- an ordering candidate must not claim reduced review load;
- policy relaxation cannot override hard blockers;
- review rate drops but a new critical silent error appears → qualification fail;
- QA sampling drops → qualification fail;
- gaps between agent predictions and actual results are recorded and must not be
  overwritten.

---

# 22. Hackathon demo script

## Scene 1: conservative starting point

```text
HAR-0001
Mandatory field review load: 41.1%
```

Show a field with no real error that was sent to a human because of a soft warning.

## Scene 2: every review leaves structured feedback

The human clicks:

```text
accept_claim
reason = ROUTING_FALSE_POSITIVE
confidence = high
```

Show it entering a Feedback Event, not just mutating the current JSON.

## Scene 3: Finding

```text
This cohort caused 43 reviews,
0 critical corrections,
8 randomized QA checks,
no hard blocker.
```

## Scene 4: Agent Candidate

The agent may modify only one rule in `routing_policy.yaml` and writes a prediction:

```text
Expected review-load reduction: 4pp
Expected new critical silent errors: 0
```

## Scene 5: eval gating

Show on one screen:

```text
Targeted: PASS
Regression: PASS
Promotion: PASS
Integrity: PASS
Review load: 41.1% → 36.8%
Critical silent errors: unchanged
```

No pre-filling before the real numbers are in.

## Scene 6: Human Promote

The human clicks Promote, generating HAR-0002 and a PromotionRecord.

## Scene 7: the next invoice

The new run manifest explicitly binds HAR-0002; the same class of soft warning is auto
policy_accept, and the full audit chain explains why a human no longer needs to look.

## Demo closing

> **Every review becomes an eval. Every policy change must re-earn trust.**

---

# 23. Public claims allowed and claims forbidden

## Allowed claims once v0.1 is complete with one promotion cycle

- InvoiceLoop captures human review as structured feedback events.
- Repeated actionable feedback becomes bounded Harness candidates.
- Candidates cannot modify evidence, evaluators or production policy.
- Every candidate is tested against targeted and regression evals before human promotion.
- A promoted policy reduced measured review load from R0 to R1 on an unseen qualification set.
- Every future run binds the exact Harness version that produced its routing decisions.

## Allowed claims after the final sealed evaluation is complete

- On a fresh sealed DocILE-derived set, the promoted Harness reduced mandatory field review load from X% to Y% without increasing observed critical generalized silent failures.

Must carry:

- exact denominators;
- dataset scope;
- confidence intervals;
- human time and DWS cost;
- a non-production-applicability statement.

## Forbidden claims

- InvoiceLoop autonomously learns from every invoice.
- Human review is no longer required.
- The system guarantees less than 1% error.
- The underlying DWS model improved.
- 30% is universally optimal.
- The system is production-safe based only on DocILE.

---

# 24. Research and engineering grounding

This design absorbs the following ideas without copying their degree of autonomy:

1. **OpenAI, “Building self-improving tax agents with Codex”**  
   expert corrections → product traces → actionable findings → targeted eval → scoped
   engineering task → regression → human shipping.

2. **Lilian Weng, “Harness Engineering for Self-Improvement” (2026)**  
   A harness includes workflow, evaluation, permission control, and persistent state;
   the evaluator and permission control should sit outside the evolution loop, and
   humans should move up to the key abstraction layers.

3. **Agentic Harness Engineering (AHE), arXiv:2604.25850**  
   component / experience / decision observability; every change must be a falsifiable
   prediction.

4. **Self-Harness, arXiv:2606.09498**  
   Weakness Mining → Harness Proposal → Proposal Validation; candidates must pass
   regression before acceptance.

5. **Harness Updating Is Not Harness Benefit, arXiv:2605.30621**  
   being able to write Harness updates does not mean downstream actually benefits;
   InvoiceLoop must evaluate the real review/risk of future runs, not the prose quality
   of proposals.

6. **Adaptive Auto-Harness, arXiv:2606.01770**  
   in open task streams a single harness under constant dense updates can turn brittle;
   drift should be monitored, rollbacks kept, and local findings must not be
   unconditionally globalized.

7. **HarnessCompass, arXiv:2608.01918 (a very recent preprint)**  
   constrained evolution, component-wise optimization, and avoiding inter-component
   interference; in the first version one candidate changes only one component.

8. **Selective Classification, arXiv:1705.08500**  
   auto-accept versus reject/human is inherently a risk–coverage trade-off; single-point
   accuracy alone must not be used.

9. **Conformal Risk Control, arXiv:2208.02814 / ICLR 2024**  
   once sample-size and selection-bias conditions are met, calibrated procedures for
   controlling monotone risk may be studied; guarantees must not be overstated in the
   current small-sample hackathon phase.

10. **Dwork et al., adaptive data analysis / reusable holdout**  
    repeatedly viewing the same test set and changing strategy accordingly overfits;
    test-set exposure must be limited, promotion sets burned, and a one-shot final
    sealed set kept.

11. **NIST AI RMF 1.0**  
    explicit roles, feedback integration, continuous monitoring, TEVV, change
    management, third-party model drift, and human oversight.

Most of the 2026 harness papers above are recent preprints, suitable as architectural
inspiration but not as evidence that industry standards have already formed.

---

# 25. Final implementation adjudication

## PASS

- make the Improve Layer InvoiceLoop's core new narrative;
- take 41%→30% as a clear product goal;
- adopt the full loop feedback→finding→candidate→eval→human promotion→future run;
- use AHE-style three-way observability;
- use the Self-Harness mine/propose/validate skeleton;
- use Tax AI's trace-to-eval engineering path.

## HOLD until P0 is complete

- final-value authority binding;
- splitting human decision semantics;
- policy_accept;
- routing report;
- Harness execution identity;
- separating evaluator and product normalization.

## Explicitly not in the first version

- arbitrary repo self-modification;
- automatic promotion;
- joint multi-component optimization;
- model weight updates;
- passing the existing 100 off as the final held-out set;
- masking safety regressions with a single composite score.

**One-sentence conclusion:**

> The InvoiceLoop Improve Layer should not be an “agent that changes rules”; it should be
> a control plane that turns real human review into attributable evaluation tasks,
> permits only bounded Harness candidates, and requires every improvement to re-earn
> trust on unseen data.
