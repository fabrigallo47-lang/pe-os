import asyncio
import base64
import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException
from jsonschema import Draft202012Validator, FormatChecker


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20ExecutionPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_runs_log = router.RUNS_LOG
        self.previous_runs = copy.deepcopy(router._runs)
        self.previous_authenticated_sessions = copy.deepcopy(
            router._authenticated_sessions
        )
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._runs.clear()
        router._authenticated_sessions.clear()
        self.run_id = "RUN-EXEC-001"
        router._store_run(
            self.run_id,
            {
                "run_id": self.run_id,
                "case_id": "keystone",
                "event_id": "EVENT-001",
                "candidate_state_id": "CAND-001",
                "status": "PREPARED",
                "prepared_selection_hash": "sha256:prepared-selection",
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
        self.session_id, _ = router._issue_authenticated_session(
            "keystone", "partner-001"
        )

    def tearDown(self):
        self.projection_patch.stop()
        router.RUNS_LOG = self.previous_runs_log
        router._runs.clear()
        router._runs.update(self.previous_runs)
        router._authenticated_sessions.clear()
        router._authenticated_sessions.update(self.previous_authenticated_sessions)
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
                session_id=self.session_id,
            )
        )

    def test_attestation_creates_immutable_durable_package(self):
        response = self._attest()
        record = response["authority_record"]
        package = response["execution_package"]

        self.assertEqual(record["status"], "ATTESTED")
        self.assertEqual(record["effect_type"], "EXTERNAL_PACKAGE")
        self.assertEqual(record["case_id"], "keystone")
        self.assertEqual(
            record["record_hash"], router._authority_record_payload_hash(record)
        )
        self.assertIn("human_stop_hash", record)
        self.assertIn("policy_refs_hash", record)
        self.assertIn("authority_resolution_hash", record)
        self.assertEqual(record["authority_record_version"], "authority-record/2.0")
        self.assertEqual(record["signature_algorithm"], "ED25519")
        self.assertEqual(record["ledger_id"], "PANTA-AUTHORITY-LEDGER-V1")
        self.assertEqual(record["ledger_sequence"], 1)
        self.assertIsNone(record["previous_record_hash"])
        self.assertEqual(
            record["authority_assignment_hash"],
            router._authority_content_hash(record["authority_assignment"]),
        )
        self.assertEqual(
            record["authentication_context_hash"],
            router._authority_content_hash(record["authentication_context"]),
        )
        self.assertEqual(
            record["authentication_context"]["principal_id"], "partner-001"
        )
        self.assertEqual(
            record["authentication_context"]["authentication_method"],
            "SERVER_ISSUED_SESSION",
        )
        self.assertNotIn(self.session_id, json.dumps(record))
        router._validate_authority_authentication_snapshot(record)
        router._verify_authority_record_signature(record)
        self.assertTrue(router._authority_ledger_path().exists())
        self.assertTrue(router._authority_signing_key_path().exists())
        self.assertEqual(
            router._authority_signing_key_path().stat().st_mode & 0o077, 0
        )
        self.assertEqual(
            router._authority_keyring_path().stat().st_mode & 0o077, 0
        )
        for relative_schema in (
            "ui/07_ENGINEERING_CONTRACTS_AND_ADAPTERS/schemas/authority_record.schema.json",
            "ui/01_PRODUCT_BUILD/app/contracts/authority_record.schema.json",
        ):
            with self.subTest(schema=relative_schema):
                schema = json.loads((PROJECT_ROOT / relative_schema).read_text())
                Draft202012Validator.check_schema(schema)
                errors = sorted(
                    Draft202012Validator(
                        schema, format_checker=FormatChecker()
                    ).iter_errors(record),
                    key=lambda error: list(error.path),
                )
                self.assertEqual(errors, [], [error.message for error in errors])
        keyring_schema = json.loads(
            (
                PROJECT_ROOT
                / "backend/dynamics/schemas/authority_keyring.schema.json"
            ).read_text()
        )
        Draft202012Validator.check_schema(keyring_schema)
        keyring_errors = sorted(
            Draft202012Validator(
                keyring_schema, format_checker=FormatChecker()
            ).iter_errors(json.loads(router._authority_keyring_path().read_text())),
            key=lambda error: list(error.path),
        )
        self.assertEqual(
            keyring_errors, [], [error.message for error in keyring_errors]
        )
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
                        "actor_id": "partner-001",
                        "artifact_hash": "sha256:candidate",
                    },
                    session_id=self.session_id,
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
            ({key: value for key, value in base.items() if key != "actor_id"}, 400),
        )
        for payload, status_code in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(HTTPException) as rejected:
                    asyncio.run(
                        router.attest(
                            self.run_id, payload, session_id=self.session_id
                        )
                    )
                self.assertEqual(rejected.exception.status_code, status_code)
        self.assertEqual(router._runs[self.run_id]["authority_records"], [])

        router._runs[self.run_id]["transition_output"]["human_stops"][0][
            "required_actor_distinct_from"
        ] = "partner-001"
        with self.assertRaises(HTTPException) as self_adoption:
            asyncio.run(
                router.attest(self.run_id, base, session_id=self.session_id)
            )
        self.assertEqual(self_adoption.exception.status_code, 409)

    def test_attestation_requires_a_matching_authenticated_session(self):
        payload = {
            "candidate_state_id": "CAND-001",
            "human_stop_id": "STOP-001",
            "course_id": "COURSE-EXTERNAL",
            "actor_id": "partner-001",
            "artifact_hash": "sha256:candidate",
        }
        expired_session, expired_principal = router._issue_authenticated_session(
            "keystone", "partner-001"
        )
        router._authenticated_sessions[
            expired_principal["session_id_hash"]
        ]["session_expires_at"] = "2000-01-01T00:00:00Z"
        attempts = (
            ({}, 401),
            ({"session_id": "SES-unknown"}, 401),
            ({"session_id": expired_session}, 401),
            (
                {
                    "session_id": self.session_id,
                    "x_panta_session": "SES-different",
                },
                401,
            ),
        )
        for session_arguments, status_code in attempts:
            with self.subTest(session_arguments=session_arguments):
                with self.assertRaises(HTTPException) as rejected:
                    asyncio.run(
                        router.attest(
                            self.run_id,
                            payload,
                            **session_arguments,
                        )
                    )
                self.assertEqual(rejected.exception.status_code, status_code)

        other_session, _ = router._issue_authenticated_session(
            "keystone", "another-authority-holder"
        )
        with self.assertRaisesRegex(HTTPException, "authenticated session principal") as mismatch:
            asyncio.run(
                router.attest(
                    self.run_id,
                    payload,
                    session_id=other_session,
                )
            )
        self.assertEqual(mismatch.exception.status_code, 403)
        self.assertEqual(router._authority_ledger_records(), [])

    def test_http_attestation_binds_the_session_header_to_the_actor(self):
        app = FastAPI()
        app.include_router(router.v20)
        payload = {
            "candidate_state_id": "CAND-001",
            "human_stop_id": "STOP-001",
            "course_id": "COURSE-EXTERNAL",
            "actor_id": "partner-001",
            "artifact_hash": "sha256:candidate",
        }

        async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://panta.test",
            ) as client:
                missing = await client.post(
                    f"/api/v20/runs/{self.run_id}/authority/attest",
                    json=payload,
                )
                bootstrap = await client.get(
                    "/api/v20/bootstrap", params={"case_id": "keystone"}
                )
                accepted = await client.post(
                    f"/api/v20/runs/{self.run_id}/authority/attest",
                    json=payload,
                    headers={
                        "X-Panta-Session": bootstrap.json()["session_id"]
                    },
                )
                return missing, bootstrap, accepted

        missing, bootstrap, accepted = asyncio.run(exercise())
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(
            accepted.json()["authority_record"]["authentication_context"][
                "principal_id"
            ],
            "partner-001",
        )

    def test_non_attestable_stop_is_enforced_by_the_server(self):
        stop = router._runs[self.run_id]["transition_output"]["human_stops"][0]
        stop.update(
            reason_code="NON_WAIVABLE_AXIOM",
            required_role="AUTHORITY_HOLDER",
            attestable=True,
        )

        with self.assertRaisesRegex(HTTPException, "cannot be authority-attested") as rejected:
            self._attest()

        self.assertEqual(rejected.exception.status_code, 409)
        normalized = router._frontend_human_stop(stop)
        self.assertFalse(normalized["attestable"])
        self.assertEqual(normalized["resolution_kind"], "NON_WAIVABLE_BLOCK")
        self.assertEqual(router._runs[self.run_id]["authority_records"], [])

    def test_tampered_authority_record_cannot_be_reused(self):
        response = self._attest()
        record = response["authority_record"]
        record["required_role"] = "PREPARER"

        with self.assertRaisesRegex(HTTPException, "scoped|hash") as package_rejected:
            router.create_execution_package(
                self.run_id,
                {"authority_record_id": record["authority_record_id"]},
            )
        self.assertEqual(package_rejected.exception.status_code, 409)

        with self.assertRaisesRegex(HTTPException, "scoped|hash") as settlement_rejected:
            router._validate_authority_record_scope(
                router._runs[self.run_id], record, for_settlement=True
            )
        self.assertEqual(settlement_rejected.exception.status_code, 409)

    def test_duplicate_authority_record_registry_fails_closed(self):
        response = self._attest()
        record = response["authority_record"]
        router._runs[self.run_id]["authority_records"].append(copy.deepcopy(record))

        with self.assertRaisesRegex(HTTPException, "duplicate IDs") as rejected:
            router.create_execution_package(
                self.run_id,
                {"authority_record_id": record["authority_record_id"]},
            )

        self.assertEqual(rejected.exception.status_code, 409)

    def test_ledger_recovers_record_missing_from_the_run_registry(self):
        record = self._attest()["authority_record"]
        router._runs[self.run_id]["authority_records"] = []
        router._store_run(self.run_id, router._runs[self.run_id])

        router._runs.clear()
        router._load_durable_registries()

        restored = router._runs[self.run_id]["authority_records"]
        self.assertEqual(restored, [record])
        router._validate_authority_record_scope(
            router._runs[self.run_id], restored[0], for_settlement=True
        )

    def test_retry_recovers_after_ledger_commit_but_run_write_failure(self):
        with patch.object(router, "_store_run", side_effect=OSError("disk fault")):
            with self.assertRaisesRegex(HTTPException, "durable in the ledger") as failed:
                self._attest()
        self.assertEqual(failed.exception.status_code, 503)
        ledger_record = router._authority_ledger_records()[0]

        router._runs.clear()
        router._load_durable_registries()
        recovered = router._runs[self.run_id]["authority_records"]
        self.assertEqual(recovered, [ledger_record])

        retried = self._attest()
        self.assertEqual(retried["authority_record"], ledger_record)
        self.assertIsNotNone(retried["execution_package"])

    def test_historical_act_does_not_depend_on_the_current_actor_directory(self):
        record = self._attest()["authority_record"]

        with patch.object(
            router,
            "_authority_actor",
            side_effect=AssertionError("historical validation must use the snapshot"),
        ):
            router._validate_authority_record_scope(
                router._runs[self.run_id], record, for_settlement=True
            )

    def test_rehashing_a_forged_record_does_not_forge_the_signature(self):
        record = copy.deepcopy(self._attest()["authority_record"])
        record["actor_role"] = "FORGED_ROLE"
        record["authority_assignment"]["actor_role"] = "FORGED_ROLE"
        record["authority_assignment_hash"] = router._authority_content_hash(
            record["authority_assignment"]
        )
        record["record_hash"] = router._authority_record_payload_hash(record)

        with self.assertRaisesRegex(HTTPException, "signature verification") as rejected:
            router._verify_authority_record_signature(record)

        self.assertEqual(rejected.exception.status_code, 409)

    def test_untrusted_signing_key_fails_closed(self):
        record = copy.deepcopy(self._attest()["authority_record"])
        attacker = router.Ed25519PrivateKey.generate()
        record["signing_key_id"] = router._authority_signing_key_id(attacker)
        record["record_hash"] = router._authority_record_payload_hash(record)
        record["record_signature"] = base64.urlsafe_b64encode(
            attacker.sign(record["record_hash"].encode("ascii"))
        ).decode("ascii").rstrip("=")

        with self.assertRaisesRegex(HTTPException, "not trusted") as rejected:
            router._verify_authority_record_signature(record)

        self.assertEqual(rejected.exception.status_code, 409)

    def test_signing_key_rotation_preserves_historical_verification(self):
        first = self._attest()["authority_record"]
        old_key_id = first["signing_key_id"]
        replacement = router.Ed25519PrivateKey.generate()
        replacement_raw = replacement.private_bytes(
            encoding=router.serialization.Encoding.Raw,
            format=router.serialization.PrivateFormat.Raw,
            encryption_algorithm=router.serialization.NoEncryption(),
        )
        configured = base64.urlsafe_b64encode(replacement_raw).decode("ascii")

        second_run_id = "RUN-ROTATED-KEY"
        second_run = copy.deepcopy(router._runs[self.run_id])
        second_run.update(
            run_id=second_run_id,
            candidate_state_id="CAND-ROTATED-KEY",
            prepared_selection_hash="sha256:prepared-rotated-key",
            authority_records=[],
            execution_packages={},
        )
        router._store_run(second_run_id, second_run)
        with patch.dict(os.environ, {"PANTA_AUTHORITY_SIGNING_KEY": configured}):
            second = asyncio.run(
                router.attest(
                    second_run_id,
                    {
                        "candidate_state_id": "CAND-ROTATED-KEY",
                        "human_stop_id": "STOP-001",
                        "course_id": "COURSE-EXTERNAL",
                        "actor_id": "partner-001",
                        "artifact_hash": "sha256:candidate",
                    },
                    session_id=self.session_id,
                )
            )["authority_record"]

        self.assertNotEqual(second["signing_key_id"], old_key_id)
        keyring = json.loads(router._authority_keyring_path().read_text())
        entries = {entry["key_id"]: entry for entry in keyring["keys"]}
        self.assertEqual(entries[old_key_id]["status"], "RETIRED")
        self.assertEqual(entries[second["signing_key_id"]]["status"], "ACTIVE")
        self.assertEqual(
            keyring["active_signing_key_id"], second["signing_key_id"]
        )
        router._verify_authority_record_signature(first)
        router._verify_authority_record_signature(second)

    def test_environment_public_keyring_verifies_without_private_key(self):
        record = self._attest()["authority_record"]
        keyring = json.loads(router._authority_keyring_path().read_text())
        entry = next(
            item
            for item in keyring["keys"]
            if item["key_id"] == record["signing_key_id"]
        )
        router._authority_keyring_path().unlink()
        router._authority_signing_key_path().unlink()
        configured = json.dumps(
            {record["signing_key_id"]: entry["public_key"]}
        )

        with patch.dict(
            os.environ,
            {"PANTA_AUTHORITY_TRUSTED_PUBLIC_KEYS": configured},
        ):
            router._verify_authority_record_signature(record)

    def test_existing_ledger_bootstraps_keyring_from_matching_private_key(self):
        record = self._attest()["authority_record"]
        router._authority_keyring_path().unlink()

        router._verify_authority_record_signature(record)

        restored = json.loads(router._authority_keyring_path().read_text())
        self.assertEqual(
            restored["active_signing_key_id"], record["signing_key_id"]
        )

    def test_revoked_signing_key_fails_closed_from_effective_time(self):
        record = self._attest()["authority_record"]
        keyring = json.loads(router._authority_keyring_path().read_text())
        keyring["active_signing_key_id"] = None
        entry = next(
            item
            for item in keyring["keys"]
            if item["key_id"] == record["signing_key_id"]
        )
        entry.update(
            status="REVOKED",
            revoked_effective_at=record["timestamp"],
            revocation_known_at=router._now_iso(),
        )
        router._write_authority_keyring(keyring)

        with self.assertRaisesRegex(HTTPException, "revoked") as rejected:
            router._verify_authority_record_signature(record)

        self.assertEqual(rejected.exception.status_code, 409)

    def test_future_authority_assignment_is_rejected_before_ledger_append(self):
        future_actor = {
            "actor_id": "partner-001",
            "role": "DEAL_PARTNER",
            "authority_roles": ["PROFESSIONAL_REVIEWER"],
            "authority_verbs": ["RESOLVE_HUMAN_STOP"],
            "effective_from": "2999-01-01T00:00:00Z",
            "known_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(router, "_authority_actor", return_value=future_actor):
            with self.assertRaisesRegex(HTTPException, "not valid") as rejected:
                self._attest()

        self.assertEqual(rejected.exception.status_code, 403)
        self.assertEqual(router._authority_ledger_records(), [])

    def test_ledger_chains_records_and_database_rejects_mutation(self):
        first = self._attest()["authority_record"]
        second_run_id = "RUN-EXEC-002"
        second_run = copy.deepcopy(router._runs[self.run_id])
        second_run.update(
            run_id=second_run_id,
            candidate_state_id="CAND-002",
            prepared_selection_hash="sha256:prepared-selection-002",
            authority_records=[],
            execution_packages={},
        )
        router._store_run(second_run_id, second_run)
        second = asyncio.run(
            router.attest(
                second_run_id,
                {
                    "candidate_state_id": "CAND-002",
                    "human_stop_id": "STOP-001",
                    "course_id": "COURSE-EXTERNAL",
                    "actor_id": "partner-001",
                    "artifact_hash": "sha256:candidate",
                },
                session_id=self.session_id,
            )
        )["authority_record"]

        self.assertEqual(second["ledger_sequence"], 2)
        self.assertEqual(second["previous_record_hash"], first["record_hash"])
        self.assertEqual(router._authority_ledger_records(), [first, second])

        connection = sqlite3.connect(router._authority_ledger_path())
        try:
            with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                connection.execute(
                    "UPDATE authority_records SET run_id = ? WHERE ledger_sequence = 1",
                    ("FORGED-RUN",),
                )
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
