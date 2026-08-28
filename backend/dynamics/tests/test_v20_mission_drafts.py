import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20MissionDraftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_vault = router.VAULT
        router.VAULT = Path(self.temporary.name) / "vault"
        self.projection = {
            "deal": {
                "agent_missions": [
                    {
                        "mission_id": "MISSION-001",
                        "label": "Contract evidence review",
                        "mission_type": "DOCUMENT_RESEARCH",
                        "objective": "Resolve the contract-duration gap.",
                        "question_ids": ["Q-REVENUE"],
                        "unknown_ids": ["UNK-CONTRACTS"],
                        "allowed_sources": ["admitted-contracts"],
                        "prohibited_sources": ["personal-email"],
                        "confidential_context_policy": "CASE_ONLY",
                        "data_egress_policy": "NO_EGRESS",
                        "expected_output": "Review-required source proposal",
                        "stop_condition": "Stop on contradictory governing law.",
                        "authority_class": "PROFESSIONAL_REVIEW",
                        "reviewer_id": "reviewer-001",
                        "auto_executable_in_mock": True,
                        "external_human_contact": False,
                    }
                ]
            }
        }
        self.projection_patch = patch.object(
            router,
            "_build_projection",
            side_effect=lambda case_id: copy.deepcopy(self.projection),
        )
        self.projection_patch.start()

    def tearDown(self):
        self.projection_patch.stop()
        router.VAULT = self.previous_vault
        self.temporary.cleanup()

    def test_preparation_persists_full_governance_envelope_without_effects(self):
        response = router.prepare_mission(
            "keystone",
            "MISSION-001",
            {"actor_id": "associate-001", "idempotency_key": "MISSION-PREP-001"},
        )

        draft = response["mission_run"]
        self.assertEqual(draft["status"], "PREPARED")
        self.assertEqual(draft["allowed_sources"], ["admitted-contracts"])
        self.assertEqual(draft["data_egress_policy"], "NO_EGRESS")
        self.assertEqual(draft["stop_condition"], "Stop on contradictory governing law.")
        self.assertFalse(draft["synthetic"])
        self.assertTrue(draft["no_external_effects"])
        persisted = router.list_mission_drafts("keystone", "MISSION-001")["mission_runs"]
        self.assertEqual(len(persisted), 1)

        replay = router.prepare_mission(
            "keystone",
            "MISSION-001",
            {"actor_id": "other", "idempotency_key": "MISSION-PREP-001"},
        )
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["mission_run"]["prepared_by"], "associate-001")
        self.assertEqual(len(router.list_mission_drafts("keystone", "MISSION-001")["mission_runs"]), 1)

    def test_unknown_mission_writes_nothing(self):
        with self.assertRaises(HTTPException) as raised:
            router.prepare_mission("keystone", "MISSION-404", {})

        self.assertEqual(raised.exception.status_code, 404)
        self.assertFalse((router.VAULT / "deals" / "keystone" / "mission_runs").exists())


if __name__ == "__main__":
    unittest.main()
