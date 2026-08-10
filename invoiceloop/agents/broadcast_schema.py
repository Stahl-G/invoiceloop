"""ADK advisor for the broadcast schema pilot.

The agent sees only an aggregate development report.  It drafts descriptions;
Python validates the exact field set and writes the advisory artifact.  It has
no access to PDFs, truth annotations, slots, harness IDs or promotion state.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from invoiceloop.fields import FIELDS

from .runtime import _resolve_model, export_credential_for_adk

APP_NAME = "invoiceloop_broadcast_schema"
STATE_KEY = "broadcast_schema_draft"


class BroadcastSchemaDraft(BaseModel):
    """Model-facing draft; Python still owns candidate identity and activation."""

    invoice_number: str
    issue_date: str
    due_date: str
    seller_name: str
    seller_vat_id: str
    buyer_name: str
    total_net: str
    total_vat: str
    total_gross: str
    amount_due: str
    rationale: str = ""
    risks: list[str] = Field(default_factory=list)


def _instruction(report: dict[str, Any]) -> str:
    return (
        "You are an advisory schema writer for a US broadcast advertising "
        "billing pilot. You receive only an aggregate development report. "
        "Draft exactly one description for each of the ten existing fields. "
        "Do not add fields, IDs, policy rules, expected values, routes, or "
        "promotion instructions. Do not infer missing page values.\n\n"
        "Semantics that must be preserved: invoice_number is an explicitly "
        "labelled invoice/bill identifier, not contract/order/contact IDs; "
        "issue_date and raw due_date require explicit printed dates. The raw "
        "due_date field must never contain a date calculated from payment terms. "
        "A separate deterministic post-extraction layer emits calculated_due_date "
        "from an explicitly labelled base date and an explicit relative term; "
        "do not put that derived value into raw due_date. seller_name is the paid "
        "media seller/station and buyer_name is the explicitly billed "
        "advertiser/agency; seller_vat_id is VAT only, not EIN/FCC/callsign; "
        "Gross, Net, Agency Commission, Tax and Amount Due must follow printed "
        "labels without arithmetic invention. Gross/Net convention disputes "
        "remain human applicability review.\n\n"
        f"Aggregate report:\n{json.dumps(report, ensure_ascii=False, indent=1)}\n\n"
        f"Exact fields required: {', '.join(FIELDS)}."
    )


def _validate_draft(value: Any) -> dict[str, Any]:
    if isinstance(value, BroadcastSchemaDraft):
        payload = value.model_dump()
    elif isinstance(value, dict):
        payload = BroadcastSchemaDraft.model_validate(value).model_dump()
    else:
        raise ValueError("ADK 没有返回 typed broadcast schema draft")
    descriptions = {field: payload.get(field) for field in FIELDS}
    if any(not isinstance(text, str) or not text.strip()
           for text in descriptions.values()):
        raise ValueError("ADK schema draft 含空 description")
    payload["descriptions"] = {field: descriptions[field].strip()
                                for field in FIELDS}
    for field in FIELDS:
        payload.pop(field, None)
    return payload


async def _run(model: Any, report: dict[str, Any]) -> dict[str, Any]:
    agent = LlmAgent(
        name="broadcast_schema_writer",
        model=model,
        instruction=_instruction(report),
        output_schema=BroadcastSchemaDraft,
        output_key=STATE_KEY,
    )
    service = InMemorySessionService()
    await service.create_session(
        app_name=APP_NAME, user_id="invoiceloop", session_id="broadcast",
        state={"report_digest": report.get("development_doc_ids_sha256")},
    )
    runner = Runner(app_name=APP_NAME, agent=agent, session_service=service)
    authors: list[str] = []
    async for event in runner.run_async(
        user_id="invoiceloop", session_id="broadcast",
        new_message=types.Content(
            role="user", parts=[types.Part(text="draft the broadcast schema")]
        ),
    ):
        if event.author not in authors:
            authors.append(event.author)
    session = await service.get_session(
        app_name=APP_NAME, user_id="invoiceloop", session_id="broadcast"
    )
    draft = _validate_draft(session.state.get(STATE_KEY))
    return {"adk": {"executed": True, "runner": "google.adk.runners.Runner",
                     "app_name": APP_NAME, "authors": authors},
            "draft": draft,
            "authority": "advisory only; Python validation and human signature required"}


def run_broadcast_schema_agent(
    report_path: Path | str,
    out_path: Path | str,
    *,
    model: str | None = None,
    credential_workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Run the blind aggregate-only ADK advisor and freeze its output."""
    report_path = Path(report_path)
    out_path = Path(out_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    credential_root = Path(credential_workspace) if credential_workspace else report_path.parent
    resolved = _resolve_model(model, credential_root)
    if isinstance(resolved, str):
        export_credential_for_adk(credential_root)
    try:
        result = asyncio.run(_run(resolved, report))
    except Exception as exc:  # preserve the blocking state; never fake a draft
        result = {
            "adk": {"executed": False, "runner": "google.adk.runners.Runner",
                    "app_name": APP_NAME},
            "status": "blocking",
            "blocking_reason": f"{type(exc).__name__}: {exc}",
            "authority": "no draft was produced",
        }
    result["report_sha256"] = __import__("hashlib").sha256(
        report_path.read_bytes()).hexdigest()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return result
