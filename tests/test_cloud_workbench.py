"""Cloud Run 绑定:PORT 解析、/healthz、公开 Host 闸。"""

from __future__ import annotations

import contextlib
import http.client
import json
import threading
import urllib.parse

import pytest

from invoiceloop import ocr
from tests.conftest import pin_corpus


DOC = "acme-001"
RUN = "run-0001"


def _ocr_payload() -> dict:
    words = [("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30)]
    return {"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99,
             "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in words
        ]}]}],
    }]}


def _record(doc_id: str, mode: str) -> dict:
    return {"doc_id": doc_id, "document": f"{doc_id}.pdf", "mode": mode,
            "http_status": 200,
            "body": {"output": {
                "data": {"invoice_number": "INV-42", "total_gross": "100.00"},
                "metadata": {},
                "pages": [{"page": 1, "width": 612, "height": 792}]}}}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "input" / "pdfs").mkdir(parents=True)
    (ws / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (ws / "ocr").mkdir()
    (ws / "ocr" / f"{DOC}.json").write_text(
        json.dumps(_ocr_payload()), encoding="utf-8")
    (ws / "raw").mkdir()
    for mode in ("understand", "agentic"):
        (ws / "raw" / f"{DOC}.{mode}.json").write_text(
            json.dumps(_record(DOC, mode)), encoding="utf-8")
    pin_corpus(monkeypatch, ws)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    from invoiceloop.pipeline import run

    run([DOC], ws / "runs" / RUN, out_of_calibration=True)
    (ws / "runs" / "current.json").write_text('{"run": "run-0001"}',
                                              encoding="utf-8")
    yield ws
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def test_resolve_port_prefers_cli_then_env(monkeypatch):
    from invoiceloop.workbench import resolve_port

    monkeypatch.delenv("PORT", raising=False)
    assert resolve_port(None) == 8765
    monkeypatch.setenv("PORT", "8080")
    assert resolve_port(None) == 8080
    assert resolve_port(9999) == 9999


def test_healthz_bypasses_host_gate(workspace):
    from invoiceloop.workbench import make_server

    srv = make_server(workspace, 0, host="0.0.0.0",
                      allowed_hosts={".run.app"})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/healthz", headers={"Host": "evil.example"})
        resp = conn.getresponse()
        body = resp.read()
        assert resp.status == 200
        assert json.loads(body)["ok"] is True
    finally:
        srv.shutdown()
        srv.server_close()


def test_public_bind_allows_run_app_suffix(workspace):
    from invoiceloop.workbench import make_server

    srv = make_server(workspace, 0, host="0.0.0.0",
                      allowed_hosts={".run.app"})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/", headers={
            "Host": "invoiceloop-xyz-uc.a.run.app",
        })
        resp = conn.getresponse()
        resp.read()
        assert resp.status != 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_public_bind_still_allows_loopback_host(workspace):
    from invoiceloop.workbench import make_server

    srv = make_server(workspace, 0, host="0.0.0.0",
                      allowed_hosts={".run.app"})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status != 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_loopback_still_rejects_foreign_host(workspace):
    from invoiceloop.workbench import make_server

    srv = make_server(workspace, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/queue", headers={"Host": "evil.example"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_cloud_pull_fails_loud_without_sdk(tmp_path):
    from invoiceloop import cloud_sync as cs

    original = cs._client

    def raise_missing():
        raise SystemExit(
            "缺 google-cloud-storage —— pip install 'invoiceloop[cloud]'"
        )

    cs._client = raise_missing  # type: ignore[assignment]
    try:
        with pytest.raises(SystemExit, match="google-cloud-storage"):
            cs.pull("gs://bucket/prefix", tmp_path / "ws")
    finally:
        cs._client = original


# ── 只读模式:公开演示不许写裁决账本 ──────────────────────────────

#: 工作台上全部写入路由。裁决账本是「某个人看过并判了」的证词 ——
#: 公网可写等于任何人都能伪造一条人类裁决。
POST_ROUTES = ["/decide", "/upload", "/ingest", "/bundle", "/verify",
               "/improve/adopt", "/improve/adopt-schema",
               "/improve/evaluate", "/improve/promote"]


@contextlib.contextmanager
def _server(workspace, **kw):
    from invoiceloop.workbench import make_server

    srv = make_server(workspace, 0, **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


def _post(port, path, host="127.0.0.1", body=""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=body, headers={
        "Host": host, "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body))})
    r = conn.getresponse()
    return r.status, r.read()


def _get(port, path, host="127.0.0.1"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path, headers={"Host": host})
    r = conn.getresponse()
    return r.status, r.read()


def test_read_only_refuses_every_write_route(workspace):
    with _server(workspace, read_only=True) as port:
        for path in POST_ROUTES:
            status, body = _post(port, path)
            assert status == 403, f"{path} 在只读模式下没有被拒(得到 {status})"


def _decide_body(claim_id: str) -> str:
    """一份**真的会写账本**的 /decide 表单。

    空 POST 在任何模式下都会被参数校验挡掉,拿它测只读等于什么都没测
    (第一版就是这样,变异测试抓到)。
    """
    return urllib.parse.urlencode({
        "run": RUN, "claim_id": claim_id, "doc": DOC,
        "field": "invoice_number", "decision": "accept",
        "rationale": "值与页面一致", "adjudicator": "judge",
    })


def _claim_id(workspace) -> str:
    ledger = json.loads(
        (workspace / "runs" / RUN / "field_ledger.json").read_text())
    return next(c["claim_id"] for c in ledger["claims"]
                if c["field"] == "invoice_number")


def test_the_decide_payload_really_writes_when_writable(workspace):
    """先证明这份表单在可写模式下确实追加账本 —— 否则下一条测试是空的。"""
    path = workspace / "runs" / RUN / "adjudication_ledger.jsonl"
    before = path.read_bytes() if path.exists() else None
    with _server(workspace) as port:
        status, _ = _post(port, "/decide", body=_decide_body(_claim_id(workspace)))
    assert status in (200, 303), status
    assert path.exists() and path.read_bytes() != before


def test_read_only_leaves_the_decision_ledger_byte_identical(workspace):
    path = workspace / "runs" / RUN / "adjudication_ledger.jsonl"
    before = path.read_bytes() if path.exists() else None

    with _server(workspace, read_only=True) as port:
        status, _ = _post(port, "/decide", body=_decide_body(_claim_id(workspace)))

    assert status == 403
    after = path.read_bytes() if path.exists() else None
    assert after == before


def test_read_only_still_serves_the_queue(workspace):
    with _server(workspace, read_only=True) as port:
        status, _ = _get(port, "/queue")
        assert status == 200


def test_read_only_page_discloses_that_it_is_read_only(workspace):
    """评委不能以为自己在真的裁决 —— 页面必须说清楚(宪章六)。"""
    with _server(workspace, read_only=True) as port:
        _, body = _get(port, "/queue")
    assert b"read-only" in body.lower() or "只读".encode() in body


def test_writable_is_the_default(workspace):
    """默认不是只读 —— 本地 HITL 必须照常能写。"""
    with _server(workspace) as port:
        status, body = _post(port, "/decide")
        assert status != 403 or b"read-only" not in body.lower()
