"""M4 裁决与交付:append-only、指向真实声明、打包带哈希清单、缺工件阻断。"""

from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from invoiceloop import adjudicate


@pytest.fixture
def run_dir(tmp_path):
    """最小合法 run 目录:必备工件 + 一条冻结声明。"""
    for name in adjudicate.REQUIRED_ARTIFACTS:
        content = {} if name.endswith(".json") else ""
        if name == "field_ledger.json":
            content = {"claims": [{"claim_id": "FC-0001", "doc_id": "doc-a",
                                   "field": "total_gross", "value": "100.00"}],
                       "sha256": "x"}
        path = tmp_path / name
        if name.endswith(".json"):
            path.write_text(json.dumps(content), encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")
    (tmp_path / "adjudication_ledger.jsonl").unlink()  # 从空白开始,测试自己造
    return tmp_path


class TestAppend:
    def test_entries_are_append_only_with_seq(self, run_dir):
        adjudicate.append_adjudication(
            run_dir, claim_id="FC-0001", doc_id="doc-a", field="total_gross",
            decision="accept", rationale="证据齐", adjudicator="y", decided_at="2026-08-02T10:00:00")
        adjudicate.append_adjudication(
            run_dir, claim_id=None, doc_id="doc-a", field="total_vat",
            decision="correct", corrected_value="10.00", rationale="纸面为 10",
            adjudicator="y", decided_at="2026-08-02T10:01:00")
        lines = (run_dir / "adjudication_ledger.jsonl").read_text().splitlines()
        assert [json.loads(x)["seq"] for x in lines] == [1, 2]
        assert json.loads(lines[1])["decision"] == "correct"

    def test_unknown_claim_id_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="不在已冻结账本"):
            adjudicate.append_adjudication(
                run_dir, claim_id="FC-9999", doc_id="doc-a", field="f",
                decision="accept", rationale="r", adjudicator="y", decided_at="t")

    def test_unknown_decision_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="decision"):
            adjudicate.append_adjudication(
                run_dir, claim_id=None, doc_id="doc-a", field="f",
                decision="looks-good", rationale="r", adjudicator="y", decided_at="t")


class TestBundle:
    def test_missing_artifact_blocks_the_bundle(self, run_dir):
        with pytest.raises(FileNotFoundError, match="阻断"):
            adjudicate.build_audit_bundle(run_dir)

    def test_bundle_carries_manifest_with_verifiable_hashes(self, run_dir):
        adjudicate.append_adjudication(
            run_dir, claim_id="FC-0001", doc_id="doc-a", field="total_gross",
            decision="accept", rationale="r", adjudicator="y", decided_at="t")
        (run_dir / "crops").mkdir()
        (run_dir / "crops" / "ES-0001-1.png").write_bytes(b"\x89PNG fake")
        bundle = adjudicate.build_audit_bundle(run_dir)
        with zipfile.ZipFile(bundle) as zf:
            names = set(zf.namelist())
            assert "MANIFEST.sha256" in names
            for required in adjudicate.REQUIRED_ARTIFACTS:
                assert required in names
            assert "crops/ES-0001-1.png" in names
            manifest = zf.read("MANIFEST.sha256").decode()
            digest = hashlib.sha256(b"\x89PNG fake").hexdigest()
            assert f"{digest}  crops/ES-0001-1.png" in manifest
