import copy
import json
import re
import unittest
from pathlib import Path

from runtime import apply_state_transition, build_runtime_state, compute_affected_set


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_case():
    return load_json("canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json")


def execution_mapping():
    return load_json("benchmark/keystone_execution_mapping_v0.json")


def materiality_policy():
    return load_json("benchmark/keystone_materiality_policy_v0.json")


def authority_policy():
    return load_json("benchmark/keystone_authority_matrix_v0.json")


def normative_case(test_id):
    suite = load_json("benchmark/transition_engine_conformance_cases_v1.json")
    return next(case for case in suite["cases"] if case["test_id"] == test_id)


def synthetic_graph(claims, edges=None, positions=None, routes=None):
    return {
        "schema_version": "1.1.0",
        "case_id": "SYNTHETIC-CASE",
        "canonical_as_of": "2026-01-01",
        "claims": claims,
        "case_positions": positions or [],
        "model_nodes": [],
        "support_routes": routes or [],
        "claim_position_edges": edges or [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def run(graph, events, mapping=None):
    return apply_state_transition(
        graph,
        events,
        mapping or {
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
        },
        materiality_policy(),
        authority_policy(),
    )


class RuntimeCoreTests(unittest.TestCase):
    def test_tce001_canonical_position_closure_is_exact(self):
        graph = canonical_case()
        case = normative_case("TCE-001-KEYSTONE-FIRM-EBITDA-CORRECTION")
        result = run(graph, case["event_batch"], execution_mapping())
        position_ids = sorted(
            item["object_id"]
            for item in result["transition_output"]["affected_set"]
            if item["object_type"] == "POSITION"
        )
        self.assertEqual(position_ids, sorted(case["expected"]["affected_position_ids_exact"]))
        model_ids = {
            item["object_id"]
            for item in result["transition_output"]["affected_set"]
            if item["object_type"] == "MODEL_NODE"
        }
        self.assertIn("MN-FIRM-EBITDA", model_ids)

    def test_candidate_changes_without_mutating_current_or_approved(self):
        graph = canonical_case()
        original = copy.deepcopy(graph)
        case = normative_case("TCE-001-KEYSTONE-FIRM-EBITDA-CORRECTION")
        state = build_runtime_state(graph)
        approved_before = copy.deepcopy(state["approved_snapshot"])
        result = run(state, case["event_batch"], execution_mapping())

        self.assertEqual(graph, original)
        self.assertEqual(state["current_graph"], original)
        self.assertEqual(result["candidate_state"]["approved_snapshot"], approved_before)
        claim = next(
            item
            for item in result["candidate_state"]["current_graph"]["claims"]
            if item["claim_id"] == "CL-028"
        )
        self.assertEqual(claim["value"], "9.8")
        deltas = result["transition_output"]["candidate_current_approved_delta"]
        self.assertEqual(
            {item["object_id"] for item in deltas["candidate"]},
            {"CL-028", "MN-FIRM-EBITDA"},
        )
        self.assertEqual(deltas["current"], [])
        self.assertEqual(deltas["approved"], [])

    def test_tce013_batch_permutation_has_same_semantics_and_replay_hash(self):
        graph = synthetic_graph(
            [
                {"claim_id": "C-A", "value": "1", "unit": None, "period": "P", "perimeter": "X"},
                {"claim_id": "C-B", "value": "3", "unit": None, "period": "P", "perimeter": "X"},
            ]
        )
        events = normative_case("TCE-013-BATCH-PERMUTATION-INVARIANCE")["event_batch"]
        first = run(graph, events)
        second = run(graph, list(reversed(events)))

        first_output = first["transition_output"]
        second_output = second["transition_output"]
        self.assertEqual(first_output, second_output)
        self.assertEqual(first["candidate_state"], second["candidate_state"])
        self.assertEqual(first_output["replay_hash"], second_output["replay_hash"])

    def test_tce014_conflicting_batch_selects_no_winner(self):
        graph = synthetic_graph(
            [{"claim_id": "C-X", "value": "1", "unit": None, "period": "P", "perimeter": "X"}]
        )
        events = normative_case("TCE-014-BATCH-CONFLICT-NO-WINNER")["event_batch"]
        result = run(graph, events)
        output = result["transition_output"]
        claim = result["candidate_state"]["current_graph"]["claims"][0]

        self.assertEqual(claim["value"], "1")
        self.assertEqual(output["candidate_current_approved_delta"]["candidate"], [])
        self.assertIn("BATCH_VALUE_CONFLICT", {item["reason_code"] for item in output["human_stops"]})
        self.assertEqual(output["blocked_components"][0]["reason_code"], "BATCH_VALUE_CONFLICT")

    def test_tce015_late_fact_preserves_bitemporal_fields_and_appends_history(self):
        graph = synthetic_graph(
            [{"claim_id": "C-LATE", "value": None, "unit": None, "period": "2026-03-31", "perimeter": "X"}]
        )
        event = normative_case("TCE-015-KNOWN-AT-NO-RETROACTIVE-REWRITE")["event_batch"][0]
        result = run(graph, [event])
        record = result["history_append"][0]

        self.assertEqual(record["known_at"], "2026-08-14T10:00:00Z")
        self.assertEqual(record["effective_dates"], ["2026-03-31"])
        self.assertEqual(result["candidate_state"]["history"], [])
        self.assertEqual(result["candidate_state"]["pending_history_append"], [record])

    def test_idempotent_replay_creates_no_new_candidate_delta(self):
        replay_case = normative_case("TCE-016-IDEMPOTENT-REPLAY")
        source_case = normative_case(replay_case["event_batch_ref"])
        graph = synthetic_graph([])
        graph["model_nodes"] = [
            {
                "model_node_id": "M-DERIVED",
                "name": "Derived output",
                "kind": "derived",
                "period": "FY2026",
                "perimeter": "TEST",
                "value": "100.00",
                "unit": "$mm",
            }
        ]
        event_batch = source_case["event_batch"]
        first = run(graph, event_batch)
        adopted = copy.deepcopy(first["candidate_state"])
        adopted["state_id"] = "STATE-AFTER-TCE-001"
        adopted["history"].extend(first["history_append"])
        adopted.pop("pending_history_append", None)
        adopted.pop("runtime_flags", None)
        adopted.pop("candidate_graph_hash", None)

        second = run(adopted, event_batch)
        output = second["transition_output"]
        self.assertEqual(output["candidate_current_approved_delta"]["candidate"], [])
        self.assertIn(
            "EQUIVALENT_EVENT",
            {item["reason_code"] for item in output["unchanged_objects"]},
        )
        self.assertEqual(second["history_append"], [])

    def test_non_applicable_definition_does_not_seed_propagation(self):
        graph = synthetic_graph(
            [
                {
                    "claim_id": "C-COV-EBITDA",
                    "value": "12.2",
                    "unit": "$mm",
                    "definition_id": "DEF-EBITDA-COV",
                    "period": "LTM-2026-06-30",
                    "perimeter": "Credit agreement borrower group",
                }
            ]
        )
        event = normative_case("TCE-006-NON-APPLICABLE-CONTRADICTION")["event_batch"]
        result = run(graph, event)
        output = result["transition_output"]
        self.assertEqual(output["affected_set"], [])
        self.assertEqual(output["candidate_current_approved_delta"]["candidate"], [])
        self.assertIn(
            "NON_APPLICABLE_DEFINITION",
            {item["reason_code"] for item in output["unchanged_objects"]},
        )

    def test_affected_set_terminates_on_cycle(self):
        graph = synthetic_graph(
            [],
            positions=[
                {"position_id": "P-A"},
                {"position_id": "P-B"},
            ],
        )
        graph["position_dependencies"] = [
            {"edge_id": "E-AB", "from_position_id": "P-A", "to_position_id": "P-B", "relation_type": "SUPPORTS"},
            {"edge_id": "E-BA", "from_position_id": "P-B", "to_position_id": "P-A", "relation_type": "SUPPORTS"},
        ]
        impact = compute_affected_set(graph, ["P-A"], {})
        self.assertEqual(impact["visited_ids"], ["P-A", "P-B"])

    def test_transition_output_contains_all_schema_required_fields(self):
        graph = synthetic_graph(
            [{"claim_id": "C-X", "value": "1", "unit": None, "period": "P", "perimeter": "X"}]
        )
        event = {
            "event_id": "EV-SCHEMA",
            "event": "Correct X",
            "effective_date": "2026-01-01",
            "known_at": "2026-01-02T00:00:00Z",
            "source_ids": ["S-X"],
            "trigger_claim_ids": ["C-X"],
            "mutations": [
                {
                    "operation": "CORRECT",
                    "object_type": "CLAIM",
                    "object_id": "C-X",
                    "field": "value",
                    "from": "1",
                    "to": "2",
                }
            ],
        }
        output = run(graph, [event])["transition_output"]
        schema = load_json("schemas/state_transition_engine_output.schema.json")
        self.assertTrue(set(schema["required"]) <= set(output))
        self.assertRegex(output["replay_hash"], re.compile(r"^sha256:[0-9a-f]{64}$"))
        self.assertRegex(output["semantic_result_hash"], re.compile(r"^sha256:[0-9a-f]{64}$"))


if __name__ == "__main__":
    unittest.main()
