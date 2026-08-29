#!/usr/bin/env python3
"""Tests for the credential-free PAN-5 baseline inventory."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.baseline_inventory import (
    governed_input_record,
    package_record,
    repo_contract_record,
)


class BaselineInventoryTests(unittest.TestCase):
    def test_versioned_repository_contracts_are_complete(self) -> None:
        record = repo_contract_record()
        self.assertEqual(record["status"], "ready", record["missing"])
        self.assertTrue(record["files"])
        self.assertTrue(all(len(item["sha256"]) == 64 for item in record["files"]))

    def test_package_record_reports_missing_files_without_hiding_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "present.json").write_text("{}", encoding="utf-8")
            record = package_record(
                "synthetic",
                root,
                ("present.json", "missing.json"),
            )
        self.assertEqual(record["status"], "missing")
        self.assertEqual(record["missing"], ["missing.json"])

    def test_future_inputs_have_an_explicit_access_plan(self) -> None:
        record = governed_input_record(
            "scout",
            None,
            "PANTA_SCOUT_INPUT",
            "Gate 2",
        )
        self.assertEqual(record["status"], "access-planned")
        self.assertEqual(record["environment_variable"], "PANTA_SCOUT_INPUT")
        self.assertIn("outside Git", record["access_policy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
