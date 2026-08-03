"""`python3 -m invoiceloop demo` —— 内嵌示例语料跑通全流程。

评委路径的关键一环:仓库不再要求任何外部数据 —— samples/ 内嵌三份
DocILE 发票 + 已存盘的 DWS 响应(抽取不重跑,零 API)+ 读图作答,
`demo --out ws/` 就地建 workspace、本地 OCR、跑完整 run,最后提示
打开工作台。其中 046e0c49 是 OCR 受阻的退化扫描件 —— 它不是意外,
是展品:受阻文档的诚实阻断 + 读图门对「买卖双方抽反」的 warning。
"""

from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path


def _copy_samples(ws: Path) -> None:
    src = resources.files("invoiceloop") / "samples"
    for sub, target in (("pdfs", ws / "input" / "pdfs"),
                        ("raw", ws / "raw"),
                        ("vision", ws / "vision")):
        target.mkdir(parents=True, exist_ok=True)
        for item in (src / sub).iterdir():
            (target / item.name).write_bytes(item.read_bytes())


def cmd_demo(out: Path) -> None:
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} 已存在且非空 —— run 不可变同样适用于 demo,换个目录")
    _copy_samples(out)

    # 语料指针只在本命令内改向,用完还回 —— 库调用不许留下环境副作用
    prev = {k: os.environ.get(k) for k in ("INVOICELOOP_CORPUS", "INVOICELOOP_DWS_DERISK")}
    os.environ["INVOICELOOP_CORPUS"] = str(out)
    try:
        from . import dws
        from .ingest import cmd_ingest
        from .pipeline import run

        summary = cmd_ingest(out, do_ocr=True, do_extract=False)
        doc_ids = dws.stored_docs()
        run_dir = out / "runs" / "run-0001"
        paths = run(doc_ids, run_dir, render_crops=True,
                    include_vision=True, out_of_calibration=True)
        (out / "runs" / "current.json").write_text(
            json.dumps({"run": "run-0001"}, ensure_ascii=False) + "\n", encoding="utf-8")
    finally:
        for key, value in prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    blocked = summary.get("ocr_blocked", [])
    print(json.dumps({
        "workspace": str(out),
        "run_dir": str(run_dir),
        "panel": str(paths["panel"]),
        "docs": doc_ids,
        "ocr_blocked": [b["doc_id"] for b in blocked],
        "next": f"python3 -m invoiceloop workbench --workspace {out}",
        "note": ("046e0c49 的 OCR 受阻是展品特性:诚实阻断 + 读图门对"
                 "「买卖双方抽反」的 warning;其余两份有文字层,全流程正常"),
    }, ensure_ascii=False, indent=1))
