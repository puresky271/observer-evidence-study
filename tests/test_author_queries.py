import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from observer_study.author_queries import make_question


class QueryAuthoringTests(unittest.TestCase):
    def test_public_question_has_no_private_entity(self):
        question = make_question("current_supported", "person:secret", "predicate:state", "geo:secret", "2026-10-20T09:00:00+09:00", True)
        self.assertNotIn("person:secret", question)
        self.assertNotIn("geo:secret", question)
        self.assertIn("entity_", question)

    def test_private_question_retains_semantics(self):
        question = make_question("current_supported", "person:subject", "predicate:state", "geo:target", "2026-10-20T09:00:00+09:00", False)
        self.assertIn("person:subject", question)
        self.assertIn("predicate:state", question)


if __name__ == "__main__":
    unittest.main()
