"""eval_norm 的冻结点一致性(v0.2 P0-5):

- 2026-08-05 的冻结点上,eval_normalise 与产品侧 fields.normalise 逐值一致;
  此后产品侧可演化,评测侧不动 —— 本测试在冻结点上钉住两侧等价;
- 已知值钉死评测口径(金额分隔符、瑞士千分位、日期、法团后缀);
- 改 eval_norm.py = 作废全部既有评测数字,必须连本测试一起书面说明。
"""

from __future__ import annotations

from invoiceloop.eval_norm import eval_normalise
from invoiceloop.fields import Kind, normalise

CASES = [
    ("$8,500.00", Kind.AMOUNT, "8500.00"),
    ("1.234,56", Kind.AMOUNT, "1234.56"),       # 欧式:逗号是小数点
    ("1,234.56", Kind.AMOUNT, "1234.56"),       # 盎格鲁:点是
    ("1'234.00", Kind.AMOUNT, "1234.00"),       # 瑞士千分位
    ("03/04/2026", Kind.DATE, "03-04-2026"),    # 不猜顺序
    ("Acme Corp.", Kind.PARTY, "acme"),
    ("MORGAN COUNTY INDUSTRIES, INC.", Kind.PARTY, "morgancountyindustries"),
    ("#18N0039311", Kind.CODE, "18n0039311"),
    ("  多空格  文本 ", Kind.TEXT, "多空格 文本"),
    ("", Kind.AMOUNT, None),
    (None, Kind.AMOUNT, None),
]


class TestFreezePoint:
    def test_eval_matches_product_at_freeze_point(self):
        for value, kind, _ in CASES:
            assert eval_normalise(value, kind) == normalise(value, kind), \
                f"冻结点上两侧必须一致:{value!r}"

    def test_known_values_pinned(self):
        for value, kind, want in CASES:
            assert eval_normalise(value, kind) == want, \
                f"评测口径漂移:{value!r} → {eval_normalise(value, kind)!r} ≠ {want!r}"
