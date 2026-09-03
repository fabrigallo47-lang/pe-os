"""PAN-69 — governed CONDITIONS production and prerequisite semantics."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(DYNAMICS_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from runtime import apply_state_transition, compute_affected_set  # noqa: E402
from runtime.panta_transition_engine import (  # noqa: E402
    _unsatisfied_condition_edges,
)


QUESTION_ID = "Q-COVERAGE-1"
CONDITION_ID = f"condition:coverage-{QUESTION_ID}"


def _semantic_gap_graph() -> dict:
    return {
        "nodes": [
            {
                "id": CONDITION_ID,
                "type": "condition",
                "label": f"Evidence required for {QUESTION_ID}",
                "coverage_status": "missing",
                "question_id": QUESTION_ID,
                "condition_kind": "EVIDENCE_COVERAGE",
            }
        ],
        "edges": [],
    }


def _position(position_id: str, *, question_id: str | None = None, usable=None) -> dict:
    item = {
        "position_id": position_id,
        "statement": position_id,
        "epistemic_status_at_ic": "OPEN",
        "decision_status_at_ic": "PENDING",
        "freshness_status_at_ic": "CURRENT",
        "outcome_status_at_ic": "NOT_TESTED",
        "model_binding_status": "UNMAPPED",
    }
    if question_id:
        item["question_id"] = question_id
    if usable is not None:
        item["usable"] = usable
    return item


def _runtime_graph(*, condition_usable: bool = False) -> dict:
    condition = _position(CONDITION_ID, usable=condition_usable)
    condition["position_kind"] = "COVERAGE_CONDITION"
    return {
        "schema_version": "1.1.0",
        "case_id": "PAN-69",
        "canonical_as_of": "2026-09-01",
        "claims": [],
        "case_positions": [
            condition,
            _position("P-TARGET", question_id=QUESTION_ID),
            _position("P-DOWNSTREAM"),
        ],
        "stated_positions": [],
        "model_nodes": [],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [
            {
                "edge_id": "PDE-CONDITION",
                "from_position_id": CONDITION_ID,
                "to_position_id": "P-TARGET",
                "relation_type": "CONDITIONS",
                "semantic_role": "evidence_coverage_prerequisite",
                "traversal_rule": "prerequisite_to_dependent",
            },
            {
                "edge_id": "PDE-DOWNSTREAM",
                "from_position_id": "P-TARGET",
                "to_position_id": "P-DOWNSTREAM",
                "relation_type": "DRIVES",
                "semantic_role": "downstream_dependency",
                "traversal_rule": "source_to_target",
            },
        ],
        "position_model_bindings": [],
        "coverage_gaps": [],
        "decision_snapshot": {},
    }


def _mapping() -> dict:
    return {
        "mapping_version": "PAN69-TEST",
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


def _policy(filename: str) -> dict:
    return json.loads((DYNAMICS_ROOT / "benchmark" / filename).read_text(encoding="utf-8"))


class Pan69ConditionProducerTests(unittest.TestCase):
    def test_semantic_gap_no_longer_emits_requires_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            router, "_pipeline_out_for_case", return_value=Path(tmpdir)
        ), patch.object(
            router,
            "_load_questions",
            return_value=[{"id": QUESTION_ID, "title": "Missing evidence"}],
        ):
            graph = router._semantic_graph_from_claims([], "PAN-69")

        self.assertIn(CONDITION_ID, {node.get("id") for node in graph["nodes"]})
        self.assertNotIn(
            "REQUIRES_EVIDENCE",
            {edge.get("rel") for edge in graph["edges"]},
        )

    def test_room_projection_materializes_governed_condition_edge(self):
        current = _runtime_graph()
        current["position_dependencies"] = []
        current["case_positions"] = [_position("P-TARGET", question_id=QUESTION_ID)]
        questions = [{"id": QUESTION_ID, "label": "Coverage", "coverage": "gap"}]

        foundations, _unknowns, positions = router._semantic_rooms(
            _semantic_gap_graph(), questions, current
        )

        condition_position = next(
            item for item in current["case_positions"]
            if item["position_id"] == CONDITION_ID
        )
        self.assertFalse(condition_position["usable"])
        edge = current["position_dependencies"][0]
        self.assertEqual(edge["relation_type"], "CONDITIONS")
        self.assertEqual(edge["from_position_id"], CONDITION_ID)
        self.assertEqual(edge["to_position_id"], "P-TARGET")
        self.assertEqual(
            edge["relation_rule"]["rule_id"],
            "DECLARED_POSITION_CONDITION",
        )
        self.assertEqual(edge["relation_rule"]["rule_version"], "pan69-1.0")
        self.assertEqual(current["relation_audit"]["deterministic_edge_pct"], 100.0)
        self.assertEqual(
            next(item for item in foundations if item["id"] == CONDITION_ID)[
                "dependent_position_ids"
            ],
            ["P-TARGET"],
        )
        self.assertNotIn(CONDITION_ID, {item["position_id"] for item in positions})

        router._semantic_rooms(_semantic_gap_graph(), questions, current)
        self.assertEqual(
            len([
                edge for edge in current["position_dependencies"]
                if edge.get("relation_type") == "CONDITIONS"
            ]),
            1,
        )

    def test_unbound_condition_is_declared_instead_of_guessing_target(self):
        current = _runtime_graph()
        current["case_positions"] = []
        current["position_dependencies"] = []
        summary = router._materialize_coverage_condition_dependencies(
            _semantic_gap_graph(), current
        )

        self.assertEqual(summary["unbound_count"], 1)
        self.assertEqual(current["position_dependencies"], [])
        self.assertEqual(
            current["coverage_gaps"][0]["reason_code"],
            "CONDITION_TARGET_UNMAPPED",
        )

    def test_attributed_question_link_is_an_explicit_target_binding(self):
        current = _runtime_graph()
        current["case_positions"] = [_position("P-TARGET")]
        current["stated_positions"] = [
            {
                "stated_position_id": "STATED-1",
                "question_ids": [QUESTION_ID],
            }
        ]
        current["position_dependencies"] = [
            {
                "edge_id": "PDE-STATED",
                "from_position_id": "STATED-1",
                "to_position_id": "P-TARGET",
                "relation_type": "SUPPORTS",
            }
        ]

        summary = router._materialize_coverage_condition_dependencies(
            _semantic_gap_graph(), current
        )

        self.assertEqual(summary["targets_by_condition"][CONDITION_ID], ["P-TARGET"])
        self.assertTrue(any(
            edge.get("relation_type") == "CONDITIONS"
            and edge.get("to_position_id") == "P-TARGET"
            for edge in current["position_dependencies"]
        ))


class Pan69ConditionRuntimeTests(unittest.TestCase):
    def test_bfs_runs_prerequisite_to_dependent_not_backwards(self):
        graph = _runtime_graph()
        forward = compute_affected_set(graph, [CONDITION_ID], _mapping())
        reverse = compute_affected_set(graph, ["P-TARGET"], _mapping())

        self.assertEqual(
            forward["visited_ids"],
            sorted([CONDITION_ID, "P-TARGET", "P-DOWNSTREAM"]),
        )
        self.assertEqual(reverse["visited_ids"], ["P-DOWNSTREAM", "P-TARGET"])
        self.assertNotIn(CONDITION_ID, reverse["visited_ids"])

    def test_only_unsatisfied_prerequisite_blocks(self):
        blocked = _unsatisfied_condition_edges(_runtime_graph(), {})
        satisfied = _unsatisfied_condition_edges(
            _runtime_graph(condition_usable=True), {}
        )

        self.assertEqual(blocked[0]["condition_state"], "FALSE")
        self.assertEqual(blocked[0]["target_id"], "P-TARGET")
        self.assertEqual(satisfied, [])

    def test_transition_exposes_condition_stop_and_downstream_scope(self):
        graph = _runtime_graph()
        event = {
            "event_id": "EVENT-PAN69",
            "event": "Refresh dependent reading",
            "effective_date": "2026-09-02",
            "known_at": "2026-09-02T08:00:00Z",
            "source_ids": ["SOURCE-PAN69"],
            "trigger_claim_ids": [],
            "mutations": [
                {
                    "operation": "CORRECT",
                    "object_type": "POSITION",
                    "object_id": "P-TARGET",
                    "field": "statement",
                    "from": "P-TARGET",
                    "to": "P-TARGET refreshed",
                }
            ],
        }
        result = apply_state_transition(
            graph,
            [event],
            _mapping(),
            _policy("keystone_materiality_policy_v0.json"),
            _policy("keystone_authority_matrix_v0.json"),
        )
        output = result["transition_output"]

        condition_block = next(
            item for item in output["blocked_components"]
            if item["reason_code"] == "UNSATISFIED_CONDITION"
        )
        self.assertEqual(
            condition_block["dependent_ids"],
            ["P-DOWNSTREAM", "P-TARGET"],
        )
        stop = next(
            item for item in output["human_stops"]
            if item["reason_code"] == "UNSATISFIED_CONDITION"
        )
        self.assertEqual(stop["object_or_component_id"], CONDITION_ID)
        self.assertEqual(stop["downstream_scope"], condition_block["dependent_ids"])


if __name__ == "__main__":
    unittest.main()
