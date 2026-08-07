"""ADK Seller Party Identification Agent (invoiceloop/agents/party.py).

Targets the #1 silent error category (6/13 silent errors in the zero-touch set):
Agency vs. Station seller_name confusion (e.g. Regional Reps vs WARU-AM).

Single-Writer Discipline:
- Agent outputs ONLY un-ID'd draft claims.
- Draft claims are ingested by freeze.py transactions, which assign claim IDs and enforce
  deterministic geometry & token-level bounding checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from invoiceloop import ocr
from .runtime import call_gemini_model


class PartyIdentificationAgent:
    """ADK Agent analyzing spatial OCR neighborhoods to distinguish seller vs. agency."""

    def __init__(self, workspace: Path | str | None = None):
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def identify_seller(
        self,
        doc_id: str,
        *,
        ocr_data: dict[str, Any] | None = None,
        candidate_seller: str | None = None,
    ) -> dict[str, Any]:
        """Analyzes spatial OCR text for 'Remit to', 'Station', 'Agency', 'Bill to' headers."""
        if not ocr_data:
            try:
                ocr_data = ocr.load_ocr(doc_id)
            except Exception:  # noqa: BLE001
                ocr_data = {}

        words = []
        if isinstance(ocr_data, dict) and "pages" in ocr_data:
            for page in ocr_data.get("pages", []):
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        line_str = " ".join(
                            w.get("value", "") for w in line.get("words", [])
                        )
                        if line_str.strip():
                            words.append(line_str.strip())

        ocr_sample = "\n".join(words[:40])  # First 40 lines containing headers

        prompt = (
            f"Document ID: {doc_id}\n"
            f"Candidate Extracted Seller: {candidate_seller or '(none)'}\n\n"
            f"OCR Header Text:\n{ocr_sample}\n\n"
            "Task: Distinguish the actual SELLER/STATION/SERVICE PROVIDER from any "
            "ADVERTISING AGENCY, REPS, or BUYER.\n"
            "Respond in JSON format: {\"seller_name\": \"...\", \"is_agency\": bool, \"confidence\": \"high|medium|low\"}"
        )

        res = call_gemini_model(
            prompt=prompt,
            system_instruction=(
                "You are an expert financial document auditor specializing in distinguishing "
                "media broadcast stations/sellers from advertising agencies."
            ),
            workspace=self.workspace,
            call_id=f"party_{doc_id}",
        )

        json_out = res.get("json") or {}
        seller_name = json_out.get("seller_name") or candidate_seller or ""

        return {
            "doc_id": doc_id,
            "field": "seller_name",
            "value": seller_name,
            "confidence": json_out.get("confidence", "medium"),
            "is_agency_flagged": json_out.get("is_agency", False),
            "replayed": res.get("replayed", False),
        }
