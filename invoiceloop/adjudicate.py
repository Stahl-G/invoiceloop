"""M4 人工裁决与交付(ARCHITECTURE.md §3 骨干④)。

人是裁决的写者,但只能写裁决 —— 不许改已冻结的运行输入(宪章一)。
裁决只追加,不编辑:`adjudication_ledger.jsonl` 是 append-only,落盘即 fsync。

每条裁决绑定**完整复核快照**(review_snapshot_id:输入清单 + 工件注册表 +
证据片段 + 冻结账本 + 门禁报告),不是只绑账本 —— 同一账本配上被替换的
证据,只绑账本检测不到。裁决语义冻结:

- `correct` 必须带 corrected_value;`accept/reject/abstain` 禁止携带
- claim_id ↔ doc_id ↔ field 三者必须精确一致(不许只指着一个真实 claim
  就裁决别的字段)
- 同一字段槽的第二次决定必须显式 supersede 当前 tip;链由 review.py 投影

交付 = audit_bundle.zip(见 build_audit_bundle)。
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

from .fields import FIELDS
from .review import load_decisions, project, target_id_for
from .snapshot import load_or_derive_snapshot

DECISIONS = ("accept", "reject", "correct", "abstain")

#: 打包进 audit bundle 的工件(缺了算包没打全,不静默跳过)
REQUIRED_ARTIFACTS = (
    "run_manifest.json",
    "input_manifest.json",
    "artifact_registry.json",
    "evidence_span_registry.json",
    "field_claim_graph.json",
    "field_drafts.json",
    "field_ledger.json",
    "gate_report.json",
    "review_snapshot.json",
    "support_matrix.json",
    "support_panel.html",
    "event_log.jsonl",
    "adjudication_ledger.jsonl",
)


def append_adjudication(
    run_dir: Path,
    *,
    claim_id: str | None,
    doc_id: str,
    field: str,
    decision: str,
    rationale: str,
    adjudicator: str,
    decided_at: str,
    corrected_value: str | None = None,
    supersedes_decision_id: str | None = None,
) -> dict:
    """追加一条裁决并 fsync。时间由调用方注入 —— 工件本身不读墙钟(可复算)。

    校验失败 → ValueError,一行都不写;写成功就是写成功(调用方做渲染,
    渲染失败不回滚这里)。
    """
    run_dir = Path(run_dir)
    if decision not in DECISIONS:
        raise ValueError(f"decision 必须是 {DECISIONS} 之一,收到 {decision!r}")
    if decision == "correct":
        if not (corrected_value and corrected_value.strip()):
            raise ValueError("correct 必须带 corrected_value —— 修正值是什么必须写出来")
        corrected_value = corrected_value.strip()
    elif corrected_value is not None:
        raise ValueError(f"{decision} 禁止携带 corrected_value —— 修正只能走 correct")
    if field not in FIELDS:
        raise ValueError(f"field {field!r} 不是受评字段({sorted(FIELDS)} 之一)")
    if not (decided_at and str(decided_at).strip()):
        raise ValueError("decided_at 不能为空 —— 裁决时间由人给出,不由系统代填")

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if doc_id not in set(manifest.get("docs", [])):
        raise ValueError(f"doc {doc_id!r} 不在本次 run 的文档集合里 —— 裁决必须指向 run 内文档")

    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    if claim_id is not None:
        ledger = json.loads((run_dir / "field_ledger.json").read_text(encoding="utf-8"))
        claims = {c["claim_id"]: c for c in ledger["claims"]}
        claim = claims.get(claim_id)
        if claim is None:
            raise ValueError(f"claim_id {claim_id!r} 不在已冻结账本里 —— 裁决必须指向真实声明")
        if claim["doc_id"] != doc_id or claim["field"] != field:
            raise ValueError(
                f"claim_id {claim_id} 属于 {claim['doc_id']}/{claim['field']},"
                f"与提交的 {doc_id}/{field} 不一致 —— 三者必须精确一致"
            )

    target = target_id_for(snapshot_id, doc_id, field)
    decisions = load_decisions(run_dir)
    slot = project(decisions).get(target)
    if slot and slot["conflict"]:
        raise ValueError(
            f"{doc_id}/{field} 的裁决链冲突(多条 tip)—— "
            f"先人工整理 adjudication_ledger.jsonl,系统不替人猜"
        )
    tip = slot["tip"] if slot else None
    if tip is None and supersedes_decision_id is not None:
        raise ValueError("该字段槽没有既有裁决,supersedes_decision_id 必须为 null")
    if tip is not None and supersedes_decision_id != tip["decision_id"]:
        raise ValueError(
            f"该字段槽已有裁决 {tip['decision_id']}({tip['decision']})—— "
            f"第二次决定必须显式带上 supersedes_decision_id={tip['decision_id']!r}"
        )

    seq = len(decisions) + 1
    entry = {
        "seq": seq,
        "decision_id": f"HD-{seq:04d}",
        "review_snapshot_id": snapshot_id,
        "target_id": target,
        "claim_id": claim_id,
        "doc_id": doc_id,
        "field": field,
        "decision": decision,
        "corrected_value": corrected_value,
        "rationale": rationale,
        "adjudicator": adjudicator,
        "decided_at": decided_at,
        "supersedes_decision_id": supersedes_decision_id,
    }
    with (run_dir / "adjudication_ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return entry


def adjudicate_and_render(run_dir: Path, **kwargs) -> dict:
    """先记裁决(权威),再重渲 panel(投影)。顺序不可逆,渲染失败不回滚:
    decision_recorded 永远为真时才落盘;panel_refreshed 为假就提示 render 命令。"""
    entry = append_adjudication(run_dir, **kwargs)
    result = {"decision": entry, "decision_recorded": True, "panel_refreshed": False}
    try:
        from .panel import render_panel_from_run

        render_panel_from_run(run_dir)
        result["panel_refreshed"] = True
    except Exception as exc:  # noqa: BLE001 —— 渲染失败不撤销已落盘的裁决
        result["render_error"] = repr(exc)
    return result


def build_audit_bundle(run_dir: Path) -> Path:
    """audit_bundle.zip:冻结工件 + crops + MANIFEST(每文件 sha256)。

    必备工件缺失 → FileNotFoundError(阻断,不打半个包)。
    """
    run_dir = Path(run_dir)
    missing = [name for name in REQUIRED_ARTIFACTS if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"audit bundle 缺工件,阻断:{missing}")

    members: list[Path] = [run_dir / name for name in REQUIRED_ARTIFACTS]
    for asset_dir in ("crops", "pages"):
        directory = run_dir / asset_dir
        if directory.exists():
            members.extend(sorted(directory.glob("*.png")))

    manifest_lines = []
    for path in members:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {path.relative_to(run_dir)}")
    manifest = "\n".join(manifest_lines) + "\n"

    bundle = run_dir / "audit_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.sha256", manifest)
        for path in members:
            zf.write(path, path.relative_to(run_dir))
    return bundle
