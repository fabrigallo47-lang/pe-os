import asyncio
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20ExecutionPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_runs_log = router.RUNS_LOG
        self.previous_runs = copy.deepcopy(router._runs)
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._runs.clear()
        self.run_id = "RUN-EXEC-001"
        router._store_run(
            self.run_id,
            {
                "run_id": self.run_id,
                "case_id": "keystone",
                "event_id": "EVENT-001",
                "candidate_state_id": "CAND-001",
                "status": "PREPARED",
                "authority_records": [],
                "transition_output": {
                    "human_stops": [{"stop_id": "STOP-001", "status": "OPEN"}],
                    "replay_hash": "sha256:candidate",
                },
            },
        )
        projection = {
            "deal": {
                "decisionRoom": {
                    "courses": [
                        {
                            "id": "COURSE-EXTERNAL",
                            "effect_type": "EXTERNAL_PACKAGE",
                            "execution": {"amount": 105.15, "currency": "USD_MM", "document_version": "v8"},
                        }
                    ]
                },
                "executionRoom": {
                    "type": "Offer delivery",
                    "recipient": "Seller adviser",
                    "sender": "Deal Partner",
                    "subject": "Revised offer",
                    "message": "Simulated package only.",
                    "attachments": ["offer-v8.pdf"],
                    "checks": ["Authority scoped", "Candidate scoped"],
                },
            }
        }
        self.projection_patch = patch.object(router, "_build_projection", return_value=projection)
        self.projection_patch.start()

    def tearDown(self):
        self.projection_patch.stop()
        router.RUNS_LOG = self.previous_runs_log
        router._runs.clear()
        router._runs.update(self.previous_runs)
        self.temporary.cleanup()

    def _attest(self):
        return asyncio.run(
            router.attest(
                self.run_id,
                {
                    "candidate_state_id": "CAND-001",
                    "human_stop_id": "STOP-001",
                    "course_id": "COURSE-EXTERNAL",
                    "actor_id": "partner-001",
                    "actor_role": "DEAL_PARTNER",
                    "artifact_hash": "sha256:candidate",
                },
            )
        )

    def test_attestation_creates_immutable_durable_package(self):
        response = self._attest()
        record = response["authority_record"]
        package = response["execution_package"]

        self.assertEqual(record["status"], "ATTESTED")
        self.assertEqual(record["effect_type"], "EXTERNAL_PACKAGE")
        self.assertEqual(package["status"], "READY")
        self.assertTrue(package["synthetic"])
        self.assertTrue(package["no_external_effects"])
        self.assertEqual(package["artifact_hash"], router._package_payload_hash(package))

        router._runs.clear()
        router._load_durable_registries()
        restored = router._runs[self.run_id]["execution_packages"][package["execution_package_id"]]
        self.assertEqual(restored["artifact_hash"], package["artifact_hash"])
        recreated = router.create_execution_package(self.run_id)
        self.assertEqual(recreated["execution_package"]["execution_package_id"], package["execution_package_id"])

    def test_simulated_failure_can_retry_and_scope_gate_requires_acceptance(self):
        response = self._attest()
        record = response["authority_record"]
        package = response["execution_package"]
        package_id = package["execution_package_id"]
        original_hash = package["artifact_hash"]

        with self.assertRaises(HTTPException):
            router._validate_execution_package_scope(
                router._runs[self.run_id], [record], [package_id]
            )

        failure = router.send_execution_package(package_id, {"simulate_failure": True})
        self.assertEqual(failure.status_code, 503)
        self.assertEqual(json.loads(failure.body)["error"]["code"], "DELIVERY_FAILED")
        accepted = router.send_execution_package(package_id, {})["execution_package"]
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertEqual(accepted["artifact_hash"], original_hash)
        self.assertTrue(accepted["no_external_effects"])
        router._validate_execution_package_scope(router._runs[self.run_id], [record], [package_id])

    def test_package_requires_prepared_run_and_matching_candidate(self):
        router._runs[self.run_id]["status"] = "CANDIDATE_READY"
        with self.assertRaises(HTTPException) as not_prepared:
            self._attest()
        self.assertEqual(not_prepared.exception.status_code, 409)

        router._runs[self.run_id]["status"] = "PREPARED"
        with self.assertRaises(HTTPException) as stale:
            asyncio.run(
                router.attest(
                    self.run_id,
                    {
                        "candidate_state_id": "CAND-STALE",
                        "human_stop_id": "STOP-001",
                        "course_id": "COURSE-EXTERNAL",
                        "artifact_hash": "sha256:candidate",
                    },
                )
            )
        self.assertEqual(stale.exception.status_code, 409)

    def test_attestation_rejects_unbound_course_hash_actor_and_self_adoption(self):
        base = {
            "candidate_state_id": "CAND-001",
            "human_stop_id": "STOP-001",
            "course_id": "COURSE-EXTERNAL",
            "actor_id": "partner-001",
            "artifact_hash": "sha256:candidate",
        }
        invalid_payloads = (
            ({**base, "course_id": "COURSE-INVENTED"}, 409),
            ({**base, "artifact_hash": "sha256:invented"}, 409),
            ({**base, "actor_id": "invented-actor"}, 403),
        )
        for payload, status_code in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(HTTPException) as rejected:
                    asyncio.run(router.attest(self.run_id, payload))
                self.assertEqual(rejected.exception.status_code, status_code)
        self.assertEqual(router._runs[self.run_id]["authority_records"], [])

        router._runs[self.run_id]["transition_output"]["human_stops"][0][
            "required_actor_distinct_from"
        ] = "partner-001"
        with self.assertRaises(HTTPException) as self_adoption:
            asyncio.run(router.attest(self.run_id, base))
        self.assertEqual(self_adoption.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
