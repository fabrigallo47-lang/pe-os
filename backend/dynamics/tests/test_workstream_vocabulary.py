#!/usr/bin/env python3
"""PAN-79 — one workstream vocabulary across extraction, questions and the router.

Three names for the same field were in use: the archetype pack's 9 canonical ids,
the Fund Lens's 7 lowercase ones, and two router placeholders that never named a
workstream at all. A claim tagged FINANCIAL_QOE and a question tagged "financial"
therefore described the same area and could not be joined.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.archetype_pack import (  # noqa: E402
    UNASSIGNED_WORKSTREAM,
    load_pack,
    normalize_workstream,
    workstream_ids,
)
from tools.extract_v2 import TOPIC_ENUM  # noqa: E402


class WorkstreamVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.canonical = set(workstream_ids(load_pack()))

    def test_extraction_and_questions_land_in_one_vocabulary(self):
        """The join that was impossible before: a claim's topic and a question's
        workstream must be comparable without a lookup table nobody maintains."""
        claim_topic = "FINANCIAL_QOE"                      # from the extractor
        question_workstream = normalize_workstream("financial")   # from the Fund Lens
        self.assertEqual(claim_topic, question_workstream)
        self.assertIn(claim_topic, TOPIC_ENUM)

    def test_every_fund_lens_value_resolves(self):
        # The seven values actually present in the shipped lens.
        for lens_value in ("commercial", "financial", "operations", "legal",
                           "financing", "people", "governance"):
            resolved = normalize_workstream(lens_value)
            self.assertIn(resolved, self.canonical,
                          f"{lens_value!r} must resolve to a canonical workstream")

    def test_people_and_governance_collapse_together(self):
        # The lens splits these; the pack does not. A real narrowing, asserted so
        # it stays a decision rather than becoming a surprise.
        self.assertEqual(normalize_workstream("people"),
                         normalize_workstream("governance"))

    def test_router_placeholders_are_unassigned_not_guessed(self):
        # "underwriting" and "deal-emergent" never named an area. Mapping them to
        # a plausible workstream would invent a placement nobody made.
        for placeholder in ("underwriting", "deal-emergent"):
            self.assertEqual(normalize_workstream(placeholder), UNASSIGNED_WORKSTREAM)

    def test_unknown_and_empty_stay_visible_as_other(self):
        # Never raise and never drop: an unplaceable question still exists.
        for value in ("", None, "something nobody defined"):
            self.assertEqual(normalize_workstream(value), UNASSIGNED_WORKSTREAM)

    def test_canonical_values_pass_through_unchanged(self):
        for workstream in self.canonical:
            self.assertEqual(normalize_workstream(workstream), workstream)

    def test_router_emits_only_canonical_values(self):
        import re
        router = (ROOT / "app" / "v20_router.py").read_text(encoding="utf-8")
        literals = re.findall(r'"workstream":\s*"([^"]+)"', router)
        for value in literals:
            self.assertIn(value, self.canonical | {UNASSIGNED_WORKSTREAM},
                          f"router writes a raw workstream literal: {value!r}")


if __name__ == "__main__":
    unittest.main()
