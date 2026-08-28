# InvoiceLoop Hackathon Scoring Rubric v0.1 — English companion

> **English translation of [`HACKATHON_RUBRIC_v0.1.md`](HACKATHON_RUBRIC_v0.1.md), source sha256 `30c5735e269ab79cdd74db4d4c2212f7e941c05d2608c78193f1ecc3b1a15a00`.**
> The original declares itself frozen ("its body remains verbatim") and is
> byte-unchanged; this companion is a translation only, not an authority.
> Translated 2026-08-28.


> **Freeze note (this section was appended by the freeze commit; the body was not changed)**
>
> - **Status**: FROZEN. This file is committed **before** scoring against repo facts, to freeze the scoring criteria and weights.
> - **Source**: user-provided, not an official Nutrient score sheet; an internal review standard reverse-engineered from the official requirements (the Overall Round looks at Progress/Concept/Feasibility; the Sponsor Round requires DWS to carry a core document operation and stresses deterministic output/confidence judgment/human intervention/audit trail).
> - **The body is preserved verbatim**; no dimension's weight is adjusted to fit the repo's current state. If the weights are to be changed later, open a separate v0.2 and state the reasons for and the date of the change; do not overwrite v0.1 in place.
> - **Freeze-purity limitation (must be registered explicitly)**: this file was written by Claude, and `CLAUDE.md` enters the context automatically at the start of a session, and it already contains claims about this repo's results (M0–M4 delivered, 116 tests, lift 4.10×/3.04×, and so on). This is therefore a freeze made **before reading the implementation code**, not a freeze made **with zero knowledge of the repo**. Per Charter Six, this limitation must appear together with any scoring result that cites this rubric.

Sure. The **InvoiceLoop Hackathon Scoring Rubric v0.1** below is written fully independently of your repo, to freeze the scoring criteria up front and keep the agent from "tailoring" the evaluation scale after reading the existing implementation.

These are not officially published numeric weights, because Nutrient has not released a detailed score sheet for the sponsor round; this is an internal review standard reverse-engineered from the official requirements. The official Overall Round explicitly looks at three things: **Progress, Concept, Feasibility**. The Nutrient Sponsor Round stresses: DWS must carry at least one meaningful core document operation, with particular emphasis on deterministic output, confidence judgment, human intervention, and a complete audit trail.

For InvoiceLoop, the most central scoring question should be:

> **Does InvoiceLoop, without throwing every invoice to a human, meaningfully reduce silent errors relative to the raw DWS output, while making every automatic release, human review, and final correction explainable, traceable, and replayable?**

---

## One. Pass the qualification gates first — no direct scoring

The officials require a public repo or shared link, setup instructions, a 2–4 minute end-to-end demo, and a one-sentence statement of where DWS carries the core work.

| Gate | What is checked | Handling |
|---|---|---|
| G1: DWS core use | Whether the Nutrient DWS API, SDK, or Viewer carries a real core document operation, rather than one decorative API call | **On FAIL the submission is not eligible for the Nutrient Sponsor Challenge** |
| G2: evidence integrity | Whether there are fabricated metrics, hard-coded demo results, test-set labels used in runtime decisions, or concealed failure samples | Marked **INVALID, final score 0** when there is definite evidence |
| G3: runnable closed loop | Whether there is at least one real "upload → DWS → decision → review/release → final result" run | Without one, the final score is capped at **59** |
| G4: submission completeness | Whether the repo/shared link, installation instructions, 2–4 minute video, and DWS heavy-lifting statement are all present | If anything is missing, the final score is capped at **89** |
| G5: competition-timeline compliance | Whether pre-competition code, code added during the competition, and reused components are disclosed | The agent does not judge violations itself; mark `REQUIRES_HUMAN_CONFIRMATION` |

The official instructions say teams should build apps from scratch. Since the official online competition runs from 2026/8/17 to 9/3 of the same year, keep a clear commit timeline and disclose which parts are pre-existing general components and which were completed inside the competition window.

---

# Two. The 100-point official scoring table

## Score structure

- **Overall Round proxy: 30 points**
  A + B + C, corresponding to the official Concept, Progress, Feasibility.
- **Nutrient Sponsor Round proxy: 63 points**
  D + E + F + G + H.
- **Submission quality: 7 points**
  I.

| ID | Scoring dimension | Points |
|---|---|---:|
| A | Real problem and project concept | 10 |
| B | Progress and end-to-end execution | 12 |
| C | Deployment and startup feasibility | 8 |
| D | Depth of Nutrient DWS integration | 15 |
| E | Reliability improvements and experimental evidence | 20 |
| F | Risk routing and Human-in-the-Loop | 13 |
| G | Audit, sourcing, and replayability | 10 |
| H | Innovation and differentiation | 5 |
| I | Submission materials and demo presentation | 7 |
|  | **Total** | **100** |

---

## A. Real problem and project concept | 10 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Clear users and workflow | 3 | Names a concrete role — AP clerk, finance reviewer, auditor, ERP operator, or another specific role — rather than the blanket term "enterprise user" |
| Clear cost of errors | 3 | Explains which errors cause mispayment, duplicate payment, tax problems, vendor errors, or audit risk |
| Clear target outcome | 2 | The goal is not "more accurate recognition" but fewer silent errors and less worthless review, while keeping automation |
| Fit with the challenge theme | 2 | Clearly explains why this is a problem of "making people genuinely trust document results" |

### Scoring anchors

- **0–2:** Just "AI OCR for invoices".
- **3–5:** Has an invoice-recognition scenario, but no clear user, error cost, or workflow.
- **6–8:** Problem, users, and trust risks are clear.
- **9–10:** Can state in one sentence "who, at which step, suffers what loss from which class of silent error, and how InvoiceLoop changes the decision".

An ideal one-sentence concept would be:

> InvoiceLoop is a risk-aware verification layer that turns raw invoice extraction into an auditable decision: safe fields flow through, risky fields go to a human with the exact source evidence, and every decision can be replayed.

---

## B. Progress and end-to-end execution | 12 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Complete core pipeline | 4 | Upload invoice → DWS extraction → normalization/validation → risk decision → automatic release or human review → final result |
| The normal path | 2 | At least one real clean invoice completes automatic processing successfully |
| The exception path | 3 | At least one real risky invoice is correctly intercepted, explained, corrected, and approved |
| Reproducible runs | 3 | Clear setup, pinned configuration, test commands, and a repeatable example |

### Situations that cannot score high

- The front-end page opens, but the core results come from static JSON.
- Only a notebook benchmark, with no interactive product loop.
- Only the happy path, with no error, failure, or human-intervention path.
- The README claims completion, but no matching implementation can be found in the repo.

---

## C. Deployment and startup feasibility | 8 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Deployment and integration path | 2 | Can explain how it enters an ERP, AP, purchasing, or document workflow |
| Cost and latency | 2 | Reports DWS credits per page or per invoice, latency, and the mode-selection strategy |
| Privacy and security | 2 | API keys never reach the front end, no secrets are committed, and document and log retention policies are stated |
| Business adoption logic | 2 | Explains who pays, which manual steps it replaces, and why it is not a display-only demo |

If the project uses different modes such as `understand` and `agentic`, full-score evidence should include:

- which documents go through the low-cost mode first;
- what signal triggers the expensive mode;
- whether this dynamic routing actually improves the cost–reliability relationship.

DWS currently splits extraction into modes such as text, structure, understand, and agentic, and stresses choosing by speed, cost, and processing depth.

---

## D. Depth of Nutrient DWS integration | 15 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| DWS carries the core operation | 5 | Invoice parsing, structured extraction, Viewer review, or another key document operation genuinely depends on DWS |
| Uses structured evidence | 4 | Not just reading the final strings, but also using confidence, page, bounding box, citation, match label, or structural information |
| DWS output drives decisions | 3 | DWS output genuinely affects automatic release, mode escalation, field review, or UI highlighting |
| Uses DWS differentiating capabilities | 3 | Demonstrates at least one real advantage among source grounding, in-document review, deterministic processing, Viewer, Processor, and signatures |

Nutrient's Data Extraction API returns structured results with page numbers, coordinates, sources, and confidence, precisely so that downstream systems can validate, route, and conduct human review — not merely to hand a paragraph of text to an LLM.

### Score caps

- DWS only converts the PDF to text, and structure or sources are never used afterward: usually no more than **8/15**.
- DWS results take part in no actual decision: usually no more than **6/15**.
- After removing DWS, only an OCR endpoint needs swapping and product behavior is completely unchanged: usually no more than **7/15**.
- There is no requirement to force multiple Nutrient products into the calls for points; **one API used deeply beats three decorative API calls.**

---

## E. Reliability improvements and experimental evidence | 20 points

This is the single most important dimension for InvoiceLoop.

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Held-out evaluation design | 4 | Tuning set separated from the final test set; test labels take no part in threshold selection or runtime decisions |
| Raw baseline comparison | 4 | At least compares raw DWS, a simple confidence threshold, and full InvoiceLoop |
| Extraction and critical-field metrics | 4 | Reports DocILE-related metrics, and separately lists performance on business-critical fields |
| Risk–coverage–human load | 4 | Reports silent errors, automation coverage, and human review load together, ideally with threshold curves |
| Error analysis and ablation | 2 | States what the system concretely fixed and on which documents it still fails; how results change when modules are removed |
| Reproducibility and statistical honesty | 2 | Pinned samples, versions, and configuration; no overstrong conclusions on small samples; reports denominators and uncertainty |

DocILE's official tasks are KILE and LIR: KILE evaluates field type and location, and LIR additionally requires correct grouping of line items; the official evaluator provides AP, F1, precision, and recall, aggregated with micro averaging. The location annotations themselves exist to support human review and audit, which aligns closely with InvoiceLoop's trust loop.

But **DocILE AP/F1 cannot by itself prove InvoiceLoop trustworthy**. They measure extraction, localization, and line-item grouping; they do not directly answer:

- whether wrong results are automatically released;
- whether wrong results would hurt the business;
- whether human review volume actually falls;
- whether the system gives wrong results a false sense of safety.

### The recommended core-metrics contract

Before testing, pre-declare a set of `critical_fields`. Examples include:

- `invoice_number`
- `issue_date`
- `due_date`
- `currency`
- `net_amount`
- `tax_amount`
- `total_amount`
- `supplier_name`
- `supplier_tax_id`
- `buyer_tax_id`
- `purchase_order_number`
- `payment_or_bank_details`

and explain why certain fields do or do not belong to the critical set. Once test results are in, you may not cherry-pick the best-performing fields as the "critical fields".

The following metrics are recommended as mandatory reporting:

```text
critical_field_accuracy
= correctly predicted critical fields / all annotated critical fields
```

```text
critical_document_pass_rate
= documents containing no critical-field error / all evaluated documents
```

```text
field_silent_error_rate
= critical fields auto-accepted but actually wrong / all auto-accepted critical fields
```

```text
document_silent_failure_rate
= documents still containing at least one critical-field error after automatic release
  / all automatically released documents
```

```text
automation_coverage
= automatically released documents / all evaluated documents
```

```text
document_review_rate
= documents entering human review / all evaluated documents
```

```text
field_review_load
= fields a human is asked to inspect / all extracted fields
```

```text
critical_error_routing_recall
= critical-error documents correctly routed to human review
  / all documents containing critical errors
```

In addition, it is recommended to report:

- average processing latency per invoice;
- credits/cost per page or per invoice;
- how many fields a reviewer must on average confirm or correct;
- net improvement from raw DWS → InvoiceLoop;
- results grouped into clean docs and risky docs;
- results under different layout clusters or document qualities.

### Key scoring principle: look for Pareto improvements, not thresholds pulled out of thin air

Do not write the following numbers directly as hard scientific success criteria:

- silent error rate below 1%;
- human load below 30%.

Unless backed by a real AP business process, payment risk, or a customer SLA, they are at most **business-scenario targets**, not a natural dividing line between project success and failure.

The agent should first judge whether InvoiceLoop, relative to raw DWS, achieves at least one of the following:

1. lower silent errors at the same human load;
2. higher automation coverage at the same silent-error level;
3. both silent errors and human load lowered together;
4. shifting humans from "checking every field" to "checking only genuinely high-risk fields".

If the work only moves a confidence threshold and does not beat a simple baseline on the risk–coverage curve, dimension E should usually not exceed **11/20**.

### Preventing metric gaming

None of the following counts as high reliability:

- every document goes to a human, so silent errors are zero;
- every field is rejected, so nothing wrong is ever released;
- every document is auto-accepted, so the automation rate is 100%;
- only successful samples are shown;
- thresholds are repeatedly tuned on the same batch of test documents;
- DocILE ground truth is used in runtime rules;
- the official evaluator is not used, yet a custom string-matching result is called a "DocILE benchmark score".

If you did not run with DocILE's official prediction format, bbox matching, and evaluator, use:

> "DocILE-derived evaluation on selected fields"

rather than:

> "Official DocILE benchmark score".

---

## F. Risk routing and Human-in-the-Loop | 13 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Field importance and risk policy | 4 | High-risk fields such as amounts, currency, and tax IDs follow handling rules different from low-risk fields |
| Not relying on raw confidence alone | 3 | Combines amount identities, date logic, tax relationships, missing fields, mode disagreement, or source quality |
| The in-document review experience | 3 | The reviewer sees the original page and the matching highlight, not just a JSON table |
| Correction, approval, and failure fallback | 2 | Human corrections are recorded; when something cannot be confirmed it can stay unresolved instead of forcing a guess |
| Preventing review-all | 1 | There is evidence the system genuinely reduces worthless human inspection |

Nutrient's official description of governed document AI is exactly this: every field carries confidence and source grounding; high-confidence results can flow through and low-confidence results enter the human queue; humans should inspect and correct in the real document context.

### Examples of full-score behavior

For one invoice:

- `supplier_address` has low confidence but does not affect payment, so low-priority review is acceptable;
- `total_amount` disagrees with the line-item sum, so even with high DWS confidence it must go to a human;
- `currency` is missing while amounts are present; the system must not default to USD and then silently release;
- when the reviewer clicks a risky field, the matching location on the original invoice is highlighted;
- after a correction, an explicit approve click is required — editing must not auto-approve.

---

## G. Audit, sourcing, and replayability | 10 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Raw input and DWS output | 2 | Stores document ID/hash, DWS request mode, the raw response or a trusted reference to it |
| Policy and versions | 2 | Stores threshold, policy version, schema version, code or model version |
| Field source evidence | 2 | Final values traceable to page, bbox, citation, or an explicit human origin |
| Decisions and human corrections | 2 | Records why something was auto-released/escalated/reviewed, and who changed what |
| Replay and final export | 2 | Judgments can be rebuilt from frozen inputs and configuration; the final export is bound to the audit record |

An ideal single-field record looks at least like:

```json
{
  "document_hash": "...",
  "field": "total_amount",
  "dws_raw_value": "1,280.00",
  "normalized_value": 1280.0,
  "dws_confidence": 0.7,
  "source_page": 1,
  "source_bbox": [0.61, 0.78, 0.81, 0.83],
  "policy_version": "invoice-risk-v0.3",
  "decision": "human_review",
  "reason_codes": [
    "TOTAL_LINE_ITEM_MISMATCH",
    "CRITICAL_FIELD"
  ],
  "human_action": {
    "action": "corrected_and_approved",
    "previous_value": 1280.0,
    "final_value": 1230.0
  }
}
```

"Recording the current final JSON" is not audit; audit must preserve **the relationship between the original result, the decision rules, the correction process, and the final result**.

---

## H. Innovation and differentiation | 5 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| More than an extraction wrapper | 2 | The value comes from the reliability control layer, not from simply adding a UI to DWS |
| Generalizable trust architecture | 2 | The approach extends to receipts, purchase orders, claims, or other documents |
| A concrete technical/product insight | 1 | For example, demonstrating that "confidence is not the final decision; risk should be decided jointly by field importance and empirical error rate" |

If the core function is only:

> upload PDF → call DWS → show JSON

it usually scores no more than **1/5**.

If the core function is:

> DWS provides structure and sources → InvoiceLoop calibrates risk → escalates or seeks human confirmation for critical errors → forms a complete audit chain

then it qualifies for a high score.

---

## I. Submission materials and demo presentation | 7 points

| Sub-item | Points | Full-score standard |
|---|---:|---|
| Complete official materials | 2 | Project name, one-sentence pitch, public repo/shared link, setup instructions, DWS heavy-lifting statement |
| A 2–4 minute end-to-end demo | 3 | Actually uploading and running, not just slides or screenshots |
| Clean and risky cases shown together | 1 | One automatically released, one intercepted and corrected by a human |
| Metrics honest and easy to understand | 1 | No pile of benchmark numbers; clearly shows "how many fewer errors, how much less to inspect, why it is trustworthy" |

The official Nutrient submission explicitly requires a 2–4 minute working end-to-end demo.

### Suggested video structure

**0:00–0:20: The problem**

> Invoice extraction is often almost right. In accounts payable, one silent error can be more expensive than dozens of manual reviews.

**0:20–0:45: The product loop**

Show upload → DWS → InvoiceLoop risk decision.

**0:45–1:20: Clean case**

Clearly show automatic release and source grounding.

**1:20–2:10: Risky case**

Show a high-confidence field whose amount logic is inconsistent, or a low-confidence critical field, correctly routed to the reviewer.

**2:10–2:40: Human correction and audit**

Show the source highlight, the correction, the approval, and the audit trail.

**2:40–3:10: The evidence**

Show only the most important risk–coverage results:

- raw DWS;
- simple threshold;
- InvoiceLoop;
- silent failure;
- automation coverage;
- review load.

**3:10–3:30: DWS heavy lifting**

State plainly what DWS did, and why InvoiceLoop is not replacing DWS but making its output safe to enter a real process.

---

# Three. Rules for scoring evidence

The scoring agent must follow these rules.

## 1. Score only what has been verified

Evidence priority for technical claims:

1. a repeatable actual run;
2. automated tests and frozen benchmark artifacts;
3. real implementation code;
4. screenshots or screen recordings;
5. README claims;
6. TODOs, roadmaps, and plans.

Suggested scoring caps:

| Evidence status | A single technical sub-item earns at most |
|---|---:|
| Repeatable run with output | 100% |
| Code, tests, and results all present, but the agent environment cannot rerun them | 80% |
| Implementation code but no test or run evidence | 60% |
| README, screenshots, or verbal claims only | 40% |
| Plans or TODOs only | 0% |

The business and product dimensions may use interviews, flowcharts, and explicit user assumptions as evidence; they are not required to be written in code.

## 2. No double counting

The same piece of evidence cannot simultaneously serve as the complete proof of:

- DWS depth;
- reliability improvement;
- Human-in-the-Loop;
- audit capability;

all four at once.

For example, storing DWS confidence:

- can prove DWS output was used;
- but cannot automatically prove the routing was correct;
- still less that human load fell;
- nor that the whole process is replayable.

## 3. Distinguish states explicitly

Every feature must be labeled as:

- `IMPLEMENTED_AND_VERIFIED`
- `IMPLEMENTED_NOT_RUN`
- `CLAIMED_ONLY`
- `PLANNED`
- `NOT_FOUND`
- `CONTRADICTED`

"Planned" must not be written as "partially implemented".

---

# Four. Internal score ceilings

These are not official disqualification rules; they exist to keep the agent from being misled by a pretty README or UI.

| Missing item | Final-score ceiling |
|---|---:|
| No real end-to-end run | 59 |
| No held-out evaluation, or no raw DWS baseline | 69 |
| No human exception-handling path at all | 74 |
| No verifiable audit trail | 84 |
| Incomplete official submission materials | 89 |

When several ceilings trigger at once, take the lowest:

```text
final_score = min(raw_score, all_applicable_score_ceiling)
```

A G1 or G2 failure does not use the normal ceilings; it is marked `INELIGIBLE` or `INVALID` respectively.

---

# Five. Interpreting the score

| Final score | Internal meaning |
|---|---|
| 90–100 | Submission-ready; complete evidence at sponsor-winner level |
| 80–89 | Strong contender; product and evidence are both strong, but one clear gap remains |
| 70–79 | Credible submission; the core holds, but reliability, audit, or the demo is incomplete |
| 60–69 | Working prototype; a real implementation exists, but "trustworthy" is not yet proven |
| 40–59 | Fragmented demo; some components done, the closed loop missing |
| 0–39 | Does not meet the core of the challenge, or is nearly impossible to verify |

This is only a project-maturity banding, **not a prediction of award probability**, because the quality of the other entries and the sponsor's final preferences cannot be known.

---

# Six. A prompt that can be handed directly to the scoring agent

```text
SYSTEM — InvoiceLoop Evidence-Bound Hackathon Judge v0.1

You are the evidence-bound hackathon judge for the InvoiceLoop project.

InvoiceLoop is entering the Nutrient DWS Challenge. Your task is not to encourage the developers,
nor to recite the project from its README, but to judge, against one fixed commit and a set of
frozen submission materials, whether the project currently truly achieves:

1. a meaningful core Nutrient DWS integration;
2. lower business-critical silent errors than raw DWS;
3. a demonstrable improvement between reliability and human load;
4. humans brought in only when necessary, and given the source text in every case;
5. processing records that are explainable, traceable, and replayable;
6. a product loop that runs, demos, and deploys.

You must use the following scoring dimensions:

A. Real problem and project concept: 10
B. Progress and end-to-end execution: 12
C. Deployment and startup feasibility: 8
D. Depth of Nutrient DWS integration: 15
E. Reliability improvements and experimental evidence: 20
F. Risk routing and Human-in-the-Loop: 13
G. Audit, sourcing, and replayability: 10
H. Innovation and differentiation: 5
I. Submission materials and demo presentation: 7

Total: 100.

Review protocol:

1. Evaluate only the named commit; do not use later branches or uncommitted changes.
2. Check the qualification gates before scoring.
3. Technical claims must cite repo path:line, test names, benchmark artifacts,
   run logs, or demo timestamps.
4. When README and code conflict, runnable code and test results win.
5. TODOs, roadmaps, and future plans earn no implementation points.
6. The same piece of evidence may not earn full credit in multiple dimensions.
7. When no evidence is found, write NOT_FOUND; do not infer a feature exists from
   file names or architecture diagrams.
8. "Could not run" is not "ran and failed", but it must be marked IMPLEMENTED_NOT_RUN,
   and the evidence score capped.
9. Check the benchmark for data leakage:
   - test labels must not take part in threshold selection;
   - test documents must not be used for prompt, schema, or rule tuning;
   - repeatedly finding the best threshold on the test set and then reporting that
     same test result is forbidden.
10. Unless the DocILE official prediction format and evaluator are used, it may not
    be called an official DocILE benchmark score.
11. Do not award a high reliability score because the system sends every document
    to a human.
12. Do not award a high automation score because the system auto-accepts everything.
13. Focus on judging whether InvoiceLoop achieves a Pareto improvement in
    risk–coverage over raw DWS or a simple confidence threshold.
14. All scores must be integers, with per-item reasons given for every deduction.
15. Apply all applicable score ceilings; the final score is the smaller of the raw
    score and the lowest ceiling.

Qualification gates:

G1 Does DWS carry the core document operation.
G2 Are there fabricated metrics, hard-coded results, or test-label leakage.
G3 Is there a real end-to-end run.
G4 Are the repo/shared link, setup, 2–4 minute demo, and DWS heavy-lifting statement
   present.
G5 Are pre-competition code and code added during the competition clearly disclosed.

Do not use vague evaluations in the output, such as "decent", "fairly strong", or
"has potential".
You must give verifiable evidence, exact scores, key gaps, and the highest-ROI
next steps.
```

---

# Seven. Suggested machine-readable output format

```json
{
  "rubric_version": "invoiceloop-hackathon-v0.1",
  "evaluated_commit": "",
  "artifacts_reviewed": [],
  "eligibility": {
    "G1_dws_core_use": {
      "status": "PASS",
      "evidence": []
    },
    "G2_evidence_integrity": {
      "status": "PASS",
      "evidence": []
    },
    "G3_end_to_end_run": {
      "status": "PASS",
      "evidence": []
    },
    "G4_submission_completeness": {
      "status": "PASS",
      "evidence": []
    },
    "G5_timeline_compliance": {
      "status": "REQUIRES_HUMAN_CONFIRMATION",
      "evidence": []
    }
  },
  "scores": {
    "A_problem_and_concept": {
      "score": 0,
      "max": 10,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "B_progress_and_execution": {
      "score": 0,
      "max": 12,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "C_feasibility": {
      "score": 0,
      "max": 8,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "D_dws_integration": {
      "score": 0,
      "max": 15,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "E_reliability_evidence": {
      "score": 0,
      "max": 20,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "F_risk_routing_and_hitl": {
      "score": 0,
      "max": 13,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "G_audit_and_replay": {
      "score": 0,
      "max": 10,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "H_innovation": {
      "score": 0,
      "max": 5,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "I_submission_and_demo": {
      "score": 0,
      "max": 7,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    }
  },
  "round_proxies": {
    "overall_round": {
      "score": 0,
      "max": 30
    },
    "nutrient_sponsor_round": {
      "score": 0,
      "max": 63
    },
    "submission_quality": {
      "score": 0,
      "max": 7
    }
  },
  "raw_total": 0,
  "applicable_score_ceilings": [],
  "final_total": 0,
  "verdict": "NOT_READY",
  "verified_strengths": [],
  "critical_gaps": [],
  "unverified_claims": [],
  "benchmark_integrity_findings": [],
  "highest_roi_actions": [
    {
      "priority": 1,
      "action": "",
      "expected_point_gain": 0,
      "reason": ""
    }
  ]
}
```

---

## Final advice

This rubric should be frozen **before** the agent looks at the repo. Scoring against repo facts may follow, but do not raise the weight of a dimension just because the project happens to have built that feature now, and do not retroactively lower a dimension's importance just because something is not yet implemented.

In particular, freeze the following three principles:

1. **Raw extraction accuracy is not the end goal.**
2. **0 observed errors does not equal having proven a true error rate below 1%.**
3. **Real success is improving the risk–coverage curve relative to the baseline, not luckily crossing a 1%/30% threshold pulled out of the air in advance.**
