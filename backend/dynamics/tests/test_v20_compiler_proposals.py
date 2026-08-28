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


class V20CompilerProposalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_vault = router.VAULT
        router.VAULT = Path(self.temporary.name) / "vault"
        self.projection = {
            "deal": {
                "case_id": "keystone",
                "as_of_date": "2026-08-28",
                "as_of_state_id": "STATE-CURRENT",
                "discrepancy_candidates": [{"discrepancy_id": "DISC-001", "label": "EBITDA conflict"}],
                "derivations": [{"derivation_id": "DER-001", "label": "Debt capacity"}],
                "hypotheses": [{"hypothesis_id": "HYP-001", "label": "Possible churn cause"}],
                "spine_change_proposals": [{"proposal_id": "SPINE-001", "label": "Split EBITDA question"}],
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

    def test_listing_returns_all_four_proposal_collections(self):
        response = router.compiler_proposals("keystone")

        self.assertEqual(response["discrepancies"][0]["discrepancy_id"], "DISC-001")
        self.assertEqual(response["derivations"][0]["derivation_id"], "DER-001")
        self.assertEqual(response["hypotheses"][0]["hypothesis_id"], "HYP-001")
        self.assertEqual(response["spine_changes"][0]["proposal_id"], "SPINE-001")

    def test_review_is_append_only_and_overlaid_without_current_mutation(self):
        response = router.review_compiler_proposal(
            "keystone",
            "discrepancy",
            "DISC-001",
            {
                "decision": "ACCEPTED",
                "rationale": "Definitions and perimeter now match.",
                "actor_id": "reviewer-001",
                "idempotency_key": "DISC-REVIEW-001",
            },
        )

        review = response["review"]
        self.assertEqual(review["institutional_effect"], "REVIEW_RECORDED_ONLY")
        self.assertFalse(review["current_mutation"])
        self.assertFalse(response["idempotent_replay"])
        listed = router.compiler_proposals("keystone")["discrepancies"][0]
        self.assertEqual(listed["review_status"], "ACCEPTED")
        self.assertEqual(listed["latest_review"]["review_id"], review["review_id"])
        files = list((router.VAULT / "deals" / "keystone" / "compiler_reviews").glob("*.md"))
        self.assertEqual(len(files), 1)

        replay = router.review_compiler_proposal(
            "keystone",
            "discrepancy",
            "DISC-001",
            {
                "decision": "REJECTED",
                "idempotency_key": "DISC-REVIEW-001",
            },
        )
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["review"]["decision"], "ACCEPTED")
        self.assertEqual(len(files), 1)

    def test_invalid_or_unknown_proposal_is_rejected_without_record(self):
        with self.assertRaises(HTTPException) as bad_kind:
            router.review_compiler_proposal("keystone", "claim", "DISC-001", {"decision": "ACCEPTED"})
        self.assertEqual(bad_kind.exception.status_code, 400)

        with self.assertRaises(HTTPException) as bad_decision:
            router.review_compiler_proposal("keystone", "discrepancy", "DISC-001", {"decision": "MAYBE"})
        self.assertEqual(bad_decision.exception.status_code, 400)

        with self.assertRaises(HTTPException) as missing:
            router.review_compiler_proposal("keystone", "discrepancy", "DISC-404", {"decision": "REJECTED"})
        self.assertEqual(missing.exception.status_code, 404)
        self.assertFalse((router.VAULT / "deals" / "keystone" / "compiler_reviews").exists())


if __name__ == "__main__":
    unittest.main()
