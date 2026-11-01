"""Tests for claim extraction — the regex layer must be stable and quiet."""
from __future__ import annotations

import unittest

from claimaudit import claims


SAMPLE = (
    "全网首发，唯一能做到全自动的量化系统。100% 无人值守，零风险躺赚。\n"
    "内置 120+ 因子，一键部署，3 分钟上手。\n"
    "完全免费开源，学员反馈月入 3 万。\n"
    "加群领取完整版。\n"
)


class ExtractTests(unittest.TestCase):
    def test_detects_core_kinds(self):
        found = claims.extract(SAMPLE)
        kinds = {c.kind for c in found}
        for expected in ("money", "absolute", "effortless", "quantity", "free_open", "time"):
            self.assertIn(expected, kinds, "缺少 %s 类宣称" % expected)

    def test_money_claim_is_severe(self):
        found = claims.extract(SAMPLE)
        money = [c for c in found if c.kind == "money"]
        self.assertTrue(money)
        self.assertEqual(money[0].severity, 3)

    def test_numeric_claims_are_verifiable(self):
        found = claims.extract("内置 120+ 因子，月入 3 万。")
        self.assertTrue(any(c.verifiable for c in found))

    def test_dedupe_repeated_sentence(self):
        text = "一键部署，零基础可用。一键部署，零基础可用。"
        found = claims.extract(text)
        effortless = [c for c in found if c.kind == "effortless"]
        self.assertLessEqual(len(effortless), 1)

    def test_empty_text(self):
        self.assertEqual(claims.extract(""), [])
        self.assertEqual(claims.extract(None), [])

    def test_neutral_text_has_no_claims(self):
        found = claims.extract("这个函数把两列做集合差，返回 JSON。")
        self.assertEqual(found, [])

    def test_counts_and_labels(self):
        found = claims.extract(SAMPLE)
        counted = claims.counts(found)
        self.assertGreaterEqual(sum(counted.values()), len(counted))
        self.assertIn("money", claims.FIELD_LABELS)


if __name__ == "__main__":
    unittest.main()
