"""阶段 D 主体方向原型:几何与标签匹配(不接线门禁)。"""

from __future__ import annotations

from invoiceloop import subject_direction as sd


def test_digest_stable():
    assert len(sd.digest()) == 64
    assert sd.digest() == sd.digest()


def test_predict_match_from_side():
    assert sd.predict_match_from_side("seller") is True
    assert sd.predict_match_from_side("buyer") is False


def test_nearest_label_same_page_euclidean():
    labels = [
        {"name": "agency", "side": "buyer", "page": 0,
         "bbox": (0.8, 0.8, 0.9, 0.85), "phrase": "agency"},
        {"name": "remit_to", "side": "seller", "page": 0,
         "bbox": (0.1, 0.1, 0.2, 0.15), "phrase": "remit to"},
        {"name": "station", "side": "seller", "page": 1,
         "bbox": (0.1, 0.1, 0.2, 0.15), "phrase": "station"},
    ]
    # span near remit_to on page 0 (1-based page=1)
    hit = sd.nearest_label([0.12, 0.12, 0.18, 0.14], 1, labels)
    assert hit is not None
    assert hit["name"] == "remit_to"
    assert hit["side"] == "seller"
    # page 1 span ignores page-0 labels
    hit2 = sd.nearest_label([0.12, 0.12, 0.18, 0.14], 2, labels)
    assert hit2 is not None
    assert hit2["name"] == "station"


def test_nearest_label_max_dist():
    labels = [
        {"name": "agency", "side": "buyer", "page": 0,
         "bbox": (0.9, 0.9, 0.95, 0.95), "phrase": "agency"},
    ]
    assert sd.nearest_label([0.1, 0.1, 0.2, 0.2], 1, labels, max_dist=0.2) is None
    assert sd.nearest_label([0.1, 0.1, 0.2, 0.2], 1, labels)["name"] == "agency"


def test_closer_side_requires_both():
    only_seller = [
        {"name": "remit_to", "side": "seller", "page": 0,
         "bbox": (0.1, 0.1, 0.2, 0.15), "phrase": "remit to"},
    ]
    assert sd.closer_side([0.12, 0.12, 0.18, 0.14], 1, only_seller) is None
    both = only_seller + [
        {"name": "agency", "side": "buyer", "page": 0,
         "bbox": (0.8, 0.8, 0.9, 0.85), "phrase": "agency"},
    ]
    assert sd.closer_side([0.12, 0.12, 0.18, 0.14], 1, both) == "seller"
    assert sd.closer_side([0.82, 0.82, 0.88, 0.84], 1, both) == "buyer"


def test_kill_line_constant():
    assert sd.KILL_LINE == 0.80
