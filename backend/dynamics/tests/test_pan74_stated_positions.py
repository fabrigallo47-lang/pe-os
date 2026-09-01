import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(DYNAMICS_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from runtime import (  # noqa: E402
    EventInputError,
    apply_state_transition,
    normalize_event_batch,
)


def load_json(relative_path):
    return json.loads((DYNAMICS_ROOT / relative_path).read_text(encoding="utf-8"))


def graph():
    return {
        "schema_version": "1.1.0",
        "case_id": "PAN74-CASE",
        "canonical_as_of": "2026-08-31",
        "claims": [],
        "case_positions": [
            {
                "position_id": "READING-1",
                "statement": "The computed reading remains separate.",
                "epistemic_status_at_ic": "OPEN",
                "decision_status_at_ic": "PENDING",
                "freshness_status_at_ic": "CURRENT",
                "outcome_status_at_ic": "NOT_TESTED",
                "model_binding_status": "UNMAPPED",
            }
        ],
        "stated_positions": [],
        "model_nodes": [],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "coverage_gaps": [],
        "decision_snapshot": {},
    }


def mapping():
    return {
        "mapping_version": "PAN74-TEST",
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


def stated_position_event(
    object_id="STATED-1",
    *,
    event_id="EVENT-STATED-1",
    statement="The partner believes the downside case is acceptable.",
    supersedes=None,
):
    mutation = {
        "operation": "ADD",
        "object_type": "STATED_POSITION",
        "object_id": object_id,
        "stated_by": "PERSON-PARTNER-1",
        "source_id": "SOURCE-IC-NOTES",
        "locator": "page 3, paragraph 2",
        "statement": statement,
        "direction": "SUPPORTIVE",
        "effective_date": "2026-08-31",
        "known_at": "2026-09-01T08:00:00Z",
        "question_ids": ["BF-FIN-01"],
        "relation_type": "SUPPORTS",
        "target_position_id": "READING-1",
    }
    if supersedes is not None:
        mutation["supersedes_stated_position_id"] = supersedes
    return {
        "event_id": event_id,
        "event": "Attributed human view recorded",
        "effective_date": "2026-08-31",
        "known_at": "2026-09-01T08:00:00Z",
        "source_ids": ["SOURCE-IC-NOTES"],
        "trigger_claim_ids": [],
        "mutations": [mutation],
    }


def run(current_graph, events):
    return apply_state_transition(
        current_graph,
        events,
        mapping(),
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class Pan74StatedPositionTests(unittest.TestCase):
    def test_additive_schema_keeps_position_as_case_reading(self):
        canonical = load_json("schemas/canonical_investment_case.schema.json")
        event_schema = load_json("schemas/state_transition_event.schema.json")
        output_schema = load_json("schemas/state_transition_engine_output.schema.json")

        self.assertEqual(canonical["properties"]["schema_version"]["const"], "1.1.0")
        self.assertIn("position", canonical["$defs"])
        self.assertIn("stated_position", canonical["$defs"])
        self.assertEqual(
            set(canonical["$defs"]["stated_position"]["required"]),
            {
                "stated_position_id",
                "stated_by",
                "source_id",
                "locator",
                "statement",
                "direction",
                "effective_date",
                "known_at",
                "question_ids",
                "created_by_event_id",
                "content_hash",
            },
        )
        event_types = set(
            event_schema["$defs"]["mutation"]["properties"]["object_type"]["enum"]
        )
        self.assertTrue({"POSITION", "STATED_POSITION"} <= event_types)
        self.assertIn(
            "STATED_POSITION",
            output_schema["$defs"]["object_type"]["enum"],
        )

    def test_add_preserves_attribution_and_propagates_to_case_reading(self):
        current = graph()
        before = copy.deepcopy(current)
        result = run(current, [stated_position_event()])
        candidate = result["candidate_state"]["current_graph"]

        self.assertEqual(current, before)
        self.assertEqual(candidate["case_positions"], before["case_positions"])
        self.assertEqual(len(candidate["stated_positions"]), 1)
        recorded = candidate["stated_positions"][0]
        self.assertEqual(recorded["stated_position_id"], "STATED-1")
        self.assertEqual(recorded["stated_by"], "PERSON-PARTNER-1")
        self.assertEqual(recorded["source_id"], "SOURCE-IC-NOTES")
        self.assertEqual(recorded["locator"], "page 3, paragraph 2")
        self.assertRegex(recorded["content_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(recorded["created_by_event_id"], "EVENT-STATED-1")

        edge = candidate["position_dependencies"][0]
        self.assertEqual(edge["from_position_id"], "STATED-1")
        self.assertEqual(edge["to_position_id"], "READING-1")
        self.assertEqual(edge["relation_type"], "SUPPORTS")
        affected = {
            (item["object_type"], item["object_id"])
            for item in result["transition_output"]["affected_set"]
        }
        self.assertIn(("STATED_POSITION", "STATED-1"), affected)
        self.assertIn(("POSITION", "READING-1"), affected)
        canonical_schema = load_json("schemas/canonical_investment_case.schema.json")
        validation_errors = list(
            Draft202012Validator(
                canonical_schema,
                format_checker=FormatChecker(),
            ).iter_errors(candidate)
        )
        self.assertEqual(validation_errors, [])

    def test_changed_view_appends_successor_without_rewriting_original(self):
        first = run(graph(), [stated_position_event()])
        first_candidate = first["candidate_state"]["current_graph"]
        original = copy.deepcopy(first_candidate["stated_positions"][0])
        successor_event = stated_position_event(
            "STATED-2",
            event_id="EVENT-STATED-2",
            statement="The partner now considers the downside case unacceptable.",
            supersedes="STATED-1",
        )
        successor_event["mutations"][0]["direction"] = "ADVERSE"

        second = run(first_candidate, [successor_event])
        positions = second["candidate_state"]["current_graph"]["stated_positions"]

        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0], original)
        self.assertEqual(positions[1]["supersedes_stated_position_id"], "STATED-1")
        self.assertNotEqual(positions[0]["content_hash"], positions[1]["content_hash"])

    def test_bounded_settlement_persists_stated_position_and_relation(self):
        current = graph()
        transition = run(current, [stated_position_event()])
        candidate = transition["candidate_state"]["current_graph"]

        settled = router._bounded_settlement_graph(
            current,
            candidate,
            {"STATED-1"},
        )

        self.assertEqual(
            [item["stated_position_id"] for item in settled["stated_positions"]],
            ["STATED-1"],
        )
        self.assertEqual(
            settled["position_dependencies"][0]["from_position_id"],
            "STATED-1",
        )
        self.assertEqual(
            settled["position_dependencies"][0]["to_position_id"],
            "READING-1",
        )

    def test_existing_stated_position_cannot_be_corrected_or_retracted(self):
        for operation in ("OBSERVE", "CORRECT", "SUPERSEDE", "RETRACT"):
            with self.subTest(operation=operation):
                event = stated_position_event()
                event["mutations"][0]["operation"] = operation
                event["mutations"][0]["field"] = "statement"
                event["mutations"][0]["to"] = "Rewritten view"
                with self.assertRaisesRegex(EventInputError, "immutable"):
                    normalize_event_batch([event])

    def test_required_attribution_temporality_and_source_are_enforced(self):
        for field in (
            "stated_by",
            "source_id",
            "locator",
            "statement",
            "direction",
            "effective_date",
            "known_at",
        ):
            with self.subTest(field=field):
                event = stated_position_event()
                event["mutations"][0].pop(field)
                with self.assertRaises(EventInputError):
                    normalize_event_batch([event])

        wrong_source = stated_position_event()
        wrong_source["mutations"][0]["source_id"] = "SOURCE-NOT-IN-EVENT"
        with self.assertRaisesRegex(EventInputError, "source_id"):
            normalize_event_batch([wrong_source])

        wrong_time = stated_position_event()
        wrong_time["mutations"][0]["known_at"] = "2026-09-01T09:00:00Z"
        with self.assertRaisesRegex(EventInputError, "known_at must match"):
            normalize_event_batch([wrong_time])

    def test_unknown_superseded_position_is_not_admitted(self):
        event = stated_position_event(
            "STATED-2",
            event_id="EVENT-STATED-2",
            supersedes="STATED-MISSING",
        )
        result = run(graph(), [event])
        candidate = result["candidate_state"]["current_graph"]

        self.assertEqual(candidate["stated_positions"], [])
        reason_codes = {
            item.get("reason_code")
            for item in result["transition_output"]["human_stops"]
        }
        self.assertIn("UNKNOWN_SUPERSEDED_STATED_POSITION_ID", reason_codes)


if __name__ == "__main__":
    unittest.main()
