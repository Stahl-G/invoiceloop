"""环境自检:评委拿到 clean clone 后的第一件事应该是 `invoiceloop doctor`。

产品路径(workspace:ingest → run → adjudicate → bundle)的硬依赖缺失
→ 退出码 1;研究路径(heldout、校准复算、run --out 读 dws-derisk 存盘证据)
只报告不阻断 —— 默认安装不要求 sibling 校准档案。
"""

from __future__ import annotations

import json
import shutil
import sys


def cmd_doctor() -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, required: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "required": required, "detail": detail})

    check("python>=3.10", sys.version_info >= (3, 10), True, sys.version.split()[0])
    try:
        import requests

        check("requests", True, True, requests.__version__)
    except ImportError:
        check("requests", False, True, "缺:pip install requests(或 pip install .)")
    for tool, why in (
        ("pdftotext", "文字层独立 OCR 与 bbox 坐标(brew install poppler)"),
        ("pdftoppm", "证据裁剪与整页渲染(同上)"),
    ):
        check(f"poppler:{tool}", shutil.which(tool) is not None, True, why)
    check("tesseract", shutil.which("tesseract") is not None, False,
          "扫描件退路(无文字层的 PDF);没有它,扫描件按宪章四阻断而不是静默跳过")

    from .ocr import derisk_root

    root = derisk_root()
    research = (root / "raw").is_dir() and (root / "data" / "docile" / "ocr").is_dir()
    check("research:dws-derisk 存盘证据", research, False,
          f"{root} —— heldout/校准复算/run --out 需要;产品路径(workspace)不需要")

    report = {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1
