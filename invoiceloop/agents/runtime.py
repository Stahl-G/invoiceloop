"""ADK Agent Runtime & Gemini API Adapter with Zero-API Replay Harness.

Design Principles:
- Single-Writer Discipline: Agents output un-ID'd drafts or suggestions only;
  they NEVER write authoritative ledger records or assign IDs.
- Zero-API Replay: All live API calls persist to `workspace/raw/agents/{call_id}.json`.
  When `INVOICELOOP_REPLAY=1` or `INVOICELOOP_NO_DOTENV=1` or no key is present,
  the runtime loads the recorded response, ensuring 100% offline, deterministic replay.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from invoiceloop import env

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def is_replay_mode(workspace: Path | str | None = None) -> bool:
    """Returns True if offline replay mode is explicitly requested or credentials are missing."""
    if os.environ.get("INVOICELOOP_REPLAY", "") in ("1", "true", "TRUE"):
        return True
    if os.environ.get("INVOICELOOP_NO_DOTENV", "") in ("1", "true", "TRUE"):
        return True
    key = env.credential("gemini", workspace=workspace)
    return key is None


class ReplayHarness:
    """Zero-API offline replay wrapper for ADK agents."""

    def __init__(self, workspace: Path | str | None = None):
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.recorder = AgentCallRecorder(self.workspace)

    def is_active(self) -> bool:
        return is_replay_mode(self.workspace)

    def get_recording(self, call_id: str) -> dict[str, Any] | None:
        return self.recorder.load(call_id)


class AgentCallRecorder:
    """Persists agent API interactions to raw/agents/{call_id}.json."""

    def __init__(self, workspace: Path | str | None = None):
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def record_dir(self) -> Path:
        p = self.workspace / "raw" / "agents"
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
        # Check workspace first
        target = self.record_dir() / f"{call_id}.json"
        if target.exists():
            try:
                return json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        # Fallback to package sample data
        sample_path = (
            Path(__file__).parent.parent
            / "samples"
            / "raw"
            / "agents"
            / f"{call_id}.json"
        )
        if sample_path.exists():
            try:
                return json.loads(sample_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return None


def call_gemini_model(
    prompt: str,
    *,
    system_instruction: str | None = None,
    model: str | None = None,
    workspace: Path | str | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    """Invokes Gemini model or returns stored replay response.

    Returns:
        {"text": str, "json": dict | list | None, "model": str, "replayed": bool}
    """
    model_name = (
        model
        or env.get("gemini_model", workspace=workspace)
        or DEFAULT_GEMINI_MODEL
    )
    if not call_id:
        key_src = f"{model_name}|{system_instruction or ''}|{prompt}"
        call_id = f"gemini_{hashlib.sha256(key_src.encode()).hexdigest()[:12]}"

    recorder = AgentCallRecorder(workspace)

    # 1. Replay check
    if is_replay_mode(workspace):
        recorded = recorder.load(call_id)
        if recorded:
            return {
                "text": recorded.get("output_text", ""),
                "json": recorded.get("output_json"),
                "model": recorded.get("model", model_name),
                "replayed": True,
                "call_id": call_id,
            }
        # If offline replay requested but no recording exists, return zero-API stub
        return {
            "text": "OFFLINE_REPLAY_STUB",
            "json": None,
            "model": model_name,
            "replayed": True,
            "call_id": call_id,
        }

    # 2. Live API Execution
    api_key = env.credential("gemini", workspace=workspace)
    base_url = env.get("gemini_base", workspace=workspace)

    output_text = ""
    parsed_json = None

    # Try official google-genai SDK first
    try:
        from google import genai  # type: ignore

        client = genai.Client(api_key=api_key)
        config = {}
        if system_instruction:
            config["system_instruction"] = system_instruction

        res = client.models.generate_content(
            model=model_name, contents=prompt, config=config if config else None
        )
        output_text = res.text or ""
    except (ImportError, Exception):
        # Fallback to direct HTTP request
        import requests

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        if base_url:
            url = f"{base_url.rstrip('/')}/v1beta/models/{model_name}:generateContent"

        contents = []
        if system_instruction:
            contents.append({"role": "user", "parts": [{"text": f"System Instruction: {system_instruction}"}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        req_body = {"contents": contents}
        headers = {"Content-Type": "application/json"}

        resp = requests.post(
            url,
            params={"key": api_key},
            headers=headers,
            json=req_body,
            timeout=120,
        )
        resp.raise_for_status()
        res_data = resp.json()
        try:
            output_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            output_text = str(res_data)

    # Try parsing JSON block if present
    start_idx = output_text.find("{")
    end_idx = output_text.rfind("}")
    if start_idx >= 0 and end_idx > start_idx:
        try:
            parsed_json = json.loads(output_text[start_idx : end_idx + 1])
        except json.JSONDecodeError:
            pass

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
