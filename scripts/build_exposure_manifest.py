"""生成 docs/development_exposure_manifest.json(封箱排除池,高级裁决二)。

「未见」的定义不是「不在两份正式名单里」,而是「开发过程从未接触过」。
本脚本汇总全部已暴露文档,逐条记 reason + source,确定性可重算:

- 校准 160:dws-derisk run_batch.sample(160)(六轮实验全用过);
- 旧留出 100:docs/heldout_doc_list.json(H1–H6 + C3/C8/漂移分析都源于它,
  69 评后降级为回归/演化集);
- SEALED-1 100:docs/sealed1_doc_list.json(封箱评测 + HITL + 泛化分析后
  已降级为演化/回归集 —— 进 SEALED-2 前必须排除);
- vendored demo 3 份:invoiceloop/samples/pdfs/(demo、live 测试、录屏素材,
  是被打开/截图/分析最多的三份);
- 测试 fixture:tests/ 全部用合成文档,无真实 DocILE id(2026-08-05 核查:
  grep 32-hex 无命中)。

用法:python3 scripts/build_exposure_manifest.py(写 docs/,幂等)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.ocr import derisk_root  # noqa: E402


def main() -> None:
    sys.path.insert(0, str(derisk_root()))
    import run_batch  # type: ignore  # dws-derisk 校准档案,只读复用

    entries: dict[str, dict] = {}

    def add(doc_id: str, reason: str, source: str) -> None:
        e = entries.setdefault(doc_id, {"doc_id": doc_id, "reasons": []})
        e["reasons"].append({"reason": reason, "source": source})

    for p in run_batch.sample(160):
        add(p.stem, "calibration-160(六轮实验设计/评分全部见过它)",
            "dws-derisk run_batch.sample(160)")
    heldout = json.loads(
        (REPO / "docs" / "heldout_doc_list.json").read_text())["doc_ids"]
    for doc_id in heldout:
        add(doc_id, "heldout-100(H1–H6、C3/C8 修复案例、漂移分析同源;"
            "69 评后降级为回归集)", "docs/heldout_doc_list.json")
    sealed1 = json.loads(
        (REPO / "docs" / "sealed1_doc_list.json").read_text())["doc_ids"]
    for doc_id in sealed1:
        add(doc_id, "sealed1-100(SEALED-1 封箱评测 + HITL-12 + 泛化回放;"
            "已降级为演化/回归集,不得进 SEALED-2)",
            "docs/sealed1_doc_list.json")
    for p in sorted((REPO / "invoiceloop" / "samples" / "pdfs").glob("*.pdf")):
        add(p.stem, "vendored demo 样本(demo/live 测试/录屏反复使用)",
            "invoiceloop/samples/pdfs/")

    manifest = {
        "purpose": "封箱排除池(SEALED-2+):这些文档开发过程已暴露,不许进新封箱评测",
        "generated": "scripts/build_exposure_manifest.py(确定性,可重算)",
        "counts": {
            "calibration_160": 160,
            "heldout_100": len(heldout),
            "sealed1_100": len(sealed1),
            "unique_total": len(entries),
        },
        "doc_ids": [entries[k] for k in sorted(entries)],
    }
    out = REPO / "docs" / "development_exposure_manifest.json"
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"暴露清单:{len(entries)} 份 → {out}")
    print("新封箱取样必须排除以上全部;新增暴露(新 demo/新分析案例)"
          "必须先加进本清单再动手")


if __name__ == "__main__":
    main()
