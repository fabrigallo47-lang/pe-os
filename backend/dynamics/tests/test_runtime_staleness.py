import copy
import json
import unittest
from pathlib import Path

from runtime import apply_state_transition, compare_incremental_global


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def empty_mapping():
    return {
        "mapping_version": "TEST",
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


def base_graph(*, freshness="CURRENT", include_clean_route=False):
    routes = [
        {
            "route_id": "R-MODEL",
            "target_position_id": "P-TARGET",
            "logic": "AND",
            "member_model_node_ids": ["M-OUT"],
        }
    ]
    claims = []
    if include_clean_route:
        claims.append(
            {
                "claim_id": "C-CLEAN",
                "statement": "Independent current evidence",
                "value": None,
                "unit": None,
                "period": "TEST",
                "perimeter": "TEST",
                "usable": True,
                "validation_only": False,
            }
        )
        routes.append(
            {
                "route_id": "R-CLEAN",
                "target_position_id": "P-TARGET",
                "logic": "INDEPENDENT",
                "member_claim_ids": ["C-CLEAN"],
            }
        )
    return {
        "schema_version": "1.1.0",
        "case_id": "STALE-CASE",
        "canonical_as_of": "2026-01-01",
        "claims": claims,
        "case_positions": [
            {
                "position_id": "P-TARGET",
                "statement": "Model-backed position",
                "criticality": "critical",
                "decision_status": "ACCEPTED",
                "freshness_status": freshness,
            }
        ],
        "model_nodes": [
            {
                "model_node_id": "M-IN",
                "name": "Input",
                "kind": "input",
                "period": "TEST",
                "perimeter": "TEST",
                "value": "1",
                "unit": None,
                "freshness_status": "CURRENT",
            },
            {
                "model_node_id": "M-OUT",
                "name": "Derived output",
                "kind": "derived",
                "period": "TEST",
                "perimeter": "TEST",
                "value": "2",
                "unit": None,
                "freshness_status": freshness,
            },
        ],
        "support_routes": routes,
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def correction_event(event_id):
    return {
        "event_id": event_id,
        "event": "Correct model input",
        "effective_date": "2026-01-02",
        "known_at": "2026-01-02T08:00:00Z",
        "source_ids": ["S-MODEL"],
        "trigger_claim_ids": [],
        "mutations": [
            {
                "operation": "CORRECT",
                "object_type": "MODEL_NODE",
                "object_id": "M-IN",
                "field": "value",
                "from": "1",
                "to": "2",
            }
        ],
    }


def run(graph, event, mapping):
    return apply_state_transition(
        graph,
        [event],
        mapping,
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


def compare_modes(graph, event, mapping):
    return compare_incremental_global(
        graph,
        [event],
        mapping,
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class RuntimeStalenessTests(unittest.TestCase):
    def test_unrecomputed_outputs_become_stale_and_stop_supporting(self):
        graph = base_graph()
        original = copy.deepcopy(graph)
        mapping = empty_mapping()
        mapping["directed_model_edges"] = [
            {
                "edge_id": "E-IN-OUT",
                "from_model_node_id": "M-IN",
                "to_model_node_id": "M-OUT",
            }
        ]

        result = run(graph, correction_event("EV-STALE"), mapping)
        output = result["transition_output"]
        candidate = result["candidate_state"]["current_graph"]
        candidate_model = next(
            item for item in candidate["model_nodes"]
            if item["model_node_id"] == "M-OUT"
        )
        candidate_position = candidate["case_positions"][0]
        route = next(
            item for item in output["route_results"]
            if item["route_id"] == "R-MODEL"
        )
        combination = output["support_combination_results"][0]
        freshness_deltas = {
            (item["object_id"], item["to"], item["reason_code"])
            for item in output["candidate_current_approved_delta"]["candidate"]
            if item["field"] == "freshness_status"
        }

        self.assertEqual(graph, original)
        self.assertEqual(candidate_model["value"], "2")
        self.assertEqual(candidate_model["freshness_status"], "STALE")
        self.assertEqual(candidate_position["freshness_status"], "STALE")
        self.assertEqual(candidate_position["decision_status"], "ACCEPTED")
        self.assertEqual(route["member_states"], {"M-OUT": "UNKNOWN"})
        self.assertEqual(route["state"], "UNKNOWN")
        self.assertIn("STALE_UPSTREAM_BASIS", route["reason_codes"])
        self.assertEqual(combination["state"], "UNKNOWN")
        self.assertEqual(combination["reason_codes"], ["STALE_UPSTREAM_BASIS"])
        self.assertEqual(
            freshness_deltas,
            {
                (
                    "M-OUT",
                    "STALE",
                    "UPSTREAM_BASIS_CHANGED_NOT_RECOMPUTED",
                ),
                (
                    "P-TARGET",
                    "STALE",
                    "UPSTREAM_BASIS_CHANGED_NOT_RECOMPUTED",
                ),
            },
        )
        self.assertTrue(
            compare_modes(graph, correction_event("EV-STALE"), mapping)[
                "equivalent"
            ]
        )

    def test_successful_formula_recomputation_restores_current_outputs(self):
        graph = base_graph(freshness="STALE")
        mapping = empty_mapping()
        mapping["directed_model_edges"] = [
            {
                "edge_id": "E-IN-OUT",
                "from_model_node_id": "M-IN",
                "to_model_node_id": "M-OUT",
            }
        ]
        mapping["formulas"] = [
            {
                "formula_id": "F-OUT",
                "input_ids": ["M-IN"],
                "output_id": "M-OUT",
                "expression_or_function_ref": "x * 2",
                "operand_bindings": {"x": "M-IN"},
            }
        ]

        result = run(graph, correction_event("EV-RECOMPUTE"), mapping)
        output = result["transition_output"]
        candidate = result["candidate_state"]["current_graph"]
        candidate_model = next(
            item for item in candidate["model_nodes"]
            if item["model_node_id"] == "M-OUT"
        )
        candidate_position = candidate["case_positions"][0]
        route = output["route_results"][0]
        freshness_deltas = {
            (item["object_id"], item["to"], item["reason_code"])
            for item in output["candidate_current_approved_delta"]["candidate"]
            if item["field"] == "freshness_status"
        }

        self.assertEqual(candidate_model["value"], "4.0")
        self.assertEqual(candidate_model["freshness_status"], "CURRENT")
        self.assertEqual(candidate_position["freshness_status"], "CURRENT")
        self.assertEqual(candidate_position["decision_status"], "ACCEPTED")
        self.assertEqual(route["member_states"], {"M-OUT": "TRUE"})
        self.assertEqual(route["state"], "TRUE")
        self.assertEqual(output["support_combination_results"][0]["state"], "TRUE")
        self.assertEqual(
            freshness_deltas,
            {
                ("M-OUT", "CURRENT", "SUCCESSFUL_RECOMPUTATION"),
                ("P-TARGET", "CURRENT", "SUCCESSFUL_RECOMPUTATION"),
            },
        )
        self.assertTrue(
            compare_modes(graph, correction_event("EV-RECOMPUTE"), mapping)[
                "equivalent"
            ]
        )

    def test_clean_independent_route_keeps_position_current(self):
        graph = base_graph(include_clean_route=True)
        mapping = empty_mapping()
        mapping["directed_model_edges"] = [
            {
                "edge_id": "E-IN-OUT",
                "from_model_node_id": "M-IN",
                "to_model_node_id": "M-OUT",
            }
        ]

        result = run(graph, correction_event("EV-ALTERNATIVE"), mapping)
        output = result["transition_output"]
        routes = {
            item["route_id"]: item for item in output["route_results"]
        }
        candidate_position = result["candidate_state"]["current_graph"][
            "case_positions"
        ][0]
        freshness_ids = {
            item["object_id"]
            for item in output["candidate_current_approved_delta"]["candidate"]
            if item["field"] == "freshness_status"
        }

        self.assertEqual(routes["R-MODEL"]["state"], "UNKNOWN")
        self.assertIn(
            "STALE_UPSTREAM_BASIS", routes["R-MODEL"]["reason_codes"]
        )
        self.assertEqual(routes["R-CLEAN"]["state"], "TRUE")
        self.assertEqual(output["support_combination_results"][0]["state"], "TRUE")
        self.assertEqual(candidate_position["freshness_status"], "CURRENT")
        self.assertEqual(freshness_ids, {"M-OUT"})
        self.assertTrue(
            compare_modes(graph, correction_event("EV-ALTERNATIVE"), mapping)[
                "equivalent"
            ]
        )


if __name__ == "__main__":
    unittest.main()
