"""证据落盘:分阶段不可变。已冻结的清单不许被后来的冻结改写。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import freeze_evidence  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze_evidence, "REPO", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    return tmp_path, src


def test_a_second_stage_cannot_erase_the_first(repo):
    """一轮里冻结好几次。若共用一份 manifest,后一次会把前一次的条目删掉 ——
    前一个 commit 背书过的清单就此消失,而清单的全部意义就是那个背书。"""
    root, src = repo
    (src / "doc_list.json").write_text("a", encoding="utf-8")
    (src / "metrics.json").write_text("b", encoding="utf-8")
    freeze_evidence.freeze("r1", "plan", [src / "doc_list.json"])
    freeze_evidence.freeze("r1", "arms", [src / "metrics.json"])
    plan = (root / "docs/evidence/r1/plan/MANIFEST.sha256").read_text(encoding="utf-8")
    arms = (root / "docs/evidence/r1/arms/MANIFEST.sha256").read_text(encoding="utf-8")
    assert "doc_list.json" in plan and "metrics.json" not in plan
    assert "metrics.json" in arms and "doc_list.json" not in arms


def test_refreezing_the_same_stage_is_refused(repo):
    """同一阶段冻结两次 = 想改写历史。哪怕内容一模一样也拒绝:
    通过了就等于承认这个阶段可以再写一次。"""
    root, src = repo
    (src / "a.json").write_text("a", encoding="utf-8")
    freeze_evidence.freeze("r1", "plan", [src / "a.json"])
    with pytest.raises(SystemExit, match="已冻结"):
        freeze_evidence.freeze("r1", "plan", [src / "a.json"])


def test_manifest_records_the_bytes_that_were_copied(repo):
    """清单里的哈希必须是落盘副本自己的哈希 —— 不然它证明不了任何事。"""
    root, src = repo
    (src / "a.json").write_text("hello", encoding="utf-8")
    freeze_evidence.freeze("r1", "plan", [src / "a.json"])
    stage = root / "docs/evidence/r1/plan"
    digest, name = (stage / "MANIFEST.sha256").read_text(
        encoding="utf-8").split()
    assert name == "a.json"
    assert digest == hashlib.sha256((stage / "a.json").read_bytes()).hexdigest()


def test_a_missing_artifact_blocks(repo):
    """要冻的东西不在 = 上一步没跑成。半份证据比没有更糟。"""
    root, src = repo
    with pytest.raises(SystemExit, match="不存在"):
        freeze_evidence.freeze("r1", "plan", [src / "nope.json"])
