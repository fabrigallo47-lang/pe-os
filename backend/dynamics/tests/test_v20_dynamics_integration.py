import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import BackgroundTasks


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20DynamicsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        inputs = {
            "current_graph.json": DYNAMICS_ROOT
            / "canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json",
            "execution_mapping.json": DYNAMICS_ROOT
            / "benchmark/keystone_execution_mapping_v0.json",
            "keystone_materiality_policy_v0.json": DYNAMICS_ROOT
            / "benchmark/keystone_materiality_policy_v0.json",
            "keystone_authority_matrix_v0.json": DYNAMICS_ROOT
            / "benchmark/keystone_authority_matrix_v0.json",
        }
        for name, source in inputs.items():
            (self.bundle / name).write_bytes(source.read_bytes())
        suite = json.loads(
            (DYNAMICS_ROOT / "benchmark/transition_engine_conformance_cases_v1.json")
            .read_text(encoding="utf-8")
        )
        case = next(
            item
            for item in suite["cases"]
            if item["test_id"] == "TCE-001-KEYSTONE-FIRM-EBITDA-CORRECTION"
        )
        self.event = case["event_batch"][0]

        self.previous_bundle = router.PIPELINE_OUT
        self.previous_vault = router.VAULT
        self.previous_jobs_log = router.INGEST_JOBS_LOG
        self.previous_runs_log = router.RUNS_LOG
        self.previous_jobs = dict(router._jobs)
        self.previous_runs = dict(router._runs)
        router.PIPELINE_OUT = self.bundle
        router.VAULT = self.root / "vault"
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._jobs.clear()
        router._runs.clear()

    def tearDown(self):
        router.PIPELINE_OUT = self.previous_bundle
        router.VAULT = self.previous_vault
        router.INGEST_JOBS_LOG = self.previous_jobs_log
        router.RUNS_LOG = self.previous_runs_log
        router._jobs.clear()
        router._jobs.update(self.previous_jobs)
        router._runs.clear()
        router._runs.update(self.previous_runs)
        self.temporary.cleanup()

    def test_change_impact_runs_engine_and_settlement_requires_attestation(self):
        background = BackgroundTasks()
        admitted = asyncio.run(
            router.admit(
                "keystone",
                self.event["event_id"],
                background,
                {"event": self.event},
            )
        )
        run_id = admitted["run"]["run_id"]
        transition = admitted["transition"]
        self.assertEqual(transition["replay_hash"], router._runs[run_id]["transition_output"]["replay_hash"])
        self.assertTrue((self.bundle / "candidate_state.json").exists())
        self.assertTrue(router.RUNS_LOG.exists())
        selected_change_ids = [
            item["artifact_id"] for item in transition["artifact_change_sets"]
        ]
        self.assertTrue(selected_change_ids)
        stop_ids = [item["stop_id"] for item in transition["human_stops"]]
        partial_required = (
            transition["partial_settlement_status"].get("candidate") != "FULL"
            or bool(transition["blocked_components"])
            or any(item.get("partial") for item in transition["artifact_change_sets"])
        )

        prepared = asyncio.run(
            router.prepare_run(
                run_id,
                {
                    "candidate_state_id": transition["candidate_state_id"],
                    "selected_change_ids": selected_change_ids,
                    "actor_id": "preparer-001",
                },
            )
        )
        self.assertEqual(prepared["selected_change_ids"], selected_change_ids)
        self.assertEqual(
            len(list((router.VAULT / "deals/keystone/events").glob("*run-prepared*.md"))),
            1,
        )

        # Simulate a full API-process restart before professional review.
        router._runs.clear()
        router._load_durable_registries()
        self.assertIn(run_id, router._runs)
        self.assertEqual(
            router._runs[run_id]["selected_change_ids"], selected_change_ids
        )

        with self.assertRaisesRegex(Exception, "recorded human approval"):
            asyncio.run(
                router.settle_run(
                    run_id,
                    BackgroundTasks(),
                    {
                        "candidate_state_id": transition["candidate_state_id"],
                        "selected_change_ids": selected_change_ids,
                        "human_stop_ids": stop_ids,
                        "authority_record_ids": [],
                        "execution_package_ids": [],
                        "actor_id": "partner-001",
                        "allow_partial_settlement": partial_required,
                        "idempotency_key": f"SETTLE-NO-AUTH-{run_id}",
                    },
                )
            )

        record_ids = []
        package_ids = []
        for stop_id in stop_ids:
            attestation = asyncio.run(
                router.attest(
                    run_id,
                    {
                        "candidate_state_id": transition["candidate_state_id"],
                        "human_stop_id": stop_id,
                        "course_id": "ADOPT-CANDIDATE",
                        "actor_id": "partner-001",
                        "artifact_hash": transition["replay_hash"],
                    },
                )
            )
            record_ids.append(
                attestation["authority_record"]["authority_record_id"]
            )
            if attestation.get("execution_package"):
                package_ids.append(
                    attestation["execution_package"]["execution_package_id"]
                )

        # The authority record must survive another restart before settlement.
        router._runs.clear()
        router._load_durable_registries()
        self.assertEqual(
            [
                item["authority_record_id"]
                for item in router._runs[run_id]["authority_records"]
            ],
            record_ids,
        )
        settled = asyncio.run(
            router.settle_run(
                run_id,
                BackgroundTasks(),
                {
                    "candidate_state_id": transition["candidate_state_id"],
                    "selected_change_ids": selected_change_ids,
                    "human_stop_ids": stop_ids,
                    "authority_record_ids": record_ids,
                    "execution_package_ids": package_ids,
                    "actor_id": "partner-001",
                    "allow_partial_settlement": partial_required,
                    "idempotency_key": f"SETTLE-{run_id}",
                },
            )
        )
        self.assertEqual(settled["runtime_state_id"], settled["current_state_id"])
        self.assertEqual(settled["selected_change_ids"], selected_change_ids)
        self.assertTrue((self.bundle / "runtime_state.json").exists())
        self.assertEqual(json.loads((self.bundle / "candidate_graph.json").read_text()), {})
        settlement_files = list(
            (router.VAULT / "deals/keystone/events").glob("*settle*.md")
        )
        self.assertEqual(len(settlement_files), 1)
        settlement_event = router._read_frontmatter(settlement_files[0])
        self.assertEqual(
            settlement_event["selected-change-ids"], selected_change_ids
        )
        self.assertEqual(settlement_event["current_state_id"], settled["current_state_id"])

        router._runs.clear()
        router._load_durable_registries()
        self.assertEqual(router._runs[run_id]["status"], "SETTLED")
        self.assertEqual(router._runs[run_id]["settled_state_id"], settled["current_state_id"])
        self.assertEqual(
            router._runs[run_id]["selected_change_ids"], selected_change_ids
        )

        refreshed = router.projection("keystone")
        self.assertEqual(refreshed["context"]["as_of_state_id"], settled["current_state_id"])
        self.assertFalse((self.bundle / "candidate_state.json").exists())
        self.assertEqual(json.loads((self.bundle / "candidate_graph.json").read_text()), {})


if __name__ == "__main__":
    unittest.main()
