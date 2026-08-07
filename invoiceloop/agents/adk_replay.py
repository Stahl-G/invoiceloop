"""Record/replay at the ADK model boundary — zero-API replay, with each recording
bound to the identity of its request.

Hangs off an `LlmAgent`'s `before_model_callback` / `after_model_callback`. ADK
documents that returning an `LlmResponse` from the before-callback skips the
model call, so in replay mode **not one request leaves the process**, while the
Runner, the SequentialAgent, state passing and the event stream all execute
normally.

A recording is keyed by the digest of the **entire request**, not by a name the
call site made up:

    sha256(model ‖ system_instruction ‖ contents ‖ response schema ‖ mime)

The previous version used hand-written call ids like `critic_{field}` and
`party_{doc_id}`, which carried neither the model nor the prompt nor the schema —
so after changing a model or a prompt, the old recording would still be returned
as this call's answer. This was not a theoretical risk: `test_agents_party.py` and
`test_agents_vision.py` held recordings that said `gemini-2.5-flash` while the
runtime default was already `gemini-3.6-flash`, and both tests passed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .runtime import AgentCallRecorder, ReplayRecordingMissing, is_replay_mode


def _schema_fingerprint(schema: Any) -> Any:
    if schema is None:
        return None
    if hasattr(schema, "model_json_schema"):          # Pydantic 类
        return schema.model_json_schema()
    if hasattr(schema, "model_dump"):                 # genai types.Schema
        return schema.model_dump(mode="json", exclude_none=True)
    return str(schema)


def request_identity(llm_request) -> dict[str, Any]:
    """请求身份的全部分量 —— 摘要之前先看得见,便于诊断不匹配。"""
    config = llm_request.config
    return {
        "model": llm_request.model,
        "system_instruction": str(
            getattr(config, "system_instruction", "") or ""
        ),
        "contents": [
            c.model_dump(mode="json", exclude_none=True)
            for c in (llm_request.contents or [])
        ],
        "response_mime_type": getattr(config, "response_mime_type", None),
        "response_schema": _schema_fingerprint(
            getattr(config, "response_schema", None)
        ),
    }


def request_digest(llm_request) -> str:
    blob = json.dumps(request_identity(llm_request), sort_keys=True,
                      ensure_ascii=False, default=str)
    return f"adk_{hashlib.sha256(blob.encode()).hexdigest()[:16]}"


def replay_callbacks(workspace: Path | str):
    """→ (before_model_callback, after_model_callback)。

    重放模式:命中录音就返回它,**没命中就抛** —— 宪章四,缺凭据不许伪造。
    实时模式:放行,并在 after 里按同一摘要落盘。
    """
    recorder = AgentCallRecorder(workspace)
    pending: dict[tuple[str, str], dict[str, Any]] = {}

    def _slot(ctx) -> tuple[str, str]:
        return (str(getattr(ctx, "invocation_id", "")), str(ctx.agent_name))

    def before_model(callback_context, llm_request):
        digest = request_digest(llm_request)
        pending[_slot(callback_context)] = {
            "digest": digest,
            "identity": request_identity(llm_request),
        }
        if not is_replay_mode(workspace):
            return None
        recorded = recorder.load(digest)
        if not recorded:
            raise ReplayRecordingMissing(
                digest, recorder.record_dir() / f"{digest}.json"
            )
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=recorded.get("output_text", ""))],
            )
        )

    def after_model(callback_context, llm_response):
        if is_replay_mode(workspace):
            return None
        slot = pending.pop(_slot(callback_context), None)
        if slot is None:                # 没有 before 就没有身份,不猜
            return None
        text = "".join(
            p.text or ""
            for p in ((llm_response.content and llm_response.content.parts) or [])
        )
        recorder.record(slot["digest"], {
            "call_id": slot["digest"],
            "agent": callback_context.agent_name,
            "identity": slot["identity"],
            "model": slot["identity"]["model"],
            "output_text": text,
        })
        return None

    return before_model, after_model
