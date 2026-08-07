"""Gemini GenAI SDK & ADK Agent Layer for InvoiceLoop.

Provides Google ADK workflow orchestration, Gemini structured output,
and offline zero-API replay while preserving InvoiceLoop's strict
deterministic governance and single-writer discipline.
"""

from __future__ import annotations

from .runtime import (
    AgentCallRecorder,
    GeminiCredentialMissing,
    GeminiSDKMissing,
    ReplayHarness,
    ReplayRecordingMissing,
    call_gemini_model,
    call_gemini_structured,
    is_replay_mode,
)

__all__ = [
    "AgentCallRecorder",
    "GeminiCredentialMissing",
    "GeminiSDKMissing",
    "ReplayHarness",
    "ReplayRecordingMissing",
    "call_gemini_model",
    "call_gemini_structured",
    "is_replay_mode",
]
