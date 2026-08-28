import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20WorkDraftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_vault = router.VAULT
        router.VAULT = Path(self.temporary.name) / "vault"

    def tearDown(self):
        router.VAULT = self.previous_vault
        self.temporary.cleanup()

    def test_draft_is_persisted_with_no_external_effects(self):
        response = router.prepare_work(
            "keystone",
            "WORK-QOE",
            {
                "owner": "associate-001",
                "object_id": "CL-EBITDA",
                "actor_id": "associate-001",
                "idempotency_key": "PREPARE-WORK-QOE-001",
            },
        )

        draft = response["draft"]
        self.assertEqual(draft["status"], "DRAFT")
        self.assertFalse(draft["synthetic"])
        self.assertTrue(draft["no_external_effects"])
        self.assertFalse(response["idempotent_replay"])
        persisted = router.list_work_drafts("keystone", "WORK-QOE")["drafts"]
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["draft_id"], draft["draft_id"])

    def test_idempotency_returns_original_draft(self):
        payload = {"actor_id": "associate-001", "idempotency_key": "WORK-REQUEST-001"}
        first = router.prepare_work("keystone", "WORK-001", payload)
        replay = router.prepare_work("keystone", "WORK-001", {**payload, "owner": "changed"})

        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["draft"]["draft_id"], first["draft"]["draft_id"])
        self.assertIsNone(replay["draft"].get("owner"))
        self.assertEqual(len(router.list_work_drafts("keystone", "WORK-001")["drafts"]), 1)

    def test_without_idempotency_each_preparation_is_append_only(self):
        router.prepare_work("keystone", "WORK-002", {"actor_id": "associate-001"})
        router.prepare_work("keystone", "WORK-002", {"actor_id": "associate-001"})

        self.assertEqual(len(router.list_work_drafts("keystone", "WORK-002")["drafts"]), 2)


if __name__ == "__main__":
    unittest.main()
