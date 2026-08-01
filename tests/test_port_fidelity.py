"""搬运保真度:InvoiceLoop 的门禁必须和 dws-derisk 里六轮测过的实现逐点一致。

交接说明会错(CLAUDE.md 已记录两条),冻结判定才是事实。这里不抄答案,
直接把两边的实现跑在同一份真实存盘数据上对比:

- citation_holds:  逐 doc × 逐字段对拍 round3.py(子串包含语义)
- consistency:     routers.py::consistency_review 的 flag 集合 ==
                   我方 extraction_present/field_wellformed/arithmetic 的 fail 并集
- agree:           paired.py::agree 逐点一致
- normalise:       score.py::normalise 逐点一致(电池用例)

校准仓库缺席时整个模块跳过(它是配置指向的外部档案,ARCHITECTURE.md §12)。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DERISK = Path("~/Developer/dws-derisk").expanduser()
pytestmark = pytest.mark.skipif(not DERISK.exists(), reason="校准仓库不在")

sys.path.insert(0, str(DERISK))

import round3  # noqa: E402
import routers  # noqa: E402
import score  # noqa: E402
import paired  # noqa: E402
from schema import BY_NAME, Kind as DeriskKind  # noqa: E402

from invoiceloop import dws, gates  # noqa: E402
from invoiceloop.fields import FIELDS, Kind, normalise  # noqa: E402

SAMPLE = dws.stored_docs()[:12]  # 确定性取样:排序后的前 12 份


@pytest.fixture(scope="module")
def responses():
    return {
        doc: (dws.load_response(doc, "understand"), dws.load_response(doc, "agentic"))
        for doc in SAMPLE
    }


class TestCitationFidelity:
    def test_matches_round3_pointwise(self, responses):
        compared = 0
        for doc, (u, _) in responses.items():
            if u is None:
                continue
            theirs_doc = round3.Doc(data=u.data, meta=u.meta, pages=u.pages)
            for field_name in FIELDS:
                theirs = round3.citation_holds(doc, theirs_doc, field_name)
                mine = gates._citation_holds(doc, u, field_name)
                assert mine == theirs, f"{doc[:8]}/{field_name}: mine={mine} theirs={theirs}"
                compared += 1
        assert compared > 100, "对拍点数太少,等于没测"


class TestConsistencyFidelity:
    def test_flagged_union_matches_routers(self, responses):
        for doc, (u, a) in responses.items():
            if u is None or a is None:
                continue
            report = gates.run_gates(
                [doc], understand={doc: u}, agentic={doc: a},
                vision_answers={}, ledger_sha256="x", artifact_digest="y",
            )
            mine = {
                field_name
                for field_name in FIELDS
                if report["evaluations"][doc][field_name]["extraction_present"] == "fail"
                or report["evaluations"][doc][field_name]["field_wellformed"] == "fail"
                or report["evaluations"][doc][field_name]["arithmetic_consistency"] == "fail"
            }
            theirs = routers.consistency_review(u.data)
            assert mine == theirs, f"{doc[:8]}: 多出 {mine - theirs},漏掉 {theirs - mine}"


class TestAgreeFidelity:
    def test_matches_paired_pointwise(self, responses):
        compared = 0
        for doc, (u, a) in responses.items():
            if u is None or a is None:
                continue
            for field_name in FIELDS:
                theirs = paired.agree(u.data.get(field_name), a.data.get(field_name), field_name)
                mine = gates._agree(u.data.get(field_name), a.data.get(field_name), field_name)
                assert mine == theirs, f"{doc[:8]}/{field_name}"
                compared += 1
        assert compared > 100


class TestNormaliseFidelity:
    BATTERY = [
        "$8,500.00", "10'692'000.00", "1.234,56", "abc", "", None,
        "INV-2024-0042", "03/25/99", "May Ab. 199%", "BioReliance Testing & Development, Inc.",
        "LORILLARD RESEARCH CENTER ATTN: MS MELANEE BENNETT 420 ENGLISH STREET",
        "21,900.66", "GB123456789", "$%&", "100,00", "1,000", "  spaces  ",
    ]

    def test_matches_score_pointwise(self):
        for value in self.BATTERY:
            for their_kind in DeriskKind:
                # 两边的 Kind 是各自包里的枚举,is 比较不通用,按值对齐
                theirs = score.normalise(value, their_kind)
                mine = normalise(value, Kind(their_kind.value))
                assert mine == theirs, f"{value!r}/{their_kind}: mine={mine} theirs={theirs}"


class TestFieldSetFidelity:
    def test_kinds_match_schema(self):
        from invoiceloop.fields import FIELD_KINDS

        for name, kind in FIELD_KINDS.items():
            assert BY_NAME[name].kind.value == kind.value, f"{name} kind 漂移"
