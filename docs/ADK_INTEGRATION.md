# InvoiceLoop & Google ADK (Agent Development Kit) Integration

**"ADK makes agents capable; InvoiceLoop makes their actions accountable."**

This document details the multi-agent architecture, Google Agent Development Kit (ADK) integration, and the non-negotiable governance boundaries of **InvoiceLoop**.

---

## 1. Executive Summary & Architecture Overview

InvoiceLoop combines adaptive AI multi-agent orchestration (powered by **Google ADK** & **Gemini API**) with an immutable, deterministic governance & verification engine.

```text
               ┌───────────────────────────────────────────────────────────┐
               │           ADK Agent Runtime (Adaptive Multi-Agent)         │
               │                                                           │
   PDF Input ──┼─► [Extractor Agent] ──(DWS API)──► 提出初始 Claims         │
               │          │                                                │
               │          ├─► [Vision Inspector Agent] ──► 补充 OCR-blocked 疑难点│
               │          │                                                │
               │          └─► [Party Identification Agent] ──► 辨析代理商 vs 电台│
               └─────────────────────────────┬─────────────────────────────┘
                                             │ (产生 Unbound Draft Claims)
                                             ▼
               ┌───────────────────────────────────────────────────────────┐
               │          InvoiceLoop / BriefLoop (Deterministic Engine)   │
               │                                                           │
               │  1. Freeze Transaction  (模型只写草稿，Python 分配 ID)      │
               │  2. 6 Deterministic Gates (C1-C6 几何/算术/语义检查)         │
               │  3. Support Matrix       (四维支持强度推导)                   │
               │  4. Workbench HITL Queue (高风险路由给人工复核)                │
               │  5. Immutable Ledger     (Append-only 账本 + PROM 链)      │
               │  6. 5-Layer Verify       (离线防篡改 Bundle + 签名)          │
               └─────────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
                                  Deliverable ERP Output
```

---

## 2. ADK Agents Division of Labor

The ADK Layer is organized into specialized, autonomous Agents:

### A. Multi-Agent Improve Loop (`invoiceloop/agents/improve_loop.py`)
- **MinerAgent**: Scans mine reports and adjudication ledger patterns.
- **ProposerAgent**: Formulates candidate policy cohorts and schema description diffs.
- **CriticAgent (Adversarial Agent)**: Evaluates proposed cohorts to ensure true ground-truth values are protected. Specifically trained to independently reject invalid cohorts (such as the `due_date` cohort that saved 37 review slots at the cost of dropping genuine due dates).
- **EvaluatorNode**: Triggers deterministic `improve.evaluate()` counterfactual re-routing.

### B. Seller Party Identification Agent (`invoiceloop/agents/party.py`)
- Addresses the #1 silent error category (6/13 silent errors in the zero-touch test set: agency vs. broadcast station/seller confusion, e.g. *Regional Reps* vs *WARU-AM*).
- Inspects spatial OCR neighborhoods (`Remit to`, `Bill to`, `Agency`, `Station`).
- Outputs un-ID'd `field_drafts.json` for ingestion by `freeze.py`.

### C. Targeted Vision Reader Agent (`invoiceloop/agents/vision.py`)
- Formulates targeted visual query prompts for OCR-blocked or unsupported document crops.
- Outputs pre-fill draft suggestions for human review forms ("adopt-to-form, never to ledger").

---

## 3. Strict Governance & Authority Isolation

1. **Single-Writer Discipline**:
   - ADK Agents **only write un-ID'd draft claims or suggestions**.
   - Model outputs NEVER contain authority IDs (`claim_id`, `decision_id`, `run_id`).
   - Python transactions (`freeze.py`, `adjudicate.py`) assign IDs and append to the immutable ledger.

2. **Deterministic Gate Enforcement**:
   - Deterministic Gate checks (C1–C6) cannot be bypassed or skipped by LLM Agents.
   - An unperformed check is recorded as a blocking infrastructure failure, not a pass.

3. **Zero-API Offline Replay**:
   - All live API interactions log to `workspace/raw/agents/{call_id}.json`.
   - `INVOICELOOP_REPLAY=1` enables 100% offline, deterministic replay across the entire test suite.

---

## 4. Cloud Run & Container Deployment

InvoiceLoop provides a multi-stage Dockerfile:
- System Dependencies: `poppler-utils` (`pdftotext`, `pdftoppm`, `pdfinfo`).
- Python Runtime: 3.12-slim.
- Port: `8765` for Workbench loopback and ERP delivery integration.
- Deployment Targets: Google Cloud Run, GKE, or local Docker containers.
