"""ADK Vision Reader Agent (invoiceloop/agents/vision.py).

Formulates targeted visual query prompts when fields are OCR-blocked or unsupported.

Single-Writer Discipline:
- Agent outputs ONLY pre-fill draft suggestions.
- Suggestions only pre-fill human review forms ("adopt-to-form, never to ledger").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runtime import call_gemini_model


class VisionReaderAgent:
    """ADK Agent formulating targeted visual prompts for OCR-blocked document slots."""

    def __init__(self, workspace: Path | str | None = None):
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def inspect_slot(
        self,
        doc_id: str,
        field: str,
        *,
        limitation_code: str | None = None,
        existing_value: str | None = None,
    ) -> dict[str, Any]:
        prompt = (
            f"Document ID: {doc_id}\n"
            f"Field Needing Review: {field}\n"
            f"Limitation Code: {limitation_code or 'OCR_UNAVAILABLE'}\n"
            f"DWS Existing Value: {existing_value or '(no value)'}\n\n"
            f"Task: Inspect the visual document for {field}. "
            "Formulate a precise reading answer.\n"
            "Respond in JSON: {\"field\": \"...\", \"suggested_value\": \"...\", \"confidence\": \"high|medium|low\", \"explanation\": \"...\"}"
        )

        res = call_gemini_model(
            prompt=prompt,
            system_instruction="You are an expert visual document reader inspecting un-OCRable or blocked invoice fields.",
            workspace=self.workspace,
            call_id=f"vision_{doc_id}_{field}",
        )

        json_out = res.get("json") or {}
        return {
            "doc_id": doc_id,
            "field": field,
            "suggested_value": json_out.get("suggested_value") or existing_value or "",
            "confidence": json_out.get("confidence", "medium"),
            "explanation": json_out.get("explanation", res.get("text", "")),
            "replayed": res.get("replayed", False),
        }
