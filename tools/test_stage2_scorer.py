#!/usr/bin/env python3
"""Tests for the public deterministic Stage-2 scorer."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.stage2_scorer import (
    Stage2ScorerError,
    guard_no_leakage,
    load_e3_manifest,
    load_live_claims,
    score_stage2,
)


FIELDS = [
    "claim_id",
    "statement",
    "source_id",
    "locator",
    "epistemic_class",
    "value",
    "unit",
    "definition_id",
    "period",
    "perimeter",
    "notes",
    "ground_truth_flag",
    "validation_only",
]


def _manifest(claims: list[dict]) -> dict:
    return {
        "schema_version": "e3-1.0",
        "manifest_id": "TEST",
        "deal": "fixture",
        "extractor": "fixture_extractor",
        "claims": claims,
        "extraction_metadata": {
            "compiler_fields_per_claim": [
                {"claim_id": claim["claim_id"], "metric": "fixture"}
                for claim in claims
            ]
        },
    }


def _claim(claim_id: str, statement: str, **overrides) -> dict:
    claim = {
        "claim_id": claim_id,
        "statement": statement,
        "source_id": "SRC-1",
        "locator": "Revenue / table 1",
        "epistemic_class": "attested",
        "value": "18.2",
        "unit": "%",
        "definition_id": "",
        "period": "FY2025",
        "perimeter": "Alderstone consolidated revenue",
        "notes": "",
        "ground_truth_flag": "False",
        "validation_only": "False",
    }
    claim.update(overrides)
    return claim


class Stage2ScorerTests(unittest.TestCase):
    def test_scores_all_fields_and_reads_epistemic_class(self) -> None:
        references = [
            _claim(
                "CL-1",
                "Riverton represents 18.2% of consolidated revenue.",
                value="0.182",
            ),
            _claim(
                "CL-2",
                "Opening EBITDA is $12.2 million.",
                value="12.2",
                unit="$mm",
                epistemic_class="observed",
            ),
        ]
        predictions = [
            _claim(
                "P-1",
                "Riverton represents 18.2% of consolidated revenue.",
                value="18.2",
            ),
            _claim(
                "P-2",
                "Opening EBITDA is $12.2 million.",
                value="11.0",
                unit="$m",
                epistemic_class="asserted",
                epistemic="observed",
            ),
        ]

        report = score_stage2(_manifest(predictions), references)

        self.assertEqual(report["recall"]["matched"], 2)
        self.assertEqual(report["recall"]["recall"], 1.0)
        self.assertEqual(report["metrics"]["value"]["correct"], 1)
        self.assertEqual(report["metrics"]["epistemic"]["correct"], 1)
        self.assertEqual(report["metrics"]["period"]["correct"], 2)
        self.assertFalse(report["details"][1]["fields"]["epistemic"]["correct"])

    def test_unmatched_claim_reduces_recall_and_is_not_field_evaluated(self) -> None:
        references = [
            _claim("CL-1", "Revenue is $74 million."),
            _claim("CL-2", "A completely unrelated legal covenant was signed."),
        ]
        predictions = [_claim("P-1", "Revenue is $74 million.")]

        report = score_stage2(_manifest(predictions), references)

        self.assertEqual(report["recall"], {
            "matched": 1,
            "reference_total": 2,
            "recall": 0.5,
        })
        self.assertEqual(report["metrics"]["value"]["evaluated"], 1)
        self.assertEqual(report["metrics"]["value"]["end_to_end_accuracy"], 0.5)

    def test_report_is_deterministic_independent_of_input_order(self) -> None:
        references = [
            _claim("CL-2", "EBITDA is $12 million.", value="12", unit="$mm"),
            _claim("CL-1", "Revenue is $74 million.", value="74", unit="$mm"),
        ]
        predictions = [
            _claim("P-2", "EBITDA is $12 million.", value="12", unit="$m"),
            _claim("P-1", "Revenue is $74 million.", value="74", unit="$m"),
        ]

        first = score_stage2(_manifest(predictions), references)
        second = score_stage2(_manifest(list(reversed(predictions))), list(reversed(references)))

        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )
        self.assertEqual(
            [detail["reference_claim_id"] for detail in first["details"]],
            ["CL-1", "CL-2"],
        )

    def test_leakage_guard_rejects_all_prohibited_inputs(self) -> None:
        rejected = [
            Path("source_materials/layer_3_validation_DO_NOT_INGEST/file.md"),
            Path("tables/claims_validation_only.csv"),
            Path("canonical/PANTA_Keystone_Canonical_Investment_Case_v1.1.json"),
        ]
        for path in rejected:
            with self.subTest(path=path):
                with self.assertRaises(Stage2ScorerError):
                    guard_no_leakage(path)

    def test_leakage_guard_rejects_embedded_manifest_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "e3.json"
            payload = _manifest([_claim("P-1", "Revenue is $74 million.")])
            payload["source_path"] = "canonical/answer_key.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(Stage2ScorerError, "embedded"):
                load_e3_manifest(path)

    def test_manifest_requires_compiler_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "e3.json"
            path.write_text(
                json.dumps({"claims": [_claim("P-1", "Revenue is $74 million.")]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Stage2ScorerError, "compiler_fields_per_claim"):
                load_e3_manifest(path)

    def test_manifest_requires_one_to_one_compiler_metadata_join(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "e3.json"
            payload = _manifest([_claim("P-1", "Revenue is $74 million.")])
            payload["extraction_metadata"]["compiler_fields_per_claim"] = []
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(Stage2ScorerError, "one-to-one"):
                load_e3_manifest(path)

    def test_loader_rejects_validation_only_live_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims_live.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(
                    _claim(
                        "CL-1",
                        "Revenue is $74 million.",
                        validation_only="True",
                    )
                )

            with self.assertRaisesRegex(Stage2ScorerError, "validation-only"):
                load_live_claims(path)

    def test_cli_writes_json_without_private_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "e3.json"
            claims_path = root / "claims_live.csv"
            output_path = root / "score.json"
            manifest_path.write_text(
                json.dumps(_manifest([_claim("P-1", "Revenue is $74 million.")])),
                encoding="utf-8",
            )
            with claims_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(_claim("CL-1", "Revenue is $74 million."))

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("stage2_scorer.py")),
                    "--e3-manifest",
                    str(manifest_path),
                    "--claims-live",
                    str(claims_path),
                    "--json-out",
                    str(output_path),
                    "--details",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Recall: 100.0%", completed.stdout)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["recall"]["matched"], 1)


if __name__ == "__main__":
    unittest.main()
