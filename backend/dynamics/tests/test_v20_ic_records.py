import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20ICRecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_vault = router.VAULT
        router.VAULT = Path(self.temporary.name) / "vault"

    def tearDown(self):
        router.VAULT = self.previous_vault
        self.temporary.cleanup()

    def test_ic_record_is_append_only_and_does_not_mutate_approved(self):
        payload = {
            "decision": "APPROVE_WITH_CONDITIONS",
            "conditions": "Executed credit agreement before close.",
            "dissent": "One member dissented on price.",
            "authority": "IC quorum 4/5",
            "actor_id": "ic-secretary-001",
            "as_of_state_id": "STATE-CURRENT",
            "idempotency_key": "IC-SESSION-001",
        }
        response = router.record_ic("keystone", payload)

        record = response["record"]
        self.assertEqual(response["status"], "ACKNOWLEDGED")
        self.assertEqual(record["institutional_effect"], "RECORD_ONLY")
        self.assertFalse(record["approved_state_mutation"])
        self.assertEqual(record["conditions"], payload["conditions"])
        persisted = router.list_ic_records("keystone")["records"]
        self.assertEqual(len(persisted), 1)
        self.assertIn("## Dissent", persisted[0]["text"])

        replay = router.record_ic("keystone", {**payload, "decision": "REJECT"})
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["record"]["commitment"], "APPROVE_WITH_CONDITIONS")
        self.assertEqual(len(router.list_ic_records("keystone")["records"]), 1)

    def test_invalid_decision_or_missing_authority_writes_nothing(self):
        with self.assertRaises(HTTPException) as invalid:
            router.record_ic("keystone", {"decision": "MAYBE", "authority": "IC"})
        self.assertEqual(invalid.exception.status_code, 400)

        with self.assertRaises(HTTPException) as missing:
            router.record_ic("keystone", {"decision": "APPROVE", "authority": ""})
        self.assertEqual(missing.exception.status_code, 400)
        self.assertFalse((router.VAULT / "deals" / "keystone" / "decisions").exists())


if __name__ == "__main__":
    unittest.main()
