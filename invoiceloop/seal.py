"""seal —— 审计包的 DWS 签名封缄(第五层的外层信封,不是成员)。

设计(DWS_SIGN_AND_VIEWER_PLAN.md,2026-08-06 评审采纳):

- `bundle` 保持离线、确定性、同输入同字节 —— 一个字不改;
- `seal` 是纯增量:读 audit_bundle.zip,造 attestation(不含我方时间戳
  —— 时间由签名的可信时间戳提供,我方不自报),渲染成一页极简 PDF
  (手写 PDF 语法,零新依赖,确定性),POST /sign(cades/b-lt),
  得 audit_bundle.sealed.zip = 原成员 + attestation.json +
  attestation.signed.pdf。MANIFEST 一个字节不动(成员身份不成环:
  attestation 证明的就是那份 manifest);
- key 只从环境变量读(NUTRIENT_API_KEY 优先,DWS_API_KEY 兜底),
  与 dws_client 同一纪律:绝不落盘;
- 诚实边界(必须同屏):签名证明「这份摘要于时间 T 经过 DWS 签名且此后
  未被改动」,签发主体是 DWS 的证书,不是本项目 —— 「谁造的包」
  仍需带外身份。verify 的 notes 按此写,不许写「现在有信任根了」。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zlib
import zipfile
from pathlib import Path

from . import __version__

#: 封缄外层信封的成员名(members 层按格式容忍,signature 层专查)
SEAL_MEMBERS = ("attestation.json", "attestation.signed.pdf")

SIGN_URL = "https://api.nutrient.io/sign"
SIGN_PROFILE = {"signatureType": "cades", "cadesLevel": "b-lt"}


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def build_attestation(run_dir: Path) -> tuple[dict, bytes]:
    """从 run + bundle 构造 attestation(canonical JSON 字节)。确定性。"""
    run_dir = Path(run_dir)
    bundle = run_dir / "audit_bundle.zip"
    if not bundle.exists():
        raise FileNotFoundError(f"先打 bundle:{bundle} 不存在")
    with zipfile.ZipFile(bundle) as zf:
        manifest_bytes = zf.read("MANIFEST.sha256")
    snap = json.loads((run_dir / "review_snapshot.json").read_text())
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    att = {
        "attests": "audit_bundle",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "review_snapshot_id": snap["review_snapshot_id"],
        "run_dir_name": run_dir.name,
        "n_docs": len(manifest.get("docs", [])),
        "invoiceloop_version": __version__,
        "signature_profile": f"{SIGN_PROFILE['signatureType']}/"
                             f"{SIGN_PROFILE['cadesLevel']}",
    }
    return att, _canonical(att)


# ---------------------------------------------------------------- 极简 PDF

def _pdf_text_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def render_attestation_pdf(attestation_bytes: bytes) -> bytes:
    """attestation JSON → 一页极简 PDF(确定性:固定对象序、无时间戳、
    无 ID 串;ASCII-only)。签名签的就是这几百字节的内容。"""
    lines = attestation_bytes.decode("ascii").splitlines()
    stream_lines = ["BT", "/F1 9 Tf", "40 800 Td", "12 TL"]
    for i, ln in enumerate(lines):
        cmd = "Tj" if i == 0 else "'"
        stream_lines.append(f"({_pdf_text_escape(ln)}) {cmd}")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {n} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


# ---------------------------------------------------------------- /sign 客户端

def _api_key() -> str:
    from .env import credential

    key = credential("nutrient")
    if not key:
        raise RuntimeError(
            "签名需要 NUTRIENT_API_KEY(或 DWS_API_KEY)—— 进程环境或"
            "项目根 .env(见 .env.example);值不写进任何工件")
    return key


def seal_run(run_dir: Path, *, _post=None) -> Path:
    """封缄一个已打好的 bundle,返回 audit_bundle.sealed.zip 路径。

    _post:测试注入的 HTTP 替身(签名 (url, files, headers) → (status, bytes))。
    """
    run_dir = Path(run_dir)
    att, att_bytes = build_attestation(run_dir)
    pdf = render_attestation_pdf(att_bytes)

    if _post is None:
        import requests

        def _post(url, *, files, headers):
            resp = requests.post(url, files=files, headers=headers, timeout=120)
            return resp.status_code, resp.content
        headers = {"Authorization": f"Bearer {_api_key()}"}
    else:
        headers = {}  # 测试替身不需要真 key

    status, body = _post(
        SIGN_URL,
        files={
            "file": ("attestation.pdf", pdf, "application/pdf"),
            "data": (None, json.dumps(SIGN_PROFILE), "application/json"),
        },
        headers=headers,
    )
    if status != 200:
        raise RuntimeError(
            f"/sign 返回 {status}:{body[:400]!r} —— 未封缄;响应全文就是证据")
    sealed_pdf = body

    out = run_dir / "audit_bundle.sealed.zip"
    with zipfile.ZipFile(run_dir / "audit_bundle.zip") as zin, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(SEAL_MEMBERS[0], att_bytes)
        zout.writestr(SEAL_MEMBERS[1], sealed_pdf)
    return out


# ---------------------------------------------------------------- 验签支持

def signed_pdf_embeds(pdf_bytes: bytes, needle: bytes) -> bool:
    """签名 PDF 的内容里是否含指定字节(原文或 FlateDecode 流内)。"""
    if needle in pdf_bytes:
        return True
    for m in re.finditer(rb"stream\r?\n", pdf_bytes):
        start = m.end()
        end = pdf_bytes.find(b"endstream", start)
        if end == -1:
            continue
        try:
            chunk = zlib.decompress(pdf_bytes[start:end])
        except zlib.error:
            continue
        if needle in chunk:
            return True
    return False


def crypto_available() -> bool:
    try:
        import asn1crypto  # noqa: F401
        import cryptography  # noqa: F401
    except ImportError:
        return False
    return True


def verify_pdf_signature(pdf_bytes: bytes) -> dict:
    """CAdES 验签(可选依赖 asn1crypto + cryptography)。

    返回 {valid, signer, note}。验证范围(照实说):
    签名数学有效 + 覆盖内容未被改动 + 签署者证书身份;
    不验证证书链到可信根(信任根仍在带外 —— 与四层同一边界)。
    """
    from asn1crypto import cms as _cms  # type: ignore
    from cryptography import x509  # type: ignore
    from cryptography.hazmat.primitives import hashes  # type: ignore
    from cryptography.hazmat.primitives.asymmetric import padding as _pad  # type: ignore

    br = re.search(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]",
                   pdf_bytes)
    contents = re.search(rb"/Contents\s*<([0-9A-Fa-f\s]+)>", pdf_bytes)
    if not br or not contents:
        return {"valid": False, "signer": None,
                "note": "PDF 里找不到 /ByteRange 或 /Contents —— 不是有效的"
                        "数字签名结构"}
    a, b, c, d = (int(x) for x in br.groups())
    covered = pdf_bytes[a:b] + pdf_bytes[c:d]
    sig_bytes = bytes.fromhex(re.sub(rb"\s", b"", contents.group(1)).decode())
    ci = _cms.ContentInfo.load(sig_bytes)
    if ci["content_type"].native != "signed_data":
        return {"valid": False, "signer": None, "note": "不是 CMS SignedData"}
    sd = ci["content"]
    signer = sd["signer_infos"][0]
    signed_attrs = signer["signed_attrs"]
    md = next((v for a in signed_attrs if a["type"].dotted
               == "1.2.840.113549.1.9.4" for v in a["values"]), None)
    if md is None or md.native != hashlib.sha256(covered).digest():
        return {"valid": False, "signer": None,
                "note": "签名覆盖内容的摘要与签名内记录不符 —— 内容被改过"}
    cert_der = sd["certificates"][0].chosen.dump()
    cert = x509.load_der_x509_certificate(cert_der)
    cert.public_key().verify(signer["signature"].native,
                             signed_attrs.dump(),
                             _pad.PKCS1v15(), hashes.SHA256())
    return {"valid": True,
            "signer": cert.subject.rfc4514_string(),
            "note": "签名数学有效(证书链到可信根未验证,信任锚仍在带外)"}
