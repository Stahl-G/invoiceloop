"""建议工件溯源:账本每槽能不能说清「当时屏幕上那条建议出自哪份工件」,
以及说不清的时候会不会阻断。"""

from __future__ import annotations

import json
import hashlib
import shutil
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


class TestLoadVerifiesTheLiveArtifacts:
    """冻结表说了什么不重要,盘上此刻是什么才重要。"""

    @staticmethod
    def _run(tmp_path: Path, *, anchor: bool = True) -> Path:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import suggest_provenance_freeze

        run_dir = tmp_path / "run-0001"
        (run_dir / "vision").mkdir(parents=True)
        (run_dir / "vision" / "answers6.adk-invoice.tsv").write_text(
            "doc\tfield\tvalue\tprinted_label\tnote\n"
            "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash\n",
            encoding="utf-8")
        (run_dir / "vision" / "invoice_read.json").write_text(json.dumps({
            "advisory": True, "source": "adk_invoice_read",
            "model": MODEL,
            "docs": {"doc1": {"invoice_number": "INV-1", "model": MODEL}},
            "failed": [],
        }), encoding="utf-8")
        suggest_provenance_freeze.freeze(
            run_dir, tag="adk-invoice", round_name="t",
            frozen_at="2026-08-25T09:00:00+00:00")
        if anchor:
            live = run_dir / "vision" / suggest_provenance.FILENAME
            stage = tmp_path / "docs" / "evidence" / "t" / "prewalk"
            stage.mkdir(parents=True)
            frozen = stage / suggest_provenance.FILENAME
            shutil.copyfile(live, frozen)
            (stage / "MANIFEST.sha256").write_text(
                f"{hashlib.sha256(frozen.read_bytes()).hexdigest()}  "
                f"{suggest_provenance.FILENAME}\n", encoding="utf-8")
        return run_dir

    def test_a_clean_run_loads(self, tmp_path):
        run_dir = self._run(tmp_path)
        prov = suggest_provenance.load(run_dir, repo_root=tmp_path)
        assert prov["slots"]["doc1|invoice_number"]["displayed_value"] == "INV-1"

    def test_a_frozen_map_without_a_committed_prewalk_anchor_blocks(self, tmp_path):
        """冻结表存在就说明这是正式走前工件；没有仓库锚点不能降级成开发模式。"""
        run_dir = self._run(tmp_path, anchor=False)
        with pytest.raises(ValueError, match="prewalk.*不存在"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)

    def test_a_manifest_that_omits_the_provenance_map_blocks(self, tmp_path):
        run_dir = self._run(tmp_path, anchor=False)
        stage = tmp_path / "docs" / "evidence" / "t" / "prewalk"
        stage.mkdir(parents=True)
        (stage / "MANIFEST.sha256").write_text(
            f"{'a' * 64}  another.json\n", encoding="utf-8")
        with pytest.raises(ValueError, match="没有绑定"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)

    def test_a_second_reader_injected_after_the_freeze_blocks(self, tmp_path):
        """走中途多注入一个 tag:页面会因读者分歧显示 split,而按 slot 查表
        仍查得到原 tag 的哈希 —— 账本会记下一份指错工件的完整溯源。"""
        run_dir = self._run(tmp_path)
        (run_dir / "vision" / "answers6.other.tsv").write_text(
            "doc\tfield\tvalue\tprinted_label\tnote\n"
            "doc1\tseller_name\tACME\tNONE\tsomething-else\n",
            encoding="utf-8")
        with pytest.raises(ValueError, match="冻结之后变过"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)

    def test_an_edited_display_row_blocks(self, tmp_path):
        run_dir = self._run(tmp_path)
        tsv = run_dir / "vision" / "answers6.adk-invoice.tsv"
        tsv.write_text(tsv.read_text(encoding="utf-8").replace("INV-1", "INV-2"),
                       encoding="utf-8")
        with pytest.raises(ValueError, match="冻结之后变过"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)

    def test_tsv_and_map_edited_together_still_blocks_against_the_repo_copy(
            self, tmp_path):
        """两边一起改就自洽了 —— 仓库里那份走前副本是唯一改不动的锚。"""
        run_dir = self._run(tmp_path)
        live = run_dir / "vision" / suggest_provenance.FILENAME
        stage = tmp_path / "docs" / "evidence" / "t" / "prewalk"
        tsv = run_dir / "vision" / "answers6.adk-invoice.tsv"
        new_tsv = tsv.read_text(encoding="utf-8").replace("INV-1", "INV-2")
        tsv.write_text(new_tsv, encoding="utf-8")
        prov = json.loads(live.read_text(encoding="utf-8"))
        row = [ln for ln in new_tsv.splitlines()[1:] if ln.strip()][0]
        prov["slots"]["doc1|invoice_number"]["displayed_value"] = "INV-2"
        prov["slots"]["doc1|invoice_number"]["row_sha256"] = hashlib.sha256(
            f"adk-invoice\t{row}".encode("utf-8")).hexdigest()
        prov["readers"]["adk-invoice"]["artifact_sha256"] = hashlib.sha256(
            tsv.read_bytes()).hexdigest()
        live.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
        # 两边已被改到自洽,_verify_live 单独跑是过的 —— 必须点名是**走前副本**
        # 挡下的,否则这条测试会在锚失效时靠 live 校验假绿。
        suggest_provenance._verify_live(
            run_dir, json.loads(live.read_text(encoding="utf-8")))
        with pytest.raises(ValueError, match="走前副本不符"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)


def _freeze_module():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import suggest_provenance_freeze

    return suggest_provenance_freeze


def test_freeze_covers_every_row_the_reviewer_can_see(tmp_path):
    """P1 的分母就是这张表。表里漏一行,那一槽的裁决会在写时被 derive 挡下,
    但更早的失败是这里 —— 所以冻结的是 TSV 全量,不是读法全量。"""
    run_dir = tmp_path / "run-0001"
    (run_dir / "vision").mkdir(parents=True)
    (run_dir / "vision" / "answers6.adk-invoice.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash\n"
        "doc2\tseller_name\tBETA\tNONE\tgemini-3.7-flash\n",
        encoding="utf-8")
    (run_dir / "vision" / "invoice_read.json").write_text(json.dumps({
        "advisory": True, "source": "adk_invoice_read", "model": MODEL,
        "docs": {"doc1": {"invoice_number": "INV-1", "model": MODEL},
                 "doc2": {"seller_name": "BETA", "model": MODEL}},
        "failed": [],
    }), encoding="utf-8")
    _freeze_module().freeze(run_dir, tag="adk-invoice", round_name="t",
                            frozen_at="2026-08-25T09:00:00+00:00")
    prov = json.loads((run_dir / "vision" / suggest_provenance.FILENAME)
                      .read_text(encoding="utf-8"))
    assert sorted(prov["slots"]) == ["doc1|invoice_number", "doc2|seller_name"]
    assert prov["readers"]["adk-invoice"]["model"] == MODEL
    assert len(prov["readers"]["adk-invoice"]["artifact_sha256"]) == 64
    assert prov["prompt_digest"] and prov["schema_digest"]
    assert prov["slots"]["doc1|invoice_number"]["reading_sha256"] != \
        prov["slots"]["doc2|seller_name"]["reading_sha256"]


def test_freeze_refuses_to_overwrite(tmp_path):
    """覆盖冻结表 = 账本里已有的哈希对不上了,而前一个 commit 已经背书过旧版。"""
    run_dir = TestLoadVerifiesTheLiveArtifacts._run(tmp_path)
    with pytest.raises(SystemExit, match="拒绝覆盖"):
        _freeze_module().freeze(run_dir, tag="adk-invoice", round_name="t",
                                frozen_at="2026-08-25T10:00:00+00:00")


def test_freeze_blocks_when_a_displayed_row_has_no_reading_behind_it(tmp_path):
    """TSV 里有一行、读法里没有对应文档 —— 人看得见,却指不出它从哪来。"""
    run_dir = tmp_path / "run-0001"
    (run_dir / "vision").mkdir(parents=True)
    (run_dir / "vision" / "answers6.adk-invoice.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash\n"
        "doc9\tamount_due\t$1.00\tNONE\tstray\n",
        encoding="utf-8")
    (run_dir / "vision" / "invoice_read.json").write_text(json.dumps({
        "advisory": True, "source": "adk_invoice_read", "model": MODEL,
        "docs": {"doc1": {"invoice_number": "INV-1", "model": MODEL}},
        "failed": [],
    }), encoding="utf-8")
    with pytest.raises(SystemExit, match="没有对应读法"):
        _freeze_module().freeze(run_dir, tag="adk-invoice", round_name="t",
                                frozen_at="2026-08-25T09:00:00+00:00")
