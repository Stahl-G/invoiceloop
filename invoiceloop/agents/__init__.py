"""ADK Agent Runtime & Multi-Agent Layer for InvoiceLoop.

Provides ADK Agent orchestration, Gemini API integration, and offline
zero-API replay functionality while preserving InvoiceLoop's strict deterministic
governance and single-writer discipline.
"""

from __future__ import annotations

from .runtime import (
    AgentCallRecorder,
    ReplayHarness,
    call_gemini_model,
    is_replay_mode,
)

__all__ = [
    "AgentCallRecorder",
    "ReplayHarness",
    "call_gemini_model",
    "is_replay_mode",
]
