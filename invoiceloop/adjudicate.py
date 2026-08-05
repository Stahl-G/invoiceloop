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
import zlib
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows 无 fcntl:跨进程锁退化,进程内 threading.Lock 仍在
    fcntl = None

from .fields import FIELDS
from .review import load_decisions, project, target_id_for
from .snapshot import load_or_derive_snapshot
from . import __version__

DECISIONS = ("accept", "confirm_absent", "not_applicable",
             "reject", "correct", "abstain")

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
    reason_code: str | None = None,
) -> dict:
    """追加一条裁决并 fsync。时间由调用方注入 —— 工件本身不读墙钟(可复算)。

    校验失败 → ValueError,一行都不写;写成功就是写成功(调用方做渲染,
    渲染失败不回滚这里)。reason_code 可选(v0.2 反馈平面):人给,
    系统不代填;给了必须在最小心码集内。
    """
    run_dir = Path(run_dir)
    if reason_code is not None:
        from .feedback import REASON_CODES

        if reason_code not in REASON_CODES:
            raise ValueError(
                f"reason_code {reason_code!r} 不在最小心码集 {REASON_CODES} 内")
    run_dir = Path(run_dir)
    if decision not in DECISIONS:
        raise ValueError(f"decision 必须是 {DECISIONS} 之一,收到 {decision!r}")
    if decision == "correct":
        if not (corrected_value and corrected_value.strip()):
            raise ValueError("correct 必须带 corrected_value —— 修正值是什么必须写出来")
        corrected_value = corrected_value.strip()
    elif corrected_value is not None:
        raise ValueError(f"{decision} 禁止携带 corrected_value —— 修正只能走 correct")
    # 决策语义拆分(81 评 P0):「接受声明」「确认页面没有」「不适用」是三种
    # 不同的东西,以前全塞在 accept 里,交付层分不出 缺失 与 人看不懂
    if decision == "accept" and claim_id is None:
        raise ValueError(
            "accept 必须带 claim_id —— 接受的是哪条冻结声明必须指明;"
            "要表达「页面上确实没有这个字段」用 confirm_absent,"
            "「该文档不适用此字段」用 not_applicable"
        )
    if decision in ("confirm_absent", "not_applicable") and claim_id is not None:
        raise ValueError(
            f"{decision} 针对无声明的槽位;这个槽位有冻结声明 {claim_id},"
            f"声明错了用 reject 或 correct"
        )
    if field not in FIELDS:
        raise ValueError(f"field {field!r} 不是受评字段({sorted(FIELDS)} 之一)")
    if not (decided_at and str(decided_at).strip()):
        raise ValueError("decided_at 不能为空 —— 裁决时间由人给出,不由系统代填")
    decided_at = str(decided_at).strip()
    from datetime import datetime

    try:
        datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"decided_at {decided_at!r} 不是 ISO 8601 时间 —— 账本里的时间必须"
            f"可机读,「下礼拜吧」进不了审计轨迹(82 评 P2)"
        ) from None

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
        # 投影↔权威交叉检查(81 评 P0):support_matrix 不在快照成分内
        # (可重建投影),但它若与冻结账本同槽位值不符,说明 run 之后有
        # 工件被动过 —— 在被动过的证据上不记裁决,先查清
        matrix_path = run_dir / "support_matrix.json"
        if matrix_path.exists():
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            row = next((r for r in matrix["rows"]
                        if r["doc_id"] == doc_id and r["field"] == field), None)
            if row is not None and row.get("claim_id") == claim_id \
                    and row.get("value") != claim["value"]:
                raise ValueError(
                    f"support_matrix 该槽位的值 {row.get('value')!r} 与冻结声明 "
                    f"{claim['value']!r} 不符 —— 投影与权威分叉,run 之后有工件"
                    f"被改动过。先查清再裁决"
                )

    target = target_id_for(snapshot_id, doc_id, field)
    # 临界区开始:加载 → tip/supersede 校验 → seq 分配 → 追加,全程持锁。
    # threading.Lock 管进程内线程(2026-08-03 并发实测抓出重复 decision_id);
    # flock 管跨进程(两个 workbench/CLI 同时追加同一 run —— 82 评 P2)。
    # 锁文件本身不是工件,不进账本不进快照。
    with _APPEND_LOCK:
        lock_fh = (run_dir / "adjudication_ledger.lock").open("a+")
        try:
            if fcntl is not None:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
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
            if reason_code is not None:
                entry["reason_code"] = reason_code
            with (run_dir / "adjudication_ledger.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return entry
        finally:
            if fcntl is not None:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()


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

    # 上游证据在 run 目录外,按 run 时记录的根解析(不看当前环境变量)。
    # 主变量与别名同设:评委环境里 export 过 INVOICELOOP_CORPUS 的话,
    # 只设别名会被遮蔽,bundle 直接读错根(81 评 P1-1 的第二处产品侧孪生)
    prev_env = {k: os.environ.get(k)
                for k in ("INVOICELOOP_CORPUS", "INVOICELOOP_DWS_DERISK")}
    if run_manifest.get("derisk_root"):
        os.environ["INVOICELOOP_CORPUS"] = run_manifest["derisk_root"]
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
        vision_members: list[tuple[str, bytes]] = []
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
        recorded_vision = input_manifest.get("vision_sha256") or {}
        for name in sorted(set(run_manifest.get("vision_captured", []))):
            # Names are generated from answers6.*.tsv and must not escape the
            # run-local evidence directory.
            if Path(name).name != name or not name.startswith("answers6."):
                raise FileNotFoundError(f"audit bundle 读图文件名非法,阻断:{name!r}")
            path = run_dir / "vision" / name
            arcname = f"vision/{name}"
            expected = recorded_vision.get(name)
            if expected is None:
                missing_up.append(arcname)
            elif not path.exists():
                missing_up.append(arcname)
            elif sha256_file(path) != expected:
                swapped.append(arcname)
            else:
                vision_members.append((arcname, path.read_bytes()))
        if missing_up or swapped:
            raise FileNotFoundError(
                f"audit bundle 上游证据与 run 时记录不符,阻断:"
                f"丢失={missing_up} 被换={swapped}"
            )

        members: list[tuple[str, bytes]] = [
            (name, (run_dir / name).read_bytes()) for name in REQUIRED_ARTIFACTS
        ]
        # deliverable.json 是可选派生物(2026-08-05 起的 run 才有;旧 run 没有
        # 不阻断 —— 与 panel 同级,纯投影,收件人可从包内工件重算)
        deliverable = run_dir / "deliverable.json"
        if deliverable.exists():
            members.append(("deliverable.json", deliverable.read_bytes()))
        # routing_report.json 同理(2026-08-05 起,进快照成分):旧 run 没有它,
        # 旧快照的成分表也没有它,两处一致,不阻断
        routing_report = run_dir / "routing_report.json"
        if routing_report.exists():
            members.append(("routing_report.json", routing_report.read_bytes()))
        for asset_dir in ("crops", "pages"):
            directory = run_dir / asset_dir
            if directory.exists():
                members.extend(
                    (f"{asset_dir}/{p.name}", p.read_bytes())
                    for p in sorted(directory.glob("*.png"))
                )
        members.extend(vision_members)
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
        if run_manifest.get("vision_captured"):
            notes.append("读图原始作答文件已复制进 run/bundle,可离线重放工作台建议")
        elif run_manifest.get("include_vision"):
            notes.append("读图作答的值已并入 field_drafts.json;本 run 未捕获原始作答文件")
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
            for key, value in prev_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

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

    报告带 layers:每层独立 True/False/None —— v1 包没有快照层,
    ok=true 不许掩盖「只过了成员级」的等级差异(评审 P2)。
    信任根说明:三层全过证明「包自内洽且未被单点篡改」;包的真实性锚
    在带外公布的本包 sha256 —— verify 不能自己当自己的信任根。
    """
    bundle = Path(bundle)
    failures: list[str] = []
    notes: list[str] = []
    layers: dict[str, bool | None] = {"members": True, "snapshot": None,
                                        "binding": None, "semantics": None}
    members = 0
    try:
        zf = zipfile.ZipFile(bundle)
    except zipfile.BadZipFile as exc:
        return {"ok": False, "failures": [f"不是合法的 zip/bundle:{exc}"],
                "members": 0, "layers": {"members": False, "snapshot": None,
                                          "binding": None, "semantics": None}, "notes": notes}
    with zf:
        names = set(zf.namelist())
        if "MANIFEST.sha256" not in names:
            return {"ok": False, "failures": ["缺 MANIFEST.sha256"], "members": 0,
                    "layers": {"members": False, "snapshot": None, "binding": None,
                            "semantics": None},
                    "notes": notes}
        try:
            manifest_text = zf.read("MANIFEST.sha256").decode()
        except zipfile.BadZipFile:
            return {"ok": False, "failures": ["MANIFEST.sha256 成员损坏(CRC)"],
                    "members": 0,
                    "layers": {"members": False, "snapshot": None, "binding": None,
                            "semantics": None},
                    "notes": notes}
        declared: dict[str, str] = {}
        for line in manifest_text.splitlines():
            if line.strip():
                if "  " not in line:
                    failures.append(f"MANIFEST 行不可解析:{line[:60]!r}")
                    layers["members"] = False
                    continue
                digest, rel = line.split("  ", 1)
                declared[rel] = digest
        member_bytes: dict[str, bytes] = {}
        for rel, digest in declared.items():
            if rel not in names:
                failures.append(f"缺成员:{rel}")
                layers["members"] = False
                continue
            try:
                data = zf.read(rel)
            except (zipfile.BadZipFile, zlib.error, OSError) as exc:
                # 成员级损坏(CRC / 压缩流):结构化失败,永不许裸 traceback ——
                # verify 是交付信任的工具(双评 P1-3)
                failures.append(f"成员损坏({type(exc).__name__}):{rel}")
                layers["members"] = False
                continue
            member_bytes[rel] = data
            members += 1
            if hashlib.sha256(data).hexdigest() != digest:
                failures.append(f"哈希不符:{rel}")
                layers["members"] = False
        extra = sorted(names - set(declared) - {"MANIFEST.sha256"})
        if extra:
            failures.append(f"未登记成员:{extra}")
            layers["members"] = False

        if "review_snapshot.json" in names:
            from .snapshot import SNAPSHOT_COMPONENTS, snapshot_id_from_components

            snap: dict | None = None
            try:
                snap = json.loads(member_bytes.get("review_snapshot.json")
                                  or zf.read("review_snapshot.json"))
            except (zipfile.BadZipFile, zlib.error, OSError,
                    UnicodeDecodeError, json.JSONDecodeError) as exc:
                failures.append(f"review_snapshot.json 不可读:{type(exc).__name__}")
                layers["snapshot"] = False
                layers["binding"] = False
            if snap is not None:
                # 按包内快照**记录的成分集**重算(不是当前 SNAPSHOT_COMPONENTS
                # 常量):routing_report.json 2026-08-05 才进成分表,旧包按旧
                # 成分集验;成分被记进快照却缺成员 → None ≠ 记录的 sha → 抓
                recorded = snap.get("components") or {}
                recomputed = {
                    name: (hashlib.sha256(member_bytes[name]).hexdigest()
                           if name in member_bytes else None)
                    for name in recorded
                }
                layers["snapshot"] = (
                    snapshot_id_from_components(recomputed) == snap.get("review_snapshot_id"))
                if not layers["snapshot"]:
                    failures.append(
                        "review_snapshot 成分与快照 id 不符 —— 快照内工件被替换过")
                snapshot_id = snap.get("review_snapshot_id")
                layers["binding"] = None
                if "adjudication_ledger.jsonl" in names:
                    seen_ids: set[str] = set()
                    parsed: list[dict] = []
                    ledger_lines: list[str] = []
                    try:
                        ledger_lines = (zf.read("adjudication_ledger.jsonl")
                                        .decode().splitlines())
                    except (zipfile.BadZipFile, zlib.error, OSError,
                            UnicodeDecodeError) as exc:
                        failures.append(
                            f"adjudication_ledger.jsonl 不可读:{type(exc).__name__}")
                        layers["binding"] = False
                    for raw in ledger_lines:
                        if not raw.strip():
                            continue
                        try:
                            entry = json.loads(raw)
                        except json.JSONDecodeError:
                            failures.append("裁决账本含不可解析行 —— 账本完整性已破坏")
                            layers["binding"] = False
                            continue
                        parsed.append(entry)
                        # 重复 decision_id = 账本曾被并发写坏的指纹(2026-08-03 复核前
                        # append 无锁,两个线程能写出两个 HD-0001)
                        decision_id = entry.get("decision_id")
                        if decision_id:
                            if decision_id in seen_ids:
                                failures.append(
                                    f"decision_id 重复:{decision_id} —— 账本完整性已破坏")
                                layers["binding"] = False
                            seen_ids.add(decision_id)
                        if ("review_snapshot_id" in entry
                                and entry["review_snapshot_id"] != snapshot_id):
                            failures.append(
                                f"裁决 {entry.get('decision_id', entry.get('seq'))} "
                                f"绑定的快照与包内快照不符")
                            layers["binding"] = False
                    if parsed:
                        layers["binding"] = layers["binding"] is not False
                        # 链投影重放(78.5 评 P1):只查「每条绑这个快照」不够 ——
                        # 伪造一条自洽但内部矛盾的链(悬挂 supersedes、跨槽位、
                        # 前向引用成环、同槽多 tip)在成员级与快照级都抓不到,
                        # 只有重放 review.project 的链语义才现形
                        shaped = [e for e in parsed
                                  if e.get("decision_id") and e.get("target_id")]
                        if len(shaped) != len(parsed):
                            failures.append(
                                "裁决行缺 decision_id/target_id —— "
                                "v2 包不许含 v1 形态的行")
                            layers["binding"] = False
                        by_id = {e["decision_id"]: e for e in shaped}
                        for entry in shaped:
                            sup = entry.get("supersedes_decision_id")
                            if sup is None:
                                continue
                            pointed = by_id.get(sup)
                            if pointed is None:
                                failures.append(
                                    f"裁决 {entry.get('decision_id')} 的 supersedes "
                                    f"指向不存在的 {sup}")
                                layers["binding"] = False
                            elif pointed.get("target_id") != entry.get("target_id"):
                                failures.append(
                                    f"裁决 {entry.get('decision_id')} 的 supersedes "
                                    f"跨槽位指向 {sup}")
                                layers["binding"] = False
                            elif pointed.get("seq", 0) >= entry.get("seq", 0):
                                failures.append(
                                    f"裁决 {entry.get('decision_id')} 的 supersedes "
                                    f"指向不早于自己的 {sup}(链成环)")
                                layers["binding"] = False
                        # 裁决必须绑定正确的槽位和冻结声明,不能只拿一个真实
                        # claim_id 改写 doc/field 后伪造另一条裁决。
                        try:
                            ledger_doc = json.loads(
                                member_bytes.get("field_ledger.json")
                                or zf.read("field_ledger.json"))
                            claims_by_id = {
                                c.get("claim_id"): c
                                for c in ledger_doc.get("claims", [])
                                if c.get("claim_id") is not None
                            }
                            run_manifest_doc = json.loads(
                                member_bytes.get("run_manifest.json")
                                or zf.read("run_manifest.json"))
                            allowed_docs = set(run_manifest_doc.get("docs", []))
                            for entry in parsed:
                                doc_id = entry.get("doc_id")
                                field_name = entry.get("field")
                                if doc_id not in allowed_docs:
                                    failures.append(
                                        f"裁决 {entry.get('decision_id')} 指向包外文档"
                                        f" {doc_id!r}")
                                    layers["binding"] = False
                                if field_name not in FIELDS:
                                    failures.append(
                                        f"裁决 {entry.get('decision_id')} 指向非法字段"
                                        f" {field_name!r}")
                                    layers["binding"] = False
                                expected_target = target_id_for(
                                    snapshot_id, doc_id, field_name)
                                if entry.get("target_id") != expected_target:
                                    failures.append(
                                        f"裁决 {entry.get('decision_id')} 的 target_id"
                                        " 与 doc/field/snapshot 不一致")
                                    layers["binding"] = False
                                cid = entry.get("claim_id")
                                if cid is not None:
                                    claim = claims_by_id.get(cid)
                                    if claim is None:
                                        failures.append(
                                            f"裁决 {entry.get('decision_id')} 指向包内"
                                            f"不存在的 claim {cid}")
                                        layers["binding"] = False
                                    elif (claim.get("doc_id") != doc_id
                                          or claim.get("field") != field_name):
                                        failures.append(
                                            f"裁决 {entry.get('decision_id')} 的 claim"
                                            f" {cid} 与 doc/field 不一致")
                                        layers["binding"] = False
                        except (zipfile.BadZipFile, zlib.error, OSError,
                                UnicodeDecodeError, json.JSONDecodeError):
                            pass  # 账本成员自身的损坏已在成员级记过,不重复
                        # decision 语义不变量重放(与 append 同规):correct 必带
                        # 修正值、其余禁带、decision 必须合法 —— 伪造账本过不了
                        for entry in parsed:
                            if entry.get("decision") not in DECISIONS:
                                failures.append(
                                    f"裁决 {entry.get('decision_id')} 的 decision "
                                    f"非法:{entry.get('decision')!r}")
                                layers["binding"] = False
                            elif entry["decision"] == "correct" and not (
                                    entry.get("corrected_value") or "").strip():
                                failures.append(
                                    f"裁决 {entry.get('decision_id')} correct "
                                    f"缺 corrected_value")
                                layers["binding"] = False
                            elif entry["decision"] != "correct" and \
                                    entry.get("corrected_value") is not None:
                                failures.append(
                                    f"裁决 {entry.get('decision_id')} "
                                    f"{entry['decision']} 禁带 corrected_value")
                                layers["binding"] = False
                        from .review import project

                        for target, slot in project(shaped).items():
                            if slot["conflict"]:
                                failures.append(
                                    f"槽位 {target} 的裁决链多条 tip —— "
                                    f"链内部矛盾,自洽伪造也过不了这层")
                                layers["binding"] = False
                    elif layers["binding"] is not False:
                        # 零裁决的包没有可绑定的对象:记 None 而不是真空理 True,
                        # 与 snapshot 层「v1 包记 None」的诚实标记一致(81 评 P2)
                        notes.append("包内裁决账本为空:无裁决可绑定,绑定层记 None")
        else:
            notes.append("v1 形态的包:无 review_snapshot,校验深度止于成员级;"
                         "v2 包(2026-08-03 之后)才有快照与绑定两层")

        # ---- 第 4 层 语义层(81 评 P0):投影成员(support_matrix/deliverable)
        # 不在快照成分内 —— 改了它们,前三层全过。这一层把投影值与包内
        # 权威(field_ledger / adjudication_ledger)交叉比对:接受值必须等于
        # 冻结声明值,修正值必须等于裁决修正值
        layers["semantics"] = None
        try:
            if "field_ledger.json" in member_bytes:
                ledger_doc = json.loads(member_bytes["field_ledger.json"])
                claim_values = {c.get("claim_id"): c.get("value")
                                for c in ledger_doc.get("claims", [])}
                layers["semantics"] = True
                if "support_matrix.json" in member_bytes:
                    matrix_doc = json.loads(member_bytes["support_matrix.json"])
                    for row in matrix_doc.get("rows", []):
                        cid = row.get("claim_id")
                        if cid and cid in claim_values \
                                and row.get("value") != claim_values[cid]:
                            failures.append(
                                f"support_matrix 行 {row.get('doc_id')}/"
                                f"{row.get('field')} 的值与冻结声明 {cid} 不符 —— "
                                f"投影被改过(前三层抓不到投影篡改)")
                            layers["semantics"] = False
                if "deliverable.json" in member_bytes:
                    deliv = json.loads(member_bytes["deliverable.json"])
                    decisions_by_id: dict[str, dict] = {}
                    if "adjudication_ledger.jsonl" in member_bytes:
                        for raw in (member_bytes["adjudication_ledger.jsonl"]
                                    .decode().splitlines()):
                            if raw.strip():
                                entry = json.loads(raw)
                                if entry.get("decision_id"):
                                    decisions_by_id[entry["decision_id"]] = entry
                    for doc_id, doc in deliv.get("docs", {}).items():
                        for field_name, fslot in doc.get("fields", {}).items():
                            status = fslot.get("status")
                            decision = decisions_by_id.get(fslot.get("source") or "")
                            if status == "accepted":
                                cid = (decision or {}).get("claim_id")
                                if decision is None or cid not in claim_values:
                                    failures.append(
                                        f"deliverable {doc_id}/{field_name} 的接受值"
                                        f"找不到对应裁决与冻结声明")
                                    layers["semantics"] = False
                                elif fslot.get("value") != claim_values[cid]:
                                    failures.append(
                                        f"deliverable {doc_id}/{field_name} 的接受值"
                                        f"与冻结声明 {cid} 不符 —— 投影与权威分叉")
                                    layers["semantics"] = False
                            elif status == "corrected":
                                if decision is None or fslot.get("value") \
                                        != decision.get("corrected_value"):
                                    failures.append(
                                        f"deliverable {doc_id}/{field_name} 的修正值"
                                        f"与裁决 {fslot.get('source')} 不符")
                                    layers["semantics"] = False
                            elif status in ("rejected", "confirmed_absent",
                                            "not_applicable", "abstained"):
                                if fslot.get("value") is not None:
                                    failures.append(
                                        f"deliverable {doc_id}/{field_name} "
                                        f"{status} 槽不许带值")
                                    layers["semantics"] = False
                            elif status == "accepted_unbound":
                                failures.append(
                                    f"deliverable {doc_id}/{field_name} 自标"
                                    f"accepted_unbound —— 完整性已破坏")
                                layers["semantics"] = False
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
            layers["semantics"] = False
            failures.append("语义层:包内投影/账本成员不可解析")
        if layers["members"] and layers["snapshot"] and layers["binding"] \
                and layers["semantics"]:
            notes.append("四层全过 = 包内自洽且未被单点篡改;包的真实性锚在"
                         "带外公布的本包 sha256 —— verify 不是自己的信任根")
        elif layers["members"] and layers["snapshot"] and layers["binding"]:
            notes.append("三层全过 = 包内自洽且未被单点篡改;包的真实性锚在"
                         "带外公布的本包 sha256 —— verify 不是自己的信任根")
    return {"ok": not failures, "failures": failures, "members": members,
            "layers": layers, "notes": notes}
