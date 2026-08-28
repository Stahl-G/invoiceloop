"""Environment self-check: the first thing to run on a clean clone.

A missing hard dependency of the product path (workspace: ingest → run →
adjudicate → bundle) exits 1. The research path (heldout, calibration recompute,
`run --out` reading stored dws-derisk evidence) is reported but never blocks —
a default install does not require the sibling calibration archive.
"""

from __future__ import annotations

import json
import shutil
import sys


def cmd_doctor() -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, required: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "required": required, "detail": detail})

    check("python>=3.10", sys.version_info >= (3, 10), True, sys.version.split()[0])
    try:
        import requests

        check("requests", True, True, requests.__version__)
    except ImportError:
        check("requests", False, True, "missing: pip install requests (or pip install .)")
    for tool, why in (
        ("pdftotext", "text-layer independent OCR and bbox coordinates (brew install poppler)"),
        ("pdftoppm", "evidence crops and full-page rendering (same)"),
        ("pdfinfo", "page dimensions for crop-coordinate math (same)"),
    ):
        check(f"poppler:{tool}", shutil.which(tool) is not None, True, why)
    check("tesseract", shutil.which("tesseract") is not None, False,
          "fallback for scanned PDFs (no text layer); without it, scans block per "
          "charter rule four instead of silently passing")

    # 凭证:只报有没有与来自哪里,**永不回显值**。全缺不阻断 ——
    # 产品路径的 demo 零 API,评委不需要任何 key 就能跑通
    from .env import status as env_status

    env_info = env_status()
    creds = env_info["credentials"]
    check("credentials:.env", env_info["env_file"] is not None, False,
          f"{env_info['env_file'] or 'no project .env found (cp .env.example .env)'}"
          + (f" mode={env_info['env_file_mode']}"
             if env_info["env_file_mode"] else ""))
    if env_info["env_file_mode"] and env_info["env_file_mode"] not in ("0o600", "0o400"):
        check("credentials:.env permissions", False, False,
              f"{env_info['env_file_mode']} — chmod 600 recommended (non-blocking)")
    for purpose, why in (
        ("dws", "DWS extraction (ingest --do-extract / workbench extraction)"),
        ("nutrient", "countersigning for invoiceloop seal (falls back to DWS_API_KEY)"),
        ("anthropic", "vision reading and the advisory suggest layer"),
        ("gemini", "Gemini API and the ADK agent layer"),
    ):
        source = creds.get(purpose)
        check(f"credentials:{purpose}", source is not None, False,
              f"{why} — " + (f"configured (source: {source})" if source else "not configured"))

    try:
        import google.adk  # noqa: F401
        import google.genai  # noqa: F401
        check("optional:google-adk", True, False,
              f"advisory layer installed in {sys.executable}")
    except ImportError:
        check("optional:google-adk", False, False,
              f"advisory layer not installed in {sys.executable} — the workbench "
              f"improve page will not offer a clickable Gemini button (does not "
              f"block the product path)")

    from .ocr import corpus_available, derisk_root

    check("research:dws-derisk stored evidence", corpus_available(), False,
          f"{derisk_root()} — needed by heldout/calibration recompute/run --out; "
          f"not needed by the product path (workspace)")

    report = {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1
