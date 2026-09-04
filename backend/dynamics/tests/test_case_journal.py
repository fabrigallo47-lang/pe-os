#!/usr/bin/env python3
"""Contract tests for the canonical case Journal projection."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DYNAMICS_ROOT))

from runtime.case_journal import build_case_journal, compare_graphs  # noqa: E402


class CaseJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "case_id": "scout",
            "claims": [
                {"claim_id": "CL-1", "statement": "Base claim", "workstream_id": "Q-COMMERCIAL"}
            ],
            "unknowns": [
                {"unknown_id": "UNK-1", "label": "Churn", "status": "OPEN", "workstream_id": "Q-COMMERCIAL"}
            ],
            "model_nodes": [
                {"model_node_id": "MN-1", "label": "EBITDA", "value": 10,
                 "preferred_direction": "HIGHER_IS_BETTER", "workstream_id": "Q-RETURNS"}
            ],
        }
        self.current = {
            "case_id": "scout",
            "claims": [
                {"claim_id": "CL-1", "statement": "Base claim", "workstream_id": "Q-COMMERCIAL"},
                {"claim_id": "CL-2", "statement": "Customer reference", "workstream_id": "Q-COMMERCIAL"},
            ],
            "unknowns": [
                {"unknown_id": "UNK-1", "label": "Churn", "status": "CLOSED", "workstream_id": "Q-COMMERCIAL"},
                {"unknown_id": "UNK-2", "label": "Pricing", "status": "OPEN", "workstream_id": "Q-COMMERCIAL"},
            ],
            "model_nodes": [
                {"model_node_id": "MN-1", "label": "EBITDA", "value": 12,
                 "preferred_direction": "HIGHER_IS_BETTER", "workstream_id": "Q-RETURNS"}
            ],
        }

    def test_graph_delta_classifies_direction_and_workstream(self) -> None:
        result = compare_graphs(self.baseline, self.current)

        by_id = {change["object_id"]: change for change in result["changes"]}
        self.assertEqual(by_id["CL-2"]["trend"], "ADVANCED")
        self.assertEqual(by_id["UNK-1"]["movement"], "CLOSED")
        self.assertEqual(by_id["UNK-2"]["trend"], "REGRESSED")
        self.assertEqual(by_id["MN-1"]["trend"], "ADVANCED")
        self.assertEqual(result["advanced"], 3)
        self.assertEqual(result["regressed"], 1)
        self.assertEqual(
            {item["workstream_id"] for item in result["workstreams"]},
            {"Q-COMMERCIAL", "Q-RETURNS"},
        )

    def test_semantically_identical_records_ignore_audit_metadata_and_set_order(self) -> None:
        baseline = {
            "claims": [{
                "claim_id": "CL-1",
                "statement": "Same claim",
                "source_ids": ["SRC-2", "SRC-1"],
                "known_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }],
        }
        current = {
            "claims": [{
                "claim_id": "CL-1",
                "statement": "Same claim",
                "source_ids": ["SRC-1", "SRC-2"],
                "known_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
            }],
        }

        self.assertEqual(compare_graphs(baseline, current)["changes"], [])

    def test_duplicate_and_missing_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate id 'CL-1'"):
            compare_graphs(
                {"claims": [
                    {"claim_id": "CL-1", "statement": "First"},
                    {"claim_id": "CL-1", "statement": "Second"},
                ]},
                {},
            )
        with self.assertRaisesRegex(ValueError, "has no stable id"):
            compare_graphs({"claims": [{"statement": "No identity"}]}, {})
        with self.assertRaisesRegex(ValueError, "must be an array or object map"):
            compare_graphs({"claims": "not-a-collection"}, {})

    def test_object_maps_use_the_map_key_as_stable_identity(self) -> None:
        graph = {"claims": {"CL-1": {"statement": "Map-addressed claim"}}}
        self.assertEqual(compare_graphs(graph, graph)["changes"], [])
        mapped = {"claims": {"storage-key": {"claim_id": "CL-OTHER"}}}
        listed = {"claims": [{"claim_id": "CL-OTHER"}]}
        self.assertEqual(compare_graphs(mapped, listed)["changes"], [])

    def test_disappearance_does_not_masquerade_as_resolution(self) -> None:
        result = compare_graphs(
            {"unknowns": [{"unknown_id": "UNK-1", "status": "OPEN"}]},
            {"unknowns": []},
        )

        change = result["changes"][0]
        self.assertEqual(change["trend"], "CHANGED")
        self.assertIsNone(change["movement"])
        self.assertIn("resolution is not inferred", change["reason"])
        self.assertEqual(result["closed"], 0)

    def test_closed_item_added_to_graph_is_not_reported_as_opened(self) -> None:
        result = compare_graphs(
            {},
            {"conditions": [{"condition_id": "COND-1", "status": "CLOSED"}]},
        )

        change = result["changes"][0]
        self.assertEqual(change["trend"], "CHANGED")
        self.assertIsNone(change["movement"])
        self.assertEqual(result["opened"], 0)

    def test_all_status_dimensions_determine_direction_and_conflicts_are_neutral(self) -> None:
        baseline = {"case_positions": [{
            "position_id": "POS-1",
            "decision_status_at_ic": "ACCEPTED",
            "epistemic_status_at_ic": "ESTABLISHED",
        }]}
        regressed = {"case_positions": [{
            "position_id": "POS-1",
            "decision_status_at_ic": "ACCEPTED",
            "epistemic_status_at_ic": "CONTESTED",
        }]}
        mixed = {"case_positions": [{
            "position_id": "POS-1",
            "decision_status_at_ic": "ACCEPTED",
            "epistemic_status_at_ic": "CONTESTED",
        }]}
        mixed_baseline = {"case_positions": [{
            "position_id": "POS-1",
            "decision_status_at_ic": "PENDING",
            "epistemic_status_at_ic": "ESTABLISHED",
        }]}

        self.assertEqual(
            compare_graphs(baseline, regressed)["changes"][0]["trend"],
            "REGRESSED",
        )
        mixed_change = compare_graphs(mixed_baseline, mixed)["changes"][0]
        self.assertEqual(mixed_change["trend"], "CHANGED")
        self.assertIn("different directions", mixed_change["reason"])

    def test_canonical_graph_edges_are_compared_directionally(self) -> None:
        result = compare_graphs(
            {},
            {"claim_position_edges": [
                {
                    "edge_id": "EDGE-COLLISION",
                    "claim_id": "CL-1",
                    "position_id": "POS-1",
                    "relation_type": "SUPPORTS",
                },
                {
                    "edge_id": "EDGE-COLLISION",
                    "claim_id": "CL-2",
                    "position_id": "POS-1",
                    "relation_type": "CONTRADICTS",
                },
            ]},
        )

        by_relation = {
            change["after"]["relation_type"]: change
            for change in result["changes"]
        }
        self.assertEqual(by_relation["SUPPORTS"]["trend"], "ADVANCED")
        self.assertEqual(by_relation["CONTRADICTS"]["trend"], "REGRESSED")

    def test_workstream_filter_keeps_objects_that_moved_out_of_the_workstream(self) -> None:
        journal = build_case_journal(
            "scout",
            baseline_graph={"claims": [{
                "claim_id": "CL-1",
                "statement": "Claim",
                "workstream_id": "Q-OLD",
            }]},
            current_graph={"claims": [{
                "claim_id": "CL-1",
                "statement": "Claim",
                "workstream_id": "Q-NEW",
            }]},
            workstream="Q-OLD",
        )

        self.assertEqual(journal["summary"]["change_count"], 1)
        change = journal["summary"]["changes"][0]
        self.assertEqual(change["before_workstream_id"], "Q-OLD")
        self.assertEqual(change["after_workstream_id"], "Q-NEW")
        self.assertEqual(journal["summary"]["workstreams"][0]["workstream_id"], "Q-OLD")

    def test_event_timeline_has_three_temporal_axes_and_actor_fallback(self) -> None:
        journal = build_case_journal(
            "scout",
            runtime_events=[{
                "event_id": "EV-ADMIT",
                "event": "CLAIM_ADMISSION",
                "effective_date": "2026-01-01",
                "known_at": "2026-01-10T10:00:00Z",
                "recorded_at": "2026-01-10T10:00:01Z",
                "actor_id": "USR-1",
                "mutations": [{"object_id": "CL-2"}],
                "workstream_ids": ["Q-COMMERCIAL"],
            }],
            vault_events=[{
                "id": "EV-NOTE",
                "type": "note",
                "effective_date": "2026-01-02",
                "known_at": "2026-01-11T10:00:00Z",
                "recorded_at": "2026-01-11T10:00:02Z",
            }],
            baseline_graph=self.baseline,
            current_graph=self.current,
            baseline_metadata={"state_id": "STATE-1"},
            current_metadata={"state_id": "STATE-2"},
        )

        self.assertEqual(journal["event_count"], 2)
        first, second = journal["events"]
        self.assertEqual(first["actor_id"], "USR-1")
        self.assertEqual(second["actor_id"], "PANTA_SYSTEM")
        self.assertEqual(second["actor_source"], "INFERRED_SYSTEM")
        self.assertEqual(
            journal["temporal"],
            {
                "effective_axis": "effective_date",
                "knowledge_axis": "known_at",
                "recording_axis": "recorded_at",
                "since": None,
                "until": None,
                "as_of": None,
            },
        )

    def test_filters_and_explicit_close_drift(self) -> None:
        journal = build_case_journal(
            "scout",
            runtime_events=[
                {"event_id": "E-1", "event": "CLAIM_ADMISSION", "kind": "EVIDENCE",
                 "effective_date": "2026-01-01", "known_at": "2026-01-10T10:00:00Z",
                 "workstream_ids": ["Q-COMMERCIAL"]},
                {"event_id": "E-2", "event": "CASE_SETTLED", "kind": "SETTLEMENT",
                 "effective_date": "2026-01-20", "known_at": "2026-01-20T10:00:00Z",
                 "workstream_ids": ["Q-RETURNS"]},
            ],
            baseline_graph=self.baseline,
            current_graph=self.current,
            current_metadata={"state_id": "STATE-2"},
            close_graph=self.baseline,
            close_metadata={"state_id": "STATE-CLOSE"},
            since="2026-01-15",
            workstream="Q-RETURNS",
            kind="SETTLEMENT",
        )

        self.assertEqual([event["event_id"] for event in journal["events"]], ["E-2"])
        self.assertEqual(
            {change["workstream_id"] for change in journal["summary"]["changes"]},
            {"Q-RETURNS"},
        )
        self.assertEqual(journal["drift"]["status"], "AVAILABLE")
        self.assertEqual(journal["drift"]["baseline_state_id"], "STATE-CLOSE")

    def test_authority_ledger_records_remain_distinct_from_vault_events(self) -> None:
        journal = build_case_journal(
            "scout",
            authority_events=[{
                "authority_record_id": "AUTH-1",
                "event_id": "AUTH-1",
                "event": "AUTHORITY_ATTESTED",
                "kind": "AUTHORITY",
                "effective_date": "2026-01-20",
                "known_at": "2026-01-20T10:00:00Z",
                "recorded_at": "2026-01-20T10:00:01Z",
                "actor_id": "USR-PARTNER",
            }],
        )

        self.assertEqual(journal["events"][0]["source"], "AUTHORITY_LEDGER")
        self.assertEqual(journal["events"][0]["phase"], "DECISION")

    def test_output_validates_against_published_schema(self) -> None:
        journal = build_case_journal(
            "scout",
            baseline_graph=self.baseline,
            current_graph=self.current,
            baseline_metadata={
                "state_id": "STATE-1", "version_id": "STATE-1",
                "known_at": "2026-01-01T00:00:00Z", "effective_date": "2026-01-01",
                "graph_hash": "sha256:one",
            },
            current_metadata={
                "state_id": "STATE-2", "version_id": "STATE-2",
                "known_at": "2026-01-02T00:00:00Z", "effective_date": "2026-01-02",
                "graph_hash": "sha256:two",
            },
        )
        schema = json.loads(
            (DYNAMICS_ROOT / "schemas/case_journal.schema.json").read_text(encoding="utf-8")
        )

        Draft202012Validator(schema, format_checker=FormatChecker()).validate(journal)


if __name__ == "__main__":
    unittest.main()
