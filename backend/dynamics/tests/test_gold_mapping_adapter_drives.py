import unittest

from runtime import compile_gold_to_runtime_inputs, compute_affected_set


class GoldMappingDrivesTests(unittest.TestCase):
    def setUp(self):
        self.gold_mapping = {
            "case_id": "PAN-67-SYNTHETIC",
            "mapping_version": "PAN-67-R7",
            "model_nodes": [
                {
                    "model_node_id": "CELL:Inputs!A1",
                    "name": "Input",
                    "workbook_locator": "Inputs!A1",
                    "baseline_value": "3",
                },
                {
                    "model_node_id": "CELL:Calc!B1",
                    "name": "Output",
                    "workbook_locator": "Calc!B1",
                    "baseline_value": "6",
                },
            ],
            "directed_model_edges": [
                {
                    "edge_id": "EDGE-INPUT-OUTPUT",
                    "from_model_node_id": "CELL:Inputs!A1",
                    "to_model_node_id": "CELL:Calc!B1",
                    "formula_or_function_ref": "FORM-OUTPUT",
                }
            ],
            "formulas": [
                {
                    "formula_id": "FORM-OUTPUT",
                    "source_type": "WORKBOOK_FORMULA",
                    "workbook_locator": "Calc!B1",
                    "input_ids": ["CELL:Inputs!A1"],
                    "output_id": "CELL:Calc!B1",
                    "expression": "=Inputs!A1*2",
                }
            ],
            "coverage_limits": [
                {
                    "limit_id": "OLD-DEPENDENCY-LIMIT",
                    "reason_code": "MISSING_MODEL_DEPENDENCY",
                },
                {
                    "limit_id": "OLD-DIRECTION-LIMIT",
                    "reason_code": "MISSING_EXECUTABLE_DIRECTION",
                },
                {
                    "limit_id": "REAL-SOURCE-LIMIT",
                    "reason_code": "MISSING_SOURCE_COVERAGE",
                },
            ],
        }

    def test_compiles_formulas_and_typed_drives_dependencies(self):
        compiled = compile_gold_to_runtime_inputs(self.gold_mapping)
        mapping = compiled["execution_mapping"]
        graph = compiled["current_graph"]
        report = compiled["adapter_report"]

        self.assertEqual(len(mapping["formulas"]), 1)
        self.assertEqual(
            mapping["formulas"][0]["expression_or_function_ref"],
            "v00000*2",
        )
        self.assertEqual(
            mapping["directed_model_edges"][0]["relation_type"],
            "DRIVES",
        )
        self.assertEqual(
            graph["position_dependencies"],
            [
                {
                    "edge_id": "EDGE-INPUT-OUTPUT",
                    "from_position_id": "CELL:Inputs!A1",
                    "to_position_id": "CELL:Calc!B1",
                    "relation_type": "DRIVES",
                    "semantic_role": "drives_model_calculation",
                    "traversal_rule": (
                        "propagate downstream through the executable model graph"
                    ),
                }
            ],
        )
        self.assertEqual(report["drives_edge_count"], 1)
        self.assertEqual(report["position_dependency_count"], 1)

    def test_real_edges_propagate_and_reached_via_names_drives_path(self):
        compiled = compile_gold_to_runtime_inputs(self.gold_mapping)
        affected = compute_affected_set(
            compiled["current_graph"],
            ["CELL:Inputs!A1"],
            compiled["execution_mapping"],
        )
        output = next(
            item
            for item in affected["affected_set"]
            if item["object_id"] == "CELL:Calc!B1"
        )

        self.assertIn("CELL:Calc!B1", affected["visited_ids"])
        self.assertIn("EDGE-INPUT-OUTPUT:DRIVES", output["reached_via"])
        self.assertNotIn(
            "EDGE-INPUT-OUTPUT:MODEL_DEPENDENCY", output["reached_via"]
        )

    def test_closes_only_topology_limits_proven_resolved(self):
        compiled = compile_gold_to_runtime_inputs(self.gold_mapping)
        mapping_reasons = {
            item["reason_code"]
            for item in compiled["execution_mapping"]["coverage_limits"]
        }
        graph_reasons = {
            item["reason_code"]
            for item in compiled["current_graph"]["coverage_gaps"]
        }

        self.assertEqual(mapping_reasons, {"MISSING_SOURCE_COVERAGE"})
        self.assertEqual(graph_reasons, {"MISSING_SOURCE_COVERAGE"})
        self.assertEqual(
            compiled["adapter_report"][
                "closed_coverage_limit_reason_codes"
            ],
            ["MISSING_EXECUTABLE_DIRECTION", "MISSING_MODEL_DEPENDENCY"],
        )


if __name__ == "__main__":
    unittest.main()
