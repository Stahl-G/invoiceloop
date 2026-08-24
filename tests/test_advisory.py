"""One Workbench AI entry, configurable advisory backends."""

from __future__ import annotations


def test_auto_prefers_configured_anthropic_compatible_backend(
        tmp_path, monkeypatch):
    from invoiceloop.advisory import resolve_backend

    monkeypatch.delenv("INVOICELOOP_AI_PROVIDER", raising=False)
    monkeypatch.delenv("INVOICELOOP_AI_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "mimo-v2.5")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.7-flash")

    backend = resolve_backend(tmp_path)

    assert backend.provider == "anthropic"
    assert backend.protocol == "anthropic-messages"
    assert backend.model == "mimo-v2.5"
    assert backend.artifact == "suggestions.json"
    assert backend.ready is True
    assert backend.reason is None


def test_explicit_gemini_uses_the_same_unified_model_override_for_display(
        tmp_path, monkeypatch):
    from invoiceloop.advisory import resolve_backend

    monkeypatch.setenv("INVOICELOOP_AI_PROVIDER", "gemini")
    monkeypatch.setenv("INVOICELOOP_AI_MODEL", "gemini-custom")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    backend = resolve_backend(tmp_path)

    assert backend.provider == "gemini-adk"
    assert backend.protocol == "google-adk"
    assert backend.model == "gemini-custom"
    assert backend.artifact == "adk_loop_report.json"
    assert backend.ready is True


def test_explicit_anthropic_without_credentials_is_unavailable(
        tmp_path, monkeypatch):
    from invoiceloop.advisory import resolve_backend

    monkeypatch.setenv("INVOICELOOP_AI_PROVIDER", "anthropic")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    backend = resolve_backend(tmp_path)

    assert backend.provider == "anthropic"
    assert backend.ready is False
    assert backend.reason == "missing_credentials"


def test_anthropic_with_credentials_but_without_model_is_unavailable(
        tmp_path, monkeypatch):
    from invoiceloop import env
    from invoiceloop.advisory import resolve_backend

    monkeypatch.setenv("INVOICELOOP_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    for name in ("INVOICELOOP_AI_MODEL", "INVOICELOOP_SUGGEST_MODEL",
                 *env.ALIASES["anthropic_model"]):
        monkeypatch.delenv(name, raising=False)

    backend = resolve_backend(tmp_path)

    assert backend.provider == "anthropic"
    assert backend.model == ""
    assert backend.ready is False
    assert backend.reason == "missing_model"


def test_unknown_provider_is_reported_without_fallback(tmp_path, monkeypatch):
    from invoiceloop.advisory import resolve_backend

    monkeypatch.setenv("INVOICELOOP_AI_PROVIDER", "mystery-cloud")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "would-have-worked")

    backend = resolve_backend(tmp_path)

    assert backend.provider == "mystery-cloud"
    assert backend.ready is False
    assert backend.reason == "unknown_provider"


def test_anthropic_dispatch_forwards_the_exact_displayed_model(
        tmp_path, monkeypatch):
    from invoiceloop.advisory import AdvisoryBackend, run_backend

    seen = {}

    def fake_suggest(workspace, *, model):
        seen.update(workspace=workspace, model=model)
        return {"advisory": True, "model": model}

    monkeypatch.setattr("invoiceloop.suggest.suggest", fake_suggest)
    backend = AdvisoryBackend(
        provider="anthropic",
        protocol="anthropic-messages",
        model="mimo-v2.5",
        artifact="suggestions.json",
        ready=True,
    )

    result = run_backend(tmp_path, backend)

    assert seen == {"workspace": tmp_path, "model": "mimo-v2.5"}
    assert result["model"] == backend.model
