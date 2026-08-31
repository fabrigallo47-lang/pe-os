#!/usr/bin/env python3
"""PAN-71 — a settlement leaves a durable row, not just a new current_graph.json.

The settlement journal that already existed is crash recovery: it is deleted on
success. current_graph.json is a materialized view the next settlement overwrites.
Neither one records that a settlement happened, which is what makes "what did we
know on date X" unanswerable except by reading git history.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DYNAMICS_ROOT))
sys.path.insert(0, str(DYNAMICS_ROOT.parents[1]))

from backend.dynamics.runtime import ledger_store  # noqa: E402
from backend.dynamics.service import (  # noqa: E402
    run_bundle_transition,
    settle_candidate_state,
)


class SettlementLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.bundle = Path(self.temporary.name) / "bundle"
        self.bundle.mkdir(parents=True)
        for name, source in {
            "current_graph.json": "canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json",
            "execution_mapping.json": "benchmark/keystone_execution_mapping_v0.json",
            "keystone_materiality_policy_v0.json": "benchmark/keystone_materiality_policy_v0.json",
            "keystone_authority_matrix_v0.json": "benchmark/keystone_authority_matrix_v0.json",
        }.items():
            (self.bundle / name).write_bytes((DYNAMICS_ROOT / source).read_bytes())

        suite = json.loads(
            (DYNAMICS_ROOT / "benchmark/transition_engine_conformance_cases_v1.json")
            .read_text(encoding="utf-8")
        )
        case = next(
            item for item in suite["cases"]
            if item["test_id"] == "TCE-001-KEYSTONE-FIRM-EBITDA-CORRECTION"
        )
        self.events = case["event_batch"]

        # Redirect the ledger into the temp tree so the test never touches the
        # real pipeline_out/.
        self._real_root = ledger_store.PIPELINE_OUT
        ledger_store.PIPELINE_OUT = Path(self.temporary.name) / "pipeline_out"

    def tearDown(self):
        ledger_store.PIPELINE_OUT = self._real_root
        self.temporary.cleanup()

    def _settle(self, state_id: str = "STATE-TEST-ADOPTED"):
        result = run_bundle_transition(self.bundle, self.events, persist_outputs=True)
        return settle_candidate_state(
            self.bundle,
            result["candidate_state"],
            result["history_append"],
            current_state_id=state_id,
        )

    def test_settlement_appends_exactly_one_row(self):
        settled = self._settle()
        case_id = json.loads(
            (self.bundle / "current_graph.json").read_text(encoding="utf-8")
        )["case_id"]

        rows = ledger_store.read_ledger(case_id)
        self.assertEqual(len(rows), 1, "one settlement must leave exactly one row")
        row = rows[0]
        self.assertEqual(row["event"], "CASE_SETTLED")
        self.assertEqual(row["state_id"], settled["state_id"])
        self.assertTrue(row["known_at"], "the row must record when we learned it")

    def test_row_survives_the_current_graph_it_describes(self):
        # The point of the ledger: current_graph.json is a view, the row is history.
        self._settle()
        case_id = json.loads(
            (self.bundle / "current_graph.json").read_text(encoding="utf-8")
        )["case_id"]
        (self.bundle / "current_graph.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(ledger_store.read_ledger(case_id)), 1)

    def test_event_id_is_derived_from_what_was_settled(self):
        # Two settlements of the same graph and state id must collide, so a
        # retried request cannot double-count a settlement that already happened.
        settled = self._settle()
        case_id = json.loads(
            (self.bundle / "current_graph.json").read_text(encoding="utf-8")
        )["case_id"]
        first = ledger_store.read_ledger(case_id)[0]

        replay = ledger_store.append_event(case_id, first)
        self.assertFalse(replay["appended"], "re-appending the same row must be a no-op")
        self.assertEqual(len(ledger_store.read_ledger(case_id)), 1)
        self.assertEqual(first["state_id"], settled["state_id"])


if __name__ == "__main__":
    unittest.main()
