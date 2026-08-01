"""端到端编排:extract → freeze → gate → matrix → panel,全部落盘到 run 目录。

纪律:
- 零 API —— 一切从存盘证据出发,重跑不计费、结果可复算(GOAL.md 优先级 2)。
- 确定性 —— 不写墙钟时间;同样输入哈希必须产出同样字节(§5.3 是可复算性的来源)。
- 单一写者 —— 模型(dws/读图)的值只是草稿;ID、门禁、事件、哈希全在 Python。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import __version__, dws, evidence, freeze, gates, matrix
from .ocr import derisk_root


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _digest(entries: list[dict]) -> str:
    """工件注册表的内容摘要:同样输入 → 同样签名(§5.3 门禁事务绑定它)。"""
    h = hashlib.sha256()
    for e in entries:
        h.update(e["artifact_id"].encode())
        h.update(e.get("sha256", "<absent>").encode())
    return h.hexdigest()


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


def run(
    doc_ids: list[str],
    out_dir: Path,
    *,
    render_crops: bool = False,
    include_vision: bool = True,
) -> dict:
    """跑全流程,返回各工件路径。render_crops 需要 poppler 与 PDF 语料。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_ids = sorted(doc_ids)
    events: list[dict] = []

    def emit(event: str, **detail) -> None:
        events.append({"seq": len(events) + 1, "event": event, **detail})

    # ---- ① 运行状态
    _write_json(out_dir / "run_manifest.json", {
        "invoiceloop_version": __version__,
        "docs": doc_ids,
        "n_docs": len(doc_ids),
        "render_crops": render_crops,
        "include_vision": include_vision,
        "derisk_root": str(derisk_root()),
    })
    emit("run_started", n_docs=len(doc_ids))

    # ---- ② 抽取事务:工件注册 + 证据片段 + 声明图
    artifacts = evidence.register_artifacts(doc_ids)
    _write_json(out_dir / "artifact_registry.json", artifacts)
    artifact_digest = _digest(artifacts)
    emit("artifacts_registered", n=len(artifacts), digest=artifact_digest)

    understand = {d: dws.load_response(d, "understand") for d in doc_ids}
    agentic = {d: dws.load_response(d, "agentic") for d in doc_ids}
    vision_answers = dws.load_vision_answers() if include_vision else {}

    spans: list[dict] = []
    graphs: list[dict] = []
    for doc_id in doc_ids:
        u = understand[doc_id]
        if u is None:
            emit("response_unavailable", doc_id=doc_id, mode="understand")
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
    drafts = build_drafts(doc_ids, understand, agentic, vision_answers)
    _write_json(out_dir / "field_drafts.json", drafts)
    result = freeze.freeze_drafts(drafts, spans=spans)
    ledger = result.ledger()
    _write_json(out_dir / "field_ledger.json", ledger)
    events.extend(result.events)
    emit("ledger_frozen", claims=len(result.claims), rejected=len(result.rejections),
         sha256=ledger["sha256"])

    # ---- ④ 门禁事务(绑定输入签名)
    gate_report = gates.run_gates(
        doc_ids,
        understand=understand, agentic=agentic, vision_answers=vision_answers,
        ledger_sha256=ledger["sha256"], artifact_digest=artifact_digest,
    )
    _write_json(out_dir / "gate_report.json", gate_report)
    emit("gates_evaluated",
         findings=len(gate_report["findings"]),
         blocking=sum(1 for f in gate_report["findings"] if f["blocking"]))

    # ---- ⑤ 支持矩阵 + panel
    support = matrix.build_matrix(
        doc_ids,
        understand=understand, claims=result.claims, rejections=result.rejections,
        gate_report=gate_report, vision_answers=vision_answers,
    )
    _write_json(out_dir / "support_matrix.json", support)
    emit("matrix_built", **support["summary"])

    from .panel import render_panel
    render_panel(out_dir, support=support, gate_report=gate_report, spans=spans,
                 ledger=ledger, artifact_digest=artifact_digest)
    emit("panel_rendered")

    (out_dir / "event_log.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
        encoding="utf-8",
    )
    return {
        "run_dir": out_dir,
        "manifest": out_dir / "run_manifest.json",
        "artifacts": out_dir / "artifact_registry.json",
        "spans": out_dir / "evidence_span_registry.json",
        "ledger": out_dir / "field_ledger.json",
        "gate_report": out_dir / "gate_report.json",
        "matrix": out_dir / "support_matrix.json",
        "panel": out_dir / "support_panel.html",
        "events": out_dir / "event_log.jsonl",
    }
