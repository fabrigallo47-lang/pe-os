#!/usr/bin/env python3
"""The canonical concept registry (dictionary section 4) as wired into validate().

Covers the part that is real today -- direct label resolution and the
required_identity completeness check -- and pins the coverage gap so nobody
mistakes partial resolution for full resolution.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.archetype_pack import (  # noqa: E402
    canonical_concepts, concept_for_metric, missing_required_identity,
    unrepresentable_required_identity,
)
from tools.extract_v2_physical import METRIC_ENUM, RawClaim, validate  # noqa: E402


def _claim(**overrides) -> RawClaim:
    base = dict(
        metric="Customer Concentration", value=18.2, unit="%", period="FY2025A",
        perimeter="Alderstone consolidated", epistemic_class="asserted",
        direction="context", topic="COMMERCIAL_AND_MARKET", definition_id=None,
        statement="Concentration was 18.2%.", locator="f.md::## S", source_id="SRC-X",
        source_path="f.md", known_at="2026-01-01T00:00:00Z", entity="Alderstone",
        period_canonical="FY2025A", scope="consolidated", measurement="total",
        claim_kind="QUANTITATIVE", bound="EXACT", basis="ReportedView", scenario="base",
    )
    base.update(overrides)
    return RawClaim(**base)


class ConceptRegistryTests(unittest.TestCase):
    def test_pack_ships_concept_seeds_with_required_identity(self) -> None:
        concepts = canonical_concepts()
        self.assertTrue(concepts, "archetype pack declares no canonical_concepts")
        self.assertTrue(
            all(isinstance(c.get("required_identity"), list) for c in concepts),
            "every concept seed must declare required_identity",
        )

    def test_label_resolves_to_its_concept(self) -> None:
        concept = concept_for_metric("Customer Concentration")
        self.assertIsNotNone(concept)
        self.assertEqual(concept["id"], "CUSTOMER_CONCENTRATION")

    def test_unknown_concept_requires_nothing_rather_than_guessing(self) -> None:
        """4.2: an unmatched concept is residue, never forced onto a neighbour."""
        self.assertIsNone(concept_for_metric("Sponsor Equity"))
        self.assertEqual(missing_required_identity(_claim(metric="Sponsor Equity")), [])

    def test_missing_identity_is_reported_per_the_pack_not_per_a_local_rule(self) -> None:
        missing = missing_required_identity(_claim(basis="unspecified", perimeter="unknown"))
        self.assertIn("basis", missing)
        self.assertIn("perimeter", missing)

    def test_incomplete_identity_flags_but_never_rejects(self) -> None:
        claim = validate(_claim(basis="unspecified"))
        self.assertTrue(
            any("incomplete identity" in e for e in claim.validation_errors),
            "an incomplete claim should say so",
        )
        # Non-blocking: assemble() admits it. Incomplete evidence is still evidence.
        self.assertTrue(
            any("incomplete identity" in e for e in claim.nonblocking_validation_errors),
            "incompleteness must not be grounds to discard the claim",
        )

    def test_complete_claim_is_not_flagged(self) -> None:
        claim = validate(_claim())
        self.assertFalse([e for e in claim.validation_errors if "incomplete identity" in e])

    def test_fields_the_schema_cannot_express_are_not_blamed_on_the_claim(self) -> None:
        """The pack declares 63 identity names; the schema carries 7. A concept
        requiring `numerator_definition` is not an incomplete extraction -- it is
        a schema that cannot say that yet, which is a migration input, not an error.
        """
        gross_margin_like = [
            c for c in canonical_concepts()
            if "numerator_definition" in (c.get("required_identity") or [])
        ]
        self.assertTrue(gross_margin_like, "expected a concept requiring numerator_definition")
        label = gross_margin_like[0]["label"]
        self.assertIn("numerator_definition", unrepresentable_required_identity(label))
        self.assertNotIn("numerator_definition", missing_required_identity(_claim(metric=label)))

    def test_coverage_gap_is_pinned_until_the_alias_table_ships(self) -> None:
        """Section 4.1's registry record includes aliases[]; the pack has none,
        so only direct label matches resolve. Pinning the number keeps the gap
        honest -- if a hand-written bridge ever appears, this fails and asks why.
        """
        resolved = [m for m in METRIC_ENUM if concept_for_metric(m) is not None]
        self.assertEqual(
            len(resolved), 12,
            "metric->concept coverage changed; if aliases[] shipped, update this "
            "and stop describing coverage as partial",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
