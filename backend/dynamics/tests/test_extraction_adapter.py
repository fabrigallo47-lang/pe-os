import copy
import json
import tempfile
import unittest
from pathlib import Path

from runtime import (
    AdmissionInputError,
    analyze_extraction_graph,
    apply_extraction_transition,
    compile_extraction_to_runtime_inputs,
)
from runtime import ledger_store


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extraction_graph():
    return {
        "nodes": [
            {
                "id": "claim:a",
                "type": "claim",
                "statement": "Admitted input is 10.",
                "value": "10",
                "unit": "$mm",
                "period": "FY2026",
                "perimeter": "Test perimeter",
                "coverage_status": "mapped",
            },
            {
                "id": "claim:b",
                "type": "claim",
                "statement": "Unadmitted extracted input is 11.",
                "value": "11",
                "unit": "$mm",
                "period": "FY2026",
                "perimeter": "Test perimeter",
                "coverage_status": "mapped",
            },
            {
                "id": "route:a",
                "type": "support_route",
                "logic": "INDEPENDENT",
                "coverage_status": "partial",
                "note": "Logic defaults to INDEPENDENT",
            },
            {
                "id": "position:a",
                "type": "case_position",
                "statement": "Test position",
                "decision_status": "PENDING",
                "coverage_status": "partial",
                "period": "FY2026",
                "perimeter": "Test perimeter",
            },
            {
                "id": "model:a",
                "type": "model_node",
                "label": "Test model output",
                "unit": "$mm",
                "coverage_status": "partial",
                "formula": None,
                "formula_ref": None,
            },
        ],
        "edges": [
            {"source": "claim:a", "target": "claim:b", "rel": "SUPPORTS"},
            {"source": "claim:a", "target": "route:a", "rel": "SUPPORTS_ROUTE"},
            {"source": "route:a", "target": "position:a", "rel": "ROUTE_FOR_POSITION"},
            {
                "source": "position:a",
                "target": "model:a",
                "rel": "BINDS_TO",
                "binding_direction": "POSITION_DRIVES_MODEL",
            },
        ],
        "execution_mapping": {
            "model_nodes": [
                {
                    "id": "model:a",
                    "unit": "$mm",
                    "formula": None,
                    "formula_ref": None,
                }
            ],
            "directed_model_edges": [],
            "position_model_directions": [
                {
                    "case_position_id": "position:a",
                    "model_node_id": "model:a",
                    "direction": "POSITION_DRIVES_MODEL",
                    "coverage_status": "partial",
                }
            ],
            "formulas": [],
            "rule_switches": [],
            "cyclic_component_solver_configs": [],
            "inverse_solver_configs": [],
            "model_controls": [],
            "coverage_limits": [
                {"node_id": "model:a", "reason": "Formula must be populated from workbook"}
            ],
        },
    }


def manifest():
    return {
        "manifest_version": "1.0",
        "case_id": "ADAPTER-TEST",
        "as_of_known_at": "2026-08-21T12:00:00+02:00",
        "admitted_claim_ids": ["claim:a"],
    }


def event():
    return {
        "event_id": "EV-ADAPTER-001",
        "event": "Correct admitted input",
        "effective_date": "2026-08-21",
        "known_at": "2026-08-21T12:00:00+02:00",
        "source_ids": ["SOURCE-REVISION"],
        "trigger_claim_ids": ["claim:a"],
        "mutations": [
            {
                "operation": "CORRECT",
                "object_type": "CLAIM",
                "object_id": "claim:a",
                "field": "value",
                "from": "10",
                "to": "9",
                "unit": "$mm",
                "period": "FY2026",
                "perimeter": "Test perimeter",
            }
        ],
    }


class ExtractionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.graph = extraction_graph()
        self.materiality = load_json("benchmark/keystone_materiality_policy_v0.json")
        self.authority = load_json("benchmark/keystone_authority_matrix_v0.json")
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_pipeline_out = ledger_store.PIPELINE_OUT
        ledger_store.PIPELINE_OUT = Path(self.temporary.name) / "pipeline_out"

    def tearDown(self):
        ledger_store.PIPELINE_OUT = self.previous_pipeline_out
        self.temporary.cleanup()

    def test_analysis_distinguishes_partial_transition_from_full_recomputation(self):
        report = analyze_extraction_graph(self.graph)
        self.assertTrue(report["applicability"]["candidate_transition_on_mapped_scope"])
        self.assertFalse(report["applicability"]["full_financial_recomputation"])
        self.assertIn("EXECUTABLE_FORMULAS", report["missing_for_full_runtime"])
        self.assertEqual(
            report["noncanonical_claim_to_claim_relations"],
            ["claim:a:SUPPORTS:claim:b"],
        )

    def test_compile_requires_explicit_institutional_admission(self):
        with self.assertRaises(AdmissionInputError):
            compile_extraction_to_runtime_inputs(self.graph, None)

    def test_compile_is_immutable_and_does_not_traverse_claim_to_claim_edges(self):
        original = copy.deepcopy(self.graph)
        compiled = compile_extraction_to_runtime_inputs(self.graph, manifest())
        self.assertEqual(self.graph, original)
        claims = {item["claim_id"]: item for item in compiled["current_graph"]["claims"]}
        self.assertFalse(claims["claim:a"]["validation_only"])
        self.assertTrue(claims["claim:b"]["validation_only"])
        self.assertEqual(compiled["current_graph"]["claim_position_edges"], [])
        route = compiled["current_graph"]["support_routes"][0]
        self.assertEqual(route["member_claim_ids"], ["claim:a"])
        reasons = {
            item["reason_code"] for item in compiled["execution_mapping"]["coverage_limits"]
        }
        self.assertIn("NON_CANONICAL_CLAIM_TO_CLAIM_RELATION", reasons)
        self.assertIn("MISSING_EXECUTABLE_FORMULA", reasons)

    def test_manifest_hash_mismatch_is_rejected(self):
        bad_manifest = manifest()
        bad_manifest["source_graph_hash"] = "sha256:" + "0" * 64
        with self.assertRaises(AdmissionInputError):
            compile_extraction_to_runtime_inputs(self.graph, bad_manifest)

    def test_event_cannot_use_unadmitted_claim(self):
        bad_event = event()
        bad_event["trigger_claim_ids"] = ["claim:b"]
        bad_event["mutations"][0]["object_id"] = "claim:b"
        with self.assertRaises(AdmissionInputError):
            apply_extraction_transition(
                self.graph,
                bad_event,
                manifest(),
                self.materiality,
                self.authority,
            )

    def test_transition_uses_definitive_runtime_and_is_deterministic(self):
        first = apply_extraction_transition(
            self.graph, event(), manifest(), self.materiality, self.authority
        )
        permuted = copy.deepcopy(self.graph)
        permuted["nodes"] = list(reversed(permuted["nodes"]))
        permuted["edges"] = list(reversed(permuted["edges"]))
        second = apply_extraction_transition(
            permuted, event(), manifest(), self.materiality, self.authority
        )
        first_output = first["transition_output"]
        second_output = second["transition_output"]
        self.assertEqual(first_output["replay_hash"], second_output["replay_hash"])
        self.assertEqual(first_output["affected_set"], second_output["affected_set"])
        affected = {item["object_id"] for item in first_output["affected_set"]}
        self.assertEqual(affected, {"claim:a", "route:a", "position:a", "model:a"})
        self.assertEqual(first_output["candidate_current_approved_delta"]["approved"], [])
        self.assertEqual(first["adapter_report"]["admitted_claim_count"], 1)
        admission_events = ledger_store.read_ledger(manifest()["case_id"])
        self.assertEqual(len(admission_events), 1)
        self.assertEqual(admission_events[0]["event"], "CLAIM_ADMISSION")


if __name__ == "__main__":
    unittest.main()
