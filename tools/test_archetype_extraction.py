#!/usr/bin/env python3
"""Archetype-selected extraction vocabulary.

The point of these tests is the generalization guard: widening the vocabulary
for venture and growth must not move buyout by a single label, because
METRIC_ENUM is what the semantic benchmark scores against.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.archetype_pack import (  # noqa: E402
    DEFAULT_ARCHETYPE, PACK_PATHS, load_pack, value_bearing_concepts,
)
from tools.extract_v2_physical import (  # noqa: E402
    CLAIM_TOOL, METRIC_ENUM, claim_tool_for, metric_vocabulary,
)


class ArchetypeVocabularyTests(unittest.TestCase):
    def test_all_three_packs_load(self) -> None:
        for archetype in ("buyout", "venture", "growth"):
            self.assertIn(archetype, PACK_PATHS)
            self.assertTrue(load_pack(archetype).get("canonical_concepts"))

    def test_buyout_vocabulary_is_untouched(self) -> None:
        """The generalization guard. buyout must be METRIC_ENUM exactly."""
        self.assertEqual(metric_vocabulary("buyout"), list(METRIC_ENUM))
        self.assertEqual(metric_vocabulary(), list(METRIC_ENUM))

    def test_buyout_reuses_the_frozen_tool_object(self) -> None:
        """Not merely equal -- the same object, so the default extraction path
        is byte-identical to before archetype selection existed."""
        self.assertIs(claim_tool_for(DEFAULT_ARCHETYPE), CLAIM_TOOL)

    def test_venture_widens_without_removing(self) -> None:
        venture = metric_vocabulary("venture")
        self.assertGreater(len(venture), len(METRIC_ENUM))
        for label in METRIC_ENUM:
            self.assertIn(label, venture, "widening must never drop a baseline label")

    def test_only_value_bearing_concepts_enter_the_metric_slot(self) -> None:
        """A `case_reading` or `qualitative_topic` is not a metric. Putting one
        in the metric enum would let two object types collide on one identity.
        """
        venture = set(metric_vocabulary("venture"))
        pack_concepts = load_pack("venture")["canonical_concepts"]
        non_value = [
            c for c in pack_concepts
            if c not in value_bearing_concepts("venture")
        ]
        self.assertTrue(non_value, "expected some non-value-bearing concepts")
        leaked = [
            c["label"] for c in non_value
            if c["label"] in venture and c["label"] not in METRIC_ENUM
        ]
        self.assertEqual(leaked, [], f"non-value-bearing concepts leaked into metrics: {leaked}")

    def test_unknown_archetype_falls_back_rather_than_emptying(self) -> None:
        """A bad archetype id must not silently narrow the vocabulary to
        nothing -- that would reject every claim as an unknown metric."""
        self.assertEqual(metric_vocabulary("no-such-archetype"), list(METRIC_ENUM))

    def test_tool_schema_carries_the_selected_vocabulary(self) -> None:
        tool = claim_tool_for("venture")
        enum = tool["input_schema"]["properties"]["claims"]["items"]["properties"]["metric"]["enum"]
        self.assertEqual(enum, metric_vocabulary("venture"))
        # and the frozen buyout tool was not mutated in the process
        buyout_enum = CLAIM_TOOL["input_schema"]["properties"]["claims"]["items"]["properties"]["metric"]["enum"]
        self.assertEqual(buyout_enum, METRIC_ENUM)


if __name__ == "__main__":
    unittest.main(verbosity=2)
