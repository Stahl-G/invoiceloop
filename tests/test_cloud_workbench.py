"""Cloud Run 绑定:PORT 解析、/healthz、公开 Host 闸。"""

from __future__ import annotations

import http.client
import json
import threading

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
