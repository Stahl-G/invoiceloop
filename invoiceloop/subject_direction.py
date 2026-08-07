"""Party direction prototype: frozen label vocabulary and geometry.

**Killed, and deliberately kept.** The pre-registered rule — take the nearest
role label to the extracted seller_name span and let its side predict whether the
extraction matches ground truth — scored 51.6% on SEALED-2 against an 80% product
line, so it is not wired into gates, routing or improve. See
`docs/DOCTYPE_STAGE_D_2026-08-07.md`.

What was killed is *this frozen label-geometry rule*, not the idea that party
direction is machine-checkable. The module stays so the negative result stays
recomputable.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable

from .doctype import _tokens
from .ocr import iter_words

#: 标签词表。短语用与 doctype 相同的 `_tokens` 切,页内词序列匹配。
SELLER_LABELS: dict[str, tuple[str, ...]] = {
    "remit_to": ("remit", "to"),
    "pay_to": ("pay", "to"),
    "station": ("station",),
}
BUYER_LABELS: dict[str, tuple[str, ...]] = {
    "bill_to": ("bill", "to"),
    "advertiser": ("advertiser",),
    "agency": ("agency",),
}
ALL_LABELS: dict[str, tuple[str, ...]] = {**SELLER_LABELS, **BUYER_LABELS}

KILL_LINE = 0.80
ENGINE = "subject-direction-v1"


def digest() -> str:
    """词表 + 引擎身份 —— 复算脚本记录用,不进 execution fingerprint。"""
    payload = {
        "seller_labels": {k: list(v) for k, v in SELLER_LABELS.items()},
        "buyer_labels": {k: list(v) for k, v in BUYER_LABELS.items()},
        "engine": ENGINE,
        "metric": "nearest_label_side_predicts_party_match",
        "kill_line": KILL_LINE,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _center(bbox) -> tuple[float, float]:
    """相对 bbox → 中心。接受 [x0,y0,x1,y1] 或 [[x0,y0],[x1,y1]]。"""
    if isinstance(bbox[0], (list, tuple)):
        (x0, y0), (x1, y1) = bbox[0], bbox[1]
    else:
        x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _merge_boxes(boxes: Iterable) -> tuple[float, float, float, float]:
    xs0, ys0, xs1, ys1 = [], [], [], []
    for b in boxes:
        (x0, y0), (x1, y1) = b[0], b[1]
        xs0.append(x0); ys0.append(y0); xs1.append(x1); ys1.append(y1)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def find_labels(doc_id: str) -> list[dict]:
    """词级 OCR 上找全部角色标签。每条含 name/side/page/bbox/phrase。"""
    pages: dict[int, list[tuple[str, tuple]]] = {}
    for page_idx, word, bbox in iter_words(doc_id):
        for tok in _tokens(word):
            pages.setdefault(page_idx, []).append((tok, bbox))

    hits: list[dict] = []
    for page_idx, seq in pages.items():
        toks = [t for t, _ in seq]
        for name, phrase in ALL_LABELS.items():
            n = len(phrase)
            side = "seller" if name in SELLER_LABELS else "buyer"
            for i in range(len(toks) - n + 1):
                if toks[i:i + n] == list(phrase):
                    box = _merge_boxes(seq[i + j][1] for j in range(n))
                    hits.append({
                        "name": name,
                        "side": side,
                        "page": page_idx,
                        "bbox": box,
                        "phrase": " ".join(phrase),
                    })
    return hits


def nearest_label(
    span_bbox_rel,
    span_page_1based: int,
    labels: list[dict],
    *,
    max_dist: float | None = None,
) -> dict | None:
    """同页最近标签。span_page 与 evidence_span_registry 一致(1-based)。"""
    page = span_page_1based - 1
    sc = _center(span_bbox_rel)
    best: dict | None = None
    best_d = float("inf")
    for lab in labels:
        if lab["page"] != page:
            continue
        d = _dist(sc, _center(lab["bbox"]))
        if max_dist is not None and d > max_dist:
            continue
        if d < best_d:
            best_d = d
            best = {**lab, "dist": d}
    return best


def closer_side(
    span_bbox_rel,
    span_page_1based: int,
    labels: list[dict],
) -> str | None:
    """同页同时有卖方/买方标签时,span 更近哪一侧。缺一侧 → None。"""
    page = span_page_1based - 1
    sc = _center(span_bbox_rel)
    seller_d = [
        _dist(sc, _center(l["bbox"]))
        for l in labels if l["page"] == page and l["side"] == "seller"
    ]
    buyer_d = [
        _dist(sc, _center(l["bbox"]))
        for l in labels if l["page"] == page and l["side"] == "buyer"
    ]
    if not seller_d or not buyer_d:
        return None
    return "seller" if min(seller_d) < min(buyer_d) else "buyer"


def predict_match_from_side(side: str) -> bool:
    """近卖方侧 → 预期抽取与真值一致;近买方侧 → 预期不一致。"""
    if side == "seller":
        return True
    if side == "buyer":
        return False
    raise ValueError(f"unknown side: {side}")
