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


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20BulkIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.previous = {
            "PIPELINE_OUT": router.PIPELINE_OUT,
            "VAULT": router.VAULT,
            "INGEST_JOBS_LOG": router.INGEST_JOBS_LOG,
            "INGEST_BATCHES_LOG": router.INGEST_BATCHES_LOG,
            "RUNS_LOG": router.RUNS_LOG,
            "jobs": dict(router._jobs),
            "batches": dict(router._batches),
            "runs": dict(router._runs),
        }
        router.PIPELINE_OUT = self.bundle
        router.VAULT = self.root / "vault"
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router.INGEST_BATCHES_LOG = self.root / "logs" / "ingest_batches.json"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._jobs.clear()
        router._batches.clear()
        router._runs.clear()
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

    def tearDown(self):
        self.index_patch.stop()
        router.PIPELINE_OUT = self.previous["PIPELINE_OUT"]
        router.VAULT = self.previous["VAULT"]
        router.INGEST_JOBS_LOG = self.previous["INGEST_JOBS_LOG"]
        router.INGEST_BATCHES_LOG = self.previous["INGEST_BATCHES_LOG"]
        router.RUNS_LOG = self.previous["RUNS_LOG"]
        router._jobs.clear()
        router._jobs.update(self.previous["jobs"])
        router._batches.clear()
        router._batches.update(self.previous["batches"])
        router._runs.clear()
        router._runs.update(self.previous["runs"])
        self.temporary.cleanup()

    @staticmethod
    def _request(files, key="BATCH-TEST"):
        return router._InlineJSONRequest({
            "purpose": "mixed source intake",
            "idempotency_key": key,
            "concurrency": 2,
            "files": [
                {
                    "file_name": name,
                    "content_b64": base64.b64encode(content).decode("ascii"),
                }
                for name, content in files
            ],
        })

    @staticmethod
    def _run_background(background):
        for task in background.tasks:
            asyncio.run(task())

    @staticmethod
    def _extractor(command, **_kwargs):
        source = Path(command[command.index("--source") + 1])
        if "fail" in source.name:
            return SimpleNamespace(returncode=2, stdout="", stderr="synthetic failure")
        if "--out" in command:
            output = Path(command[command.index("--out") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "claims.json").write_text(json.dumps([{
                "claim_id": f"claim-{source.stem}",
                "statement": f"Claim extracted from {source.name}",
                "value": len(source.name),
                "unit": "count",
                "period": "FY2026",
                "perimeter": "Target",
                "epistemic_class": "asserted",
                "locator": f"{source.name}::1",
            }]), encoding="utf-8")
        else:
            output = Path(command[command.index("--output") + 1]) / "SINGLE"
            output.mkdir(parents=True, exist_ok=True)
            (output / "e3_claims.json").write_text(json.dumps({"claims": [{
                "claim_id": f"claim-{source.stem}",
                "statement": f"Claim extracted from {source.name}",
                "value": len(source.name),
                "unit": "count",
                "period": "FY2026",
                "perimeter": "Target",
                "epistemic_class": "asserted",
                "locator": f"{source.name}::Sheet1!1:1",
            }]}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="complete", stderr="")

    def test_partial_failure_persists_and_failed_file_retries_independently(self):
        background = BackgroundTasks()
        with patch.object(router.subprocess, "run", side_effect=self._extractor):
            queued = asyncio.run(router.bulk_ingest(
                "keystone",
                self._request([
                    ("first.txt", b"first"),
                    ("fail.md", b"fail"),
                    ("deck.pdf", b"pdf"),
                    ("model.xlsx", b"xlsx"),
                ]),
                background,
            ))
            self._run_background(background)

        batch_id = queued["batch_id"]
        batch = router.get_ingest_batch("keystone", batch_id)["batch"]
        self.assertEqual(batch["status"], "PARTIAL_ERROR")
        self.assertEqual(batch["counts"]["complete"], 3)
        self.assertEqual(batch["counts"]["error"], 1)
        self.assertEqual({job["batch_id"] for job in batch["jobs"]}, {batch_id})
        self.assertTrue(all(item.get("batch_id") == batch_id for item in router._read_inbox_manifest()))

        router._jobs.clear()
        router._batches.clear()
        router._load_durable_registries()
        reloaded = router.get_ingest_batch("keystone", batch_id)["batch"]
        self.assertEqual(reloaded["status"], "PARTIAL_ERROR")
        failed = next(job for job in reloaded["jobs"] if job["status"] == "ERROR")

        retry_background = BackgroundTasks()
        with patch.object(router.subprocess, "run", side_effect=lambda command, **kwargs: self._extractor([
            str(part).replace("fail", "recovered") for part in command
        ], **kwargs)):
            retried = asyncio.run(router.retry_batch_job(
                "keystone", batch_id, failed["job_id"], retry_background, {}
            ))
            self._run_background(retry_background)
        self.assertEqual(router.get_ingest_batch("keystone", batch_id)["status"], "COMPLETE")
        self.assertEqual(retried["retry_of"], failed["job_id"])
        self.assertEqual(len(router._batches[batch_id]["retry_history"]), 1)

    def test_batch_idempotency_does_not_duplicate_jobs(self):
        first_background = BackgroundTasks()
        first = asyncio.run(router.bulk_ingest(
            "keystone", self._request([("one.txt", b"one")], "SAME-KEY"), first_background
        ))
        second_background = BackgroundTasks()
        second = asyncio.run(router.bulk_ingest(
            "keystone", self._request([("different.txt", b"different")], "SAME-KEY"), second_background
        ))
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["batch_id"], second["batch"]["batch_id"])
        self.assertEqual(len(router._jobs), 1)
        self.assertFalse(second_background.tasks)

    def test_cumulative_merge_preserves_prior_claims_and_source_identity(self):
        first = [{"claim_id": "C-1", "statement": "First", "source_id": "source-a", "source_ids": ["source-a"]}]
        merged, added = router._merge_claim_corpus(first, [
            {"claim_id": "C-2", "statement": "Second", "source_id": "source-b", "source_ids": ["source-b"]}
        ])
        self.assertEqual({claim["claim_id"] for claim in merged}, {"C-1", "C-2"})
        self.assertEqual([claim["claim_id"] for claim in added], ["C-2"])
        merged_again, added_again = router._merge_claim_corpus(merged, [
            {"claim_id": "C-1", "statement": "First", "source_id": "source-c", "source_ids": ["source-c"]}
        ])
        self.assertFalse(added_again)
        first_claim = next(claim for claim in merged_again if claim["claim_id"] == "C-1")
        self.assertEqual(first_claim["source_ids"], ["source-a", "source-c"])


class V20OverflowUIContractTests(unittest.TestCase):
    def test_fixture_and_layout_contract_are_wired(self):
        ui = PROJECT_ROOT / "ui" / "01_PRODUCT_BUILD" / "app"
        index = (ui / "index.html").read_text(encoding="utf-8")
        render = (ui / "src" / "render.js").read_text(encoding="utf-8")
        engine = (ui / "src" / "engine.js").read_text(encoding="utf-8")
        css = (ui / "v20.css").read_text(encoding="utf-8")
        fixture = (ui / "src" / "overflow_qa.js").read_text(encoding="utf-8")
        self.assertIn('src/overflow_qa.js', index)
        self.assertIn('type="file" multiple', render)
        self.assertIn('data-retry-batch-job', render)
        self.assertIn('ingestFiles', engine)
        self.assertIn('.foundation-nodes', css)
        self.assertIn('overscroll-behavior:contain', css)
        self.assertIn('No document-level horizontal overflow', fixture)


if __name__ == "__main__":
    unittest.main()
