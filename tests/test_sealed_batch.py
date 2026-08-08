"""SEALED multi-harness batch: one opening, frozen arms, no adaptive peeking."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from invoiceloop import harness, ocr
from invoiceloop.ingest import default_extraction_schema
from invoiceloop.routing import policy_digest
from invoiceloop.sealed_batch import (
    BatchPlanError,
    frozen_harness,
    load_plan,
    run_batch,
    score_completed_batch,
    verify_completed_batch,
)


DOC = "sealed-doc"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy(harness_id: str, *, release: bool) -> dict:
    return {
        "harness_id": harness_id,
        "version": 1,
        "release_tier1_explicit": release,
        "auto_accept_cohorts": [],
        "qa": {
            "seed": "sealed-batch-test",
            "policy_accepted_tier1_rate": 0.0,
            "cohort_relax_rate": 0.0,
        },
    }


@pytest.fixture
def batch_fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    corpus = tmp_path / "corpus"
    (corpus / "input" / "pdfs").mkdir(parents=True)
    (corpus / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (corpus / "ocr").mkdir()
    _write_json(corpus / "ocr" / f"{DOC}.json", {"pages": [{
        "page_idx": 0,
        "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": value, "confidence": 0.99,
             "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for value, x in (("INV-42", 0.10), ("Total", 0.20),
                             ("100.00", 0.30))
        ]}]}],
    }]})
    (corpus / "raw").mkdir()
    data = {"invoice_number": "INV-42", "total_gross": "100.00"}
    for mode in ("understand", "agentic"):
        _write_json(corpus / "raw" / f"{DOC}.{mode}.json", {
            "doc_id": DOC,
            "document": f"{DOC}.pdf",
            "mode": mode,
            "http_status": 200,
            "body": {"output": {
                "data": data,
                "metadata": {},
                "pages": [{"page": 1, "width": 612, "height": 792}],
            }},
        })
    _write_json(
        corpus / "data" / "docile" / "annotations" / f"{DOC}.json",
        {"field_extractions": [
            {"fieldtype": "document_id", "text": "INV-42"},
            {"fieldtype": "amount_total_gross", "text": "100.00"},
        ]},
    )

    doc_list = {"n": 1, "doc_ids": [DOC]}
    _write_json(repo / "docs" / "doc_list.json", doc_list)
    _write_json(corpus / "doc_list.json", doc_list)
    schema = default_extraction_schema()
    _write_json(repo / "schema.json", schema)

    arms = []
    for arm_id, hid, release, repeat_of in (
        ("B0", "HAR-T1", True, None),
        ("P", "HAR-T2", False, None),
        ("P-REPEAT", "HAR-T2", False, "P"),
    ):
        policy_path = repo / "policies" / f"{arm_id}.json"
        policy = _policy(hid, release=release)
        _write_json(policy_path, policy)
        spec = {
            "arm_id": arm_id,
            "harness_id": hid,
            "role": "repeatability_control" if repeat_of else "test",
            "policy_path": str(policy_path.relative_to(repo)),
            "policy_sha256": _sha(policy_path),
            "policy_digest": policy_digest(policy),
        }
        if repeat_of:
            spec["repeat_of"] = repeat_of
        arms.append(spec)

    schema_path = repo / "schema.json"
    plan = {
        "protocol_version": "sealed3-multiharness-v1",
        "primary_arm_id": "P",
        "qualification_baseline_arm_id": "B0",
        "doc_list_path": "docs/doc_list.json",
        "doc_list_sha256": _sha(repo / "docs" / "doc_list.json"),
        "corpus_doc_list": "doc_list.json",
        "n_docs": 1,
        "schema": {
            "path": "schema.json",
            "sha256": _sha(schema_path),
            "digest": harness.schema_digest(schema),
        },
        "run_options": {
            "include_vision": False,
            "render_crops": False,
            "out_of_calibration": False,
        },
        "arms": arms,
        "comparisons": [
            {"comparison_id": "primary_vs_baseline", "candidate": "P",
             "baseline": "B0", "purpose": "qualification"},
            {"comparison_id": "repeatability", "candidate": "P-REPEAT",
             "baseline": "P", "purpose": "determinism"},
        ],
        "frozen_files": [
            {"path": "schema.json", "sha256": _sha(schema_path)},
        ],
    }
    plan_path = repo / "docs" / "plan.json"
    _write_json(plan_path, plan)

    # The batch owns corpus switching and must leave callers' environment intact.
    monkeypatch.setenv("INVOICELOOP_CORPUS", "sentinel-corpus")
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", "sentinel-legacy")
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield repo, corpus, plan_path
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def test_plan_rejects_policy_byte_drift(batch_fixture):
    repo, _corpus, plan_path = batch_fixture
    plan = json.loads(plan_path.read_text())
    policy_path = repo / plan["arms"][0]["policy_path"]
    policy_path.write_text(policy_path.read_text() + "\n", encoding="utf-8")

    with pytest.raises(BatchPlanError, match="policy_sha256"):
        load_plan(plan_path, repo_root=repo)


def test_frozen_harness_restores_loader_after_exception():
    original = harness.load_active
    active = {
        "harness_id": "HAR-TEST",
        "policy": _policy("HAR-TEST", release=False),
        "policy_digest": "digest",
        "policy_sha256": "bytes",
        "schema": default_extraction_schema(),
        "schema_digest": "schema-digest",
        "schema_sha256": "schema-bytes",
    }

    with pytest.raises(RuntimeError, match="boom"):
        with frozen_harness(active):
            assert harness.load_active(Path("ignored"))["harness_id"] == "HAR-TEST"
            raise RuntimeError("boom")

    assert harness.load_active is original


def test_batch_recomputes_each_arm_on_identical_evidence(batch_fixture, monkeypatch):
    repo, corpus, plan_path = batch_fixture
    monkeypatch.setattr("invoiceloop.sealed_batch._git_head", lambda _repo: "abc123")
    monkeypatch.setattr("invoiceloop.sealed_batch._tracked_dirty", lambda _repo: False)
    output = repo / "batch"

    complete = run_batch(
        plan_path,
        output,
        corpus_root=corpus,
        repo_root=repo,
        expected_head="abc123",
    )

    assert complete["status"] == "complete"
    assert complete["n_docs"] == 1
    assert {a["arm_id"] for a in complete["arms"]} == {"B0", "P", "P-REPEAT"}
    assert len({a["input_fingerprint"] for a in complete["arms"]}) == 1
    assert len({a["execution_fingerprint"] for a in complete["arms"]}) == 2
    assert complete["invariants"] == {
        "same_input_fingerprint": True,
        "same_upstream_artifacts": True,
        "repeat_runs_byte_identical": True,
    }

    b0 = json.loads((output / "B0" / "run" / "run_manifest.json").read_text())
    primary = json.loads((output / "P" / "run" / "run_manifest.json").read_text())
    assert b0["harness_id"] == "HAR-T1"
    assert primary["harness_id"] == "HAR-T2"
    for name in (
        "artifact_registry.json",
        "evidence_span_registry.json",
        "field_claim_graph.json",
        "field_drafts.json",
        "field_ledger.json",
    ):
        assert (output / "B0" / "run" / name).read_bytes() == \
            (output / "P" / "run" / name).read_bytes()

    assert (output / "P" / "run" / "event_log.jsonl").read_bytes() == \
        (output / "P-REPEAT" / "run" / "event_log.jsonl").read_bytes()
    assert not (output / "metrics.json").exists(), \
        "opening batch must not inspect or score intermediate outcomes"


def test_batch_refuses_an_existing_output_directory(batch_fixture, monkeypatch):
    repo, corpus, plan_path = batch_fixture
    monkeypatch.setattr("invoiceloop.sealed_batch._git_head", lambda _repo: "abc123")
    monkeypatch.setattr("invoiceloop.sealed_batch._tracked_dirty", lambda _repo: False)
    output = repo / "batch"
    output.mkdir()

    with pytest.raises(BatchPlanError, match="必须不存在"):
        run_batch(plan_path, output, corpus_root=corpus, repo_root=repo,
                  expected_head="abc123")


def test_completed_batch_verifies_and_scores_only_after_marker(batch_fixture, monkeypatch):
    repo, corpus, plan_path = batch_fixture
    monkeypatch.setattr("invoiceloop.sealed_batch._git_head", lambda _repo: "abc123")
    monkeypatch.setattr("invoiceloop.sealed_batch._tracked_dirty", lambda _repo: False)
    output = repo / "batch"
    run_batch(plan_path, output, corpus_root=corpus, repo_root=repo,
              expected_head="abc123")

    verified = verify_completed_batch(output)
    assert verified["status"] == "complete"
    scored = score_completed_batch(
        output,
        corpus_root=corpus,
        repo_root=Path(__file__).resolve().parent.parent,
    )
    assert scored["primary_arm_id"] == "P"
    assert scored["human_adjudication_accuracy"]["status"] == "NOT_MEASURED"
    assert {a["arm_id"] for a in scored["arms"]} == {"B0", "P", "P-REPEAT"}
    comparison = next(c for c in scored["comparisons"]
                      if c["comparison_id"] == "primary_vs_baseline")
    assert comparison["candidate"] == "P" and comparison["baseline"] == "B0"
    assert scored["qualification"]["H7"]["status"] == "PENDING_BUNDLE_VERIFY"


def test_completed_batch_detects_post_opening_tamper(batch_fixture, monkeypatch):
    repo, corpus, plan_path = batch_fixture
    monkeypatch.setattr("invoiceloop.sealed_batch._git_head", lambda _repo: "abc123")
    monkeypatch.setattr("invoiceloop.sealed_batch._tracked_dirty", lambda _repo: False)
    output = repo / "batch"
    run_batch(plan_path, output, corpus_root=corpus, repo_root=repo,
              expected_head="abc123")
    ledger = output / "P" / "run" / "field_ledger.json"
    ledger.write_text(ledger.read_text() + "\n", encoding="utf-8")

    with pytest.raises(BatchPlanError, match="run 工件哈希漂移"):
        verify_completed_batch(output)


def test_score_refuses_partial_batch(tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    _write_json(batch / "batch_started.json", {"status": "opened"})

    with pytest.raises(BatchPlanError, match="batch_complete"):
        score_completed_batch(batch, corpus_root=tmp_path, repo_root=tmp_path)


def test_committed_sealed3_plan_is_self_consistent():
    repo = Path(__file__).resolve().parent.parent
    plan = load_plan(repo / "docs" / "sealed3_multiharness_plan.json",
                     repo_root=repo)

    assert len(plan["_doc_ids"]) == 100
    assert len(plan["_loaded_arms"]) == 7
    assert plan["primary_arm_id"] == "P-HAR-0004"
    assert plan["qualification_baseline_arm_id"] == "B0-HAR-0001"
