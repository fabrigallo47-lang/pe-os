from __future__ import annotations

import copy
import hashlib
import unittest
from pathlib import Path

from evaluation.evaluator import evaluate_case
from evaluation.io import read_cases, read_records
from evaluation.metrics import score_metric
from evaluation.runner import EvaluationRunner
from evaluation.schema import validate_case, validate_prediction


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evaluation" / "fixtures" / "semantic_cases"
PREDICTIONS = ROOT / "evaluation" / "fixtures" / "semantic_predictions" / "perfect.json"


class SemanticClaimMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = {case["test_id"]: case for case in read_cases(CASES)}
        cls.predictions = {
            prediction["test_id"]: prediction for prediction in read_records(PREDICTIONS)
        }

    def case_and_prediction(self, suffix: str) -> tuple[dict, dict]:
        test_id = next(test_id for test_id in self.cases if test_id.endswith(suffix))
        return copy.deepcopy(self.cases[test_id]), copy.deepcopy(self.predictions[test_id])

    def test_semantic_fixtures_validate_and_are_hash_locked(self) -> None:
        self.assertEqual(len(self.cases), 3)
        for case in self.cases.values():
            validate_case(case)
            validate_prediction(self.predictions[case["test_id"]])
            for item in case["inputs"]:
                path = ROOT / item["path"]
                self.assertTrue(path.is_file(), f"missing fixture: {path}")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

    def test_oracle_contract_scores_one_without_reusing_gold_claim_ids(self) -> None:
        run = EvaluationRunner().run(list(self.cases.values()), predictions_path=PREDICTIONS)
        self.assertEqual(run["summary"]["overall"]["tests"], 3)
        self.assertEqual(run["summary"]["overall"]["passed"], 3)
        self.assertEqual(run["summary"]["overall"]["mean_score"], 1.0)
        case, prediction = self.case_and_prediction("identity-and-derivation-001")
        self.assertNotEqual(case["gold"]["claims"][0]["claim_id"], prediction["claims"][0]["claim_id"])
        self.assertEqual(score_metric("semantic_relation_f1", case, prediction), 1.0)

        # Extractor-local IDs are deliberately not evaluator identities.
        for index, claim in enumerate(prediction["claims"]):
            claim["source_id"] = f"PREDICTED-SOURCE-{index}"
        self.assertEqual(score_metric("semantic_grounding_accuracy", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 1.0)

    def test_wrong_economic_basis_keeps_detection_but_fails_semantics(self) -> None:
        case, prediction = self.case_and_prediction("identity-and-derivation-001")
        firm = next(claim for claim in prediction["claims"] if claim["claim_id"] == "P-EBITDA-FIRM")
        firm["basis"] = "SellerView"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_basis_accuracy", case, prediction), 15 / 16)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 15 / 16)
        self.assertLess(score_metric("semantic_critical_exact_match", case, prediction), 1.0)

    def test_missing_and_hallucinated_claims_change_recall_and_precision(self) -> None:
        case, prediction = self.case_and_prediction("identity-and-derivation-001")
        missing = copy.deepcopy(prediction)
        missing["claims"] = missing["claims"][:-1]
        self.assertEqual(score_metric("semantic_claim_recall", case, missing), 15 / 16)

        extra = copy.deepcopy(prediction["claims"][0])
        extra.update({
            "claim_id": "P-HALLUCINATION",
            "statement": "Alderstone had 74 employees.",
            "source_id": "SRC-NOT-PRESENT",
            "source_quote": "Alderstone had 74 employees.",
            "locator": {"type": "generic", "value": "invented"},
            "metric": "EmployeeCount",
            "measurement": "headcount",
            "unit": "people",
        })
        prediction["claims"].append(extra)
        self.assertEqual(score_metric("semantic_claim_precision", case, prediction), 16 / 17)
        self.assertLess(score_metric("semantic_claim_f1", case, prediction), 1.0)

    def test_equal_value_with_unrelated_meaning_does_not_align(self) -> None:
        case, prediction = self.case_and_prediction("identity-and-derivation-001")
        unrelated = copy.deepcopy(prediction["claims"][0])
        unrelated.update({
            "claim_id": "P-UNRELATED",
            "statement": "Alderstone had 74 employees.",
            "source_id": "SRC-UNRELATED",
            "source_quote": "Alderstone had 74 employees.",
            "locator": {"type": "generic", "value": "unrelated"},
            "entity": "Alderstone Workforce",
            "metric": "EmployeeCount",
            "measurement": "headcount",
            "unit": "people",
        })
        one_claim_case = copy.deepcopy(case)
        one_claim_case["gold"]["claims"] = [case["gold"]["claims"][0]]
        one_claim_case["gold"]["relations"] = []
        one_claim_prediction = {**prediction, "claims": [unrelated], "relations": []}
        self.assertEqual(score_metric("semantic_claim_recall", one_claim_case, one_claim_prediction), 0.0)
        self.assertEqual(score_metric("semantic_claim_precision", one_claim_case, one_claim_prediction), 0.0)

    def test_derivation_requires_the_correct_operands(self) -> None:
        case, prediction = self.case_and_prediction("identity-and-derivation-001")
        derived = next(
            claim for claim in prediction["claims"] if claim["claim_id"] == "P-RIV-CONCENTRATION"
        )
        derived["derivation"]["operand_claim_ids"] = ["P-RIV-TOTAL", "P-EBITDA-REPORTED"]
        self.assertEqual(score_metric("semantic_derivation_accuracy", case, prediction), 0.0)

    def test_marketing_language_requires_abstention(self) -> None:
        case, prediction = self.case_and_prediction("marketing.abstention-001")
        keystone_claim = copy.deepcopy(
            self.predictions["panta-semantic.keystone.identity-and-derivation-001"]["claims"][0]
        )
        keystone_claim.update({
            "claim_id": "P-MARKETING-HALLUCINATION",
            "input_id": "marketing-only",
            "source_id": "SRC-MARKETING",
            "locator": {"type": "generic", "value": "panta_semantic_marketing_only.md"},
        })
        prediction["claims"] = [keystone_claim]
        self.assertEqual(score_metric("semantic_abstention_accuracy", case, prediction), 0.0)
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 0.0)

    def test_future_source_is_leakage_even_if_claim_omits_known_at(self) -> None:
        case, prediction = self.case_and_prediction("temporal.as-of-001")
        future = copy.deepcopy(prediction["claims"][0])
        future.update({
            "claim_id": "P-ATLAS-FUTURE",
            "statement": "Project Atlas FY2026 YTD revenue was $21.0 million.",
            "source_id": "SRC-ATLAS-Q1",
            "input_id": "atlas-future",
            "locator": {"type": "generic", "value": "panta_semantic_future_update.md"},
            "source_quote": "On 15 April 2026, the Q1 update reported FY2026 year-to-date consolidated revenue of $21.0 million.",
            "value": 21.0,
            "period": "FY2026YTD",
            "period_canonical": "FY2026YTD",
        })
        future.pop("known_at", None)
        prediction["claims"].append(future)
        self.assertEqual(score_metric("semantic_no_temporal_leakage", case, prediction), 0.5)


if __name__ == "__main__":
    unittest.main()
