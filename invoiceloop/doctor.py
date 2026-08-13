"""Environment self-check: the first thing to run on a clean clone.

A missing hard dependency of the product path (workspace: ingest → run →
adjudicate → bundle) exits 1. The research path (heldout, calibration recompute,
`run --out` reading stored dws-derisk evidence) is reported but never blocks —
a default install does not require the sibling calibration archive.
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
        ("pdfinfo", "裁剪坐标换算的页尺寸来源(同上)"),
    ):
        check(f"poppler:{tool}", shutil.which(tool) is not None, True, why)
    check("tesseract", shutil.which("tesseract") is not None, False,
          "扫描件退路(无文字层的 PDF);没有它,扫描件按宪章四阻断而不是静默跳过")

    # 凭证:只报有没有与来自哪里,**永不回显值**。全缺不阻断 ——
    # 产品路径的 demo 零 API,评委不需要任何 key 就能跑通
    from .env import status as env_status

    env_info = env_status()
    creds = env_info["credentials"]
    check("credentials:.env", env_info["env_file"] is not None, False,
          f"{env_info['env_file'] or '未找到项目 .env(cp .env.example .env)'}"
          + (f" mode={env_info['env_file_mode']}"
             if env_info["env_file_mode"] else ""))
    if env_info["env_file_mode"] and env_info["env_file_mode"] not in ("0o600", "0o400"):
        check("credentials:.env 权限", False, False,
              f"{env_info['env_file_mode']} —— 建议 chmod 600(不阻断)")
    for purpose, why in (
        ("dws", "DWS 抽取(ingest --do-extract / 工作台抽取)"),
        ("nutrient", "签名封缄 invoiceloop seal(缺则回退 DWS_API_KEY)"),
        ("anthropic", "读图 vision 与顾问层 suggest"),
        ("gemini", "Gemini API 与 ADK Agent 编排层"),
    ):
        source = creds.get(purpose)
        check(f"credentials:{purpose}", source is not None, False,
              f"{why} —— " + (f"已配置(来源:{source})" if source else "未配置"))

    try:
        import google.adk  # noqa: F401
        import google.genai  # noqa: F401
        check("optional:google-adk", True, False,
              f"顾问层已装进 {sys.executable}")
    except ImportError:
        check("optional:google-adk", False, False,
              f"顾问层未装进 {sys.executable} —— 工作台改进页不会给出"
              f"可点的 Gemini 按钮(不阻断产品路径)")

    from .ocr import corpus_available, derisk_root

    check("research:dws-derisk 存盘证据", corpus_available(), False,
          f"{derisk_root()} —— heldout/校准复算/run --out 需要;产品路径(workspace)不需要")

    report = {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1
