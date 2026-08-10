"""Batch-level domain scope attestations.

The document class vocabulary answers "what kind of document is this?".  A
domain scope answers "which frozen batch is allowed to use a specialised
harness?".  They are deliberately separate control-plane concepts.

Scope is an explicit, human-approved batch claim.  It is not inferred by a
model and it never changes a slot's decision buttons or applicability.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SCOPE_VERSION = "batch-scope-v1"
BROADCAST_DOMAIN = "us_broadcast_ad_billing"
SCOPE_FILENAME = "domain_scope.json"


def canonical_doc_ids(doc_ids: Sequence[str]) -> list[str]:
    """Return a duplicate-free, deterministic document-id list."""
    values = [str(doc_id) for doc_id in doc_ids]
    if any(not value for value in values):
        raise ValueError("domain scope 不能包含空 doc_id")
    if len(values) != len(set(values)):
        raise ValueError("domain scope 的 doc_id 不能重复")
    return sorted(values)


def doc_ids_digest(doc_ids: Sequence[str]) -> str:
    """Content digest for the exact sorted batch membership."""
    payload = json.dumps(canonical_doc_ids(doc_ids), ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scope_digest(scope: Mapping[str, Any]) -> str:
    """Canonical digest of a validated scope object."""
    payload = json.dumps(dict(scope), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_scope(
    domain: str,
    doc_ids: Sequence[str],
    *,
    approved_by: str,
    approved_at: str,
    evidence_basis: str = "frozen_public_docile_ocr_signals",
) -> dict[str, Any]:
    """Build a human-attested scope; Python owns the membership digest."""
    if not domain or not approved_by or not approved_at:
        raise ValueError("domain、approved_by、approved_at 都不能为空")
    ordered = canonical_doc_ids(doc_ids)
    return {
        "scope_version": SCOPE_VERSION,
        "domain": domain,
        "doc_ids_sha256": doc_ids_digest(ordered),
        "n_docs": len(ordered),
        "evidence_basis": evidence_basis,
        "approved_by": approved_by,
        "approved_at": approved_at,
    }


def validate_scope(
    scope: Mapping[str, Any],
    doc_ids: Sequence[str],
    *,
    required_domain: str | None = None,
) -> dict[str, Any]:
    """Validate scope and exact batch membership, failing closed."""
    if not isinstance(scope, Mapping):
        raise ValueError("domain scope 必须是 JSON object")
    if scope.get("scope_version") != SCOPE_VERSION:
        raise ValueError("domain scope 版本不受支持")
    domain = scope.get("domain")
    if not isinstance(domain, str) or not domain:
        raise ValueError("domain scope 缺少 domain")
    if required_domain is not None and domain != required_domain:
        raise ValueError(
            f"domain scope={domain!r} 与 harness 要求的 {required_domain!r} 不符"
        )
    ordered = canonical_doc_ids(doc_ids)
    if scope.get("n_docs") != len(ordered):
        raise ValueError("domain scope 的 n_docs 与当前批次不符")
    expected = doc_ids_digest(ordered)
    if scope.get("doc_ids_sha256") != expected:
        raise ValueError("domain scope 的 doc_ids_sha256 与当前批次不符")
    for key in ("approved_by", "approved_at", "evidence_basis"):
        if not isinstance(scope.get(key), str) or not scope[key]:
            raise ValueError(f"domain scope 缺少 {key}")
    return dict(scope)


def load_workspace_scope(root: Path) -> dict[str, Any] | None:
    """Load a workspace attestation without silently inventing one."""
    path = Path(root) / SCOPE_FILENAME
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"domain scope 不可读:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("domain scope 顶层必须是 object")
    return value


def require_workspace_scope(
    root: Path,
    doc_ids: Sequence[str],
    required_domain: str | None,
) -> dict[str, Any] | None:
    """Require an exact workspace scope only when a harness asks for one."""
    if required_domain is None:
        return None
    scope = load_workspace_scope(root)
    if scope is None:
        raise ValueError(
            f"当前 harness 要求 domain={required_domain!r},但 workspace 没有 "
            f"{SCOPE_FILENAME};请先完成批次署名"
        )
    return validate_scope(scope, doc_ids, required_domain=required_domain)
