"""End-to-end orchestration: extract → freeze → gate → matrix → panel, all written
into a run directory.

Discipline:
- Zero API — everything starts from stored evidence, so re-running costs nothing
  and results recompute (GOAL.md priority 2).
- Deterministic — no wall clock is written; the same input hash must produce the
  same bytes (§5.3 is where recomputability comes from).
- Single writer — values from models (DWS, vision) are drafts only; IDs, gates,
  events and hashes are all Python's.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import __version__, dws, due_date, evidence, freeze, gates, harness, matrix, snapshot
from .ocr import OcrUnavailable, derisk_root, layout, load_ocr, pdf_path


class RunExistsError(RuntimeError):
    """输出目录非空 —— 运行不可变。没有 --force,也不许建议删裁决账本:
    销毁历史不是显式 Human decision。"""


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def build_drafts(
    doc_ids: list[str],
    understand: dict[str, dws.StoredResponse | None],
    agentic: dict[str, dws.StoredResponse | None],
    vision_answers: dict[str, dict[tuple[str, str], dict]],
) -> list[dict]:
    """把存盘证据整理成模型草稿 —— 无 ID、无权威,顺序固定(FC 编号才确定)。

    ABSTAIN / 空值不成草稿:弃权不是声明;DWS 没返回值由 extraction_present
    门禁记阻断,不是草稿。
    """
    drafts: list[dict] = []
    wanted = set(doc_ids)
    for doc_id in doc_ids:
        for field_name, value in sorted((understand[doc_id].data if understand.get(doc_id) else {}).items()):
            if value is not None and str(value).strip():
                drafts.append({"doc_id": doc_id, "field": field_name,
                               "value": str(value), "drafted_by": "dws_understand"})
        for field_name, value in sorted((agentic[doc_id].data if agentic.get(doc_id) else {}).items()):
            if value is not None and str(value).strip():
                drafts.append({"doc_id": doc_id, "field": field_name,
                               "value": str(value), "drafted_by": "dws_agentic"})
        for model in sorted(vision_answers):
            for (doc, field_name), row in sorted(vision_answers[model].items()):
                if doc != doc_id or doc not in wanted:
                    continue
                if row["value"] and row["value"].upper() != "ABSTAIN":
                    drafts.append({"doc_id": doc_id, "field": field_name,
                                   "value": row["value"], "drafted_by": f"vision:{model}"})
    return drafts


def _load(doc_id: str, mode: str) -> dws.StoredResponse | None:
    """存盘响应损坏(JSON 不可读、结构缺失)= 不可用,由门禁记阻断,不 crash 整批。"""
    try:
        return dws.load_response(doc_id, mode)
    except Exception:  # noqa: BLE001
        return None


def run(
    doc_ids: list[str],
    out_dir: Path,
    *,
    render_crops: bool = False,
    include_vision: bool = True,
    out_of_calibration: bool = False,
) -> dict:
    """跑全流程,返回各工件路径。render_crops 需要 poppler 与 PDF 语料。

    out_of_calibration:工作区(非校准集)输入时为真,panel 顶部必须
    声明校准数字不直接适用(§12 输入契约)。
    """
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RunExistsError(
            f"运行目录 {out_dir} 已存在且非空 —— 运行不可变,没有 --force。"
            f"--out 请换一个目录;--workspace 会自动分配 runs/run-NNNN"
        )
    doc_ids = sorted(doc_ids)
    active_for_scope = harness.load_active(derisk_root())
    domain_scope = active_for_scope["policy"].get("domain_scope")
    if domain_scope is not None and not isinstance(domain_scope, dict):
        raise ValueError("harness 的 domain_scope 必须是 JSON object")
    from .scope import require_workspace_scope

    workspace_scope = require_workspace_scope(
        derisk_root(), doc_ids,
        domain_scope.get("domain") if domain_scope is not None else None,
    )

    # 占坑分两步:mkdir 尽量建,再用 O_EXCL 独占 run_manifest.json。
    # 单看 mkdir 有线程级 TOCTOU(两个进程都看到「不存在」→ 一边 FileExistsError
    # 裸奔,或两边交错写出半成品 —— 81 评 P2);O_EXCL 让输的那个当场拿到
    # RunExistsError。占坑文件在 run 真正写 manifest 时被覆盖。
    try:
        out_dir.mkdir(parents=True)
    except FileExistsError:
        pass
    try:
        (out_dir / "run_manifest.json").open("x").close()
    except FileExistsError:
        raise RunExistsError(
            f"运行目录 {out_dir} 已被另一个进程占用(run_manifest.json 已存在)—— "
            f"运行不可变,没有 --force;--out 请换一个目录"
        ) from None
    events: list[dict] = []
    vision_paths = dws.vision_answer_paths() if include_vision else []

    def emit(event: str, **detail) -> None:
        events.append({"seq": len(events) + 1, "event": event, **detail})

    # ---- ① 运行状态 + 输入指纹(重放与新 run 代数的依据)
    _write_json(out_dir / "run_manifest.json", {
        "invoiceloop_version": __version__,
        "code_revision": snapshot._code_revision(),
        "harness_id": harness.load_active(derisk_root())["harness_id"],
        "docs": doc_ids,
        "n_docs": len(doc_ids),
        "render_crops": render_crops,
        "include_vision": include_vision,
        "out_of_calibration": out_of_calibration,
        "layout": layout(),
        "derisk_root": str(derisk_root()),
        "vision_captured": [path.name for path in vision_paths],
        "domain_scope": workspace_scope,
    })
    input_manifest = snapshot.build_input_manifest(doc_ids, include_vision=include_vision)
    _write_json(out_dir / "input_manifest.json", input_manifest)
    emit("run_started", n_docs=len(doc_ids),
         fingerprint=input_manifest["fingerprint"],
         execution_fingerprint=input_manifest["execution_fingerprint"])

    # ---- ② 抽取事务:工件注册 + 证据片段 + 声明图
    artifacts = evidence.register_artifacts(doc_ids)
    _write_json(out_dir / "artifact_registry.json", artifacts)
    artifact_digest = evidence.digest_registry(artifacts)
    emit("artifacts_registered", n=len(artifacts), digest=artifact_digest)

    understand = {d: _load(d, "understand") for d in doc_ids}
    agentic = {d: _load(d, "agentic") for d in doc_ids}
    skipped_vision_rows: list[dict] = []
    vision_answers = dws.load_vision_answers(
        on_skip=lambda fname, line: skipped_vision_rows.append(
            {"file": fname, "line": line})) if include_vision else {}
    if skipped_vision_rows:
        # 畸形行跳过必须留痕(78.5 评 P1):不崩批,但事件日志要看得见
        emit("vision_rows_skipped", count=len(skipped_vision_rows),
             samples=skipped_vision_rows[:5])
    if vision_paths:
        captured_dir = out_dir / "vision"
        captured_dir.mkdir(parents=True, exist_ok=True)
        for source in vision_paths:
            shutil.copyfile(source, captured_dir / source.name)
        emit("vision_inputs_captured", files=[path.name for path in vision_paths])

    # 独立 OCR 缺失的文档:这份阻断,其余照常(宪章四)。不预查的话,
    # freeze 的 OcrUnavailable 会把整批带死 —— 那是崩溃,不是阻断。
    ocr_ok: dict[str, bool] = {}
    for doc_id in doc_ids:
        try:
            load_ocr(doc_id)
            ocr_ok[doc_id] = True
        except OcrUnavailable:
            ocr_ok[doc_id] = False
            emit("doc_blocked", doc_id=doc_id, reason="ocr_unavailable", blocking=True)

    # ---- ②b 页面规则派生:raw due_date 与 calculated_due_date 永不混写
    # 只读独立 OCR。结果是新的、可审计的派生工件;它不改变冻结 raw claim,
    # 不绕过六门,也不把相对条款伪装成页面上的绝对日期。
    calculated_due_dates = {
        doc_id: (due_date.derive_due_date(load_ocr(doc_id))
                 if ocr_ok[doc_id]
                 else due_date.unavailable_due_date())
        for doc_id in doc_ids
    }
    _write_json(out_dir / "calculated_due_dates.json", {
        "artifact": "calculated_due_dates.json",
        "derivation_version": due_date.DERIVATION_VERSION,
        "raw_due_date_semantics": (
            "raw DWS due_date is an explicit-page-date claim; it is never overwritten"
        ),
        "records": calculated_due_dates,
        "summary": {
            "docs": len(calculated_due_dates),
            "computed": sum(r["status"] == "computed"
                             for r in calculated_due_dates.values()),
            "not_computable": sum(r["status"] == "not_computable"
                                   for r in calculated_due_dates.values()),
        },
    })
    emit("due_dates_derived",
         computed=sum(r["status"] == "computed"
                      for r in calculated_due_dates.values()),
         not_computable=sum(r["status"] == "not_computable"
                            for r in calculated_due_dates.values()))

    spans: list[dict] = []
    graphs: list[dict] = []
    for doc_id in doc_ids:
        u = understand[doc_id]
        if render_crops and pdf_path(doc_id).exists():
            # 整页渲染不依赖 OCR 或 DWS 响应 —— 它正是 OCR 受阻文档的最后
            # 证据:没有它,受阻文档的每一行都「没有原图」,人工复核直接
            # 断粮(2026-08-03 工作台实测,用户在 HD-0015 写下「没有原图」)
            pages = evidence.render_pages(pdf_path(doc_id), out_dir / "pages")
            if not pages and shutil.which("pdftoppm"):
                # 坏 PDF / 渲染超时(poppler 缺席不算 —— 那是环境问题,doctor 的事):
                # 不崩批(红队 P0-3),但缺口要进事件日志,不许静默 ——
                # 没有原图的行在 panel 上光秃秃,人要看得见为什么
                emit("pages_unavailable", doc_id=doc_id, reason="render_failed")
        if u is None:
            emit("response_unavailable", doc_id=doc_id, mode="understand")
            continue
        if not ocr_ok[doc_id]:
            continue
        builder = evidence.SpanBuilder(
            doc_id, u, crop_dir=(out_dir / "crops") if render_crops else None,
            start_seq=len(spans),
        )
        spans.extend(builder.build())
        graphs.append(evidence.build_claim_graph(doc_id))
    _write_json(out_dir / "evidence_span_registry.json", spans)
    _write_json(out_dir / "field_claim_graph.json", graphs)
    emit("evidence_registered", n_spans=len(spans))

    # ---- ③ 冻结事务:草稿 → 绑定校验 → FC ID → 冻结账本
    # field_drafts.json 记模型的全部产出(忠实);OCR 缺失文档的草稿不进冻结,
    # 缺口由 doc_blocked 事件承担,不藏
    drafts_all = build_drafts(doc_ids, understand, agentic, vision_answers)
    _write_json(out_dir / "field_drafts.json", drafts_all)
    drafts = [d for d in drafts_all if ocr_ok[d["doc_id"]]]
    if len(drafts) != len(drafts_all):
        emit("drafts_excluded", reason="ocr_unavailable",
             count=len(drafts_all) - len(drafts))
    result = freeze.freeze_drafts(drafts, spans=spans)
    ledger = result.ledger()
    _write_json(out_dir / "field_ledger.json", ledger)
    events.extend(result.events)
    emit("ledger_frozen", claims=len(result.claims), rejected=len(result.rejections),
         sha256=ledger["sha256"])

    # ---- ④ 门禁事务(绑定输入签名)
    # 跨文档查重(C8)看的是冻结账本:同号同卖家的内容冲突/重复提交,
    # 六门之外的文档集维度,人裁不进错误率
    from . import crossdoc

    dup_groups = crossdoc.duplicate_groups(result.claims)
    if dup_groups:
        emit("cross_document_duplicates", groups=len(dup_groups),
             docs=sorted({d["doc_id"] for g in dup_groups for d in g["docs"]}))
    from .harness import load_active

    active = load_active(derisk_root())
    from .adaptive import load_agentic_policy

    agentic_policy = load_agentic_policy(derisk_root())
    agentic_optional = frozenset(
        d for d, pol in agentic_policy.items() if pol == "optional_skipped")
    gate_report = gates.run_gates(
        doc_ids,
        understand=understand, agentic=agentic, vision_answers=vision_answers,
        ledger_sha256=ledger["sha256"], artifact_digest=artifact_digest,
        ocr_blocked=frozenset(d for d in doc_ids if not ocr_ok[d]),
        duplicate_groups=dup_groups,
        absent_expected_cohorts=active["policy"].get(
            "absent_expected_cohorts", []),
        absent_evidenced_cohorts=active["policy"].get(
            "absent_evidenced_cohorts", []),
        agentic_optional=agentic_optional,
    )
    _write_json(out_dir / "gate_report.json", gate_report)
    emit("gates_evaluated",
         findings=len(gate_report["findings"]),
         blocking=sum(1 for f in gate_report["findings"] if f["blocking"]))

    # ---- ⑤ 支持矩阵 + 分诊路由(routing_report 进快照成分,必须先落盘)
    from .harness import load_active

    active = load_active(derisk_root())
    support, routing_report = matrix.build_matrix(
        doc_ids,
        understand=understand, claims=result.claims, rejections=result.rejections,
        gate_report=gate_report, vision_answers=vision_answers,
        blocked_docs=frozenset(d for d in doc_ids if not ocr_ok[d]),
        spans=spans,
        policy=active["policy"], harness_id=active["harness_id"],
    )
    _write_json(out_dir / "routing_report.json", routing_report)
    emit("routing_decided", harness_id=active["harness_id"],
         policy_digest=routing_report["policy_digest"],
         review=sum(1 for r in routing_report["routes"] if r["route"] != "auto_accept"))

    # ---- ④b 复核快照:人工裁决绑定的完整身份(不只是账本)
    review_snapshot = snapshot.compute_review_snapshot(out_dir)
    _write_json(out_dir / "review_snapshot.json", review_snapshot)
    emit("review_snapshot", review_snapshot_id=review_snapshot["review_snapshot_id"])

    _write_json(out_dir / "support_matrix.json", support)
    emit("matrix_built", **support["summary"])

    from .panel import render_panel
    render_panel(out_dir, support=support, gate_report=gate_report, spans=spans,
                 ledger=ledger, artifact_digest=artifact_digest,
                 out_of_calibration=out_of_calibration)
    emit("panel_rendered")

    # deliverable 与 panel 同为纯投影,run 时就生成(此时零裁决,
    # 全部 pending —— 如实展示「还没开始复核」)
    from .deliver import write_deliverable

    write_deliverable(out_dir)

    (out_dir / "event_log.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
        encoding="utf-8",
    )
    # 空裁决账本也是真账本(零条裁决):run 时刻创建,人之后往里追加 —
    # 否则「先打 bundle 再裁决」的自然流程会被缺工件阻断
    (out_dir / "adjudication_ledger.jsonl").touch()
    return {
        "run_dir": out_dir,
        "manifest": out_dir / "run_manifest.json",
        "input_manifest": out_dir / "input_manifest.json",
        "review_snapshot": out_dir / "review_snapshot.json",
        "artifacts": out_dir / "artifact_registry.json",
        "spans": out_dir / "evidence_span_registry.json",
        "ledger": out_dir / "field_ledger.json",
        "calculated_due_dates": out_dir / "calculated_due_dates.json",
        "gate_report": out_dir / "gate_report.json",
        "matrix": out_dir / "support_matrix.json",
        "panel": out_dir / "support_panel.html",
        "events": out_dir / "event_log.jsonl",
    }
