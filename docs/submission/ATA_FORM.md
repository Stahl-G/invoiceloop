# All Things Agentic submission draft

> **Draft.** Replace the video placeholder before submitting. A 20-document
> ADK×HITL human walk record now exists
> ([`HITL_ADK_OAUTH_20_2026-08-27.md`](../HITL_ADK_OAUTH_20_2026-08-27.md)) —
> exploratory, development set, not qualification evidence; this document does
> not turn planned work into a result.

## Project

- **Name:** InvoiceLoop
- **Public repository:** https://github.com/Stahl-G/invoiceloop
- **Video:** `[PASTE THE 2–4 MINUTE ATA DEMO LINK HERE]`

## One-line pitch

InvoiceLoop gives an agent a useful job inside invoice review without giving it
authority: Google ADK agents may mine review history, propose a routing candidate,
and argue about it, while deterministic Python evaluates the candidate and a human
alone can approve promotion.

## What is agentic

The agentic component is the improvement loop in
[`ADK_INTEGRATION.md`](../ADK_INTEGRATION.md): a Google ADK `Runner` executes a
four-stage pipeline of miner, proposer, deterministic evaluator, and critic. The
Gemini stages write structured advisory output only. They do not assign ledger IDs,
write adjudications, change gates, promote a policy, or approve an invoice.

The control boundary is explicit:

- the model proposes un-ID'd candidates and an advisory report;
- Python assigns IDs, freezes artifacts, runs counterfactual evaluation, and
  applies promotion gates;
- a named human signs the final promotion decision.

## DWS heavy-lifting

Nutrient DWS remains the document-intelligence layer that extracts invoice values
and page grounding; ADK is a second-layer proposer for routing-policy improvement,
not a substitute extractor and not a decorative API call.

## Judge quickstart and replay

The zero-cost judge path is the same three-command quickstart in
[`README.md`](../../README.md):

```bash
git clone https://github.com/Stahl-G/invoiceloop
cd invoiceloop
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m invoiceloop demo --out /tmp/invoiceloop-demo
.venv/bin/python -m invoiceloop workbench --workspace /tmp/invoiceloop-demo --port 8793
# In a second terminal, after reviewing the browser page:
.venv/bin/python -m pytest tests/ -q
```

The live ADK extra is optional and is not needed for the judge-path demo:

```bash
.venv/bin/pip install -e ".[dev,gemini]"
```

The stored ADK evidence can be replayed without credentials when its workspace is
available, for example:

```bash
env -u GEMINI_API_KEY -u GOOGLE_API_KEY \
  INVOICELOOP_REPLAY=1 .venv/bin/python -m invoiceloop agents improve-loop \
  --workspace runs/adk-real-2026-08-07
```

For a clean-clone installation and product-path check, use
`bash scripts/fresh_venv_check.sh`.

## Evidence of the agentic requirements

- First live Gemini / ADK evidence:
  [`evidence/adk_live_2026-08-07/`](../evidence/adk_live_2026-08-07/).
- Real review-history ADK run and its negative findings:
  [`evidence/adk_real_2026-08-07/`](../evidence/adk_real_2026-08-07/).
- Google Agent Framework execution and authority boundary:
  [`ADK_INTEGRATION.md`](../ADK_INTEGRATION.md).
- Google Cloud deployment artifact and read-only smoke result:
  [`evidence/cloud_run_2026-08-07/`](../evidence/cloud_run_2026-08-07/).
- Pre-existing-work disclosure:
  [`DISCLOSURE.md`](../../DISCLOSURE.md).

## Explicit limitations

The critic's judgment quality has one corrected run on one review-history corpus;
the artifacts do not establish general agent quality or safe policy promotion.
Nothing in the agent layer changes the negative v2 qualification result. The
20-document ADK×HITL walk record (2026-08-27) is exploratory evidence on a
previously-exposed development set: list it with that caveat or not at all.

## Final checklist

- [x] Complete a human 20-document ADK×HITL walk and write its result document
      (2026-08-27, exploratory — see the walk record's limitations section).
- [ ] Replace the video placeholder with the uploaded ATA demo.
- [ ] Re-run `scripts/fresh_venv_check.sh` from the submitted commit.
- [ ] Confirm every claim still points to a committed artifact and not to this
      draft or to the implementation plan.
