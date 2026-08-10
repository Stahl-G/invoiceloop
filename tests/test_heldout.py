"""留出集驱动的测试:名单可复现、换 key/熔断/续跑逻辑正确(不调 API)。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from invoiceloop import heldout

from invoiceloop.ocr import corpus_available


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestDocList:
    def test_deterministic_and_preregistered_shape(self):
        ids = heldout.heldout_list()
        assert len(ids) == 100
        assert ids == heldout.heldout_list(), "名单必须可复现"
        assert len(set(ids)) == 100, "等距抽样不得出重复"
        assert not set(ids) & heldout.calibration_ids(), "留出集与校准 160 必须互斥"

    def test_pool_members_meet_the_worth_a_call_bar(self):
        pool = set(heldout.heldout_pool())
        assert len(pool) > 1000
        for doc_id in heldout.heldout_list()[:5]:
            assert doc_id in pool


class FakeExtract:
    """模拟 DWS 客户端:按脚本返回状态码,记录每次调用时的 key。"""

    def __init__(self, script, cost=25.0):
        self.script = script  # list of http_status,按出队返回
        self.cost = cost
        self.calls: list[dict] = []

    def __call__(self, document, schema, *, doc_id, mode, **kw):
        status = self.script.pop(0)
        self.calls.append({"doc_id": doc_id, "mode": mode,
                           "key": os.environ.get("DWS_API_KEY"), "status": status})
        body = {"usage": {"data_extraction_credits": {"cost": self.cost}}} if status == 200 else {}
        return {"doc_id": doc_id, "mode": mode, "http_status": status, "body": body}


def _workspace(tmp_path, docs=("d1", "d2")):
    ws = tmp_path / "ws"
    (ws / "raw").mkdir(parents=True)
    (ws / "doc_list.json").write_text(json.dumps({"doc_ids": list(docs)}))
    return ws


@pytest.fixture
def fake_client(monkeypatch):
    def install(script, cost=25.0):
        fake_mod = type("FakeExtractModule", (), {})()
        fake_mod.extract = FakeExtract(script, cost)
        fake_mod.RAW_DIR = None
        monkeypatch.setattr(heldout, "_derisk_imports",
                            lambda: (None, type("S", (), {"extraction_schema": lambda self: {}})(), fake_mod))
        monkeypatch.setattr(heldout, "derisk_root", lambda: Path("/nonexistent"))
        return fake_mod.extract
    return install


class TestExtractDriver:
    def test_rotates_key_on_credit_exhaustion(self, fake_client, tmp_path, monkeypatch):
        monkeypatch.setenv("DWS_API_KEYS", "k1,k2,k3")
        ws = _workspace(tmp_path, docs=("d1",))
        fake = fake_client([402, 200, 200])  # understand 402→换key→200;agentic 200
        summary = heldout.cmd_extract(ws, budget=6000)
        assert summary["done"] == 2 and summary["keys_used"] == 2
        assert fake.calls[0]["key"] == "k1" and fake.calls[0]["status"] == 402
        assert all(c["key"] == "k2" for c in fake.calls[1:])

    def test_budget_circuit_breaker_stops_midway(self, fake_client, tmp_path, monkeypatch):
        monkeypatch.setenv("DWS_API_KEYS", "k1")
        ws = _workspace(tmp_path, docs=("d1", "d2"))
        fake_client([200, 200, 200, 200], cost=3500.0)
        summary = heldout.cmd_extract(ws, budget=6000)
        assert summary["done"] == 2, "第二次成功后 spent=7000>6000 应熔断"
        assert summary["spent_estimate"] == 7000.0

    def test_restart_skips_completed_records(self, fake_client, tmp_path, monkeypatch):
        monkeypatch.setenv("DWS_API_KEYS", "k1")
        ws = _workspace(tmp_path, docs=("d1", "d2"))
        (ws / "raw" / "d1.understand.json").write_text(json.dumps(
            {"doc_id": "d1", "mode": "understand", "http_status": 200, "body": {}}))
        fake = fake_client([200, 200, 200])
        summary = heldout.cmd_extract(ws, budget=6000)
        assert summary["skipped"] == 1 and summary["done"] == 3
        assert not any(c["doc_id"] == "d1" and c["mode"] == "understand" for c in fake.calls)

    def test_corrupt_record_is_rerun_not_skipped(self, fake_client, tmp_path, monkeypatch):
        monkeypatch.setenv("DWS_API_KEYS", "k1")
        ws = _workspace(tmp_path, docs=("d1",))
        (ws / "raw" / "d1.understand.json").write_text("{broken")
        fake_client([200, 200])
        summary = heldout.cmd_extract(ws, budget=6000)
        assert summary["done"] == 2 and summary["skipped"] == 0

    def test_failure_is_recorded_not_fatal(self, fake_client, tmp_path, monkeypatch):
        monkeypatch.setenv("DWS_API_KEYS", "k1")
        ws = _workspace(tmp_path, docs=("d1", "d2"))
        fake_client([500, 200, 200, 200])  # d1.understand 500(无更多 key 可换)
        summary = heldout.cmd_extract(ws, budget=6000)
        assert summary["failed"] == 1 and summary["done"] == 3
        assert summary["failures"][0]["http_status"] == 500

    def test_adaptive_workspace_refused(self, tmp_path, monkeypatch):
        """密封/留出抽取不得在 adaptive workspace 上跑(会拆掉双模式门)。"""
        monkeypatch.setenv("DWS_API_KEYS", "k1")
        ws = _workspace(tmp_path, docs=("d1",))
        (ws / "adaptive.json").write_text('{"adaptive": true}\n')
        with pytest.raises(RuntimeError, match="adaptive.json"):
            heldout.cmd_extract(ws, budget=6000)


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestSealedList:
    def test_deterministic_given_seed(self):
        a = heldout.sealed_list("ab" * 32)
        b = heldout.sealed_list("ab" * 32)
        assert a == b and len(a) == 100 and len(set(a)) == 100
        c = heldout.sealed_list("cd" * 32)
        assert c != a, "换种子必须换名单"

    def test_excludes_full_exposure_manifest(self):
        import json as _json
        from pathlib import Path as _P

        manifest = _json.loads((_P("docs") / "development_exposure_manifest.json")
                               .read_text())
        exposed = {e["doc_id"] for e in manifest["doc_ids"]}
        ids = heldout.sealed_list("ab" * 32)
        assert not set(ids) & exposed, \
            "封箱名单与暴露清单必须互斥(校准/旧留出/demo 样本全部排除)"
        assert not set(ids) & set(heldout.heldout_list()), \
            "与旧留出 100 互斥(暴露清单的子集,双保险)"

    def test_pool_shrinks_by_exposure(self):
        """合格池 = 留出池 − 暴露清单在留出池内的部分,逐份对上。

        原先这里写死「−300」,于是每加一批封箱都要来改一次数字,而改数字
        的人正是刚刚扩大暴露清单的那个人 —— 那样这条测试只会确认自己的
        改动。改成从清单本身导出:它钉的是「排除是完整的」,不是「排除了
        几份」。
        """
        import json as _json
        from pathlib import Path as _P

        manifest = _json.loads(
            (_P(__file__).resolve().parent.parent / "docs"
             / "development_exposure_manifest.json").read_text(encoding="utf-8"))
        exposed = {e["doc_id"] for e in manifest["doc_ids"]}
        pool = set(heldout.heldout_pool())
        assert set(heldout.sealed_pool()) == pool - exposed, \
            "合格池必须恰好是留出池减去全部已暴露文档"
        assert exposed & pool, "暴露清单与留出池无交集 —— 清单大概接错了"

    def test_sealed1_recompute_context(self):
        """SEALED-1 名单复算必须用 sealed1-v1 语境,不得被 sealed2 默认污染。"""
        import json as _json
        from pathlib import Path as _P

        sealed1 = _json.loads((_P("docs") / "sealed1_doc_list.json").read_text())
        # 临时:若暴露已含 sealed1,池变小,但同种子+同语境仍应复算原名单
        # —— 仅当 sealed1 尚未进暴露池时池够大;进池后 sealed_list 会因池
        # 变化而无法逐份复算。协议要求:复算用冻结时的池。此处只钉语境串。
        a = heldout.sealed_list(sealed1["seed"], context="sealed1-v1")
        b = heldout.sealed_list(sealed1["seed"], context="sealed1-v1")
        assert a == b
        c = heldout.sealed_list(sealed1["seed"], context="sealed2-v1")
        assert c != a, "换语境必须换名单"


def test_line_digest_is_order_independent_line_join():
    """A1 复算锚口径:排序后逐行连接的 sha256(与 scope.doc_ids_digest 的
    JSON canonical 是两回事,别混用)。"""
    import hashlib as _h

    expect = _h.sha256("a\nb".encode("utf-8")).hexdigest()
    assert heldout.doc_ids_line_digest(["b", "a"]) == expect
    assert heldout.doc_ids_line_digest(["a", "b"]) == expect


def test_unknown_scope_rejected_before_touching_corpus():
    with pytest.raises(ValueError, match="未知封箱范围"):
        heldout.sealed_list("ab" * 32, context="sealed4-v2", scope="golf")
    with pytest.raises(ValueError, match="未知封箱范围"):
        heldout.sealed_scope_pool("golf")


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestSealedBroadcastScope:
    """SEALED-4 增补件 A1:迁移进包的分类器重算 4,931 池,必须与冻结
    的子池计数和 digest 逐字节一致 —— 任一不符 = 名单不可复算。"""

    def test_subpool_matches_frozen_amendment(self):
        strong, weak = heldout.sealed_scope_pool("broadcast-pilot-v1")
        union = sorted(strong + weak)
        assert (len(strong), len(weak), len(union)) == (2725, 1471, 4196)
        assert heldout.doc_ids_line_digest(strong) == (
            "d1e79686fe67f389cc08f9deba200aaa21f8c661445d5de738af65bb1f926489")
        assert heldout.doc_ids_line_digest(weak) == (
            "72066c8be5e082abd31093a1ca8c60cffdbbf39e449cd575498f440917bbcb16")
        assert heldout.doc_ids_line_digest(union) == (
            "78066c41a4bea9fa5f5102ccd5977ae2993297ba5fbb055b04cee810e0ae438c")

    def test_scope_sampling_deterministic_within_subpool(self):
        strong, weak = heldout.sealed_scope_pool("broadcast-pilot-v1")
        union = set(strong) | set(weak)
        a = heldout.sealed_list("ef" * 32, context="sealed4-v2",
                                scope="broadcast-pilot-v1")
        b = heldout.sealed_list("ef" * 32, context="sealed4-v2",
                                scope="broadcast-pilot-v1")
        assert a == b and len(a) == 100 and len(set(a)) == 100
        assert set(a) <= union, "名单必须落在广播 union 子池内"
        c = heldout.sealed_list("ef" * 32, context="sealed4-v1",
                                scope="broadcast-pilot-v1")
        assert c != a, "换语境必须换名单"

    def test_plan_sealed_payload_carries_scope_anchor(self, tmp_path):
        heldout.cmd_plan_sealed(tmp_path / "ws", seed_hex="ef" * 32,
                                seed_source="test", context="sealed4-v2",
                                scope="broadcast-pilot-v1")
        payload = json.loads((tmp_path / "ws" / "doc_list.json").read_text())
        assert payload["scope"] == "broadcast-pilot-v1"
        assert payload["context"] == "sealed4-v2"
        sp = payload["scope_pool"]
        assert (sp["strong_n"], sp["weak_n"], sp["union_n"]) == (2725, 1471, 4196)
        assert sp["union_sha256"] == (
            "78066c41a4bea9fa5f5102ccd5977ae2993297ba5fbb055b04cee810e0ae438c")
        assert len(payload["doc_ids"]) == 100
