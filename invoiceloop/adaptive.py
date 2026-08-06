"""L1 自适应二次抽取(opt-in):understand → 风险诊断 → 必要时 agentic。

默认产品路径仍是双模式全跑(README:cross_mode_agreement 门依赖 agentic)。
本模块只服务 `--adaptive` ingest:故意跳过 agentic 的干净文档不得被
gates 当成「agentic 缺失阻断」。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fields import FIELD_KINDS, TIER1
from .gates import _c1_c3, _wellformed_failure

ATTEMPTS_DIR = "attempts"


def _present(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def diagnose_risk(understand_data: dict[str, Any] | None) -> list[str]:
    """文档级风险理由。非空 ⇒ 应 escalate 到 agentic。"""
    reasons: list[str] = []
    if not isinstance(understand_data, dict):
        return ["understand_data_missing"]
    for field in sorted(TIER1):
        if not _present(understand_data.get(field)):
            reasons.append(f"tier1_missing:{field}")
    failed = _c1_c3(understand_data)
    for check_id in sorted(failed):
        reasons.append(f"arithmetic:{check_id}")
    for field, value in sorted(understand_data.items()):
        # DWS 常回 invoice_type/currency/seller_country 等非受评键;
        # FIELD_KINDS 外字段一律忽略(2026-08-06:漏守卫 → KeyError 必崩)
        if field not in FIELD_KINDS:
            continue
        if not _present(value):
            continue
        bad = _wellformed_failure(field, value)
        if bad is not None:
            reasons.append(f"wellformed:{field}:{bad}")
    return reasons


def attempts_root(workspace: Path) -> Path:
    return Path(workspace) / ATTEMPTS_DIR


def write_attempt_record(
    workspace: Path,
    doc_id: str,
    *,
    escalated: bool,
    reasons: list[str],
    understand_status: int | None,
    agentic_status: int | None,
) -> Path:
    """落盘 attempts/{doc}/manifest.json(元数据;raw 仍是权威响应)。"""
    root = attempts_root(workspace) / doc_id
    root.mkdir(parents=True, exist_ok=True)
    attempts = [{
        "id": "ATT-0001-understand",
        "mode": "understand",
        "http_status": understand_status,
        "raw": f"raw/{doc_id}.understand.json",
    }]
    if escalated:
        attempts.append({
            "id": "ATT-0002-agentic-escalation",
            "mode": "agentic",
            "status": "escalated",
            "http_status": agentic_status,
            "reasons": reasons,
            "raw": f"raw/{doc_id}.agentic.json",
        })
    else:
        attempts.append({
            "id": "ATT-0002-agentic-escalation",
            "mode": "agentic",
            "status": "skipped_clean",
            "reasons": [],
            "raw": None,
        })
    payload = {
        "doc_id": doc_id,
        "adaptive": True,
        "escalated": escalated,
        "reasons": reasons,
        "attempts": attempts,
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def mark_workspace_adaptive(workspace: Path) -> Path:
    """工作区级标记:snapshot 执行指纹用它区分双模式 vs adaptive。"""
    workspace = Path(workspace)
    path = workspace / "adaptive.json"
    path.write_text(json.dumps({"adaptive": True, "version": "l1-v0"}) + "\n",
                    encoding="utf-8")
    return path


def is_workspace_adaptive(root: Path) -> bool:
    path = Path(root) / "adaptive.json"
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("adaptive"))
    except (json.JSONDecodeError, OSError):
        return False


def load_agentic_policy(root: Path) -> dict[str, str]:
    """doc_id → required | optional_skipped | escalated。

    无 attempts 记录的文档默认 required(双模式/遗漏 agentic 仍阻断)。
    """
    root = Path(root)
    out: dict[str, str] = {}
    base = attempts_root(root)
    if not base.is_dir():
        return out
    for manifest_path in sorted(base.glob("*/manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        doc_id = payload.get("doc_id") or manifest_path.parent.name
        if payload.get("escalated"):
            out[doc_id] = "escalated"
        elif payload.get("adaptive"):
            out[doc_id] = "optional_skipped"
    return out


def adaptive_fingerprint_token(root: Path) -> str:
    """执行指纹分量:非 adaptive → 'dual';否则哈希全部 attempt 清单。"""
    import hashlib

    root = Path(root)
    if not is_workspace_adaptive(root):
        return "dual"
    parts = ["adaptive:l1-v0"]
    base = attempts_root(root)
    if base.is_dir():
        for path in sorted(base.glob("*/manifest.json")):
            parts.append(f"{path.parent.name}:{path.read_bytes().hex()}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
