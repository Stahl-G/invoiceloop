"""seal(DWS 签名封缄)与 verify 第五层的契约测试。

钉死的语义:
- seal 是纯增量:原 bundle 成员逐字节保留,MANIFEST 不动;
- 无 attestation 的包:signature = None,不是失败;
- 封缄后 MANIFEST 被换 → signature False;
- 签名 PDF 内容不含该摘要 → False;
- 缺验签依赖时不许报 True(宪章四:验不了 = None + 注明)。
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from invoiceloop import adjudicate, ocr, seal
from invoiceloop.pipeline import run as pipeline_run
from tests.conftest import pin_corpus

DOC = "acme-001"


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
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
    adjudicate.build_audit_bundle(out)
    yield out
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


def _fake_post(url, *, files, headers):
    """/sign 替身:回一份「签了名」的 PDF —— 内容嵌 attestation 文本
    (内容检查能过;不是真 CMS,密码学层会走依赖缺失/解析失败分支)。"""
    att_pdf = files["file"][1]
    return 200, att_pdf + b"\n% signed-by-fake-dws\n"


def _unzip(path):
    with zipfile.ZipFile(path) as zf:
        return {i.filename: zf.read(i.filename) for i in zf.infolist()}


def _rezip(path, items):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in items.items():
            zf.writestr(name, data)


class TestSeal:
    def test_seal_is_pure_overlay(self, run_dir):
        sealed = seal.seal_run(run_dir, _post=_fake_post)
        original = _unzip(run_dir / "audit_bundle.zip")
        items = _unzip(sealed)
        for name, data in original.items():
            assert items[name] == data, f"原成员 {name} 必须逐字节保留"
        assert set(items) == set(original) | set(seal.SEAL_MEMBERS)
        att = json.loads(items["attestation.json"])
        assert att["manifest_sha256"] == hashlib.sha256(
            original["MANIFEST.sha256"]).hexdigest()
        assert att["signature_profile"] == "cades/b-lt"

    def test_unsealed_bundle_signature_none(self, run_dir):
        report = adjudicate.verify_bundle(run_dir / "audit_bundle.zip")
        assert report["ok"], report["failures"]
        assert report["layers"]["signature"] is None
        assert any("未封缄" in n for n in report["notes"])

    def test_sealed_bundle_members_and_signature(self, run_dir):
        sealed = seal.seal_run(run_dir, _post=_fake_post)
        report = adjudicate.verify_bundle(sealed)
        assert report["layers"]["members"] is True, \
            "封缄外层信封按格式容忍,members 层照过"
        if seal.crypto_available():
            # 假 CMS:验签必须失败,不许判过
            assert report["layers"]["signature"] is False
        else:
            assert report["layers"]["signature"] is None, \
                "缺验签依赖 → None + 注明,不报 True(宪章四)"
            assert any("验签" in n for n in report["notes"])

    def test_manifest_swap_after_seal_caught(self, run_dir):
        sealed = seal.seal_run(run_dir, _post=_fake_post)
        items = _unzip(sealed)
        # 攻击:换 MANIFEST 里一行哈希(成员字节不动,members 层会抓;
        # 就算攻击者同步修了成员,attestation 里的摘要也对不上)
        lines = items["MANIFEST.sha256"].decode().splitlines()
        first = lines[0].split("  ", 1)
        lines[0] = ("0" * 64) + "  " + first[1]
        items["MANIFEST.sha256"] = ("\n".join(lines) + "\n").encode()
        _rezip(sealed, items)
        report = adjudicate.verify_bundle(sealed)
        assert report["layers"]["signature"] is False, \
            "封缄后 MANIFEST 被换,签名层必须抓住"
        assert not report["ok"]

    def test_signed_pdf_without_hash_caught(self, run_dir):
        sealed = seal.seal_run(run_dir, _post=_fake_post)
        items = _unzip(sealed)
        items["attestation.signed.pdf"] = b"%PDF-1.4 fake signature"
        _rezip(sealed, items)
        report = adjudicate.verify_bundle(sealed)
        assert report["layers"]["signature"] is False
        assert any("签的不是这份" in f for f in report["failures"])


class TestAttestationPdf:
    def test_pdf_is_deterministic_and_valid(self):
        _, att = seal.build_attestation.__wrapped__ if False else (None, None)
        a1 = seal.render_attestation_pdf(b'{"a": 1}\n')
        a2 = seal.render_attestation_pdf(b'{"a": 1}\n')
        assert a1 == a2, "同输入同字节(封缄链路的确定性)"
        assert a1.startswith(b"%PDF-1.4\n")
        assert b"xref" in a1 and b"%%EOF" in a1
        assert b'({"a": 1}) Tj' in a1

    def test_pdf_escapes_parens(self):
        pdf = seal.render_attestation_pdf(b'{"k": "v(1)"}\n')
        assert b'v\\(1\\)' in pdf
