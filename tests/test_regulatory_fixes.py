"""Offline regression tests for status handling, IDs and ESRS metadata."""
import sys
import types
import unittest

# The tests do not call Gemini; stub its import so they run offline.
google = types.ModuleType("google")
genai = types.ModuleType("google.genai")
types_mod = types.ModuleType("google.genai.types")
genai.Client = object
types_mod.Content = object
types_mod.Part = object
types_mod.GenerateContentConfig = object
google.genai = genai
sys.modules.setdefault("google", google)
sys.modules.setdefault("google.genai", genai)
sys.modules.setdefault("google.genai.types", types_mod)

from backend import requirement_engine as engine
from backend.pdf_extract import _metadata_for_chunk


class EmptyStore:
    def retrieve(self, query, top_k=4):
        return []


class FixTests(unittest.TestCase):
    def test_esrs_heading_recognized(self):
        self.assertEqual(_metadata_for_chunk("E1-6 Gross Scopes 1, 2, 3 and Total GHG emissions")[2], "E1-6")
        self.assertEqual(_metadata_for_chunk("Disclosure Requirement E2-1 Policies related to pollution")[2], "E2-1")
        self.assertEqual(_metadata_for_chunk("GOV-1 The role of the administrative, management and supervisory bodies")[2], "GOV-1")

    def test_passing_esrs_mention_not_tagged_as_heading(self):
        self.assertNotEqual(_metadata_for_chunk("See E1-6 for the emissions disclosure.")[2], "E1-6")

    def test_no_api_key_is_assessment_failed(self):
        result = engine.assess_requirement({"id": "REQ-001", "requirement": "Test"}, [], api_key="")
        self.assertEqual(result["status"], "Assessment failed")

    def test_empty_evidence_never_becomes_potential_gap(self):
        # Avoid any model call: no key returns failed, which is distinct from a gap.
        result = engine.assess_requirement({"id": "REQ-001", "requirement": "Test"}, [], api_key="")
        self.assertNotEqual(result["status"], "Potential gap")

    def test_duplicate_input_ids_are_made_unique_in_results(self):
        original = engine.assess_requirement
        engine.assess_requirement = lambda req, evidence, api_key=None: {
            "status": "Insufficient evidence", "assessment": "Not enough evidence", "evidence": [], "missing_elements": []
        }
        try:
            reqs = [
                {"id": "REQ-008", "requirement": "A"},
                {"id": "REQ-008", "requirement": "B"},
                {"id": "REQ-008", "requirement": "C"},
            ]
            results = engine.run_gap_analysis(reqs, EmptyStore(), api_key="fake")
            ids = [x["id"] for x in results]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(ids[0], "REQ-008")
        finally:
            engine.assess_requirement = original


if __name__ == "__main__":
    unittest.main()


def test_wrapped_line_starting_with_code_is_not_a_heading():
    from backend.pdf_extract import _metadata_for_chunk
    text = "[Page 4]\nthe policy shall apply. See also\nE1-2 and Article 19a where relevant to the plan."
    assert _metadata_for_chunk(text)[2] == "Article 19a"


def test_capitalised_title_after_code_is_a_heading():
    from backend.pdf_extract import _metadata_for_chunk
    assert _metadata_for_chunk("[Page 4]\nE1-6 Gross Scopes 1, 2, 3 emissions")[2] == "E1-6"
    assert _metadata_for_chunk("[Page 4]\nE1-6\nGross Scopes 1, 2, 3 emissions")[2] == "E1-6"
