"""独立的 DWS /extraction/extract 客户端(不依赖 dws-derisk 仓库)。

存盘纪律与 dws-derisk extract.py 相同:**先写原始响应,再谈解释**;
record 形状逐字段一致,所以 dws.load_response 零改动读取。
4xx body 也存 —— 文档被拒的原因只在那里(dws-derisk 的教训)。

密钥只从参数或环境变量 DWS_API_KEY 读,绝不落盘。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

EXTRACT_URL = "https://api.nutrient.io/extraction/extract"


def extract(
    document: Path,
    schema: dict[str, Any],
    *,
    doc_id: str,
    mode: str = "understand",
    api_key: str | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    """跑一次 schema 驱动的抽取并返回存盘 record(写不写盘由调用方定)。"""
    key = api_key or os.environ.get("DWS_API_KEY")
    if not key:
        raise RuntimeError("DWS_API_KEY 未设置;环境变量注入,不写进任何文件")

    payload: dict[str, Any] = {"schema": schema, "parseConfig": {"mode": mode}}
    document = Path(document)
    with document.open("rb") as handle:
        response = requests.post(
            EXTRACT_URL,
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (document.name, handle, "application/pdf")},
            data={"instructions": json.dumps(payload)},
            timeout=timeout,
        )

    try:
        body: Any = response.json()
    except ValueError:
        body = {"_non_json_body": response.text[:4000]}

    return {
        "doc_id": doc_id,
        "document": document.name,
        "mode": mode,
        "http_status": response.status_code,
        "body": body,
        "credits": response.headers.get("x-credits-used"),
        "request_id": response.headers.get("x-request-id"),
    }


def extract_to_raw(
    document: Path,
    schema: dict[str, Any],
    raw_dir: Path,
    *,
    doc_id: str,
    mode: str = "understand",
    api_key: str | None = None,
) -> dict[str, Any]:
    """抽取并先落盘(存盘纪律),返回 record。"""
    record = extract(document, schema, doc_id=doc_id, mode=mode, api_key=api_key)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{doc_id}.{mode}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return record
