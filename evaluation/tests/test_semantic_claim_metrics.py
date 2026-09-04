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
from evaluation.semantic_validation import validate_semantic_integrity


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evaluation" / "fixtures" / "semantic_cases"
PREDICTIONS = ROOT / "evaluation" / "fixtures" / "semantic_predictions" / "oracle.ndjson"


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
        self.assertEqual(len(self.cases), 11)
        for case in self.cases.values():
            validate_case(case)
            validate_prediction(self.predictions[case["test_id"]])
            for item in case["inputs"]:
                path = ROOT / item["path"]
                self.assertTrue(path.is_file(), f"missing fixture: {path}")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
            self.assertEqual(validate_semantic_integrity(case, asset_root=ROOT, inspect_files=True), [])

    def test_semantic_gold_integrity_detects_broken_graph_quote_and_arithmetic(self) -> None:
        case, _prediction = self.case_and_prediction("entity-resolution.concentration-002")
        derived = next(
            claim for claim in case["gold"]["claims"]
            if claim["claim_id"] == "G-ACME-CONCENTRATION"
        )
        derived["source_quote"] = "This sentence does not occur in the document."
        derived["derivation"]["expression"] = "7.0 / 70.0 * 10"
        derived["derivation"]["operand_claim_ids"] = ["G-DOES-NOT-EXIST"]
        findings = validate_semantic_integrity(case, asset_root=ROOT, inspect_files=True)
        self.assertTrue(any("quote is not present" in finding for finding in findings))
        self.assertTrue(any("unknown derivation operands" in finding for finding in findings))
        self.assertTrue(any("do not match DERIVED_FROM" in finding for finding in findings))
        self.assertTrue(any("derivation evaluates" in finding for finding in findings))

    def test_oracle_contract_scores_one_without_reusing_gold_claim_ids(self) -> None:
        run = EvaluationRunner().run(list(self.cases.values()), predictions_path=PREDICTIONS)
        self.assertEqual(run["summary"]["overall"]["tests"], 11)
        self.assertEqual(run["summary"]["overall"]["passed"], 11)
        self.assertEqual(run["summary"]["overall"]["mean_score"], 1.0)
        self.assertEqual(run["summary"]["by_tag"]["restatement"]["tests"], 1)
        self.assertEqual(run["summary"]["by_tag"]["derivation"]["tests"], 2)
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

    def test_restatement_edges_are_not_implied_by_equal_concepts(self) -> None:
        case, prediction = self.case_and_prediction("conflict.restatement-002")
        prediction["relations"] = [
            relation for relation in prediction["relations"]
            if relation["relation"] != "CONTRADICTS"
        ]
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertLess(score_metric("semantic_relation_f1", case, prediction), 1.0)

    def test_covenant_threshold_requires_bound_and_rejects_drafting_example(self) -> None:
        case, prediction = self.case_and_prediction("covenant.bounds-002")
        leverage = next(
            claim for claim in prediction["claims"] if claim["claim_id"] == "P-HARBOR-LEVERAGE"
        )
        leverage["bound"] = "EXACT"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_bound_accuracy", case, prediction), 2 / 3)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 2 / 3)

        illustrative = copy.deepcopy(leverage)
        illustrative.update({
            "claim_id": "P-HARBOR-ILLUSTRATIVE",
            "statement": "Project Harbor has a 6.00x covenant.",
            "source_quote": "The 6.00x ratio shown in the drafting example is illustrative only and is not an operative covenant.",
            "value": 6.0,
        })
        prediction["claims"].append(illustrative)
        self.assertEqual(score_metric("semantic_claim_precision", case, prediction), 3 / 4)

    def test_forecast_scenarios_cannot_be_collapsed(self) -> None:
        case, prediction = self.case_and_prediction("forecast.scenarios-002")
        for claim in prediction["claims"]:
            if claim["metric"] == "Revenue":
                claim["scenario"] = "base"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_scenario_accuracy", case, prediction), 2 / 4)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 2 / 4)

    def test_similar_customer_name_does_not_override_ultimate_parent(self) -> None:
        case, prediction = self.case_and_prediction("entity-resolution.concentration-002")
        europa = next(claim for claim in prediction["claims"] if claim["claim_id"] == "P-EUROPA-201")
        europa["entity"] = "Acme Holdings"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_entity_accuracy", case, prediction), 7 / 8)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 7 / 8)

    def test_units_ranges_and_bounds_are_scored_independently(self) -> None:
        case, prediction = self.case_and_prediction("values.units-and-ranges-002")
        aliases = copy.deepcopy(prediction)
        for claim in aliases["claims"]:
            if claim["unit"] == "EURm":
                claim["unit"] = "€m"
            elif claim["unit"] == "%":
                claim["unit"] = "percent"
        self.assertEqual(score_metric("semantic_unit_accuracy", case, aliases), 1.0)
        self.assertEqual(score_metric("semantic_exact_match", case, aliases), 1.0)

        margin = next(claim for claim in prediction["claims"] if claim["claim_id"] == "P-VALE-MARGIN")
        debt = next(claim for claim in prediction["claims"] if claim["claim_id"] == "P-VALE-NET-DEBT")
        revenue = next(claim for claim in prediction["claims"] if claim["claim_id"] == "P-VALE-REVENUE")
        margin["value"] = [31.0, 34.0]
        debt["bound"] = "EXACT"
        revenue["unit"] = "USDm"
        self.assertEqual(score_metric("semantic_scalar_accuracy", case, prediction), 3 / 4)
        self.assertEqual(score_metric("semantic_bound_accuracy", case, prediction), 3 / 4)
        self.assertEqual(score_metric("semantic_unit_accuracy", case, prediction), 3 / 4)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 1 / 4)

    def test_consolidated_standalone_and_segment_perimeters_cannot_be_collapsed(self) -> None:
        case, prediction = self.case_and_prediction("identity.perimeters-003")
        for claim in prediction["claims"]:
            claim["scope"] = "consolidated"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_scope_accuracy", case, prediction), 1 / 3)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 1 / 3)

    def test_fiscal_quarter_and_ltm_periods_cannot_be_collapsed(self) -> None:
        case, prediction = self.case_and_prediction("identity.periods-003")
        for claim in prediction["claims"]:
            claim["period_canonical"] = "FY2025A"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_period_accuracy", case, prediction), 1 / 3)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 1 / 3)

    def test_competing_views_require_basis_and_epistemic_attribution(self) -> None:
        case, prediction = self.case_and_prediction("attribution.competing-views-003")
        for claim in prediction["claims"]:
            claim["basis"] = "SellerView"
            claim["epistemic_class"] = "asserted"
        self.assertEqual(score_metric("semantic_claim_f1", case, prediction), 1.0)
        self.assertEqual(score_metric("semantic_basis_accuracy", case, prediction), 1 / 3)
        self.assertEqual(score_metric("semantic_epistemic_accuracy", case, prediction), 1 / 3)
        self.assertEqual(score_metric("semantic_exact_match", case, prediction), 1 / 3)


if __name__ == "__main__":
    unittest.main()
