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
from tests.conftest import pin_corpus

DOC = "acme-001"
RUN = "run-0001"

# decided_at 是服务器在点击瞬间盖的 UTC ISO 秒戳,只认 Z 或 +00:00 结尾
_DECIDED_AT_RE = re.compile(r"^20\d\d-\d\d-\d\dT.*(Z|[+]00:00)$")


def _ocr_payload() -> dict:
    # "INVOICE" 是单据类型的**页面字面证据**。没有它,doctype 判 no_claim,
    # 改进层就挖不出任何类别×字段的缺席候选(mine 只收类型证据通过的事件),
    # 工作台的改进页也就永远是空的。
    words = [
        ("INVOICE", 0.02), ("INV-42", 0.10), ("Total", 0.20),
        ("100.00", 0.30), ("Gross", 0.40),
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
                "data": {"invoice_number": "INV-42", "total_gross": "100.00",
                         "invoice_type": "Invoice"},
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
    # 读图预填建议层的输入:必须在 pipeline.run 之前落盘(进 run 输入指纹)。
    (ws / "vision").mkdir()
    (ws / "vision" / "answers6.A.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        f"{DOC}\ttotal_gross\t100.00\tTotal\t\n"
        f"{DOC}\ttotal_net\t10.00\tNet\t\n"
        f"{DOC}\tissue_date\t10/31/2020\tDate\t\n"
        f"{DOC}\tinvoice_number\tABSTAIN\t\t\n", encoding="utf-8")
    (ws / "vision" / "answers6.B.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        f"{DOC}\ttotal_gross\t100.00\tTotal\t\n"
        f"{DOC}\ttotal_net\t10.00\tNet\t\n"
        f"{DOC}\tissue_date\t11/30/2020\tDate\t\n"
        f"{DOC}\tinvoice_number\tABSTAIN\t\t\n", encoding="utf-8")
    pin_corpus(monkeypatch, ws)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    from invoiceloop.pipeline import run

    run([DOC], ws / "runs" / RUN, include_vision=True, out_of_calibration=True)
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


def _claim_id_for(port: int, doc: str, field: str) -> str:
    """从队列页表单里读出该槽位的 claim_id(冻结顺序不该被测试硬编码)。"""
    status, _, text = _req(port, "GET", f"/queue?run={RUN}&filter=all")
    assert status == 200
    for m in re.finditer(
            r'name="doc" value="([^"]+)">.*?name="field" value="([^"]+)">'
            r'.*?name="claim_id" value="([^"]*)"', text, re.S):
        if m.group(1) == doc and m.group(2) == field:
            return m.group(3)
    raise AssertionError(f"queue 页找不到 {doc}/{field} 的表单")


def _decide(port: int, **over) -> tuple[int, dict, str]:
    """POST /decide 的便捷封装:默认是一条合法的 accept(claim_id 从队列页
    表单现读 —— 81 评 P0 后 accept 必须指向冻结声明),按字段覆盖。"""
    form = {"run": RUN, "doc": DOC, "field": "total_gross",
            "decision": "accept", "corrected_value": "",
            "rationale": "证据齐", "adjudicator": "alice", "supersedes": ""}
    form.update(over)
    if "claim_id" not in form or form["claim_id"] is None:
        form["claim_id"] = _claim_id_for(port, form["doc"], form["field"])
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
        assert '<details class="wb-evidence" open>' in text, \
            "证据默认摊开:多点一下才看得见 = 交互无意义(2026-08-03 用户原话)"

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
        # fixture 的 run 与 /ingest 都按 include_vision=True 算指纹,
        # 读图作答原样在盘上 —— 输入一字未动,必须重放
        status, headers, _ = _req(
            server, "POST", "/ingest",
            body=urlencode({"do_extract": "0"}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert status == 303
        assert "notice=replayed" in headers.get("location", ""), \
            "输入指纹没变就必须重放既有 run,不静默开新 run"

    def test_queue_uses_run_local_vision_inputs(self, workspace, server):
        for name in ("answers6.A.tsv", "answers6.B.tsv"):
            (workspace / "vision" / name).write_text(
                "doc\tfield\tvalue\tprinted_label\tnote\n"
                f"{DOC}\ttotal_gross\t999.00\tTotal\t\n",
                encoding="utf-8")
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh&filter=all")
        gross = _vs_row(text, "total_gross")
        assert "100.00" in gross and "999.00" not in gross, \
            "工作台必须使用 run 内捕获的读图输入,不读 run 之后被改的外部 TSV"


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
        assert "正确映射为" in text, "有值的行要说出 DWS 把什么读成了哪个字段"
        assert "买方名称" in text, "字段要有人类名字,不只是 buyer_name"
        assert "请检查页面是否明确写出" in text, "无值的行要说出补录路径"
        assert "buyer_name" in text, "原始字段名保留(小字),对账用"

    def test_task_line_english_default(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=en&filter=all")
        assert "Task: page evidence supports" in text and "Buyer name" in text

    def test_task_line_asks_about_mapping_not_mere_presence(
            self, workspace, server):
        """任务措辞必须问「这个值是不是这个字段的」,不是「页面上有没有」。

        两条已裁定口径的直接产物:值出现在页面上不等于映射对
        (WRONG_FIELD_MAPPING),以及缺的字段不许从邻栏或付款条款推导出来
        (docs/ARM_RUN_LOG_2026-08-08.md 口径裁定之二)。
        """
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=en&filter=all")
        assert "not merely" in text, "有值的行要点破「出现在页面上」不算数"
        assert "derive it from payment terms or another field" in text, \
            "无值的行要挡住从付款条款/邻栏推导"

    def test_document_class_never_licenses_an_assumed_absence(
            self, workspace, server):
        """认出类别之后,任务措辞必须**明确禁止**用类别当缺席的理由。

        SEALED-3 主臂唯一的静默缺席就是这条:doctype 正确认出 credit note,
        而「这类单据没有税号」这个无条件假设吞掉了一个真有值的 seller_vat_id
        (docs/SEALED3_RESULTS.md §4)。类别是上下文,不是答案。
        """
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh&filter=all")
        assert "不要仅凭单据类别假定缺失" in text
        _, _, en = _req(server, "GET", f"/queue?run={RUN}&lang=en&filter=all")
        assert "Do not assume it is absent from the document type" in en

    def test_limitation_codes_are_humanized(self, workspace, server):
        from invoiceloop.workbench import _lim

        assert "机械核对" in _lim("zh", "ocr_unavailable_pipeline_blocked")
        assert "机械核对" not in _lim("zh", "unknown_future_code"), \
            "没收录的码原样显示,不编"
        assert _lim("en", "vision_offers:GPT=x") == \
            "vision reader GPT saw “x” (reference only)"


class TestAcceptPreset:
    """接受 = 「与页面一致」的天然理由,不该手打(2026-08-03 用户要求)。"""

    def test_form_carries_accept_preset_and_js_uses_it(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert 'data-accept-preset="与页面一致"' in text
        _, _, js = _req(server, "GET", "/assets.js")
        assert "acceptPreset" in js, "JS 要在选接受时预填、切走时还原"

    def test_positive_chip_present(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert '>与页面一致</button>' in text


class TestQuickPathCarriesReasonCode:
    """快路按钮自带心码(2026-08-06):按钮文案本来就是一次语义选择,
    再用下拉问一遍是同一件事问两遍(run-0002 心码填写率 8/123 → 挖掘臂
    合格事件 0)。纪律:只在一对一时带,含糊的留空,不代人选。"""

    def test_accept_splits_into_plain_and_false_positive(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert 'data-decision="accept" data-value="" data-reason=""' in text, \
            "「该拦,我确认没问题」不带心码 —— 词表里没有「路由判对了」,"\
            "它也不构成放松规则的证据"
        assert 'data-reason="ROUTING_FALSE_POSITIVE"' in text, \
            "「白拦了」要能一键说出来 —— 这是挖掘低收益 cohort 唯一的信号"
        assert "不该进队列" in text

    def test_every_quick_button_declares_a_reason_slot(self, workspace, server):
        """每个快路按钮都要显式带 data-reason(可以为空)—— 漏掉属性和
        「故意留空」在 HTML 上必须区分得开,否则 JS 分不出来。"""
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh&filter=all")
        buttons = re.findall(r'<button[^>]*class="wb-quick-ok[^"]*"[^>]*>', text)
        assert buttons, "队列页应有快路按钮"
        assert all("data-reason=" in b for b in buttons), \
            [b for b in buttons if "data-reason=" not in b]

    def test_issue_chips_carry_one_to_one_codes_only(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert 'data-text="值不对" data-reason="WRONG_VALUE"' in text
        assert 'data-text="位置不对" data-reason="BAD_SOURCE_BINDING"' in text
        assert 'data-text="与页面一致" data-reason=""' in text, \
            "「与页面一致」不带码 —— 词表里没有「路由判对了」"
        assert 'data-text="口径冲突" data-reason=""' in text, \
            "applicability 争议在心码集里没有对应项,硬塞一个就是编"

    def test_js_writes_button_reason_and_one_to_one_prefill(self, workspace, server):
        """一对一心码仍自动预填,但判据必须来自 option 上的 data-decisions
        —— 2026-08-08 之前这里内置了一份 {confirm_absent: CONFIRMED_ABSENT}
        的小表,那就是 combo 表在前端的第二份副本(会漂移)。"""
        _, _, js = _req(server, "GET", "/assets.js")
        assert "dataset.reason" in js, "快路必须把按钮上的心码写进下拉"
        assert "CONFIRMED_ABSENT" not in js and "NOT_APPLICABLE" not in js, \
            "前端不许硬编码任何一个心码 —— 表只有 adjudicate 那一份"
        assert "dataset.decisions" in js and "only.length === 1" in js, \
            "唯一确定的心码照旧自动预填,判据是「这个心码只配这一个决策」"

    def test_false_positive_button_records_reason_code(self, workspace, server):
        status, _, _ = _decide(server, reason_code="ROUTING_FALSE_POSITIVE")
        assert status == 303
        entry = _ledger(workspace)[0]
        assert entry["reason_code"] == "ROUTING_FALSE_POSITIVE"

    def test_confidence_is_now_opt_in_for_doubt(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert "只在没把握时填" in text, \
            "把握度改成存疑标注 —— 未填不再取消挖掘资格,主动标低才出局"


class TestImprovePage:
    """改进循环页:只读。原话是主体,模型草稿必须看起来像草稿。"""

    def _mine(self, workspace):
        from invoiceloop import improve
        return improve.mine(workspace)

    def test_page_renders_without_any_improve_artifacts(self, workspace, server):
        """还没跑过 mine 也要能打开 —— 空页面比 500 有用。"""
        status, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert status == 200
        assert "改进循环" in text
        assert "没有模型草稿" in text

    def test_reviewer_notes_reach_the_page(self, workspace, server):
        _decide(server, rationale="页面右下角还有一个小写的 total",
                reason_code="ROUTING_FALSE_POSITIVE")
        self._mine(workspace)
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "页面右下角还有一个小写的 total" in text, \
            "复核者原话必须出现在改进页上 —— 这一页就是为了让人读它"

    def test_page_writes_nothing(self, workspace, server):
        """唯一写 active 的入口是 improve promote —— 网页上不许有按钮
        能改策略,只给可复制的命令。"""
        self._mine(workspace)
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert 'action="/improve"' not in text
        assert "还没写过复核意见" in text

    def test_model_draft_is_marked_advisory_with_its_citations(
            self, workspace, server):
        self._mine(workspace)
        (workspace / "improve" / "suggestions.json").write_text(json.dumps({
            "advisory": True, "model": "m", "note_count": 1,
            "suggestions": [{
                "action": "absent_expected", "cohort": {"field": "seller_vat_id"},
                "finding": "美国发票普遍无 VAT", "prediction": "少一类重复确认",
                "confidence": "medium", "cites": [0],
                "cited_notes": [{"doc_id": "d1", "rationale": "页面上没有"}]}],
            "dropped": ["suggestion[1]:引用为空或越界 —— 没出处的建议不收"],
        }, ensure_ascii=False), encoding="utf-8")
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "advisory" in text, "模型草稿要打上 advisory 标"
        assert "页面上没有" in text, "草稿要挂着它读的原话,人才能核"
        assert "没出处的建议不收" in text, "被丢弃的草稿也要看得见"

    def test_overturned_auto_accept_is_shown_first(self, workspace, server):
        run_dir = workspace / "runs" / RUN
        matrix = json.loads((run_dir / "support_matrix.json").read_text("utf-8"))
        row = next(r for r in matrix["rows"] if r["field"] == "total_gross")
        row["route"] = "auto_accept"
        (run_dir / "support_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
        _decide(server, decision="reject", rationale="Fed. I.D. 不是 VAT 号",
                reason_code="WRONG_FIELD_MAPPING")
        self._mine(workspace)
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "被你推翻了" in text, "推翻记录必须出现"
        assert "Fed. I.D. 不是 VAT 号" in text, "你写的原话要摆出来"
        assert text.index("被你推翻了") < text.index("你写过的全部意见"), \
            "收紧信号排在放松线索前面 —— 安全方向优先"


class TestQueueSections:
    """队列必须区分「需要裁决」与「印证行(抽检)」—— 混在一起,
    用户会以为全绿行也要复审 = 假错误(2026-08-03 实测原话)。"""

    def test_queue_splits_required_from_corroborated(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh&filter=all")
        assert "需要裁决" in text and "印证行" in text
        assert text.index("需要裁决") < text.index("印证行"), \
            "需要裁决的行必须排在印证行前面"


class TestGateTooltips:
    """门禁 chip 悬停必须说出:这门查什么 + 这行的状态意味着什么
    (2026-08-03 用户要求,评委也要能看懂)。"""

    def test_chips_carry_plain_language_tooltips_zh(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert "算术一致性:验算" in text
        assert "读图:前沿模型整页读图" in text
        assert "只作警示,不作否决" in text, \
            "读图门的真实立法理由(读者自身静默错误超限)必须同屏(宪章六)"

    def test_chips_carry_plain_language_tooltips_en(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=en")
        assert "Arithmetic: checks net+VAT=gross" in text
        assert "it warns, it never convicts" in text


# ---------------------------------------------------- 读图预填建议层(契约,先测试后实现)

def _vs_row(text: str, field: str) -> str:
    """切出某一字段的整张行卡片(行锚 → 下一行锚),断言才不会串行。"""
    start = text.index(f'id="row-{DOC}-{field}"')
    nxt = text.find('<div class="wb-row" id="', start + 1)
    return text[start: nxt if nxt != -1 else len(text)]


class TestVisionSuggest:
    """行内读图建议:数据源 workspace/vision/answers6.{tag}.tsv。

    钉死的语义(渲染层与 JS 双向遵守):
    - 一致且与 DWS 同值 → wb-vs-value + 「2/2 读者一致」 + 采用按钮;
    - 一致但值在冻结时被拒(绑不进本文档)→ 照常展示建议值,
      但标注「同值冻结时被拒」且绝不给采用按钮 —— 否则建议层架空
      冻结否决权,注入载荷也能借预填按钮进门(82 评 P1-5;
      fixture 里 vision 的 total_net=10.00 正是这个案例:OCR 里没有
      「10.00」,绑定拒绝,事件日志有 draft_binding_rejected);
    - 分歧 → wb-vs-split 列出各读者作答,没有采用按钮;
    - 全弃权 → muted + 「读图也看不清」;
    - 无作答 → 该行根本不出现 wb-vision-suggest;
    - 建议只是表单预填,人没点提交,账本一个字不写(宪章)。
    """

    def test_vs_render_contract_zh(self, workspace, server):
        status, _, text = _req(server, "GET",
                               f"/queue?run={RUN}&lang=zh&filter=all")
        assert status == 200

        gross = _vs_row(text, "total_gross")
        assert 'class="wb-vision-suggest"' in gross
        assert 'wb-vs-value">100.00' in gross, "一致建议要显示建议值"
        assert "2/2 读者一致" in gross
        assert 'wb-vs-adopt" data-value="100.00"' in gross, \
            "一致且未被拒的建议必须有采用按钮,data-value 带建议值"

        net = _vs_row(text, "total_net")
        assert 'wb-vs-value">10.00' in net, "被拒的建议值照常展示(不藏)"
        assert "同值冻结时被拒" in net, \
            "冻结拒绝过的值必须标注 —— 同一卡片写着「冻结时被拒」不能又递按钮"
        assert "wb-vs-adopt" not in net, \
            "冻结否决的值绝不给采用按钮(82 评 P1-5:建议层不许架空冻结)"

        split = _vs_row(text, "issue_date")
        assert "wb-vs-split" in split, "读者分歧要走分歧块,不装作一致"
        assert "Kimi K3=10/31/2020" in split and "Opus 5=11/30/2020" in split, \
            "分歧块要列出各读者(显示名,来自 dws.VISION_READERS)的作答"
        assert "wb-vs-adopt" not in split, "分歧没有可采用的单一值,不许给按钮"

        blind = _vs_row(text, "invoice_number")
        assert "wb-vision-suggest muted" in blind
        assert "读图也看不清" in blind, "全弃权 = 承认看不清,不许伪装成没建议"
        assert "wb-vs-adopt" not in blind

        silent = _vs_row(text, "due_date")
        assert "wb-vision-suggest" not in silent, \
            "无作答的字段不出现建议块 —— 空块是噪音"

    def test_vs_assets_js_adopt_handler(self, workspace, server):
        status, _, js = _req(server, "GET", "/assets.js")
        assert status == 200
        assert "wb-vs-adopt" in js, "JS 必须有 .wb-vs-adopt 点击处理器"
        assert "dataset.rationale" in js, \
            "采用时 rationale 由按钮的 data-rationale 预填(空才填,不覆盖人写的)"
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert 'data-rationale="确认读图建议"' in text, \
            "预填文案由服务器按语言注入按钮属性(JS 保持语言中立)"
        assert "acceptPreset" in js, "既有 acceptPreset 预填逻辑不许被挤掉"

    def test_vs_render_contract_en(self, workspace, server):
        _, _, text = _req(server, "GET",
                          f"/queue?run={RUN}&lang=en&filter=all")
        gross = _vs_row(text, "total_gross")
        assert "2/2 readers agree" in gross

    def test_vs_suggestion_writes_nothing(self, workspace, server):
        status, _, _ = _req(server, "GET",
                            f"/queue?run={RUN}&lang=zh&filter=all")
        assert status == 200
        assert _ledger(workspace) == [], \
            "渲染建议只是表单状态,人没点提交就一个字不写进裁决账本(宪章)"

    def test_vs_value_is_escaped(self, workspace):
        payload = "<script>alert(1)</script>"
        (workspace / "runs" / RUN / "vision" / "answers6.A.tsv").write_text(
            "doc\tfield\tvalue\tprinted_label\tnote\n"
            f"{DOC}\ttotal_gross\t{payload}\tTotal\t\n", encoding="utf-8")
        # 读图作答在 run 内读取,另起一个服务器避免顺序依赖
        from invoiceloop.workbench import make_server

        srv = make_server(workspace, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            _, _, text = _req(srv.server_address[1], "GET",
                              f"/queue?run={RUN}&lang=zh&filter=all")
        finally:
            srv.shutdown()
            srv.server_close()
        assert payload not in text, \
            "读图值原样进 HTML 就是 XSS —— data-value 与显示值都必须转义"
        assert "&lt;script&gt;" in text, \
            "转义后的值必须真的渲染出来,否则这条断言守的是一块没有输出的页面"


# ---------------------------------------------------- Gradescope 风格裁决页(契约,先测试后实现)

def _queue_order(workspace: Path) -> list[dict]:
    """分诊序:需要裁决在前、印证行在后,组内保矩阵原序(与 workbench 同序)。"""
    rows = json.loads(
        (workspace / "runs" / RUN / "support_matrix.json").read_text())["rows"]
    return ([r for r in rows if r["requires_adjudication"]]
            + [r for r in rows if not r["requires_adjudication"]])


def _inject_spans(workspace: Path) -> None:
    """给 total_gross 行造两类 span(冻结绑定 + DWS 引用)与一页假渲染图,
    让 overlay 有东西可画 —— fixture 的 DWS 记录本来不带 source_bboxes。"""
    run = workspace / "runs" / RUN
    reg = json.loads((run / "evidence_span_registry.json").read_text())
    reg.append({"span_id": "ES-T001", "doc_id": DOC, "field": "total_gross",
                "page": 1, "bbox_rel": [0.10, 0.20, 0.30, 0.35],
                "ocr_text": "Total 100.00", "printed_label": "Total",
                "source": "dws_source_bbox", "crop": None})
    reg.append({"span_id": "ES-T002", "doc_id": DOC, "field": "total_gross",
                "page": 1, "bbox_rel": [0.40, 0.50, 0.60, 0.65],
                "ocr_text": "100.00", "printed_label": "Total",
                "source": "dws_source_bbox", "crop": None})
    (run / "evidence_span_registry.json").write_text(
        json.dumps(reg), encoding="utf-8")
    matrix = json.loads((run / "support_matrix.json").read_text())
    for row in matrix["rows"]:
        if row["doc_id"] == DOC and row["field"] == "total_gross":
            row["span_ids"] = ["ES-T001"]
            row["cited_span_ids"] = ["ES-T002"]
    (run / "support_matrix.json").write_text(
        json.dumps(matrix), encoding="utf-8")
    (run / "pages").mkdir(exist_ok=True)
    (run / "pages" / f"{DOC}-1.png").write_bytes(b"\x89PNG fake")


def _set_document_check(workspace: Path, check: dict | None,
                        *, remove_key: bool = False) -> None:
    """Patch only the fixture's frozen gate report; never recompute doctype.

    `remove_key=True` reproduces a pre-doctype run.  A concrete check reproduces
    a current run whose document-level result was frozen by gates.run_gates.
    """
    path = workspace / "runs" / RUN / "gate_report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if remove_key:
        report.pop("document_checks", None)
    else:
        report["document_checks"] = {DOC: check}
    path.write_text(json.dumps(report), encoding="utf-8")


class TestAdjudicatePage:
    """/adjudicate 单槽裁决页:左整页 + overlay,右判定卡 + 表单,底栏导航。

    钉死的契约(布局可演进,这些不许松):
    - 决策表单与队列页同一套字段名、同一个 /decide 端点 —— 裁决语义唯一;
    - span bbox 以绝对定位 overlay div 呈现,不重渲染图片;
    - 冻结绑定、DWS 引用、doctype 字面证据三类框可区分且有图例;
    - doctype 只给上下文,不改按钮、不预选、不删槽;
    - 底栏按分诊序导航上一条/下一条未裁决,进度是真实计数。
    """

    def test_two_column_structure_and_same_form_contract(self, workspace, server):
        status, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross")
        assert status == 200
        assert 'class="wb-adj"' in text, "双栏容器必须在"
        assert "wb-adj-left" in text and "wb-adj-right" in text
        assert "wb-adj-card" in text, "右栏判定卡"
        assert "wb-adj-nav" in text, "底栏导航"
        assert 'action="/decide"' in text and 'name="rationale"' in text \
            and 'name="decision"' in text and 'name="claim_id"' in text, \
            "表单字段名与端点与队列页完全一致 —— 裁决语义唯一入口"
        assert 'name="next" value="adjudicate"' in text, \
            "裁决页表单带 next 标记,提交后服务器推进到下一条未裁决"

    def test_overlay_divs_for_both_span_kinds(self, workspace, server):
        _inject_spans(workspace)
        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh")
        assert "/files/%s/pages/%s-1.png" % (RUN, DOC) in text, \
            "左栏引用整页渲染图(现有图片端点,不重渲染)"
        bind = re.search(r'class="wb-hl wb-hl-bind" style="([^"]+)"', text)
        cited = re.search(r'class="wb-hl wb-hl-cited" style="([^"]+)"', text)
        assert bind and cited, "两类框都要画:冻结绑定 + DWS 引用"
        assert "left:10.000%" in bind.group(1) and "top:20.000%" in bind.group(1), \
            "相对坐标 → CSS 百分比"
        assert "width:20.000%" in bind.group(1)
        assert "left:40.000%" in cited.group(1)
        assert "冻结绑定" in text and "DWS 引用" in text, "图例注明两类框"

    def test_overlay_legend_english(self, workspace, server):
        _inject_spans(workspace)
        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=en")
        assert "frozen binding (span_ids)" in text
        assert "DWS citation (cited_span_ids)" in text

    def test_evidenced_doctype_is_context_and_a_literal_page_overlay(
            self, workspace, server):
        """A frozen pass helps the reviewer recognise the document class,
        while remaining context: it cannot choose or remove a decision.
        """
        _inject_spans(workspace)
        before = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh",
        )[2]
        _set_document_check(workspace, {
            "gate_id": "doctype_evidence",
            "raw_type": "Purchase Order",
            "doc_class": "purchase_order",
            "status": "pass",
            "evidence": {
                "phrase": "purchase order", "page": 0,
                "bbox": [[0.05, 0.06], [0.25, 0.10]], "words": 2,
            },
        })

        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh",
        )

        assert "采购订单" in text and "purchase order" in text
        assert "字段是否适用仍由你判断" in text, \
            "doctype 是复核上下文,不是替人裁 applicability"
        assert "DWS 是否把“100.00”正确映射为总额" in text
        assert "不只是确认这个值出现在页面上" in text, \
            "类别化问题只提醒核对字段映射,不能暗示裁决答案"
        mark = re.search(
            r'class="wb-hl wb-hl-doctype" style="([^"]+)"', text)
        assert mark, "页面字面类型证据必须能在整页上圈出来"
        assert "left:5.000%" in mark.group(1) \
            and "top:6.000%" in mark.group(1)
        assert "单据类型字面证据" in text

        decisions = lambda page: re.findall(
            r'<input type="radio" name="decision" value="([^"]+)"', page)
        assert decisions(text) == decisions(before), \
            "显示 doctype 不许改变按钮集合、预填答案或裁决语义"
        assert not re.search(
            r'<input type="radio" name="decision"[^>]* checked', text), \
            "类别上下文不许替复核者预选答案"

        _, _, queue = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        assert "DWS 是否把“100.00”正确映射为总额" in queue, \
            "队列页和单槽页必须共用同一类条件问题生成器"

    def test_evidenced_doctype_rephrases_an_empty_slot_without_assuming_absence(
            self, workspace, server):
        _set_document_check(workspace, {
            "gate_id": "doctype_evidence",
            "raw_type": "Purchase Order",
            "doc_class": "purchase_order",
            "status": "pass",
            "evidence": {
                "phrase": "purchase order", "page": 0,
                "bbox": [[0.05, 0.06], [0.25, 0.10]], "words": 2,
            },
        })

        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=buyer_name&lang=zh",
        )

        assert "页面字面证据支持这是采购订单" in text
        assert "检查页面是否明确写出买方名称" in text
        assert "不要仅凭单据类别假定缺失" in text
        assert "不要从付款条款或其他字段推算" in text
        assert not re.search(
            r'<input type="radio" name="decision"[^>]* checked', text)

    def test_untrusted_doctype_warns_and_never_draws_evidence(
            self, workspace, server):
        _inject_spans(workspace)
        _set_document_check(workspace, {
            "gate_id": "doctype_evidence", "raw_type": "Contract",
            "doc_class": "contract", "status": "fail", "evidence": None,
        })

        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh",
        )

        assert "合同" in text and "没有页面字面证据" in text
        assert "不得用它判断字段适用性" in text
        assert "wb-hl-doctype" not in text, \
            "模型自报类型没有独立 OCR 支持时不许画成证据"
        assert "页面字面证据支持这是合同" not in text
        assert "请确认该值确实属于总额" in text, \
            "不可信类别必须回退为不带类别的通用问题"

    def test_old_run_says_doctype_was_not_measured(self, workspace, server):
        """The UI must not backfill a new check into an old frozen run."""
        _set_document_check(workspace, None, remove_key=True)

        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh",
        )

        assert "本 run 未执行单据类型检查" in text
        assert "不能补算成当时的结果" in text
        assert "wb-hl-doctype" not in text

    def test_malformed_passing_doctype_fails_closed(self, workspace, server):
        _inject_spans(workspace)
        _set_document_check(workspace, {
            "gate_id": "doctype_evidence", "raw_type": "Mystery",
            "doc_class": "made_up_class", "status": "pass",
            "evidence": {
                "phrase": "mystery", "page": 0,
                "bbox": [[0.05, 0.06], [0.25, 0.10]], "words": 1,
            },
        })

        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh",
        )

        assert "字面证据不完整" in text
        assert "wb-hl-doctype" not in text, \
            "未知类即使伪造 pass 也不许进入受信展示"

    def test_highlights_do_not_cover_text_and_can_be_hidden(self, workspace,
                                                             server):
        """框线画在 bbox 外侧,并提供隐藏框/打开原图两条退路。

        2026-08-08 人工复核实测:极扁的 span 与字同高,即使 1.5px 边框也会
        直接压在数字上。修复不能只再缩一点线宽;描边必须移到框外,且复核者
        随时能看无覆盖的原图。
        """
        _inject_spans(workspace)
        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh")
        assert 'class="wb-hl-toggle"' in text, "页面上要能一键隐藏所有框"
        assert 'class="wb-page-clean"' in text and 'target="_blank"' in text, \
            "JS 失效时也要能打开没有 overlay 的原图"
        assert f'href="/files/{RUN}/pages/{DOC}-1.png"' in text

        _, _, css = _req(server, "GET", "/assets.css")
        bind = re.search(r"[.]wb-hl-bind\s*{([^}]+)}", css, re.S).group(1)
        cited = re.search(r"[.]wb-hl-cited\s*{([^}]+)}", css, re.S).group(1)
        for block in (bind, cited):
            assert "outline" in block and "outline-offset" in block, \
                "描边要移到 bbox 外,不能压住 bbox 里的字"
            assert "background: transparent" in block, "高亮层不再给文字罩色"
            assert "border:" not in block, "bbox 自身不能再向内吃掉文字"
        _, _, js = _req(server, "GET", "/assets.js")
        assert "wb-hl-off" in js and "aria-pressed" in js, \
            "隐藏按钮必须真的切换 overlay,并向辅助技术报告状态"

    def test_nav_progress_and_prev_next(self, workspace, server):
        ordered = _queue_order(workspace)
        cur = ordered[1]  # 取第二条:前后都有未裁决,两个方向都测得到
        _, _, text = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={cur['doc_id']}&field={cur['field']}"
            f"&lang=zh")
        assert f"第 2 / {len(ordered)} 条 · 已裁决 0" in text, \
            "进度是真实计数:当前位次 / 总数 / 已裁决"
        assert "上一条未裁决" in text and "下一条未裁决" in text
        assert f"doc={ordered[0]['doc_id']}&field={ordered[0]['field']}" in text, \
            "上一条按分诊序指向当前之前的未裁决槽位"
        assert f"doc={ordered[2]['doc_id']}&field={ordered[2]['field']}" in text, \
            "下一条按分诊序指向当前之后的未裁决槽位"
        s, _, _ = _decide(server)  # 裁掉 total_gross
        assert s == 303
        _, _, text2 = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={cur['doc_id']}&field={cur['field']}"
            f"&lang=zh")
        assert "已裁决 1" in text2, "裁决后底栏进度照实加一"

    def test_decide_from_adjudicate_advances_to_next_pending(
            self, workspace, server):
        # amount_due 是分诊序队首(需要裁决组),裁它之后必有下一条
        status, headers, _ = _decide(server, field="amount_due",
                                     decision="confirm_absent",
                                     rationale="页面上确实没有",
                                     next="adjudicate")
        assert status == 303
        loc = headers.get("location", "")
        assert "notice=recorded" in loc
        assert loc.startswith("/adjudicate?"), \
            "裁决页提交后推进到下一条未裁决,不是跳回队列"
        assert "field=buyer_name" in loc, "推进到分诊序里的下一条"
        assert "field=amount_due" not in loc, "推进到的不是刚裁掉的槽位"
        entries = _ledger(workspace)
        assert len(entries) == 1 and entries[0]["decision"] == "confirm_absent", \
            "推进只是落点不同,裁决本身一字未差"

    def test_decide_last_pending_falls_back_to_queue(self, workspace, server):
        # total_gross 是分诊序末尾(印证组),其后没有未裁决 → 落回队列
        status, headers, _ = _decide(server, next="adjudicate")
        assert status == 303
        loc = headers.get("location", "")
        assert loc.startswith("/queue?") and "notice=recorded" in loc

    def test_decide_from_queue_still_redirects_to_queue(self, workspace, server):
        status, headers, _ = _decide(server)
        assert status == 303
        assert headers.get("location", "").startswith("/queue?"), \
            "不带 next 的提交(队列页)维持原行为:跳回队列锚点"

    def test_unknown_slot_is_404_with_way_back(self, workspace, server):
        status, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=no_such")
        assert status == 404
        assert f"/queue?run={RUN}" in text, "404 也要给回队列的路"

    def test_no_claim_slot_shows_no_claim_and_absent_options(
            self, workspace, server):
        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=buyer_name")
        assert "(无声明)" in text or "(no claim)" in text
        assert 'value="confirm_absent"' in text, \
            "无声明槽位的决策集与队列页一致:确认缺失/修正/不适用/弃权"

    def test_quick_accept_button_on_claim_rows(self, workspace, server):
        """一键快路(2026-08-05 用户实测反馈):有声明的槽给
        「原值正确,接受并下一条」—— 预填 accept + 理由,一次点击。"""
        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh")
        assert 'wb-quick-ok' in text, "有声明槽位必须有一键接受"
        assert 'data-decision="accept"' in text
        assert 'data-rationale="与页面一致"' in text

    def test_quick_draft_button_on_rejected_rows(self, workspace, server):
        """草稿被冻结拒的槽(无声明):快路 = correct 预填被拒草稿的值 ——
        绑定失败是机械门槛,人看页面确认后对就是对人证成立。"""
        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_net&lang=zh")
        assert 'wb-quick-ok' in text, "被拒草稿槽位必须有「采用被拒草稿」快路"
        assert 'data-decision="correct"' in text
        assert 'data-value="10.00"' in text, "预填值 = 被拒草稿的值"
        assert "采用被拒草稿" in text

    def test_multipage_doc_has_page_tabs(self, workspace, server):
        """多页文档:页码切换签必须出现,?page=2 必须真的换页
        (2026-08-05 用户实测:003cc916 两页,第二页够不着)。"""
        import subprocess
        run_dir = workspace / "runs" / RUN
        pages = run_dir / "pages"
        pages.mkdir(exist_ok=True)
        # 造第二页占位(内容不限,存在性驱动页签)
        if not (pages / f"{DOC}-1.png").exists():
            (pages / f"{DOC}-1.png").write_bytes(b"\x89PNG")
        (pages / f"{DOC}-2.png").write_bytes(b"\x89PNG")
        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh")
        assert 'wb-page-tab' in text, "多页文档必须有页码签"
        assert f"{DOC}-1.png" in text
        _, _, text2 = _req(
            server, "GET",
            f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh&page=2")
        assert f'class="wb-page" src="/files/{RUN}/pages/{DOC}-2.png"' in text2, \
            "?page=2 左栏主图必须换到第二页"
        assert f'class="wb-page" src="/files/{RUN}/pages/{DOC}-1.png"' not in text2

    def test_adopt_button_scope_on_adjudicate_page(self, workspace, server):
        """裁决页上的「采用建议」必须找得到同页表单(JS 作用域契约:
        按钮在 .wb-adj-card 里,不在 .wb-row 里 —— 2026-08-05 实测
        点了没反应,handler 只认队列页结构)。"""
        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_net&lang=zh")
        if "wb-vs-adopt" in text:
            assert 'class="wb-adj-card"' in text
            assert 'form class="decide"' in text or "form class=\"decide\"" in text
            assert 'name="decision"' in text, \
                "采用按钮所在页必须有可预填的裁决表单"

    def test_why_block_skips_clean_placeholder(self, workspace, server):
        """reason_codes 里 CLEAN 是占位不是原因 —— QA_SAMPLE 槽的
        「为什么在队列里」必须说是抽检,不许因为 CLEAN 在前就不显示
        (2026-08-06 用户实测:全绿票被问,卡片却没解释)。"""
        from invoiceloop.workbench import Workbench
        wb = Workbench.__new__(Workbench)
        row = {"requires_adjudication": True,
               "reason_codes": ["CLEAN", "QA_SAMPLE:policy_accepted_tier1"]}
        html = wb._why_html("zh", row)
        assert "随机抽检" in html, "CLEAN 占位不许吞掉 QA_SAMPLE 的入队原因"
        row2 = {"requires_adjudication": True, "reason_codes": ["INFRA_BLOCKED"]}
        assert "OCR" in wb._why_html("zh", row2)
        row3 = {"requires_adjudication": False, "reason_codes": ["CLEAN"]}
        assert wb._why_html("zh", row3) == "", "不在队列里的槽没有入队原因块"

    def test_lang_toggle_preserves_query_params(self, workspace, server):
        """语言切换不许丢 run/doc/field —— 裸 ?lang= 会把裁决页切成
        空槽 404(2026-08-06 用户实测)。"""
        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross&lang=zh")
        m = re.search(r'class="wb-lang"><a href="([^"]+)"', text)
        assert m, "语言切换链接必须在"
        href = m.group(1)
        assert f"run={RUN}" in href and f"doc={DOC}" in href \
            and "field=total_gross" in href and "lang=en" in href, \
            f"切换链接必须保留当前槽位参数,实际:{href}"


@pytest.fixture
def scoped_server(workspace):
    """只准复核两个槽,且顺序故意与全队列相反。"""
    from invoiceloop.workbench import make_server

    ordered = _queue_order(workspace)
    chosen = [ordered[-1], ordered[0]]
    slots = [f"{r['doc_id']}|{r['field']}" for r in chosen]
    scope = workspace / "review-scope.json"
    scope.write_text(json.dumps({"slots": slots}), encoding="utf-8")
    srv = make_server(workspace, 0, review_scope=scope)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], chosen, ordered[1]
    srv.shutdown()
    srv.server_close()


class TestReviewScope:
    """实验抽样是写权限边界,不只是另一张静态索引页。

    2026-08-08 原工作台仍在 1000 槽 run 上导航,导致 H2 留下 1 条样本外
    裁决。scope 必须同时约束队列、上一条/下一条和 POST 写入口;只隐藏链接
    仍可由旧标签页或手改 URL 越界。
    """

    def test_queue_and_navigation_use_exact_scope_order(self, workspace,
                                                         scoped_server):
        port, chosen, outside = scoped_server
        _, _, queue = _req(port, "GET", f"/queue?run={RUN}&lang=zh")
        assert "已复核 0 / 2" in queue, "分母必须是抽样槽数,不是整个 run"
        for row in chosen:
            assert f'row-{row["doc_id"]}-{row["field"]}' in queue
        assert f'row-{outside["doc_id"]}-{outside["field"]}' not in queue

        first, second = chosen
        _, _, page = _req(
            port, "GET",
            f"/adjudicate?run={RUN}&doc={first['doc_id']}"
            f"&field={first['field']}&lang=zh")
        assert "第 1 / 2 条 · 已裁决 0" in page
        assert f"doc={second['doc_id']}&field={second['field']}" in page, \
            "下一条必须按 scope 文件顺序走,不能掉回全 run 的分诊序"
        assert "限定复核范围:2 槽" in page, "页面要持续告诉人当前有写入边界"

    def test_manual_get_and_post_outside_scope_are_blocked(self, workspace,
                                                            scoped_server):
        port, _, outside = scoped_server
        path = (f"/adjudicate?run={RUN}&doc={outside['doc_id']}"
                f"&field={outside['field']}&lang=zh")
        status, _, text = _req(port, "GET", path)
        assert status == 409 and "限定复核范围" in text

        form = {"run": RUN, "doc": outside["doc_id"],
                "field": outside["field"], "claim_id": "",
                "decision": "abstain", "corrected_value": "",
                "rationale": "旧标签页", "adjudicator": "alice",
                "supersedes": "", "lang": "zh"}
        status, _, text = _req(
            port, "POST", "/decide", body=urlencode(form).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert status == 409 and "限定复核范围" in text
        assert _ledger(workspace) == [], "越界 POST 不能留一行账本"

    def test_submit_advances_within_scope(self, workspace, scoped_server):
        port, chosen, _ = scoped_server
        first, second = chosen
        assert first["field"] == "total_gross", \
            "fixture 依赖现有队尾的有声明槽,若排序变了请显式重选"
        status, headers, _ = _decide(port, next="adjudicate")
        assert status == 303
        loc = headers["location"]
        assert f"field={second['field']}" in loc
        assert "field=total_gross" not in loc
        assert len(_ledger(workspace)) == 1

    def test_scope_loader_rejects_duplicates(self, workspace):
        from invoiceloop.workbench import load_review_scope

        path = workspace / "bad-scope.json"
        path.write_text(json.dumps({"slots": ["a|b", "a|b"]}),
                        encoding="utf-8")
        with pytest.raises(ValueError, match="重复"):
            load_review_scope(path)

    def test_scope_run_mismatch_is_blocking(self, workspace):
        from invoiceloop.workbench import make_server

        scope = workspace / "wrong-run-scope.json"
        scope.write_text(json.dumps({"slots": ["missing-doc|amount_due"]}),
                         encoding="utf-8")
        srv = make_server(workspace, 0, review_scope=scope)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            status, _, text = _req(
                srv.server_address[1], "GET", f"/queue?run={RUN}&lang=zh")
        finally:
            srv.shutdown()
            srv.server_close()
        assert status == 409 and "当前 run 不存在" in text
        assert _ledger(workspace) == [], \
            "scope 与 run 对不上是阻断,不能退回全队列或偷偷忽略缺口"


class TestQueueSearch:
    def test_search_filters_by_doc_and_field(self, workspace, server):
        _, _, text = _req(server, "GET", f"/queue?run={RUN}&q={DOC[:6]}&lang=zh")
        assert DOC[:8] in text
        _, _, text2 = _req(server, "GET", f"/queue?run={RUN}&q=total_gross&lang=zh")
        assert "total_gross" in text2
        _, _, text3 = _req(server, "GET", f"/queue?run={RUN}&q=zzz-no-match&lang=zh")
        assert "total_gross" not in text3, "搜不到就空,不许退回全量"
        # 搜索状态在 chip 链接里保持(翻 filter 不丢搜索词)
        _, _, text4 = _req(server, "GET", f"/queue?run={RUN}&q={DOC[:6]}&lang=zh")
        assert f"q={DOC[:6]}" in text4

    def test_adjudicate_evidence_collapsed_queue_open(self, workspace, server):
        """证据区:队列页默认摊开(2026-08-03 反馈),裁决页默认收起
        (2026-08-06 反馈)—— 两处场景各自默认。"""
        _, _, queue_text = _req(server, "GET", f"/queue?run={RUN}&filter=all")
        assert '<details class="wb-evidence" open>' in queue_text
        _, _, adj_text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross")
        assert '<details class="wb-evidence">' in adj_text
        assert '<details class="wb-evidence" open>' not in adj_text


def _imp_post(port: int, path: str, form: dict) -> tuple[int, dict, str]:
    return _req(port, "POST", path, body=urlencode(form).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"})


class TestImproveLoopPage:
    """改进循环页的写操作:采纳→评测→晋升,三级摩擦各自到位。

    分级是刻意的(v0.2 §12 的人工闸门不能被一个按钮做成摆设):
    adopt/evaluate 写的是候选,对 active harness 零影响;promote 会改变
    之后每一张发票的路由,所以要署名 + 理由 + 时间,少一样就拒。
    """

    def _adopt(self, port, **over) -> tuple[int, dict, str]:
        form = {"run": RUN, "lang": "zh", "kind": "absent_expected",
                "c_doc_class": "invoice", "c_field": "seller_vat_id",
                "finding": "12 份 invoice 里反复 confirm_absent",
                "prediction": "负载下降;风险是把真有值的槽误判成缺席"}
        form.update(over)
        return _imp_post(port, "/improve/adopt", form)

    def _adopt_accept(self, port, **over) -> tuple[int, dict, str]:
        """自动放行候选 —— 晋升路径的测试用它。

        类别缺席候选在没有真值的 workspace 上会被 Gate 2 硬拒(见
        test_class_absence_candidate_cannot_be_promoted_without_truth),
        拿它测「晋升记下了人的原话」只会测到拒绝,测不到记录。
        """
        form = {"run": RUN, "lang": "zh",
                "kind": "auto_accept", "c_field": "total_gross",
                "c_strength": "corroborated", "cohort_id": "AC-GROSS",
                "finding": "多方印证的含税额从没被改过",
                "prediction": "负载下降;风险是放过一个错值"}
        form.update(over)
        return _imp_post(port, "/improve/adopt", form)

    def test_adopt_writes_a_candidate_and_evaluates_it(self, workspace, server):
        status, headers, _ = self._adopt(server)
        assert status == 303 and "notice=proposed" in headers["location"]
        cand = workspace / "harnesses" / "HAR-0002"
        assert (cand / "routing_policy.json").exists()
        assert (workspace / "improve" / "eval_HAR-0002.json").exists(), \
            "采纳即评测 —— 人要在同一屏看到代价,不是只看到改善"

    def test_adopt_does_not_change_the_active_harness(self, workspace, server):
        """这是整套分级摩擦的根据:采纳是安全的,因为它什么都没生效。"""
        from invoiceloop.harness import load_active

        before = load_active(workspace)["harness_id"]
        self._adopt(server)
        assert load_active(workspace)["harness_id"] == before
        assert not (workspace / "improve" / "promotions").exists()

    def test_adopt_refuses_a_nameless_cohort(self, workspace, server):
        status, _, _ = self._adopt_accept(server, cohort_id="")
        assert status == 400

    def test_adopt_refuses_an_absence_rule_with_no_document_class(
            self, workspace, server):
        """缺席规则的名字由 Python 从类别×字段生成,所以界面不给起名框 ——
        但没给类别就必须当场拒:不带类别的缺席规则对所有单据生效。"""
        status, _, body = self._adopt(server, c_doc_class="")
        assert status == 400
        assert "哪一类单据" in body

    def test_adopt_refuses_a_cohort_with_no_features(self, workspace, server):
        status, _, _ = self._adopt(server, c_field="")
        assert status == 400, "没有 cohort 特征就没有可路由的东西"

    def test_promote_requires_a_name_and_a_reason(self, workspace, server):
        # 用一个**能**晋升的候选:否则 400 可能来自安全门而不是缺署名,
        # 这条断言就测不到它要测的东西了。
        self._adopt_accept(server)
        base = {"run": RUN, "lang": "zh", "candidate": "HAR-0002",
                "approved_at": "2026-08-06T12:00:00Z"}
        no_name, _, _ = _imp_post(server, "/improve/promote",
                                  {**base, "approved_by": "",
                                   "rationale": "r"})
        no_why, _, _ = _imp_post(server, "/improve/promote",
                                 {**base, "approved_by": "alice",
                                  "rationale": ""})
        assert no_name == 400 and no_why == 400, \
            "网页入口不许比 CLI 松:署名与理由都是硬要求"

    def test_class_absence_candidate_cannot_be_promoted_without_truth(
            self, workspace, server):
        """会自动判缺席的规则,拿不到真值评分就不许生效 —— 硬拒,不是警告。

        一个被误判成缺席的槽再也不会有人看,所以它没有 QA 兜底可依赖。
        SEALED-3 主臂就栽在这里:规则本身「看起来只减负」,代价是一个真有
        值的税号被静默吞掉(docs/SEALED3_RESULTS.md §4)。
        """
        self._adopt(server)
        status, _, body = _imp_post(server, "/improve/promote", {
            "run": RUN, "lang": "zh", "candidate": "HAR-0002",
            "approved_by": "alice", "rationale": "我认了这个风险",
            "approved_at": "2026-08-06T12:00:00Z"})
        assert status == 400, "署名和理由齐全也不行 —— 人签不掉一个没测过的缺席规则"
        assert "真值评分" in body
        from invoiceloop.harness import load_active
        assert load_active(workspace)["harness_id"] == "HAR-0001", \
            "被拒的晋升不许改动 active harness"

    def test_promote_records_the_humans_own_words(self, workspace, server):
        self._adopt_accept(server)
        status, headers, _ = _imp_post(server, "/improve/promote", {
            "run": RUN, "lang": "zh", "candidate": "HAR-0002",
            "approved_by": "alice", "rationale": "接受 QA 抽检的残余风险",
            "approved_at": "2026-08-06T12:00:00Z"})
        assert status == 303 and "notice=promoted" in headers["location"]
        rec = json.loads((workspace / "improve" / "promotions"
                          / "PROM-0001.json").read_text(encoding="utf-8"))
        assert rec["approved_by"] == "alice"
        assert rec["rationale"] == "接受 QA 抽检的残余风险"
        from invoiceloop.harness import load_active
        assert load_active(workspace)["harness_id"] == "HAR-0002"

    def test_page_shows_the_gate_verdict_and_the_cost_side(self, workspace,
                                                           server):
        self._adopt(server)
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "需要你过目的字段" in text, "试算结果必须摆出来"
        # 无真值的 workspace:不许显示「安全检查通过」(宪章四:没跑 ≠ 通过)。
        # 类别缺席规则更进一步 —— 它不是「没跑,结论未知」,而是**明确拒绝**:
        # 一条会自动判缺席的规则,没拿到真值评分就不许生效。
        assert "安全检查不通过" in text
        assert "未取得 QA 前真值评分" in text, "拒绝要说清是哪一关没过"
        assert "安全检查通过" not in text
        # 工程标识不在正文里,收进技术细节折叠区
        assert "技术细节" in text and "HAR-0002" in text

    def test_unscoreable_non_absence_candidate_still_says_not_run(
            self, workspace, server):
        """没有真值时,**非**缺席候选仍是「没跑」而不是「拒绝」。

        两者不能混:自动放行错值有 QA 抽检兜底,自动判缺席没有 ——
        缺席一旦判错,那个槽再也不会有人看。所以只有后者升级成硬拒绝。
        """
        self._adopt(server, kind="auto_accept", c_doc_class="",
                    c_strength="corroborated", cohort_id="AC-GROSS")
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "安全检查没跑" in text
        assert "安全检查通过" not in text

    def test_schema_candidate_is_not_auto_evaluated(self, workspace, server):
        """schema 候选要真重抽才评得了,那要花钱 —— 不许替人按下去。"""
        status, headers, _ = _imp_post(server, "/improve/adopt-schema", {
            "run": RUN, "lang": "zh", "field": "due_date",
            "description": "Payment due date, or the date implied by terms.",
            "finding": "抽取器什么都没返回", "prediction": "缺值下降;可能编日期"})
        assert status == 303 and "notice=proposed" in headers["location"]
        assert (workspace / "harnesses" / "HAR-0002"
                / "extraction_schema.json").exists()
        assert not (workspace / "improve" / "eval_HAR-0002.json").exists()
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "会产生费用" in text, "要花钱的那一步必须先说清再让人点"

    def test_stale_lineage_candidate_gets_no_promote_button(self, workspace,
                                                            server):
        """谱系对不上 active 的候选:promote 必拒,页面就不该给按钮。

        造法:两个候选都从 HAR-0001 派生,晋升掉其中一个 —— 另一个的 parent
        就成了旧 active。这是真实会出现的状态(第一次在工作台上跑通闭环时,
        HAR-0002/0003 正是这样挂在页面上,还各带一个注定被拒的晋升表单)。
        """
        self._adopt_accept(server)                 # HAR-0002,parent=HAR-0001
        self._adopt_accept(server, c_field="total_net",
                           cohort_id="AC-NET")     # HAR-0003,parent=HAR-0001
        _imp_post(server, "/improve/promote", {
            "run": RUN, "lang": "zh", "candidate": "HAR-0002",
            "approved_by": "alice", "rationale": "r",
            "approved_at": "2026-08-06T12:00:00Z"})
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "基于一版更早的规则" in text, \
            "HAR-0003 的上游已经不是当前规则了,必须说人话讲清楚"
        _, _, tail = text.partition("HAR-0003")
        assert "/improve/promote" not in tail, \
            "注定被拒的操作不该给按钮 —— 让人填完表单再吃 400 是坏交互"


class TestModelDraftRendering:
    """模型草稿 → 采纳表单的渲染。suggestions.json 在这里是显式 fixture,
    不是真实模型输出 —— 测的是页面怎么呈现草稿,不是模型说得对不对。"""

    def _write(self, workspace, suggestions, dropped=()):
        (workspace / "improve").mkdir(exist_ok=True)
        (workspace / "improve" / "suggestions.json").write_text(
            json.dumps({"advisory": True, "model": "m",
                        "suggestions": suggestions,
                        "dropped": list(dropped)}, ensure_ascii=False),
            encoding="utf-8")

    def test_cohort_draft_renders_an_editable_adopt_form(self, workspace,
                                                         server):
        self._write(workspace, [{
            "kind": "cohort", "action": "absent_expected",
            "cohort": {"field": "seller_vat_id"},
            "finding": "模型读出来的事实", "prediction": "模型的预测",
            "confidence": "medium", "cites": [0],
            "cited_notes": [{"rationale": "页面上没有"}]}])
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert 'action="/improve/adopt"' in text
        assert 'name="c_field" value="seller_vat_id"' in text
        assert "页面上没有" in text, "被引用的原话要跟着草稿一起显示"
        # 模型的话是**预填**,不是既成事实 —— 人必须能改
        assert "<textarea" in text and "模型读出来的事实" in text

    def test_schema_draft_lets_the_human_edit_the_description(self, workspace,
                                                              server):
        self._write(workspace, [{
            "kind": "schema", "action": "schema_description",
            "field": "due_date",
            "description": "Payment due date, or the date implied by terms.",
            "finding": "f", "prediction": "p", "confidence": "low",
            "cites": [0], "cited_notes": [{"rationale": "页面上没有"}]}])
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert 'action="/improve/adopt-schema"' in text
        assert "the date implied by terms" in text
        assert 'name="description"' in text, "描述必须可改,签字的是人"

    def test_revoke_draft_gets_no_button_because_there_is_no_such_path(
            self, workspace, server):
        """宪章四:做不了要说,不许给一个假按钮。"""
        self._write(workspace, [{
            "kind": "cohort", "action": "revoke",
            "cohort": {"field": "seller_vat_id"},
            "finding": "f", "prediction": "p", "confidence": "high",
            "cites": [0], "cited_notes": [{"rationale": "推翻过一次"}]}])
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "收回一条已经生效的规则" in text
        assert 'action="/improve/adopt"' not in text

    def test_rejected_drafts_are_shown_not_swallowed(self, workspace, server):
        self._write(workspace, [], dropped=["suggestion[0]:引用为空 —— 不收"])
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "被挡下的 AI 建议" in text and "引用为空" in text

    def test_draft_text_is_escaped(self, workspace, server):
        """模型输出直接进 HTML 就是 XSS —— 和人写的 rationale 同一条纪律。"""
        self._write(workspace, [{
            "kind": "cohort", "action": "auto_accept",
            "cohort": {"field": "seller_name"},
            "finding": "<script>alert(1)</script>", "prediction": "p",
            "confidence": "low", "cites": [0],
            "cited_notes": [{"rationale": "x"}]}])
        _, _, text = _req(server, "GET", f"/improve?run={RUN}&lang=zh")
        assert "<script>alert(1)</script>" not in text
        assert "&lt;script&gt;" in text


class TestRejectedSubmissionKeepsTypedInput:
    """提交被拒不许丢内容(2026-08-08 用户实测)。

    原状:组合自洽校验拒掉 → 整页「阻断」+ 一个回队列链接,复核者写的
    rationale / corrected_value / adjudicator 全部重打。一轮 200 槽里这是
    实打实的成本,而且诱导人写更短的理由 —— rationale 正是 improve.mine
    唯一原样带出去给人读的东西(improve.py 的 cohort notes)。

    钉死的契约:被拒 → 回到**该槽的裁决页**(不是消息页),已填内容原样
    在表单里,错误显示在表单旁边,账本一行不落。
    """

    def _reject(self, port: int, **over) -> tuple[int, dict, str]:
        """触发组合自洽拒绝:弃权 + 上一次残留的 CONFIRMED_ABSENT。"""
        form = {"next": "adjudicate", "decision": "abstain",
                "reason_code": "CONFIRMED_ABSENT",
                "rationale": "这一栏印得太糊,读不出来是 8 还是 B",
                "adjudicator": "bob"}
        form.update(over)
        return _decide(port, **form)

    def test_typed_input_survives_a_rejected_submission(self, workspace, server):
        status, _, text = self._reject(server)
        assert status == 400
        assert _ledger(workspace) == [], "被拒的裁决一行都不许落盘"
        assert 'action="/decide"' in text and 'name="rationale"' in text, \
            "被拒后要回到能直接改完再交的裁决页,不是只有一个链接的消息页"
        assert "这一栏印得太糊,读不出来是 8 还是 B" in text, \
            "复核者写的理由必须原样还在表单里 —— 重打的代价会把理由写短"
        assert 'name="adjudicator"' in text and 'value="bob"' in text, \
            "署名也是人打的,一并保留"

    def test_corrected_value_survives_too(self, workspace, server):
        status, _, text = self._reject(
            server, decision="correct", corrected_value="INV-4711")
        assert status == 400
        assert 'value="INV-4711"' in text, "修正值是最不该让人重打的一格"

    def test_the_rejected_decision_comes_back_selected(self, workspace, server):
        status, _, text = self._reject(server)
        assert status == 400
        radio = re.search(r'<input type="radio" name="decision" '
                          r'value="abstain"[^>]*>', text)
        assert radio and "checked" in radio.group(0), \
            "选过的决策要回来 —— 否则人得重新想一遍自己刚才判的是什么"

    def test_rejected_form_is_marked_so_js_does_not_wipe_it(self, workspace,
                                                            server):
        status, _, text = self._reject(server)
        assert status == 400
        assert 'data-rejected="1"' in text, \
            "回填的表单要有标记:载入时的心码过滤必须跳过它,"\
            "否则报错说「你选的是 CONFIRMED_ABSENT」而下拉已经空了"
        _, _, js = _req(server, "GET", "/assets.js")
        assert "rejected" in js, "JS 要认这个标记"

    def test_still_400_and_still_no_write_for_other_rejections(self, workspace,
                                                              server):
        """回填是交互,不是放水:其他校验拒绝照样 400、照样不写账本。"""
        status, _, text = _decide(server, decision="correct",
                                  corrected_value="", next="adjudicate")
        assert status == 400
        assert _ledger(workspace) == []
        assert "corrected_value" in text or "修正值" in text


class TestReasonCodeIsBoundToDecision:
    """心码下拉必须跟着决策走(2026-08-08 用户实测)。

    界面已按槽位裁剪决策按钮,心码却一直是全集 —— 等于允许人拼出一个
    必然被服务器拒掉的组合。绑定规则只有一份:adjudicate.REASON_CODE_COMBOS。
    渲染层从那里读,前端不许复制第二份(两处定义会漂移)。
    """

    def test_options_declare_the_decisions_they_are_allowed_with(
            self, workspace, server):
        from invoiceloop.adjudicate import REASON_CODE_COMBOS
        from invoiceloop.feedback import REASON_CODES

        _, _, text = _req(
            server, "GET", f"/adjudicate?run={RUN}&doc={DOC}&field=total_gross")
        options = dict(re.findall(
            r'<option value="([A-Z_]+)"[^>]*data-decisions="([^"]*)"', text))
        assert set(options) == set(REASON_CODES), \
            "每个心码 option 都要显式声明允许的决策(不受限的声明为空)"
        for code, allowed in REASON_CODE_COMBOS.items():
            assert set(options[code].split()) == set(allowed), \
                f"{code} 的允许决策必须与 adjudicate 的 combo 表逐字一致"
        unrestricted = set(REASON_CODES) - set(REASON_CODE_COMBOS)
        assert all(options[c] == "" for c in unrestricted), \
            "combo 表没管的心码不许在界面上凭空多一条限制"

    def test_the_table_is_not_duplicated_in_the_workbench(self):
        """反漂移:工作台不许自己再写一份 combo 表。"""
        source = (Path(__file__).resolve().parents[1] / "invoiceloop"
                  / "workbench.py").read_text(encoding="utf-8")
        assert "REASON_CODE_COMBOS" in source, "渲染层要从 adjudicate 读"
        assert '"CONFIRMED_ABSENT": {"confirm_absent"}' not in source, \
            "第二份 combo 表就是漂移的起点"

    def test_js_filters_options_by_the_declared_attribute(self, workspace,
                                                          server):
        _, _, js = _req(server, "GET", "/assets.js")
        assert "decisions" in js, \
            "JS 只能读 option 上的 data-decisions,不许内置自己的表"
        assert "dataset.decisions" in js


class TestComboErrorSpeaksInterfaceWords:
    """报错要用复核者在界面上看得见的词(2026-08-08 用户实测)。

    原文案:`reason_code CONFIRMED_ABSENT 只能搭配 ['confirm_absent'],
    收到 abstain` —— Python list repr + 内部字段名 + 英文常量。界面上写的
    是「弃权」「确认缺失」,对不上号。

    纪律:adjudicate 抛的**原始异常文本不改**(给 API 调用方与日志,而且
    有测试钉着),改的是工作台怎么显示它。
    """

    def test_error_uses_the_words_on_the_buttons(self, workspace, server):
        status, _, text = _decide(
            server, next="adjudicate", decision="abstain",
            reason_code="CONFIRMED_ABSENT", rationale="读不出来", lang="zh")
        assert status == 400
        assert "弃权" in text and "确认缺失" in text, \
            "决策与心码都要说界面上的词"
        assert "['confirm_absent']" not in text, "Python 的 list repr 不进界面"
        assert "reason_code CONFIRMED_ABSENT 只能搭配" not in text, \
            "内部字段名与英文常量不进界面"

    def test_error_is_english_on_the_english_page(self, workspace, server):
        status, _, text = _decide(
            server, next="adjudicate", decision="abstain",
            reason_code="CONFIRMED_ABSENT", rationale="illegible", lang="en")
        assert status == 400
        assert "Abstain" in text and "Confirm absent" in text
        assert "['confirm_absent']" not in text

    def test_core_error_text_is_untouched(self, workspace):
        """API 调用方与日志看的那句话一个字不改。"""
        with pytest.raises(ValueError) as exc:
            adjudicate.append_adjudication(
                workspace / "runs" / RUN, claim_id=None, doc_id=DOC,
                field="total_gross", decision="abstain", rationale="r",
                adjudicator="a", decided_at="2026-08-08T00:00:00+00:00",
                reason_code="CONFIRMED_ABSENT")
        assert "reason_code CONFIRMED_ABSENT 只能搭配 ['confirm_absent']" \
            in str(exc.value)


class TestFeedbackLabelsStateTheConsequence:
    """两条误导性标签(2026-08-08):说了「可选」「什么时候填」,没说
    填不填会发生什么 —— 而两者都决定这条意见进不进挖掘池
    (feedback.actionable)。只改文案,不改行为。"""

    def test_reason_code_is_not_advertised_as_optional(self, workspace, server):
        _, _, zh = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        label = re.search(r'原因码[^<]*', zh).group(0)
        assert "可选" not in label, \
            "不填这条事件 actionable 就是 false,整条被 mine 排除 —— 不是可选"
        assert "改进循环" in label, "要说清不填的后果"
        _, _, en = _req(server, "GET", f"/queue?run={RUN}&lang=en")
        label_en = re.search(r'Reason code[^<]*', en).group(0)
        assert "optional" not in label_en.lower()
        assert "improvement loop" in label_en.lower()

    def test_confidence_label_says_what_low_does(self, workspace, server):
        _, _, zh = _req(server, "GET", f"/queue?run={RUN}&lang=zh")
        label = re.search(r'标注存疑[^<]*', zh).group(0)
        assert "改进循环" in label, "标 low 会把这条事件踢出挖掘池,要说出来"
        _, _, en = _req(server, "GET", f"/queue?run={RUN}&lang=en")
        label_en = re.search(r'Flag doubt[^<]*', en).group(0)
        assert "improvement loop" in label_en.lower()
