"""绑定规则的回归测试:拿一次真实的错位事故当基准。

第六轮实验里,三个读图模型各读了同一批 60 份发票的整页图。其中一个
(GPT 5.6 SOL)把答案系统性地绑定到了别的发票上 —— 63% 的作答内容出现在
其他文档里,而且两份文档的答案互相对调。当时是靠事后用 OCR 逐条取证才发现的。

冻结事务存在的意义就是让那种事故当场被拒,而不是事后被考古。这个测试把那次
事故连同两个正常读者的作答一起冻在 fixture 里,用真实数据回答一个问题:
绑定规则实际会拒掉多少行。

规则必须是**文档级**的:值要出现在这份发票的独立 OCR 文本里。片段级(要求值
落在 DWS 注册的 bbox 内)看起来更严谨,实测却会误伤 26–28% 的合法作答 ——
被误伤的正是 DWS 没返回值或框错位置、而读图在页面别处找到的那些行,也就是读图
唯一有增量价值的地方。ARCHITECTURE.md §5.2 有那张对照表。
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURE = pathlib.Path(__file__).parent / "fixtures/round6_binding.json"


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_carries_a_real_incident(fixture: dict) -> None:
    """没有那次事故,这个测试就只是在测两个表现正常的读者。"""

    sol = fixture["readers"]["GPT 5.6 SOL"]
    assert sol["expect_rejected"] / sol["answered"] > 0.5, (
        "fixture 应当包含那次错位事故;若拒绝率掉到一半以下,"
        "说明 fixture 被换过或规则被放宽了"
    )


@pytest.mark.parametrize(
    "model,answered,rejected",
    [("Kimi K3", 140, 14), ("Opus 5", 146, 9), ("GPT 5.6 SOL", 168, 118)],
)
def test_expected_counts_are_frozen(
    fixture: dict, model: str, answered: int, rejected: int
) -> None:
    """这些数字来自 dws-derisk 提交 173cbf9 的真实作答,不该漂移。"""

    reader = fixture["readers"][model]
    assert reader["answered"] == answered
    assert reader["expect_rejected"] == rejected
    assert sum(1 for row in reader["rows"] if not row["expect_admitted"]) == rejected


@pytest.mark.parametrize("model", ["Kimi K3", "Opus 5", "GPT 5.6 SOL"])
def test_binding_rule_reproduces_the_fixture(fixture: dict, model: str) -> None:
    """真正被测的东西:实现出来的规则要和冻结的判定逐行一致。

    M2 实现 invoiceloop.freeze.binds_to_document 之后解除跳过。签名:

        binds_to_document(doc_id: str, value: str) -> bool
    """

    try:
        from invoiceloop.freeze import binds_to_document
    except ImportError:
        pytest.skip("M2 未实现:invoiceloop.freeze.binds_to_document")

    mismatches = [
        (row["doc"], row["field"], row["value"])
        for row in fixture["readers"][model]["rows"]
        if binds_to_document(row["doc"], row["value"]) != row["expect_admitted"]
    ]
    assert not mismatches, f"{len(mismatches)} 行与冻结判定不符,前三条:{mismatches[:3]}"


def test_normal_readers_are_not_over_rejected(fixture: dict) -> None:
    """规则收得太紧的话,正常读者会先受伤 —— 这一条是防误伤的护栏。"""

    for model in ("Kimi K3", "Opus 5"):
        reader = fixture["readers"][model]
        rate = reader["expect_rejected"] / reader["answered"]
        assert rate < 0.15, (
            f"{model} 拒绝率 {rate:.0%} 偏高。片段级规则在这两位身上是 26–28%,"
            f"若看到那个量级,说明实现退回了片段级"
        )
