"""Which fields gate payment posting.

Absence of ``release_profile`` in a routing policy is census: every scored
field's pending / pending_tier1 / abstain keeps the document from
``ready_for_approval``. Packaged HAR-0001 stays that way so sealed replay
does not drift.

A profile does not relax routing, does not forge a human accept, and does
not take TIER1 auto-accepts off ``pending_tier1``. It only answers "which
field statuses block posting". Document-level approve remains the only
path to export (``approve.py``).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .fields import FIELDS

#: Frozen payment-required set. Same three names as
#: ``scripts/doc_touch_economics.py`` 「付款必需(3 个)」. Changing the
#: membership requires a new profile id.
PAYMENT_REQUIRED_V1: tuple[str, ...] = (
    "invoice_number", "seller_name", "amount_due",
)

#: Optional wider posting set. Not the product default.
POSTING_REQUIRED_V1: tuple[str, ...] = (
    "invoice_number", "seller_name", "amount_due",
    "issue_date", "seller_vat_id",
)

_FROZEN: dict[str, tuple[str, ...]] = {
    "payment_required_v1": PAYMENT_REQUIRED_V1,
    "posting_required_v1": POSTING_REQUIRED_V1,
}

#: Field statuses that block posting under census (no profile).
CENSUS_BLOCKING_STATUSES = frozenset({"pending", "pending_tier1", "abstained"})
#: Under a profile, TIER1 auto-accept stays labelled pending_tier1 but
#: does not keep the document from ready_for_approval.
PROFILE_BLOCKING_STATUSES = frozenset({"pending", "abstained"})

AUTO_ROUTES = frozenset({"auto_accept", "auto_absent"})


def parse_release_profile(policy: Mapping[str, Any] | None) -> dict | None:
    """Return the validated profile or None (census). Unknown id fails closed."""
    if not policy:
        return None
    raw = policy.get("release_profile")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("release_profile 必须是 JSON object")
    pid = raw.get("id")
    if not isinstance(pid, str) or pid not in _FROZEN:
        raise ValueError(
            f"未知 release_profile.id {pid!r} —— 只认 "
            f"{sorted(_FROZEN)}"
        )
    frozen = _FROZEN[pid]
    given = raw.get("fields")
    if given is not None:
        if not isinstance(given, Sequence) or isinstance(given, (str, bytes)):
            raise ValueError("release_profile.fields 必须是字段名列表")
        if tuple(given) != frozen and frozenset(given) != frozenset(frozen):
            raise ValueError(
                f"{pid} 的字段集是冻结的 {list(frozen)},不许在政策里改名单"
            )
    return {"id": pid, "fields": frozenset(frozen)}


def gating_fields(policy: Mapping[str, Any] | None) -> frozenset[str]:
    """Fields whose unresolved status keeps a document from posting."""
    profile = parse_release_profile(policy)
    if profile is None:
        return frozenset(FIELDS)
    return profile["fields"]


def status_blocks_posting(
    field: str,
    status: str,
    *,
    policy: Mapping[str, Any] | None,
) -> bool:
    """Whether this field's delivery status keeps the document pending."""
    profile = parse_release_profile(policy)
    if profile is None:
        return status in CENSUS_BLOCKING_STATUSES
    if field not in profile["fields"]:
        return False
    return status in PROFILE_BLOCKING_STATUSES


def reject_blocks_document(
    field: str,
    *,
    policy: Mapping[str, Any] | None,
    tier1: frozenset[str],
) -> bool:
    """Whether a human reject of this field keeps the document from posting.

    Census (no profile): TIER1 reject blocks; TIER2 does not.
    Under a profile: any gating-field reject blocks, including TIER2
    members of the frozen set such as ``seller_name``.
    """
    if field not in gating_fields(policy):
        return False
    if parse_release_profile(policy) is None:
        return field in tier1
    return True


def document_touch_metrics(
    routes: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Routing-time touch counts for the next HITL protocol.

    A document is touched when any gating field is ``review``, or when any
    QA probe (reason_codes starting ``QA_SAMPLE``) is ``review``. Opening
    a probe counts as opening.
    """
    profile = parse_release_profile(policy)
    gate = profile["fields"] if profile else frozenset(FIELDS)
    docs = sorted({str(row["doc_id"]) for row in routes})
    touched: set[str] = set()
    unresolved = 0
    qa_probes = 0
    for row in routes:
        codes = [str(c) for c in (row.get("reason_codes") or [])]
        is_qa = any(c.startswith("QA_SAMPLE") for c in codes)
        if is_qa:
            qa_probes += 1
        in_review = row.get("route") not in AUTO_ROUTES
        field = str(row.get("field"))
        doc_id = str(row["doc_id"])
        if in_review and (field in gate or is_qa):
            touched.add(doc_id)
        if in_review and field in gate:
            unresolved += 1
    return {
        "release_profile_id": None if profile is None else profile["id"],
        "gating_fields": sorted(gate),
        "docs": len(docs),
        "zero_touch_docs": len(docs) - len(touched),
        "touched_docs": len(touched),
        "unresolved_release_slots": unresolved,
        "qa_probe_slots": qa_probes,
    }
