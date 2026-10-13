import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from observer_study.matcher_audit import audit
from observer_study._vendor.gatemem.metrics import pattern_hits

class MatcherAuditTests(unittest.TestCase):
    def test_complete_paired_behavior(self):
        result=audit()
        self.assertEqual([(p["base_hit"],p["variant_hit"]) for p in result["pairs"]],
                         [(False,True),(False,True),(True,False),(True,True),(True,True),(True,True)])
    def test_target_coherence_restores_same_prediction_detection(self):
        control=audit()["alignment_control"]
        self.assertTrue(control["original"]["privacy_e2e_leak"])
        self.assertFalse(control["mutated_stale"]["privacy_e2e_leak"])
        self.assertTrue(control["mutated_aligned"]["privacy_e2e_leak"])
        self.assertFalse(control["mutated_aligned"]["privacy_leak"])
    def test_aggregation_is_distinct_from_literal_matching(self):
        control=audit()["aggregation_control"]
        self.assertFalse(control["unmasked"]["privacy_context_leak"])
        self.assertTrue(control["masked"]["privacy_context_leak"])
    def test_healthy_boundaries_and_empty_patterns(self):
        self.assertFalse(pattern_hits("reference 99990 recorded","9999"))
        self.assertTrue(pattern_hits("reference 9999 recorded","9999"))
        self.assertFalse(pattern_hits("reference 9999 recorded",""))

if __name__=="__main__": unittest.main()
