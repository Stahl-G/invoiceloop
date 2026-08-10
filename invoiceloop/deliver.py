"""Whole-document delivery (P2, 2026-08-05): deliverable.json — the projection of
final values after adjudication.

Design (approved 2026-08-04; semantic-integrity fix 2026-08-05, from the 81-point
review's P0):

- A pure projection, peer to the panel: recomputed from field_ledger +
  support_matrix + the adjudication ledger. Not authoritative, and it changes no
  triage behaviour (calibration numbers drift by zero).
- **Values always come from the frozen ledger and the adjudication ledger, never
  from support_matrix.** The matrix is not a snapshot component (it is a
  rebuildable projection), so using it as the value source would let an edit to
  the projection poison the delivery while all three verify layers still pass —
  this was an attack demonstrated during the 81-point review. Here the matrix
  supplies only the row set and the requires_adjudication flag; every value comes
  from a field_ledger claim.
- Per slot: `correct` → the corrected value; `accept` → **the frozen claim's
  value** (accept must carry claim_id); `confirm_absent` / `not_applicable` →
  null (two different meanings, never merged); `reject` → null; `abstain` →
  undecided; needs adjudication but has none → pending; **a TIER1 corroborated
  slot with no explicit decision → pending_tier1** (key fields differ in business
  consequence at the exit, so corroboration alone does not release them); a TIER2
  corroborated slot → unreviewed_corroborated (the value ships, labelled honestly
  as not individually reviewed).
- Per document: a rejected TIER1 slot, or an adjudication pointing at a claim
  that does not exist → blocked; any pending or abstained slot → pending; a
  release carrying document-level blocking findings (missing OCR and the like) is
  labelled released_with_caveats — a document released while a check could not
  run must never look as clean as one where every check passed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .fields import TIER1
from .review import load_decisions, project, target_id_for
from .snapshot import load_or_derive_snapshot

#: 槽位状态 → 是否挡住整单放行
PENDING_STATUSES = ("pending", "pending_tier1", "abstained")
#: 由**策略**而非人处置的槽。三者是一回事的三种形状:harness 决定这个槽
#: 不必问人。`unreviewed_corroborated` 名字里没有 policy,但它同样是策略
#: 处置 —— 它落在 route=auto_accept 且 release_tier1_explicit=true 的
#: TIER2 槽上,决定「不问人」的是 harness,不是证据强度本身。
POLICY_STATUSES = ("policy_accepted", "policy_confirmed_absent",
                   "unreviewed_corroborated")
#: 兼容旧名(外部脚本在用)。新代码用不带下划线的。
_PENDING_STATUSES = PENDING_STATUSES


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
    # 类型字面证据(阶段 C):旧 run 无 document_checks → 视为未知,不编造 pass
    document_checks = gate_report.get("document_checks") or {}
    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    slots = project(load_decisions(run_dir))
    # 本次 run 的策略(不是当前 active —— 晋升之后旧 run 的说法不许变);
    # routing_report.json 自 2026-08-05 起是 run 工件,旧 run 没有 → 保守默认
    routing_path = run_dir / "routing_report.json"
    routing = json.loads(routing_path.read_text(encoding="utf-8")) \
        if routing_path.exists() else None
    derived_path = run_dir / "calculated_due_dates.json"
    derived = json.loads(derived_path.read_text(encoding="utf-8")) \
        if derived_path.exists() else {}
    derived_by_doc = derived.get("records") or {}
    tier1_explicit = ((routing or {}).get("policy") or {}) \
        .get("release_tier1_explicit", True)
    harness_id = (routing or {}).get("harness_id", "HAR-0001")
    # route/requires 以 routing_report(快照成分)为准,不以 matrix 行为准 ——
    # matrix 是投影;改了投影行不许改变交付语义(评审裁决三)
    routes_by_slot = {
        (r["doc_id"], r["field"]): r["route"]
        for r in (routing or {}).get("routes", [])
    }

    docs: dict[str, dict] = {}
    for row in matrix["rows"]:
        doc_id, field = row["doc_id"], row["field"]
        doc = docs.setdefault(doc_id, {"status": None, "fields": {},
                                       "blocking_reasons": [],
                                       "derived_fields": {}})
        if doc_id in derived_by_doc:
            # 派生日期是业务规则结果,不是十字段 raw claim;它不参与
            # accept/reject/route,且原始 due_date 仍在 fields 中单列。
            doc["derived_fields"]["calculated_due_date"] = derived_by_doc[doc_id]
        if "type_trust" not in doc:
            check = document_checks.get(doc_id) or {}
            st = check.get("status")
            if st == "pass":
                doc["type_trust"] = "evidenced"
                doc["doc_class"] = check.get("doc_class")
            elif st == "fail":
                doc["type_trust"] = "untrusted"
                doc["doc_class"] = check.get("doc_class")
            elif st in ("no_claim", "unmapped", "ocr_unavailable"):
                doc["type_trust"] = st
                doc["doc_class"] = check.get("doc_class")
            else:
                doc["type_trust"] = "unknown"  # 旧 run / 未跑检查
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
        else:
            route = routes_by_slot.get((doc_id, field))
            requires = (route not in ("auto_accept", "auto_absent")) \
                if route is not None \
                else row.get("requires_adjudication", True)
            if requires:
                # 缺这个键的只可能是手工构造/极旧的矩阵 —— 缺失按「需裁决」
                # 处理,交付层的默认方向永远是让人看,不是放行
                entry = {"value": row["value"], "status": "pending",
                         "source": None}
            elif route == "auto_absent":
                # 政策确认缺失(absent_expected cohort):显式记录策略版本,
                # 不是伪造一条人工 confirm_absent;QA 抽检盯着缺席是否成立
                entry = {"value": None,
                         "status": "policy_confirmed_absent",
                         "source": f"policy:{harness_id}"}
            elif route == "auto_accept" and not tier1_explicit:
                # 策略放行(v0.2 P0-6):系统自动接受必须显式记录为
                # policy_accept + 策略版本,不是伪造一条人工 accept;
                # 值仍只来自冻结 claim
                claim = claims_by_id.get(row.get("claim_id") or "")
                entry = {"value": claim["value"] if claim else None,
                         "status": "policy_accepted",
                         "source": f"policy:{harness_id}"}
            elif field in TIER1:
                # 印证槽也要显式裁决才放行 —— 关键字段在出口有差异(78 评 P2)
                entry = {"value": row["value"], "status": "pending_tier1",
                         "source": None}
            else:
                # 未逐个人看的 TIER2 印证槽。source 写 policy 而不是 null:
                # 「没人做过决定」是假的 —— 有决定,是 harness 做的,权威链
                # 必须一路指得回那份 policy(2026-08-09 Northstar)。
                entry = {"value": row["value"],
                         "status": "unreviewed_corroborated",
                         "source": f"policy:{harness_id}"}
        doc["fields"][field] = entry

    from .approve import document_digest, latest_by_doc

    approvals = latest_by_doc(run_dir)
    for doc_id, doc in docs.items():
        statuses = {f["status"] for f in doc["fields"].values()}
        if doc["blocking_reasons"]:
            doc["status"] = "blocked"
        elif statuses & set(PENDING_STATUSES):
            doc["status"] = "pending"
        else:
            # 槽全部处置完毕 = **自动化的终点**,不是记账授权的起点。
            # 十个槽全被策略放行的文档同样走到这里,而它从头到尾没人看过 ——
            # 所以这个状态只能叫「等人批」,不能叫「放行了」
            # (2026-08-09 Northstar:机器可达的状态不得授予外发权限)。
            doc["status"] = "ready_for_approval"
        # 带文档级阻断发现(如独立 OCR 缺失)的文档即使全部处置完毕,
        # 也是另一档:如实标 _with_caveats —— 机检没跑过这件事不许在交付物里
        # 消失(2026-08-05 实测抓出的披露缺口),批准之后同样不许消失。
        caveats = blocking_by_doc.get(doc_id)
        if caveats and doc["status"] == "ready_for_approval":
            doc["status"] = "ready_for_approval_with_caveats"
            doc["release_caveats"] = sorted(set(caveats))
        # 文档级批准(approve_ledger.jsonl):唯一能让状态变成可外发的东西。
        # 绑死批准当时的内容摘要 —— 值改了旧签名不跟着走,但**留在工件里**:
        # 谁在什么内容上批过字是审计轨迹。
        # 批准前必须看得见的东西:这份单里有多少槽是**没有人看过**的,
        # 其中哪些是关键字段。批准是一次署名,署名的人有权知道自己在替
        # 多少条策略处置背书 —— 这比禁止策略放行 TIER1 更有用:知情之后
        # 才谈得上放心把自动放行开大(这正是降人工率要走的路)。
        doc["policy_disposed_fields"] = sorted(
            f for f, e in doc["fields"].items()
            if e["status"] in POLICY_STATUSES)
        doc["tier1_policy_disposed_fields"] = sorted(
            f for f in doc["policy_disposed_fields"] if f in TIER1)
        approval = approvals.get(doc_id)
        if approval is not None:
            stale = (approval["document_digest"] != document_digest(doc)
                     or doc["status"] not in ("ready_for_approval",
                                              "ready_for_approval_with_caveats"))
            doc["approval"] = {**approval, "stale": stale}
            if not stale:
                doc["status"] = doc["status"].replace(
                    "ready_for_approval", "approved_for_export")

    by_status: dict[str, int] = {}
    for doc in docs.values():
        by_status[doc["status"]] = by_status.get(doc["status"], 0) + 1
    # 真实人工负载(81 评 P1):这份策略下,要走完整单必须有人碰的槽占比。
    #
    # 2026-08-09 重写。原式是 `requires_adjudication ∪ 全部 TIER1`,压根不看
    # route —— 于是它对 harness **完全不敏感**:SEALED-3 七个臂全报 82.8%,
    # 而同一份 deliverable 的逐字段状态显示 HAR-0001 是 624 个待处置、
    # HAR-0004 是 527(docs/SEALED3_RESULTS.md §5)。一个用来做多臂比较的
    # 指标恰好在 harness 维度上是常数,只能判为不可解释。
    #
    # 新口径直接由下面同一份 fields 状态复算:非策略处置的槽 ÷ 总槽。
    # 它不随「已经裁了几个」变化 —— 衡量的是策略要人碰几个槽,不是还剩几个。
    n_slots = sum(len(d["fields"]) for d in docs.values())
    n_policy = sum(1 for d in docs.values() for f in d["fields"].values()
                   if f["status"] in POLICY_STATUSES)
    n_decide = n_slots - n_policy
    # 字段级人工队列直方图(deliver 口径:route ∉ auto_accept|auto_absent)
    per_doc_queue: dict[str, int] = {d: 0 for d in docs}
    for row in matrix["rows"]:
        in_q = row.get("in_human_queue")
        if in_q is None:
            in_q = row.get("route") not in ("auto_accept", "auto_absent") \
                if row.get("route") is not None \
                else row.get("requires_adjudication", True)
        if in_q:
            per_doc_queue[row["doc_id"]] = per_doc_queue.get(row["doc_id"], 0) + 1
    counts = sorted(per_doc_queue.values())
    histogram: dict[str, int] = {}
    for n in counts:
        key = str(n)
        histogram[key] = histogram.get(key, 0) + 1
    median = counts[len(counts) // 2] if counts else 0
    return {
        "run": run_dir.name,
        "review_snapshot_id": snapshot_id,
        # 顶层记 harness —— 它此前只以 `source: "policy:HAR-000N"` 出现在被
        # 策略放行的槽上,所以零 straight-through 的 run 里,决定「哪些槽
        # 不用问人」的那份策略在交付物里完全不出现。冻结账本不在这里重记:
        # field_ledger.json 已是 review_snapshot 的成分。
        "harness_id": harness_id,
        "docs": dict(sorted(docs.items())),
        "summary": {
            "docs": len(docs), "by_status": by_status,
            "slots": n_slots,
            "decision_load_for_release": n_decide / max(n_slots, 1),
            "policy_disposed_slots": n_policy,
            # 还差几次人工批准才能外发。它和槽级负载是两笔账:槽全裁完
            # 也不等于可以入账(2026-08-09 权威链)。
            "documents_awaiting_approval": sum(
                1 for d in docs.values()
                if d["status"].startswith("ready_for_approval")),
            "documents_approved_for_export": sum(
                1 for d in docs.values()
                if d["status"].startswith("approved_for_export")),
            "fields_in_human_queue_histogram": dict(sorted(
                histogram.items(), key=lambda kv: int(kv[0]))),
            "median_fields_in_human_queue": median,
            "mean_fields_in_human_queue":
                (sum(counts) / len(counts)) if counts else 0.0,
        },
        "note": ("harness_id 是产生本次路由的策略;冻结账本由 review_snapshot_id "
                 "绑定,不在此重记。"
                 "纯投影:最终值只来自 field_ledger 与裁决账本(support_matrix "
                 "不参与取值);unreviewed_corroborated = 多方印证但未逐个人看的 "
                 "TIER2 槽,由 harness 处置,source 指回该策略;"
                 "残余风险见 panel 校准限定;"
                 "字段级人工队列用 in_human_queue(不含 auto_absent),"
                 "勿把文档级 pending 当成「机器一点忙没帮上」。"
                 "**只有 approved_for_export 可以外发**:ready_for_approval "
                 "是自动化能到的终点,机器不批准单据。"
                 "decision_load_for_release = 非策略处置槽占比,与本文件的 "
                 "fields 状态同源复算"),
    }


def write_deliverable(run_dir: Path) -> Path:
    """落盘 deliverable.json(重写式 —— 投影随时可重建,不是账本)。"""
    out = Path(run_dir) / "deliverable.json"
    out.write_text(
        json.dumps(build_deliverable(run_dir), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return out
