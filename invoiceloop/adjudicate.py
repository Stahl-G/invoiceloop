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
import threading
import zipfile
from pathlib import Path

from .fields import FIELDS
from .review import load_decisions, project, target_id_for
from .snapshot import load_or_derive_snapshot
from . import __version__

DECISIONS = ("accept", "reject", "correct", "abstain")

#: append 的读-改-写临界区(加载 → tip/supersede 校验 → seq 分配 → 追加)
#: 必须串行:工作台是 ThreadingHTTPServer,两个并发 /decide 不打锁会
#: 产出重复的 seq/decision_id —— 冻结账本里出现两个 HD-0001,而且
#: verify 之前查不出来(对抗复核 2026-08-03 实测 261/300 命中)
_APPEND_LOCK = threading.Lock()

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
    # 落盘的快照必须与此刻盘上的工件一致 —— 有人在 run 之后动过工件的话,
    # 裁决会静默绑到一个名存实亡的快照上。不一致 = 阻断,先查清再裁决。
    if (run_dir / "review_snapshot.json").exists():
        from .snapshot import compute_review_snapshot

        current = compute_review_snapshot(run_dir)["review_snapshot_id"]
        if current != snapshot_id:
            raise ValueError(
                "run 目录内工件与 review_snapshot.json 不符 —— 有工件在 run 之后"
                "被改动过。先比对 components 查清哪份被动了,再裁决;"
                "系统不在被动过的证据上记裁决"
            )
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
    # 临界区开始:加载 → tip/supersede 校验 → seq 分配 → 追加,全程持锁
    with _APPEND_LOCK:
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
    """audit_bundle.zip —— 方案 A 全量自包含:冻结工件 + 裁决 + panel
    + 全部上游证据(原始 PDF、独立 OCR、DWS 存盘响应 ×2)+ 抽取 schema
    + bundle_manifest(范围元数据)+ MANIFEST.sha256(逐成员哈希)。

    拿到包的人不需要本机任何东西就能逐项核验(verify_bundle)。
    缺任一上游证据 → FileNotFoundError(阻断,不打半自包含的包 —
    只收派生物、缺上游证据的包会让收包人看到结论却验不了来源)。
    """
    run_dir = Path(run_dir)
    missing = [name for name in REQUIRED_ARTIFACTS if not (run_dir / name).exists()]
    if missing:
        hint = ""
        if any(n in ("input_manifest.json", "review_snapshot.json") for n in missing):
            hint = "(v1 旧 run 缺身份工件 —— 重跑 pipeline 生成 v2 run 再打包;旧 run 不可变,保持原样)"
        raise FileNotFoundError(f"audit bundle 缺工件,阻断:{missing}{hint}")

    run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    docs = run_manifest["docs"]

    # 上游证据在 run 目录外,按 run 时记录的根解析(不看当前环境变量)
    prev_env = os.environ.get("INVOICELOOP_DWS_DERISK")
    if run_manifest.get("derisk_root"):
        os.environ["INVOICELOOP_DWS_DERISK"] = run_manifest["derisk_root"]
    try:
        from .dws import MODES, response_path
        from .evidence import sha256_file
        from .ocr import ocr_path, pdf_path

        # 上游证据的「应该有」以 input_manifest 在 run 时记录的 sha 为准:
        # 记录了 sha → 必须存在且内容一致(run 之后丢失或被换 = 阻断);
        # 记录为 null → run 时就不存在,如实进 notes,不算缺证据。
        # 只查存在性会把"run 之后被换掉"的证据静默打进包。
        input_manifest = json.loads(
            (run_dir / "input_manifest.json").read_text(encoding="utf-8"))
        recorded = {d["doc_id"]: d for d in input_manifest.get("docs", [])}

        upstream: list[tuple[str, bytes]] = []
        missing_up: list[str] = []
        swapped: list[str] = []
        absent_at_run: list[str] = []
        for doc in docs:
            rec = recorded.get(doc, {})
            raw_shas = rec.get("raw_sha256") or {}
            pairs = [
                (pdf_path(doc), f"evidence/pdfs/{doc}.pdf", rec.get("pdf_sha256")),
                (ocr_path(doc), f"evidence/ocr/{doc}.json", rec.get("ocr_sha256")),
            ] + [(response_path(doc, mode), f"evidence/raw/{doc}.{mode}.json",
                  raw_shas.get(mode)) for mode in MODES]
            for path, arcname, recorded_sha in pairs:
                if recorded_sha is None:
                    absent_at_run.append(arcname)
                elif not path.exists():
                    missing_up.append(arcname)
                elif sha256_file(path) != recorded_sha:
                    swapped.append(arcname)
                else:
                    upstream.append((arcname, path.read_bytes()))
        if missing_up or swapped:
            raise FileNotFoundError(
                f"audit bundle 上游证据与 run 时记录不符,阻断:"
                f"丢失={missing_up} 被换={swapped}"
            )

        members: list[tuple[str, bytes]] = [
            (name, (run_dir / name).read_bytes()) for name in REQUIRED_ARTIFACTS
        ]
        for asset_dir in ("crops", "pages"):
            directory = run_dir / asset_dir
            if directory.exists():
                members.extend(
                    (f"{asset_dir}/{p.name}", p.read_bytes())
                    for p in sorted(directory.glob("*.png"))
                )
        members.extend(upstream)

        if run_manifest.get("layout") == "workspace":
            from .ingest import extraction_schema

            members.append(("extraction_schema.json", json.dumps(
                extraction_schema(), indent=1, ensure_ascii=False, sort_keys=True,
            ).encode() + b"\n"))

        snapshot = json.loads((run_dir / "review_snapshot.json").read_text(encoding="utf-8"))
        notes = []
        if absent_at_run:
            notes.append(f"以下上游证据在 run 时就不存在(input_manifest 记录为 null),"
                         f"非打包缺失:{absent_at_run}")
        if run_manifest.get("include_vision"):
            notes.append("读图作答的值已并入 field_drafts.json;原始作答文件在校准档案"
                         "(dws-derisk 第六轮),不在包内 —— 本包唯一的非自包含成分")
        if run_manifest.get("layout") != "workspace":
            notes.append("抽取 schema 由校准档案持有,本仓库无副本"
                         "(input_manifest.schema_sha256 为 null)")
        members.append(("bundle_manifest.json", json.dumps({
            "bundle_scope": "full_run",
            "run_dir_name": run_dir.name,
            "n_docs": len(docs),
            "docs": docs,
            "review_snapshot_id": snapshot["review_snapshot_id"],
            "invoiceloop_version": __version__,
            "notes": notes,
        }, indent=1, ensure_ascii=False).encode() + b"\n"))
    finally:
        if run_manifest.get("derisk_root"):
            if prev_env is None:
                os.environ.pop("INVOICELOOP_DWS_DERISK", None)
            else:
                os.environ["INVOICELOOP_DWS_DERISK"] = prev_env

    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {arcname}\n" for arcname, data in members
    )
    bundle = run_dir / "audit_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.sha256", manifest)
        for arcname, data in members:
            zf.writestr(arcname, data)
    return bundle


def verify_bundle(bundle: Path) -> dict:
    """离线校验 audit bundle。三层,一层比一层深:

    1. 成员级:MANIFEST.sha256 登记的每个成员存在且哈希相符;未登记成员也算篡改
    2. 快照级:用包内成分工件重算 review_snapshot_id —— 攻击者改了工件又
       同步改 MANIFEST 时,成员级抓不到,这一层抓
    3. 绑定级:每条裁决绑定的快照 id 必须等于包内快照 —— 攻击者连快照文件
       一起换时,裁决绑定抓
    """
    bundle = Path(bundle)
    failures: list[str] = []
    members = 0
    try:
        zf = zipfile.ZipFile(bundle)
    except zipfile.BadZipFile as exc:
        return {"ok": False, "failures": [f"不是合法的 zip/bundle:{exc}"], "members": 0}
    with zf:
        names = set(zf.namelist())
        if "MANIFEST.sha256" not in names:
            return {"ok": False, "failures": ["缺 MANIFEST.sha256"], "members": 0}
        declared: dict[str, str] = {}
        for line in zf.read("MANIFEST.sha256").decode().splitlines():
            if line.strip():
                digest, rel = line.split("  ", 1)
                declared[rel] = digest
        for rel, digest in declared.items():
            if rel not in names:
                failures.append(f"缺成员:{rel}")
                continue
            members += 1
            if hashlib.sha256(zf.read(rel)).hexdigest() != digest:
                failures.append(f"哈希不符:{rel}")
        extra = sorted(names - set(declared) - {"MANIFEST.sha256"})
        if extra:
            failures.append(f"未登记成员:{extra}")

        if "review_snapshot.json" in names:
            from .snapshot import SNAPSHOT_COMPONENTS, snapshot_id_from_components

            snap = json.loads(zf.read("review_snapshot.json"))
            recomputed = {
                name: (hashlib.sha256(zf.read(name)).hexdigest() if name in names else None)
                for name in SNAPSHOT_COMPONENTS
            }
            if snapshot_id_from_components(recomputed) != snap.get("review_snapshot_id"):
                failures.append(
                    "review_snapshot 成分与快照 id 不符 —— 快照内工件被替换过")
            snapshot_id = snap.get("review_snapshot_id")
            if "adjudication_ledger.jsonl" in names:
                seen_ids: set[str] = set()
                for raw in zf.read("adjudication_ledger.jsonl").decode().splitlines():
                    if not raw.strip():
                        continue
                    entry = json.loads(raw)
                    # 重复 decision_id = 账本曾被并发写坏的指纹(2026-08-03 复核前
                    # append 无锁,两个线程能写出两个 HD-0001)
                    decision_id = entry.get("decision_id")
                    if decision_id:
                        if decision_id in seen_ids:
                            failures.append(
                                f"decision_id 重复:{decision_id} —— 账本完整性已破坏")
                        seen_ids.add(decision_id)
                    if ("review_snapshot_id" in entry
                            and entry["review_snapshot_id"] != snapshot_id):
                        failures.append(
                            f"裁决 {entry.get('decision_id', entry.get('seq'))} "
                            f"绑定的快照与包内快照不符")
    return {"ok": not failures, "failures": failures, "members": members}
