"""输入契约(§12 决定 3):人把 PDF 放进 `input/pdfs/`,系统从这里读。

```
workspace/
  input/pdfs/   ← 把发票丢这里(文件名即文档身份,见 sanitise_doc_id)
  ocr/          ← 独立 OCR(本地产,文字层或 tesseract)
  raw/          ← DWS 响应落这里(先存盘后解释)
  runs/run-NNNN ← run --workspace 的产出:不可变,逐代递增;
  runs/current.json   最新一代的指针(可重建,不是权威)
```

两条命令:`python3 -m invoiceloop ingest --workspace ws/`(本文)
+ `python3 -m invoiceloop run --workspace ws/`。
断点续跑:已存在的 OCR 与 200 响应一律跳过。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .fields import FIELD_KINDS, Kind
from .ocr import OcrUnavailable
from .ocr_ingest import ocr_pdf

#: 十个评估字段的默认描述(包内 HAR-0001 的提取 schema 同源;
#: 不给 required —— 必填会逼抽取器对不存在的字段编造,把诚实缺失变成自信幻觉)。
#: 可演化面在 harnesses/*/extraction_schema.json;此处仅作回退常量。
FIELD_DESCRIPTIONS = {
    "invoice_number": "Seller-assigned invoice identifier.",
    "issue_date": "Date the invoice was issued.",
    "due_date": "Payment due date.",
    "seller_name": "Full legal name of the seller.",
    "seller_vat_id": "Seller VAT identifier.",
    "buyer_name": "Full legal name of the buyer.",
    "total_net": "Invoice total without VAT.",
    "total_vat": "Total VAT amount.",
    "total_gross": "Invoice total with VAT.",
    "amount_due": "Amount the buyer must actually pay.",
}


def default_extraction_schema() -> dict:
    """包内默认 schema(无 harness 文件时的回退)。"""
    return {
        "type": "object",
        "properties": {
            name: {"type": "string", "description": FIELD_DESCRIPTIONS[name]}
            for name, kind in FIELD_KINDS.items()
            if kind in (Kind.AMOUNT, Kind.DATE, Kind.PARTY, Kind.CODE, Kind.TEXT)
        },
    }


def extraction_schema(root: Path | None = None) -> dict:
    """传给 DWS 的 JSON Schema:只要 string,不加任何额外关键字。

    优先读 active harness 的 extraction_schema.json;缺文件则回退包内默认。
    """
    from .harness import load_active

    try:
        active = load_active(root)
        schema = active.get("schema")
        if isinstance(schema, dict) and schema.get("properties"):
            return schema
    except Exception:  # noqa: BLE001 —— 无 workspace / 链未就绪时用默认
        pass
    return default_extraction_schema()


def sanitise_doc_id(stem: str) -> str:
    """文件名 → doc_id:小写、非字母数字折叠成连字符;空了就给内容哈希。

    确定性:同一文件名永远同一 doc_id(断点续跑的前提)。
    """
    doc_id = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not doc_id:
        doc_id = hashlib.sha256(stem.encode()).hexdigest()[:12]
    return doc_id


def discover(workspace: Path) -> dict[str, Path]:
    """input/pdfs/ 里的全部 PDF:{doc_id: 路径},按 doc_id 排序。

    后缀按小写比较:.PDF/.Pdf 在大小写敏感的文件系统上会被 glob("*.pdf")
    漏掉 —— 那正是宪章四立誓要防的「静默丢单」(82 评 P1-6)。
    """
    pdf_dir = Path(workspace) / "input" / "pdfs"
    out: dict[str, Path] = {}
    for pdf in sorted(pdf_dir.iterdir()):
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            continue
        doc_id = sanitise_doc_id(pdf.stem)
        if doc_id in out:  # 同名碰撞,挂短哈希,仍确定
            doc_id = f"{doc_id}-{hashlib.sha256(pdf.name.encode()).hexdigest()[:6]}"
        out[doc_id] = pdf
    return out


def cmd_ingest(
    workspace: Path,
    *,
    modes: tuple[str, ...] = ("understand", "agentic"),
    do_ocr: bool = True,
    do_extract: bool = True,
    adaptive: bool = False,
) -> dict:
    """input/pdfs/*.pdf → ocr/(本地)+ raw/(DWS)。返回并打印摘要。

    adaptive=True:先 understand,风险诊断后再决定是否调 agentic
    (L1 opt-in;默认 False 保持双模式全跑)。
    """
    workspace = Path(workspace)
    pdf_dir = workspace / "input" / "pdfs"
    if not pdf_dir.is_dir():
        raise SystemExit(
            f"输入契约:{pdf_dir} 不存在。把发票 PDF 放进 workspace/input/pdfs/ 再跑 ingest"
        )
    docs = discover(workspace)
    if not docs:
        raise SystemExit(f"输入契约:{pdf_dir} 里没有 .pdf 文件")

    if adaptive:
        modes = ("understand",)  # agentic 按文档 escalate,不在外层笛卡尔积

    summary = {"docs": len(docs), "ocred": 0, "ocr_blocked": [],
               "extracted": 0, "extract_skipped": 0, "extract_failed": [],
               "adaptive": adaptive, "escalated": 0, "skipped_clean": 0}

    if do_ocr:
        ocr_dir = workspace / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        for doc_id, pdf in docs.items():
            target = ocr_dir / f"{doc_id}.json"
            if target.exists():
                summary["ocred"] += 1
                continue
            try:
                payload = ocr_pdf(pdf)
            except OcrUnavailable as exc:
                summary["ocr_blocked"].append({"doc_id": doc_id, "reason": str(exc)})
                continue
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            summary["ocred"] += 1

    if do_extract:
        from .dws_client import extract_to_raw

        raw_dir = workspace / "raw"
        if adaptive:
            from .adaptive import (
                diagnose_risk,
                mark_workspace_adaptive,
                write_attempt_record,
            )
            mark_workspace_adaptive(workspace)

        for doc_id, pdf in docs.items():
            if adaptive:
                # ---- L1:understand → diagnose → maybe agentic
                u_target = raw_dir / f"{doc_id}.understand.json"
                u_record = _extract_one(pdf, raw_dir, doc_id, "understand",
                                        u_target, summary)
                udata = None
                u_status = None
                if isinstance(u_record, dict):
                    u_status = u_record.get("http_status")
                    body = u_record.get("body") or {}
                    output = body.get("output") or {}
                    data = output.get("data") if isinstance(output, dict) else None
                    udata = data if isinstance(data, dict) else None
                reasons = diagnose_risk(udata)
                escalated = bool(reasons)
                a_status = None
                if escalated:
                    a_target = raw_dir / f"{doc_id}.agentic.json"
                    a_record = _extract_one(pdf, raw_dir, doc_id, "agentic",
                                            a_target, summary)
                    if isinstance(a_record, dict):
                        a_status = a_record.get("http_status")
                    summary["escalated"] += 1
                else:
                    summary["skipped_clean"] += 1
                write_attempt_record(
                    workspace, doc_id, escalated=escalated, reasons=reasons,
                    understand_status=u_status if isinstance(u_status, int) else None,
                    agentic_status=a_status if isinstance(a_status, int) else None,
                )
                continue

            for mode in modes:
                target = raw_dir / f"{doc_id}.{mode}.json"
                _extract_one(pdf, raw_dir, doc_id, mode, target, summary)

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def _extract_one(pdf, raw_dir, doc_id, mode, target, summary) -> dict | None:
    """单次抽取,更新 summary;返回存盘 record 或 None。"""
    from .dws_client import extract_to_raw

    if target.exists():
        record: object = None
        try:
            record = json.loads(target.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        if isinstance(record, dict) and record.get("http_status") == 200:
            summary["extract_skipped"] += 1
            return record
    try:
        record = extract_to_raw(pdf, extraction_schema(), raw_dir,
                                doc_id=doc_id, mode=mode)
    except Exception as exc:  # noqa: BLE001 —— 记失败,不中断整批
        summary["extract_failed"].append(
            {"doc_id": doc_id, "mode": mode, "error": repr(exc)})
        return None
    status = record.get("http_status") if isinstance(record, dict) else None
    if status == 200:
        summary["extracted"] += 1
    else:
        summary["extract_failed"].append(
            {"doc_id": doc_id, "mode": mode,
             "error": f"http_status={status}"})
    return record if isinstance(record, dict) else None
