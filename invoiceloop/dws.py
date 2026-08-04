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
VISION_READERS = {"A": "Kimi K3", "B": "Opus 5", "C": "GPT 5.6 SOL",
                  "D": "kimi-k3"}


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


def vision_answer_paths(vision_dir: Path | None = None) -> list[Path]:
    """返回读图作答文件,按文件名排序。

    pipeline 会把这些输入复制进 run,这样工作台和 audit bundle 不依赖
    run 之后仍可变的校准目录。
    """
    root = Path(vision_dir) if vision_dir is not None else derisk_root() / "vision"
    if not root.is_dir():
        return []
    return sorted(root.glob("answers6.*.tsv"))


def load_response(doc_id: str, mode: str) -> StoredResponse | None:
    """读一份存盘响应;文件不存在或 HTTP 非 200 返回 None(调用方记阻断)。"""
    path = response_path(doc_id, mode)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("DWS record top level 不是 object")
    if record.get("http_status") != 200:
        return None
    body = record.get("body")
    if not isinstance(body, dict):
        raise ValueError("DWS record body 不是 object")
    output = body.get("output") or {}
    if not isinstance(output, dict):
        raise ValueError("DWS output 不是 object")
    data = output.get("data") or {}
    meta = output.get("metadata") or {}
    pages = output.get("pages") or []
    if not isinstance(data, dict):
        raise ValueError("DWS output.data 不是 object")
    if not isinstance(meta, dict):
        raise ValueError("DWS output.metadata 不是 object")
    if not isinstance(pages, list):
        raise ValueError("DWS output.pages 不是 array")
    return StoredResponse(
        doc_id=doc_id,
        mode=mode,
        http_status=record["http_status"],
        data=data,
        meta=meta,
        pages=pages,
        path=path,
    )


def stored_docs() -> list[str]:
    """raw/ 里有 understand 响应的全部 doc_id,排序固定(可复算)。"""
    return sorted(p.name[: -len(".understand.json")] for p in raw_dir().glob("*.understand.json"))


def load_vision_answers(
    on_skip=None, *, vision_dir: Path | None = None
) -> dict[str, dict[tuple[str, str], dict]]:
    """读图模型的整页作答(vision/answers6.<tag>.tsv,全部 tag)。

    返回 {模型名: {(doc_id, field): {"value", "printed_label", "note"}}}。
    tag → 显示名走 VISION_READERS,没收录的 tag(比如 vision-ingest 新接的
    读者)用 tag 本身 —— 文件在就算数,不许硬编码名单把新读者漏掉。
    ABSTAIN 也是真实作答(承认看不清),保留原样,由使用方决定怎么解释。
    on_skip:畸形行(少列/空 doc/空 field)的回调 (文件名, 行首 40 字) ——
    跳过必须有人知道,不许静默(78.5 评 P1)。
    """
    out: dict[str, dict[tuple[str, str], dict]] = {}
    for path in vision_answer_paths(vision_dir):
        tag = path.name.split(".")[1]
        model = VISION_READERS.get(tag, tag)
        rows: dict[tuple[str, str], dict] = {}
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) < 2 or not cols[0].strip() or not cols[1].strip():
                # 畸形行(空行/少列):跳过 —— 一行坏数据不许 IndexError 崩掉
                # 整个 run(82 评 P1-7);空值=弃权由 cmd_vision 的解析保证,
                # 这里收的是手改/截断的文件
                if on_skip:
                    on_skip(path.name, line[:40])
                continue
            doc, field = cols[0], cols[1]
            rows[(doc, field)] = {
                "value": cols[2].strip() if len(cols) > 2 else "",
                "printed_label": cols[3].strip() if len(cols) > 3 else "",
                "note": cols[4].strip() if len(cols) > 4 else "",
            }
        out[model] = rows
    return out
