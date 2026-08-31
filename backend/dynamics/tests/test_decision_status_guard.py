#!/usr/bin/env python3
"""PAN-76 — decision_status is writable only by a recorded human decision.

The engine may compute how well supported a position is. Whether the firm has
decided is not a computation. `decision_status_at_ic` was already frozen by the
_at_ic rule, but the unsuffixed `decision_status` — the field `_truth_status`
reads first, and the one the V20 router writes — was reachable by any mutation.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.dynamics.runtime.panta_transition_engine import (  # noqa: E402
    HUMAN_ONLY_FIELDS,
    _is_recorded_human_decision,
)


class TestHumanDecisionRecognition(unittest.TestCase):
    def test_automated_event_is_not_a_human_decision(self):
        for event_type in ("CLAIM_ADMITTED", "SOURCE_INGESTED", "RECOMPUTE", ""):
            self.assertFalse(
                _is_recorded_human_decision({"event": event_type, "actor_id": "a1"}),
                f"{event_type!r} must not count as a human decision",
            )

    def test_decision_event_without_actor_is_refused(self):
        # A decision nobody made is the shape an automated write would take if it
        # tried to pass itself off as one.
        self.assertFalse(_is_recorded_human_decision({"event": "IC_DECISION"}))
        self.assertFalse(
            _is_recorded_human_decision({"event": "IC_DECISION", "actor_id": ""})
        )

    def test_decision_event_with_actor_is_accepted(self):
        for field in ("actor_id", "decided_by"):
            self.assertTrue(
                _is_recorded_human_decision({"event": "IC_DECISION", field: "fabrizio"}),
                f"a signed IC decision via {field} must be accepted",
            )

    def test_case_is_not_a_bypass(self):
        self.assertTrue(
            _is_recorded_human_decision({"event": "ic_decision", "actor_id": "x"})
        )

    def test_guarded_field_set(self):
        self.assertIn("decision_status", HUMAN_ONLY_FIELDS)
        # epistemic_status stays computable — that is the whole distinction.
        self.assertNotIn("epistemic_status", HUMAN_ONLY_FIELDS)


if __name__ == "__main__":
    unittest.main()
