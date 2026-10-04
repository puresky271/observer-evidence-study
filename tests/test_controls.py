import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from observer_study.controls import opaque_entities, zero_evidence


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "as_of_jst": "2026-10-20T09:10:00+09:00",
            "current": [{"subject": "person:anon", "object": "geo:home", "validity": "current"}],
            "history": [{"subject": "person:anon", "object": "geo:venue", "validity": "historical"}],
            "unknown": [],
        }

    def test_zero_evidence_preserves_anchor(self):
        result = zero_evidence(self.context)
        self.assertEqual(result["as_of_jst"], self.context["as_of_jst"])
        self.assertEqual(result["current"], [])
        self.assertEqual(result["history"], [])

    def test_opaque_entities_preserve_time_and_structure(self):
        result = opaque_entities(self.context)
        self.assertEqual(result["context"]["as_of_jst"], self.context["as_of_jst"])
        self.assertTrue(result["context"]["current"][0]["subject"].startswith("entity_"))
        self.assertNotEqual(result["opaque_mapping_digest"], "")


if __name__ == "__main__":
    unittest.main()
