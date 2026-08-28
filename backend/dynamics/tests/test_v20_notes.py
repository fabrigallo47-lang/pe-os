import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20NotesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_vault = router.VAULT
        router.VAULT = Path(self.temporary.name) / "vault"

    def tearDown(self):
        router.VAULT = self.previous_vault
        self.temporary.cleanup()

    def test_note_is_persisted_and_read_without_process_memory(self):
        response = asyncio.run(
            router.add_note(
                "keystone",
                {
                    "object_id": "CL-EBITDA",
                    "kind": "ANNOTATION",
                    "text": "Reconcile against the signed QoE.",
                    "actor_id": "analyst-001",
                    "known_at": "2026-08-28T18:00:00Z",
                    "idempotency_key": "NOTE-REQUEST-001",
                },
            )
        )

        self.assertEqual(response["status"], "PERSISTED")
        self.assertFalse(response["idempotent_replay"])
        self.assertEqual(response["note"]["server_ack_at"], response["note"]["written_at"])
        notes = router.list_notes("keystone")["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "Reconcile against the signed QoE.")
        self.assertEqual(notes[0]["object_id"], "CL-EBITDA")

    def test_idempotency_replays_original_note_without_overwrite(self):
        first = {
            "text": "Original professional review.",
            "actor_id": "reviewer-001",
            "idempotency_key": "REVIEW-001",
        }
        asyncio.run(router.add_note("keystone", first))
        replay = asyncio.run(
            router.add_note(
                "keystone",
                {**first, "text": "This must not replace the original review."},
            )
        )

        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["note"]["text"], first["text"])
        self.assertEqual(len(router.list_notes("keystone")["notes"]), 1)

    def test_note_requires_text_and_safe_case_id(self):
        with self.assertRaises(HTTPException) as missing_text:
            asyncio.run(router.add_note("keystone", {"text": "  "}))
        self.assertEqual(missing_text.exception.status_code, 400)

        with self.assertRaises(HTTPException) as unsafe_case:
            asyncio.run(router.add_note("../outside", {"text": "No traversal"}))
        self.assertEqual(unsafe_case.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
