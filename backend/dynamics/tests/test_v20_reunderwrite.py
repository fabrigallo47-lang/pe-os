import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20ReunderwriteTests(unittest.TestCase):
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
        self.case_id = "scout"
        (router.VAULT / "deals" / self.case_id).mkdir(parents=True)

        baseline = {
            "case_id": self.case_id,
            "state_id": "STATE-BASELINE",
            "claims": [self._claim("C-1", 10)],
            "case_positions": [self._position("CP-1", 10)],
            "model_nodes": [{"model_node_id": "MN-1", "value": 10}],
            "position_model_bindings": [
                {"position_id": "CP-1", "model_node_id": "MN-1", "status": "ACTIVE"}
            ],
        }
        current = {
            "case_id": self.case_id,
            "state_id": "STATE-CURRENT",
            "claims": [self._claim("C-1", 12), self._claim("C-2", 2)],
            "case_positions": [self._position("CP-1", 12), self._position("CP-2", 2)],
            "model_nodes": [{"model_node_id": "MN-1", "value": 12}],
            "position_model_bindings": [
                {"position_id": "CP-1", "model_node_id": "MN-1", "status": "ACTIVE"}
            ],
        }
        router._archive_graph_version(
            self.case_id,
            "STATE-BASELINE",
            "CURRENT",
            baseline,
            known_at="2026-01-10T00:00:00Z",
        )
        router._archive_graph_version(
            self.case_id,
            "STATE-CURRENT",
            "CURRENT",
            current,
            prior_state_id="STATE-BASELINE",
            known_at="2026-02-10T00:00:00Z",
        )

    def tearDown(self):
        router.PIPELINE_OUT = self.previous_pipeline_out
        router.CASE_PIPELINE_ROOT = self.previous_case_pipeline_root
        router.VAULT = self.previous_vault
        router.INDEX_DB = self.previous_index_db
        self.temporary.cleanup()

    @staticmethod
    def _claim(claim_id: str, value: int) -> dict:
        return {
            "claim_id": claim_id,
            "statement": claim_id,
            "value": value,
            "source_id": "source-1",
            "effective_date": "2025-12-31",
            "known_at": "2026-01-01T00:00:00Z",
        }

    @staticmethod
    def _position(position_id: str, value: int) -> dict:
        return {
            "position_id": position_id,
            "statement": position_id,
            "value": value,
            "decision_status": "PENDING",
            "epistemic_status": "CONTESTED",
        }

    def test_reunderwrite_compares_two_immutable_current_states(self):
        result = router.reunderwrite(self.case_id)
        comparison = result["comparison"]
        projection = result["projection"]["projection"]

        self.assertEqual(result["mode"], "RE_UNDERWRITE")
        self.assertTrue(result["read_only"])
        self.assertEqual(comparison["baseline_state_id"], "STATE-BASELINE")
        self.assertEqual(comparison["current_state_id"], "STATE-CURRENT")
        self.assertEqual(comparison["collections"]["claims"]["added_ids"], ["C-2"])
        self.assertEqual(
            comparison["collections"]["claims"]["changed"][0]["changed_fields"],
            ["value"],
        )
        self.assertEqual(
            comparison["collections"]["case_positions"]["added_ids"],
            ["CP-2"],
        )
        self.assertEqual(comparison["collections"]["model_nodes"]["counts"]["changed"], 1)
        self.assertEqual(projection["deal"]["as_of_state_id"], "STATE-CURRENT")
        self.assertEqual(projection["deal"]["current_graph"]["state_id"], "STATE-CURRENT")
        self.assertEqual(
            {claim["claim_id"] for claim in projection["deal"]["claims"]},
            {"C-1", "C-2"},
        )
        self.assertEqual(projection["deal"]["reunderwrite"], comparison)
        self.assertEqual(
            projection["deal"]["load_bearing_assumptions"][0]["position_id"],
            "CP-1",
        )

    def test_reunderwrite_rejects_reversed_or_missing_baseline(self):
        with self.assertRaises(HTTPException) as reversed_states:
            router.reunderwrite(
                self.case_id,
                baseline_state_id="STATE-CURRENT",
                current_state_id="STATE-BASELINE",
            )
        self.assertEqual(reversed_states.exception.status_code, 400)

        only_case = "single-state"
        (router.VAULT / "deals" / only_case).mkdir(parents=True)
        router._archive_graph_version(
            only_case,
            "STATE-ONLY",
            "CURRENT",
            {"case_id": only_case, "state_id": "STATE-ONLY"},
            known_at="2026-01-01T00:00:00Z",
        )
        with self.assertRaises(HTTPException) as missing_prior:
            router.reunderwrite(only_case)
        self.assertEqual(missing_prior.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
