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

#: 十个评估字段的描述(搬 dws-derisk schema.py 的字段语义;
#: 不给 required —— 必填会逼抽取器对不存在的字段编造,把诚实缺失变成自信幻觉)
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


def extraction_schema() -> dict:
    """传给 DWS 的 JSON Schema:只要 string,不加任何额外关键字
    (端点实测会拒 additionalProperties 等,见 dws-derisk schema.py)。"""
    return {
        "type": "object",
        "properties": {
            name: {"type": "string", "description": FIELD_DESCRIPTIONS[name]}
            for name, kind in FIELD_KINDS.items()
            if kind in (Kind.AMOUNT, Kind.DATE, Kind.PARTY, Kind.CODE, Kind.TEXT)
        },
    }


def sanitise_doc_id(stem: str) -> str:
    """文件名 → doc_id:小写、非字母数字折叠成连字符;空了就给内容哈希。

    确定性:同一文件名永远同一 doc_id(断点续跑的前提)。
    """
    doc_id = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not doc_id:
        doc_id = hashlib.sha256(stem.encode()).hexdigest()[:12]
    return doc_id


def discover(workspace: Path) -> dict[str, Path]:
    """input/pdfs/ 里的全部 PDF:{doc_id: 路径},按 doc_id 排序。"""
    pdf_dir = Path(workspace) / "input" / "pdfs"
    out: dict[str, Path] = {}
    for pdf in sorted(pdf_dir.glob("*.pdf")):
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
) -> dict:
    """input/pdfs/*.pdf → ocr/(本地)+ raw/(DWS)。返回并打印摘要。"""
    workspace = Path(workspace)
    pdf_dir = workspace / "input" / "pdfs"
    if not pdf_dir.is_dir():
        raise SystemExit(
            f"输入契约:{pdf_dir} 不存在。把发票 PDF 放进 workspace/input/pdfs/ 再跑 ingest"
        )
    docs = discover(workspace)
    if not docs:
        raise SystemExit(f"输入契约:{pdf_dir} 里没有 .pdf 文件")

    summary = {"docs": len(docs), "ocred": 0, "ocr_blocked": [],
               "extracted": 0, "extract_skipped": 0, "extract_failed": []}

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
        for doc_id, pdf in docs.items():
            for mode in modes:
                target = raw_dir / f"{doc_id}.{mode}.json"
                if target.exists():
                    try:
                        if json.loads(target.read_text()).get("http_status") == 200:
                            summary["extract_skipped"] += 1
                            continue
                    except json.JSONDecodeError:
                        pass
                try:
                    extract_to_raw(pdf, extraction_schema(), raw_dir,
                                   doc_id=doc_id, mode=mode)
                    summary["extracted"] += 1
                except Exception as exc:  # noqa: BLE001 —— 记失败,不中断整批
                    summary["extract_failed"].append(
                        {"doc_id": doc_id, "mode": mode, "error": repr(exc)})

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary
