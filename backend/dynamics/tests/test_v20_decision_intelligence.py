import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20DecisionIntelligenceTests(unittest.TestCase):
    def test_rankings_are_lexicographic_and_explain_their_basis(self):
        projection = {
            "deal": {
                "current_graph": {
                    "case_positions": [
                        {
                            "position_id": "CP-GATE",
                            "statement": "A contested gate assumption",
                            "decision_status_at_ic": "ACCEPTED_WITH_CONDITIONS",
                            "epistemic_status_at_ic": "CONTESTED",
                        },
                        {
                            "position_id": "CP-MODEL",
                            "statement": "A settled model assumption",
                            "decision_status_at_ic": "ACCEPTED",
                            "epistemic_status_at_ic": "ESTABLISHED",
                            "model_node_ids": ["MN-1", "MN-2"],
                        },
                    ],
                    "position_model_bindings": [
                        {
                            "position_id": "CP-GATE",
                            "model_node_id": "MN-GATE",
                            "status": "ACTIVE",
                        }
                    ],
                    "position_dependencies": [
                        {
                            "source_position_id": "CP-GATE",
                            "target_position_id": "CP-DOWNSTREAM",
                        }
                    ],
                },
                "question_spine": [
                    {
                        "id": "Q-PARTIAL",
                        "label": "Critical but partially covered",
                        "critical": True,
                        "coverage": "partial",
                        "claim_count": 1,
                        "status": "open",
                    },
                    {
                        "id": "Q-GAP",
                        "label": "Critical uncovered question",
                        "critical": True,
                        "coverage": "gap",
                        "claim_count": 0,
                        "status": "open",
                        "owner": "Associate",
                        "work_plan": [
                            {"label": "Obtain the missing schedule", "owner": "Analyst"}
                        ],
                    },
                    {
                        "id": "Q-NONCRITICAL",
                        "label": "Non-critical gap",
                        "critical": False,
                        "coverage": "gap",
                        "claim_count": 0,
                        "status": "open",
                    },
                ],
                "rooms": {},
            }
        }

        ranked = router._apply_decision_intelligence(projection)["deal"]

        assumptions = ranked["load_bearing_assumptions"]
        self.assertEqual([item["position_id"] for item in assumptions], ["CP-GATE", "CP-MODEL"])
        self.assertEqual(assumptions[0]["rank"], 1)
        self.assertEqual(assumptions[0]["active_model_node_ids"], ["MN-GATE"])
        self.assertEqual(assumptions[0]["dependent_position_ids"], ["CP-DOWNSTREAM"])
        self.assertIn("gate_relevant=true", assumptions[0]["explanation"])

        unknowns = ranked["rooms"]["unknowns"]["items"]
        self.assertEqual(
            [item["question_id"] for item in unknowns],
            ["Q-GAP", "Q-PARTIAL", "Q-NONCRITICAL", None],
        )
        # CP-GATE is CONTESTED in the fixture: a real conflict between
        # admitted claims, not a coverage gap, so it must surface too - but
        # after the ranked question-spine gaps, not mixed into their order.
        conflict = unknowns[-1]
        self.assertEqual(conflict["id"], "conflict:CP-GATE")
        self.assertEqual(conflict["status"], "CONTESTED")
        self.assertEqual(ranked["next_best_work"]["question_id"], "Q-GAP")
        self.assertEqual(ranked["next_best_work"]["label"], "Obtain the missing schedule")
        self.assertEqual(ranked["next_best_work"]["owner"], "Analyst")
        self.assertIn("critical=true", ranked["next_best_work"]["reason"])

    def test_no_open_gap_produces_an_explicit_empty_ranking(self):
        projection = {
            "deal": {
                "current_graph": {},
                "question_spine": [
                    {
                        "id": "Q-COVERED",
                        "coverage": "full",
                        "claim_count": 3,
                        "status": "open",
                    }
                ],
                "rooms": {},
            }
        }

        deal = router._apply_decision_intelligence(projection)["deal"]

        self.assertEqual(deal["load_bearing_assumptions"], [])
        self.assertEqual(deal["rooms"]["unknowns"]["items"], [])
        self.assertEqual(deal["next_best_work"]["label"], "No unresolved evidence gap")


if __name__ == "__main__":
    unittest.main()
