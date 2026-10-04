import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from observer_study.single_rater import choose_delayed


class SingleRaterTests(unittest.TestCase):
    def test_delayed_subset_is_deterministic_and_stratified(self):
        rows = [{"review_id": f"r{i}", "response_status": "usable" if i % 2 else "empty"} for i in range(12)]
        key = {f"r{i}": {"family_id": f"f{i // 3}", "strategy": "on_query" if i % 2 else "fixed_interval"} for i in range(12)}
        first = choose_delayed(rows, key, 0.25, "test")
        second = choose_delayed(rows, key, 0.25, "test")
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 4)
        self.assertEqual(len({row["review_id"] for row in first}), len(first))


if __name__ == "__main__":
    unittest.main()
