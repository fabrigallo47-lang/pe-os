#!/usr/bin/env python3
"""Regression tests for durable extraction claim admission."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import AdmissionInputError, compile_extraction_to_runtime_inputs
from runtime import ledger_store


def graph() -> dict:
    return {
        "nodes": [
            {"id": "claim:a", "type": "claim", "source_id": "SRC-A"},
            {"id": "claim:b", "type": "claim", "source_doc": "SRC-B"},
        ],
        "edges": [],
    }


def manifest() -> dict:
    return {
        "manifest_version": "1.0",
        "case_id": "admission-ledger-test",
        "as_of_known_at": "2026-08-21T12:00:00+02:00",
        "admitted_claim_ids": ["claim:b", "claim:a"],
        "actor_id": "reviewer-001",
    }


class AdmissionLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_pipeline_out = ledger_store.PIPELINE_OUT
        ledger_store.PIPELINE_OUT = Path(self.temporary.name) / "pipeline_out"

    def tearDown(self) -> None:
        ledger_store.PIPELINE_OUT = self.previous_pipeline_out
        self.temporary.cleanup()

    def test_successful_admission_appends_manifest_cutoff_and_claim_sources(self) -> None:
        compiled = compile_extraction_to_runtime_inputs(graph(), manifest())

        events = ledger_store.read_ledger("admission-ledger-test")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "CLAIM_ADMISSION")
        self.assertEqual(events[0]["known_at"], manifest()["as_of_known_at"])
        self.assertEqual(events[0]["source_ids"], ["SRC-A", "SRC-B"])
        self.assertEqual(events[0]["trigger_claim_ids"], ["claim:a", "claim:b"])
        self.assertEqual(events[0]["actor_id"], "reviewer-001")
        self.assertEqual(set(compiled), {"current_graph", "execution_mapping", "adapter_report"})

    def test_invalid_manifest_appends_nothing(self) -> None:
        invalid = manifest()
        invalid["admitted_claim_ids"] = ["missing-claim"]

        with self.assertRaises(AdmissionInputError):
            compile_extraction_to_runtime_inputs(graph(), invalid)

        self.assertEqual(ledger_store.read_ledger("admission-ledger-test"), [])

    def test_same_manifest_is_idempotent(self) -> None:
        compile_extraction_to_runtime_inputs(graph(), manifest())
        compile_extraction_to_runtime_inputs(graph(), manifest())

        self.assertEqual(len(ledger_store.read_ledger("admission-ledger-test")), 1)

    def test_ledger_write_failure_stops_admission(self) -> None:
        with patch.object(ledger_store, "append_event", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                compile_extraction_to_runtime_inputs(graph(), manifest())


if __name__ == "__main__":
    unittest.main()
