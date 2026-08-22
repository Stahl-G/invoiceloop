"""四臂名单过滤:不带名单会把旧的 660 份已曝光文档一起测进去。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import doctouch_arms  # noqa: E402

A = "a" * 24
B = "b" * 24
C = "c" * 24


def test_filter_keeps_only_the_listed_documents():
    """不过滤的话资格轮会测 860 份(200 新 + 660 旧曝光),
    然后把它当作「未曝光」的零触达率报出去。"""
    sources = {A: Path("/raw/new"), C: Path("/raw/old")}
    assert doctouch_arms.select_sources(sources, [A]) == {A: Path("/raw/new")}


def test_missing_dual_mode_blocks_instead_of_shrinking_the_sample():
    """名单 200 份、盘上只有 187 份齐全 —— 静默丢掉 13 份,
    报告照写 n=200。硬约束:负面发现即阻断。"""
    sources = {A: Path("/raw/new")}
    with pytest.raises(SystemExit) as exc:
        doctouch_arms.select_sources(sources, [A, B])
    assert B in str(exc.value)


def test_no_list_means_every_dual_mode_document():
    """旧的 doctouch 复算路径不受影响。"""
    sources = {A: Path("/raw/old"), C: Path("/raw/old")}
    assert doctouch_arms.select_sources(sources, None) == sources
