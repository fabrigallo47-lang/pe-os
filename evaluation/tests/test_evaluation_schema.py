from __future__ import annotations

import unittest

from evaluation.schema import SchemaValidationError, validate_case, validate_prediction


def valid_case() -> dict:
    return {
        "schema_version": "panta-eval.case/1.0",
        "test_id": "fixture:pdf:1",
        "benchmark": {"id": "fixture", "version": "1", "original_id": "1"},
        "split": "smoke",
        "task": "field_extraction",
        "inputs": [{
            "input_id": "doc", "family": "document", "format": "pdf",
            "path": "fixture.pdf", "role": "primary",
        }],
        "query": None,
        "gold": {"fields": [{
            "name": "total", "value": 42,
            "locator": {"type": "page", "page": 1, "index_base": 1},
        }]},
        "evidence": [{
            "input_id": "doc", "locator": {"type": "page", "page": 1, "index_base": 1},
            "role": "answer",
        }],
        "metrics": ["field_f1"],
        "tags": ["fixture"],
    }


class EvaluationSchemaTests(unittest.TestCase):
    def test_accepts_canonical_case_and_prediction(self) -> None:
        case = valid_case()
        validate_case(case)
        validate_prediction({
            "schema_version": "panta-eval.prediction/1.0",
            "test_id": case["test_id"],
            "status": "success",
            "fields": case["gold"]["fields"],
        })

    def test_rejects_unknown_format_and_reports_json_path(self) -> None:
        case = valid_case()
        case["inputs"][0]["format"] = "wordish"
        with self.assertRaises(SchemaValidationError) as raised:
            validate_case(case)
        self.assertIn("$.inputs[0].format", str(raised.exception))

    def test_rejects_locator_with_extra_properties(self) -> None:
        case = valid_case()
        case["evidence"][0]["locator"]["slide"] = 2
        with self.assertRaises(SchemaValidationError):
            validate_case(case)


if __name__ == "__main__":
    unittest.main()
