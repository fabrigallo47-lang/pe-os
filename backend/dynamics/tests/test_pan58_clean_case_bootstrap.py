"""PAN-58 — an explicit clean case is never replaced by another deal."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class PAN58CleanCaseBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous = {
            "VAULT": router.VAULT,
            "PIPELINE_OUT": router.PIPELINE_OUT,
            # Repointing PIPELINE_OUT alone does not isolate this test.
            # _pipeline_out_for_case() returns PIPELINE_OUT only for keystone and
            # CASE_PIPELINE_ROOT / case_id for every other case, so a "clean" case
            # kept reading the developer's real pipeline_out/cases/clean/ —
            # producing 20 condition:coverage-Q-* nodes in a case asserted to be
            # empty, on any machine that had ever run that case locally.
            "CASE_PIPELINE_ROOT": router.CASE_PIPELINE_ROOT,
            "INGEST_JOBS_LOG": router.INGEST_JOBS_LOG,
            "INGEST_BATCHES_LOG": router.INGEST_BATCHES_LOG,
            "RUNS_LOG": router.RUNS_LOG,
            "jobs": dict(router._jobs),
            "batches": dict(router._batches),
            "runs": dict(router._runs),
        }
        router.VAULT = self.root / "vault"
        router.PIPELINE_OUT = self.root / "pipeline_out"
        router.CASE_PIPELINE_ROOT = self.root / "pipeline_out" / "cases"
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router.INGEST_BATCHES_LOG = self.root / "logs" / "ingest_batches.json"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._jobs.clear()
        router._batches.clear()
        router._runs.clear()

        # Reproduce the original failure condition: another valid deal exists
        # while the explicitly requested clean case has no deal.md yet.
        astrelia = router.VAULT / "deals" / "astrelia"
        astrelia.mkdir(parents=True)
        (astrelia / "deal.md").write_text(
            "---\nid: astrelia\nentity: Astrelia\n---\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        router.VAULT = self.previous["VAULT"]
        router.PIPELINE_OUT = self.previous["PIPELINE_OUT"]
        router.CASE_PIPELINE_ROOT = self.previous["CASE_PIPELINE_ROOT"]
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

    def test_explicit_clean_case_stays_empty_and_navigable(self) -> None:
        bootstrap = router.bootstrap_flat("clean")

        self.assertEqual(bootstrap["context"]["case_id"], "clean")
        self.assertEqual(bootstrap["available_cases"][0], "clean")
        self.assertIn("astrelia", bootstrap["available_cases"])

        response = router.projection("clean")
        deal = response["projection"]["deal"]
        source_center = router.sources("clean")

        self.assertEqual(deal["case_id"], "clean")
        self.assertEqual(deal["claims"], [])
        self.assertEqual(deal["rooms"]["foundations"]["sets"], [])
        self.assertTrue(deal["rooms"]["unknowns"]["items"])
        self.assertTrue(all(
            item["status"] == "OPEN"
            for item in deal["rooms"]["unknowns"]["items"]
        ))
        self.assertEqual(source_center, {"sources": [], "inbox": []})

        # Projection must remain a read-only bootstrap: it must not materialize
        # claims or a fake deal merely to make the empty room navigable.
        claims_path = router._pipeline_out_for_case("clean") / "claims.json"
        self.assertFalse(claims_path.exists())
        self.assertFalse((router.VAULT / "deals" / "clean" / "deal.md").exists())

    def test_narrow_source_tabs_scroll_instead_of_shrinking_over_each_other(self) -> None:
        css = (
            PROJECT_ROOT / "ui" / "01_PRODUCT_BUILD" / "app" / "v20.css"
        ).read_text(encoding="utf-8")

        self.assertIn(".source-tabs{max-width:100%;overflow-x:auto", css)
        self.assertIn(".source-tabs button{flex:0 0 auto}", css)
        self.assertIn(".source-card header{align-items:flex-start}", css)
        self.assertIn(".source-card header .pill{flex:0 0 auto}", css)


if __name__ == "__main__":
    unittest.main()
