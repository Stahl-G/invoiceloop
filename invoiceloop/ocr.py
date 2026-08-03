"""DocILE 词级 OCR 的只读访问层。

校准档案在 `~/Developer/dws-derisk/`(ARCHITECTURE.md §12 决定 1),本包通过
配置指向它,不复制数据。打分与绑定只读存盘文件,零 API。

宪章四:OCR 缺失不是"绑定失败",是检查跑不了 —— 抛 `OcrUnavailable`,
由上层记成阻断发现,不许压成 `False` 藏进拒绝率。
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class OcrUnavailable(RuntimeError):
    """该 doc 的独立 OCR 不存在或不可读 —— 高危阻断发现,不是跳过。"""


def derisk_root() -> Path:
    """校准档案根目录,可用环境变量覆盖(测试指向临时语料)。"""
    return Path(os.environ.get("INVOICELOOP_DWS_DERISK", "~/Developer/dws-derisk")).expanduser()


def layout(root: Path | None = None) -> str:
    """根目录的摆放契约(§12 决定 3 的输入契约):

    - ``"derisk"``:校准档案 —— raw/ + data/docile/{ocr,pdfs,annotations}
    - ``"workspace"``:用户工作区 —— raw/ + ocr/ + input/pdfs/
      (有 input/pdfs 目录即视为工作区;held-out 工作区带 data/ 符号链接,
      仍按 derisk 布局解析,不受影响)
    """
    root = root or derisk_root()
    return "workspace" if (root / "input" / "pdfs").is_dir() else "derisk"


def ocr_path(doc_id: str) -> Path:
    root = derisk_root()
    if layout(root) == "workspace":
        return root / "ocr" / f"{doc_id}.json"
    return root / "data" / "docile" / "ocr" / f"{doc_id}.json"


def pdf_path(doc_id: str) -> Path:
    root = derisk_root()
    if layout(root) == "workspace":
        return root / "input" / "pdfs" / f"{doc_id}.pdf"
    return root / "data" / "docile" / "pdfs" / f"{doc_id}.pdf"


def raw_dir() -> Path:
    """存盘 DWS 响应目录:`{doc_id}.understand.json` / `{doc_id}.agentic.json`。"""
    return derisk_root() / "raw"


def corpus_available() -> bool:
    """研究路径(校准复算 / heldout / run --out)需要的全部存盘证据是否齐。

    与代码取数走同一个 derisk_root()(env 可变)—— 测试守卫必须用它,
    各写各的硬编码路径就会出现「守卫说有、取数说没有」的错位。
    产品路径(workspace)不查这个。
    """
    root = derisk_root()
    return all((root / p).is_dir() for p in (
        "raw", "vision",
        "data/docile/ocr", "data/docile/annotations", "data/docile/pdfs",
    ))


@lru_cache(maxsize=None)
def load_ocr(doc_id: str) -> dict:
    """整份文档的词级 OCR(pages → blocks → lines → words)。

    word.geometry 是相对坐标 [[x0,y0],[x1,y1]],与页尺寸无关。
    """
    path = ocr_path(doc_id)
    if not path.exists():
        raise OcrUnavailable(f"OCR 不存在:{path}(doc {doc_id})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OcrUnavailable(f"OCR 不可读:{path}(doc {doc_id}):{exc}") from exc


def iter_words(doc_id: str) -> Iterator[tuple[int, str, tuple]]:
    """产出 (page_idx, word_value, rel_bbox) 三元组,按文档顺序。"""
    for page in load_ocr(doc_id)["pages"]:
        for block in page["blocks"]:
            for line in block["lines"]:
                for word in line["words"]:
                    yield page["page_idx"], word["value"], tuple(
                        tuple(pt) for pt in word["geometry"]
                    )


def page_dimensions(doc_id: str) -> list[tuple[int, int]]:
    """每页像素尺寸 (w, h),按 page_idx 排序。"""
    return [
        (page["dimensions"][0], page["dimensions"][1])
        for page in sorted(load_ocr(doc_id)["pages"], key=lambda p: p["page_idx"])
    ]


def normalise_tokens(text: str) -> list[str]:
    """绑定规则唯一的分词器:小写后按 `[a-z0-9]+` 切。

    ⚠ 两侧(值与文档)必须用这同一个函数,不得给文档侧额外收
    "整词剥标点"的 token:`$5.00` 整剥是 `500`,与金额 `500` 撞车;
    实测 dws-derisk doc 0486b911 里两处 `$5.00` 的碎片足以让一行错位的
    `$8,500.00` 从 2/3 拒绝变成 3/3 接纳(ARCHITECTURE.md §8b)。
    不要"优化"这条。

    已知边界:非 ASCII 字母(é、ß、中文字)整词丢弃 —— 校准语料是美国
    英文发票,这是刻意的简单,不是疏漏;换语料时与 §8b 一起重测。
    """
    return _TOKEN_RE.findall(text.lower())


@lru_cache(maxsize=None)
def doc_tokens(doc_id: str) -> frozenset[str]:
    """整份文档 OCR 文本的 token 集合(与值侧同一分词器)。"""
    toks: set[str] = set()
    for _, value, _ in iter_words(doc_id):
        toks.update(normalise_tokens(value))
    return frozenset(toks)
