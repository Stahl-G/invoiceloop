"""H1 复核工作台:loopback 服务器的契约测试(先测试,后实现)。

钉死的东西(服务器与测试双向遵守,谁也不许单方面改):

- make_server(workspace, port) 绑 127.0.0.1,port=0 由系统分配;
- /decide 是裁决的唯一入口:语义透传 adjudicate(correct 必带值、
  accept 禁带值、二次决定必须显式 supersedes),decided_at 由服务器盖戳;
- 页面输出必须转义 —— 人写的 rationale 原样进 HTML 就是 XSS;
- /upload 的文件名只留 [a-z0-9-],/files 不许路径穿越;
- bundle 离线可验:改一个字节,/verify 页面必须说出失败。

fixture 形状照抄 test_run_immutability.py(同一仓库的最小 workspace)。
"""

from __future__ import annotations

import http.client
import io
import json
import re
import threading
import zipfile
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest

from invoiceloop import adjudicate, ocr

DOC = "acme-001"
RUN = "run-0001"

# decided_at 是服务器在点击瞬间盖的 UTC ISO 秒戳,只认 Z 或 +00:00 结尾
_DECIDED_AT_RE = re.compile(r"^20\d\d-\d\d-\d\dT.*(Z|[+]00:00)$")


def _ocr_payload() -> dict:
    words = [
        ("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30), ("Gross", 0.40),
    ]
    return {"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
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
    """最小 workspace + 一个跑完的 run-0001,并登记为 current。"""
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
    monkeypatch.setenv("INVOICELOOP_DWS_DERISK", str(ws))
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    from invoiceloop.pipeline import run

    run([DOC], ws / "runs" / RUN, include_vision=False, out_of_calibration=True)
    (ws / "runs" / "current.json").write_text('{"run": "run-0001"}',
                                              encoding="utf-8")
    yield ws
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


@pytest.fixture
def server(workspace):
    """起在后台线程的工作台,yield 实际端口;收尾 shutdown + server_close。"""
    from invoiceloop.workbench import make_server

    srv = make_server(workspace, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _req(port: int, method: str, path: str, body: bytes | None = None,
         headers: dict | None = None) -> tuple[int, dict, str]:
    """发一个请求,不跟随重定向(303 就是看 Location,不是到对岸)。

    返回 (status, headers, text);headers 的 key 一律小写,调用方不用猜大小写。
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}, \
        data.decode("utf-8", errors="replace")


def _decide(port: int, **over) -> tuple[int, dict, str]:
    """POST /decide 的便捷封装:默认是一条合法的 accept,按字段覆盖。"""
    form = {"run": RUN, "doc": DOC, "field": "total_gross", "claim_id": "",
            "decision": "accept", "corrected_value": "",
            "rationale": "证据齐", "adjudicator": "alice", "supersedes": ""}
    form.update(over)
    return _req(port, "POST", "/decide", body=urlencode(form).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"})


def _ledger(workspace: Path) -> list[dict]:
    p = workspace / "runs" / RUN / "adjudication_ledger.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()
            if x.strip()]


def _repack(data: bytes, mutate) -> bytes:
    """重打包 bundle:读全部成员 → mutate 改内容 → 重写(同 test_adjudicate)。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        items = {i.filename: zf.read(i.filename) for i in zf.infolist()}
    mutate(items)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, blob in items.items():
            zf.writestr(name, blob)
    return buf.getvalue()


class TestRouting:
    def test_root_redirects_to_queue(self, workspace, server):
        status, headers, _ = _req(server, "GET", "/")
        assert status == 303
        assert headers.get("location", "").startswith("/queue")

    def test_queue_page_lists_rows_with_decide_form(self, workspace, server):
        status, _, text = _req(server, "GET",
                               f"/queue?run={RUN}&filter=all")
        assert status == 200
        assert "INV-42" in text, "队列页得让人看到自己复核的是什么值"
        assert 'class="decide"' in text, "每行一个裁决表单,这是 H1 的主交互"
        assert 'name="rationale"' in text, "「问题/理由」输入域必须在表单里"

    def test_report_shows_progress_after_decision(self, workspace, server):
        rows = json.loads(
            (workspace / "runs" / RUN / "support_matrix.json").read_text())["rows"]
        s, _, _ = _decide(server)
        assert s == 303
        status, _, text = _req(server, "GET", f"/report?run={RUN}")
        assert status == 200
        assert f"1 / {len(rows)}" in text, \
            "完成度必须是真实计数(decided/total),不是恒真文案(对抗复核 #16)"

    def test_files_rejects_path_traversal(self, workspace, server):
        status, _, _ = _req(server, "GET",
                            f"/files/{RUN}/../../pyproject.toml")
        assert status in (400, 404), "路径穿越不许读到 run 目录外的任何东西"


class TestDecide:
    def test_decide_accept_happy_path(self, workspace, server):
        status, headers, _ = _decide(server)
        assert status == 303
        assert "notice=recorded" in headers.get("location", "")
        entries = _ledger(workspace)
        assert len(entries) == 1, "一次点击恰好一行裁决,不多不少"
        assert entries[0]["decision"] == "accept"
        assert _DECIDED_AT_RE.match(entries[0]["decided_at"]), \
            "decided_at 由服务器在点击时盖 UTC ISO 秒戳,不是表单带的"

    def test_decide_correct_without_value_is_400(self, workspace, server):
        status, _, text = _decide(server, decision="correct")
        assert status == 400
        assert any("一" <= c <= "鿿" for c in text), \
            "校验失败的页面要用中文说清为什么拒"
        assert _ledger(workspace) == [], "被拒的裁决一行都不许落盘"

    def test_decide_accept_with_corrected_value_is_400(self, workspace, server):
        status, _, _ = _decide(server, corrected_value="100.00")
        assert status == 400, "accept 禁止携带 corrected_value(裁决语义已冻结)"
        assert _ledger(workspace) == []

    def test_second_decision_requires_supersedes(self, workspace, server):
        s1, _, _ = _decide(server)
        assert s1 == 303
        first_id = _ledger(workspace)[0]["decision_id"]

        s2, _, _ = _decide(server, decision="reject", rationale="看错了")
        assert s2 == 400, "同槽第二次决定不带 supersedes 必须拒"
        assert len(_ledger(workspace)) == 1

        s3, _, _ = _decide(server, decision="reject", rationale="复核后改判",
                           supersedes=first_id)
        assert s3 == 303
        entries = _ledger(workspace)
        assert len(entries) == 2
        assert entries[1]["supersedes_decision_id"] == first_id, \
            "链靠 supersedes_decision_id 接上,投影才知道谁是 tip"

    def test_decide_sets_adjudicator_cookie(self, workspace, server):
        status, headers, _ = _decide(server)
        assert status == 303
        assert "alice" in headers.get("set-cookie", ""), \
            "成功后写裁决人 cookie —— 下次免填,但账本里永远显式"

    def test_rationale_is_escaped_on_queue(self, workspace, server):
        payload = "<script>alert(1)</script>"
        s, _, _ = _decide(server, rationale=payload)
        assert s == 303
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&filter=all")
        assert payload not in text, \
            "人写的理由原样进 HTML 就是 XSS —— 要么转义要么不出现"
        assert "&lt;script&gt;" in text, \
            "理由必须真的渲染在队列页(当前裁决提示里)—— 否则这条断言守的是" \
            "一块没有输出的页面(对抗复核 #17)"


class TestUpload:
    def test_upload_sanitizes_filename(self, workspace, server):
        path = "/upload?filename=" + quote("evil<script>.pdf")
        status, _, text = _req(server, "POST", path, body=b"%PDF-1.4 evil",
                               headers={"Content-Type":
                                        "application/octet-stream"})
        assert status == 200
        saved = json.loads(text)["saved"]
        assert re.fullmatch(r"[a-z0-9-]+", saved), \
            "doc_id 进路径进 URL,文件名必须净化到只剩 [a-z0-9-]"
        assert (workspace / "input" / "pdfs" / f"{saved}.pdf").exists()

    def test_upload_rejects_non_pdf(self, workspace, server):
        status, _, _ = _req(server, "POST", "/upload?filename=x.txt",
                            body=b"not a pdf",
                            headers={"Content-Type":
                                     "application/octet-stream"})
        assert status == 400


class TestIngest:
    def test_ingest_replays_same_inputs(self, workspace, server):
        status, headers, _ = _req(
            server, "POST", "/ingest",
            body=urlencode({"do_extract": "0"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert status == 303
        assert "notice=replayed" in headers.get("location", ""), \
            "输入指纹没变就必须重放既有 run,不静默开新 run"


class TestBundle:
    def _bundle(self, workspace, server) -> Path:
        """先裁一条(账本非空,bundle 必需工件才齐),再 POST /bundle。"""
        s, _, _ = _decide(server)
        assert s == 303
        status, _, _ = _req(
            server, "POST", "/bundle",
            body=urlencode({"run": RUN}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert status == 303
        bundle = workspace / "runs" / RUN / "audit_bundle.zip"
        assert bundle.exists(), "POST /bundle 之后 run 目录必须出现 audit_bundle.zip"
        return bundle

    def test_bundle_download_and_verify(self, workspace, server):
        bundle = self._bundle(workspace, server)
        status, headers, _ = _req(server, "GET",
                                  f"/download/{RUN}/audit_bundle.zip")
        assert status == 200
        assert "zip" in headers.get("content-type", "")
        report = adjudicate.verify_bundle(bundle)
        assert report["ok"], report["failures"]

    def test_verify_reports_tampered_bundle(self, workspace, server):
        bundle = self._bundle(workspace, server)
        tampered = _repack(bundle.read_bytes(), lambda items: items.__setitem__(
            "gate_report.json", items["gate_report.json"] + b"x"))
        status, _, text = _req(server, "POST", "/verify", body=tampered,
                               headers={"Content-Type":
                                        "application/octet-stream"})
        assert status == 200
        assert "哈希" in text or "失败" in text or "fail" in text.lower(), \
            "被改过的 bundle 过 /verify,页面必须说出失败,不许只回个 ok"

# 契约如有调整以 invoiceloop/workbench.py 模块 docstring 为准。


# ---------------------------------------------------------------- 对抗复核修复批(2026-08-03)

class TestLoopbackGates:
    """Host/Origin 两道闸:loopback ≠ 安全(跨站表单 + DNS rebinding)。"""

    def test_foreign_host_is_rejected(self, server):
        status, _, _ = _req(server, "GET", "/queue",
                            headers={"Host": "evil.example"})
        assert status == 403

    def test_loopback_hosts_pass(self, server):
        status, _, _ = _req(server, "GET", "/queue?run=%s" % RUN,
                            headers={"Host": "localhost"})
        assert status == 200

    def test_cross_origin_post_writes_nothing(self, workspace, server):
        form = {"run": RUN, "doc": DOC, "field": "total_gross", "claim_id": "",
                "decision": "accept", "corrected_value": "",
                "rationale": " forged by a malicious page",
                "adjudicator": "mallory", "supersedes": ""}
        status, _, _ = _req(
            server, "POST", "/decide", body=urlencode(form).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Origin": "http://evil.example"})
        assert status == 403
        assert _ledger(workspace) == [], "跨源 POST 一个字都不许写进裁决账本"


class TestUploadInvalidation:
    def test_changed_same_name_pdf_invalidates_stale_evidence(self, workspace, server):
        assert (workspace / "ocr" / f"{DOC}.json").exists()
        status, _, text = _req(server, "POST", "/upload?filename=acme-001.pdf",
                               body=b"%PDF-1.4 different bytes entirely",
                               headers={"Content-Type": "application/octet-stream"})
        assert status == 200
        payload = json.loads(text)
        assert payload["saved"] == DOC
        assert set(payload["invalidated"]) == {
            f"{DOC}.json", f"{DOC}.understand.json", f"{DOC}.agentic.json"}
        assert not (workspace / "ocr" / f"{DOC}.json").exists(), \
            "旧 OCR 必须随新内容失效 —— 拿旧证据配新文档是最坏的静默"
        assert not (workspace / "raw" / f"{DOC}.understand.json").exists()

    def test_identical_reupload_keeps_evidence(self, workspace, server):
        body = (workspace / "input" / "pdfs" / f"{DOC}.pdf").read_bytes()
        status, _, text = _req(server, "POST", "/upload?filename=acme-001.pdf",
                               body=body,
                               headers={"Content-Type": "application/octet-stream"})
        assert status == 200
        assert json.loads(text)["invalidated"] == []
        assert (workspace / "ocr" / f"{DOC}.json").exists(), "同内容重传是幂等,不许失效"


class TestIngestFailureSurfacing:
    def test_ingest_without_pdfs_is_400_not_a_hang(self, tmp_path):
        import os

        from invoiceloop.workbench import make_server

        empty = tmp_path / "empty-ws"
        empty.mkdir()
        prev = os.environ.get("INVOICELOOP_DWS_DERISK")
        srv = make_server(empty, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            status, _, text = _req(
                srv.server_address[1], "POST", "/ingest",
                body=urlencode({"do_extract": "0"}).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            assert status == 400, "SystemExit 必须变成 400 页,不是掐连接"
            assert "input/pdfs" in text
        finally:
            srv.shutdown()
            srv.server_close()
            if prev is not None:
                os.environ["INVOICELOOP_DWS_DERISK"] = prev


class TestNoJsFallback:
    def test_corrected_value_input_is_not_disabled_in_html(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}")
        tag = re.search(r'<input class="wb-corr"[^>]*>', text)
        assert tag, "修正值输入框必须在"
        assert "disabled" not in tag.group(0), \
            "disabled 只能由 JS 加载后按选择加 —— 无 JS 时 correct 也要能提交"


class TestVerifyFragment:
    def test_non_zip_body_is_failure_fragment_not_500(self, workspace, server):
        status, _, text = _req(server, "POST", "/verify?lang=zh",
                               body=b"definitely not a zip",
                               headers={"Content-Type": "application/octet-stream"})
        assert status == 200
        assert "不是合法的 zip" in text, "坏输入要走失败分支,不是服务器崩溃"


class TestNavigation:
    def test_upload_tab_href_uses_question_mark(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert "/upload&lang=" not in text, \
            "tab 链接拼接必须按有无 query string 选 ?/&(实测 /upload&lang=zh 404)"
        assert 'href="/upload?lang=' in text

    def test_404_page_has_a_way_back(self, workspace, server):
        status, _, text = _req(server, "GET", "/no-such-page")
        assert status == 404
        assert f"/queue?run={RUN}" in text, \
            "404/消息页必须给回队列的路(实测只剩上传 tab,被困住)"


class TestTaskLines:
    """2026-08-03 用户反馈:复核者要在每行看到自己的任务目标。"""

    def test_row_states_the_task_in_plain_language(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh&filter=all")
        assert "任务:在页面上核对" in text, "有值的行要说出核什么、DWS 读到什么"
        assert "买方名称" in text, "字段要有人类名字,不只是 buyer_name"
        assert "任务:DWS 没给出" in text, "无值的行要说出补录路径"
        assert "buyer_name" in text, "原始字段名保留(小字),对账用"

    def test_task_line_english_default(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=en&filter=all")
        assert "Task: verify the" in text and "Buyer name" in text

    def test_limitation_codes_are_humanized(self, workspace, server):
        from invoiceloop.workbench import _lim

        assert "机械核对" in _lim("zh", "ocr_unavailable_pipeline_blocked")
        assert "机械核对" not in _lim("zh", "unknown_future_code"), \
            "没收录的码原样显示,不编"
        assert _lim("en", "vision_offers:GPT=x") == \
            "vision reader GPT saw “x” (reference only)"
