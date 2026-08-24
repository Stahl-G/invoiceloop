"""Dependency-free defaults shared by AI adapters and optional runtimes.

Keeping model names here lets the Workbench resolve and display a backend even
when that backend's optional SDK is not installed.  Callers still pass the
resolved model explicitly, so the displayed name and the API invocation cannot
drift.
"""

from __future__ import annotations


DEFAULT_GEMINI_MODEL = "gemini-3.7-flash"
