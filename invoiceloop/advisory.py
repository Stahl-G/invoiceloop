"""Resolve the single Workbench AI button to a configured model backend.

The user-facing interface is deliberately singular.  Provider choice is a
deployment setting, not a second workflow:

``INVOICELOOP_AI_PROVIDER=auto|anthropic|gemini``

``anthropic`` means an Anthropic Messages-compatible API, so it can point at
Claude, MiMo, Kimi, or another gateway through the existing
``ANTHROPIC_BASE_URL`` / key / model settings.  ``gemini`` keeps the Google ADK
multi-agent path.  Both are advisory producers and retain separate artifact
files; neither can write the active harness.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import env
from .ai_config import DEFAULT_GEMINI_MODEL


PROVIDER_ENV = "INVOICELOOP_AI_PROVIDER"
MODEL_ENV = "INVOICELOOP_AI_MODEL"

_ANTHROPIC_ALIASES = {
    "anthropic", "anthropic-compatible", "anthropic_messages", "messages",
    "mimo",
}
_GEMINI_ALIASES = {"gemini", "gemini-adk", "google", "google-adk", "adk"}


@dataclass(frozen=True)
class AdvisoryBackend:
    """Safe-to-display backend metadata.  It never contains a credential."""

    provider: str
    protocol: str
    model: str
    artifact: str
    ready: bool
    reason: str | None = None

    @property
    def label(self) -> str:
        if self.provider == "anthropic":
            return "Anthropic-compatible"
        if self.provider == "gemini-adk":
            return "Gemini ADK"
        return self.provider


def _normalise_provider(value: str | None) -> str | None:
    raw = (value or "").strip().lower().replace("_", "-")
    if not raw or raw == "auto":
        return None
    if raw in {v.replace("_", "-") for v in _ANTHROPIC_ALIASES}:
        return "anthropic"
    if raw in {v.replace("_", "-") for v in _GEMINI_ALIASES}:
        return "gemini-adk"
    return raw


def _unified_model(workspace: Path | str | None) -> str | None:
    return env.get(MODEL_ENV, workspace=workspace)


def _anthropic_backend(workspace: Path | str | None) -> AdvisoryBackend:
    model = (
        _unified_model(workspace)
        or env.get("INVOICELOOP_SUGGEST_MODEL", workspace=workspace)
        or env.credential("anthropic_model", workspace=workspace)
        or ""
    ).strip()
    has_credentials = env.credential("anthropic", workspace=workspace) is not None
    ready = has_credentials and bool(model)
    reason = None
    if not has_credentials:
        reason = "missing_credentials"
    elif not model:
        reason = "missing_model"
    return AdvisoryBackend(
        provider="anthropic",
        protocol="anthropic-messages",
        model=model,
        artifact="suggestions.json",
        ready=ready,
        reason=reason,
    )


def _gemini_backend(workspace: Path | str | None) -> AdvisoryBackend:
    model = (
        _unified_model(workspace)
        or env.credential("gemini_model", workspace=workspace)
        or DEFAULT_GEMINI_MODEL
    )
    replay = os.environ.get("INVOICELOOP_REPLAY", "") in ("1", "true", "TRUE")
    ready = replay or env.credential("gemini", workspace=workspace) is not None
    return AdvisoryBackend(
        provider="gemini-adk",
        protocol="google-adk",
        model=model,
        artifact="adk_loop_report.json",
        ready=ready,
        reason=None if ready else "missing_credentials",
    )


def resolve_backend(workspace: Path | str | None = None) -> AdvisoryBackend:
    """Resolve provider/model once so display and invocation cannot drift.

    Auto mode prefers a configured Anthropic-compatible endpoint because that
    path is part of the core install.  Gemini remains selectable explicitly and
    is the fallback when it is the only configured credential.
    """
    requested_raw = env.get(PROVIDER_ENV, workspace=workspace)
    requested = _normalise_provider(requested_raw)
    if requested is None:
        if env.credential("anthropic", workspace=workspace):
            requested = "anthropic"
        elif (env.credential("gemini", workspace=workspace)
              or os.environ.get("INVOICELOOP_REPLAY", "")
              in ("1", "true", "TRUE")):
            requested = "gemini-adk"
        else:
            requested = "anthropic"

    if requested == "anthropic":
        return _anthropic_backend(workspace)
    if requested == "gemini-adk":
        return _gemini_backend(workspace)
    return AdvisoryBackend(
        provider=requested,
        protocol="unknown",
        model=_unified_model(workspace) or "",
        artifact="",
        ready=False,
        reason="unknown_provider",
    )


def run_backend(workspace: Path | str, backend: AdvisoryBackend) -> dict:
    """Run the selected advisory producer; never promote or write active."""
    if not backend.ready:
        raise RuntimeError(
            f"AI advisory backend unavailable: {backend.reason or 'not ready'}"
        )
    if backend.provider == "anthropic":
        from .suggest import suggest

        return suggest(Path(workspace), model=backend.model)
    if backend.provider == "gemini-adk":
        from .agents.improve_loop import run_improve_loop

        return run_improve_loop(Path(workspace), model=backend.model)
    raise RuntimeError(f"unknown AI advisory provider: {backend.provider}")
