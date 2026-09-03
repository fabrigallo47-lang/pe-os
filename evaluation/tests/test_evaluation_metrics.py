from __future__ import annotations

import unittest

from evaluation.evaluator import evaluate_case
from evaluation.metrics import bbox_iou, normalized_edit_similarity, score_metric, token_f1, values_equal
from evaluation.tests.test_evaluation_schema import valid_case


class EvaluationMetricTests(unittest.TestCase):
    def test_text_and_numeric_normalization(self) -> None:
        self.assertTrue(values_equal("EUR 42,500", 42500))
        self.assertTrue(values_equal("1.250,5", "1250.5"))
        self.assertEqual(token_f1("alpha beta", "beta alpha"), 1.0)
        self.assertGreater(normalized_edit_similarity("Revenue 125", "revenue 125"), 0.99)

    def test_bbox_iou(self) -> None:
        self.assertEqual(bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(bbox_iou([0, 0, 1, 1], [2, 2, 3, 3]), 0.0)

    def test_rouge_metrics_support_multiple_references(self) -> None:
        case = valid_case()
        case["gold"] = {"answers": ["The deal was rejected.", "The deal was approved."]}
        prediction = {"answer": "The deal was approved."}
        self.assertEqual(score_metric("rouge1", case, prediction), 1.0)
        self.assertEqual(score_metric("rouge2", case, prediction), 1.0)
        self.assertEqual(score_metric("rouge_l", case, prediction), 1.0)

    def test_field_and_grounding_score(self) -> None:
        case = valid_case()
        case["metrics"] = ["field_precision", "field_recall", "field_f1", "evidence_f1"]
        prediction = {
            "schema_version": "panta-eval.prediction/1.0",
            "test_id": case["test_id"], "status": "success",
            "fields": case["gold"]["fields"], "evidence": case["evidence"],
        }
        result = evaluate_case(case, prediction)
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)

    def test_information_profile_ignores_shape_and_unannotated_extra_facts(self) -> None:
        case = valid_case()
        case["evaluation_profile"] = "information_graph"
        case["gold"] = {
            "coverage": "subset",
            "fields": [
                {"name": "revenue_eur_m", "value": 125, "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B4"}},
                {"name": "cost_eur_m", "value": 80, "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B5"}},
                {"name": "ebitda_eur_m", "value": 45, "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B6"}},
                {"name": "risk", "value": "LOW", "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B7"}},
                {"name": "decision_owner", "value": "Maria Rossi", "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B8"}},
                {"name": "decision_date", "value": "2026-08-15", "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B9"}},
            ],
        }
        case["metrics"] = [
            "information_recall", "fact_value_accuracy",
            "fact_grounding_accuracy", "status_accuracy",
        ]
        case["diagnostic_metrics"] = ["field_precision", "field_recall", "field_f1"]
        prediction = {
            "schema_version": "panta-eval.prediction/1.0",
            "test_id": case["test_id"],
            "status": "success",
            "fields": [
                {"name": "Revenue (EUR m)", "value": 125, "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B4"}},
                {"name": "Cost (EUR m)", "value": 80, "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B5"}},
                {"name": "EBITDA (EUR m)", "value": 45, "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B6"}},
                {"name": "Risk", "value": "LOW", "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B7"}},
                {"name": "Decision owner", "value": "Maria Rossi", "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B8"}},
                {"name": "Decision date", "value": "2026-08-15", "input_id": "doc",
                 "locator": {"type": "cell", "sheet": "Summary", "range": "B9"}},
                {"name": "Q1 Revenue (EUR m)", "value": 10},
                {"name": "Q2 Revenue (EUR m)", "value": 15},
                {"name": "Q3 Revenue (EUR m)", "value": 22},
            ],
        }
        result = evaluate_case(case, prediction)
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["scores"]["information_recall"], 1.0)
        self.assertEqual(result["scores"]["fact_value_accuracy"], 1.0)
        self.assertEqual(result["scores"]["fact_grounding_accuracy"], 1.0)
        self.assertAlmostEqual(result["scores"]["field_recall"], 1 / 6, places=6)
        self.assertAlmostEqual(result["scores"]["field_precision"], 1 / 9, places=6)
        self.assertEqual(result["details"]["diagnostic_metrics"], case["diagnostic_metrics"])

    def test_explicit_fact_aliases_match_but_unrelated_equal_values_do_not(self) -> None:
        case = valid_case()
        case["gold"] = {
            "coverage": "subset",
            "facts": [{
                "fact_id": "company.revenue.fy2025",
                "subject": "company",
                "predicate": "revenue",
                "aliases": ["turnover"],
                "value": 125,
                "unit": "EUR m",
                "qualifiers": {"period": "FY2025"},
            }],
        }
        matching = {
            "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
            "status": "success", "facts": [{
                "subject": "company", "predicate": "turnover", "value": 125,
                "unit": "EUR_m", "qualifiers": {"period": "FY2025"},
            }, {"predicate": "employee_count", "value": 20}],
        }
        unrelated = {
            "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
            "status": "success", "facts": [{"predicate": "cost", "value": 125}],
        }
        self.assertEqual(score_metric("information_recall", case, matching), 1.0)
        self.assertEqual(score_metric("fact_precision", case, matching), 1.0)
        self.assertEqual(score_metric("information_recall", case, unrelated), 0.0)

    def test_information_recall_rejects_a_wrong_value(self) -> None:
        case = valid_case()
        case["gold"]["coverage"] = "subset"
        prediction = {
            "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
            "status": "success", "fields": [{
                "name": "Total", "value": 41,
                "locator": {"type": "page", "page": 1, "index_base": 1},
            }],
        }
        self.assertEqual(score_metric("fact_value_accuracy", case, prediction), 0.0)
        self.assertEqual(score_metric("information_recall", case, prediction), 0.0)

    def test_exhaustive_gold_penalizes_extra_facts(self) -> None:
        case = valid_case()
        case["gold"]["coverage"] = "exhaustive"
        prediction = {
            "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
            "status": "success", "fields": [
                *case["gold"]["fields"],
                {"name": "unrequested", "value": "extra"},
            ],
        }
        self.assertEqual(score_metric("fact_precision", case, prediction), 0.5)

    def test_source_locator_can_align_a_presentation_specific_label(self) -> None:
        case = valid_case()
        case["gold"]["coverage"] = "subset"
        prediction = {
            "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
            "status": "success", "facts": [{
                "predicate": "invoice grand amount", "value": 42,
                "locator": {"type": "page", "page": 1, "index_base": 1},
            }],
        }
        self.assertEqual(score_metric("information_recall", case, prediction), 1.0)
        self.assertEqual(score_metric("fact_grounding_accuracy", case, prediction), 1.0)

    def test_missing_prediction_is_a_stable_failure(self) -> None:
        result = evaluate_case(valid_case(), None)
        self.assertEqual(result["status"], "missing_prediction")
        self.assertFalse(result["passed"])

    def test_expected_abstention_passes(self) -> None:
        case = valid_case()
        case["task"] = "abstention"
        case["gold"] = {"expected_status": "abstained", "unanswerable": True}
        case["metrics"] = ["status_accuracy"]
        prediction = {
            "schema_version": "panta-eval.prediction/1.0",
            "test_id": case["test_id"], "status": "abstained",
        }
        self.assertTrue(evaluate_case(case, prediction)["passed"])


if __name__ == "__main__":
    unittest.main()
