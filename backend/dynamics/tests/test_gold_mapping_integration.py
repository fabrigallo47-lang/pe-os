import json
import unittest
from decimal import Decimal
from pathlib import Path

from runtime import (
    apply_state_transition,
    compare_incremental_global,
    compile_gold_to_runtime_inputs,
    compute_affected_set,
)


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
GOLD_DIRS = (PROJECT_ROOT / "GOLD", PROJECT_ROOT.parent / "GOLD")
GOLD_DIR = next((path for path in GOLD_DIRS if path.exists()), GOLD_DIRS[0])
GOLD_MAPPING = GOLD_DIR / "keystone_execution_mapping_v1 (3).json"
GOLD_GRAPH = GOLD_DIR / "keystone_semantic_financial_graph_v1 (5).json"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class FinancialGoldIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GOLD_MAPPING.exists() or not GOLD_GRAPH.exists():
            raise unittest.SkipTest(
                "optional Financial Gold fixtures are not installed"
            )
        cls.gold_mapping = load_json(GOLD_MAPPING)
        cls.gold_graph = load_json(GOLD_GRAPH)
        cls.compiled = compile_gold_to_runtime_inputs(
            cls.gold_mapping,
            cls.gold_graph,
        )
        cls.materiality = load_json(
            ROOT / "benchmark" / "keystone_materiality_policy_v0.json"
        )
        cls.authority = load_json(
            ROOT / "benchmark" / "keystone_authority_matrix_v0.json"
        )
        cls.event = {
            "event_id": "GOLD-TEST-001",
            "event": "Standalone Base 2026 Firm EBITDA margin stress",
            "effective_date": "2026-01-01",
            "known_at": "2026-08-24T09:00:00Z",
            "source_ids": ["FINANCIAL-GOLD"],
            "trigger_claim_ids": [],
            "mutations": [
                {
                    "operation": "CORRECT",
                    "object_type": "MODEL_NODE",
                    "object_id": "CELL:Inputs!C42",
                    "field": "value",
                    "from": "0.156",
                    "to": "0.146",
                    "unit": "%",
                }
            ],
        }

    def run_incremental(self):
        return apply_state_transition(
            self.compiled["current_graph"],
            [self.event],
            self.compiled["execution_mapping"],
            self.materiality,
            self.authority,
        )

    @staticmethod
    def values(graph):
        return {
            node["model_node_id"]: node.get("value")
            for node in graph["model_nodes"]
        }

    def test_gold_compiles_to_complete_typed_acyclic_runtime_graph(self):
        report = self.compiled["adapter_report"]
        self.assertEqual(report["model_node_count"], 14318)
        self.assertEqual(report["directed_model_edge_count"], 30996)
        self.assertEqual(report["position_dependency_count"], 30996)
        self.assertEqual(report["drives_edge_count"], 30996)
        self.assertEqual(report["gold_formula_count"], 11381)
        self.assertEqual(report["compiled_formula_count"], 11381)
        self.assertEqual(report["compiled_scalar_formula_count"], 11371)
        self.assertEqual(report["compiled_typed_formula_count"], 10)
        self.assertEqual(report["skipped_non_scalar_formula_count"], 0)
        self.assertEqual(report["skipped_formulas"], [])
        self.assertEqual(report["hydration_error_count"], 0)
        self.assertTrue(report["directed_graph_acyclic"])
        self.assertTrue(
            all(
                edge["relation_type"] == "DRIVES"
                for edge in self.compiled["execution_mapping"][
                    "directed_model_edges"
                ]
            )
        )
        self.assertEqual(
            len(self.compiled["current_graph"]["position_dependencies"]),
            30996,
        )
        coverage_reasons = {
            item["reason_code"]
            for item in self.compiled["execution_mapping"]["coverage_limits"]
        }
        self.assertNotIn("MISSING_MODEL_DEPENDENCY", coverage_reasons)
        self.assertNotIn("MISSING_EXECUTABLE_DIRECTION", coverage_reasons)

        current_values = self.values(self.compiled["current_graph"])
        cash_flows = current_values[
            "SEM:STANDALONE_BASE:RETURN_CASH_FLOW_VECTOR"
        ]
        self.assertEqual(cash_flows["value_type"], "DATED_CASH_FLOW_VECTOR")
        self.assertEqual(cash_flows["day_count_basis"], "ACT_365")
        self.assertEqual(len(cash_flows["cash_flows"]), 2)
        acquisition_cash_flows = current_values[
            "SEM:ACQUISITION_BASE:RETURN_CASH_FLOW_VECTOR"
        ]["cash_flows"]
        self.assertEqual(
            acquisition_cash_flows[:2],
            [
                {"date": "2026-03-31", "amount": "-62.0"},
                {"date": "2027-06-30", "amount": "-5.0"},
            ],
        )
        self.assertGreater(
            Decimal(str(current_values["CELL:Ownership_Returns!L4"])),
            Decimal("0"),
        )

    def test_gold_affected_set_explains_real_drives_path(self):
        affected = compute_affected_set(
            self.compiled["current_graph"],
            ["CELL:Inputs!C42"],
            self.compiled["execution_mapping"],
        )
        first_output = next(
            item
            for item in affected["affected_set"]
            if item["object_id"] == "CELL:Scenario_Drivers!C7"
        )
        self.assertTrue(
            any(path.endswith(":DRIVES") for path in first_output["reached_via"]),
            first_output["reached_via"],
        )

    def test_gold_margin_shock_propagates_to_debt_and_moic(self):
        result = self.run_incremental()
        output = result["transition_output"]
        current_values = self.values(self.compiled["current_graph"])
        candidate_values = self.values(result["candidate_state"]["current_graph"])

        expected_first_quarter_ebitda = (
            Decimal(str(current_values["CELL:Scenario_Drivers!C5"]))
            * Decimal("0.146")
        )
        self.assertEqual(
            Decimal(str(candidate_values["CELL:Scenario_Drivers!C7"])),
            expected_first_quarter_ebitda,
        )
        self.assertEqual(
            candidate_values["CELL:SB_Base!C10"],
            candidate_values["CELL:Scenario_Drivers!C7"],
        )
        self.assertGreater(
            Decimal(str(candidate_values["CELL:SB_Base!V92"])),
            Decimal(str(current_values["CELL:SB_Base!V92"])),
        )
        self.assertLess(
            Decimal(str(candidate_values["CELL:Ownership_Returns!K4"])),
            Decimal(str(current_values["CELL:Ownership_Returns!K4"])),
        )
        self.assertLess(
            Decimal(str(candidate_values["CELL:Ownership_Returns!L4"])),
            Decimal(str(current_values["CELL:Ownership_Returns!L4"])),
        )
        self.assertNotEqual(
            candidate_values["SEM:STANDALONE_BASE:RETURN_CASH_FLOW_VECTOR"],
            current_values["SEM:STANDALONE_BASE:RETURN_CASH_FLOW_VECTOR"],
        )
        self.assertEqual(
            candidate_values["SEM:STANDALONE_BASE:RETURN_CASH_FLOW_VECTOR"][
                "cash_flows"
            ][-1]["amount"],
            candidate_values["CELL:Ownership_Returns!J4"],
        )

        affected_ids = {item["object_id"] for item in output["affected_set"]}
        for object_id in (
            "CELL:Inputs!C42",
            "CELL:Scenario_Drivers!C7",
            "CELL:SB_Base!C10",
            "CELL:SB_Base!V92",
            "CELL:Ownership_Returns!K4",
            "SEM:STANDALONE_BASE:RETURN_CASH_FLOW_VECTOR",
            "CELL:Ownership_Returns!L4",
        ):
            self.assertIn(object_id, affected_ids)
        self.assertEqual(len(output["affected_set"]), 823)
        self.assertEqual(len(output["recomputed_values"]), 628)
        recomputed_ids = {
            item["object_id"] for item in output["recomputed_values"]
        }
        self.assertIn(
            "SEM:STANDALONE_BASE:RETURN_CASH_FLOW_VECTOR", recomputed_ids
        )
        self.assertIn("CELL:Ownership_Returns!L4", recomputed_ids)
        self.assertFalse(
            any("XIRR" in item["reason_code"] for item in output["coverage_limits"])
        )
        self.assertEqual(output["materiality_assessment"]["overall_class"], "M2_GATE_AUTHORITY")
        self.assertEqual(output["partial_settlement_status"]["candidate"], "PARTIAL")
        self.assertEqual(
            output["candidate_current_approved_delta"]["current"], []
        )
        self.assertEqual(
            output["candidate_current_approved_delta"]["approved"], []
        )
        self.assertEqual(current_values["CELL:Inputs!C42"], "0.156")
        self.assertEqual(candidate_values["CELL:Inputs!C42"], "0.146")

    def test_gold_run_is_deterministic(self):
        first = self.run_incremental()
        second = self.run_incremental()
        self.assertEqual(first["transition_output"], second["transition_output"])
        self.assertEqual(first["candidate_state"], second["candidate_state"])
        self.assertEqual(
            first["transition_output"]["replay_hash"],
            second["transition_output"]["replay_hash"],
        )

    def test_gold_incremental_equals_full_global_recompute(self):
        comparison = compare_incremental_global(
            self.compiled["current_graph"],
            [self.event],
            self.compiled["execution_mapping"],
            self.materiality,
            self.authority,
        )
        self.assertTrue(comparison["equivalent"], comparison["comparisons"])
        self.assertTrue(all(comparison["comparisons"].values()))


if __name__ == "__main__":
    unittest.main()
