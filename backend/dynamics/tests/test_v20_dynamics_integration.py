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
        router.PIPELINE_OUT = self.bundle
        router.VAULT = self.root / "vault"
        router._runs.clear()

    def tearDown(self):
        router.PIPELINE_OUT = self.previous_bundle
        router.VAULT = self.previous_vault
        router._runs.clear()
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
        stop_id = transition["human_stops"][0]["stop_id"]

        with self.assertRaisesRegex(Exception, "recorded human approval"):
            asyncio.run(router.settle_run(run_id, BackgroundTasks(), {}))

        attestation = asyncio.run(
            router.attest(
                run_id,
                {
                    "candidate_state_id": transition["candidate_state_id"],
                    "human_stop_id": stop_id,
                    "course_id": "ADOPT-CANDIDATE",
                    "actor_id": "reviewer-001",
                    "actor_role": "PROFESSIONAL_REVIEWER",
                    "artifact_hash": transition["replay_hash"],
                },
            )
        )
        record_id = attestation["authority_record"]["authority_record_id"]
        settled = asyncio.run(
            router.settle_run(
                run_id,
                BackgroundTasks(),
                {
                    "actor_id": "reviewer-001",
                    "authority_record_ids": [record_id],
                    "selected_change_ids": ["CL-028"],
                },
            )
        )
        self.assertEqual(settled["runtime_state_id"], settled["current_state_id"])
        self.assertTrue((self.bundle / "runtime_state.json").exists())
        self.assertEqual(json.loads((self.bundle / "candidate_graph.json").read_text()), {})


if __name__ == "__main__":
    unittest.main()
