"""输入指纹与复核快照 —— 不可变 run 的身份层。

两个确定性哈希,都不读墙钟:

- **input_manifest.fingerprint**:这批输入(PDF + 独立 OCR + DWS 存盘响应 +
  抽取 schema)是什么。同样输入重跑 = 重放既有 run,不新开;输入变了才开新 run。
- **review_snapshot.review_snapshot_id**:复核者当时看到的完整快照
  (输入清单 + 工件注册表 + 证据片段注册表 + 冻结账本 + 门禁报告)。
  人工裁决绑定它 —— 只绑账本的话,同一账本配上被替换的证据检测不到。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .evidence import sha256_file
from .ocr import layout, ocr_path, pdf_path

#: review_snapshot_id 覆盖的成分 —— 权威冻结工件,不含投影(矩阵/panel 可重算)
SNAPSHOT_COMPONENTS = (
    "input_manifest.json",
    "artifact_registry.json",
    "evidence_span_registry.json",
    "field_ledger.json",
    "gate_report.json",
    "routing_report.json",
)


def _sha_or_none(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _adaptive_token(root: Path) -> str:
    from .adaptive import adaptive_fingerprint_token
    return adaptive_fingerprint_token(root)


def _code_revision() -> str | None:
    """当前代码的 git commit —— 门禁与规范化规则就是「策略」,策略的版本
    就是代码版本(78 评 P4)。装在非 git 环境(如打包安装)则为 None,
    如实记 null,不编造。"""
    import subprocess

    repo = Path(__file__).resolve().parent.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def build_input_manifest(doc_ids: list[str], *, include_vision: bool = True) -> dict:
    """这批输入的内容清单 + 指纹。缺的成分记 null,不阻断
    (缺 DWS 响应是 extraction_present 门禁的事,不是清单的事)。

    include_vision:读图作答(vision/answers6.*.tsv)也进草稿,必须进指纹 —
    否则改了读图答案,重放会错误地返回旧 run。--no-vision 的 run 不消费
    它们,指纹也不含(改了不影响该 run 的输入)。
    """
    from .dws import MODES, response_path
    from .ocr import derisk_root

    docs = []
    for doc_id in sorted(doc_ids):
        docs.append({
            "doc_id": doc_id,
            "pdf_sha256": _sha_or_none(pdf_path(doc_id)),
            "ocr_sha256": _sha_or_none(ocr_path(doc_id)),
            "raw_sha256": {mode: _sha_or_none(response_path(doc_id, mode))
                           for mode in MODES},
        })
    vision_sha256 = None
    if include_vision:
        # 盘上有几个 answers6 文件就哈希几个 —— vision-ingest 新接的读者
        # (tag D、E…)不在 VISION_READERS 名单里,只按名单哈希会把新读者
        # 漏出指纹,改了作答旧 run 照样被重放
        shas = {
            path.name: _sha_or_none(path)
            for path in sorted((derisk_root() / "vision").glob("answers6.*.tsv"))
        } if (derisk_root() / "vision").is_dir() else {}
        # 一个读图文件都不存在时(典型:workspace),归一成 None ——
        # 否则 --vision/--no-vision 会产出两个不同指纹,而实际上两边
        # 消费的输入完全相同(空气),重放会在 CLI 与工作台之间失灵
        if any(shas.values()):
            vision_sha256 = shas
    # schema 只有产品路径(workspace)知道:ingest 用本包的 extraction_schema;
    # derisk 存盘响应是校准仓库抽的,schema 不在本仓库手里,诚实记 null
    schema_sha256 = None
    if layout() == "workspace":
        from .ingest import extraction_schema

        schema_sha256 = hashlib.sha256(
            json.dumps(extraction_schema(), sort_keys=True).encode()
        ).hexdigest()
    from .harness import load_active

    active = load_active(derisk_root())
    manifest = {"layout": layout(), "schema_sha256": schema_sha256,
                "vision_sha256": vision_sha256, "docs": docs}
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    # 输入指纹只含输入(裁决:评审二分)—— 证明两批 run 处理的是同一份证据;
    # 代码/harness 不许进来,那是执行身份的事
    manifest["fingerprint"] = hashlib.sha256(canonical).hexdigest()
    # 执行身份 = 输入 + 代码 + harness + 路由引擎版本(v0.2 P0-4 /
    # 评审裁决二):同输入换策略/换代码 = 不同执行身份,不许重放
    execution = {
        "input_fingerprint": manifest["fingerprint"],
        "code_revision": _code_revision(),
        "harness_id": active["harness_id"],
        "harness_digest": active["policy_digest"],
        "schema_digest": active.get("schema_digest") or "none",
        "routing_engine": "routing-v1",
        "adaptive": _adaptive_token(derisk_root()),
    }
    manifest.update(execution)
    manifest["execution_fingerprint"] = hashlib.sha256(
        json.dumps(execution, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return manifest


def snapshot_id_from_components(components: dict[str, str | None]) -> str:
    """成分哈希 → 快照 id。bundle verify 在 zip 内重算时也走这里。

    只哈希 components 里**存在**的键(按 SNAPSHOT_COMPONENTS 序):
    routing_report.json 是 2026-08-05 才进成分表的 —— 旧 run/旧包没有它,
    按旧成分集重算才能与旧快照 id 相符(旧 run 不可变,id 不许漂移)。
    新 run 落了 routing_report.json 则进成分,删除它 → 快照对不上 → 阻断。
    """
    h = hashlib.sha256()
    for name in SNAPSHOT_COMPONENTS:
        if name in components:
            h.update(f"{name}={components.get(name)}\n".encode())
    return h.hexdigest()


def compute_review_snapshot(run_dir: Path) -> dict:
    """从 run 目录的工件字节推导复核快照。成分缺失记 null(v1 旧 run 没有
    input_manifest.json,快照仍确定 —— 旧 run 不可变,推导结果不变);
    routing_report.json 只在文件存在时进成分(见 snapshot_id_from_components)。"""
    run_dir = Path(run_dir)
    components = {}
    for name in SNAPSHOT_COMPONENTS:
        path = run_dir / name
        if not path.exists():
            if name == "routing_report.json":
                continue  # 旧 run 无此工件:不进成分,不是记 null(见上)
            components[name] = None
        else:
            components[name] = _sha_or_none(path)
    return {"review_snapshot_id": snapshot_id_from_components(components),
            "components": components}


def load_or_derive_snapshot(run_dir: Path) -> dict:
    """优先读 run 落盘的 review_snapshot.json;v1 旧 run 没有就现场推导
    (确定性,不写回 —— 旧 run 保持原样)。"""
    path = Path(run_dir) / "review_snapshot.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return compute_review_snapshot(run_dir)


def find_run_by_fingerprint(runs_dir: Path, fingerprint: str) -> Path | None:
    """runs/ 下是否已有同样**执行指纹**的完整 run —— 有就重放它,不新开。

    传入的是 execution_fingerprint(输入+代码+harness);旧 run 的
    input_manifest 没有该字段时回退匹配它的 legacy fingerprint ——
     legacy 指纹不含执行身份,与新执行指纹必然不等 → 自动开新代,
    安全方向。半拉子 run(有 input_manifest 但没有 event_log)不算。
    """
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return None
    for candidate in sorted(runs_dir.glob("run-*/input_manifest.json")):
        if not (candidate.parent / "event_log.jsonl").exists():
            continue
        try:
            manifest = json.loads(candidate.read_text(encoding="utf-8"))
            recorded = manifest.get("execution_fingerprint",
                                    manifest.get("fingerprint"))
            if recorded != fingerprint:
                continue
            snapshot_path = candidate.parent / "review_snapshot.json"
            if snapshot_path.exists():
                stored = json.loads(snapshot_path.read_text(encoding="utf-8"))
                if compute_review_snapshot(candidate.parent)["review_snapshot_id"] != \
                        stored.get("review_snapshot_id"):
                    continue
            return candidate.parent
        except json.JSONDecodeError:
            continue
    return None


def allocate_run_dir(runs_dir: Path) -> Path:
    """下一个 run-NNNN。只增不改:既有 run 永远原样保留。"""
    runs_dir = Path(runs_dir)
    existing = [int(p.name.split("-", 1)[1]) for p in runs_dir.glob("run-*")
                if p.name.split("-", 1)[-1].isdigit()]
    return runs_dir / f"run-{(max(existing) + 1) if existing else 1:04d}"
