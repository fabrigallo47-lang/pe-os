#!/usr/bin/env python3
"""Regression tests for the append-only runtime event ledger."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime import ledger_store  # noqa: E402


def event(event_id: str, source_id: str, known_at: str, value: str = "10") -> dict:
    return {
        "event_id": event_id,
        "event": "Claim observed",
        "effective_date": "2026-04-01",
        "known_at": known_at,
        "source_ids": [source_id],
        "trigger_claim_ids": ["claim-1"],
        "mutations": [
            {
                "operation": "OBSERVE",
                "object_type": "CLAIM",
                "object_id": "claim-1",
                "field": "value",
                "to": value,
            }
        ],
    }


class LedgerStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_pipeline_out = ledger_store.PIPELINE_OUT
        ledger_store.PIPELINE_OUT = Path(self.temporary.name) / "pipeline_out"
        self.case_id = "case-ledger-test"

    def tearDown(self) -> None:
        ledger_store.PIPELINE_OUT = self.previous_pipeline_out
        self.temporary.cleanup()

    def test_duplicate_event_id_is_a_no_op_with_one_line(self) -> None:
        first = ledger_store.append_event(
            self.case_id, event("event-1", "source-1", "2026-04-01T09:00:00Z")
        )
        second = ledger_store.append_event(
            self.case_id, event("event-1", "source-1", "2026-04-01T09:00:00Z")
        )

        self.assertEqual(first, {"appended": True, "event_id": "event-1", "reason": None})
        self.assertFalse(second["appended"])
        self.assertIsNotNone(second["reason"])
        stored = ledger_store.read_ledger(self.case_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["ledger_sequence"], 1)
        self.assertIsNone(stored[0]["previous_ledger_hash"])
        self.assertTrue(stored[0]["recorded_at"])
        self.assertTrue(stored[0]["ledger_hash"].startswith("sha256:"))

    def test_identical_claim_content_from_different_sources_both_persist(self) -> None:
        ledger_store.append_event(
            self.case_id, event("event-source-1", "source-1", "2026-04-01T09:00:00Z")
        )
        ledger_store.append_event(
            self.case_id, event("event-source-2", "source-2", "2026-04-01T09:00:01Z")
        )

        events = ledger_store.read_ledger(self.case_id)
        self.assertEqual([item["event_id"] for item in events], ["event-source-1", "event-source-2"])
        self.assertEqual([item["source_ids"] for item in events], [["source-1"], ["source-2"]])

    def test_as_of_filters_on_known_at_inclusively(self) -> None:
        ledger_store.append_event(
            self.case_id, event("event-early", "source-1", "2026-04-01T09:00:00Z")
        )
        ledger_store.append_event(
            self.case_id, event("event-late", "source-2", "2026-04-01T09:00:01Z")
        )

        events = ledger_store.read_ledger(self.case_id, as_of="2026-04-01T09:00:00Z")
        self.assertEqual([item["event_id"] for item in events], ["event-early"])

    def test_replay_hash_is_deterministic(self) -> None:
        ledger_store.append_event(
            self.case_id, event("event-1", "source-1", "2026-04-01T09:00:00Z", "10")
        )
        ledger_store.append_event(
            self.case_id, event("event-2", "source-2", "2026-04-01T09:00:01Z", "12")
        )

        hashes = {ledger_store.replay(self.case_id)["replay_hash"] for _ in range(10)}
        self.assertEqual(len(hashes), 1)

    def test_fresh_case_reads_as_empty(self) -> None:
        self.assertEqual(ledger_store.read_ledger("fresh-case"), [])

    def test_new_claim_admission_requires_a_canonical_mode(self) -> None:
        admission = event("admission-1", "source-1", "2026-04-01T09:00:00Z")
        admission["event"] = "CLAIM_ADMISSION"

        with self.assertRaisesRegex(ValueError, "admission_mode is required"):
            ledger_store.append_event(self.case_id, admission)

        admission["admission_mode"] = "INFERRED_FROM_ACTOR"
        with self.assertRaisesRegex(ValueError, "admission_mode must be one of"):
            ledger_store.append_event(self.case_id, admission)

        self.assertEqual(ledger_store.read_ledger(self.case_id), [])

    def test_legacy_event_without_admission_mode_remains_distinguishable(self) -> None:
        legacy = event("legacy-admission", "source-1", "2026-04-01T09:00:00Z")
        legacy["event"] = "CLAIM_ADMISSION"
        path = ledger_store.PIPELINE_OUT / "cases" / self.case_id / "ledger.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

        stored = ledger_store.read_ledger(self.case_id)
        replayed = ledger_store.replay(self.case_id)

        self.assertNotIn("admission_mode", stored[0])
        self.assertEqual(replayed["event_count"], 1)
        self.assertEqual(
            replayed["objects"]["CLAIM"]["claim-1"]["value"], "10"
        )

    def test_hash_chain_detects_tampering(self) -> None:
        ledger_store.append_event(
            self.case_id, event("event-1", "source-1", "2026-04-01T09:00:00Z")
        )
        path = ledger_store.PIPELINE_OUT / "cases" / self.case_id / "ledger.jsonl"
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["known_at"] = "2026-04-02T09:00:00Z"
        path.write_text(json.dumps(stored) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "failed integrity"):
            ledger_store.read_ledger(self.case_id)

    def test_first_protected_row_anchors_legacy_history(self) -> None:
        legacy = event("legacy", "source-1", "2026-04-01T09:00:00Z")
        path = ledger_store.PIPELINE_OUT / "cases" / self.case_id / "ledger.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

        ledger_store.append_event(
            self.case_id, event("protected", "source-2", "2026-04-01T09:00:01Z")
        )
        rows = ledger_store.read_ledger(self.case_id)

        self.assertNotIn("ledger_hash", rows[0])
        self.assertEqual(rows[1]["ledger_sequence"], 2)
        self.assertEqual(rows[1]["previous_ledger_hash"], ledger_store._sha256(rows[0]))

    def test_concurrent_duplicate_append_remains_exactly_once(self) -> None:
        candidate = event("same-event", "source-1", "2026-04-01T09:00:00Z")
        with ThreadPoolExecutor(max_workers=12) as executor:
            outcomes = list(
                executor.map(
                    lambda _: ledger_store.append_event(self.case_id, candidate),
                    range(24),
                )
            )

        self.assertEqual(sum(item["appended"] for item in outcomes), 1)
        self.assertEqual(len(ledger_store.read_ledger(self.case_id)), 1)


if __name__ == "__main__":
    unittest.main()
