#!/usr/bin/env python3
"""Connected API tests for journal timeline, cutoffs and graph-state selection."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from backend.dynamics.runtime import ledger_store  # noqa: E402


class V20JournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous = {
            "PIPELINE_OUT": router.PIPELINE_OUT,
            "CASE_PIPELINE_ROOT": router.CASE_PIPELINE_ROOT,
            "VAULT": router.VAULT,
            "LEDGER_PIPELINE_OUT": ledger_store.PIPELINE_OUT,
        }
        router.PIPELINE_OUT = self.root / "keystone-bundle"
        router.CASE_PIPELINE_ROOT = self.root / "case-bundles"
        router.VAULT = self.root / "vault"
        ledger_store.PIPELINE_OUT = self.root / "ledger-pipeline-out"
        self.case_id = "journal-case"

        baseline = {
            "case_id": self.case_id,
            "state_id": "STATE-1",
            "claims": [{
                "claim_id": "CL-1", "statement": "Initial revenue evidence",
                "workstream_id": "Q-COMMERCIAL",
            }],
            "unknowns": [{
                "unknown_id": "UNK-1", "label": "Churn", "status": "OPEN",
                "workstream_id": "Q-COMMERCIAL",
            }],
        }
        current = {
            "case_id": self.case_id,
            "state_id": "STATE-2",
            "claims": baseline["claims"] + [{
                "claim_id": "CL-2", "statement": "Customer reference admitted",
                "workstream_id": "Q-COMMERCIAL",
            }],
            "unknowns": [{
                "unknown_id": "UNK-1", "label": "Churn", "status": "CLOSED",
                "workstream_id": "Q-COMMERCIAL",
            }],
        }
        router._archive_graph_version(
            self.case_id, "STATE-1", "CURRENT", baseline,
            effective_date="2026-01-01", known_at="2026-01-10T10:00:00Z",
        )
        router._archive_graph_version(
            self.case_id, "STATE-2", "CURRENT", current,
            prior_state_id="STATE-1", effective_date="2026-01-20",
            known_at="2026-01-20T10:00:00Z",
        )
        ledger_store.append_event(self.case_id, {
            "event_id": "LEDGER-ADMISSION",
            "event": "CLAIM_ADMISSION",
            "admission_mode": "HUMAN_CONFIRMED",
            "effective_date": "2026-01-19",
            "known_at": "2026-01-20T09:00:00Z",
            "actor_id": "USR-ASSOCIATE",
            "source_ids": ["SRC-1"],
            "trigger_claim_ids": ["CL-2"],
            "workstream_ids": ["Q-COMMERCIAL"],
            "mutations": [{
                "operation": "ADD", "object_type": "CLAIM", "object_id": "CL-2",
            }],
        })
        events_dir = router.VAULT / "deals" / self.case_id / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "note.md").write_text(
            "---\n"
            "id: VAULT-NOTE\n"
            "type: note\n"
            "kind: annotation\n"
            "label: Partner follow-up\n"
            "detail: Recheck customer cohort after settlement.\n"
            "actor: USR-PARTNER\n"
            "workstream: Q-COMMERCIAL\n"
            "effective_date: '2026-01-21'\n"
            "known_at: '2026-01-21T09:00:00Z'\n"
            "---\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        router.PIPELINE_OUT = self.previous["PIPELINE_OUT"]
        router.CASE_PIPELINE_ROOT = self.previous["CASE_PIPELINE_ROOT"]
        router.VAULT = self.previous["VAULT"]
        ledger_store.PIPELINE_OUT = self.previous["LEDGER_PIPELINE_OUT"]
        self.temporary.cleanup()

    def test_changes_since_uses_state_at_cutoff_as_baseline(self) -> None:
        journal = router.get_case_journal(self.case_id, since="2026-01-15")

        self.assertEqual(journal["baseline"]["state_id"], "STATE-1")
        self.assertEqual(journal["current"]["state_id"], "STATE-2")
        by_id = {change["object_id"]: change for change in journal["summary"]["changes"]}
        self.assertEqual(by_id["CL-2"]["trend"], "ADVANCED")
        self.assertEqual(by_id["UNK-1"]["movement"], "CLOSED")
        self.assertEqual(
            [event["event_id"] for event in journal["events"]],
            ["LEDGER-ADMISSION", "VAULT-NOTE"],
        )

    def test_as_of_reconstructs_earlier_current_and_excludes_future_events(self) -> None:
        journal = router.get_case_journal(
            self.case_id, as_of_date="2026-01-15"
        )

        self.assertEqual(journal["current"]["state_id"], "STATE-1")
        self.assertEqual(journal["event_count"], 0)

    def test_workstream_kind_and_close_drift_are_explicit(self) -> None:
        journal = router.get_case_journal(
            self.case_id,
            workstream="Q-COMMERCIAL",
            kind="EVIDENCE",
            close_state_id="STATE-1",
        )

        self.assertEqual([event["event_id"] for event in journal["events"]], ["LEDGER-ADMISSION"])
        self.assertEqual(journal["drift"]["status"], "AVAILABLE")
        self.assertEqual(journal["drift"]["baseline_state_id"], "STATE-1")
        self.assertGreater(journal["drift"]["change_count"], 0)
        self.assertEqual(
            {change["workstream_id"] for change in journal["summary"]["changes"]},
            {"Q-COMMERCIAL"},
        )

    def test_runtime_hash_chain_corruption_fails_closed(self) -> None:
        path = ledger_store.PIPELINE_OUT / "cases" / self.case_id / "ledger.jsonl"
        row = json.loads(path.read_text(encoding="utf-8"))
        row["actor_id"] = "TAMPERED"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")

        with self.assertRaises(router.HTTPException) as raised:
            router.get_case_journal(self.case_id)
        self.assertEqual(raised.exception.status_code, 409)

    def test_duplicate_graph_identity_fails_as_integrity_conflict(self) -> None:
        router._archive_graph_version(
            self.case_id,
            "STATE-DUPLICATE",
            "CURRENT",
            {
                "case_id": self.case_id,
                "state_id": "STATE-DUPLICATE",
                "claims": [
                    {"claim_id": "CL-DUP", "statement": "First"},
                    {"claim_id": "CL-DUP", "statement": "Second"},
                ],
            },
            prior_state_id="STATE-2",
            effective_date="2026-01-21",
            known_at="2026-01-21T10:00:00Z",
        )

        with self.assertRaises(router.HTTPException) as raised:
            router.get_case_journal(
                self.case_id,
                baseline_state_id="STATE-2",
                current_state_id="STATE-DUPLICATE",
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("duplicate id", str(raised.exception.detail))

    def test_durable_notes_outside_event_directory_are_included(self) -> None:
        notes = router.VAULT / "deals" / self.case_id / "notes"
        notes.mkdir(parents=True)
        (notes / "note-1.md").write_text(
            "---\n"
            "id: NOTE-1\n"
            "type: note\n"
            "label: Follow up recorded\n"
            "actor_id: USR-ASSOCIATE\n"
            "effective_date: '2026-01-22'\n"
            "known_at: '2026-01-22T10:00:00Z'\n"
            "---\n",
            encoding="utf-8",
        )

        journal = router.get_case_journal(self.case_id)

        event = next(item for item in journal["events"] if item["event_id"] == "NOTE-1")
        self.assertEqual(event["kind"], "ANNOTATION")
        self.assertEqual(event["actor_id"], "USR-ASSOCIATE")


if __name__ == "__main__":
    unittest.main()
