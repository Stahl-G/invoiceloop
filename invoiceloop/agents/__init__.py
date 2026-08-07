"""Gemini GenAI SDK and ADK agent layer.

The improvement loop is genuinely executed by an ADK `Runner` (see
`improve_loop`), and the model boundary carries record/replay callbacks for
zero-API replay (see `adk_replay`). Models produce advice only: they assign no
IDs, write no ledger, decide no check's scheduling, and promote nothing.

There is one call path, the structured one — `call_gemini_structured`. The
unstructured `call_gemini_model` has been removed: it swallowed JSON parse
errors, and nothing a machine consumes may travel that way.
"""

from __future__ import annotations

from .runtime import (
    AgentCallRecorder,
    GeminiCredentialMissing,
    GeminiSDKMissing,
    ReplayHarness,
    ReplayRecordingMissing,
    call_gemini_structured,
    is_replay_mode,
)

__all__ = [
    "AgentCallRecorder",
    "GeminiCredentialMissing",
    "GeminiSDKMissing",
    "ReplayHarness",
    "ReplayRecordingMissing",
    "call_gemini_structured",
    "is_replay_mode",
]
