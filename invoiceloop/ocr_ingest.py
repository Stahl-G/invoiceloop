"""任意 PDF → 独立 OCR(DocILE 词级格式),输入契约的本地腿。

绑定/引用/证据全都建立在"独立 OCR"上 —— 独立的意思是**不来自 DWS**。
born-digital PDF 用文字层(pdftotext -bbox,词级坐标);
扫描件退到 tesseract(若在);两条都没有 = OcrUnavailable,阻断不藏。

产出形状与 DocILE OCR 一致(pages → blocks → lines → words,
geometry 为相对坐标),下游所有消费者(iter_words / doc_tokens /
region_ocr_text / printed_label)零改动复用。
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from .evidence import DPI
from .ocr import OcrUnavailable

#: 单个外部命令的超时(秒):坏 PDF 不许把 ingest 挂死(红队 P2:subprocess 无超时)。
CMD_TIMEOUT = 120


def _word(value: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.99) -> dict:
    return {
        "value": value,
        "confidence": conf,
        "geometry": [[x0, y0], [x1, y1]],
        "snapped_geometry": [[x0, y0], [x1, y1]],
    }


def _page(words: list[dict], idx: int, width: float, height: float) -> dict:
    return {
        "page_idx": idx,
        "dimensions": [int(width), int(height)],
        "orientation": {"value": None, "confidence": None},
        "language": {"value": None, "confidence": None},
        "blocks": [{
            "geometry": [[0, 0], [1, 1]],
            "artefacts": [],
            "lines": [{"geometry": [[0, 0], [1, 1]], "words": words}],
        }],
    }


def _local(tag: str) -> str:
    """XHTML 带默认命名空间,按本地名匹配({ns}page 与 page 通吃)。"""
    return tag.rsplit("}", 1)[-1]


def _pdftotext_pages(pdf_path: Path) -> list[dict]:
    """文字层取词:pdftotext -bbox 的 XHTML,坐标为 pt,按页宽高归一化。

    取不到(命令失败、输出不是合法 XHTML)= 空列表退 tesseract,
    不是异常 —— 损坏 PDF 是常态输入,宪章四要的是最后的 OcrUnavailable
    阻断,不是半路的崩溃。
    """
    if shutil.which("pdftotext") is None:
        return []
    try:
        out = subprocess.run(
            ["pdftotext", "-bbox", str(pdf_path), "-"],
            check=True, capture_output=True, text=True, timeout=CMD_TIMEOUT,
        ).stdout
        root = ET.fromstring(out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ET.ParseError):
        return []
    pages = []
    for page_el in (e for e in root.iter() if _local(e.tag) == "page"):
        idx = len(pages)
        w = float(page_el.get("width", "0"))
        h = float(page_el.get("height", "0"))
        if not w or not h:
            continue
        words = [
            _word(
                (el.text or "").strip(),
                float(el.get("xMin")) / w, float(el.get("yMin")) / h,
                float(el.get("xMax")) / w, float(el.get("yMax")) / h,
            )
            for el in page_el.iter()
            if _local(el.tag) == "word" and (el.text or "").strip()
        ]
        pages.append(_page(words, idx, w, h))
    return pages


def _png_size(png: Path) -> tuple[int, int]:
    with png.open("rb") as fh:
        fh.read(16)
        return struct.unpack(">II", fh.read(8))


def parse_tesseract_tsv(tsv: str, width: int, height: int) -> list[dict]:
    """tesseract TSV 的词行(level 5)→ 词级几何(相对坐标)。独立出来便于测试。"""
    words = []
    for line in tsv.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) != 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        x, y, w, h = (int(cols[i]) for i in (6, 7, 8, 9))
        conf = float(cols[10]) / 100.0
        words.append(_word(text, x / width, y / height,
                           (x + w) / width, (y + h) / height, conf))
    return words


def _tesseract_pages(pdf_path: Path, work_dir: Path) -> list[dict]:
    """扫描件退路:pdftoppm 渲染后 tesseract 取词。渲染/识别失败同样退化
    为空列表,由 ocr_pdf 统一给 OcrUnavailable。"""
    if shutil.which("tesseract") is None or shutil.which("pdftoppm") is None:
        return []
    work_dir.mkdir(parents=True, exist_ok=True)
    stem = work_dir / pdf_path.stem
    try:
        subprocess.run(["pdftoppm", "-png", "-r", str(DPI), str(pdf_path), str(stem)],
                       check=True, capture_output=True, timeout=CMD_TIMEOUT * 3)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return []
    pages = []
    for idx, png in enumerate(sorted(work_dir.glob(f"{pdf_path.stem}-*.png"))):
        w_px, h_px = _png_size(png)
        try:
            tsv = subprocess.run(
                ["tesseract", str(png), "stdout", "tsv"],
                check=True, capture_output=True, text=True, timeout=CMD_TIMEOUT,
            ).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            continue
        pages.append(_page(parse_tesseract_tsv(tsv, w_px, h_px), idx, w_px, h_px))
    return pages


def ocr_pdf(pdf_path: Path, *, work_dir: Path | None = None) -> dict:
    """一份 PDF 的独立 OCR。文字层优先,tesseract 兜底,都没有 = 阻断。"""
    pdf_path = Path(pdf_path)
    pages = _pdftotext_pages(pdf_path)
    if not any(p["blocks"][0]["lines"][0]["words"] for p in pages):
        scratch = (work_dir or pdf_path.parent) / ".ocr-scratch"
        pages = _tesseract_pages(pdf_path, scratch)
    if not pages or not any(p["blocks"][0]["lines"][0]["words"] for p in pages):
        raise OcrUnavailable(
            f"{pdf_path.name}: 无文字层且 tesseract 不可用或取不到词 —— "
            f"这份文档的独立 OCR 产不出,按宪章四阻断"
        )
    return {"pages": pages}
