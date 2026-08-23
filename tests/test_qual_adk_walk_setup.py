"""ADK 行走 run 身份必须绑定代码与协议字节。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_adk_walk_setup  # noqa: E402


def test_run_identity_changes_with_code_or_protocol(tmp_path):
    protocol = tmp_path / "protocol.md"
    doc_list = tmp_path / "doc-list.json"
    decision = tmp_path / "decision.json"
    inputs = tmp_path / "inputs.json"
    protocol.write_text("v1", encoding="utf-8")
    doc_list.write_text("list-v1", encoding="utf-8")
    decision.write_text("decision-v1", encoding="utf-8")
    inputs.write_text("inputs-v1", encoding="utf-8")
    active = {
        "harness_id": "HAR-0023", "policy_digest": "p",
        "policy_sha256": "ps", "schema_sha256": "ss",
    }
    one = qual_adk_walk_setup.run_identity(
        active, ["a" * 24], round_name="walk-v2", protocol_path=protocol,
        doc_list_path=doc_list, qualification_decision_path=decision,
        qualification_input_manifest_path=inputs,
        selected_corpus_sha256="c1", code_revision="rev-1")
    protocol.write_text("v2", encoding="utf-8")
    two = qual_adk_walk_setup.run_identity(
        active, ["a" * 24], round_name="walk-v2", protocol_path=protocol,
        doc_list_path=doc_list, qualification_decision_path=decision,
        qualification_input_manifest_path=inputs,
        selected_corpus_sha256="c1", code_revision="rev-1")
    three = qual_adk_walk_setup.run_identity(
        active, ["a" * 24], round_name="walk-v2", protocol_path=protocol,
        doc_list_path=doc_list, qualification_decision_path=decision,
        qualification_input_manifest_path=inputs,
        selected_corpus_sha256="c1", code_revision="rev-2")

    assert one["code_revision"] == "rev-1"
    assert one["protocol_sha256"] != two["protocol_sha256"]
    assert two != three


def test_run_identity_changes_with_list_decision_or_corpus(tmp_path):
    protocol = tmp_path / "protocol.md"
    doc_list = tmp_path / "doc-list.json"
    decision = tmp_path / "decision.json"
    inputs = tmp_path / "inputs.json"
    for path in (protocol, doc_list, decision, inputs):
        path.write_text("v1", encoding="utf-8")
    active = {
        "harness_id": "HAR-0023", "policy_digest": "p",
        "policy_sha256": "ps", "schema_sha256": "ss",
    }

    def identity(corpus="c1"):
        return qual_adk_walk_setup.run_identity(
            active, ["a" * 24], round_name="walk-v2",
            protocol_path=protocol, doc_list_path=doc_list,
            qualification_decision_path=decision,
            qualification_input_manifest_path=inputs,
            selected_corpus_sha256=corpus, code_revision="rev")

    baseline = identity()
    doc_list.write_text("v2", encoding="utf-8")
    assert identity() != baseline
    doc_list.write_text("v1", encoding="utf-8")
    decision.write_text("v2", encoding="utf-8")
    assert identity() != baseline
    decision.write_text("v1", encoding="utf-8")
    assert identity("c2") != baseline


def test_corpus_source_verification_blocks_changed_raw(tmp_path, monkeypatch):
    derisk = tmp_path / "derisk"
    raw = tmp_path / "raw"
    doc = "a" * 24
    pdf = derisk / "data/docile/pdfs" / f"{doc}.pdf"
    ocr = derisk / "data/docile/ocr" / f"{doc}.json"
    understand = raw / f"{doc}.understand.json"
    agentic = raw / f"{doc}.agentic.json"
    for path, data in ((pdf, b"pdf"), (ocr, b"ocr"),
                       (understand, b"understand"), (agentic, b"agentic")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = tmp_path / "input_manifest.json"
    manifest.write_text(json.dumps({"docs": [{
        "doc_id": doc, "pdf_sha256": sha(pdf), "ocr_sha256": sha(ocr),
        "raw_sha256": {"understand": sha(understand),
                       "agentic": sha(agentic)},
    }]}), encoding="utf-8")
    monkeypatch.setattr(qual_adk_walk_setup, "DERISK", derisk)

    assert len(qual_adk_walk_setup.verify_corpus_sources(
        {doc: raw}, [doc], manifest)) == 64
    understand.write_bytes(b"changed")
    with pytest.raises(SystemExit, match="冻结 qualification input manifest"):
        qual_adk_walk_setup.verify_corpus_sources(
            {doc: raw}, [doc], manifest)
