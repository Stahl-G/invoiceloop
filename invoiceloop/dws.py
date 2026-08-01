"""存盘 DWS 响应与第六轮读图答案的只读访问。

零 API:一切读 `~/Developer/dws-derisk/raw/` 的存盘文件,比较规则改了重跑
不再计费,panel 上每个数字都能从存盘证据重算(GOAL.md 优先级 2)。

存盘 record 形状(dws-derisk extract.py 写入)::

    {doc_id, document, mode, http_status, body, credits, request_id}
    body.output.data     — {field: value} 抽取值
    body.output.metadata — {field: {bbox, confidence, source_bboxes, pageIndex, ...}}
    body.output.pages    — [{page, width, height}] DWS 自己的像素空间
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ocr import raw_dir, derisk_root

MODES = ("understand", "agentic")

#: answers6.{A,B,C}.tsv → 读者登记(vision/readers6.md,打分前与答案同一次提交)。
VISION_READERS = {"A": "Kimi K3", "B": "Opus 5", "C": "GPT 5.6 SOL"}


@dataclass
class StoredResponse:
    doc_id: str
    mode: str
    http_status: int
    data: dict
    meta: dict
    pages: list[dict]
    path: Path

    def value(self, field: str) -> object:
        return self.data.get(field)


def response_path(doc_id: str, mode: str) -> Path:
    return raw_dir() / f"{doc_id}.{mode}.json"


def load_response(doc_id: str, mode: str) -> StoredResponse | None:
    """读一份存盘响应;文件不存在或 HTTP 非 200 返回 None(调用方记阻断)。"""
    path = response_path(doc_id, mode)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("http_status") != 200:
        return None
    output = record["body"].get("output") or {}
    return StoredResponse(
        doc_id=doc_id,
        mode=mode,
        http_status=record["http_status"],
        data=output.get("data") or {},
        meta=output.get("metadata") or {},
        pages=output.get("pages") or [],
        path=path,
    )


def stored_docs() -> list[str]:
    """raw/ 里有 understand 响应的全部 doc_id,排序固定(可复算)。"""
    return sorted(p.name[: -len(".understand.json")] for p in raw_dir().glob("*.understand.json"))


def load_vision_answers() -> dict[str, dict[tuple[str, str], dict]]:
    """第六轮三个读图模型的整页作答。

    返回 {模型名: {(doc_id, field): {"value", "printed_label", "note"}}}。
    ABSTAIN 也是真实作答(承认看不清),保留原样,由使用方决定怎么解释。
    """
    vision_dir = derisk_root() / "vision"
    out: dict[str, dict[tuple[str, str], dict]] = {}
    for tag, model in VISION_READERS.items():
        path = vision_dir / f"answers6.{tag}.tsv"
        if not path.exists():
            continue
        rows: dict[tuple[str, str], dict] = {}
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            if not line.strip():
                continue
            cols = line.split("\t")
            doc, field = cols[0], cols[1]
            rows[(doc, field)] = {
                "value": cols[2].strip() if len(cols) > 2 else "",
                "printed_label": cols[3].strip() if len(cols) > 3 else "",
                "note": cols[4].strip() if len(cols) > 4 else "",
            }
        out[model] = rows
    return out
