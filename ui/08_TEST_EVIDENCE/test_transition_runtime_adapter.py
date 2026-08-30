from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (
    ROOT
    / "07_ENGINEERING_CONTRACTS_AND_ADAPTERS"
    / "adapters"
    / "transition_runtime_adapter.py"
)
SPEC = importlib.util.spec_from_file_location("transition_runtime_adapter", ADAPTER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def runtime_output() -> dict:
    return {
        "schema_version": "transition-output-1.0",
        "engine_version": "test",
        "run_id": "run:test",
        "case_id": "case:test",
        "prior_state_id": "STATE-0",
        "source_event_id": "EVENT-1",
        "policy_refs": {},
        "affected_set": [{"object_type": "CLAIM", "object_id": "CL-1"}],
        "ordered_transitions": [
            {
                "component_id": "COMP-1",
                "member_ids": ["CL-1"],
                "result": "SETTLED",
            }
        ],
        "rule_switches": [],
        "recomputed_values": [],
        "unchanged_objects": [],
        "human_stops": [
            {
                "stop_id": "STOP-1",
                "object_or_component_id": "candidate-change-set",
                "reason_code": "DECISION_REQUIRES_HUMAN",
                "requested_action": "Review the Candidate.",
                "required_role": "PROFESSIONAL_REVIEWER",
                "policy_rule_id": "AUTH-1",
                "downstream_scope": ["CL-1"],
            }
        ],
        "blocked_components": [
            {
                "component_id": "COMP-BLOCKED",
                "member_ids": ["CL-X"],
                "reason_code": "MISSING_INPUT",
                "dependent_ids": ["CL-Y"],
                "missing_assumption_or_condition": "Supply the missing input.",
            }
        ],
        "coverage_limits": [],
        "invariant_checks": [{"invariant_id": "INV-1", "status": "PASS"}],
        "candidate_current_approved_delta": {
            "candidate": [
                {
                    "object_type": "CLAIM",
                    "object_id": "CL-1",
                    "field": "value",
                    "from": 1,
                    "to": 2,
                    "status": "PROPOSED",
                    "reason_code": "DIRECT_EVENT_MUTATION",
                }
            ],
            "current": [],
            "approved": [],
        },
        "partial_settlement_status": {
            "candidate": "FULL",
            "current": "REVIEW_PENDING",
            "approved": "UNCHANGED",
            "settled_component_ids": ["COMP-1"],
            "unsettled_component_ids": [],
        },
        "replay_hash": "sha256:test",
        "candidate_state_id": "CANDIDATE-1",
    }


class TransitionRuntimeAdapterTests(unittest.TestCase):
    def test_runtime_delta_lists_map_without_mutation(self) -> None:
        raw = runtime_output()
        before = copy.deepcopy(raw)
        mapped = MODULE.map_engine_output(raw)

        self.assertEqual(raw, before)
        self.assertIsInstance(
            mapped["candidate_current_approved_delta"]["candidate"], list
        )
        self.assertEqual(mapped["candidate_state_id"], "CANDIDATE-1")
        self.assertEqual(mapped["change_sets"][0]["change_set_id"], "CL-1")
        self.assertEqual(mapped["artifact_change_sets"][0]["artifact_id"], "CL-1")

    def test_native_stop_and_block_fields_become_renderable(self) -> None:
        mapped = MODULE.map_engine_output(runtime_output())
        stop = mapped["human_stops"][0]
        blocked = mapped["blocked_components"][0]

        self.assertEqual(stop["object_id"], "candidate-change-set")
        self.assertEqual(stop["reason"], "Review the Candidate.")
        self.assertEqual(stop["status"], "OPEN")
        self.assertTrue(stop["attestable"])
        self.assertEqual(blocked["downstream_scope"], ["CL-Y"])
        self.assertEqual(blocked["resolvable_by"], "Supply the missing input.")
        self.assertEqual(mapped["invariant_checks"][0]["check_id"], "INV-1")


if __name__ == "__main__":
    unittest.main()
