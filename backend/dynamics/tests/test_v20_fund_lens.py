import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from tools.bind_questions_e3 import (  # noqa: E402
    DEFAULT_FUND_LENS,
    ranked_bindings,
    validate_fund_lens,
)


class V20FundLensTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_vault = router.VAULT
        router.VAULT = self.root / "vault"

    def tearDown(self):
        router.VAULT = self.previous_vault
        self.temporary.cleanup()

    @staticmethod
    def _manual_lens(version: str = "1.0.0") -> dict:
        lens = copy.deepcopy(DEFAULT_FUND_LENS)
        lens.update({
            "lens_id": "FL-SCOUT-MANUAL",
            "version": version,
            "label": "Scout Manual Buyout Lens",
            "binding_profile": "scout-commercial-v1",
            "binding_config": {
                "schema_version": "binding-config/1.0",
                "permitted_question_ids": ["SQ-01", "SQ-02"],
                "metric_rules": [],
                "keyword_rules": [],
            },
            "effective_date": "2026-08-29",
            "questions": [
                {
                    "id": "SQ-01",
                    "version": 1,
                    "workstream": "commercial",
                    "title": "How durable is contracted revenue?",
                },
                {
                    "id": "SQ-02",
                    "version": 1,
                    "workstream": "financial",
                    "title": "What is normalized EBITDA?",
                },
            ],
        })
        return lens

    def test_default_lens_and_schema_are_versioned(self):
        validated = validate_fund_lens(DEFAULT_FUND_LENS)
        self.assertEqual(validated["schema_version"], "fund-lens/1.0")
        self.assertEqual(len(validated["questions"]), 20)
        schema = json.loads(
            (PROJECT_ROOT / "vault/policy/fund_lens.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], "fund-lens/1.0")
        response = router.get_fund_lens("scout")
        self.assertEqual(response["source"], "repository_default")
        self.assertEqual(response["active"]["lens_id"], DEFAULT_FUND_LENS["lens_id"])
        capabilities = router.action_capabilities()["actions"]
        self.assertEqual(capabilities["getFundLens"]["method"], "GET")
        self.assertEqual(capabilities["configureFundLens"]["method"], "PUT")

    def test_manual_lens_is_archived_active_and_idempotent(self):
        lens = self._manual_lens()
        first = router.configure_fund_lens("scout", lens)
        second = router.configure_fund_lens("scout", lens)

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(len(first["versions"]), 1)
        self.assertEqual(router.get_fund_lens("scout")["source"], "case_override")
        self.assertTrue((router.VAULT / "deals/scout/fund_lens.json").exists())
        self.assertTrue(
            (router.VAULT / "deals/scout/fund_lenses/FL-SCOUT-MANUAL__1.0.0.json").exists()
        )
        questions = router._load_questions("scout")
        ids = [item["id"] for item in questions]
        self.assertEqual(len(ids), 56)
        self.assertEqual(ids[-2:], ["SQ-01", "SQ-02"])
        self.assertTrue(all(
            item["fund_lens_version"] == "1.0.0"
            for item in questions if item["origin"] == "fund_lens"
        ))
        context = router._make_context("scout", "STATE-SCOUT-CURRENT", "2026-08-29")
        self.assertEqual(context["active_lens_id"], "FL-SCOUT-MANUAL")
        with self.assertRaises(HTTPException) as inactive:
            router.projection("scout", lens_id="FL-NOT-ACTIVE")
        self.assertEqual(inactive.exception.status_code, 409)

    def test_same_version_cannot_be_mutated(self):
        lens = self._manual_lens()
        router.configure_fund_lens("scout", lens)
        changed = copy.deepcopy(lens)
        changed["label"] = "Mutated label"
        with self.assertRaises(HTTPException) as raised:
            router.configure_fund_lens("scout", changed)
        self.assertEqual(raised.exception.status_code, 409)

    def test_new_version_reconciles_active_questions_without_deleting_history(self):
        first = self._manual_lens()
        router.configure_fund_lens("scout", first)
        second = self._manual_lens("1.1.0")
        second["questions"] = [{
            "id": "SQ-02",
            "version": 2,
            "workstream": "financial",
            "title": "What is defensible normalized EBITDA?",
        }]
        second["binding_config"]["permitted_question_ids"] = ["SQ-02"]
        router.configure_fund_lens("scout", second)

        questions = router._load_questions("scout")
        self.assertEqual(len(questions), 55)
        self.assertEqual(questions[-1]["id"], "SQ-02")
        self.assertEqual(questions[-1]["question_version"], 2)
        self.assertEqual(questions[-1]["title"], "What is defensible normalized EBITDA?")
        self.assertTrue((router.VAULT / "deals/scout/questions/sq-01.md").exists())
        self.assertEqual(len(router.get_fund_lens("scout")["versions"]), 2)

    def test_invalid_or_conflicting_manual_lens_is_rejected(self):
        duplicate = self._manual_lens()
        duplicate["questions"][1]["id"] = "SQ-01"
        with self.assertRaises(HTTPException) as invalid:
            router.configure_fund_lens("scout", duplicate)
        self.assertEqual(invalid.exception.status_code, 422)

        q_dir = router.VAULT / "deals/scout/questions"
        q_dir.mkdir(parents=True)
        (q_dir / "sq-01.md").write_text(
            "---\nid: SQ-01\norigin: deal_emergent\n---\n\n# Existing question\n",
            encoding="utf-8",
        )
        with self.assertRaises(HTTPException) as conflict:
            router.configure_fund_lens("scout", self._manual_lens())
        self.assertEqual(conflict.exception.status_code, 409)

    def test_case_profile_can_bind_without_keystone_question_ids_or_rules(self):
        lens = self._manual_lens()
        lens["binding_profile"] = "scout-commercial-v1"
        lens["binding_config"] = {
            "schema_version": "binding-config/1.0",
            "permitted_question_ids": ["SQ-01", "SQ-02"],
            "metric_rules": [{
                "aliases": ["Contracted Revenue", "ARR"],
                "question_ids": ["SQ-01"], "confidence": 0.95, "rank": 10,
            }],
            "keyword_rules": [{
                "pattern": "normaliz(ed|ation) EBITDA",
                "question_ids": ["SQ-02"], "confidence": 0.8, "rank": 20,
            }],
        }
        validated = validate_fund_lens(lens)
        bindings = ranked_bindings(
            {"statement": "The normalized EBITDA is still under review."},
            {"metric": "Contracted Revenue"}, validated,
        )
        self.assertEqual([item["question_id"] for item in bindings], ["SQ-01", "SQ-02"])
        self.assertEqual(bindings[0]["confidence"], 0.95)
        self.assertEqual(bindings[1]["rule"], "keyword")


if __name__ == "__main__":
    unittest.main()
