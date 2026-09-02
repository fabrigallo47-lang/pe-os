from __future__ import annotations

import hashlib
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from evaluation.evaluator import evaluate_case
from evaluation.io import read_cases
from evaluation.runner import EvaluationRunner


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evaluation" / "fixtures" / "cases"
PREDICTIONS = ROOT / "evaluation" / "fixtures" / "predictions" / "perfect.ndjson"


class EvaluationFixtureTests(unittest.TestCase):
    def test_gold_files_are_present_and_hash_locked(self) -> None:
        cases = read_cases(CASES)
        formats = {item["format"] for case in cases for item in case["inputs"]}
        self.assertTrue({"pdf", "docx", "pptx", "xlsx", "eml", "png"}.issubset(formats))
        for case in cases:
            for item in case["inputs"]:
                path = ROOT / item["path"]
                self.assertTrue(path.is_file(), f"missing fixture: {path}")
                if item.get("sha256"):
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

    def test_email_fixture_has_pdf_and_image_attachments(self) -> None:
        path = ROOT / "evaluation" / "fixtures" / "documents" / "panta_approval.eml"
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        self.assertEqual(message["Subject"], "Project Aurora - approval details")
        self.assertEqual(
            [part.get_filename() for part in message.iter_attachments()],
            ["panta_investment_report.pdf", "panta_test_visual.png"],
        )

    def test_office_and_pdf_containers_have_expected_native_parts(self) -> None:
        documents = ROOT / "evaluation" / "fixtures" / "documents"
        with ZipFile(documents / "panta_acquisition_review.docx") as archive:
            names = set(archive.namelist())
            self.assertIn("word/document.xml", names)
            self.assertTrue(any(name.startswith("word/media/") for name in names))
        with ZipFile(documents / "panta_revenue_review.pptx") as archive:
            names = set(archive.namelist())
            self.assertIn("ppt/slides/slide1.xml", names)
            self.assertTrue(any("/charts/chart" in name for name in names))
        with ZipFile(documents / "panta_financial_model.xlsx") as archive:
            names = set(archive.namelist())
            self.assertIn("xl/worksheets/sheet1.xml", names)
            self.assertTrue(any("/charts/chart" in name for name in names))
            worksheet = archive.read("xl/worksheets/sheet1.xml")
            self.assertIn(b"<x:f>B4-B5</x:f>", worksheet)
            self.assertIn(b"<x:v>45</x:v>", worksheet)
        self.assertTrue((documents / "panta_investment_report.pdf").read_bytes().startswith(b"%PDF-"))

    def test_oracle_predictions_are_a_perfect_contract_check(self) -> None:
        run = EvaluationRunner().run(read_cases(CASES), predictions_path=PREDICTIONS)
        self.assertEqual(run["summary"]["overall"]["tests"], 8)
        self.assertEqual(run["summary"]["overall"]["passed"], 8)
        self.assertEqual(run["summary"]["overall"]["mean_score"], 1.0)

    def test_deliberately_degraded_prediction_fails_the_gate(self) -> None:
        case = read_cases(CASES)[0]
        with self.subTest(test_id=case["test_id"]):
            prediction = {
                "schema_version": "panta-eval.prediction/1.0",
                "test_id": case["test_id"],
                "status": "success",
                "content": "unrelated output",
            }
            result = evaluate_case(case, prediction)
            self.assertFalse(result["passed"])
            self.assertLess(result["score"], result["threshold"])


if __name__ == "__main__":
    unittest.main()
