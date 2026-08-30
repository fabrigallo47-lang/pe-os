import asyncio
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import BackgroundTasks
from starlette.requests import Request


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20LiveEvidenceLoopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()

        pre_e3 = json.loads(
            (PROJECT_ROOT / "pipeline_out/e3/K-PRE/e3_claims.json").read_text(
                encoding="utf-8"
            )
        )
        ic_e3 = json.loads(
            (PROJECT_ROOT / "pipeline_out/e3/K-IC/e3_claims.json").read_text(
                encoding="utf-8"
            )
        )
        claim_id = "ks-77418c65e681"
        self.claim = dict(
            next(item for item in ic_e3["claims"] if item["claim_id"] == claim_id)
        )
        compiler_metadata = next(
            item
            for item in ic_e3["extraction_metadata"]["compiler_fields_per_claim"]
            if item["claim_id"] == claim_id
        )
        for key, value in compiler_metadata.items():
            if value is not None and not self.claim.get(key):
                self.claim[key] = value

        (self.bundle / "claims.json").write_text(
            json.dumps(pre_e3["claims"], indent=2) + "\n",
            encoding="utf-8",
        )

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
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

    def tearDown(self):
        self.index_patch.stop()
        router.PIPELINE_OUT = self.previous_bundle
        router.VAULT = self.previous_vault
        router.INGEST_JOBS_LOG = self.previous_jobs_log
        router.RUNS_LOG = self.previous_runs_log
        router._jobs.clear()
        router._jobs.update(self.previous_jobs)
        router._runs.clear()
        router._runs.update(self.previous_runs)
        self.temporary.cleanup()

    @staticmethod
    def _json_request(payload: dict) -> Request:
        body = json.dumps(payload).encode("utf-8")
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v20/cases/keystone/ingest",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
        )

    def test_real_extracted_claim_reaches_candidate_settlement_and_reload(self):
        request = self._json_request(
            {
                "file_name": "keystone-live-source.txt",
                "purpose": "PAN-37 live runtime smoke",
                "content_b64": base64.b64encode(b"real source content").decode("ascii"),
            }
        )
        extraction_tasks = BackgroundTasks()

        def fake_extractor(command, **_kwargs):
            output_dir = Path(command[command.index("--output") + 1]) / "SINGLE"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "e3_claims.json").write_text(
                json.dumps({"deal": "keystone", "claims": [self.claim]}, indent=2) + "\n",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="one real claim", stderr="")

        with patch.object(router.subprocess, "run", side_effect=fake_extractor):
            queued = asyncio.run(
                router.ingest("keystone", request, extraction_tasks)
            )
            for task in extraction_tasks.tasks:
                asyncio.run(task())

        job_id = queued["job_id"]
        self.assertEqual(router.get_job(job_id)["status"], "COMPLETE")
        proposal = json.loads(router._proposal_path(job_id).read_text(encoding="utf-8"))
        self.assertEqual(proposal["claims"][0]["claim_id"], self.claim["claim_id"])
        self.assertFalse((self.bundle / "current_graph.json").exists())

        admitted = asyncio.run(
            router.admit_evidence(
                "keystone",
                job_id,
                {"decision": "ADMIT", "actor_id": "reviewer-001"},
            )
        )
        event_id = admitted["event_id"]
        self.assertEqual(admitted["runtime_event"]["event_id"], event_id)
        self.assertEqual(admitted["runtime_event"]["mutation_count"], 1)
        self.assertEqual(admitted["runtime_event"]["mapped_claim_count"], 1)
        self.assertTrue((self.bundle / "current_graph.json").exists())
        runtime_event = json.loads(
            Path(admitted["runtime_event"]["path"]).read_text(encoding="utf-8")
        )
        mutation = runtime_event["mutations"][0]
        self.assertEqual(mutation["object_id"], self.claim["claim_id"])
        self.assertEqual(mutation["target_position_id"], "CP-DSO")
        self.assertNotEqual(runtime_event.get("event_status"), "SYNTHETIC_TEST_EVENT")
        current_before_dynamics = json.loads(
            (self.bundle / "current_graph.json").read_text(encoding="utf-8")
        )

        candidate = asyncio.run(
            router.admit("keystone", event_id, BackgroundTasks(), {})
        )
        run_id = candidate["run"]["run_id"]
        transition = candidate["transition"]
        affected_ids = {item["object_id"] for item in transition["affected_set"]}
        self.assertIn(self.claim["claim_id"], affected_ids)
        self.assertIn("CP-DSO", affected_ids)
        self.assertIn("MN-BASE-DSO", affected_ids)
        recomputed = {
            item["object_id"]: item for item in transition["recomputed_values"]
        }
        self.assertEqual(
            str(recomputed[self.claim["claim_id"]]["candidate_value"]),
            str(self.claim["value"]),
        )
        self.assertEqual(
            candidate["candidate_graph"],
            json.loads((self.bundle / "candidate_graph.json").read_text()),
        )
        self.assertNotEqual(candidate["candidate_graph"], current_before_dynamics)
        self.assertNotIn(
            self.claim["claim_id"],
            {item["claim_id"] for item in current_before_dynamics["claims"]},
        )
        self.assertIn(
            self.claim["claim_id"],
            {item["claim_id"] for item in candidate["candidate_graph"]["claims"]},
        )
        self.assertTrue((self.bundle / "candidate_state.json").exists())
        versions_before_settlement = router.list_graph_versions("keystone")["versions"]
        self.assertEqual(
            [item["kind"] for item in versions_before_settlement],
            ["CURRENT", "CANDIDATE"],
        )
        candidate_version = candidate["candidate_graph_version"]
        self.assertEqual(candidate_version["kind"], "CANDIDATE")
        self.assertEqual(
            router.get_graph_version(
                "keystone", candidate_version["version_id"]
            )["graph"],
            candidate["candidate_graph"],
        )

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

        router._runs.clear()
        router._load_durable_registries()
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
        self.assertEqual(prepared["status"], "PREPARED")
        self.assertEqual(prepared["selected_change_ids"], selected_change_ids)

        authority_record_ids = []
        execution_package_ids = []
        for stop_id in stop_ids:
            attested = asyncio.run(
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
            authority_record_ids.append(
                attested["authority_record"]["authority_record_id"]
            )
            if attested.get("execution_package"):
                execution_package_ids.append(
                    attested["execution_package"]["execution_package_id"]
                )

        settled = asyncio.run(
            router.settle_run(
                run_id,
                BackgroundTasks(),
                {
                    "candidate_state_id": transition["candidate_state_id"],
                    "selected_change_ids": selected_change_ids,
                    "human_stop_ids": stop_ids,
                    "authority_record_ids": authority_record_ids,
                    "execution_package_ids": execution_package_ids,
                    "actor_id": "partner-001",
                    "allow_partial_settlement": partial_required,
                    "idempotency_key": f"SETTLE-{run_id}",
                },
            )
        )
        self.assertEqual(settled["runtime_state_id"], settled["current_state_id"])
        self.assertEqual(settled["replay_hash"], transition["replay_hash"])
        self.assertEqual(settled["selected_change_ids"], selected_change_ids)

        router._runs.clear()
        router._load_durable_registries()
        refreshed = router.projection("keystone")
        self.assertEqual(
            refreshed["context"]["as_of_state_id"], settled["current_state_id"]
        )
        self.assertEqual(
            len(refreshed["projection"]["deal"]["graph_versions"]),
            3,
        )
        self.assertNotIn("_adapter_error", refreshed["projection"])
        self.assertFalse((self.bundle / "candidate_state.json").exists())
        self.assertEqual(json.loads((self.bundle / "candidate_graph.json").read_text()), {})
        settled_graph = json.loads((self.bundle / "current_graph.json").read_text())
        self.assertIn(
            self.claim["claim_id"],
            {item["claim_id"] for item in settled_graph["claims"]},
        )
        versions_after_settlement = router.list_graph_versions("keystone")["versions"]
        self.assertEqual(len(versions_after_settlement), 3)
        self.assertEqual(versions_after_settlement[-1]["kind"], "CURRENT")
        self.assertEqual(
            router.get_graph_version(
                "keystone", candidate_version["version_id"]
            )["graph"],
            candidate["candidate_graph"],
        )
        self.assertEqual(
            router.get_graph_version(
                "keystone", settled["graph_version"]["version_id"]
            )["graph"],
            settled_graph,
        )


if __name__ == "__main__":
    unittest.main()
