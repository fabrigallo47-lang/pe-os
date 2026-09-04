import copy
import json
import unittest
from pathlib import Path

from runtime import apply_state_transition, build_runtime_state


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def suite():
    return load_json("benchmark/transition_engine_conformance_cases_v1.json")


def normative_case(test_id):
    return next(case for case in suite()["cases"] if case["test_id"] == test_id)


def synthetic_fixture(fixture_id):
    return next(
        fixture for fixture in suite()["synthetic_fixtures"] if fixture["fixture_id"] == fixture_id
    )


def policies():
    return (
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


def cumulative_policy(object_id, threshold):
    policy = load_json("benchmark/keystone_materiality_policy_v0.json")
    policy["economic_thresholds"] = [
        {
            "rule_id": "MAT-TEST-CUMULATION",
            "metric": "PROTECTED_OUTPUT",
            "selectors": {"model_node_ids": [object_id]},
            "aggregation": "ANY",
            "tests": [
                {
                    "basis": "ABSOLUTE_CHANGE",
                    "operator": "gte",
                    "value": threshold,
                    "unit": "$mm",
                }
            ],
            "minimum_class_when_triggered": "M1_PROFESSIONAL_REVIEW",
        }
    ]
    return policy


def base_graph(case_id):
    return {
        "schema_version": "1.1.0",
        "case_id": case_id,
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


def mapping():
    return {
        "mapping_version": "TEST-CUMULATION-RULES",
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


def event(event_id, known_at, object_id, old, new):
    return {
        "event_id": event_id,
        "event": "Update protected output",
        "effective_date": known_at[:10],
        "known_at": known_at,
        "source_ids": ["S-TEST"],
        "trigger_claim_ids": [],
        "mutations": [
            {
                "operation": "CORRECT",
                "object_type": "MODEL_NODE",
                "object_id": object_id,
                "field": "value",
                "from": old,
                "to": new,
                "unit": "$mm",
            }
        ],
    }


def advance_working_state(result):
    state = copy.deepcopy(result["candidate_state"])
    state["state_id"] = result["candidate_state"]["state_id"]
    state["history"].extend(result["history_append"])
    state.pop("pending_history_append", None)
    state.pop("runtime_flags", None)
    state.pop("candidate_graph_hash", None)
    return state


class RuntimeCumulationAndRuleSwitchTests(unittest.TestCase):
    def test_tce019_cumulation_compares_candidate_to_k_t(self):
        fixture = synthetic_fixture("SF-CUMULATION-KT")
        graph = base_graph(fixture["fixture_id"])
        graph["model_nodes"].append(
            {
                "model_node_id": fixture["protected_output_id"],
                "name": "Firm EBITDA protected output",
                "kind": "derived",
                "definition_id": "DEF-EBITDA-FIRM",
                "period": "LTM",
                "perimeter": "Firm",
                "value": fixture["last_absorbed_current_value"],
                "unit": fixture["unit"],
            }
        )
        state = build_runtime_state(
            graph,
            k_t={fixture["protected_output_id"]: fixture["last_absorbed_current_value"]},
        )
        _, authority_policy = policies()
        materiality_policy = cumulative_policy(
            fixture["protected_output_id"], fixture["absolute_materiality_threshold"]
        )
        outputs = []
        old = fixture["last_absorbed_current_value"]
        case = normative_case("TCE-019-CUMULATION-AGAINST-KT")
        for item in case["event_sequence"]:
            result = apply_state_transition(
                state,
                [event(item["event_id"], item["known_at"], fixture["protected_output_id"], old, item["candidate_value"])],
                mapping(),
                materiality_policy,
                authority_policy,
            )
            outputs.append(result["transition_output"])
            state = advance_working_state(result)
            old = item["candidate_value"]

        self.assertEqual(outputs[0]["materiality_assessment"]["overall_class"], "M0_LOCAL")
        self.assertEqual(outputs[1]["materiality_assessment"]["overall_class"], "M0_LOCAL")
        third = outputs[2]
        self.assertEqual(third["materiality_assessment"]["overall_class"], "M1_PROFESSIONAL_REVIEW")
        self.assertEqual(third["accumulation"]["K_t"][fixture["protected_output_id"]], "11.40")
        self.assertIn(
            "CUMULATIVE_THRESHOLD_CROSSED",
            {item.get("reason_code") for item in third["materiality_assessment"]["assessments"]},
        )

    def test_tce019_epsilon_events_are_audited_and_trigger_at_63(self):
        fixture = synthetic_fixture("SF-CUMULATION-KT")
        object_id = fixture["protected_output_id"]
        graph = base_graph("SF-CUMULATION-KT-EPSILON")
        graph["model_nodes"].append(
            {
                "model_node_id": object_id,
                "name": "Firm EBITDA protected output",
                "kind": "derived",
                "definition_id": "DEF-EBITDA-FIRM",
                "period": "LTM",
                "perimeter": "Firm",
                "value": "11.400",
                "unit": "$mm",
            }
        )
        execution_mapping = mapping()
        execution_mapping["model_nodes"] = [
            {
                "model_node_id": object_id,
                "unit": "$mm",
                "period": "LTM",
                "perimeter": "Firm",
                "immediate_propagation_tolerance": fixture["immediate_propagation_tolerance"],
            }
        ]
        state = build_runtime_state(graph, k_t={object_id: "11.400"})
        _, authority_policy = policies()
        materiality_policy = cumulative_policy(
            object_id, fixture["absolute_materiality_threshold"]
        )
        old = "11.400"
        outputs = []
        for index in range(1, 64):
            new = f"{11.4 - 0.004 * index:.3f}"
            result = apply_state_transition(
                state,
                [event(f"EV-EPS-{index:03d}", f"2026-07-{10 + (index - 1) // 24:02d}T{(index - 1) % 24:02d}:00:00Z", object_id, old, new)],
                execution_mapping,
                materiality_policy,
                authority_policy,
            )
            outputs.append(result["transition_output"])
            state = advance_working_state(result)
            old = new

        self.assertTrue(all(not item["affected_set"] for item in outputs[:62]))
        self.assertTrue(all(item["accumulation"]["sub_tolerance_recorded"] for item in outputs))
        self.assertEqual(outputs[62]["accumulation"]["cumulative_trigger_ids"], [object_id])
        self.assertIn(
            "CUMULATIVE_THRESHOLD_CROSSED",
            {item.get("reason_code") for item in outputs[62]["materiality_assessment"]["assessments"]},
        )

    def test_tce020_rule_switch_is_material_with_zero_output_delta(self):
        fixture = synthetic_fixture("SF-FINANCING-GRID-SWITCH")
        graph = base_graph(fixture["fixture_id"])
        graph["claims"].append(
            {
                "claim_id": "C-SINGLE-PARENT-EXPOSURE",
                "statement": "Single-parent exposure",
                "value": "0.149",
                "unit": "decimal_ratio",
                "period": "CURRENT_UNDERWRITING",
                "perimeter": "Borrower group customer exposure",
            }
        )
        graph["model_nodes"].append(
            {
                "model_node_id": "M-FINANCING-CAPACITY",
                "name": "Financing capacity",
                "kind": "derived",
                "value": "40.0",
                "unit": "$mm",
                "period": "CURRENT_UNDERWRITING",
                "perimeter": "Borrower group",
            }
        )
        execution_mapping = mapping()
        execution_mapping["rule_switches"] = [
            {
                "rule_switch_id": "RS-FINANCING-GRID",
                "selector_input_ids": ["C-SINGLE-PARENT-EXPOSURE"],
                "branches": [
                    {"branch_id": branch["rule_id"], "condition": branch["condition"]}
                    for branch in fixture["branches"]
                ],
                "source_ref": fixture["rule_source_ref"],
                "dependent_ids": ["M-FINANCING-CAPACITY"],
                "minimum_materiality_class": "M2_GATE_AUTHORITY",
                "authority_change_types": ["LEVERAGE"],
                "numeric_delta_at_switch_detection": "0",
            }
        ]
        case = normative_case("TCE-020-RULE-SWITCH-MATERIAL-WITH-ZERO-NUMERIC-DELTA")
        output = apply_state_transition(
            graph,
            case["event_batch"],
            execution_mapping,
            *policies(),
        )["transition_output"]

        switch = output["rule_switches"][0]
        self.assertEqual(switch["from"], "GRID-DIVERSIFIED")
        self.assertEqual(switch["to"], "GRID-SINGLE-PARENT-STEPDOWN")
        self.assertEqual(switch["source_ref"], fixture["rule_source_ref"])
        self.assertEqual(switch["numeric_delta"], "0")
        self.assertEqual(switch["reason_code"], "RULE_SWITCH_MATERIAL_BY_DEFINITION")
        self.assertTrue(switch["dependent_financing_component_requeued"])
        self.assertEqual(output["materiality_assessment"]["overall_class"], "M2_GATE_AUTHORITY")
        self.assertEqual(
            output["authority_resolution"]["selected_rule_id"], "AUTH-040"
        )
        self.assertIn(
            "M-FINANCING-CAPACITY",
            {item["object_id"] for item in output["affected_set"]},
        )


if __name__ == "__main__":
    unittest.main()
