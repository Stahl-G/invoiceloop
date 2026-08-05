"""整单交付层(P2,2026-08-05):deliverable.json —— 裁决后的最终值投影。

设计(用户 2026-08-04 批准):
- 纯投影,与 panel 同级:由 field_ledger + support_matrix + 裁决账本重算,
  不是权威,不改任何分诊行为(校准数字零漂移);
- 每槽最终值:correct → 修正值;accept → 声明值;reject → null;abstain →
  未决;未裁决且需裁决 → pending;**TIER1 印证槽未显式裁决 → pending_tier1**
  (关键字段在出口有业务后果差异:印证也不能默认放行);
  TIER2 印证槽 → unreviewed_corroborated(值照出,如实标注未逐个人看);
- 整单状态:TIER1 槽被 reject → blocked;任何 pending/abstain → pending;
  其余 → released。
"""

from __future__ import annotations

import json
from pathlib import Path

from .fields import TIER1
from .review import load_decisions, project, target_id_for
from .snapshot import load_or_derive_snapshot

#: 槽位状态 → 是否挡住整单放行
_PENDING_STATUSES = ("pending", "pending_tier1", "abstained")


def build_deliverable(run_dir: Path) -> dict:
    """run 目录 → 最终交付投影。确定性:同工件同账本,任何机器重算同字节。"""
    run_dir = Path(run_dir)
    matrix = json.loads((run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    gate_report = json.loads((run_dir / "gate_report.json").read_text(encoding="utf-8"))
    blocking_by_doc: dict[str, list[str]] = {}
    for f in gate_report["findings"]:
        # 只收文档级阻断(field=None:OCR 缺失、响应缺失、门禁异常 ——
        # 机检基础设施没跑);字段级阻断是每槽的正常路由,人已逐槽裁过
        if f["blocking"] and f.get("field") is None:
            blocking_by_doc.setdefault(f["doc_id"], []).append(f["gate_id"])
    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    slots = project(load_decisions(run_dir))

    docs: dict[str, dict] = {}
    for row in matrix["rows"]:
        doc_id, field = row["doc_id"], row["field"]
        doc = docs.setdefault(doc_id, {"status": None, "fields": {},
                                       "blocking_reasons": []})
        target = target_id_for(snapshot_id, doc_id, field)
        tip = (slots.get(target) or {}).get("tip")

        if tip is not None:
            decision = tip["decision"]
            if decision == "correct":
                entry = {"value": tip["corrected_value"], "status": "corrected",
                         "source": tip["decision_id"]}
            elif decision == "accept":
                entry = {"value": row["value"], "status": "accepted",
                         "source": tip["decision_id"]}
            elif decision == "reject":
                entry = {"value": None, "status": "rejected",
                         "source": tip["decision_id"]}
                if field in TIER1:
                    doc["blocking_reasons"].append(
                        f"关键字段 {field} 被 {tip['decision_id']} 拒绝")
            else:  # abstain:人也无法判定 —— 未决,不许带着它放行
                entry = {"value": None, "status": "abstained",
                         "source": tip["decision_id"]}
        elif row.get("requires_adjudication", True):
            # 缺这个键的只可能是手工构造/极旧的矩阵 —— 缺失按「需裁决」处理,
            # 交付层的默认方向永远是让人看,不是放行
            entry = {"value": row["value"], "status": "pending", "source": None}
        elif field in TIER1:
            # 印证槽也要显式裁决才放行 —— 关键字段在出口有差异(78 评 P2)
            entry = {"value": row["value"], "status": "pending_tier1",
                     "source": None}
        else:
            entry = {"value": row["value"],
                     "status": "unreviewed_corroborated", "source": None}
        doc["fields"][field] = entry

    for doc_id, doc in docs.items():
        statuses = {f["status"] for f in doc["fields"].values()}
        if doc["blocking_reasons"]:
            doc["status"] = "blocked"
        elif statuses & set(_PENDING_STATUSES):
            doc["status"] = "pending"
        else:
            doc["status"] = "released"
        # 带阻断发现(如独立 OCR 缺失)的文档即使全部人裁完毕,放行也必须
        # 带说明 —— 机检没跑过这件事不许在交付物里消失
        caveats = blocking_by_doc.get(doc_id)
        if caveats and doc["status"] == "released":
            doc["release_caveats"] = sorted(set(caveats))

    by_status: dict[str, int] = {}
    for doc in docs.values():
        by_status[doc["status"]] = by_status.get(doc["status"], 0) + 1
    return {
        "run": run_dir.name,
        "review_snapshot_id": snapshot_id,
        "docs": dict(sorted(docs.items())),
        "summary": {"docs": len(docs), "by_status": by_status},
        "note": ("纯投影:由 field_ledger + support_matrix + 裁决账本重算;"
                 "unreviewed_corroborated = 多方印证但未逐个人看的 TIER2 槽,"
                 "如实标注;残余风险见 panel 校准限定"),
    }


def write_deliverable(run_dir: Path) -> Path:
    """落盘 deliverable.json(重写式 —— 投影随时可重建,不是账本)。"""
    out = Path(run_dir) / "deliverable.json"
    out.write_text(
        json.dumps(build_deliverable(run_dir), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return out
