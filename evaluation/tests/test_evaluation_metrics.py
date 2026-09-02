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
