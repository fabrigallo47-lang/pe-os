import copy
import json
import unittest
from pathlib import Path

from runtime import apply_state_transition, compare_incremental_global


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


def graph_from_support_fixture(fixture, *, initially_unusable=None):
    initially_unusable = set(initially_unusable or [])
    claims = [
        {
            "claim_id": claim_id,
            "statement": claim_id,
            "value": None,
            "unit": None,
            "definition_id": None,
            "period": "TEST",
            "perimeter": "TEST",
            "usable": claim_id not in initially_unusable,
            "validation_only": False,
        }
        for claim_id in fixture.get("claims", [])
    ]
    positions = [
        {
            "position_id": position_id,
            "statement": position_id,
            "criticality": "critical",
            "decision_status": "ACCEPTED",
            "freshness_status": "CURRENT",
        }
        for position_id in fixture.get("positions", [])
    ]
    dependencies = [
        {
            "edge_id": f"PD-{index:03d}",
            "from_position_id": dependency["from"],
            "to_position_id": dependency["to"],
            "relation_type": dependency["relation_type"],
        }
        for index, dependency in enumerate(fixture.get("position_dependencies", []), start=1)
    ]
    return {
        "schema_version": "1.1.0",
        "case_id": fixture["fixture_id"],
        "canonical_as_of": "2026-01-01",
        "claims": claims,
        "case_positions": positions,
        "model_nodes": [],
        "support_routes": copy.deepcopy(fixture.get("support_routes", [])),
        "claim_position_edges": [],
        "position_dependencies": dependencies,
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def run(graph, events, mapping=None):
    return apply_state_transition(
        graph,
        events,
        mapping or empty_mapping(),
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


def compare_modes(graph, events, mapping=None):
    return compare_incremental_global(
        graph,
        events,
        mapping or empty_mapping(),
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class RuntimeRoutesAndFormulaTests(unittest.TestCase):
    def test_conflicting_support_is_unknown_publicly_and_stops_governance(self):
        graph = graph_from_support_fixture({
            "fixture_id": "SF-CONFLICTED-SUPPORT",
            "claims": ["C-SUPPORT", "C-COUNTER"],
            "positions": ["P-TARGET"],
            "support_routes": [
                {
                    "route_id": "R-CONFLICTED",
                    "target_position_id": "P-TARGET",
                    "logic": "AND_WITH_COUNTEREVIDENCE",
                    "member_claim_ids": ["C-SUPPORT"],
                    "counter_claim_ids": ["C-COUNTER"],
                }
            ],
        })
        event = {
            "event_id": "EV-EVALUATE-CONFLICT",
            "event": "Evaluate conflicting evidence",
            "effective_date": "2026-01-02",
            "known_at": "2026-01-02T08:00:00Z",
            "source_ids": ["S-REVIEW"],
            "trigger_claim_ids": ["C-COUNTER"],
            "mutations": [],
        }

        output = run(graph, [event])["transition_output"]
        route = next(
            item
            for item in output["route_results"]
            if item["route_id"] == "R-CONFLICTED"
        )
        combined = next(
            item
            for item in output["support_combination_results"]
            if item["position_id"] == "P-TARGET"
        )

        self.assertEqual(route["state"], "UNKNOWN")
        self.assertEqual(combined["state"], "UNKNOWN")
        self.assertIn("CONFLICTING_SUPPORT_EVIDENCE", route["reason_codes"])
        self.assertIn(
            "CONFLICTING_SUPPORT_EVIDENCE",
            {item["reason_code"] for item in output["human_stops"]},
        )
        self.assertIn(
            "CONFLICTING_SUPPORT_EVIDENCE",
            {item["reason_code"] for item in output["blocked_components"]},
        )
        self.assertNotIn("proof_graph", output)
        self.assertNotIn('"state": "CONFLICTED"', json.dumps(output, sort_keys=True))
        self.assertTrue(compare_modes(graph, [event])["equivalent"])

    def test_clean_alternative_route_survives_conflicted_route(self):
        graph = graph_from_support_fixture({
            "fixture_id": "SF-CONFLICTED-ALTERNATIVE",
            "claims": ["C-SUPPORT", "C-COUNTER", "C-ALTERNATIVE"],
            "positions": ["P-TARGET"],
            "support_routes": [
                {
                    "route_id": "R-CONFLICTED",
                    "target_position_id": "P-TARGET",
                    "logic": "AND_WITH_COUNTEREVIDENCE",
                    "member_claim_ids": ["C-SUPPORT"],
                    "counter_claim_ids": ["C-COUNTER"],
                },
                {
                    "route_id": "R-ALTERNATIVE",
                    "target_position_id": "P-TARGET",
                    "logic": "INDEPENDENT",
                    "member_claim_ids": ["C-ALTERNATIVE"],
                },
            ],
        })
        event = {
            "event_id": "EV-EVALUATE-ALTERNATIVE",
            "event": "Evaluate independent support",
            "effective_date": "2026-01-02",
            "known_at": "2026-01-02T08:00:00Z",
            "source_ids": ["S-REVIEW"],
            "trigger_claim_ids": ["C-COUNTER"],
            "mutations": [],
        }

        output = run(graph, [event])["transition_output"]
        combined = next(
            item
            for item in output["support_combination_results"]
            if item["position_id"] == "P-TARGET"
        )

        self.assertEqual(combined["state"], "TRUE")
        self.assertFalse(any(
            item["reason_code"] == "CONFLICTING_SUPPORT_EVIDENCE"
            and item["object_or_component_id"] == "P-TARGET"
            for item in output["human_stops"]
        ))
        self.assertTrue(compare_modes(graph, [event])["equivalent"])

    def test_model_node_member_propagates_through_support_route(self):
        graph = graph_from_support_fixture({
            "fixture_id": "SF-MODEL-SUPPORT",
            "claims": [],
            "positions": ["P-TARGET"],
            "support_routes": [
                {
                    "route_id": "R-MODEL",
                    "target_position_id": "P-TARGET",
                    "logic": "AND",
                    "member_model_node_ids": ["M-INPUT"],
                }
            ],
        })
        graph["model_nodes"] = [
            {
                "model_node_id": "M-INPUT",
                "name": "Model input",
                "kind": "input",
                "period": "TEST",
                "perimeter": "TEST",
                "value": "1",
                "unit": None,
            }
        ]
        event = {
            "event_id": "EV-MODEL-SUPPORT",
            "event": "Model input becomes unknown",
            "effective_date": "2026-01-02",
            "known_at": "2026-01-02T08:00:00Z",
            "source_ids": ["S-MODEL"],
            "trigger_claim_ids": [],
            "mutations": [
                {
                    "operation": "CORRECT",
                    "object_type": "MODEL_NODE",
                    "object_id": "M-INPUT",
                    "field": "value",
                    "from": "1",
                    "to": None,
                }
            ],
        }

        output = run(graph, [event])["transition_output"]
        affected_ids = {item["object_id"] for item in output["affected_set"]}
        route = next(item for item in output["route_results"] if item["route_id"] == "R-MODEL")
        combined = next(
            item
            for item in output["support_combination_results"]
            if item["position_id"] == "P-TARGET"
        )

        self.assertEqual(affected_ids, {"M-INPUT", "R-MODEL", "P-TARGET"})
        self.assertEqual(route["member_states"], {"M-INPUT": "UNKNOWN"})
        self.assertEqual(route["state"], "UNKNOWN")
        self.assertEqual(combined["state"], "UNKNOWN")
        self.assertEqual(output["partial_settlement_status"]["candidate"], "PARTIAL")
        self.assertTrue(compare_modes(graph, [event])["equivalent"])

    def test_counterevidence_member_requeues_its_support_route(self):
        graph = graph_from_support_fixture({
            "fixture_id": "SF-COUNTEREVIDENCE",
            "claims": ["C-SUPPORT", "C-COUNTER"],
            "positions": ["P-TARGET"],
            "support_routes": [
                {
                    "route_id": "R-COUNTER",
                    "target_position_id": "P-TARGET",
                    "logic": "AND_WITH_COUNTEREVIDENCE",
                    "member_claim_ids": ["C-SUPPORT"],
                    "counter_claim_ids": ["C-COUNTER"],
                }
            ],
        })
        event = {
            "event_id": "EV-RETRACT-COUNTER",
            "event": "Retract counterevidence",
            "effective_date": "2026-01-02",
            "known_at": "2026-01-02T08:00:00Z",
            "source_ids": ["S-COUNTER"],
            "trigger_claim_ids": ["C-COUNTER"],
            "mutations": [
                {
                    "operation": "RETRACT",
                    "object_type": "CLAIM",
                    "object_id": "C-COUNTER",
                }
            ],
        }

        output = run(graph, [event])["transition_output"]
        affected_ids = {item["object_id"] for item in output["affected_set"]}
        route = next(
            item for item in output["route_results"] if item["route_id"] == "R-COUNTER"
        )

        self.assertEqual(affected_ids, {"C-COUNTER", "R-COUNTER", "P-TARGET"})
        self.assertEqual(route["counter_member_states"], {"C-COUNTER": "FALSE"})
        self.assertEqual(route["counterevidence_present"], "FALSE")
        self.assertEqual(route["state"], "TRUE")
        self.assertTrue(compare_modes(graph, [event])["equivalent"])

    def test_tce001_formula_recomputes_firm_ebitda(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        mapping = load_json("benchmark/keystone_execution_mapping_v0.json")
        case = normative_case("TCE-001-KEYSTONE-FIRM-EBITDA-CORRECTION")
        result = run(graph, case["event_batch"], mapping)
        output = result["transition_output"]

        formula_result = next(
            item for item in output["route_results"] if item["route_id"] == "SR-EBITDA-FIRM"
        )
        self.assertEqual(formula_result["state"], "TRUE")
        self.assertEqual(formula_result["candidate_value"], "11.0")
        model_result = next(
            item for item in output["recomputed_values"] if item["object_id"] == "MN-FIRM-EBITDA"
        )
        self.assertEqual(model_result["old_value"], 11.4)
        self.assertEqual(model_result["candidate_value"], "11.0")
        candidate_model = next(
            item
            for item in result["candidate_state"]["current_graph"]["model_nodes"]
            if item["model_node_id"] == "MN-FIRM-EBITDA"
        )
        self.assertEqual(candidate_model["value"], "11.0")

    def test_tce002_alternative_route_survives(self):
        fixture = synthetic_fixture("SF-ALTERNATIVE-ROUTES")
        graph = graph_from_support_fixture(fixture)
        case = normative_case("TCE-002-ALTERNATIVE-ROUTE-SURVIVES")
        output = run(graph, case["event_batch"])["transition_output"]
        route_states = {item["route_id"]: item["state"] for item in output["route_results"]}
        combined = {
            item["position_id"]: item["state"]
            for item in output["support_combination_results"]
        }

        self.assertEqual(route_states, {"R-A": "FALSE", "R-B": "TRUE"})
        self.assertEqual(combined["P-TARGET"], "TRUE")
        self.assertIn(
            "ROUTE_SURVIVES_ALTERNATIVE",
            {item["reason_code"] for item in output["unchanged_objects"]},
        )
        self.assertEqual(output["human_stops"], [])
        self.assertEqual(output["partial_settlement_status"]["candidate"], "FULL")

    def test_m0_retraction_safe_harbor_requires_a_surviving_route(self):
        fixture = copy.deepcopy(synthetic_fixture("SF-ALTERNATIVE-ROUTES"))
        fixture["support_routes"] = [
            route for route in fixture["support_routes"] if route["route_id"] == "R-A"
        ]
        graph = graph_from_support_fixture(fixture)
        case = normative_case("TCE-002-ALTERNATIVE-ROUTE-SURVIVES")

        output = run(graph, case["event_batch"])["transition_output"]

        self.assertEqual(
            output["support_combination_results"][0]["state"], "FALSE"
        )
        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        self.assertEqual(
            output["materiality_assessment"]["classification_coverage"]["status"],
            "FAIL_CLOSED",
        )
        self.assertEqual(
            output["candidate_current_approved_delta"]["current"], []
        )

    def test_tce003_circular_routes_do_not_defeat_grounded_route(self):
        fixture = synthetic_fixture("SF-CIRCULAR-SUPPORT")
        graph = graph_from_support_fixture(fixture, initially_unusable={"C-EXT"})
        case = normative_case("TCE-003-CIRCULAR-SUPPORT-WITH-GROUNDED-ALTERNATIVE")
        output = run(graph, case["event_batch"])["transition_output"]
        route_states = {item["route_id"]: item["state"] for item in output["route_results"]}
        combined = {
            item["position_id"]: item["state"]
            for item in output["support_combination_results"]
        }

        self.assertEqual(set(output["invalid_route_ids"]), {"R-CYCLE-A", "R-CYCLE-B"})
        self.assertEqual(route_states["R-EXTERNAL-A"], "TRUE")
        self.assertEqual(combined["P-A"], "TRUE")
        self.assertEqual(output["numerical_solver_invocations"], 0)
        self.assertFalse(output["global_block"])

    def test_tce004_ungrounded_cycle_is_unknown_and_stops(self):
        fixture = copy.deepcopy(synthetic_fixture("SF-CIRCULAR-SUPPORT"))
        fixture["support_routes"] = [
            route for route in fixture["support_routes"] if route["route_id"] != "R-EXTERNAL-A"
        ]
        graph = graph_from_support_fixture(fixture)
        case = normative_case("TCE-004-CIRCULAR-SUPPORT-UNGROUNDED")
        output = run(graph, case["event_batch"])["transition_output"]

        self.assertEqual(set(output["invalid_route_ids"]), {"R-CYCLE-A", "R-CYCLE-B"})
        self.assertTrue(
            all(item["state"] == "UNKNOWN" for item in output["support_combination_results"])
        )
        self.assertIn(
            "CIRCULAR_SUPPORT",
            {item["reason_code"] for item in output["human_stops"]},
        )
        self.assertEqual(output["numerical_solver_invocations"], 0)


if __name__ == "__main__":
    unittest.main()
