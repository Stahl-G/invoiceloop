"""资格轮抽样测试:池里不许有任何被碰过的文档,名单必须第三方可复算。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from invoiceloop import heldout
from invoiceloop.ocr import corpus_available, derisk_root

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestQualPool:
    def test_pool_excludes_every_document_that_was_ever_touched(self):
        """池里混进一份跑过的文档 = 「未曝光」这个头条主张直接是假的。

        三个曝光集**都必须是冻结的**:活查 discover_dual_mode() 在 Task 4
        之后必然自打嘴巴 —— 那 200 份提取完就有了双模式响应,却仍在池里。
        冻结时的盘上快照由 cmd_plan_qual 写进 doc_list.json。
        """
        pool = set(heldout.qual_pool())
        manifest = {
            e["doc_id"] for e in json.loads(
                (REPO / "docs" / "development_exposure_manifest.json")
                .read_text(encoding="utf-8"))["doc_ids"]}
        sealed4 = set(json.loads(
            (REPO / "docs" / "sealed4_doc_list.json")
            .read_text(encoding="utf-8"))["doc_ids"])
        assert not pool & manifest, "开发期曝光清单里的文档进了资格池"
        assert not pool & sealed4, "SEALED-4 已抽的 100 份进了资格池"

    def test_v1_pool_and_list_remain_byte_for_byte_recomputable(self):
        """新增 v2 排除项不能回头改变 v1 当时的池或名单。"""
        pool = heldout.qual_pool(context="qual-narrow-v1")
        ids = heldout.qual_list(200, context="qual-narrow-v1")
        assert len(pool) == 4831
        assert heldout.doc_ids_line_digest(pool) == (
            "c5232063e6cd03c0979bd8adcc2cd8dfe73b585fe5ca107285221eed03303ce5")
        assert heldout.doc_ids_line_digest(ids) == (
            "22c566997043c5c8185431cb813f84d3eef5a95ca1b2b61bf6182a381fbdb052")

    def test_v2_pool_excludes_the_spent_v1_qualification_list(self):
        v1 = set(json.loads(
            (REPO / "docs" / "qual_narrow_doc_list.json")
            .read_text(encoding="utf-8"))["doc_ids"])
        v1_pool = set(heldout.qual_pool(context="qual-narrow-v1"))
        v2_pool = set(heldout.qual_pool(context="qual-narrow-v2"))
        assert v1 <= v1_pool, "v1 自己的历史池必须还能包含 v1 名单"
        assert not v1 & v2_pool, "污染/已曝光的 v1 名单不得进入 v2 池"
        assert len(v1_pool) - len(v2_pool) == len(v1)
        assert len(v2_pool) == 4631
        assert heldout.doc_ids_line_digest(v2_pool) == (
            "e7265a79aacf57fd4dd9af3d709c7b5963ab71d36a3d17ae762af202ab797fb8")

    def test_frozen_v2_list_recomputes_and_stays_disjoint(self):
        path = (REPO / "docs" / "evidence" / "qual-narrow-v2-2026-08-23"
                / "plan" / "doc_list.json")
        spec = json.loads(path.read_text(encoding="utf-8"))
        ids = heldout.qual_list(200, context="qual-narrow-v2")
        v1 = set(heldout.qual_list(200, context="qual-narrow-v1"))
        assert spec["context"] == "qual-narrow-v2"
        assert spec["doc_ids"] == ids
        assert spec["doc_ids_sha256"] == heldout.doc_ids_line_digest(ids)
        assert not set(ids) & v1

    def test_frozen_list_never_touched_anything_on_disk_at_freeze_time(self):
        """冻结那一刻盘上有双模式响应的文档,一份都不在名单里。

        名单落盘后这条永远为真(两边都是冻结值);Task 3 另有一条**活查**
        的闸,那才是提取前的实时把关。名单还没落盘就跳过。
        """
        path = REPO / "docs" / "qual_narrow_doc_list.json"
        if not path.is_file():
            pytest.skip("名单尚未冻结(Task 3 之前)")
        spec = json.loads(path.read_text(encoding="utf-8"))
        touched = set(spec["dual_mode_on_disk_at_freeze"])
        assert touched, "冻结时的盘上快照不能是空的 —— 空集让这条测试无话可说"
        assert not set(spec["doc_ids"]) & touched

    def test_pool_members_all_have_pdf_and_word_ocr(self):
        """缺 OCR 的文档会被 doctouch_arms.assemble 静默剔掉 —— 报告仍写
        n=200,实际测了更少。所以进池就必须装得起来。"""
        root = derisk_root() / "data" / "docile"
        for doc in heldout.qual_list(20):
            assert (root / "pdfs" / f"{doc}.pdf").is_file(), doc
            assert (root / "ocr" / f"{doc}.json").is_file(), doc


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestQualList:
    def test_list_is_recomputable_by_a_third_party(self):
        """预注册的意义全在这条:拿到池和盐,任何人都能算出同一份 200。"""
        ids = heldout.qual_list(200)
        salt = heldout.QUAL_CONTEXTS[heldout.DEFAULT_QUAL_CONTEXT]
        expected = sorted(sorted(
            heldout.qual_pool(),
            key=lambda d: hashlib.sha256(
                f"{salt}|{d}".encode("utf-8")).hexdigest())[:200])
        assert ids == expected
        assert len(set(ids)) == 200

    def test_unknown_context_is_refused(self):
        """盐是协议的一部分。打错语境应当报错,不该悄悄用默认盐抽一份别的。"""
        with pytest.raises(ValueError, match="未知资格语境"):
            heldout.qual_list(10, context="qual-narrow-v99")

    def test_v2_list_is_deterministic_and_disjoint_from_v1(self):
        one = heldout.qual_list(200, context="qual-narrow-v2")
        two = heldout.qual_list(200, context="qual-narrow-v2")
        v1 = set(heldout.qual_list(200, context="qual-narrow-v1"))
        assert one == two
        assert len(one) == len(set(one)) == 200
        assert not set(one) & v1
        assert heldout.doc_ids_line_digest(one) == (
            "50be4e8f4554055c8e0a83cc19ecc20b31319728879dbf6f663218d8b82df853")


def test_exposure_registry_refuses_a_drifted_list(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    spent = docs / "spent.json"
    spent.write_text(json.dumps({"doc_ids": ["a" * 24]}), encoding="utf-8")
    registry = docs / "qualification_exposure_registry.json"
    registry.write_text(json.dumps({
        "registry_version": "qualification-exposure-v1",
        "lists": [{
            "id": "spent",
            "path": "docs/spent.json",
            "list_sha256": "0" * 64,
            "doc_ids_sha256": heldout.doc_ids_line_digest(["a" * 24]),
            "exclude_from_contexts": ["qual-narrow-v2"],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(heldout, "QUAL_REPO_ROOT", tmp_path)
    monkeypatch.setattr(heldout, "QUAL_EXPOSURE_REGISTRY", registry)
    heldout.qual_exposure_doc_ids.cache_clear()
    try:
        with pytest.raises(ValueError, match="list_sha256 漂移"):
            heldout.qual_exposure_doc_ids("qual-narrow-v2")
    finally:
        heldout.qual_exposure_doc_ids.cache_clear()


def test_every_exposure_registry_list_is_hash_bound():
    registry = json.loads(
        (REPO / "docs" / "qualification_exposure_registry.json")
        .read_text(encoding="utf-8"))
    assert registry["lists"]
    for entry in registry["lists"]:
        path = REPO / entry["path"]
        assert path.is_file(), entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["list_sha256"]
        ids = json.loads(path.read_text(encoding="utf-8"))["doc_ids"]
        assert heldout.doc_ids_line_digest(ids) == entry["doc_ids_sha256"]


@pytest.fixture
def pin_disk(monkeypatch):
    """把「盘上已有双模式响应」钉成固定集合。

    活查 doctouch_arms.discover_dual_mode 会随提取进度变:本轮 200 份一开跑,
    重新 plan 同一把盐就会撞上自己刚存下的响应。那是**生产路径该有的行为**
    (见下面的 leak guard 用例),但让单测跟着盘面漂就只是环境噪声。
    """
    import doctouch_arms

    def _pin(docs):
        monkeypatch.setattr(doctouch_arms, "discover_dual_mode",
                            lambda: {d: Path("/raw") for d in docs})
    return _pin


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
def test_plan_writes_the_list_before_any_call(tmp_path, pin_disk):
    """落盘即预注册:名单、池摘要、盐语境必须在调用之前就在盘上。"""
    pin_disk(["z" * 24])
    ids = heldout.cmd_plan_qual(tmp_path, n=5)
    payload = json.loads((tmp_path / "doc_list.json").read_text(encoding="utf-8"))
    assert payload["doc_ids"] == ids
    assert payload["context"] == heldout.DEFAULT_QUAL_CONTEXT
    assert payload["doc_ids_sha256"] == heldout.doc_ids_line_digest(ids)
    assert payload["pool_sha256"] == heldout.doc_ids_line_digest(heldout.qual_pool())
    assert payload["dual_mode_on_disk_at_freeze"], "盘上快照必须落盘,否则复算时无从判断"
    assert not set(ids) & set(payload["dual_mode_on_disk_at_freeze"])
    assert not list((tmp_path / "raw").glob("*.json")), "plan 阶段不许有任何响应"


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
def test_v2_plan_records_its_context_specific_exclusions(tmp_path, pin_disk):
    pin_disk(["z" * 24])
    ids = heldout.cmd_plan_qual(
        tmp_path, n=5, context="qual-narrow-v2")
    payload = json.loads((tmp_path / "doc_list.json").read_text(encoding="utf-8"))
    assert payload["doc_ids"] == ids
    assert payload["context"] == "qual-narrow-v2"
    assert payload["pool_sha256"] == heldout.doc_ids_line_digest(
        heldout.qual_pool(context="qual-narrow-v2"))
    assert payload["exclusion_lists"] == [
        "docs/qual_narrow_doc_list.json",
        "docs/sealed4_doc_list.json",
    ]


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
def test_plan_refuses_a_list_whose_documents_were_already_run(tmp_path, pin_disk):
    """提取前的实时闸:抽中的文档若盘上已有响应,「未曝光」当场不成立。

    这是名单落盘**之前**的最后一道检查,与冻结快照那条测试互补:那条查的是
    「冻结时对不对」,这条查的是「现在还对不对」。
    """
    sampled = heldout.qual_list(5)
    pin_disk([sampled[1]])
    with pytest.raises(RuntimeError, match="「未曝光」不成立"):
        heldout.cmd_plan_qual(tmp_path, n=5)
    assert not (tmp_path / "doc_list.json").exists(), \
        "闸没过就不许留下名单 —— 半份预注册会被当成完整的"
