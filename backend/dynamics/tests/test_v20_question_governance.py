import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402


class V20QuestionGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_vault = router.VAULT
        self.previous_pipeline_out = router.PIPELINE_OUT
        self.previous_case_pipeline_root = router.CASE_PIPELINE_ROOT
        self.previous_index_db = router.INDEX_DB
        router.VAULT = self.root / "vault"
        router.PIPELINE_OUT = self.root / "pipeline"
        router.CASE_PIPELINE_ROOT = self.root / "cases"
        router.INDEX_DB = self.root / "missing-index.db"
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

    def tearDown(self):
        self.index_patch.stop()
        router.VAULT = self.previous_vault
        router.PIPELINE_OUT = self.previous_pipeline_out
        router.CASE_PIPELINE_ROOT = self.previous_case_pipeline_root
        router.INDEX_DB = self.previous_index_db
        self.temporary.cleanup()

    @staticmethod
    def _claim(claim_id: str, statement: str, metric: str, source_id: str) -> dict:
        return {
            "claim_id": claim_id,
            "statement": statement,
            "metric": metric,
            "source_id": source_id,
            "source_ids": [source_id],
            "locator": "page 1",
            "period": "2026-06-30",
            "perimeter": "Keystone consolidated",
            "epistemic_class": "asserted",
        }

    def test_fund_lens_materializes_versioned_questions_and_drives_binding(self):
        lens = router._active_fund_lens("keystone")
        router._ensure_question_registry("keystone", lens)

        question_paths = sorted((router.VAULT / "deals/keystone/questions").glob("*.md"))
        self.assertEqual(len(question_paths), 20)
        metadata = router._read_frontmatter(question_paths[0])
        self.assertEqual(metadata["origin"], "fund_lens")
        self.assertEqual(metadata["fund_lens_id"], lens["lens_id"])
        self.assertEqual(metadata["fund_lens_version"], lens["version"])

        revenue = self._claim("claim-revenue", "Revenue increased in FY2025", "Revenue", "cim.pdf")
        derived = router._derive_bears_on(
            [revenue],
            {"deal": "keystone", "extraction_metadata": {"compiler_fields_per_claim": [revenue]}},
            lens,
        )
        self.assertEqual(derived[0]["bears_on"], ["Q-04"])

    def test_clean_multi_source_proposals_surface_unbound_topics_without_mutating_current(self):
        lens = router._active_fund_lens("keystone")
        router._ensure_question_registry("keystone", lens)
        bound = self._claim("claim-bound", "FY2025 revenue was 100", "Revenue", "cim.pdf")
        unbound = self._claim(
            "claim-unbound", "Cyber insurance excludes social engineering", "Cyber Insurance", "insurance.pdf"
        )
        e3 = {
            "deal": "keystone",
            "extraction_metadata": {"compiler_fields_per_claim": [bound, unbound]},
        }
        claims = router._derive_bears_on([bound, unbound], e3, lens)
        first = router._write_evidence_proposal("job-cim", "keystone", "cim.pdf", [claims[0]], [], lens)
        question_proposals = router._derive_question_proposals([claims[1]], "keystone")
        second = router._write_evidence_proposal(
            "job-insurance", "keystone", "insurance.pdf", [claims[1]], question_proposals, lens
        )

        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(len(router._load_spine_change_proposals("keystone")), 1)
        preview = router.get_evidence_proposal("keystone", "job-insurance")
        self.assertFalse(preview["semantic_preview"]["current_mutated"])
        self.assertEqual(len(preview["questions"]), 20)
        self.assertFalse((router.PIPELINE_OUT / "current_graph.json").exists())
        self.assertFalse((router.VAULT / "deals/keystone/claims").exists())

    def test_reviewed_claims_can_correct_fields_and_bindings_but_not_provenance(self):
        lens = router._active_fund_lens("keystone")
        router._ensure_question_registry("keystone", lens)
        original = self._claim("claim-1", "Draft statement", "Revenue", "source-a.pdf")
        proposal = {"source_id": "source-a.pdf", "claims": [original]}
        reviewed = router._validated_reviewed_claims(
            "keystone",
            proposal,
            {"claims": [{
                "claim_id": "claim-1",
                "statement": "Reviewed statement",
                "source_id": "forged.pdf",
                "bears_on": ["Q-04", "Q-06"],
            }]},
        )

        self.assertEqual(reviewed[0]["statement"], "Reviewed statement")
        self.assertEqual(reviewed[0]["source_id"], "source-a.pdf")
        self.assertEqual(reviewed[0]["bears_on"], ["Q-04", "Q-06"])
        with self.assertRaises(HTTPException) as invalid:
            router._validated_reviewed_claims(
                "keystone", proposal,
                {"claims": [{"claim_id": "claim-1", "bears_on": ["Q-404"]}]},
            )
        self.assertEqual(invalid.exception.status_code, 422)

    def test_accepting_deal_emergent_question_migrates_pending_binding(self):
        lens = router._active_fund_lens("keystone")
        router._ensure_question_registry("keystone", lens)
        claim = self._claim("claim-cyber", "Cyber policy exclusion", "Cyber Insurance", "insurance.pdf")
        proposal = router._derive_question_proposals([claim], "keystone")[0]
        router._write_evidence_proposal(
            "job-cyber", "keystone", "insurance.pdf", [claim], [proposal], lens
        )
        proposal.update(evidence_job_id="job-cyber")

        result = router._accept_spine_change("keystone", proposal)

        self.assertTrue(result["question_created"])
        question_id = result["question_id"]
        question_path = router.VAULT / "deals/keystone/questions" / f"{question_id.lower()}.md"
        self.assertEqual(router._read_frontmatter(question_path)["origin"], "deal_emergent")
        evidence = json.loads(router._proposal_path("job-cyber", "keystone").read_text())
        self.assertEqual(evidence["claims"][0]["bears_on"], [question_id])


if __name__ == "__main__":
    unittest.main()
