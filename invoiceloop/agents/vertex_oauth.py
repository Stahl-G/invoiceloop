"""In-memory gcloud OAuth for the Vertex AI (aiplatform) endpoint.

Why this exists: ``generativelanguage.googleapis.com`` is unreachable from
this network, and ``google.auth.default()`` requires an ADC file the operator
never created. A short-lived gcloud access token works against Vertex AI
``global`` — this module activates that route **in memory only**: the token
is captured from ``gcloud auth print-access-token``, wrapped in a
non-refreshing Credentials object, and installed by patching
``google.genai._api_client.load_auth``. Nothing is written to disk; runs
record only the *shape* of the auth (see ``oauth_run_metadata``), matching
the 2026-08-27 ADK-OAuth walk.

This is a demo/verification credential path, not a product feature. The
token lives as long as the process and expires in about an hour; there is no
refresh — a run that outlives it fails loudly (charter rule four), it does
not silently degrade.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

#: 激活标记:runtime.export_credential_for_adk 看到它就不再要求
#: GEMINI_API_KEY —— 凭据已由本模块在进程内装好。
ENV_FLAG = "INVOICELOOP_GCLOUD_OAUTH"


class GcloudUnavailable(RuntimeError):
    """gcloud 不在 PATH 或没有可用凭据 —— 明确失败,不静默降级。"""


def activate(project: str, location: str = "global") -> dict[str, Any]:
    """把 gcloud 短时 OAuth token 装进进程,走 Vertex AI 端点。

    返回的元数据**不含 token 本身**;调用方把它写进 run 目录时也只写
    这个形状(``auth: gcloud short-lived OAuth access token (in-memory)``)。
    """
    try:
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise GcloudUnavailable(
            f"gcloud auth print-access-token 不可用:{exc}") from exc
    if not token:
        raise GcloudUnavailable("gcloud 没有返回 access token —— 先 gcloud auth login")

    import google.oauth2.credentials  # type: ignore
    from google.genai import _api_client  # type: ignore

    creds = google.oauth2.credentials.Credentials(token=token)

    def _load_auth(*, project: str | None):
        return creds, project or _project

    _project = project
    _api_client.load_auth = _load_auth  # noqa: SLF001 — 见模块 docstring
    os.environ[ENV_FLAG] = "1"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_CLOUD_LOCATION"] = location
    return {
        "auth": "gcloud short-lived OAuth access token (in-memory)",
        "vertexai": True,
        "endpoint_family": "aiplatform.googleapis.com",
        "project": project,
        "location": location,
    }
