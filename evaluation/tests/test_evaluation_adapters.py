from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.adapters import ADAPTERS, get_adapter
from evaluation.schema import validate_case


class EvaluationAdapterTests(unittest.TestCase):
    def _adapt(self, adapter_id: str, payload: object, **kwargs) -> list[dict]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            cases = get_adapter(adapter_id).adapt(path, dataset_root=Path(directory), **kwargs)
            for case in cases:
                validate_case(case)
            return cases

    def test_all_registry_adapters_are_installed(self) -> None:
        self.assertEqual(set(ADAPTERS), {
            "native", "office_comprehension", "omnidocbench", "docile", "docvqa",
            "slidevqa", "spreadsheetbench", "spreadsheetbench2", "qaconv",
            "emailsum", "tika_fixtures",
        })

    def test_office_comprehension_adapter(self) -> None:
        cases = self._adapt("office_comprehension", [{
            "id": "w1", "reference_files": ["memo.docx"], "question": "What is approved?",
            "expected_assertions": ["The investment is approved."], "weights": [2],
            "feature": "paragraph_text", "track": "file_fidelity", "app_type": "word",
        }], split="public_test", version="2026")
        self.assertEqual(cases[0]["inputs"][0]["format"], "docx")
        self.assertEqual(cases[0]["gold"]["assertions"][0]["weight"], 2)

    def test_docile_adapter_preserves_bbox_and_line_items(self) -> None:
        cases = self._adapt("docile", {"invoice-1": [{
            "page": 0, "bbox": [0.1, 0.2, 0.3, 0.4], "fieldtype": "amount_total",
            "line_item_id": 2, "text": "42,500",
        }]}, split="validation", version="1.0", options={"track": "LIR"})
        field = cases[0]["gold"]["fields"][0]
        self.assertEqual(field["line_item_id"], 2)
        self.assertEqual(field["locator"]["bbox"], [0.1, 0.2, 0.3, 0.4])

    def test_omnidocbench_adapter_preserves_elements(self) -> None:
        cases = self._adapt("omnidocbench", [{
            "page_info": {"page_id": "p1", "image_path": "p1.jpg", "language": "english"},
            "layout_dets": [{"category_type": "text", "poly": [0, 0, 10, 0, 10, 10, 0, 10],
                             "text": "Approved"}],
        }], split="validation", version="1.7")
        self.assertEqual(cases[0]["gold"]["content"], "Approved")
        self.assertEqual(cases[0]["gold"]["elements"][0]["locator"]["bbox"], [0.0, 0.0, 10.0, 10.0])

    def test_slidevqa_and_qaconv_adapters(self) -> None:
        slide = self._adapt("slidevqa", [{
            "qa_id": "s1", "deck_name": "deck-1", "question": "Largest quarter?",
            "answer": "Q3", "evidence_pages": [2], "reasoning_type": "comparison",
        }], split="validation", version="1")
        self.assertEqual(slide[0]["evidence"][0]["locator"], {"type": "slide", "slide": 2})
        email = self._adapt("qaconv", [{
            "id": "q1", "article_segment_id": "email-3", "question": "Who approved?",
            "answers": ["Maria"],
        }], split="public_test", version="1.1")
        self.assertEqual(email[0]["inputs"][0]["selector"]["article_segment_id"], "email-3")

    def test_docvqa_document_centric_records_expand_questions(self) -> None:
        cases = self._adapt("docvqa", [{
            "doc_id": "report-1", "doc_category": "business_report",
            "page_paths": ["p1.png", "p2.png"],
            "questions": {"question_id": ["q1", "q2"], "question": ["Amount?", "Risk?"]},
            "answers": {"question_id": ["q1", "q2"], "answer": ["42", "low"]},
        }], split="validation", version="2026")
        self.assertEqual([case["test_id"] for case in cases], ["docvqa:q1", "docvqa:q2"])
        self.assertEqual(len(cases[0]["inputs"]), 2)
        self.assertEqual(cases[1]["gold"]["answers"], ["low"])

    def test_spreadsheet_email_and_tika_adapters(self) -> None:
        spreadsheet = self._adapt("spreadsheetbench2", [{
            "id": "s1", "instruction": "Repair the EBITDA formula.",
            "spreadsheet_path": "input.xlsx", "golden_response_path": "gold.xlsx",
            "category": "Financial_Model",
        }], split="public_test", version="2.0")
        self.assertEqual(spreadsheet[0]["benchmark"]["id"], "spreadsheetbench2")
        self.assertEqual(spreadsheet[0]["metrics"], ["native:online_judge"])
        emails = self._adapt("emailsum", [{
            "id": "e1", "thread_path": "thread.json", "summary": "The deal was approved."
        }], split="public_test", version="1.0")
        self.assertEqual(emails[0]["task"], "summarization")
        self.assertEqual(emails[0]["metrics"], ["rouge1", "rouge2", "rouge_l"])
        tika = self._adapt("tika_fixtures", [{
            "id": "m1", "file": "mail.msg", "expected_text": "Hello",
            "expected_metadata": {"subject": "Approval"},
        }], split="smoke", version="4.0.0")
        self.assertEqual(tika[0]["inputs"][0]["format"], "msg")
        self.assertIn("field_f1", tika[0]["metrics"])


if __name__ == "__main__":
    unittest.main()
