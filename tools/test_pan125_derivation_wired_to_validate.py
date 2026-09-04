#!/usr/bin/env python3
"""PAN-125: arithmetic findings must be visible without discarding evidence.

Most workbook derivations are symbolic Excel formulas, so a deterministic
checker can often be unable to execute them.  That uncertainty must stay
silent, while a claim whose own literal arithmetic contradicts its stored
value is flagged for review and remains in the admitted graph.

    python3 tools/test_pan125_derivation_wired_to_validate.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import RawClaim, _to_e3_manifest, assemble, validate


def _raw(**overrides) -> RawClaim:
    base = dict(
        metric="Revenue", value=15.0, unit="$m", period="FY2026E",
        perimeter="Apex Manufacturing", epistemic_class="derived",
        direction="context", topic="Financial Performance", definition_id=None,
        statement="Synthetic derived claim.", locator="model.xlsx::Inputs!C89",
        source_id="SRC-MODEL", source_path="model.xlsx", known_at="2026-03-05",
        derivation="10 + 5 = 15",
    )
    base.update(overrides)
    return RawClaim(**base)


class DerivationValidationTests(unittest.TestCase):
    def test_correct_arithmetic_adds_no_validation_error(self):
        claim = validate(_raw())

        self.assertEqual(claim.validation_errors, [])

    def test_wrong_literal_arithmetic_is_flagged_but_admitted(self):
        """The real Apex mismatch merits review, not evidence deletion."""
        claim = validate(_raw(
            value=0.68,
            derivation=(
                "0.2020 + 0.1617 = $0.36 million "
                "(corrected: 0.2020 + 0.1617 = 0.3637)"
            ),
        ))
        graph = assemble([claim])

        self.assertEqual(len(claim.validation_errors), 1)
        self.assertIn("status=value_disagrees_with_text", claim.validation_errors[0])
        self.assertIn("computed=0.3637", claim.validation_errors[0])
        self.assertIn("claimed=0.68", claim.validation_errors[0])
        self.assertEqual(graph.admitted_count, 1)
        self.assertEqual(graph.rejected_count, 0)
        self.assertEqual(graph.claims[0].claim_id, claim.claim_id)

    def test_symbolic_derivation_is_not_punished_for_being_unverifiable(self):
        """Cell references are legitimate formulas, not malformed evidence."""
        claim = validate(_raw(
            derivation="C89 (Gross debt) minus C90 (Eligible cash)",
        ))

        self.assertEqual(claim.validation_errors, [])

    def test_asserted_claim_without_derivation_is_unchanged(self):
        claim = validate(_raw(epistemic_class="asserted", derivation=None))

        self.assertEqual(claim.validation_errors, [])

    def test_the_flag_actually_reaches_the_written_manifest(self):
        """validate()/assemble() compute the flag in-process; nothing
        upstream of this test checks it ever leaves the process. A flag
        that never reaches e3_claims.json is invisible to every downstream
        reader (a human, claim_overlap.py, vault admission) -- computing it
        and then dropping it on the way to disk is the same as never
        computing it."""
        claim = validate(_raw(
            value=0.68,
            derivation=(
                "0.2020 + 0.1617 = $0.36 million "
                "(corrected: 0.2020 + 0.1617 = 0.3637)"
            ),
        ))
        graph = assemble([claim])
        manifest = _to_e3_manifest(graph, deal="test-deal", manifest="SINGLE",
                                   sources_used=[{"source_id": "SRC-MODEL"}])

        fields = manifest["extraction_metadata"]["compiler_fields_per_claim"]
        self.assertEqual(len(fields), 1)
        flags = fields[0]["nonblocking_validation_errors"]
        self.assertEqual(len(flags), 1)
        self.assertIn("value_disagrees_with_text", flags[0])
        # And the claim itself is genuinely admitted, in the same manifest.
        self.assertEqual(len(manifest["claims"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
