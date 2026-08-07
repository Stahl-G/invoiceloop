"""Gemini GenAI SDK Agent Runtime & Zero-API Replay Harness.

Design Principles:
- Single-Writer Discipline: Agents output un-ID'd drafts or suggestions only;
  they NEVER write authoritative ledger records or assign IDs.
- Zero-API Replay: All live API calls persist to `workspace/agent_calls/{call_id}.json`.
  When `INVOICELOOP_REPLAY=1`, the runtime loads the recorded response,
  ensuring 100% offline, deterministic replay.
- Structured Output: All agent calls use Gemini response_schema with Pydantic
  models. Parse failure → raise, never return None.
- Fail Loud: Missing credentials → explicit error, not silent fallback.
  Missing recordings in replay → explicit error, not fabricated data.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from invoiceloop import env

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


class ReplayRecordingMissing(FileNotFoundError):
    """Raised when replay mode is active but no recording exists for a call.

    Constitution Rule 4: a decision that doesn't run is a blocking failure,
    not a bypass. Fabricating a response is worse than failing.
    """

    def __init__(self, call_id: str, expected: Path):
        super().__init__(
            f"Replay recording missing: {call_id} — expected at {expected}. "
            f"Run with live credentials first to create the recording, "
            f"or unset INVOICELOOP_REPLAY."
        )
        self.call_id = call_id
        self.expected = expected


class GeminiSDKMissing(ImportError):
    """Raised when google-genai SDK is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "google-genai is not installed — run: pip install invoiceloop[gemini]"
        )


class GeminiCredentialMissing(RuntimeError):
    """Raised when Gemini API credentials are not configured and replay is off."""

    def __init__(self) -> None:
        super().__init__(
            "GEMINI_API_KEY not configured and INVOICELOOP_REPLAY is not set. "
            "Either set GEMINI_API_KEY / GOOGLE_API_KEY in your .env, "
            "or set INVOICELOOP_REPLAY=1 for offline replay."
        )


def is_replay_mode(workspace: Path | str | None = None) -> bool:
    """Returns True only when INVOICELOOP_REPLAY is explicitly set.

    Missing credentials is a configuration error, NOT a replay mode.
    INVOICELOOP_NO_DOTENV disables .env file loading but does NOT
    imply replay — tests that want replay must set INVOICELOOP_REPLAY=1.
    """
    return os.environ.get("INVOICELOOP_REPLAY", "") in ("1", "true", "TRUE")


class ReplayHarness:
    """Zero-API offline replay wrapper for agent calls."""

    def __init__(self, workspace: Path | str | None = None):
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.recorder = AgentCallRecorder(self.workspace)

    def is_active(self) -> bool:
        return is_replay_mode(self.workspace)

    def get_recording(self, call_id: str) -> dict[str, Any] | None:
        return self.recorder.load(call_id)


class AgentCallRecorder:
    """Persists agent API interactions to agent_calls/{call_id}.json.

    Recordings live in ``workspace/agent_calls/`` — NOT in ``raw/``.
    ``raw/`` is the DWS response archive (320 calls, scoring reads it);
    mixing agent recordings in would change its semantics and break
    any script that counts/validates by ``raw/``.
    """

    def __init__(self, workspace: Path | str | None = None):
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def record_dir(self) -> Path:
        p = self.workspace / "agent_calls"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def record(self, call_id: str, payload: dict[str, Any]) -> Path:
        target = self.record_dir() / f"{call_id}.json"
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    def load(self, call_id: str) -> dict[str, Any] | None:
        target = self.record_dir() / f"{call_id}.json"
        if target.exists():
            try:
                return json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return None


def _resolve_model(model: str | None, workspace: Path | str | None) -> str:
    """Resolve model name: explicit arg > env var > default."""
    return (
        model
        or env.get("gemini_model", workspace=workspace)
        or DEFAULT_GEMINI_MODEL
    )


def _make_call_id(model_name: str, system_instruction: str | None, prompt: str) -> str:
    """Deterministic call_id from content hash."""
    key_src = f"{model_name}|{system_instruction or ''}|{prompt}"
    return f"gemini_{hashlib.sha256(key_src.encode()).hexdigest()[:12]}"


def _get_client(workspace: Path | str | None = None):
    """Create a google-genai Client, failing loudly if SDK or credentials missing."""
    try:
        from google import genai  # type: ignore
    except ImportError:
        raise GeminiSDKMissing() from None

    api_key = env.credential("gemini", workspace=workspace)
    if not api_key:
        raise GeminiCredentialMissing()

    return genai.Client(api_key=api_key)


def call_gemini_structured(
    prompt: str,
    *,
    schema: type[BaseModel],
    system_instruction: str | None = None,
    model: str | None = None,
    workspace: Path | str | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    """Invoke Gemini with structured output (response_schema) or replay.

    Returns:
        {"text": str, "json": dict, "parsed": BaseModel, "model": str,
         "replayed": bool, "call_id": str}

    Raises:
        ReplayRecordingMissing: replay mode + no recording on disk.
        GeminiSDKMissing: google-genai not installed.
        GeminiCredentialMissing: no API key and not in replay mode.
        ValidationError: model output doesn't match schema.
    """
    model_name = _resolve_model(model, workspace)
    if not call_id:
        call_id = _make_call_id(model_name, system_instruction, prompt)

    recorder = AgentCallRecorder(workspace)

    # 1. Replay path
    if is_replay_mode(workspace):
        recorded = recorder.load(call_id)
        if not recorded:
            expected = recorder.record_dir() / f"{call_id}.json"
            raise ReplayRecordingMissing(call_id, expected)
        output_json = recorded.get("output_json", {})
        parsed = schema.model_validate(output_json) if output_json else None
        return {
            "text": recorded.get("output_text", ""),
            "json": output_json,
            "parsed": parsed,
            "model": recorded.get("model", model_name),
            "replayed": True,
            "call_id": call_id,
        }

    # 2. Live API — structured output via google-genai SDK
    client = _get_client(workspace)

    config = {
        "response_mime_type": "application/json",
        "response_schema": schema,
    }
    if system_instruction:
        config["system_instruction"] = system_instruction

    response = client.models.generate_content(
        model=model_name, contents=prompt, config=config,
    )
    output_text = response.text or ""

    # Parse structured output — failure raises, never returns None
    parsed = schema.model_validate_json(output_text)
    output_json = parsed.model_dump()

    # Record for future replay
    record_payload = {
        "call_id": call_id,
        "model": model_name,
        "system_instruction": system_instruction,
        "prompt": prompt,
        "output_text": output_text,
        "output_json": output_json,
        "schema": schema.__name__,
    }
    recorder.record(call_id, record_payload)

    return {
        "text": output_text,
        "json": output_json,
        "parsed": parsed,
        "model": model_name,
        "replayed": False,
        "call_id": call_id,
    }


def call_gemini_model(
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str | None = None,
    workspace: Path | str | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    """Invoke Gemini (unstructured) or replay. For agents that don't need
    Pydantic schema validation (e.g. free-form text analysis).

    Returns:
        {"text": str, "json": dict | None, "model": str, "replayed": bool,
         "call_id": str}

    Raises:
        ReplayRecordingMissing: replay mode + no recording on disk.
        GeminiSDKMissing: google-genai not installed.
        GeminiCredentialMissing: no API key and not in replay mode.
    """
    model_name = _resolve_model(model, workspace)
    if not call_id:
        call_id = _make_call_id(model_name, system_instruction, prompt)

    recorder = AgentCallRecorder(workspace)

    # 1. Replay path
    if is_replay_mode(workspace):
        recorded = recorder.load(call_id)
        if not recorded:
            expected = recorder.record_dir() / f"{call_id}.json"
            raise ReplayRecordingMissing(call_id, expected)
        return {
            "text": recorded.get("output_text", ""),
            "json": recorded.get("output_json"),
            "model": recorded.get("model", model_name),
            "replayed": True,
            "call_id": call_id,
        }

    # 2. Live API — google-genai SDK only, no HTTP fallback
    client = _get_client(workspace)

    config = {}
    if system_instruction:
        config["system_instruction"] = system_instruction

    response = client.models.generate_content(
        model=model_name, contents=prompt, config=config if config else None,
    )
    output_text = response.text or ""

    # Attempt JSON parse if response looks like JSON — but don't use
    # string slicing. If the model was asked for JSON, it should return JSON.
    parsed_json = None
    stripped = output_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed_json = json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Record for future replay
    record_payload = {
        "call_id": call_id,
        "model": model_name,
        "system_instruction": system_instruction,
        "prompt": prompt,
        "output_text": output_text,
        "output_json": parsed_json,
    }
    recorder.record(call_id, record_payload)

    return {
        "text": output_text,
        "json": parsed_json,
        "model": model_name,
        "replayed": False,
        "call_id": call_id,
    }
