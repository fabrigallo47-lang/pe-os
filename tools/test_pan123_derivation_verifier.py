#!/usr/bin/env python3
"""PAN-123: execute a derivation's arithmetic, never trust the prose.

Logic-LM / Faithful Chain-of-Thought / FinQA's shared pattern applied to
PANTA's own `derivation` field: translate to an expression, execute with
the deterministic evaluator already built for the model graph
(tools/model_evaluator.py), never let a claim's own arithmetic stand
unverified.

The real-data test at the bottom is the point: run against the actual
Keystone pipeline output and it finds three claims whose stored value
disagrees with their own derivation's arithmetic -- not constructed for
this test, sitting in production output before this module existed.

    python3 tools/test_pan123_derivation_verifier.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.derivation_verifier import parse_derivation, verify_claims, verify_derivation


class ParsingTests(unittest.TestCase):
    def test_a_clean_chain_parses(self):
        parsed = parse_derivation("10.2 + 0.35 + 0.25 = 10.8")
        self.assertTrue(parsed["parsed"])
        self.assertEqual(parsed["stated_result"], 10.8)

    def test_unicode_operators_are_normalized(self):
        """"−" (U+2212) and "×"/"÷" are not ASCII '-', '*', '/' to Python's
        own tokenizer -- a real derivation used the minus-sign glyph."""
        parsed = parse_derivation("$8.4m − $7.7m = $0.7m")
        self.assertTrue(parsed["parsed"])
        self.assertEqual(parsed["expression"], "8.4 - 7.7")

    def test_unit_suffixes_are_stripped_only_when_adjacent(self):
        parsed = parse_derivation("(21 + 50) / 2 = 35.5 days")
        self.assertEqual(parsed["expression"], "(21 + 50) / 2")
        self.assertEqual(parsed["stated_result"], 35.5)

    def test_the_rightmost_equals_is_the_one_that_counts(self):
        """A derivation can resolve an intermediate '=' before its final
        one; the computation to check is left of the LAST '='."""
        parsed = parse_derivation(
            "(2025-11-15 minus each hire date) / 8 employees = "
            "(10.83 + 9.75 + 8.08) / 8 = 3.57 years")
        self.assertTrue(parsed["parsed"])
        self.assertEqual(parsed["expression"], "(10.83 + 9.75 + 8.08) / 8")
        self.assertEqual(parsed["stated_result"], 3.57)

    def test_prose_mixed_into_the_chain_is_refused_not_mis_parsed(self):
        """"customer relationships $2.8m + non-compete $0.2m" has an
        operator but also words inside the chain -- silently dropping the
        labels and computing 2.8+0.2 would hide which addend is which."""
        parsed = parse_derivation(
            "Sum: customer relationships $2.8m + non-compete $0.2m = $3.0m")
        self.assertFalse(parsed["parsed"])

    def test_no_equals_sign_is_refused(self):
        parsed = parse_derivation("The formula establishes a 1.5% floor.")
        self.assertFalse(parsed["parsed"])
        self.assertIn("no '='", parsed["reason"])

    def test_empty_derivation_is_refused(self):
        self.assertFalse(parse_derivation("")["parsed"])
        self.assertFalse(parse_derivation(None or "")["parsed"])


class VerificationTests(unittest.TestCase):
    def test_matching_arithmetic_and_value_verifies(self):
        result = verify_derivation("10.2 + 0.35 = 10.55", 10.55)
        self.assertEqual(result["status"], "verified")

    def test_floating_point_noise_within_tolerance_still_verifies(self):
        """0.1 + 0.2 != 0.3 exactly in IEEE 754 -- a tolerance-free compare
        would flag the EBITDA claim (10.2 + ... = 11.899999999999999) as
        wrong purely from float error, which is worse than the bug it
        exists to catch."""
        result = verify_derivation(
            "10.2 + 0.35 + 0.25 + 0.3 + 0.2 + 0.15 + 0.25 + 0 - 0.1 + 0.2 + 0.1 = 11.9", "11.9")
        self.assertEqual(result["status"], "verified")

    def test_stored_value_disagreeing_with_a_correct_derivation_is_flagged(self):
        """The real Apex Manufacturing case: the derivation's own
        arithmetic is right (0.2020+0.1617=0.3637) but the stored value
        is 0.68 -- neither the original nor the corrected sum."""
        result = verify_derivation(
            "0.2020 + 0.1617 = $0.36 million (corrected: 0.2020 + 0.1617 = 0.3637)", 0.68)
        self.assertEqual(result["status"], "value_disagrees_with_text")
        self.assertAlmostEqual(result["computed"], 0.3637, places=4)

    def test_derivation_that_miscalculates_its_own_stated_result(self):
        """The real Team Tenure case: three numbers (10.73 stated, 10.75
        stored, 8.24 computed) that all disagree with each other."""
        result = verify_derivation(
            "(10.83 + 9.75 + 8.08 + 7.08 + 0.92 + 9.75 + 9.75 + 9.75) / 8 = 10.73 years", 10.75)
        self.assertEqual(result["status"], "computed_disagrees_with_both")
        self.assertAlmostEqual(result["computed"], 8.23875, places=4)

    def test_unparseable_derivation_is_reported_not_guessed(self):
        result = verify_derivation("Sum of all invoice amounts (F5:F44) = $5.8 million", None)
        self.assertEqual(result["status"], "unparseable")

    def test_non_numeric_claimed_value_does_not_crash(self):
        result = verify_derivation("10 + 5 = 15", "8-12")
        self.assertIn(result["status"], {"value_not_numeric", "text_inconsistent"})


class RealClaimsTests(unittest.TestCase):
    """The point of this module: run it, don't just unit-test the parser."""

    CLAIMS = ROOT / "pipeline_out/e3/K-PRE/e3_claims.json"

    def test_real_keystone_output_has_flagged_derivations(self):
        if not self.CLAIMS.exists():
            self.skipTest("real E3 claims file not present in this checkout")
        payload = json.loads(self.CLAIMS.read_text())
        results = verify_claims(payload)
        self.assertGreaterEqual(len(results), 9, "expected at least the 9 derived claims measured")
        flagged = [r for r in results if r["status"] not in ("verified", "unparseable")]
        # Pins the finding itself: if this drops to zero, either the pipeline
        # fixed real bugs (good -- update this test) or the parser regressed
        # (bad -- it would be silently swallowing the same three claims).
        self.assertGreaterEqual(len(flagged), 3,
                                "expected the three measured real inconsistencies "
                                "(Team Tenure, Riverton, Apex) to still be flagged")


if __name__ == "__main__":
    unittest.main(verbosity=2)
