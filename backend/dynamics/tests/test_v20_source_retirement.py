import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20SourceRetirementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_vault = router.VAULT
        router.VAULT = Path(self.temporary.name) / "vault"
        self.claims = [
            {"claim_id": "CL-001", "source_id": "SRC-QOE", "source_doc": "QoE report"},
            {"claim_id": "CL-002", "source_id": "SRC-CIM", "source_doc": "CIM"},
        ]
        self.claim_patch = patch.object(router, "_load_claims", return_value=self.claims)
        self.claim_patch.start()

    def tearDown(self):
        self.claim_patch.stop()
        router.VAULT = self.previous_vault
        self.temporary.cleanup()

    def test_retirement_is_append_only_visible_and_idempotent(self):
        response = router.retire_source("keystone", "SRC-QOE", {"actor_id": "reviewer-001"})

        self.assertEqual(response["status"], "RETIRED")
        self.assertFalse(response["idempotent_replay"])
        projected = {item["source_id"]: item for item in router.sources("keystone")["sources"]}
        self.assertEqual(projected["SRC-QOE"]["status"], "RETIRED")
        self.assertEqual(projected["SRC-CIM"]["status"], "ACTIVE")
        event_files = list((router.VAULT / "deals" / "keystone" / "events").glob("*.md"))
        self.assertEqual(len(event_files), 1)

        replay = router.retire_source("keystone", "SRC-QOE", {"actor_id": "other-actor"})
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(len(list(event_files[0].parent.glob("*.md"))), 1)
        self.assertEqual(len(self.claims), 2, "Retirement must not delete historical claims")

    def test_unknown_source_is_rejected_without_writing(self):
        with self.assertRaises(HTTPException) as raised:
            router.retire_source("keystone", "SRC-MISSING")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertFalse((router.VAULT / "deals" / "keystone" / "events").exists())


if __name__ == "__main__":
    unittest.main()
