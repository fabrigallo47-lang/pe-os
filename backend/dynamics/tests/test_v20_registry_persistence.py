import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20RegistryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_jobs_log = router.INGEST_JOBS_LOG
        self.previous_runs_log = router.RUNS_LOG
        self.previous_jobs = dict(router._jobs)
        self.previous_runs = dict(router._runs)
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._jobs.clear()
        router._runs.clear()

    def tearDown(self):
        router.INGEST_JOBS_LOG = self.previous_jobs_log
        router.RUNS_LOG = self.previous_runs_log
        router._jobs.clear()
        router._jobs.update(self.previous_jobs)
        router._runs.clear()
        router._runs.update(self.previous_runs)
        self.temporary.cleanup()

    def test_job_updates_survive_restart(self):
        router._store_job(
            "JOB-001",
            {"job_id": "JOB-001", "case_id": "keystone", "status": "PENDING"},
        )
        router._store_job("JOB-001", status="COMPLETE", progress=100)

        router._jobs.clear()
        router._load_durable_registries()

        response = router.get_job("JOB-001")
        self.assertEqual(response["status"], "COMPLETE")
        self.assertEqual(response["progress"], 100)
        self.assertEqual(response["case_id"], "keystone")

    def test_job_registry_keeps_only_latest_200_jobs(self):
        for index in range(204):
            job_id = f"JOB-{index:03d}"
            router._jobs[job_id] = {"job_id": job_id, "status": "COMPLETE"}
        router._store_job("JOB-204", {"job_id": "JOB-204", "status": "COMPLETE"})

        payload = json.loads(router.INGEST_JOBS_LOG.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["jobs"]), 200)
        self.assertNotIn("JOB-000", payload["jobs"])
        self.assertNotIn("JOB-004", payload["jobs"])
        self.assertIn("JOB-005", payload["jobs"])
        self.assertIn("JOB-204", payload["jobs"])

    def test_corrupt_registry_does_not_prevent_startup(self):
        router.INGEST_JOBS_LOG.parent.mkdir(parents=True, exist_ok=True)
        router.INGEST_JOBS_LOG.write_text("{not-json", encoding="utf-8")
        router.RUNS_LOG.write_text("{not-json", encoding="utf-8")

        router._load_durable_registries()

        self.assertEqual(router._jobs, {})
        self.assertEqual(router._runs, {})


if __name__ == "__main__":
    unittest.main()
