"""建议工件溯源:账本每槽能不能说清「当时屏幕上那条建议出自哪份工件」,
以及说不清的时候会不会阻断。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoiceloop import suggest_provenance

SHA_A = "a" * 64
MODEL = "gemini-3.7-flash"


def _map(**over):
    base = {
        "round": "test-round",
        "frozen_at": "2026-08-25T09:00:00+00:00",
        "prompt_digest": "p" * 64,
        "schema_digest": "s" * 64,
        "readers": {"adk-invoice": {
            "model": MODEL, "artifact": "vision/answers6.adk-invoice.tsv",
            "artifact_sha256": SHA_A}},
        "slots": {"doc1|invoice_number": {
            "tag": "adk-invoice", "displayed_value": "INV-1",
            "row_sha256": "r" * 64, "reading_sha256": "d" * 64}},
    }
    base.update(over)
    return base


class TestDerive:
    def test_returns_the_artifact_and_model_for_a_frozen_slot(self):
        assert suggest_provenance.derive(
            _map(), "doc1", "invoice_number", "agree:INV-1") == (SHA_A, MODEL)

    def test_a_slot_the_reviewer_saw_but_the_map_never_froze_blocks(self):
        """走中途补生成的建议会长这样 —— 废臂条款点名的那条,写时就该挡。"""
        with pytest.raises(ValueError, match="冻结表里没有"):
            suggest_provenance.derive(
                _map(), "doc2", "invoice_number", "agree:INV-9")

    def test_a_frozen_slot_the_ledger_claims_nobody_saw_blocks(self):
        """P1 覆盖率最该发现的故障:该展示建议的槽,账本却一个字都没记。
        取自账本的分母会让它消失,所以要在写时挡。"""
        with pytest.raises(ValueError, match="冻结表里有"):
            suggest_provenance.derive(_map(), "doc1", "invoice_number", None)

    def test_a_displayed_value_that_drifted_from_the_frozen_row_blocks(self):
        """TSV 在冻结之后被改过 —— 人看见的与工件里的不是同一条。"""
        with pytest.raises(ValueError, match="与冻结值不符"):
            suggest_provenance.derive(
                _map(), "doc1", "invoice_number", "agree:INV-CHANGED")

    def test_split_and_blind_need_no_value_match(self):
        """读者分歧/全弃权时屏幕上没有可比的值,只要槽在表里就算对得上。"""
        assert suggest_provenance.derive(
            _map(), "doc1", "invoice_number", "split") == (SHA_A, MODEL)

    def test_no_frozen_map_means_no_provenance_and_no_blocking(self):
        """demo 与旧轮没有冻结表,必须照常能裁决。"""
        assert suggest_provenance.derive(None, "doc1", "invoice_number",
                                         "agree:INV-1") is None
        assert suggest_provenance.derive(None, "doc1", "invoice_number",
                                         None) is None


def test_build_map_reads_every_injected_tag(tmp_path):
    """冻结的必须是**人真正看见的那一行** —— 裁决页的建议来自
    answers6.<tag>.tsv,不是 invoice_read.json。inject 会 skip 已有行、
    也会 drop 坏行,两者能漂开。"""
    vision = tmp_path / "vision"
    vision.mkdir()
    (vision / "answers6.adk-invoice.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash role=payee\n"
        "doc1\tseller_name\tACME\tNONE\tgemini-3.7-flash role=payee\n",
        encoding="utf-8")
    slots = suggest_provenance.build_slots(tmp_path)
    assert sorted(slots) == ["doc1|invoice_number", "doc1|seller_name"]
    assert slots["doc1|invoice_number"]["displayed_value"] == "INV-1"
    assert slots["doc1|invoice_number"]["tag"] == "adk-invoice"
    assert len(slots["doc1|invoice_number"]["row_sha256"]) == 64
    assert slots["doc1|invoice_number"]["row_sha256"] != \
        slots["doc1|seller_name"]["row_sha256"]
