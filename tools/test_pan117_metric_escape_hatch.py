#!/usr/bin/env python3
"""PAN-117: a closed metric enum must be able to say "this isn't mine".

Measured failure this pins: METRIC_ENUM is shaped for buyout underwriting,
and with no exit from the enum the extractor force-fit a venture term-sheet
fragment onto the nearest-sounding entries — a EUR 6.0m primary round became
"Sponsor Equity" (a buyout sponsor's own cheque), a EUR 24.0m pre-money
became "Enterprise Value", and "eighteen to twenty-four months of runway"
became "Exit Horizon" = 21, a number stated nowhere in the source. Those
claims are not gaps, they are wrong, and wrong in a way that then merges
silently with real Sponsor Equity and Enterprise Value claims.

The fix under test: metric "Other" + a required `metric_label`, which
normalize_metric() maps to "" so the claim is UNRESOLVABLE by design —
it stays in the ledger, visible, and is never silently matched.

    python3 tools/test_pan117_metric_escape_hatch.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import CLAIM_TOOL, METRIC_ENUM, RawClaim, validate
from tools.object_identity import claim_id, is_resolvable, metric_identity


def _raw(**overrides) -> RawClaim:
    base = dict(
        metric="Other", value=24.0, unit="EUR m", period="2026",
        perimeter="Silexara primary round", epistemic_class="asserted",
        direction="context", topic="OTHER", definition_id=None,
        statement="Target is twenty-four million pre-money.",
        locator="SRC-06::funding", source_id="SRC-06", source_path="p",
        known_at="2026-05-18", entity="Silexara",
    )
    base.update(overrides)
    return RawClaim(**base)


class SchemaTests(unittest.TestCase):
    def test_enum_offers_an_exit(self):
        self.assertIn("Other", METRIC_ENUM)

    def test_metric_label_is_in_the_tool_schema_and_optional(self):
        """Optional, not required: only 'Other' claims carry a label, and a
        required field would force every ordinary claim to emit a null."""
        items = CLAIM_TOOL["input_schema"]["properties"]["claims"]["items"]
        self.assertIn("metric_label", items["properties"])
        self.assertNotIn("metric_label", items["required"])

    def test_measurement_description_covers_the_sibling_covenant_case(self):
        """A page with a leverage cap, an FCCR minimum and a liquidity floor
        holds three Covenant Threshold claims; 'total' on each collapses them."""
        items = CLAIM_TOOL["input_schema"]["properties"]["claims"]["items"]
        description = items["properties"]["measurement"]["description"]
        self.assertIn("threshold", description.lower())
        self.assertIn("FCCR", description)


class ValidationTests(unittest.TestCase):
    def test_other_with_a_label_is_accepted(self):
        claim = validate(_raw(metric_label="Pre-money valuation"))
        self.assertEqual(claim.validation_errors, [])
        self.assertEqual(claim.metric_label, "Pre-money valuation")

    def test_other_without_a_label_is_rejected(self):
        """An unlabelled hole is the failure the escape hatch exists to stop."""
        claim = validate(_raw(metric_label=None))
        self.assertTrue(any("requires metric_label" in e for e in claim.validation_errors))

    def test_blank_label_counts_as_missing(self):
        claim = validate(_raw(metric_label="   "))
        self.assertTrue(any("requires metric_label" in e for e in claim.validation_errors))
        self.assertIsNone(claim.metric_label)

    def test_label_on_a_real_metric_is_rejected(self):
        """'Revenue' + a label would let two vocabularies name one quantity."""
        claim = validate(_raw(metric="Revenue", metric_label="Bookings"))
        self.assertTrue(any("non-Other metric" in e for e in claim.validation_errors))


class IdentityTests(unittest.TestCase):
    """The point of the escape hatch is what it does NOT do: match."""

    def _as_dict(self, claim) -> dict:
        return {
            "entity": claim.entity, "metric": claim.metric, "period": claim.period,
            "period_canonical": claim.period_canonical, "scope": claim.scope,
            "basis": claim.basis, "measurement": claim.measurement,
            "scenario": claim.scenario, "unit": claim.unit,
            "source_id": claim.source_id, "source_version_id": claim.source_version_id,
            "locator": claim.locator, "epistemic_class": claim.epistemic_class,
            "value": claim.value, "perimeter": claim.perimeter,
        }

    def test_an_out_of_ontology_claim_is_unresolvable_not_wrong(self):
        """Declared coverage limit, per tools/object_identity.is_resolvable:
        it stays in the ledger and is never silently compared to anything."""
        claim = validate(_raw(metric_label="Pre-money valuation"))
        self.assertFalse(is_resolvable(self._as_dict(claim)))
        self.assertEqual(metric_identity(self._as_dict(claim))[1], "")

    def test_other_does_not_collide_with_the_metric_it_would_have_faked(self):
        """The measured bug: a EUR 24.0m pre-money labelled Enterprise Value
        lands on the same identity as a real Enterprise Value of 24.0m."""
        honest = self._as_dict(validate(_raw(metric_label="Pre-money valuation")))
        faked = self._as_dict(validate(_raw(metric="Enterprise Value")))
        self.assertNotEqual(claim_id(honest), claim_id(faked))

    def test_two_different_other_concepts_stay_distinct(self):
        """Pre-money 24.0 and post-money 30.0 are different facts, and the
        value dimension keeps them apart even though both normalize to ''."""
        pre = self._as_dict(validate(_raw(metric_label="Pre-money valuation", value=24.0)))
        post = self._as_dict(validate(_raw(metric_label="Post-money valuation", value=30.0)))
        self.assertNotEqual(claim_id(pre), claim_id(post))


if __name__ == "__main__":
    unittest.main(verbosity=2)
