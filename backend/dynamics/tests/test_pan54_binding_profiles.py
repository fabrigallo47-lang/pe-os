import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from tools.bind_questions_e3 import (  # noqa: E402
    BindingProfileReviewBlocker,
    DEFAULT_FUND_LENS,
    load_fund_lens,
    ranked_bindings,
    review_blocked_result,
)


GROWTH_LENS_PATH = (
    PROJECT_ROOT / "vault" / "policy" / "fund_lens_growth_equity_v1.json"
)


class Pan54BindingProfileTests(unittest.TestCase):
    def test_schema_and_keystone_rules_are_complete_versioned_configuration(self):
        schema = json.loads(
            (PROJECT_ROOT / "vault/policy/fund_lens.schema.json").read_text(
                encoding="utf-8"
            )
        )
        binding_schema = schema["properties"]["binding_config"]
        self.assertIn("binding_config", schema["required"])
        self.assertEqual(
            set(binding_schema["required"]),
            {
                "schema_version",
                "permitted_question_ids",
                "metric_rules",
                "keyword_rules",
            },
        )
        self.assertEqual(
            set(schema["$defs"]["metricRule"]["required"]),
            {"aliases", "question_ids", "confidence", "rank"},
        )
        self.assertEqual(
            set(schema["$defs"]["keywordRule"]["required"]),
            {"pattern", "question_ids", "confidence", "rank"},
        )

        lens = load_fund_lens()
        config = lens["binding_config"]
        self.assertEqual(config["schema_version"], "binding-config/1.0")
        self.assertEqual(
            set(config["permitted_question_ids"]),
            {question["id"] for question in lens["questions"]},
        )
        self.assertGreater(len(config["metric_rules"]), 10)
        self.assertGreater(len(config["keyword_rules"]), 20)

    def test_two_archetype_lenses_bind_same_claim_differently_without_code_branch(self):
        growth_lens = load_fund_lens(GROWTH_LENS_PATH)
        claim = {
            "claim_id": "claim-shared",
            "statement": "Revenue increased while retention remained stable.",
        }
        compiler_meta = {"metric": "Revenue"}

        keystone = ranked_bindings(claim, compiler_meta, DEFAULT_FUND_LENS)
        growth = ranked_bindings(claim, compiler_meta, growth_lens)

        self.assertEqual([item["question_id"] for item in keystone], ["Q-04"])
        self.assertEqual(
            [item["question_id"] for item in growth],
            ["GE-Q-02", "GE-Q-01"],
        )
        self.assertEqual(growth[0]["confidence"], 0.96)
        self.assertEqual(growth[0]["rank"], 10)

    def test_runtime_binding_uses_active_case_lens_and_proposes_unbound_evidence(self):
        growth_lens = load_fund_lens(GROWTH_LENS_PATH)
        previous_vault = router.VAULT
        with tempfile.TemporaryDirectory() as temporary:
            router.VAULT = Path(temporary) / "vault"
            try:
                router.configure_fund_lens("growth-case", growth_lens)
                claim = {
                    "claim_id": "claim-growth",
                    "statement": "Revenue increased while retention remained stable.",
                    "metric": "Revenue",
                    "source_id": "board-pack.pdf",
                }
                unbound = {
                    "claim_id": "claim-patent",
                    "statement": "The patent opposition hearing is scheduled.",
                    "metric": "Patent Opposition",
                    "source_id": "legal-memo.pdf",
                }
                e3 = {
                    "deal": "growth-case",
                    "extraction_metadata": {
                        "compiler_fields_per_claim": [claim, unbound]
                    },
                }

                derived = router._derive_bears_on([claim, unbound], e3)
                proposals = router._derive_question_proposals(
                    derived,
                    "growth-case",
                )
            finally:
                router.VAULT = previous_vault

        self.assertEqual(derived[0]["bears_on"], ["GE-Q-02", "GE-Q-01"])
        self.assertEqual(derived[1]["bears_on"], [])
        self.assertEqual(derived[1]["statement"], unbound["statement"])
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["status"], "PENDING_REVIEW")
        self.assertEqual(
            proposals[0]["binding_migration"]["claim_ids"],
            ["claim-patent"],
        )

    def test_missing_profile_is_an_explicit_machine_readable_review_blocker(self):
        missing = copy.deepcopy(DEFAULT_FUND_LENS)
        missing.pop("binding_config")

        with self.assertRaises(BindingProfileReviewBlocker) as raised:
            ranked_bindings(
                {"statement": "Revenue increased"},
                {"metric": "Revenue"},
                missing,
            )

        blocker = raised.exception.as_dict()
        self.assertEqual(blocker["status"], "REVIEW_BLOCKED")
        self.assertEqual(blocker["reason_code"], "BINDING_PROFILE_MISSING")
        self.assertEqual(blocker["profile_id"], "keystone-e3-v1")
        self.assertEqual(
            blocker["required_action"],
            "CONFIGURE_VALID_FUND_LENS_BINDING_PROFILE",
        )

        evidence = {
            "manifest_id": "manifest-1",
            "deal": "example",
            "claims": [{
                "claim_id": "claim-1",
                "statement": "Evidence survives the policy stop.",
                "source_id": "source.pdf",
                "locator": "page 4",
            }],
        }
        blocked_result = review_blocked_result(evidence, raised.exception)
        self.assertEqual(blocked_result["unbound_evidence"], evidence["claims"])
        self.assertEqual(blocked_result["bindings"][0]["question_ids"], [])
        self.assertFalse(
            blocked_result["deal_emergent_question_policy"][
                "automatic_question_creation"
            ]
        )

    def test_v20_persists_unbound_evidence_and_review_blocker_without_case_lens(self):
        previous_vault = router.VAULT
        previous_case_pipeline_root = router.CASE_PIPELINE_ROOT
        claim = {
            "claim_id": "claim-no-profile",
            "statement": "Evidence remains intact at the governed boundary.",
            "source_id": "memo.txt",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            router.VAULT = root / "vault"
            router.CASE_PIPELINE_ROOT = root / "pipeline_out" / "cases"
            try:
                derived, lens, blockers = router._bind_extracted_claims(
                    "unconfigured-case",
                    [claim],
                    {"deal": "unconfigured-case"},
                )
                proposal_path = router._write_evidence_proposal(
                    "job-no-profile",
                    "unconfigured-case",
                    "memo.txt",
                    derived,
                    review_blockers=blockers,
                )
                proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                materialized_questions = list(
                    (router.VAULT / "deals/unconfigured-case/questions").glob("*.md")
                )
            finally:
                router.VAULT = previous_vault
                router.CASE_PIPELINE_ROOT = previous_case_pipeline_root

        self.assertIsNone(lens)
        self.assertEqual(derived[0]["statement"], claim["statement"])
        self.assertEqual(derived[0]["bears_on"], [])
        self.assertEqual(derived[0]["binding_evidence"], [])
        self.assertEqual(blockers[0]["reason_code"], "BINDING_PROFILE_MISSING")
        self.assertEqual(proposal["status"], "REVIEW_BLOCKED")
        self.assertEqual(proposal["review_blockers"], blockers)
        self.assertEqual(proposal["question_proposals"], [])
        self.assertEqual(len(materialized_questions), 54)

    def test_invalid_profile_cannot_bind_to_question_outside_its_permitted_set(self):
        invalid = copy.deepcopy(DEFAULT_FUND_LENS)
        invalid["binding_config"]["metric_rules"][0]["question_ids"] = ["Q-20"]
        invalid["binding_config"]["permitted_question_ids"].remove("Q-20")

        with self.assertRaises(BindingProfileReviewBlocker) as raised:
            ranked_bindings({}, {"metric": "Customer Concentration"}, invalid)

        blocker = raised.exception.as_dict()
        self.assertEqual(blocker["reason_code"], "BINDING_PROFILE_INVALID")
        self.assertIn("not permitted", blocker["detail"])

    def test_missing_lens_file_is_review_blocked_instead_of_opaque_io_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            absent = Path(temporary) / "absent-fund-lens.json"
            with self.assertRaises(BindingProfileReviewBlocker) as raised:
                load_fund_lens(absent)

        blocker = raised.exception.as_dict()
        self.assertEqual(blocker["reason_code"], "BINDING_PROFILE_MISSING")
        self.assertEqual(blocker["profile_path"], str(absent))

    def test_unmatched_evidence_remains_unbound_and_unmodified(self):
        growth_lens = load_fund_lens(GROWTH_LENS_PATH)
        claim = {
            "claim_id": "claim-unbound",
            "statement": "The patent opposition hearing is scheduled.",
            "source_id": "legal-memo.pdf",
        }
        before = copy.deepcopy(claim)

        self.assertEqual(
            ranked_bindings(claim, {"metric": "Patent Opposition"}, growth_lens),
            [],
        )
        self.assertEqual(claim, before)


if __name__ == "__main__":
    unittest.main()
