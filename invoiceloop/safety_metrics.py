"""Safety metrics: silent errors, review load, and triage lift, scored against
ground truth.

Only ever runs against a corpus that has annotations. `annotations_available()`
gates the lab/production boundary — without truth the metrics are marked
`unscored` rather than quietly reported as passing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .eval_norm import eval_normalise
from .fields import FIELD_KINDS
from .ocr import derisk_root

DOCILE_TO_FIELD = {
    "document_id": "invoice_number", "date_issue": "issue_date", "date_due": "due_date",
    "vendor_name": "seller_name", "vendor_tax_id": "seller_vat_id",
    "customer_billing_name": "buyer_name", "amount_total_net": "total_net",
    "amount_total_tax": "total_vat", "amount_total_gross": "total_gross",
    "amount_due": "amount_due",
}

AUTO_ROUTES = ("auto_accept", "auto_absent")

SAFETY_NOTE_SCORED = (
    "静默错按 DocILE 真值计(真值非空即计 silent_absent,含 $0.00 口径边界;"
    "与 docs/LOOP_GENERALIZATION_2026-08-06.md 同函数)。"
    "silent_absent 拆两列:真静默(silent_absent_true,晋升门只看它)与"
    "口径争议(caliber_disputes,truth-caliber-v1,SEALED-4 增补件 A3);"
    "对外叙述两列都报,门内不等式不另开旁路。"
)

SAFETY_NOTE_UNSCORED = (
    "反事实重路由(不重跑抽取与门禁);本 workspace 无可读 DocILE 标注,"
    "「被放松槽是否有害」未计 —— safety_status=unscored,"
    "本报告不给安全性结论。"
)


def truth(doc_id: str) -> dict[str, str]:
    """DocILE 标注 → 字段名→原文。文件不存在或无映射字段 → 空 dict。"""
    path = derisk_root() / "data" / "docile" / "annotations" / f"{doc_id}.json"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for item in json.loads(path.read_text(encoding="utf-8"))["field_extractions"]:
        name = DOCILE_TO_FIELD.get(item.get("fieldtype"))
        if name and item.get("text"):
            out.setdefault(name, item["text"])
    return out


def annotations_available(doc_ids: Iterable[str]) -> bool:
    """至少一份文档有非空 DocILE 标注 → 可 scored。"""
    for doc_id in doc_ids:
        if truth(doc_id):
            return True
    return False


def annotation_record_available(doc_id: str) -> bool:
    """Whether this document has a readable annotation record boundary.

    An omitted field inside an existing DocILE record is meaningful absence;
    a missing record is not.  Class-conditioned absence safety needs this
    distinction before QA sampling, otherwise an unscored document can be
    mistaken for a zero conflict.
    """
    path = derisk_root() / "data" / "docile" / "annotations" / f"{doc_id}.json"
    if not path.is_file():
        return False
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(body, dict) and isinstance(
        body.get("field_extractions"), list)


def score_slot(
    *,
    route: str,
    field: str,
    truth_value: str | None,
    understand_value: object,
) -> dict[str, bool]:
    """单槽静默错标志(与 loop_generalization L64–73 同判定)。"""
    out = {
        "is_review": route not in AUTO_ROUTES,
        "absent_hit": False,
        "silent_absent": False,
        "value_hit": False,
        "silent_wrong": False,
    }
    if out["is_review"]:
        return out
    if route == "auto_absent":
        out["absent_hit"] = True
        if truth_value is not None:
            out["silent_absent"] = True
        return out
    # auto_accept
    if truth_value is not None and understand_value is not None:
        kind = FIELD_KINDS[field]
        got = eval_normalise(understand_value, kind)
        want = eval_normalise(truth_value, kind)
        out["value_hit"] = True
        if got != want:
            out["silent_wrong"] = True
    return out


def empty_counts() -> dict[str, int]:
    return {
        "slots": 0,
        "review": 0,
        "absent_hits": 0,
        "silent_absent": 0,
        "value_hits": 0,
        "silent_wrong": 0,
        # 真值口径拆分(SEALED-4 增补件 A3,truth-caliber-v1):
        # silent_absent 是原口径(真值非空即计);caliber_disputes 是其中
        # 被 T1/T2 重分类的部分;silent_absent_true 是差值,晋升门只看它。
        "caliber_disputes": 0,
        "silent_absent_true": 0,
    }


def accumulate_slot(counts: dict[str, int], flags: Mapping[str, bool]) -> None:
    counts["slots"] += 1
    if flags["is_review"]:
        counts["review"] += 1
        return
    if flags["absent_hit"]:
        counts["absent_hits"] += 1
    if flags["silent_absent"]:
        counts["silent_absent"] += 1
    if flags["value_hit"]:
        counts["value_hits"] += 1
    if flags["silent_wrong"]:
        counts["silent_wrong"] += 1


def score_routes(
    routes: Sequence[Mapping[str, Any]],
    *,
    truth_of: Callable[[str], Mapping[str, str]] | None = None,
    understand_of: Callable[[str], Mapping[str, Any] | None] | None = None,
    caliber_of: Callable[[str, str, Mapping[str, str]], str | None] | None = None,
) -> dict[str, int]:
    """对一组路由行累计静默错。routes 项需含 doc_id/field/route。

    caliber_of(doc_id, field, truth_map) -> "T1"/"T2(i)"/"T2(ii)"/None:
    给出时把属口径争议的 silent_absent 拆进 caliber_disputes,
    silent_absent_true 只计真静默(增补件 A3;不给则全计真静默)。
    """
    truth_of = truth_of or truth
    understand_of = understand_of or (lambda _doc: None)
    counts = empty_counts()
    for row in routes:
        doc_id = row["doc_id"]
        field = row["field"]
        tmap = truth_of(doc_id)
        umap = understand_of(doc_id) or {}
        flags = score_slot(
            route=row["route"],
            field=field,
            truth_value=tmap.get(field),
            understand_value=umap.get(field),
        )
        accumulate_slot(counts, flags)
        if flags["silent_absent"]:
            dispute = caliber_of(doc_id, field, tmap) if caliber_of else None
            if dispute:
                counts["caliber_disputes"] += 1
            else:
                counts["silent_absent_true"] += 1
    return counts


def write_annotation_stub(root: Path, doc_id: str,
                          fields: Mapping[str, str]) -> Path:
    """测试用:在 root/data/docile/annotations/ 写一份最小 DocILE 标注。"""
    rev = {v: k for k, v in DOCILE_TO_FIELD.items()}
    extractions = []
    for field, text in fields.items():
        ft = rev.get(field)
        if ft is None:
            raise ValueError(f"无 DocILE 映射:{field}")
        extractions.append({"fieldtype": ft, "text": text})
    path = root / "data" / "docile" / "annotations" / f"{doc_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"field_extractions": extractions}),
                    encoding="utf-8")
    return path
