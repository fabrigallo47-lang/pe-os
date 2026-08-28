import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20SearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary.name) / "vault.db"
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                CREATE TABLE nodes (
                    id TEXT PRIMARY KEY, type TEXT, path TEXT, title TEXT,
                    state TEXT, epistemic TEXT, subject TEXT, value TEXT,
                    deal TEXT, frontmatter TEXT, metric_category TEXT,
                    digital_source TEXT, extracted TEXT, last_seen TEXT,
                    period TEXT, perimeter TEXT
                )
                """
            )
            self._insert(
                con,
                "CL-EBITDA",
                "claim",
                "Firm EBITDA",
                "Firm-underwritten EBITDA is $11.4m",
                "11.4",
                "keystone",
                {"statement": "Firm-underwritten EBITDA is $11.4m"},
            )
            self._insert(
                con,
                "Q-EBITDA",
                "question",
                "Which EBITDA basis is supportable?",
                None,
                None,
                "keystone",
                {"question": "Which EBITDA basis is supportable?", "bearing": "price and leverage"},
            )
            self._insert(
                con,
                "ART-QOE",
                "artifact",
                "Quality of Earnings report",
                None,
                None,
                "keystone",
                {"title": "Quality of Earnings report", "kind": "consultant-report"},
            )
            self._insert(
                con,
                "CL-OTHER",
                "claim",
                "Other EBITDA",
                "EBITDA from another deal",
                "99",
                "other-deal",
                {"statement": "EBITDA from another deal"},
            )
        self.previous_db = router.INDEX_DB
        router.INDEX_DB = self.db_path

    def tearDown(self):
        router.INDEX_DB = self.previous_db
        self.temporary.cleanup()

    @staticmethod
    def _insert(con, node_id, node_type, title, subject, value, deal, frontmatter):
        con.execute(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                node_id,
                node_type,
                f"deals/{deal}/{node_id}.md",
                title,
                None,
                None,
                subject,
                value,
                deal,
                json.dumps(frontmatter),
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        )

    def test_search_returns_v20_shape_and_filters_by_case(self):
        started = time.perf_counter()
        response = router.search_case("keystone", "EBITDA")
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.2)
        self.assertEqual([item["id"] for item in response["results"]], ["CL-EBITDA", "Q-EBITDA"])
        self.assertEqual(
            set(response["results"][0]),
            {"id", "type", "label", "route", "search_text"},
        )
        self.assertEqual(response["results"][0]["type"], "CLAIM")
        self.assertEqual(response["results"][0]["route"], "deal-command")
        self.assertNotIn("CL-OTHER", {item["id"] for item in response["results"]})

    def test_artifact_search_routes_to_artifacts_room(self):
        response = router.search_case("keystone", "consultant-report")

        self.assertEqual(len(response["results"]), 1)
        self.assertEqual(response["results"][0]["id"], "ART-QOE")
        self.assertEqual(response["results"][0]["type"], "ARTIFACT")
        self.assertEqual(response["results"][0]["route"], "artifacts")


if __name__ == "__main__":
    unittest.main()
