"""M0 抽取事务(ARCHITECTURE.md §5.1):存盘响应 → 工件注册 → 证据片段 → 声明图。

不调 API:响应早已存盘(extract.py 的纪律是先存盘再解释),这里把存盘文件
按内容哈希冻结为工件,从 `source_bboxes` 注册证据片段,并为每个片段挂上
独立 OCR 文本与旁边印着的标签 —— 支持关系是几何的,这几样就是可验证的载体。

裁剪渲染走 poppler(pdftoppm/pdfinfo),坐标换算搬自
vision_eval.py::_rects / crop_field:DWS 报的是自己像素空间的 bbox
(Letter 上约 1700×2200),经 `body.output.pages` 的页尺寸归一化,
再在目标 DPI 的真实页尺寸上乘回去。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .dws import MODES, StoredResponse
from .fields import FIELDS
from .ocr import derisk_root, iter_words

#: 引用区很紧,允许带上邻近 token(与 round3.citation_holds 同一 padding)。
REGION_PAD = 0.03
#: 裁剪边距与整页回退阈值,搬自 vision_eval.py。
MARGIN = 0.08
FULL_PAGE = 0.50
DPI = 150


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register_artifacts(doc_ids: Iterable[str]) -> list[dict]:
    """把每份存盘响应按内容哈希登记为工件(§10 保留:内容寻址冻结)。

    非 200 的响应也登记 —— 4xx body 是文档被拒原因的唯一记录,
    那些案例属于分母(dws-derisk extract.py 的存盘纪律)。
    """
    from .dws import response_path

    registry = []
    for doc_id in doc_ids:
        for mode in MODES:
            path = response_path(doc_id, mode)
            entry = {
                "artifact_id": f"raw-{mode}-{doc_id[:12]}",
                "doc_id": doc_id,
                "mode": mode,
                "path": str(path),
                "present": path.exists(),
            }
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                entry["http_status"] = record.get("http_status")
                entry["sha256"] = sha256_file(path)
            registry.append(entry)
    return registry


# ---------------------------------------------------------------------- 几何

def rel_rects(meta: dict, pages: list[dict]) -> dict[int, list[float]]:
    """一个字段的引用框,按页归一化,页内取并集。搬 vision_eval.py::_rects。"""
    dims = {}
    for i, p in enumerate(pages):
        page_no = p.get("page", i + 1)
        dims[page_no] = (p.get("width"), p.get("height"))
    rects: dict[int, list[float]] = {}
    for src in meta.get("source_bboxes") or []:
        bbox = src.get("bbox")
        page_no = src.get("pageNumber", src.get("pageIndex", 0) + 1)
        wh = dims.get(page_no)
        if not bbox or not wh or not wh[0]:
            continue
        w, h = wh
        rel = [
            bbox["x"] / w,
            bbox["y"] / h,
            (bbox["x"] + bbox["width"]) / w,
            (bbox["y"] + bbox["height"]) / h,
        ]
        if page_no not in rects:
            rects[page_no] = rel
        else:
            r = rects[page_no]
            r[0], r[1] = min(r[0], rel[0]), min(r[1], rel[1])
            r[2], r[3] = max(r[2], rel[2]), max(r[3], rel[3])
    return rects


def _intersects(a: tuple, b) -> bool:
    return not (a[2] < b[0][0] or a[0] > b[1][0] or a[3] < b[0][1] or a[1] > b[1][1])


def region_ocr_text(doc_id: str, page_no: int, rect: list[float]) -> str:
    """引用区(加 pad)内的独立 OCR 词,按阅读序拼接。搬 round3.citation_holds 的取词。"""
    region = (rect[0] - REGION_PAD, rect[1] - REGION_PAD, rect[2] + REGION_PAD, rect[3] + REGION_PAD)
    words = [
        (bbox[0][1], bbox[0][0], value)
        for page_idx, value, bbox in iter_words(doc_id)
        if page_idx == page_no - 1 and _intersects(region, bbox)
    ]
    return " ".join(w for _, _, w in sorted(words))


def printed_label(doc_id: str, page_no: int, rect: list[float]) -> str:
    """值旁边印着的标签原文:与引用框同水平带、整体在其左侧的 OCR 词。

    只能抓住"标签在值左边"的布局(发票金额区大多如此);标签印在值上方
    的布局抓不到,记 "NONE" —— 这是已知的取词边界,不是静默。
    """
    band = (0.0, rect[1] - 0.005, rect[0] + 0.003, rect[3] + 0.005)
    words = [
        (bbox[0][1], bbox[0][0], value)
        for page_idx, value, bbox in iter_words(doc_id)
        if page_idx == page_no - 1
        and _intersects(band, bbox)
        and bbox[1][0] <= rect[0] + 0.003
    ]
    return " ".join(w for _, _, w in sorted(words)) or "NONE"


# ---------------------------------------------------------------------- 裁剪

def _page_pixels(pdf_path: Path, page_no: int) -> tuple[float, float]:
    info = subprocess.run(
        ["pdfinfo", "-f", str(page_no), "-l", str(page_no), str(pdf_path)],
        check=True, capture_output=True, text=True,
    ).stdout
    for line in info.splitlines():
        if "size:" in line and "pts" in line:
            nums = line.split("size:")[1].split("pts")[0].split("x")
            return float(nums[0]) * DPI / 72, float(nums[1]) * DPI / 72
    raise RuntimeError(f"pdfinfo: no page size for {pdf_path.name} p{page_no}")


def render_crop(pdf_path: Path, page_no: int, rect: list[float], out_stem: Path) -> tuple[str, str] | None:
    """渲染引用区裁剪图,返回 (文件名, sha256);渲染不了返回 None(调用方记缺口)。

    左边距切到页边而不是 x0 - MARGIN:DWS 框的是值,说明"这是什么值"的词
    在左边,对称边距实测会把它切掉(vision_eval.py crop_field 的教训)。
    """
    if not pdf_path.exists() or shutil.which("pdftoppm") is None:
        return None
    x0, y0, x1, y1 = rect
    area = (x1 - x0) * (y1 - y0)
    if area <= FULL_PAGE:
        x0, y0 = 0.0, max(0.0, y0 - MARGIN)
        x1, y1 = min(1.0, x1 + MARGIN), min(1.0, y1 + MARGIN)
    width, height = _page_pixels(pdf_path, page_no)
    px, pw = int(x0 * width), max(1, int((x1 - x0) * width))
    py, ph = int(y0 * height), max(1, int((y1 - y0) * height))
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-f", str(page_no), "-l", str(page_no),
         "-x", str(px), "-y", str(py), "-W", str(pw), "-H", str(ph),
         str(pdf_path), str(out_stem)],
        check=True, capture_output=True,
    )
    # pdftoppm 按文档总页数给序号补零(10 页以上输出 stem-03.png),
    # 不猜文件名,按产物找
    produced = sorted(out_stem.parent.glob(f"{out_stem.name}-*.png"))
    if not produced:
        return None
    return produced[0].name, sha256_file(produced[0])


# ------------------------------------------------------------------ 证据片段

@dataclass
class SpanBuilder:
    """为一个文档的响应注册证据片段;crop_dir 为 None 时不渲染(测试/无 poppler)。

    span_id 在整个 run 内唯一:start_seq 由编排层跨文档续号。
    """

    doc_id: str
    response: StoredResponse
    crop_dir: Path | None = None
    start_seq: int = 0
    spans: list[dict] = field(default_factory=list)

    def build(self) -> list[dict]:
        pdf = derisk_root() / "data" / "docile" / "pdfs" / f"{self.doc_id}.pdf"
        seq = self.start_seq
        for field_name in FIELDS:
            meta = self.response.meta.get(field_name)
            if not meta:
                continue
            for page_no, rect in sorted(rel_rects(meta, self.response.pages).items()):
                seq += 1
                span_id = f"ES-{seq:04d}"
                span = {
                    "span_id": span_id,
                    "doc_id": self.doc_id,
                    "field": field_name,
                    "page": page_no,
                    "bbox_rel": [round(v, 6) for v in rect],
                    "ocr_text": region_ocr_text(self.doc_id, page_no, rect),
                    "printed_label": printed_label(self.doc_id, page_no, rect),
                    "source": "dws_source_bbox",
                    "crop": None,
                    "crop_sha256": None,
                }
                if self.crop_dir is not None:
                    self.crop_dir.mkdir(parents=True, exist_ok=True)
                    rendered = render_crop(pdf, page_no, rect, self.crop_dir / span_id)
                    if rendered:
                        span["crop"], span["crop_sha256"] = rendered
                self.spans.append(span)
        return self.spans


def build_claim_graph(doc_id: str) -> dict:
    """原子声明图:节点是字段,边是可验证的算术恒等式(ARCHITECTURE.md §4)。

    边是结构,不是裁决 —— 恒等式成立与否由 arithmetic_consistency 门禁评。
    """
    return {
        "doc_id": doc_id,
        "nodes": [{"field": f} for f in FIELDS],
        "edges": [
            {"from": ["total_net", "total_vat"], "to": "total_gross", "relation": "sum", "check": "C1"},
            {"from": ["total_gross"], "to": "amount_due", "relation": "equals", "check": "C2"},
            {"from": ["issue_date"], "to": "due_date", "relation": "before", "check": "C3"},
        ],
    }
