# Arm U — unattended adjudication and approval (experimental arm)

> Status: **experimental arm, not the product default.** On the default path
> only a named human can still sign approvals (`approve.py`'s product
> discipline is unchanged); this arm is entered only via an explicit
> `python3 -m invoiceloop unattended --run …` invocation, and its approvals
> carry their own policy digest and an `agent:critic:` signature that is
> distinguishable from human approval at a glance.
>
> Origin: the implementation plan from the 2026-08-27 independent judge notes
> (PLAN-UNATTENDED-AP-ARM, incorporated into this repository). Design motive:
> `HITL_ADK_OAUTH_20_2026-08-27.md` — the three real failures of the
> single-clerk arm (a fake net, an EIN taken as an invoice number, and
> "queue is empty → sign") proved that "one model both judges and approves"
> is unacceptable.

## What this arm is

```
PDF → DWS → Python freeze/six gates/matrix          (existing, untouched)
              │
              ▼
   Runner.run_async() — SequentialAgent "unattended_pipeline"
     ├─ clerk    LlmAgent  per slot, page images in → AdjudicationDraft (no IDs)
     ├─ binder   BaseAgent Python: append_adjudication, signed agent:<model>
     ├─ critic   LlmAgent  per slot, re-reads the same images + the clerk draft
     ├─ binder2  BaseAgent Python: disagreements supersede via the
     │                    same writer, signed agent:critic:<model>
     ├─ gate     BaseAgent Python: deliverable recompute + unattended_policy
     │                    audit — a not-ready document never reaches
     │                    the approver at all
     ├─ approver LlmAgent  per ready document → {release, rationale}
     └─ binder3  BaseAgent Python: policy AND approver both yes →
                  append_approval(policy_digest=…)
```

The three model roles are three independent ADK apps (`invoiceloop_arm_u_clerk`
reuses the adjudicator's `invoiceloop_arm_ta` pattern, `…_critic`,
`…_approver`) whose sessions never mix; binder/gate are BaseAgents rather than
tools — a tool runs at model discretion, a BaseAgent inside a SequentialAgent
**cannot be skipped** (the same argument as the improve loop's EvaluatorNode).

## Approval signatures and digests

```text
approved_by   = unattended-policy-v3+agent:critic:<model>
policy_digest = sha256(POLICY_ID + R1..R10 rule text)
```

Changing a rule means a new policy id and a new digest; old approvals never
silently inherit semantics they were not given under (v1→v2: after the first
live acceptance round R5 gained amount/date format equivalence and R10 was
added; v2→v3: after PR review R4 records a missing role draft as
no-consensus, and R3 forbids a critic vouching for its own override).
Approval times are injected by the operator via `--decided-at` (a future
Cloud Run Job injects them from the trigger); no artifact reads the wall
clock. Human approvals pass no `policy_digest` (default None) — behavior
unchanged.

## The policy (unattended-policy-v3, R1–R10)

| Rule | The failure it stops (all measured) |
|---|---|
| R1 every posting-blocking slot carries a tip (census pending/pending_tier1 included) | "queue is empty → sign"; the first live round also showed that walking only review slots leaves TIER1 corroboration slots pending forever |
| R2 deliverable status is approvable | blocked/pending documents never reach the approver |
| R3 absence needs evidence (an override tip accepts only the page probe) | fake absence; and a role vouching for its own override |
| R4 TIER1 two-role agreement (a missing draft is no consensus) | one model checking its own judgement; a TIER1 slot read by a single role being released |
| R5 the corrected value is printed on the page (with format equivalence) | invented numbers; and ISO dates / bare amounts misjudged as absent (same family as §4.4) |
| R6 EIN ≠ invoice number | `58-0391492` is a tax ID |
| R7 terms prose ≠ date | `Due on Receipt` |
| R8 no correct on a label-absent field | filling in net when the page has no Net column |
| R9 the approver must independently say yes | a policy pass is not an approval |
| R10 a printed EIN voids a seller_vat_id absence | fake absence — in the first live round clerk **and** critic both missed the Taxpayer ID; only a deterministic rule could catch it |

The policy is pure Python (`invoiceloop/unattended_policy.py`); fixtures in
`tests/test_unattended_policy.py` give one counter-example per failure, zero
API.

## Authority boundaries (what the implementation may not do)

1. Do not alter the ID semantics of `append_adjudication` / `append_approval`
   — models still emit un-ID'd drafts only, Python remains the sole writer;
2. no DocILE annotations / truth / `eval_normalise` reads at runtime;
3. the public Cloud Run workbench stays read-only — a publicly writable
   adjudication ledger means forged testimony;
4. clerk and critic share no call or session; the approver sees no demo
   instructions;
5. credentials enter no image, no `raw/`, no artifact (the token in
   `agents/vertex_oauth.py` lives in memory only).

## Credential route (demo/acceptance)

`generativelanguage.googleapis.com` is unreachable from this network and the
machine has no ADC file. `--gcloud-oauth-project <id>` takes the in-memory
gcloud short-lived OAuth + Vertex AI `global` route (token never touches disk;
`oauth_run_metadata.json` records only the shape, never the token). Replay
works as before: `INVOICELOOP_REPLAY=1` is zero-API, with recordings under
`workspace/agent_calls/` (clerk `adj_*`, critic `crit_*`, approver `appr_*`
prefixes).

## P0 acceptance record (2026-08-27, three live rounds, demo docs)

Evidence: [`evidence/arm-u-2026-08-27/acceptance/`](evidence/arm-u-2026-08-27/acceptance/)
(third-round artifacts + MANIFEST). Model `gemini-3.7-flash` (Vertex AI
global, in-memory gcloud OAuth).

| Round | Result | What it taught |
|---|---|---|
| 1 (policy v1) | 0 approvals. The critic caught the clerk's fake net (Powell) on the spot; ISO dates / bare amounts were misjudged by R5; both roles missed the Taxpayer ID; TIER1 corroboration slots were not in the queue | → v2: R5 format equivalence, R10 EIN-voids-absence, queue extended to posting-blocking slots |
| 2 (v2) | crashed mid-run: the clerk chose accept on a slot with no frozen claim — one slot killed the whole arm; 429 quota pressure | → per-slot isolation in binders with recorded binding_failures; a factual claim-semantics instruction for the clerk; backoff 3s/6s/9s |
| 3 (v2, acceptance) | **26/26 written, 0 failures; all three documents reached an approvable state (2 ready + 1 ready_with_caveats); the policy blocked all three, 0 approvals** | below |

Per-document block reasons in round 3 (verbatim from `unattended_run.json`,
not consolidated):

- **UMI** (1): R8 — the clerk corrected the date to a real calendar date
  (correct), but the page prints no "Due Date" label, so the absence probe
  says label-absent. R8 was designed to catch fake nets and is strict for
  "printed but unlabeled" dates — a **known v3 candidate change, not made**:
  loosening it is a real risk trade-off, not a late-night decision.
- **Powell** (1): R4 — clerk and critic disagree on total_net (gold has no
  such slot). The two-role consensus gate **working as designed**: a
  disagreement blocks release — that is the feature, not a defect.
- **Cumulus** (7): the OCR-blocked document. The 5 clerk-corrected slots all
  fail R5 (the independent OCR has no words, machine checks cannot decide),
  plus two R4s on total_gross/total_net (critic overrode to confirm_absent).
  Final state is `ready_for_approval_with_caveats` (independent_ocr); the
  policy does not release. Charter rule four done right: what cannot be
  machine-checked is never released.

**Zero unsafe exports across three rounds; every "not approved" carries a
named rule and a real reason.** Against plan §6's acceptance: UMI is one rule
short; Powell took legal end-state ② (disagreement blocks); Cumulus is an
honest failure. The P0 conclusion: **the kernel absorbs an agent closing the
loop, while the deterministic policy releases nothing on the demo corpus —
and every one of those blocks stands on its own.**

## P2 deployment and first cloud execution (2026-08-28, Cloud Run Job)

One command, `scripts/deploy_cloud_run_job.sh`: Cloud Build builds the image →
an IAM-private Job (no URL, the SA uses native Vertex ADC) → execute → GCS
artifacts → evidence frozen under
[`evidence/cloud_run_job_2026-08-27/`](evidence/cloud_run_job_2026-08-27/).
The public `.run.app` workbench stays read-only.

Execution `invoiceloop-unattended-gqw8q` (succeeded 1/0, 24 artifacts in the
bucket):

- **This arm's first real approval happened in the cloud**: Cumulus
  (`046e0c49`) passed the gate under policy v3 with **zero violations**, the
  approver released, and AP-0001 is signed
  `unattended-policy-v3+agent:critic:gemini-3.7-flash` (digest in the ledger).
  The difference from local round 3: the cloud poppler build **recovered a
  text layer** from the degraded scan (`ocred: 3, ocr_blocked: []` — the
  README records that both outcomes are legal), so Cumulus was no longer
  OCR-blocked and the page evidence was complete.
- UMI was still stopped by R8 (an unlabeled printed date) and Powell still by
  R4 (two-role disagreement) — the same named rules as local round 3; not one
  loosened.
- Delivery projection: 2 ready_for_approval + **1 approved_for_export**.
- Honest history: the previous execution (`pmdtq`) died at the **upload step**
  on a `Path()` boxing bug in this repository (fixed in `479ed4b`); its three
  retries' artifacts existed only in logs and never reached the bucket.
  `gqw8q` is the complete post-fix execution.

## Alignment with the two hackathons

- **ATA**: the video may show Arm U carrying documents to export (the Utility
  story), but the authority boundary (ADK writes no ledger, the gate cannot
  be skipped, approvals carry a digest) must be on screen too — that is the
  differentiation from "one agent approves its own postings."
- **Nutrient**: Arm U does **not** enter the Nutrient narrative; that demo
  stays Arm A (human signature, audit bundle). Same repository, two arms —
  the README sections stay separate so no judge thinks unattended posting is
  the default.

## Not done

- Whether "the approver sees only a summary, not pixels" holds up awaits data
  from more real runs.
