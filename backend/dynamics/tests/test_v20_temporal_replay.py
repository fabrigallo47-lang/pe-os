import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20TemporalReplayTests(unittest.TestCase):
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
        case_dir = router.VAULT / "deals" / self.case_id
        events_dir = case_dir / "events"
        events_dir.mkdir(parents=True)
        (case_dir / "deal_profile.json").write_text(
            json.dumps({"entity": "Scout"}), encoding="utf-8"
        )
        (events_dir / "early.md").write_text(
            "---\n"
            "id: E-EARLY\n"
            "type: evidence_admitted\n"
            "label: Early evidence admitted\n"
            "source: early-source\n"
            "effective_date: '2026-01-01'\n"
            "known_at: '2026-01-10T12:00:00Z'\n"
            "result_state_id: STATE-EARLY\n"
            "---\n",
            encoding="utf-8",
        )
        (events_dir / "late.md").write_text(
            "---\n"
            "id: E-LATE\n"
            "type: settlement\n"
            "label: Late decision settled\n"
            "source: late-source\n"
            "effective_date: '2026-01-02'\n"
            "known_at: '2026-01-20T09:00:00Z'\n"
            "source_state_id: STATE-EARLY\n"
            "result_state_id: STATE-LATE\n"
            "---\n",
            encoding="utf-8",
        )

        bundle = router._pipeline_out_for_case(self.case_id)
        bundle.mkdir(parents=True)
        (bundle / "claims.json").write_text(
            json.dumps(
                [
                    {
                        "claim_id": "claim-early",
                        "statement": "Known before cutoff",
                        "source_id": "early-source",
                        "period": "2025-12-31",
                        "known_at": "2026-01-05T08:00:00Z",
                    },
                    {
                        "claim_id": "claim-late",
                        "statement": "Learned after cutoff",
                        "source_id": "late-source",
                        "period": "2025-12-31",
                        "known_at": "2026-01-20T08:00:00Z",
                    },
                ]
            ),
            encoding="utf-8",
        )
        router._archive_graph_version(
            self.case_id,
            "STATE-EARLY",
            "CURRENT",
            {"case_id": self.case_id, "state_id": "STATE-EARLY", "case_positions": []},
            known_at="2026-01-10T12:00:00Z",
        )
        router._archive_graph_version(
            self.case_id,
            "STATE-LATE",
            "CURRENT",
            {"case_id": self.case_id, "state_id": "STATE-LATE", "case_positions": []},
            known_at="2026-01-20T09:00:00Z",
        )

    def tearDown(self):
        router.PIPELINE_OUT = self.previous_pipeline_out
        router.CASE_PIPELINE_ROOT = self.previous_case_pipeline_root
        router.VAULT = self.previous_vault
        router.INDEX_DB = self.previous_index_db
        self.temporary.cleanup()

    def test_date_replay_excludes_future_knowledge_and_future_graph(self):
        first = router.replay(self.case_id, as_of_date="2026-01-15")
        second = router.replay(self.case_id, as_of_date="2026-01-15")
        projection = first["projection"]["projection"]

        self.assertEqual(first["stable_hash"], second["stable_hash"])
        self.assertEqual(first["event"]["event_id"], "E-EARLY")
        self.assertEqual(first["result_state_id"], "STATE-EARLY")
        self.assertEqual(
            [claim["claim_id"] for claim in projection["deal"]["claims"]],
            ["claim-early"],
        )
        self.assertEqual(set(projection["events"]), {"E-EARLY"})
        self.assertEqual(
            projection["deal"]["current_graph"]["state_id"], "STATE-EARLY"
        )
        self.assertEqual(projection["deal"]["candidate_graph"], {})
        self.assertEqual(
            [item["event_id"] for item in projection["deal"]["replay"]["snapshots"]],
            ["E-EARLY"],
        )
        refreshed = router.projection(self.case_id, as_of_date="2026-01-15")
        self.assertEqual(
            [claim["claim_id"] for claim in refreshed["projection"]["deal"]["claims"]],
            ["claim-early"],
        )
        self.assertEqual(refreshed["context"]["as_of_state_id"], "STATE-EARLY")

    def test_event_replay_uses_exact_event_cutoff(self):
        replayed = router.replay(self.case_id, event_id="E-LATE")
        projection = replayed["projection"]["projection"]

        self.assertEqual(replayed["event"]["event_id"], "E-LATE")
        self.assertEqual(replayed["source_state_id"], "STATE-EARLY")
        self.assertEqual(replayed["result_state_id"], "STATE-LATE")
        self.assertEqual(
            {claim["claim_id"] for claim in projection["deal"]["claims"]},
            {"claim-early", "claim-late"},
        )
        self.assertEqual(len(replayed["projection"]["registry"]), 2)

    def test_invalid_or_unknown_replay_target_is_rejected(self):
        with self.assertRaises(HTTPException) as invalid:
            router.replay(self.case_id, as_of_date="15-01-2026")
        self.assertEqual(invalid.exception.status_code, 400)

        with self.assertRaises(HTTPException) as missing:
            router.replay(self.case_id, event_id="E-MISSING")
        self.assertEqual(missing.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
