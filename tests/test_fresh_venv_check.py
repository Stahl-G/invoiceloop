"""Opt-in judge-path smoke test; the ordinary suite must stay fast."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("INVOICELOOP_RUN_SLOW") != "1",
                    reason="set INVOICELOOP_RUN_SLOW=1 for the clean-clone check")
def test_judge_quickstart_in_a_fresh_clone():
    env = os.environ.copy()
    env.pop("INVOICELOOP_RUN_SLOW", None)  # inner pytest must not recurse
    subprocess.run(["bash", "scripts/fresh_venv_check.sh"], check=True,
                   cwd=Path(__file__).resolve().parents[1], env=env)
