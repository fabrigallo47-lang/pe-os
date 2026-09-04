import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from runtime import apply_state_transition


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normative_case(test_id):
    suite = load_json("benchmark/transition_engine_conformance_cases_v1.json")
    return next(case for case in suite["cases"] if case["test_id"] == test_id)


def empty_mapping():
    return {
        "mapping_version": "TEST",
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
        "decision_snapshot": {"approved_marker": "FROZEN"},
    }


def leverage_policy_with_declared_limit():
    policy = load_json("benchmark/keystone_materiality_policy_v0.json")
    leverage_rule = next(
        rule
        for rule in policy["economic_thresholds"]
        if rule["rule_id"] == "MAT-ECON-005"
    )
    absolute_test = next(
        test for test in leverage_rule["tests"] if test["basis"] == "ABSOLUTE_CHANGE"
    )
    absolute_test["value"] = "1.00"
    limit_test = next(
        test for test in leverage_rule["tests"] if test["basis"] == "LIMIT_CROSSING"
    )
    limit_test["unit"] = "x"
    limit_test["limits"] = [
        {
            "limit_id": "COV-NET-LEVERAGE",
            "limit_type": "COVENANT",
            "operator": "lte",
            "value": "4.50",
            "unit": "x",
            "source_ref": "S-CREDIT-AGREEMENT",
        }
    ]
    return policy


def run(graph, event_batch, mapping=None):
    return apply_state_transition(
        graph,
        event_batch,
        mapping or empty_mapping(),
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class RuntimeMaterialityAndGovernanceTests(unittest.TestCase):
    def test_materiality_policy_conforms_to_declared_input_schema(self):
        schema = load_json("schemas/materiality_policy.schema.json")
        policy = load_json("benchmark/keystone_materiality_policy_v0.json")

        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(policy),
            key=lambda error: list(error.absolute_path),
        )
        self.assertEqual(errors, [])

    def test_authority_policy_conforms_to_declared_input_schema(self):
        schema = load_json("schemas/authority_policy.schema.json")
        policy = load_json("benchmark/keystone_authority_matrix_v0.json")

        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(policy),
            key=lambda error: list(error.absolute_path),
        )
        self.assertEqual(errors, [])

    def test_tce005_material_contradiction_contests_candidate_only(self):
        graph = base_graph("SYNTHETIC-CRITICAL-POSITION")
        graph["case_positions"].append(
            {
                "position_id": "P-CRITICAL",
                "statement": "Critical position",
                "definition_id": "DEF-X",
                "period": "FY2026",
                "perimeter": "PERIMETER-X",
                "criticality": "critical",
                "epistemic_status_at_ic": "ESTABLISHED",
                "decision_status_at_ic": "ACCEPTED",
                "freshness_status_at_ic": "CURRENT",
                "outcome_status_at_ic": "NOT_TESTED",
                "model_binding_status": "UNMAPPED",
            }
        )
        case = normative_case("TCE-005-APPLICABLE-MATERIAL-CONTRADICTION")
        result = run(graph, case["event_batch"])
        output = result["transition_output"]

        epistemic_delta = next(
            item
            for item in output["candidate_current_approved_delta"]["candidate"]
            if item["object_id"] == "P-CRITICAL" and item["field"] == "epistemic_status"
        )
        self.assertEqual(epistemic_delta["to"], "CONTESTED")
        self.assertFalse(
            any(item["field"].startswith("decision_status") for item in output["candidate_current_approved_delta"]["candidate"])
        )
        self.assertEqual(output["materiality_assessment"]["overall_class"], "M1_PROFESSIONAL_REVIEW")
        self.assertIn(
            "QUALIFIED_PROFESSIONAL_REVIEWER",
            {item["required_role"] for item in output["human_stops"]},
        )
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        self.assertNotEqual(epistemic_delta["to"], "STALE")
        self.assertEqual(
            output["authority_resolution"]["selected_rule_id"], "AUTH-020"
        )

    def test_tce007_m0_derived_change_auto_reconciles_current(self):
        graph = base_graph("SYNTHETIC-DERIVED-ONLY")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-DERIVED",
                "name": "Derived output",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "100.00",
                "unit": "$mm",
            }
        )
        case = normative_case("TCE-007-M0-DETERMINISTIC-RECONCILIATION")
        output = run(graph, case["event_batch"])["transition_output"]

        self.assertEqual(output["materiality_assessment"]["overall_class"], "M0_LOCAL")
        self.assertEqual(output["governance"]["current_treatment"], "AUTOMATIC_RECONCILIATION")
        self.assertEqual(output["partial_settlement_status"]["current"], "RECONCILED")
        self.assertEqual(output["human_stops"], [])
        self.assertTrue(output["candidate_current_approved_delta"]["current"])
        self.assertTrue(
            all(item["status"] == "APPLIED" for item in output["candidate_current_approved_delta"]["current"])
        )
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        self.assertEqual(output["authority_resolution"]["status"], "RESOLVED")
        self.assertEqual(
            output["authority_resolution"]["selected_rule_id"], "AUTH-000"
        )
        self.assertEqual(
            output["materiality_assessment"]["classification_coverage"]["status"],
            "COMPLETE",
        )
        self.assertIn(
            "EXPLICIT_M0_SAFE_HARBOR",
            {
                item["reason_code"]
                for item in output["materiality_assessment"]["assessments"]
            },
        )

    def test_unmatched_model_change_fails_closed_to_professional_review(self):
        graph = base_graph("SYNTHETIC-UNMATCHED-MATERIALITY")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-UNMATCHED",
                "name": "Unclassified operating input",
                "kind": "input",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "1.0",
                "unit": "$mm",
            }
        )
        event_batch = [
            {
                "event_id": "EV-UNMATCHED-MATERIALITY",
                "event": "Large unclassified model correction",
                "effective_date": "2026-07-02",
                "known_at": "2026-07-02T10:00:00Z",
                "source_ids": ["S-TEST"],
                "trigger_claim_ids": [],
                "mutations": [
                    {
                        "operation": "CORRECT",
                        "object_type": "MODEL_NODE",
                        "object_id": "M-UNMATCHED",
                        "field": "value",
                        "from": "1.0",
                        "to": "1000.0",
                        "unit": "$mm",
                    }
                ],
            }
        ]

        output = run(graph, event_batch)["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        coverage = output["materiality_assessment"]["classification_coverage"]
        self.assertEqual(coverage["status"], "FAIL_CLOSED")
        self.assertEqual(
            coverage["unmatched_delta_keys"],
            ["MODEL_NODE:M-UNMATCHED.value"],
        )
        self.assertEqual(
            output["governance"]["current_treatment"],
            "PROFESSIONAL_REVIEW_REQUIRED",
        )
        self.assertEqual(
            output["candidate_current_approved_delta"]["current"], []
        )
        self.assertIn(
            "MATERIALITY_POLICY_COVERAGE_UNPROVEN",
            {item["reason_code"] for item in output["human_stops"]},
        )
        self.assertIn(
            "MATERIALITY_POLICY_COVERAGE_UNPROVEN",
            {item["reason_code"] for item in output["coverage_limits"]},
        )

    def test_missing_coverage_declaration_is_safe_by_default(self):
        graph = base_graph("SYNTHETIC-MISSING-COVERAGE-DECLARATION")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-DERIVED",
                "name": "Derived output",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "100.00",
                "unit": "$mm",
            }
        )
        case = normative_case("TCE-007-M0-DETERMINISTIC-RECONCILIATION")
        policy = load_json("benchmark/keystone_materiality_policy_v0.json")
        policy.pop("classification_coverage")

        output = apply_state_transition(
            graph,
            case["event_batch"],
            empty_mapping(),
            policy,
            load_json("benchmark/keystone_authority_matrix_v0.json"),
        )["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        coverage = output["materiality_assessment"]["classification_coverage"]
        self.assertFalse(coverage["policy_declaration_present"])
        self.assertEqual(coverage["status"], "FAIL_CLOSED")
        self.assertEqual(
            output["candidate_current_approved_delta"]["current"], []
        )

    def test_incomplete_m0_safe_harbor_fails_closed(self):
        graph = base_graph("SYNTHETIC-INCOMPLETE-M0-SAFE-HARBOR")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-DERIVED",
                "name": "Derived output",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "100.00",
                "unit": "$mm",
            }
        )
        case = normative_case("TCE-007-M0-DETERMINISTIC-RECONCILIATION")
        policy = load_json("benchmark/keystone_materiality_policy_v0.json")
        policy["classification_coverage"]["m0_safe_harbors"][0][
            "conditions"
        ] = []

        output = apply_state_transition(
            graph,
            case["event_batch"],
            empty_mapping(),
            policy,
            load_json("benchmark/keystone_authority_matrix_v0.json"),
        )["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        self.assertEqual(
            output["materiality_assessment"]["classification_coverage"]["status"],
            "FAIL_CLOSED",
        )
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])

    def test_matching_rule_with_unevaluable_test_fails_at_rule_minimum(self):
        graph = base_graph("SYNTHETIC-UNEVALUABLE-MATERIALITY")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-LEVERAGE-UNCLASSIFIED",
                "name": "Net leverage",
                "kind": "input",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "4.00",
                "unit": "x",
            }
        )
        event_batch = [
            {
                "event_id": "EV-UNEVALUABLE-MATERIALITY",
                "event": "Small leverage correction without executable limit context",
                "effective_date": "2026-07-02",
                "known_at": "2026-07-02T10:00:00Z",
                "source_ids": ["S-TEST"],
                "trigger_claim_ids": [],
                "mutations": [
                    {
                        "operation": "CORRECT",
                        "object_type": "MODEL_NODE",
                        "object_id": "M-LEVERAGE-UNCLASSIFIED",
                        "field": "value",
                        "from": "4.00",
                        "to": "4.01",
                        "unit": "x",
                    }
                ],
            }
        ]

        output = run(graph, event_batch)["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M2_GATE_AUTHORITY",
        )
        coverage = output["materiality_assessment"]["classification_coverage"]
        self.assertEqual(coverage["status"], "FAIL_CLOSED")
        self.assertEqual(
            coverage["unevaluable_delta_keys"],
            ["MODEL_NODE:M-LEVERAGE-UNCLASSIFIED.value"],
        )
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(
            output["partial_settlement_status"]["approved"],
            "AUTHORITY_PENDING",
        )
        self.assertIn(
            "MATERIALITY_RULE_NOT_FULLY_EVALUABLE",
            {item["reason_code"] for item in output["coverage_limits"]},
        )

    def test_declared_limit_crossing_is_evaluated_and_disclosed(self):
        graph = base_graph("SYNTHETIC-DECLARED-LIMIT-CROSSING")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-LEVERAGE-DECLARED",
                "name": "Net leverage",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "4.40",
                "unit": "x",
            }
        )
        event_batch = [
            {
                "event_id": "EV-DECLARED-LIMIT-CROSSING",
                "event": "Net leverage enters covenant breach",
                "effective_date": "2026-07-02",
                "known_at": "2026-07-02T10:00:00Z",
                "source_ids": ["S-CREDIT-AGREEMENT"],
                "trigger_claim_ids": [],
                "mutations": [
                    {
                        "operation": "CORRECT",
                        "object_type": "MODEL_NODE",
                        "object_id": "M-LEVERAGE-DECLARED",
                        "field": "value",
                        "from": "4.40",
                        "to": "4.60",
                        "unit": "x",
                    }
                ],
            }
        ]

        output = apply_state_transition(
            graph,
            event_batch,
            empty_mapping(),
            leverage_policy_with_declared_limit(),
            load_json("benchmark/keystone_authority_matrix_v0.json"),
        )["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M2_GATE_AUTHORITY",
        )
        self.assertEqual(
            output["materiality_assessment"]["classification_coverage"]["status"],
            "COMPLETE",
        )
        assessment = next(
            item
            for item in output["materiality_assessment"]["assessments"]
            if item["rule_id"] == "MAT-ECON-005"
        )
        crossing_test = next(
            item for item in assessment["tests"] if item["basis"] == "LIMIT_CROSSING"
        )
        self.assertEqual(
            crossing_test["observed"]["crossings"],
            [
                {
                    "limit_id": "COV-NET-LEVERAGE",
                    "limit_type": "COVENANT",
                    "operator": "lte",
                    "limit_value": "4.5",
                    "source_ref": "S-CREDIT-AGREEMENT",
                    "direction": "INTO_BREACH",
                }
            ],
        )
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(
            output["partial_settlement_status"]["approved"],
            "AUTHORITY_PENDING",
        )

    def test_declared_limit_without_crossing_remains_fully_evaluable(self):
        graph = base_graph("SYNTHETIC-DECLARED-LIMIT-NO-CROSSING")
        graph["model_nodes"].append(
            {
                "model_node_id": "M-LEVERAGE-DECLARED",
                "name": "Net leverage",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "4.00",
                "unit": "x",
            }
        )
        event_batch = [
            {
                "event_id": "EV-DECLARED-LIMIT-NO-CROSSING",
                "event": "Net leverage changes inside covenant limit",
                "effective_date": "2026-07-02",
                "known_at": "2026-07-02T10:00:00Z",
                "source_ids": ["S-CREDIT-AGREEMENT"],
                "trigger_claim_ids": [],
                "mutations": [
                    {
                        "operation": "CORRECT",
                        "object_type": "MODEL_NODE",
                        "object_id": "M-LEVERAGE-DECLARED",
                        "field": "value",
                        "from": "4.00",
                        "to": "4.10",
                        "unit": "x",
                    }
                ],
            }
        ]

        output = apply_state_transition(
            graph,
            event_batch,
            empty_mapping(),
            leverage_policy_with_declared_limit(),
            load_json("benchmark/keystone_authority_matrix_v0.json"),
        )["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        coverage = output["materiality_assessment"]["classification_coverage"]
        self.assertEqual(coverage["status"], "COMPLETE")
        self.assertEqual(coverage["unevaluable_delta_keys"], [])
        self.assertEqual(
            output["materiality_assessment"]["m0_auto_reconciliation_guards"][
                "status"
            ],
            "FAIL",
        )
        self.assertIn(
            "NO_RESERVED_DECISION_CHANGE",
            output["materiality_assessment"]["m0_auto_reconciliation_guards"][
                "failed_conditions"
            ],
        )
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(
            output["authority_resolution"]["selected_rule_id"], "AUTH-040"
        )
        self.assertEqual(
            output["partial_settlement_status"]["approved"], "AUTHORITY_PENDING"
        )

    def test_below_threshold_input_does_not_bypass_m0_guards(self):
        graph = base_graph("SYNTHETIC-M0-GUARD-FAILURE")
        graph["model_nodes"].append(
            {
                "model_node_id": "MN-TEST-MOIC",
                "name": "Test MOIC input",
                "kind": "input",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "2.00",
                "unit": "x",
            }
        )
        event_batch = [
            {
                "event_id": "EV-M0-GUARD-FAILURE",
                "event": "Sub-threshold direct input correction",
                "effective_date": "2026-07-02",
                "known_at": "2026-07-02T10:00:00Z",
                "source_ids": ["S-TEST"],
                "trigger_claim_ids": [],
                "mutations": [
                    {
                        "operation": "CORRECT",
                        "object_type": "MODEL_NODE",
                        "object_id": "MN-TEST-MOIC",
                        "field": "value",
                        "from": "2.00",
                        "to": "2.01",
                        "unit": "x",
                    }
                ],
            }
        ]

        output = run(graph, event_batch)["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["classification_coverage"]["status"],
            "COMPLETE",
        )
        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        guard_result = output["materiality_assessment"][
            "m0_auto_reconciliation_guards"
        ]
        self.assertEqual(guard_result["status"], "FAIL")
        self.assertIn(
            "DETERMINISTIC_DERIVED_CHANGE",
            guard_result["failed_conditions"],
        )
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertIn(
            "M0_AUTO_RECONCILIATION_GUARDS_FAILED",
            {item["reason_code"] for item in output["human_stops"]},
        )

    def test_matching_rule_without_tests_fails_closed(self):
        graph = base_graph("SYNTHETIC-EMPTY-MATERIALITY-RULE")
        graph["model_nodes"].append(
            {
                "model_node_id": "MN-TEST-MOIC",
                "name": "Test derived MOIC",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "2.00",
                "unit": "x",
            }
        )
        policy = load_json("benchmark/keystone_materiality_policy_v0.json")
        moic_rule = next(
            rule
            for rule in policy["economic_thresholds"]
            if rule["rule_id"] == "MAT-ECON-004"
        )
        moic_rule["tests"] = []
        event_batch = [
            {
                "event_id": "EV-EMPTY-MATERIALITY-RULE",
                "event": "Correction matched by an incomplete rule",
                "effective_date": "2026-07-02",
                "known_at": "2026-07-02T10:00:00Z",
                "source_ids": ["S-TEST"],
                "trigger_claim_ids": [],
                "mutations": [
                    {
                        "operation": "CORRECT",
                        "object_type": "MODEL_NODE",
                        "object_id": "MN-TEST-MOIC",
                        "field": "value",
                        "from": "2.00",
                        "to": "2.01",
                        "unit": "x",
                    }
                ],
            }
        ]

        output = apply_state_transition(
            graph,
            event_batch,
            empty_mapping(),
            policy,
            load_json("benchmark/keystone_authority_matrix_v0.json"),
        )["transition_output"]

        self.assertEqual(
            output["materiality_assessment"]["overall_class"],
            "M1_PROFESSIONAL_REVIEW",
        )
        self.assertEqual(
            output["materiality_assessment"]["classification_coverage"]["status"],
            "FAIL_CLOSED",
        )
        self.assertIn(
            "MATERIALITY_RULE_NOT_FULLY_EVALUABLE",
            {
                item["reason_code"]
                for item in output["materiality_assessment"]["assessments"]
            },
        )

    def test_tce008_exact_ev_threshold_is_inclusive_and_requires_authority(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        result = run(graph, case["event_batch"], load_json("benchmark/keystone_execution_mapping_v0.json"))
        output = result["transition_output"]

        self.assertEqual(output["materiality_assessment"]["overall_class"], "M2_GATE_AUTHORITY")
        self.assertIn("MAT-ECON-002", output["materiality_assessment"]["triggered_rule_ids"])
        self.assertEqual(output["partial_settlement_status"]["current"], "REVIEW_PENDING")
        self.assertEqual(output["partial_settlement_status"]["approved"], "AUTHORITY_PENDING")
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        self.assertEqual(result["candidate_state"]["approved_snapshot"], graph["decision_snapshot"])
        self.assertEqual(
            output["authority_resolution"]["selected_rule_id"], "AUTH-040"
        )

    def test_authority_roles_are_resolved_from_the_versioned_policy(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        reserved_rule = next(
            rule for rule in authority_policy["rules"] if rule["rule_id"] == "AUTH-040"
        )
        reserved_rule["current_adoption"]["required_role"] = "CUSTOM_CURRENT_REVIEWER"
        reserved_rule["approved_action"]["required_role_beyond_delegation"] = "CUSTOM_IC"

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        resolution = output["authority_resolution"]
        self.assertEqual(resolution["status"], "RESOLVED")
        self.assertEqual(resolution["selected_rule_id"], "AUTH-040")
        self.assertEqual(
            resolution["matched_rule_ids"], ["AUTH-035", "AUTH-040"]
        )
        self.assertEqual(
            resolution["context"]["change_types"],
            ["MODEL_INPUT_CORRECTION", "PRICE"],
        )
        current_stop = next(
            item for item in output["human_stops"] if item["stop_id"] == "STOP-CURRENT-REVIEW"
        )
        approved_stop = next(
            item for item in output["human_stops"] if item["stop_id"] == "STOP-APPROVED-AUTHORITY"
        )
        self.assertEqual(current_stop["required_role"], "CUSTOM_CURRENT_REVIEWER")
        self.assertEqual(approved_stop["required_role"], "CUSTOM_IC")
        self.assertEqual(current_stop["policy_rule_id"], "AUTH-040")
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])

    def test_missing_authority_route_fails_closed_without_hardcoded_fallback(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        authority_policy["rules"] = [
            rule
            for rule in authority_policy["rules"]
            if rule["rule_id"] not in {"AUTH-035", "AUTH-040"}
        ]

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        self.assertEqual(output["authority_resolution"]["status"], "UNRESOLVED")
        self.assertEqual(
            output["authority_resolution"]["reason_code"],
            "NO_AUTHORITY_RULE_MATCH",
        )
        stop = next(
            item
            for item in output["human_stops"]
            if item["stop_id"] == "STOP-AUTHORITY-ROUTING"
        )
        self.assertEqual(stop["reason_code"], "AUTHORITY_POLICY_UNRESOLVED")
        self.assertEqual(stop["required_role"], "AUTHORITY_POLICY_OWNER")
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])

    def test_equal_highest_authority_priority_is_ambiguous_and_fails_closed(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        duplicate = copy.deepcopy(
            next(
                rule
                for rule in authority_policy["rules"]
                if rule["rule_id"] == "AUTH-040"
            )
        )
        duplicate["rule_id"] = "AUTH-041"
        authority_policy["rules"].append(duplicate)

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        resolution = output["authority_resolution"]
        self.assertEqual(resolution["status"], "AMBIGUOUS")
        self.assertEqual(
            resolution["reason_code"], "AMBIGUOUS_AUTHORITY_RULE_PRIORITY"
        )
        self.assertEqual(resolution["selected_rule_id"], None)
        self.assertEqual(resolution["selected_priority"], 50)
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        self.assertIn(
            "AUTHORITY_POLICY_UNRESOLVED",
            {item["reason_code"] for item in output["human_stops"]},
        )

    def test_duplicate_authority_rule_id_fails_closed(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        duplicate = copy.deepcopy(
            next(
                rule
                for rule in authority_policy["rules"]
                if rule["rule_id"] == "AUTH-040"
            )
        )
        duplicate["name"] = "Conflicting duplicate identity"
        authority_policy["rules"].append(duplicate)

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        resolution = output["authority_resolution"]
        self.assertEqual(resolution["status"], "UNRESOLVED")
        self.assertEqual(
            resolution["reason_code"], "DUPLICATE_AUTHORITY_RULE_ID"
        )
        self.assertIsNone(resolution["selected_rule_id"])
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])

    def test_malformed_high_priority_rule_cannot_fall_through(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        reserved_rule = next(
            rule
            for rule in authority_policy["rules"]
            if rule["rule_id"] == "AUTH-040"
        )
        reserved_rule["priority"] = "50"

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        resolution = output["authority_resolution"]
        self.assertEqual(resolution["status"], "UNRESOLVED")
        self.assertEqual(
            resolution["reason_code"], "MALFORMED_AUTHORITY_RULE_SET"
        )
        self.assertNotEqual(resolution.get("selected_rule_id"), "AUTH-035")
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])

    def test_unsafe_authority_resolution_policy_fails_closed(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        authority_policy["rule_resolution"][
            "escalation_required_when_delegation_unproven"
        ] = False

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        resolution = output["authority_resolution"]
        self.assertEqual(resolution["status"], "UNRESOLVED")
        self.assertEqual(
            resolution["reason_code"], "UNSAFE_AUTHORITY_RESOLUTION_POLICY"
        )
        self.assertIsNone(resolution["selected_rule_id"])
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])

    def test_incomplete_highest_priority_authority_rule_fails_closed(self):
        graph = load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")
        case = normative_case("TCE-008-M2-INCLUSIVE-EV-THRESHOLD")
        authority_policy = load_json("benchmark/keystone_authority_matrix_v0.json")
        reserved_rule = next(
            rule
            for rule in authority_policy["rules"]
            if rule["rule_id"] == "AUTH-040"
        )
        reserved_rule["approved_action"].pop("required_role_beyond_delegation")
        reserved_rule["approved_action"].pop("required_role_within_delegation")
        reserved_rule["escalation"] = None

        output = apply_state_transition(
            graph,
            case["event_batch"],
            load_json("benchmark/keystone_execution_mapping_v0.json"),
            load_json("benchmark/keystone_materiality_policy_v0.json"),
            authority_policy,
        )["transition_output"]

        resolution = output["authority_resolution"]
        self.assertEqual(resolution["status"], "UNRESOLVED")
        self.assertEqual(
            resolution["reason_code"], "INCOMPLETE_AUTHORITY_RULE_ACTION"
        )
        self.assertEqual(resolution["selected_rule_id"], None)
        self.assertEqual(resolution["selected_priority"], None)
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])

    def test_tce009_non_waivable_axiom_is_m3_and_blocks_gate(self):
        graph = base_graph("SYNTHETIC-AXIOM")
        graph["claims"].append(
            {
                "claim_id": "C-AXIOM-FAIL",
                "statement": "Axiom is satisfied",
                "source_id": "S-POLICY",
                "locator": "fixture",
                "epistemic_class": "attested",
                "period": "FY2026",
                "perimeter": "TEST",
                "ground_truth_flag": False,
                "validation_only": False,
                "satisfied": True,
            }
        )
        case = normative_case("TCE-009-M3-NON-WAIVABLE-AXIOM")
        output = run(graph, case["event_batch"])["transition_output"]

        self.assertEqual(output["materiality_assessment"]["overall_class"], "M3_HARD_BLOCKER")
        self.assertEqual(output["governance"]["gate_status"], "BLOCKED")
        self.assertFalse(output["governance"]["waiver_allowed"])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        self.assertEqual(
            output["authority_resolution"]["selected_rule_id"], "AUTH-050"
        )

    def test_tce021_preparer_cannot_adopt_own_change(self):
        graph = base_graph("SF-INDEPENDENT-REVIEW")
        case = normative_case("TCE-021-PREPARER-CANNOT-SELF-ADOPT")
        output = run(graph, case["event_batch"])["transition_output"]

        action = output["governance_action_results"][0]
        self.assertEqual(action["result"], "REJECTED")
        self.assertEqual(action["reason_code"], "SELF_ADOPTION_FORBIDDEN")
        self.assertEqual(
            output["authority_resolution"]["status"], "NOT_APPLICABLE"
        )
        self.assertTrue(action["candidate_change_set_preserved"])
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        stop = next(item for item in output["human_stops"] if item["reason_code"] == "SELF_ADOPTION_FORBIDDEN")
        self.assertEqual(stop["required_role"], "FINANCIAL_OR_WORKSTREAM_REVIEWER")
        self.assertEqual(stop["required_actor_distinct_from"], "ACTOR-ASSOCIATE-01")
        self.assertTrue(any(item["record_type"] == "GOVERNANCE_ACTION_REJECTED" for item in output["audit_records"]))


if __name__ == "__main__":
    unittest.main()
