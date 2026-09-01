import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


def question(coverage="partial"):
    return {
        "id": "BF-FIN-01",
        "question_id": "BF-FIN-01",
        "label": "What is sustainable revenue?",
        "coverage": coverage,
    }


def semantic_graph():
    return {
        "nodes": [
            {
                "id": "claim:000",
                "type": "claim",
                "claim_id": "CLAIM-1",
                "statement": "Revenue retention is 92%.",
                "value": 92,
                "unit": "%",
                "period": "FY2025A",
                "perimeter": "Company",
                "source_id": "SOURCE-QOE",
                "locator": "page 12",
            },
            {
                "id": "q:BF-FIN-01",
                "type": "question",
                "label": "What is sustainable revenue?",
            },
        ],
        "edges": [
            {
                "source": "claim:000",
                "target": "q:BF-FIN-01",
                "rel": "BEARS_ON",
            }
        ],
    }


def reading():
    return {
        "position_id": "READING-1",
        "statement": "Current evidence supports durable recurring revenue.",
        "epistemic_status_at_ic": "SUPPORTED",
        "decision_status_at_ic": "PENDING",
        "freshness_status_at_ic": "CURRENT",
        "outcome_status_at_ic": "NOT_TESTED",
        "model_binding_status": "UNMAPPED",
        "known_at": "2026-09-01T08:00:00Z",
        "support_routes": [{"route_id": "ROUTE-1"}],
    }


def stated_position(
    object_id="STATED-1",
    *,
    statement="The partner believes revenue durability is acceptable.",
    supersedes=None,
):
    item = {
        "stated_position_id": object_id,
        "stated_by": "PERSON-PARTNER-1",
        "source_id": "SOURCE-IC-NOTES",
        "locator": "page 3, paragraph 2",
        "statement": statement,
        "direction": "SUPPORTIVE",
        "effective_date": "2026-08-31",
        "known_at": "2026-09-01T08:00:00Z",
        "question_ids": ["BF-FIN-01"],
        "created_by_event_id": f"EVENT-{object_id}",
        "content_hash": "sha256:" + "a" * 64,
    }
    if supersedes:
        item["supersedes_stated_position_id"] = supersedes
    return item


def current_graph(stated=None, dependencies=None):
    return {
        "case_id": "PAN75-CASE",
        "claims": [],
        "case_positions": [reading()],
        "stated_positions": list(stated or []),
        "model_nodes": [],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": list(dependencies or []),
        "position_model_bindings": [],
        "coverage_gaps": [],
        "decision_snapshot": {},
    }


def dependency(source="STATED-1"):
    return {
        "edge_id": f"EDGE-{source}",
        "from_position_id": source,
        "to_position_id": "READING-1",
        "relation_type": "SUPPORTS",
        "semantic_role": "ATTRIBUTED_VIEW_TO_CASE_READING",
    }


class Pan75CaseReadingTests(unittest.TestCase):
    def test_question_and_evidence_do_not_create_position_from_question_title(self):
        claim = {
            "claim_id": "CLAIM-1",
            "statement": "A source discusses a policy topic.",
            "subject": "Policy topic",
            "metric": "Policy topic",
            "value": None,
            "unit": "",
            "period": "FY2025A",
            "perimeter": "Company",
            "epistemic_class": "asserted",
            "source_id": "SOURCE-1",
            "source_ids": ["SOURCE-1"],
            "locator": "page 1",
            "bears_on": ["BF-FIN-01"],
        }
        with patch.object(
            router,
            "_load_questions",
            return_value=[{"id": "BF-FIN-01", "title": "Question title"}],
        ):
            graph = router._semantic_graph_from_claims(
                [claim],
                "PAN75-CASE",
                excel_models=[],
            )

        node_ids = {item["id"] for item in graph["nodes"]}
        self.assertNotIn("position:BF-FIN-01", node_ids)
        self.assertFalse(any(
            edge.get("rel") == "FRAMES_POSITION"
            for edge in graph["edges"]
        ))
        semantic_claim = next(
            item for item in graph["nodes"] if item.get("id") == "claim:000"
        )
        self.assertEqual(semantic_claim["claim_id"], "CLAIM-1")

    def test_day_zero_keeps_question_unformed_even_with_claim_and_runtime_reading(self):
        spine = [question()]
        foundations, unknowns, positions = router._semantic_rooms(
            semantic_graph(),
            spine,
            current_graph(),
        )

        self.assertEqual(positions, [])
        self.assertEqual(foundations, [])
        self.assertEqual(
            spine[0]["current_view"]["view"],
            "No one has expressed a view.",
        )
        self.assertEqual(spine[0]["current_view"]["state"], "UNEXAMINED")
        self.assertEqual(
            unknowns["items"][0]["value"],
            "No one has expressed a view.",
        )

    def test_admitted_stated_position_and_evidence_project_system_reading(self):
        spine = [question()]
        foundations, unknowns, positions = router._semantic_rooms(
            semantic_graph(),
            spine,
            current_graph([stated_position()], [dependency()]),
        )

        self.assertEqual(len(positions), 1)
        projected = positions[0]
        self.assertEqual(projected["reading_id"], "READING-1")
        self.assertEqual(
            projected["reading_statement"],
            "Current evidence supports durable recurring revenue.",
        )
        self.assertNotEqual(projected["reading_statement"], spine[0]["label"])
        self.assertTrue(projected["system_attributed"])
        self.assertEqual(projected["stated_position_ids"], ["STATED-1"])
        self.assertRegex(projected["derivation_hash"], r"^sha256:[0-9a-f]{64}$")
        evidence_types = {
            item["object_type"] for item in projected["evidence_options"]
        }
        self.assertEqual(evidence_types, {"CLAIM", "STATED_POSITION"})
        self.assertEqual(foundations[0]["kind"], "case_reading")
        self.assertEqual(
            foundations[0]["members"],
            ["STATED-1", "CLAIM-1"],
        )
        self.assertEqual(spine[0]["current_view"]["reading_id"], "READING-1")
        self.assertEqual(unknowns["items"], [])

    def test_superseded_view_is_not_used_in_current_reading(self):
        old = stated_position("STATED-OLD")
        new = stated_position(
            "STATED-NEW",
            statement="The partner now sees revenue durability as adverse.",
            supersedes="STATED-OLD",
        )
        graph = current_graph(
            [old, new],
            [dependency("STATED-OLD"), dependency("STATED-NEW")],
        )

        _foundations, _unknowns, positions = router._semantic_rooms(
            semantic_graph(),
            [question()],
            graph,
        )

        self.assertEqual(positions[0]["stated_position_ids"], ["STATED-NEW"])
        self.assertNotIn(
            "STATED-OLD",
            {item.get("stated_position_id") for item in positions[0]["evidence_options"]},
        )

    def test_attributed_view_without_runtime_reading_stays_open(self):
        spine = [question()]
        graph = current_graph([stated_position()], [])

        foundations, unknowns, positions = router._semantic_rooms(
            semantic_graph(),
            spine,
            graph,
        )

        self.assertEqual(foundations, [])
        self.assertEqual(positions, [])
        self.assertEqual(spine[0]["current_view"]["view"], "Reading not formed.")
        self.assertEqual(spine[0]["current_view"]["state"], "OPEN")
        self.assertIn("CaseReading not formed", unknowns["items"][0]["value"])

    def test_multi_question_view_requires_explicit_reading_question_identity(self):
        view = stated_position()
        view["question_ids"] = ["BF-FIN-01", "BF-FIN-02"]
        spine = [
            question(),
            {
                "id": "BF-FIN-02",
                "question_id": "BF-FIN-02",
                "label": "What is normalized EBITDA?",
                "coverage": "partial",
                "versions": None,
            },
        ]

        foundations, unknowns, positions = router._semantic_rooms(
            semantic_graph(),
            spine,
            current_graph([view], [dependency()]),
        )

        self.assertEqual(foundations, [])
        self.assertEqual(positions, [])
        self.assertEqual(len(unknowns["items"]), 2)
        self.assertTrue(all(
            item["current_view"]["view"] == "Reading not formed."
            for item in spine
        ))

    def test_empty_semantic_graph_still_emits_day_zero_view(self):
        spine = [question("gap")]

        foundations, unknowns, positions = router._semantic_rooms(
            {},
            spine,
            {},
        )

        self.assertEqual(foundations, [])
        self.assertEqual(positions, [])
        self.assertEqual(len(unknowns["items"]), 1)
        self.assertEqual(
            spine[0]["versions"]["current"]["view"],
            "No one has expressed a view.",
        )

    def test_decision_intelligence_keeps_unformed_view_visible_at_full_coverage(self):
        spine = [question("full")]
        foundations, unknowns, positions = router._semantic_rooms(
            semantic_graph(),
            spine,
            current_graph(),
        )
        projection = {
            "deal": {
                "current_graph": current_graph(),
                "question_spine": spine,
                "transition_output": {},
                "rooms": {
                    "foundations": {"sets": foundations},
                    "unknowns": unknowns,
                    "shadowIC": {"theses": []},
                },
                "positions": positions,
            }
        }

        result = router._apply_decision_intelligence(projection)

        projected_unknowns = result["deal"]["rooms"]["unknowns"]["items"]
        self.assertEqual(len(projected_unknowns), 1)
        self.assertEqual(
            projected_unknowns[0]["value"],
            "No one has expressed a view.",
        )
        self.assertIn("StatedPosition", projected_unknowns[0]["closure"])

    def test_input_graphs_remain_immutable(self):
        semantic = semantic_graph()
        runtime = current_graph([stated_position()], [dependency()])
        semantic_before = copy.deepcopy(semantic)
        runtime_before = copy.deepcopy(runtime)

        router._semantic_rooms(semantic, [question()], runtime)

        self.assertEqual(semantic, semantic_before)
        self.assertEqual(runtime, runtime_before)


if __name__ == "__main__":
    unittest.main()
