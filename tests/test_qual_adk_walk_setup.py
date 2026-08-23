"""ADK 行走 run 身份必须绑定代码与协议字节。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_adk_walk_setup  # noqa: E402


def test_run_identity_changes_with_code_or_protocol(tmp_path):
    protocol = tmp_path / "protocol.md"
    protocol.write_text("v1", encoding="utf-8")
    active = {
        "harness_id": "HAR-0023", "policy_digest": "p",
        "policy_sha256": "ps", "schema_sha256": "ss",
    }
    one = qual_adk_walk_setup.run_identity(
        active, ["a" * 24], protocol_path=protocol, code_revision="rev-1")
    protocol.write_text("v2", encoding="utf-8")
    two = qual_adk_walk_setup.run_identity(
        active, ["a" * 24], protocol_path=protocol, code_revision="rev-1")
    three = qual_adk_walk_setup.run_identity(
        active, ["a" * 24], protocol_path=protocol, code_revision="rev-2")

    assert one["code_revision"] == "rev-1"
    assert one["protocol_sha256"] != two["protocol_sha256"]
    assert two != three
