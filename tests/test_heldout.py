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
        # 暴露清单含旧留出 100 + SEALED-1 100(均 ⊂ heldout_pool)
        assert len(heldout.sealed_pool()) == \
            len(heldout.heldout_pool()) - 200, \
            "旧留出 100 + SEALED-1 100 必须从合格池中移除"

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
