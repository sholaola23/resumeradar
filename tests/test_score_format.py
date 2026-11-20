"""The score is rounded the same way everywhere: halves up, like the ring."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.score_format import whole_percent  # noqa: E402
from backend.ai_analyzer import _get_fallback_suggestions  # noqa: E402


class WholePercentTests(unittest.TestCase):
    def test_halves_round_up_like_math_round(self):
        self.assertEqual(whole_percent(42.5), 43)
        self.assertEqual(whole_percent(0.5), 1)
        self.assertEqual(whole_percent(74.5), 75)

    def test_other_values_round_to_nearest(self):
        self.assertEqual(whole_percent(42.4), 42)
        self.assertEqual(whole_percent(42.6), 43)
        self.assertEqual(whole_percent(100), 100)
        self.assertEqual(whole_percent("42.5"), 43)

    def test_non_numbers_become_zero(self):
        for value in (None, "abc", "", float("nan"), float("inf"), True, [], {}):
            self.assertEqual(whole_percent(value), 0, value)


class ScoreTextMatchesRingTests(unittest.TestCase):
    def test_fallback_summary_uses_the_ring_number(self):
        result = _get_fallback_suggestions({"overall_score": 42.5, "missing_keywords": {}})
        self.assertIn("match estimate is 43%", result["summary"])


if __name__ == "__main__":
    unittest.main()
