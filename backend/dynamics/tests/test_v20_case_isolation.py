import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from backend.dynamics import DynamicsBundleError  # noqa: E402


class V20CaseIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_pipeline_out = router.PIPELINE_OUT
        self.previous_case_pipeline_root = router.CASE_PIPELINE_ROOT
        self.previous_vault = router.VAULT
        self.previous_index_db = router.INDEX_DB
        router.PIPELINE_OUT = self.root / "keystone-bundle"
        router.CASE_PIPELINE_ROOT = self.root / "case-bundles"
        router.VAULT = self.root / "vault"
        router.INDEX_DB = self.root / "missing-index.db"

    def tearDown(self):
        router.PIPELINE_OUT = self.previous_pipeline_out
        router.CASE_PIPELINE_ROOT = self.previous_case_pipeline_root
        router.VAULT = self.previous_vault
        router.INDEX_DB = self.previous_index_db
        self.temporary.cleanup()

    @staticmethod
    def _claim(claim_id: str, source_id: str) -> dict:
        return {
            "claim_id": claim_id,
            "statement": f"Statement for {claim_id}",
            "source_id": source_id,
            "period": "2026-12-31",
            "known_at": "2026-08-29T00:00:00Z",
        }

    def _write_case(self, case_id: str, claim_id: str, state_id: str) -> Path:
        bundle = router._pipeline_out_for_case(case_id)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "claims.json").write_text(
            json.dumps([self._claim(claim_id, f"source-{case_id}")]),
            encoding="utf-8",
        )
        (bundle / "current_graph.json").write_text(
            json.dumps({"case_id": case_id, "state_id": state_id}),
            encoding="utf-8",
        )
        profile_dir = router.VAULT / "deals" / case_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "deal_profile.json").write_text(
            json.dumps({"entity": case_id.title()}),
            encoding="utf-8",
        )
        return bundle

    def test_projection_and_current_state_are_isolated_by_case(self):
        keystone_bundle = self._write_case(
            "keystone", "claim-keystone", "STATE-KEYSTONE-ONLY"
        )
        scout_bundle = self._write_case("scout", "claim-scout", "STATE-SCOUT-ONLY")

        keystone = router._build_projection("keystone")
        scout = router._build_projection("scout")

        self.assertEqual(router._pipeline_out_for_case("keystone"), keystone_bundle)
        self.assertEqual(router._pipeline_out_for_case("scout"), scout_bundle)
        self.assertEqual(
            {item["claim_id"] for item in keystone["deal"]["claims"]},
            {"claim-keystone"},
        )
        self.assertEqual(
            {item["claim_id"] for item in scout["deal"]["claims"]},
            {"claim-scout"},
        )
        self.assertEqual(router._current_state_id("keystone"), "STATE-KEYSTONE-ONLY")
        self.assertEqual(router._current_state_id("scout"), "STATE-SCOUT-ONLY")

    def test_case_scoping_covers_proposals_runs_and_graph_versions(self):
        router.PIPELINE_OUT.mkdir(parents=True)
        (router.PIPELINE_OUT / "execution_graph_v7.json").write_text(
            "{}", encoding="utf-8"
        )

        proposal = router._write_evidence_proposal(
            "job-scout",
            "scout",
            "scout-source.txt",
            [self._claim("claim-scout", "source-scout")],
        )
        label, command = router._extraction_command(
            self.root / "scout-source.txt", "scout", "job-scout"
        )
        version = router._archive_graph_version(
            "scout", "STATE-SCOUT-1", "CURRENT", {"case_id": "scout"}
        )

        scout_bundle = router._pipeline_out_for_case("scout")
        self.assertEqual(label, "SINGLE")
        self.assertTrue(proposal.is_relative_to(scout_bundle))
        self.assertIn(str(scout_bundle / "runs" / "job-scout"), command)
        self.assertEqual(version["case_id"], "scout")
        self.assertTrue((scout_bundle / "graph_versions" / "index.json").exists())
        self.assertFalse((router.PIPELINE_OUT / "graph_versions" / "index.json").exists())
        with self.assertRaises(DynamicsBundleError):
            router._runtime_execution_graph("scout")

    def test_inbox_only_lists_records_for_requested_case(self):
        router._write_inbox_manifest(
            [
                {"job_id": "job-keystone", "case_id": "keystone", "stored_name": "k.txt"},
                {"job_id": "job-scout", "case_id": "scout", "stored_name": "s.txt"},
            ]
        )

        scout_items = router.sources("scout")["inbox"]

        self.assertEqual([item["job_id"] for item in scout_items], ["job-scout"])

    def test_bootstrap_exposes_every_available_case(self):
        for case_id in ("keystone", "scout"):
            deal_dir = router.VAULT / "deals" / case_id
            deal_dir.mkdir(parents=True, exist_ok=True)
            (deal_dir / "deal.md").write_text(
                f"---\nid: {case_id}\n---\n", encoding="utf-8"
            )

        flat = router.bootstrap_flat("scout")
        scoped = router.bootstrap("scout")

        self.assertEqual(flat["context"]["case_id"], "scout")
        self.assertEqual(flat["available_cases"], ["keystone", "scout"])
        self.assertEqual(flat["cases"], ["keystone", "scout"])
        self.assertEqual(scoped["available_cases"], ["keystone", "scout"])


if __name__ == "__main__":
    unittest.main()
