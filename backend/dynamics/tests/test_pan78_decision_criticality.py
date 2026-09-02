import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.decision_criticality import (  # noqa: E402
    next_position_work,
    rank_decision_criticality,
)


class Pan78DecisionCriticalityTests(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "case_positions": [
                {
                    "position_id": "CP-FRAGILE",
                    "metric": "Fragile input",
                    "decision_status_at_ic": "ACCEPTED_WITH_CONDITIONS",
                    "epistemic_status_at_ic": "CONTESTED",
                    "model_node_ids": ["MN-A"],
                    "support_routes": [
                        {"route_id": "R-1", "source": "Seller CIM"},
                        {"route_id": "R-2", "source": "Seller CIM"},
                    ],
                },
                {
                    "position_id": "CP-CORROBORATED",
                    "metric": "Corroborated input",
                    "decision_status_at_ic": "ACCEPTED",
                    "epistemic_status_at_ic": "ESTABLISHED",
                    "model_node_ids": ["MN-B"],
                    "support_routes": [
                        {"route_id": "R-3", "source_version_id": "SV-1"},
                        {"route_id": "R-4", "source_version_id": "SV-2"},
                    ],
                },
            ],
            "claim_position_edges": [
                {
                    "edge_id": "COND-1",
                    "position_id": "CP-FRAGILE",
                    "relation_type": "CONDITIONS",
                }
            ],
        }
        self.mapping = {
            "decision_root_ids": ["MN-DECISION"],
            "directed_model_edges": [
                {"from_model_node_id": "MN-A", "to_model_node_id": "MN-MID"},
                {"from_model_node_id": "MN-MID", "to_model_node_id": "MN-DECISION"},
                {"from_model_node_id": "MN-B", "to_model_node_id": "MN-DECISION"},
            ],
            "model_controls": [
                {
                    "control_id": "CTRL-A",
                    "scope_ids": ["MN-MID"],
                    "blocks_on_fail": ["MN-DECISION"],
                },
                {"control_id": "CTRL-UNRELATED", "scope_ids": ["MN-Z"]},
            ],
        }
        self.transition = {
            "blocked_components": [
                {
                    "component_id": "BLOCK-A",
                    "status": "BLOCKED",
                    "scope_ids": ["MN-MID"],
                },
                {
                    "component_id": "BLOCK-UNRELATED",
                    "status": "BLOCKED",
                    "scope_ids": ["MN-Z"],
                },
            ]
        }

    def test_ranking_is_deterministic_decomposable_and_source_independent(self):
        first = rank_decision_criticality(self.graph, self.mapping, self.transition)
        second = rank_decision_criticality(self.graph, self.mapping, self.transition)

        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(first["policy"]["aggregation"], "NONE")
        self.assertTrue(first["policy"]["factors_exposed"])
        self.assertEqual(first["policy"]["root_selection"]["method"], "EXPLICIT_MAPPING_DECLARATION")
        self.assertEqual(
            [item["position_id"] for item in first["ranking"]],
            ["CP-FRAGILE", "CP-CORROBORATED"],
        )

        fragile = first["ranking"][0]
        self.assertEqual(
            set(fragile["factors"]),
            {
                "decision_root_reachability",
                "economic_sensitivity_from_mapping",
                "independent_support_routes",
                "marginal_constraints",
            },
        )
        self.assertTrue(fragile["factors"]["decision_root_reachability"]["reachable"])
        self.assertEqual(
            fragile["factors"]["economic_sensitivity_from_mapping"]["reachable_model_node_count"],
            3,
        )
        self.assertFalse(
            fragile["factors"]["economic_sensitivity_from_mapping"]["numeric_sensitivity_available"]
        )
        support = fragile["factors"]["independent_support_routes"]
        self.assertEqual(support["raw_route_count"], 2)
        self.assertEqual(support["independent_route_count"], 1)
        constraints = fragile["factors"]["marginal_constraints"]
        self.assertEqual(constraints["binding_or_failed_ids"], ["BLOCK-A"])
        self.assertEqual(constraints["declared_ids"], ["COND-1", "CTRL-A"])
        self.assertNotIn("CTRL-UNRELATED", constraints["declared_ids"])
        self.assertNotIn("BLOCK-UNRELATED", constraints["binding_or_failed_ids"])

        serialized = json.dumps(first).lower()
        self.assertNotIn('"score"', serialized)
        self.assertNotIn("truth", serialized)
        self.assertNotIn("optimal", serialized)

    def test_structural_root_fallback_is_declared_as_a_coverage_limit(self):
        report = rank_decision_criticality(
            {
                "case_positions": [
                    {"position_id": "CP-INPUT", "model_node_ids": ["MN-INPUT"]}
                ]
            },
            {
                "formulas": [
                    {"formula_id": "F-1", "input_ids": ["MN-INPUT"], "output_id": "MN-OUT"}
                ]
            },
        )

        roots = report["policy"]["root_selection"]
        self.assertFalse(roots["explicit"])
        self.assertEqual(roots["root_ids"], ["MN-OUT"])
        self.assertEqual(report["coverage_limits"][0]["limit_id"], "DECISION_ROOTS_NOT_EXPLICIT")
        self.assertTrue(
            report["ranking"][0]["factors"]["decision_root_reachability"]["reachable"]
        )

    def test_explicit_semantic_decision_link_is_a_zero_hop_root_link(self):
        report = rank_decision_criticality(
            {
                "case_positions": [
                    {
                        "position_id": "CP-DIRECT",
                        "decision_root_id": "DECISION-INVEST",
                    }
                ]
            },
            {"decision_root_ids": ["DECISION-INVEST"]},
        )

        reachability = report["ranking"][0]["factors"]["decision_root_reachability"]
        self.assertTrue(reachability["reachable"])
        self.assertEqual(reachability["directly_linked_root_ids"], ["DECISION-INVEST"])
        self.assertEqual(reachability["minimum_hops_to_root"], 0)

    def test_next_work_uses_the_first_actionable_root_linked_position(self):
        report = rank_decision_criticality(self.graph, self.mapping, self.transition)
        work = next_position_work(report)

        self.assertEqual(work["position_id"], "CP-FRAGILE")
        self.assertIn("BLOCK-A", work["label"])
        self.assertEqual(work["unlocks"], ["MN-DECISION"])
        self.assertEqual(work["factors"], report["ranking"][0]["factors"])


if __name__ == "__main__":
    unittest.main()
