import json
import unittest
from pathlib import Path

from runtime import apply_state_transition, compare_incremental_global


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def case(test_id):
    suite = load_json("benchmark/transition_engine_conformance_cases_v1.json")
    return next(item for item in suite["cases"] if item["test_id"] == test_id)


def policies():
    return (
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


def empty_graph():
    return {
        "schema_version": "1.1.0",
        "case_id": "SYNTHETIC-DILIGENCE-WORKFLOW",
        "canonical_as_of": "2026-01-01",
        "claims": [],
        "case_positions": [],
        "model_nodes": [],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def empty_mapping():
    return {
        "mapping_version": "TEST-WORKFLOW",
        "canonical_graph_hash": "sha256:" + "0" * 64,
        "model_nodes": [],
        "directed_model_edges": [],
        "position_model_directions": [],
        "formulas": [],
        "rule_switches": [],
        "inverse_solver_configs": [],
        "model_controls": [],
        "cyclic_component_solver_configs": [],
        "coverage_limits": [],
    }


class RuntimeOracleAndWorkflowTests(unittest.TestCase):
    def test_tce017_incremental_equals_global_on_mapped_projection(self):
        normative = case("TCE-017-INCREMENTAL-EQUALS-GLOBAL-KEYSTONE")
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        mapping = load_json("benchmark/keystone_execution_mapping_v0.json")
        materiality, authority = policies()
        event_batch = case(normative["event_batch_ref"])["event_batch"]

        comparison = compare_incremental_global(
            graph, event_batch, mapping, materiality, authority
        )

        self.assertTrue(comparison["equivalent"], comparison["comparisons"])
        self.assertTrue(all(comparison["comparisons"].values()))
        self.assertEqual(
            comparison["incremental"]["transition_output"]["execution_mode"],
            "INCREMENTAL_SCC",
        )
        self.assertEqual(
            comparison["global"]["transition_output"]["execution_mode"],
            "GLOBAL_RECOMPUTE",
        )

    def test_tce018_workflow_loop_is_three_events_not_a_solver(self):
        labels = case("TCE-018-WORKFLOW-LOOP-IS-EVENT-SEQUENCE")["event_sequence"]
        events = [
            {
                "event_id": f"EV-WORKFLOW-{index}",
                "event": label,
                "effective_date": f"2026-07-{15 + index:02d}",
                "known_at": f"2026-07-{15 + index:02d}T10:00:00Z",
                "source_ids": [],
                "trigger_claim_ids": [],
                "mutations": [],
            }
            for index, label in enumerate(labels)
        ]
        materiality, authority = policies()
        result = apply_state_transition(
            empty_graph(), events, empty_mapping(), materiality, authority
        )

        self.assertEqual(result["transition_output"]["numerical_solver_invocations"], 0)
        self.assertEqual(result["transition_output"]["inverse_solver_invocations"], 0)
        self.assertEqual(len(result["history_append"]), 3)
        self.assertEqual(
            [record["known_at"] for record in result["history_append"]],
            sorted(record["known_at"] for record in result["history_append"]),
        )


if __name__ == "__main__":
    unittest.main()
