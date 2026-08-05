"""81 评 P0:投影被当成权威值使用的攻击链回归测试。

攻击(评审在副本上实测):只改 support_matrix.json 里的行值(投影,
不在快照成分内)→ append accept → deliverable 输出被污染值 →
bundle verify 三层全过。修复的四层防线:

1. append:matrix 行值与冻结声明不符 → 拒绝裁决;
2. deliverable:值源永远是 field_ledger / adjudication_ledger,不是 matrix;
3. verify:第 4 层(语义层)交叉验证投影值与包内权威;
4. 本文件:钉死这条链不许复活。
"""

from __future__ import annotations

import json

import pytest

from invoiceloop import adjudicate, deliver, ocr
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"
DECIDED = "2026-08-05T02:00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / f"{DOC}.json").write_text(json.dumps({"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in (("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30))]}]}],
    }]}))
    (d / "raw").mkdir()
    data = {"invoice_number": "INV-42", "total_gross": "100.00"}
    for mode in ("understand", "agentic"):
        (d / "raw" / f"{DOC}.{mode}.json").write_text(json.dumps(
            {"doc_id": DOC, "document": f"{DOC}.pdf", "mode": mode,
             "http_status": 200,
             "body": {"output": {"data": data, "metadata": {},
                                 "pages": [{"page": 1, "width": 612,
                                            "height": 792}]}}}))
    pin_corpus(monkeypatch, d)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    out = d / "runs" / "run-0001"
    pipeline_run([DOC], out, include_vision=False, out_of_calibration=True)
    yield out
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def _tamper_matrix(run_dir, new_value):
    path = run_dir / "support_matrix.json"
    m = json.loads(path.read_text())
    for row in m["rows"]:
        if row["field"] == "total_gross":
            row["value"] = new_value
    path.write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return new_value


class TestProjectionIsNotAuthority:
    def test_append_refuses_tampered_projection(self, ws):
        """防线 1:投影被改,append 交叉检查直接拒 —— 在被动过的证据上不记裁决。"""
        _tamper_matrix(ws, "999999999.99")
        ledger = json.loads((ws / "field_ledger.json").read_text())
        claim = next(c for c in ledger["claims"]
                     if c["doc_id"] == DOC and c["field"] == "total_gross"
                     and c["drafted_by"] == "dws_understand")
        with pytest.raises(ValueError, match="投影与权威分叉"):
            adjudicate.append_adjudication(
                ws, claim_id=claim["claim_id"], doc_id=DOC, field="total_gross",
                decision="accept", rationale="r", adjudicator="t",
                decided_at=DECIDED)

    def test_deliverable_ignores_tampered_projection(self, ws):
        """防线 2:就算投影被改,deliverable 的值仍来自冻结账本。"""
        _tamper_matrix(ws, "999999999.99")
        ledger = json.loads((ws / "field_ledger.json").read_text())
        claim = next(c for c in ledger["claims"]
                     if c["doc_id"] == DOC and c["field"] == "total_gross"
                     and c["drafted_by"] == "dws_understand")
        # accept 走「绕过 append 交叉检查」的路径:先把投影改回去 append,
        # 再改投影验证 deliverable 取值
        path = ws / "support_matrix.json"
        m = json.loads(path.read_text())
        for row in m["rows"]:
            if row["field"] == "total_gross":
                row["value"] = claim["value"]
        path.write_text(json.dumps(m, indent=1, ensure_ascii=False))
        adjudicate.append_adjudication(
            ws, claim_id=claim["claim_id"], doc_id=DOC, field="total_gross",
            decision="accept", rationale="r", adjudicator="t", decided_at=DECIDED)
        _tamper_matrix(ws, "999999999.99")
        f = deliver.build_deliverable(ws)["docs"][DOC]["fields"]["total_gross"]
        assert f["value"] == "100.00" and f["status"] == "accepted", \
            "deliverable 的值必须来自 field_ledger,不是 support_matrix"

    def test_verify_semantics_layer_catches_tampered_projection(self, ws):
        """防线 3:打包时投影已污染,verify 语义层必须失败(前三层全过)。"""
        bundle = adjudicate.build_audit_bundle(ws)
        import zipfile

        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename)
                     for i in zf.infolist() if i.filename != "MANIFEST.sha256"}
        m = json.loads(items["support_matrix.json"])
        for row in m["rows"]:
            if row["field"] == "total_gross":
                row["value"] = "999999999.99"
        items["support_matrix.json"] = json.dumps(
            m, indent=1, ensure_ascii=False).encode()
        import hashlib

        manifest = "".join(
            f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in items.items())
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)
            zf.writestr("MANIFEST.sha256", manifest)
        report = adjudicate.verify_bundle(bundle)
        assert report["layers"]["members"] is True, "攻击者重算了 MANIFEST,成员级照过"
        assert report["layers"]["snapshot"] is True, "matrix 不是快照成分,快照层照过"
        assert report["layers"]["semantics"] is False, \
            "语义层必须抓住投影值与冻结声明分叉"
        assert not report["ok"]

    def test_verify_recomputes_routing_report(self, ws):
        """评审裁决三:伪造 routing_report(某槽 review→auto_accept)+
        同步重算快照 —— 成员级与快照级全过,语义层必须抓住
        「路由不是所嵌策略的正确执行」。"""
        import hashlib
        import zipfile

        from invoiceloop.snapshot import snapshot_id_from_components

        bundle = adjudicate.build_audit_bundle(ws)
        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename)
                     for i in zf.infolist() if i.filename != "MANIFEST.sha256"}
        rr = json.loads(items["routing_report.json"])
        target = next(r for r in rr["routes"] if r["route"] != "auto_accept")
        target["route"] = "auto_accept"
        target["reason_codes"] = ["POLICY_ACCEPT:FORGED"]
        items["routing_report.json"] = json.dumps(
            rr, indent=1, ensure_ascii=False).encode() + b"\n"
        # 攻击者同步重算快照(routing_report 是快照成分)
        snap = json.loads(items["review_snapshot.json"])
        snap["components"]["routing_report.json"] = hashlib.sha256(
            items["routing_report.json"]).hexdigest()
        snap["review_snapshot_id"] = snapshot_id_from_components(
            snap["components"])
        items["review_snapshot.json"] = json.dumps(
            snap, indent=1, ensure_ascii=False).encode()
        manifest = "".join(
            f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in items.items())
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)
            zf.writestr("MANIFEST.sha256", manifest)
        report = adjudicate.verify_bundle(bundle)
        assert report["layers"]["members"] is True
        assert report["layers"]["snapshot"] is True, "攻击者同步重算了快照"
        assert report["layers"]["semantics"] is False, \
            "语义层必须重算路由并抓住伪造"
        assert any("路由" in f for f in report["failures"])

    def test_coordinated_matrix_routing_tamper_caught(self, ws):
        """83 评残余边界(高级裁决六钉死):同步改矩阵行事实(gate_verdicts
        伪造成全 pass)+ routing_report 对应槽改 auto_accept + 重算快照
        + 重算 MANIFEST。旧版语义层从矩阵行取事实,此攻击能过四层;
        现在事实从 field_ledger + gate_report + raw 重建,矩阵行与权威
        重建不符即被抓。"""
        import hashlib
        import zipfile

        from invoiceloop.snapshot import snapshot_id_from_components

        bundle = adjudicate.build_audit_bundle(ws)
        with zipfile.ZipFile(bundle) as zf:
            items = {i.filename: zf.read(i.filename)
                     for i in zf.infolist() if i.filename != "MANIFEST.sha256"}
        m = json.loads(items["support_matrix.json"])
        rr = json.loads(items["routing_report.json"])
        target = next(r for r in m["rows"] if r["route"] != "auto_accept")
        key = (target["doc_id"], target["field"])
        # 协调篡改:矩阵事实伪造成「全部门禁通过、双源印证」
        target["gate_verdicts"] = {g: "pass" for g in target["gate_verdicts"]}
        target["support_strength"] = "corroborated"
        target["slot_blocking"] = False
        target["doc_blocked"] = False
        for route in rr["routes"]:
            if route["doc_id"] == key[0] and route["field"] == key[1]:
                route["route"] = "auto_accept"
                route["reason_codes"] = ["CLEAN"]
        items["support_matrix.json"] = json.dumps(
            m, indent=1, ensure_ascii=False).encode() + b"\n"
        items["routing_report.json"] = json.dumps(
            rr, indent=1, ensure_ascii=False).encode() + b"\n"
        snap = json.loads(items["review_snapshot.json"])
        snap["components"]["routing_report.json"] = hashlib.sha256(
            items["routing_report.json"]).hexdigest()
        snap["review_snapshot_id"] = snapshot_id_from_components(
            snap["components"])
        items["review_snapshot.json"] = json.dumps(
            snap, indent=1, ensure_ascii=False).encode()
        manifest = "".join(
            f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in items.items())
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in items.items():
                zf.writestr(name, data)
            zf.writestr("MANIFEST.sha256", manifest)
        report = adjudicate.verify_bundle(bundle)
        assert report["layers"]["members"] is True
        assert report["layers"]["snapshot"] is True, "攻击者同步重算了快照"
        assert report["layers"]["semantics"] is False, \
            "协调篡改必须被抓:矩阵事实与权威工件(field_ledger/gate_report)" \
            "重建不符"
        assert not report["ok"]


class TestDecisionSemantics:
    def test_accept_requires_claim(self, ws):
        with pytest.raises(ValueError, match="必须带 claim_id"):
            adjudicate.append_adjudication(
                ws, claim_id=None, doc_id=DOC, field="total_gross",
                decision="accept", rationale="r", adjudicator="t",
                decided_at=DECIDED)

    def test_confirm_absent_projects_to_confirmed_absent(self, ws):
        adjudicate.append_adjudication(
            ws, claim_id=None, doc_id=DOC, field="seller_name",
            decision="confirm_absent", rationale="页面上确实没有", adjudicator="t",
            decided_at=DECIDED)
        f = deliver.build_deliverable(ws)["docs"][DOC]["fields"]["seller_name"]
        assert f["status"] == "confirmed_absent" and f["value"] is None

    def test_not_applicable_is_a_distinct_semantics(self, ws):
        adjudicate.append_adjudication(
            ws, claim_id=None, doc_id=DOC, field="due_date",
            decision="not_applicable", rationale="本票无账期", adjudicator="t",
            decided_at=DECIDED)
        f = deliver.build_deliverable(ws)["docs"][DOC]["fields"]["due_date"]
        assert f["status"] == "not_applicable", \
            "不适用与确认缺失不许混 —— 下游 improvement 的信号不一样"

    def test_accept_on_claimed_slot_forbids_absence_decisions(self, ws):
        ledger = json.loads((ws / "field_ledger.json").read_text())
        claim = next(c for c in ledger["claims"]
                     if c["doc_id"] == DOC and c["field"] == "total_gross"
                     and c["drafted_by"] == "dws_understand")
        with pytest.raises(ValueError, match="声明错了用 reject 或 correct"):
            adjudicate.append_adjudication(
                ws, claim_id=claim["claim_id"], doc_id=DOC, field="total_gross",
                decision="confirm_absent", rationale="r", adjudicator="t",
                decided_at=DECIDED)
