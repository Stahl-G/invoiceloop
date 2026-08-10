"""真值口径规则 T1/T2(SEALED-4 增补件 A3,2026-08-10 经 stahl 采纳并冻结)。

既有口径 ruling 管的是项目侧行为:

- `6dce2e9`(单总额):页面只印一个 Total 时归 amount_due,其余三个金额
  字段 confirm_absent;
- `95c6b66`(派生值):页面上没有该名目的标注列 → confirm_absent,不许从
  邻列推断。

DocILE 真值侧存在同族分歧,而打分器没有第三个桶。本模块把两条 ruling
一致化到真值侧:下列情形的 silent_absent **不计真静默,单列照登为
「口径争议」**(applicability 维度,宪章五)。

- **T1(单总额)**:slot (doc, F),F ∈ {total_net, total_vat, total_gross},
  truth[F] 与 truth[amount_due] 规范化为同一金额 —— 真值只是选了另一个
  槽放同一个 Total。
- **T2(别名目日期)**:slot (doc, due_date),truth[due_date] 非空且其
  文本在页面 OCR 中出现,且 (i) 与 truth[issue_date] 规范化后为同一
  字符串,或 (ii) 出现位置 ±12 词窗内含冻结词集
  {transaction, donation, authorization, adjustment} 之一。

冻结纪律:词集与窗口只许加不许删/窄;看过结果之后加词 = 拟合,该批作废。
判不出来的(OCR 缺失、日期不在页面上)一律返回 None —— 维持原判(真静默),
宁可多报不可漏报。
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Mapping

from .eval_norm import eval_normalise
from .fields import Kind
from .ocr import OcrUnavailable, iter_words

#: 规则版本。改任何判定细节都要换版本并回写增补件。
TRUTH_CALIBER_VERSION = "truth-caliber-v1"

#: T1 适用字段:单总额单据里真值可能选错的三个金额槽。
T1_FIELDS = frozenset({"total_net", "total_vat", "total_gross"})

#: T2 的词窗半径与冻结词集(增补件 A3 原文)。
T2_WINDOW_WORDS = 12
T2_CONTEXT_TERMS = ("transaction", "donation", "authorization", "adjustment")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm_tokens(text: object) -> list[str]:
    """小写 + 非 [a-z0-9] 折叠为分隔符;一个词可拆出多个 token。"""
    return [t for t in _NON_ALNUM.sub(" ", str(text).lower()).split() if t]


@lru_cache(maxsize=None)
def page_tokens(doc_id: str) -> tuple[str, ...]:
    """整份文档 OCR 的规范化 token 流(保持词序)。"""
    out: list[str] = []
    for _page, word, _bbox in iter_words(doc_id):
        out.extend(_norm_tokens(word))
    return tuple(out)


def t1_applies(truth_map: Mapping[str, str], field: str) -> bool:
    """truth[field] 与 truth[amount_due] 规范化为同一金额(同一 Total 两槽)。"""
    if field not in T1_FIELDS:
        return False
    have = truth_map.get(field)
    due = truth_map.get("amount_due")
    if not have or not due:
        return False
    norm_have = eval_normalise(have, Kind.AMOUNT)
    norm_due = eval_normalise(due, Kind.AMOUNT)
    return norm_have is not None and norm_have == norm_due


def t2_applies(truth_map: Mapping[str, str],
               tokens: tuple[str, ...] | list[str]) -> str | None:
    """别名目日期判据。返回 "T2(i)" / "T2(ii)" / None。

    前提:truth[due_date] 的规范化 token 序列在页面 token 流中至少出现
    一次(不出现 = 无法建立「这是页面上的别名目日期」,维持真静默)。
    """
    want = _norm_tokens(truth_map.get("due_date") or "")
    if not want:
        return None
    n = len(want)
    starts = [i for i in range(len(tokens) - n + 1)
              if list(tokens[i:i + n]) == want]
    if not starts:
        return None
    issue = _norm_tokens(truth_map.get("issue_date") or "")
    if issue and issue == want:
        return "T2(i)"
    terms = set(T2_CONTEXT_TERMS)
    for i in starts:
        lo = max(0, i - T2_WINDOW_WORDS)
        hi = min(len(tokens), i + n + T2_WINDOW_WORDS)
        if terms & set(tokens[lo:hi]):
            return "T2(ii)"
    return None


def caliber_dispute(doc_id: str, field: str,
                    truth_map: Mapping[str, str]) -> str | None:
    """(doc, field) 的 silent_absent 是否属口径争议:"T1"/"T2(i)"/"T2(ii)"/None。

    score_routes 的 caliber_of 回调与门内 truth_conflicts 核算共用这个
    入口 —— 两处必须是同一份代码,否则门内门外两个口径。
    """
    if field in T1_FIELDS:
        return "T1" if t1_applies(truth_map, field) else None
    if field == "due_date":
        try:
            tokens = page_tokens(doc_id)
        except OcrUnavailable:
            return None  # 无 OCR = 判不了,维持真静默(宪章四)
        return t2_applies(truth_map, tokens)
    return None
