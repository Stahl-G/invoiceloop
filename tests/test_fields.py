"""预注册规范化规则的单元测试(规则即结果,每条都值得钉死)。"""

from __future__ import annotations

from invoiceloop.fields import Kind, amount, date_parts, normalise


class TestAmount:
    def test_anglo_thousands(self):
        assert normalise("$8,500.00", Kind.AMOUNT) == "8500.00"

    def test_swiss_apostrophe_thousands(self):
        # 撇号是千分位不是小数点;剥早了会把 10'692'000.00 打成 0.00
        assert normalise("10'692'000.00", Kind.AMOUNT) == "10692000.00"

    def test_european_decimal_comma(self):
        assert normalise("1.234,56", Kind.AMOUNT) == "1234.56"

    def test_longest_run_wins(self):
        assert normalise("USD 100.00 due", Kind.AMOUNT) == "100.00"

    def test_unparseable(self):
        assert normalise("abc", Kind.AMOUNT) is None
        assert amount("abc") is None

    def test_two_digit_comma_tail_is_decimal(self):
        assert normalise("100,00", Kind.AMOUNT) == "100.00"

    def test_long_comma_tail_is_thousands(self):
        assert normalise("1,000", Kind.AMOUNT) == "1000.00"


class TestDate:
    def test_digit_tuple(self):
        assert normalise("03/25/99", Kind.DATE) == "03-25-99"

    def test_no_digits(self):
        assert normalise("May", Kind.DATE) is None

    def test_date_parts_plausible(self):
        assert date_parts("03/25/99") == (3, 25, 99)

    def test_date_parts_rejects_non_dates(self):
        assert date_parts("abc") is None
        assert date_parts("12345") is None  # 单个超 9999 的数字串
        assert date_parts("2024") is None  # 只有一段,成不了日期


class TestParty:
    def test_legal_suffix_folded(self):
        got = normalise("BioReliance Testing & Development, Inc.", Kind.PARTY)
        assert got is not None and "inc" not in got

    def test_truncated_at_40(self):
        got = normalise("A" * 100 + " Inc", Kind.PARTY)
        assert got is not None and len(got) <= 40


class TestCode:
    def test_separators_stripped(self):
        assert normalise("INV-2024-0042", Kind.CODE) == "inv20240042"

    def test_empty_after_strip(self):
        assert normalise("$%&", Kind.CODE) is None
