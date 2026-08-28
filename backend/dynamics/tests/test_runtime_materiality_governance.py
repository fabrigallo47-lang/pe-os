import copy
import json
import unittest
from pathlib import Path

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


def run(graph, event_batch, mapping=None):
    return apply_state_transition(
        graph,
        event_batch,
        mapping or empty_mapping(),
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class RuntimeMaterialityAndGovernanceTests(unittest.TestCase):
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

    def test_tce021_preparer_cannot_adopt_own_change(self):
        graph = base_graph("SF-INDEPENDENT-REVIEW")
        case = normative_case("TCE-021-PREPARER-CANNOT-SELF-ADOPT")
        output = run(graph, case["event_batch"])["transition_output"]

        action = output["governance_action_results"][0]
        self.assertEqual(action["result"], "REJECTED")
        self.assertEqual(action["reason_code"], "SELF_ADOPTION_FORBIDDEN")
        self.assertTrue(action["candidate_change_set_preserved"])
        self.assertEqual(output["candidate_current_approved_delta"]["current"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["approved"], [])
        stop = next(item for item in output["human_stops"] if item["reason_code"] == "SELF_ADOPTION_FORBIDDEN")
        self.assertEqual(stop["required_role"], "FINANCIAL_OR_WORKSTREAM_REVIEWER")
        self.assertEqual(stop["required_actor_distinct_from"], "ACTOR-ASSOCIATE-01")
        self.assertTrue(any(item["record_type"] == "GOVERNANCE_ACTION_REJECTED" for item in output["audit_records"]))


if __name__ == "__main__":
    unittest.main()
