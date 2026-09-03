from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation.runner import EvaluationRunError, EvaluationRunner
from evaluation.tests.test_evaluation_schema import valid_case


class EvaluationRunnerTests(unittest.TestCase):
    def test_saved_predictions_and_filters(self) -> None:
        case = valid_case()
        prediction = {
            "schema_version": "panta-eval.prediction/1.0", "test_id": case["test_id"],
            "status": "success", "fields": case["gold"]["fields"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.ndjson"
            path.write_text(json.dumps(prediction) + "\n", encoding="utf-8")
            run = EvaluationRunner().run([case], predictions_path=path, families={"document"})
        self.assertEqual(run["summary"]["overall"]["passed"], 1)

    def test_command_protocol_does_not_leak_gold(self) -> None:
        case = valid_case()
        case["task"] = "semantic_qa"
        case["query"] = "What is the status?"
        case["gold"] = {"answer": "approved"}
        case["metrics"] = ["answer_exact_match"]
        helper = Path(__file__).with_name("fixture_system.py")
        run = EvaluationRunner().run([case], system_command=f"{sys.executable} {helper}")
        self.assertEqual(run["summary"]["overall"]["passed"], 1)

    def test_requires_exactly_one_prediction_source(self) -> None:
        with self.assertRaises(EvaluationRunError):
            EvaluationRunner().run([valid_case()])


if __name__ == "__main__":
    unittest.main()
