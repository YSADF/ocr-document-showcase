import unittest
from examples.vlm_fallback_policy import _risk_priority, _valid_output, _weight, _critical_change

class FallbackPolicyTests(unittest.TestCase):
    def test_page_review_is_not_a_region_trigger(self):
        self.assertIsNone(_risk_priority({"needs_review": True}))
    def test_high_risk_precedes_completeness(self):
        self.assertLess(_risk_priority({"risks": ["positioned_candidate_conflict"]}),
                        _risk_priority({"risks": ["dimension_symbol_completeness_unverified"]}))
    def test_output_failures_cannot_be_used(self):
        for output in ({"status": "ok", "text": ""}, {"status": "ok", "text": "10", "truncated": True},
                       {"status": "ok", "text": "10\n20"}, {"status": "timeout", "text": "10"}):
            self.assertNotEqual(_valid_output(output, "text"), "ok")
    def test_model_names_do_not_establish_weight_identity(self):
        self.assertIsNone(_weight({"model": {"id": "model-label"}}))
        self.assertEqual(_weight({"model": {"id": "a", "weight_identity": "same"}}),
                         _weight({"model": {"id": "b", "weight_identity": "same"}}))
    def test_symbol_changes_require_the_stronger_path(self):
        for before, after in (("10", "Ø10"), ("1.2", "12"), ("+1", "-1"), ("∅2", "Ø2")):
            self.assertTrue(_critical_change(before, after, "text"))
        self.assertTrue(_critical_change("x", "y", "formula"))
        self.assertFalse(_critical_change("NOTE", "NOTES", "text"))

if __name__ == "__main__":
    unittest.main()
