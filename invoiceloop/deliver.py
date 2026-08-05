"""整单交付层(P2,2026-08-05):deliverable.json —— 裁决后的最终值投影。

设计(用户 2026-08-04 批准;语义完整性修复 2026-08-05,81 评 P0):
- 纯投影,与 panel 同级:由 field_ledger + support_matrix + 裁决账本重算,
  不是权威,不改任何分诊行为(校准数字零漂移);
- **值源永远是冻结账本与裁决账本,不是 support_matrix** —— matrix 不在
  快照成分内(可重建投影),若拿它当值源,改动投影即可污染交付物且
  三层 verify 全过(81 评实测攻击)。matrix 在这里只提供行集与
  requires_adjudication 标记,值一律从 field_ledger 的 claim 取;
- 每槽最终值:correct → 修正值;accept → **冻结 claim 的值**(accept 必须
  带 claim_id);confirm_absent / not_applicable → null(两种不同语义,
  不许混);reject → null;abstain → 未决;未裁决且需裁决 → pending;
  **TIER1 印证槽未显式裁决 → pending_tier1**(关键字段在出口有业务
  后果差异:印证也不能默认放行);TIER2 印证槽 →
  unreviewed_corroborated(值照出,如实标注未逐个人看);
- 整单状态:TIER1 槽被 reject 或裁决指向不存在的 claim → blocked;
  任何 pending/abstain → pending;带文档级阻断发现(OCR 缺失等)的
  放行如实标 released_with_caveats —— 机检没跑过的放行不许看起来
  和机检全过的一样。
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
    ledger = json.loads((run_dir / "field_ledger.json").read_text(encoding="utf-8"))
    claims_by_id = {c["claim_id"]: c for c in ledger["claims"]}
    blocking_by_doc: dict[str, list[str]] = {}
    for f in gate_report["findings"]:
        # 只收文档级阻断(field=None:OCR 缺失、响应缺失、门禁异常 ——
        # 机检基础设施没跑);字段级阻断是每槽的正常路由,人已逐槽裁过
        if f["blocking"] and f.get("field") is None:
            blocking_by_doc.setdefault(f["doc_id"], []).append(f["gate_id"])
    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    slots = project(load_decisions(run_dir))
    # 本次 run 的策略(不是当前 active —— 晋升之后旧 run 的说法不许变);
    # routing_report.json 自 2026-08-05 起是 run 工件,旧 run 没有 → 保守默认
    routing_path = run_dir / "routing_report.json"
    routing = json.loads(routing_path.read_text(encoding="utf-8")) \
        if routing_path.exists() else None
    tier1_explicit = ((routing or {}).get("policy") or {}) \
        .get("release_tier1_explicit", True)
    harness_id = (routing or {}).get("harness_id", "HAR-0001")

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
                claim = claims_by_id.get(tip.get("claim_id") or "")
                if claim is not None:
                    entry = {"value": claim["value"], "status": "accepted",
                             "source": tip["decision_id"]}
                elif tip.get("claim_id") is None:
                    # legacy(2026-08-05 前允许无 claim 的 accept)= 确认缺失的
                    # 旧写法:投影成 confirmed_absent 并标注,语义不回写
                    entry = {"value": None, "status": "confirmed_absent",
                             "source": tip["decision_id"], "legacy": True}
                else:
                    # 裁决指向冻结账本里不存在的 claim —— 完整性已破坏,
                    # 值不可知,整单 blocked(verify 语义层同样抓这个)
                    entry = {"value": None, "status": "accepted_unbound",
                             "source": tip["decision_id"]}
                    doc["blocking_reasons"].append(
                        f"裁决 {tip['decision_id']} 指向不存在的 "
                        f"claim {tip.get('claim_id')}")
            elif decision == "confirm_absent":
                entry = {"value": None, "status": "confirmed_absent",
                         "source": tip["decision_id"]}
            elif decision == "not_applicable":
                entry = {"value": None, "status": "not_applicable",
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
        elif row.get("route") == "auto_accept" and not tier1_explicit:
            # 策略放行(v0.2 P0-6):系统自动接受必须显式记录为 policy_accept
            # + 策略版本,不是伪造一条人工 accept;值仍只来自冻结 claim
            claim = claims_by_id.get(row.get("claim_id") or "")
            entry = {"value": claim["value"] if claim else None,
                     "status": "policy_accepted",
                     "source": f"policy:{harness_id}"}
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
        # 带文档级阻断发现(如独立 OCR 缺失)的文档即使全部人裁完毕,
        # 放行也是另一档:如实标 released_with_caveats —— 机检没跑过
        # 这件事不许在交付物里消失(2026-08-05 实测抓出的披露缺口)
        caveats = blocking_by_doc.get(doc_id)
        if caveats and doc["status"] == "released":
            doc["status"] = "released_with_caveats"
            doc["release_caveats"] = sorted(set(caveats))

    by_status: dict[str, int] = {}
    for doc in docs.values():
        by_status[doc["status"]] = by_status.get(doc["status"], 0) + 1
    # 真实人工负载(81 评 P1):要整单放行,必须显式裁决的槽 =
    # 分诊需裁决 ∪ 全部 TIER1(印证槽也要人点)—— 与反事实分诊负载
    # (requires_adjudication 比例)是两回事,交付物里两个数字都在才诚实
    n_slots = sum(len(d["fields"]) for d in docs.values())
    n_decide = sum(
        1 for row in matrix["rows"]
        if row.get("requires_adjudication", True) or row["field"] in TIER1)
    return {
        "run": run_dir.name,
        "review_snapshot_id": snapshot_id,
        "docs": dict(sorted(docs.items())),
        "summary": {
            "docs": len(docs), "by_status": by_status,
            "slots": n_slots,
            "decision_load_for_release": n_decide / max(n_slots, 1),
        },
        "note": ("纯投影:最终值只来自 field_ledger 与裁决账本(support_matrix "
                 "不参与取值);unreviewed_corroborated = 多方印证但未逐个人看的 "
                 "TIER2 槽,如实标注;残余风险见 panel 校准限定"),
    }


def write_deliverable(run_dir: Path) -> Path:
    """落盘 deliverable.json(重写式 —— 投影随时可重建,不是账本)。"""
    out = Path(run_dir) / "deliverable.json"
    out.write_text(
        json.dumps(build_deliverable(run_dir), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return out
