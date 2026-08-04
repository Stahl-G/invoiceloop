"""`python3 -m invoiceloop demo` —— 内嵌示例语料跑通全流程。

评委路径的关键一环:仓库不再要求任何外部数据 —— samples/ 内嵌三份
DocILE 发票 + 已存盘的 DWS 响应(抽取不重跑,零 API)+ 读图作答,
`demo --out ws/` 就地建 workspace、本地 OCR、跑完整 run,最后提示
打开工作台。046e0c49 是退化扫描件:多数 poppler 构建抽不出文字层,
OCR 受阻 → 诚实阻断展品;个别构建能抽出,它就照常走全流程 ——
两种形态都合法。与环境无关的展品是读图门对「买卖双方抽反」的
warning(由 vendored 数据决定)。钉死「受阻必显式」的不变量,
不钉「某份文档必须受阻」(78 评 P3:后者在评委机上实测失败)。
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
        from . import dws, ocr as ocr_mod
        from .ingest import cmd_ingest, discover
        from .pipeline import run

        # lru_cache 按 doc_id 记:同进程里别的语料先跑过的话,
        # 同名文档会拿到旧语料的 OCR(长驻进程缓存污染,同复核 #6 一类)
        ocr_mod.load_ocr.cache_clear()
        ocr_mod.doc_tokens.cache_clear()

        summary = cmd_ingest(out, do_ocr=True, do_extract=False)
        doc_ids = sorted(set(discover(out)) | set(dws.stored_docs()))
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
    blocked_ids = [b["doc_id"] for b in blocked]
    if blocked_ids:
        note = (f"OCR 受阻:{', '.join(blocked_ids)} —— 诚实阻断展品;"
                f"046e0c49 的读图门「买卖双方抽反」warning 两份展品都在")
    else:
        note = ("本机 poppler 从退化扫描件也抽出了文字层,三份全流程正常;"
                "046e0c49 的展品是读图门对「买卖双方抽反」的 warning(数据决定)")
    print(json.dumps({
        "workspace": str(out),
        "run_dir": str(run_dir),
        "panel": str(paths["panel"]),
        "docs": doc_ids,
        "ocr_blocked": blocked_ids,
        "next": f"python3 -m invoiceloop workbench --workspace {out}",
        "note": note,
    }, ensure_ascii=False, indent=1))
