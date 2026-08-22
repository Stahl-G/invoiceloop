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


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
def test_plan_writes_the_list_before_any_call(tmp_path):
    """落盘即预注册:名单、池摘要、盐语境必须在调用之前就在盘上。"""
    ids = heldout.cmd_plan_qual(tmp_path, n=5)
    payload = json.loads((tmp_path / "doc_list.json").read_text(encoding="utf-8"))
    assert payload["doc_ids"] == ids
    assert payload["context"] == heldout.DEFAULT_QUAL_CONTEXT
    assert payload["doc_ids_sha256"] == heldout.doc_ids_line_digest(ids)
    assert payload["pool_sha256"] == heldout.doc_ids_line_digest(heldout.qual_pool())
    assert payload["dual_mode_on_disk_at_freeze"], "盘上快照必须落盘,否则复算时无从判断"
    assert not set(ids) & set(payload["dual_mode_on_disk_at_freeze"])
    assert not list((tmp_path / "raw").glob("*.json")), "plan 阶段不许有任何响应"
