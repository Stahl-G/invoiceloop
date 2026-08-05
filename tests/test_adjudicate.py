"""M4 裁决 v2:快照绑定、三元一致、决策语义、supersession、渲染失败隔离。

对应不变量 5/6/7/8/9:裁决绑完整 review_snapshot;claim_id↔doc_id↔field
精确一致;缺值槽用稳定 target_id;二次决定必须显式 supersede;panel 是
可重建投影,渲染失败不回滚已落盘的裁决。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import adjudicate
from invoiceloop.review import project_run, target_id_for
from invoiceloop.snapshot import compute_review_snapshot

DECIDED = "2026-08-03T10:00:00"


@pytest.fixture
def run_dir(tmp_path):
    """最小但可渲染、可打包的 v2 run 目录:真实形状的工件 + 上游证据 + 快照。"""
    import hashlib

    d = tmp_path
    (d / "run_manifest.json").write_text(json.dumps({
        "docs": ["doc-a"], "n_docs": 1, "out_of_calibration": False,
        "layout": "workspace", "derisk_root": str(tmp_path)}), encoding="utf-8")
    (d / "artifact_registry.json").write_text("[]", encoding="utf-8")
    (d / "evidence_span_registry.json").write_text("[]", encoding="utf-8")
    (d / "field_claim_graph.json").write_text("[]", encoding="utf-8")
    (d / "field_drafts.json").write_text("[]", encoding="utf-8")
    (d / "field_ledger.json").write_text(json.dumps({
        "claims": [{"claim_id": "FC-0001", "doc_id": "doc-a",
                    "field": "total_gross", "value": "100.00"}],
        "rejections": [], "sha256": "ledger-sha"}), encoding="utf-8")
    (d / "gate_report.json").write_text(json.dumps({"findings": []}), encoding="utf-8")
    row = {"doc_id": "doc-a", "field": "total_gross", "value": "100.00",
           "support_strength": "single_source", "source_tiers": ["dws_extraction"],
           "applicability": "applicable", "limitations": [], "span_ids": [],
           "cited_span_ids": [], "rejections": [], "blocking_findings": [],
           "gate_verdicts": {}}
    (d / "support_matrix.json").write_text(json.dumps({
        "rows": [row],
        "summary": {"docs": 1, "slots": 1,
                    "by_strength": {"unsupported": 0, "single_source": 1, "corroborated": 0},
                    "requires_adjudication": 1, "applicability_disputed": 0,
                    "blocking_findings": 0, "drafts_rejected": 0,
                    "rejected_by_drafter": {}}}), encoding="utf-8")
    (d / "event_log.jsonl").write_text("", encoding="utf-8")
    # 上游证据(workspace 根 = run_manifest.derisk_root = 同一个 tmp_path)
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / "doc-a.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / "doc-a.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    (d / "raw").mkdir()
    for mode in ("understand", "agentic"):
        (d / "raw" / f"doc-a.{mode}.json").write_text(
            json.dumps({"http_status": 200}), encoding="utf-8")
    # input_manifest 记录上游证据的真实 sha —— bundle 按它判断
    # 「应该有且内容一致 / run 时就不存在」,只查存在性会把被换的证据静默打进包
    def h(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    (d / "input_manifest.json").write_text(json.dumps({
        "fingerprint": "f" * 64,
        "docs": [{"doc_id": "doc-a",
                  "pdf_sha256": h(d / "input" / "pdfs" / "doc-a.pdf"),
                  "ocr_sha256": h(d / "ocr" / "doc-a.json"),
                  "raw_sha256": {m: h(d / "raw" / f"doc-a.{m}.json")
                                 for m in ("understand", "agentic")}}],
    }), encoding="utf-8")
    # 快照最后写:成分齐了再算,与 pipeline 的顺序一致
    (d / "review_snapshot.json").write_text(
        json.dumps(compute_review_snapshot(d)), encoding="utf-8")
    return d


def _render(run_dir):
    from invoiceloop.panel import render_panel_from_run

    render_panel_from_run(run_dir)


def _append(d, **kw):
    base = dict(claim_id="FC-0001", doc_id="doc-a", field="total_gross",
                decision="accept", rationale="证据齐", adjudicator="y",
                decided_at=DECIDED)
    base.update(kw)
    return adjudicate.append_adjudication(d, **base)


class TestEntryShape:
    def test_entry_binds_full_review_snapshot(self, run_dir):
        entry = _append(run_dir)
        persisted = json.loads((run_dir / "review_snapshot.json").read_text())
        assert entry["review_snapshot_id"] == persisted["review_snapshot_id"]
        assert entry["decision_id"] == "HD-0001"
        assert entry["target_id"] == target_id_for(
            persisted["review_snapshot_id"], "doc-a", "total_gross")
        assert entry["supersedes_decision_id"] is None

    def test_missing_field_slot_uses_stable_target(self, run_dir):
        entry = _append(run_dir, claim_id=None, field="total_vat",
                        decision="correct", corrected_value="10.00",
                        rationale="纸面为 10")
        sid = json.loads((run_dir / "review_snapshot.json").read_text())["review_snapshot_id"]
        assert entry["target_id"] == target_id_for(sid, "doc-a", "total_vat")
        assert entry["claim_id"] is None

    def test_entries_are_append_only_with_seq(self, run_dir):
        _append(run_dir)
        _append(run_dir, claim_id=None, field="total_vat", decision="abstain",
                rationale="看不准")
        lines = (run_dir / "adjudication_ledger.jsonl").read_text().splitlines()
        assert [json.loads(x)["seq"] for x in lines] == [1, 2]
        assert json.loads(lines[1])["decision_id"] == "HD-0002"


class TestValidation:
    def test_unknown_decision_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="decision"):
            _append(run_dir, decision="looks-good")

    def test_correct_requires_corrected_value(self, run_dir):
        with pytest.raises(ValueError, match="corrected_value"):
            _append(run_dir, decision="correct")

    def test_non_correct_forbids_corrected_value(self, run_dir):
        with pytest.raises(ValueError, match="禁止携带"):
            _append(run_dir, decision="accept", corrected_value="100.00")

    def test_unknown_field_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="受评字段"):
            _append(run_dir, field="address")

    def test_doc_outside_run_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="文档集合"):
            _append(run_dir, claim_id=None, doc_id="doc-b", decision="abstain")

    def test_empty_decided_at_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="decided_at"):
            _append(run_dir, decided_at=" ")

    def test_unknown_claim_id_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="不在已冻结账本"):
            _append(run_dir, claim_id="FC-9999")

    def test_claim_doc_field_triple_must_match(self, run_dir):
        with pytest.raises(ValueError, match="精确一致"):
            _append(run_dir, claim_id="FC-0001", field="total_net")


class TestSupersession:
    def test_second_decision_must_supersede_current_tip(self, run_dir):
        first = _append(run_dir)
        with pytest.raises(ValueError, match="supersedes_decision_id='HD-0001'"):
            _append(run_dir, decision="reject", rationale="看错了")
        with pytest.raises(ValueError, match="supersedes"):
            _append(run_dir, decision="reject", rationale="看错了",
                    supersedes_decision_id="HD-9999")
        second = _append(run_dir, decision="reject", rationale="复核后改判",
                         supersedes_decision_id=first["decision_id"])
        assert second["decision_id"] == "HD-0002"
        slot = project_run(run_dir)[first["target_id"]]
        assert slot["tip"]["decision_id"] == "HD-0002"
        assert len(slot["history"]) == 2 and not slot["conflict"]

    def test_supersedes_on_fresh_slot_is_refused(self, run_dir):
        with pytest.raises(ValueError, match="必须为 null"):
            _append(run_dir, supersedes_decision_id="HD-0001")

    def test_conflicted_chain_blocks_new_decisions(self, run_dir):
        sid = json.loads((run_dir / "review_snapshot.json").read_text())["review_snapshot_id"]
        target = target_id_for(sid, "doc-a", "total_gross")
        lines = []
        for i, decision in enumerate(("accept", "reject"), 1):
            lines.append(json.dumps({
                "seq": i, "decision_id": f"HD-{i:04d}", "review_snapshot_id": sid,
                "target_id": target, "claim_id": "FC-0001", "doc_id": "doc-a",
                "field": "total_gross", "decision": decision, "corrected_value": None,
                "rationale": "r", "adjudicator": "y", "decided_at": DECIDED,
                "supersedes_decision_id": None}))
        (run_dir / "adjudication_ledger.jsonl").write_text("\n".join(lines) + "\n")
        with pytest.raises(ValueError, match="冲突"):
            _append(run_dir, decision="abstain", rationale="r")


class TestRenderProjection:
    def test_adjudicate_and_render_reflects_on_panel(self, run_dir):
        result = adjudicate.adjudicate_and_render(
            run_dir, claim_id="FC-0001", doc_id="doc-a", field="total_gross",
            decision="correct", corrected_value="21000.00",
            rationale="printed total 与独立 OCR 一致", adjudicator="alice",
            decided_at=DECIDED)
        assert result["decision_recorded"] is True
        assert result["panel_refreshed"] is True
        html = (run_dir / "support_panel.html").read_text(encoding="utf-8")
        assert "人工修正" in html and "21000.00" in html
        assert "HD-0001" in html and "alice" in html
        assert "printed total 与独立 OCR 一致" in html
        assert "100.00" in html, "原 DWS 值必须留在原处,不许被修正值替换"
        assert "已人工裁决" in html

    def test_render_failure_does_not_rollback_decision(self, run_dir, monkeypatch):
        import invoiceloop.panel

        def boom(_):
            raise RuntimeError("磁盘满了")

        monkeypatch.setattr(invoiceloop.panel, "render_panel_from_run", boom)
        result = adjudicate.adjudicate_and_render(
            run_dir, claim_id="FC-0001", doc_id="doc-a", field="total_gross",
            decision="accept", rationale="证据齐", adjudicator="y", decided_at=DECIDED)
        assert result["decision_recorded"] is True
        assert result["panel_refreshed"] is False
        assert "磁盘满了" in result["render_error"]
        lines = (run_dir / "adjudication_ledger.jsonl").read_text().splitlines()
        assert len(lines) == 1, "渲染失败不许重复写裁决,也不许撤销"

    def test_render_from_disk_after_offline_append(self, run_dir):
        from invoiceloop.panel import render_panel_from_run

        _append(run_dir, decision="abstain", rationale="吃不准")
        render_panel_from_run(run_dir)
        html = (run_dir / "support_panel.html").read_text(encoding="utf-8")
        assert "人工弃权" in html and "review_snapshot_id=" in html


class TestBundle:
    def test_missing_artifact_blocks_the_bundle(self, run_dir):
        _append(run_dir)
        _render(run_dir)
        (run_dir / "gate_report.json").unlink()
        with pytest.raises(FileNotFoundError, match="阻断"):
            adjudicate.build_audit_bundle(run_dir)

    def test_bundle_carries_manifest_with_verifiable_hashes(self, run_dir):
        import hashlib
        import zipfile

        _append(run_dir)
        _render(run_dir)
        (run_dir / "crops").mkdir()
        (run_dir / "crops" / "ES-0001-1.png").write_bytes(b"\x89PNG fake")
        (run_dir / "pages").mkdir()
        (run_dir / "pages" / "doc-a-1.png").write_bytes(b"\x89PNG page")
        bundle = adjudicate.build_audit_bundle(run_dir)
        with zipfile.ZipFile(bundle) as zf:
            names = set(zf.namelist())
            assert "MANIFEST.sha256" in names
            for required in adjudicate.REQUIRED_ARTIFACTS:
                assert required in names
            manifest = zf.read("MANIFEST.sha256").decode()
            digest = hashlib.sha256(b"\x89PNG fake").hexdigest()
            assert f"{digest}  crops/ES-0001-1.png" in manifest


class TestSelfContainedBundle:
    def test_bundle_includes_all_upstream_evidence(self, run_dir):
        import hashlib
        import zipfile

        _append(run_dir)
        _render(run_dir)
        bundle = adjudicate.build_audit_bundle(run_dir)
        with zipfile.ZipFile(bundle) as zf:
            names = set(zf.namelist())
            assert {"evidence/pdfs/doc-a.pdf", "evidence/ocr/doc-a.json",
                    "evidence/raw/doc-a.understand.json",
                    "evidence/raw/doc-a.agentic.json",
                    "extraction_schema.json", "bundle_manifest.json"} <= names
            scope = json.loads(zf.read("bundle_manifest.json"))
            assert scope["bundle_scope"] == "full_run"
            assert scope["docs"] == ["doc-a"]
            assert scope["review_snapshot_id"]
            manifest = zf.read("MANIFEST.sha256").decode()
            digest = hashlib.sha256(b"%PDF-1.4 fake").hexdigest()
            assert f"{digest}  evidence/pdfs/doc-a.pdf" in manifest

    def test_missing_upstream_evidence_blocks(self, run_dir):
        _append(run_dir)
        _render(run_dir)
        (run_dir / "ocr" / "doc-a.json").unlink()
        with pytest.raises(FileNotFoundError, match="上游证据"):
            adjudicate.build_audit_bundle(run_dir)

    def test_bundle_captures_run_local_vision_inputs(self, run_dir):
        import hashlib

        vision_name = "answers6.A.tsv"
        vision = run_dir / "vision"
        vision.mkdir()
        vision_file = vision / vision_name
        vision_file.write_text(
            "doc\tfield\tvalue\n"
            "doc-a\ttotal_gross\t100.00\n", encoding="utf-8")

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        manifest.update({"include_vision": True, "vision_captured": [vision_name]})
        (run_dir / "run_manifest.json").write_text(json.dumps(manifest))
        input_manifest = json.loads((run_dir / "input_manifest.json").read_text())
        input_manifest["vision_sha256"] = {
            vision_name: hashlib.sha256(vision_file.read_bytes()).hexdigest()
        }
        (run_dir / "input_manifest.json").write_text(json.dumps(input_manifest))
        (run_dir / "review_snapshot.json").write_text(
            json.dumps(compute_review_snapshot(run_dir)))

        _append(run_dir)
        _render(run_dir)
        bundle = adjudicate.build_audit_bundle(run_dir)
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            assert f"vision/{vision_name}" in zf.namelist()
            scope = json.loads(zf.read("bundle_manifest.json"))
            assert any("已复制进 run/bundle" in n for n in scope["notes"])


class TestVerify:
    def _build(self, run_dir):
        _append(run_dir)
        _render(run_dir)
        return adjudicate.build_audit_bundle(run_dir)

    def _repack(self, bundle, mutate):
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename) for i in zf.infolist()}
        mutate(items)
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)

    def test_fresh_bundle_verifies(self, run_dir):
        report = adjudicate.verify_bundle(self._build(run_dir))
        assert report["ok"] and report["failures"] == [] and report["members"] > 10

    def test_one_flipped_byte_fails(self, run_dir):
        bundle = self._build(run_dir)
        self._repack(bundle, lambda items: items.__setitem__(
            "gate_report.json", items["gate_report.json"] + b"x"))
        report = adjudicate.verify_bundle(bundle)
        assert not report["ok"]
        assert any("哈希不符" in f for f in report["failures"])

    def test_unregistered_member_fails(self, run_dir):
        bundle = self._build(run_dir)
        self._repack(bundle, lambda items: items.__setitem__("evil.txt", b"x"))
        report = adjudicate.verify_bundle(bundle)
        assert not report["ok"]
        assert any("未登记成员" in f for f in report["failures"])

    def test_manifest_aware_attacker_is_caught_by_snapshot_recompute(self, run_dir):
        """改了工件又同步改 MANIFEST 的攻击者:成员级被蒙过,快照级抓。"""
        import hashlib

        bundle = self._build(run_dir)

        def attack(items):
            items["gate_report.json"] = items["gate_report.json"] + b"x"
            lines = []
            for line in items["MANIFEST.sha256"].decode().splitlines():
                digest, rel = line.split("  ", 1)
                if rel == "gate_report.json":
                    digest = hashlib.sha256(items["gate_report.json"]).hexdigest()
                lines.append(f"{digest}  {rel}")
            items["MANIFEST.sha256"] = ("\n".join(lines) + "\n").encode()

        self._repack(bundle, attack)
        report = adjudicate.verify_bundle(bundle)
        assert not report["ok"]
        assert any("review_snapshot" in f for f in report["failures"])
        assert not any("哈希不符" in f for f in report["failures"]), \
            "成员级应被攻击者蒙过 —— 抓它的必须是快照级重算"


class TestSnapshotConsistency:
    def test_append_blocks_when_run_artifacts_were_altered(self, run_dir):
        _append(run_dir)  # 第一条在一致状态下落盘
        (run_dir / "gate_report.json").write_text(json.dumps({"findings": [{"x": 1}]}))
        with pytest.raises(ValueError, match="被改动过"):
            _append(run_dir, claim_id=None, field="total_vat",
                    decision="abstain", rationale="r")


class TestOrphans:
    def test_foreign_snapshot_decisions_are_flagged_not_projected(self, run_dir):
        from invoiceloop.review import load_decisions

        foreign_sid = "e" * 64
        foreign = {"seq": 1, "decision_id": "HD-0001",
                   "review_snapshot_id": foreign_sid,
                   "target_id": target_id_for(foreign_sid, "doc-a", "total_gross"),
                   "claim_id": "FC-0001", "doc_id": "doc-a", "field": "total_gross",
                   "decision": "accept", "corrected_value": None,
                   "rationale": "从另一个 run 复制来的",
                   "adjudicator": "y", "decided_at": DECIDED,
                   "supersedes_decision_id": None}
        (run_dir / "adjudication_ledger.jsonl").write_text(
            json.dumps(foreign) + "\n", encoding="utf-8")
        decisions = load_decisions(run_dir)
        assert decisions[0]["orphan"] is True
        assert project_run(run_dir) == {}, "orphan 不进链,不许错投到这个 run 的槽位"
        _render(run_dir)
        html = (run_dir / "support_panel.html").read_text(encoding="utf-8")
        assert "未投影" in html and "HD-0001" in html, "历史不藏:orphan 要显式标出"


class TestUpstreamIntegrity:
    def test_swapped_upstream_evidence_blocks(self, run_dir):
        _append(run_dir)
        _render(run_dir)
        (run_dir / "input" / "pdfs" / "doc-a.pdf").write_bytes(b"%PDF-1.4 SWAPPED")
        with pytest.raises(FileNotFoundError, match="被换"):
            adjudicate.build_audit_bundle(run_dir)

    def test_absent_at_run_is_noted_not_blocked(self, run_dir):
        import zipfile

        # run 时 agentic 响应就不存在:input_manifest 记 null → 不拦,进 notes
        manifest = json.loads((run_dir / "input_manifest.json").read_text())
        manifest["docs"][0]["raw_sha256"]["agentic"] = None
        (run_dir / "input_manifest.json").write_text(json.dumps(manifest))
        (run_dir / "raw" / "doc-a.agentic.json").unlink()
        (run_dir / "review_snapshot.json").write_text(
            json.dumps(compute_review_snapshot(run_dir)))
        _append(run_dir)
        _render(run_dir)
        bundle = adjudicate.build_audit_bundle(run_dir)
        with zipfile.ZipFile(bundle) as zf:
            assert "evidence/raw/doc-a.agentic.json" not in zf.namelist()
            scope = json.loads(zf.read("bundle_manifest.json"))
            assert any("run 时就不存在" in n for n in scope["notes"])


class TestAppendConcurrency:
    """对抗复核(2026-08-03)实测:无锁时两个 barrier 对齐的线程 261/300
    写出重复 decision_id。现在临界区持锁,必须确定性唯一。"""

    def test_concurrent_appends_get_unique_ids(self, run_dir, tmp_path):
        import threading

        # 每线程一个独立槽位、每槽只打一枪(同槽第二枪合法地 400,
        # 不是本测试的目标;本测试打的是 seq/decision_id 分配的读-改-写竞态)。
        # 5 个全新 run 目录 × 10 线程同时开火。
        fields = ["total_gross", "total_net", "total_vat", "issue_date",
                  "due_date", "seller_name", "buyer_name", "seller_vat_id",
                  "invoice_number", "amount_due"]
        errors: list[Exception] = []

        def fresh_run(name: str) -> object:
            from invoiceloop.snapshot import compute_review_snapshot

            d = tmp_path / name
            d.mkdir()
            (d / "run_manifest.json").write_text(json.dumps(
                {"docs": ["doc-a"], "layout": "workspace"}))
            (d / "field_ledger.json").write_text(json.dumps(
                {"claims": [], "sha256": "x"}))
            (d / "review_snapshot.json").write_text(
                json.dumps(compute_review_snapshot(d)))
            return d

        for wave in range(5):
            d = fresh_run(f"wave-{wave}")
            barrier = threading.Barrier(len(fields) + 1)

            def hammer(field, _d=d):
                try:
                    barrier.wait()
                    adjudicate.append_adjudication(
                        _d, claim_id=None, doc_id="doc-a", field=field,
                        decision="abstain", rationale="race",
                        adjudicator="t", decided_at="2026-08-03T00:00:00")
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                    barrier.abort()

            threads = [threading.Thread(target=hammer, args=(f,)) for f in fields]
            for t in threads:
                t.start()
            barrier.wait()
            for t in threads:
                t.join()
            lines = (d / "adjudication_ledger.jsonl").read_text().splitlines()
            ids = [json.loads(x)["decision_id"] for x in lines]
            seqs = [json.loads(x)["seq"] for x in lines]
            assert len(lines) == len(fields)
            assert len(set(ids)) == len(ids), f"decision_id 重复:{ids}"
            assert sorted(seqs) == list(range(1, len(fields) + 1))
        assert not errors, f"并发追加不该出错:{errors}"


class TestVerifyHardening:
    def test_verify_detects_duplicate_decision_ids(self, run_dir):
        _append(run_dir)
        # 手工伪造一条与 HD-0001 同 id 的条目(模拟无锁时代写坏的账本)
        lines = (run_dir / "adjudication_ledger.jsonl").read_text().splitlines()
        dup = json.loads(lines[0])
        dup["seq"] = 2
        dup["supersedes_decision_id"] = "HD-0001"
        with (run_dir / "adjudication_ledger.jsonl").open("a") as fh:
            fh.write(json.dumps(dup, ensure_ascii=False) + "\n")
        _render(run_dir)
        report = adjudicate.verify_bundle(adjudicate.build_audit_bundle(run_dir))
        assert not report["ok"]
        assert any("重复" in f for f in report["failures"])

    def test_verify_rejects_claim_doc_field_mismatch(self, run_dir):
        import hashlib
        import zipfile

        from invoiceloop.snapshot import load_or_derive_snapshot

        _append(run_dir)
        _render(run_dir)
        bundle = adjudicate.build_audit_bundle(run_dir)
        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename) for i in zf.infolist()}
        entry = json.loads(items["adjudication_ledger.jsonl"].decode().strip())
        snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
        entry["field"] = "total_net"
        entry["target_id"] = target_id_for(snapshot_id, "doc-a", "total_net")
        items["adjudication_ledger.jsonl"] = (
            (json.dumps(entry, ensure_ascii=False) + "\n").encode())
        items["MANIFEST.sha256"] = "".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n"
            for name, data in items.items() if name != "MANIFEST.sha256"
        ).encode()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)

        report = adjudicate.verify_bundle(bundle)
        assert not report["ok"]
        assert any("claim" in failure and "不一致" in failure
                   for failure in report["failures"])

    def test_verify_rejects_non_zip(self, tmp_path):
        bad = tmp_path / "not-a-bundle.zip"
        bad.write_text("hello", encoding="utf-8")
        report = adjudicate.verify_bundle(bad)
        assert report["ok"] is False
        assert any("zip" in f for f in report["failures"])


class TestVerifyLayers:
    def test_v2_bundle_reports_all_layers_and_trust_root(self, run_dir):
        _append(run_dir)
        _render(run_dir)
        report = adjudicate.verify_bundle(adjudicate.build_audit_bundle(run_dir))
        assert report["ok"]
        assert report["layers"] == {"members": True, "snapshot": True,
                                    "binding": True, "semantics": True}
        assert any("信任根" in n or "带外" in n for n in report["notes"]), \
            "三层全过也必须说清:真实性锚在带外哈希,verify 不是自己的根"

    def test_v1_bundle_reports_member_only_depth(self, run_dir):
        _append(run_dir)
        _render(run_dir)
        bundle = adjudicate.build_audit_bundle(run_dir)
        # 从包里删掉 review_snapshot.json(模拟 v1 包)并重算 MANIFEST
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename) for i in zf.infolist()}
        del items["review_snapshot.json"]
        lines = [x for x in items["MANIFEST.sha256"].decode().splitlines()
                 if "review_snapshot.json" not in x]
        items["MANIFEST.sha256"] = ("\n".join(lines) + "\n").encode()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)
        report = adjudicate.verify_bundle(bundle)
        assert report["ok"], "v1 包成员级应通过"
        assert report["layers"]["members"] is True
        assert report["layers"]["snapshot"] is None, \
            "v1 包没有快照层 —— ok 不许掩盖深度差异(评审 P2)"
        assert any("v1" in n for n in report["notes"])

    def test_fully_consistent_forgery_passes_and_that_is_the_boundary(self, run_dir):
        """钉死信任边界:攻击者把工件、MANIFEST、review_snapshot、裁决绑定
        全部一致地重写(用项目自己的函数),verify 会过 —— 这不是 bug,
        是「verify 不能自己当信任根」的边界,真实性锚在带外哈希。"""
        import hashlib
        import zipfile

        from invoiceloop.snapshot import (SNAPSHOT_COMPONENTS,
                                          snapshot_id_from_components)

        _append(run_dir)
        _render(run_dir)
        bundle = adjudicate.build_audit_bundle(run_dir)
        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename) for i in zf.infolist()}

        # 协同伪造:改门禁报告 → 重算快照 → 重写裁决绑定 → 重算 MANIFEST
        gate = json.loads(items["gate_report.json"])
        gate["findings"] = []
        items["gate_report.json"] = json.dumps(gate).encode()
        new_sid = snapshot_id_from_components({
            name: hashlib.sha256(items[name]).hexdigest()
            for name in json.loads(items["review_snapshot.json"])["components"]})
        snap = json.loads(items["review_snapshot.json"])
        snap["review_snapshot_id"] = new_sid
        snap["components"]["gate_report.json"] = hashlib.sha256(
            items["gate_report.json"]).hexdigest()
        items["review_snapshot.json"] = json.dumps(snap).encode()
        entries = [json.loads(x) for x in
                   items["adjudication_ledger.jsonl"].decode().splitlines() if x]
        for e in entries:
            e["review_snapshot_id"] = new_sid
        items["adjudication_ledger.jsonl"] = (
            "".join(json.dumps(e) + "\n" for e in entries)).encode()
        items["MANIFEST.sha256"] = "".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n"
            for name, data in items.items() if name != "MANIFEST.sha256"
        ).encode()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)
        report = adjudicate.verify_bundle(bundle)
        assert report["ok"], "全一致的伪造会过 —— 这正是为什么要带外公布哈希"
