#!/usr/bin/env python3
"""QUALITATIVE claims: checkable non-numeric evidence must survive.

Guards both directions of the change that added the kind. Non-numeric but
checkable evidence (proof states, capability assessments, a counterparty's
stance) must reach the graph; un-checkable adjectives must still not.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import (  # noqa: E402
    CLAIM_KIND_ENUM, RawClaim, assemble, validate,
)


def _claim(**overrides) -> RawClaim:
    base = dict(
        metric="Other", metric_label="Deployment state", value=None, unit=None,
        period="as of 2026-05-13", perimeter="Silexara field deployment",
        epistemic_class="observed", direction="context", topic="OTHER",
        definition_id=None,
        statement="Installed and streaming, customer notifications not yet enabled.",
        locator="f.md::## S", source_id="SRC-X", source_path="f.md",
        known_at="2026-06-05T00:00:00Z", entity="Silexara",
        period_canonical="2026-05-13", scope="unspecified", measurement="total",
        claim_kind="QUALITATIVE", bound="NONE", basis="unspecified", scenario="unspecified",
    )
    base.update(overrides)
    return RawClaim(**base)


class QualitativeClaimTests(unittest.TestCase):
    def test_kind_exists_and_characterisation_still_does(self) -> None:
        self.assertIn("QUALITATIVE", CLAIM_KIND_ENUM)
        self.assertIn("CHARACTERISATION", CLAIM_KIND_ENUM)

    def test_qualitative_claim_reaches_the_graph(self) -> None:
        graph = assemble([validate(_claim())])
        self.assertEqual(graph.admitted_count, 1, "a checkable non-numeric claim must survive")
        self.assertEqual(graph.rejected_count, 0)

    def test_a_qualitative_claim_needs_no_value(self) -> None:
        """A proof state has no number. Requiring one would delete it again."""
        claim = validate(_claim(value=None))
        self.assertNotIn(
            "characterisation without checkable content",
            " ".join(claim.validation_errors),
        )

    def test_characterisation_is_still_rejected(self) -> None:
        graph = assemble([validate(_claim(
            claim_kind="CHARACTERISATION",
            statement="A leading, scaled platform with attractive momentum.",
        ))])
        self.assertEqual(graph.admitted_count, 0, "adjectives must still not become evidence")
        self.assertEqual(graph.rejected_count, 1)

    def test_benchmark_cannot_represent_the_new_kind(self) -> None:
        """Pins WHY the eval adapter withholds these rather than relabelling.

        The benchmark's claim_kind is a closed enum without QUALITATIVE, and one
        invalid claim invalidates an entire prediction -- observed live as
        conflict.restatement-002 scoring 0.000. If this ever starts passing,
        the fixtures grew the kind and the adapter should stop withholding.
        """
        schema = json.loads(
            (ROOT / "evaluation" / "schemas" / "evaluation_case.schema.json").read_text(encoding="utf-8")
        )
        kinds = schema["$defs"]["semantic_claim"]["properties"]["claim_kind"]["enum"]
        self.assertNotIn(
            "QUALITATIVE", kinds,
            "benchmark now models QUALITATIVE; drop the withholding in "
            "evaluation/panta_semantic_command.py",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
