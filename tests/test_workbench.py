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


class TestAdjudicatePage:
    """/adjudicate 单槽裁决页:左整页 + overlay,右判定卡 + 表单,底栏导航。

    钉死的契约(布局可演进,这些不许松):
    - 决策表单与队列页同一套字段名、同一个 /decide 端点 —— 裁决语义唯一;
    - span bbox 以绝对定位 overlay div 呈现,不重渲染图片;
    - 冻结绑定(span_ids)与 DWS 引用(cited_span_ids)两类框可区分且有图例;
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
