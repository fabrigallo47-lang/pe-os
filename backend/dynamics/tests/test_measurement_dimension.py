#!/usr/bin/env python3
"""A breakdown is not a disagreement.

Found by replaying the Keystone corpus one claim at a time. These three shared an
identity and were each reported as contradicting the others:

    Keystone | Revenue | FY2025E | consolidated | SellerView | base | mm | USD
      30.3  Environmental, health and safety compliance service line revenue
      20.0  Industrial hygiene and workplace testing service line revenue
      14.1  Field inspection and asset integrity service line revenue

They are three components of one revenue. The tuple had no dimension for which
slice of a quantity a figure covers, so a component collided with its siblings and
with its own total. Most of the 374 conflicts in that corpus were this.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.object_identity import metric_identity, normalize_measurement  # noqa: E402


def claim(measurement: str | None, value: float) -> dict:
    return {"entity": "Keystone", "metric": "Revenue", "period_canonical": "FY2025E",
            "scope": "consolidated", "basis": "SellerView", "scenario": "base",
            "unit": "$mm", "measurement": measurement, "value": value}


class MeasurementDimensionTests(unittest.TestCase):
    def test_service_lines_do_not_collide_with_each_other(self):
        lines = [claim("EHS compliance service line", 30.3),
                 claim("industrial hygiene", 20.0),
                 claim("field inspection", 14.1)]
        identities = {metric_identity(c) for c in lines}
        self.assertEqual(len(identities), 3, "each service line is its own quantity")

    def test_a_component_does_not_collide_with_its_total(self):
        self.assertNotEqual(metric_identity(claim("field inspection", 14.1)),
                            metric_identity(claim("total", 64.4)))

    def test_unstated_slice_is_not_the_same_as_total(self):
        # A claim that never said whether it was the whole is a coverage limit,
        # not an assertion that it was. Merging the two would fold a component
        # into the total it belongs to.
        self.assertNotEqual(normalize_measurement(""), normalize_measurement("total"))
        self.assertEqual(normalize_measurement(""), "")
        self.assertEqual(normalize_measurement("unspecified"), "")

    def test_same_slice_still_compares(self):
        # The dimension must not make everything incomparable: two sources on the
        # same slice remain one identity, so a real conflict is still detectable.
        a = claim("field inspection", 14.1)
        b = claim("Field Inspection", 15.9)
        self.assertEqual(metric_identity(a), metric_identity(b))

    def test_extractor_requires_the_field(self):
        from tools.extract_v2 import CLAIM_TOOL
        required = CLAIM_TOOL["input_schema"]["properties"]["claims"]["items"]["required"]
        self.assertIn("measurement", required,
                      "the extractor must ask for the slice, or it is always empty")


if __name__ == "__main__":
    unittest.main()
