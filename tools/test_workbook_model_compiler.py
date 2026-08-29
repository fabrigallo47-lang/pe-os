from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.bridge_v7 import _validate_execution  # noqa: E402
from tools.workbook_model_compiler import compile_workbook_formula_graphs  # noqa: E402


FIXTURE = ROOT / "tools" / "fixtures" / "pan55_workbook_formula_graph.json"


class WorkbookModelCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = compile_workbook_formula_graphs(FIXTURE, case_id="synthetic-case")
        self.nodes = self.graph["model_nodes"]

    def test_acyclic_chain_preserves_formula_text_and_precedent_edges(self) -> None:
        c1 = "MN-SYNTHETIC-CASE-XLSX-MODEL-C1"
        d1 = "MN-SYNTHETIC-CASE-XLSX-MODEL-D1"
        b1 = "MN-SYNTHETIC-CASE-XLSX-MODEL-B1"
        formulas = {item["output_id"]: item for item in self.graph["formulas"]}
        self.assertEqual(formulas[c1]["expression_or_function_ref"], "=B1*2")
        self.assertEqual(formulas[c1]["operand_bindings"], {"MODEL!B1": b1})
        self.assertEqual(formulas[d1]["input_ids"], [c1])
        pairs = {(edge["from_model_node_id"], edge["to_model_node_id"])
                 for edge in self.graph["directed_model_edges"]}
        self.assertIn((b1, c1), pairs)
        self.assertIn((c1, d1), pairs)

    def test_referenced_raw_cell_is_input_and_noise_is_excluded(self) -> None:
        input_id = "MN-SYNTHETIC-CASE-XLSX-MODEL-B1"
        self.assertEqual(self.nodes[input_id]["computational_form"], "INPUT")
        self.assertEqual(self.nodes[input_id]["value_current"], 10)
        self.assertNotIn("MN-SYNTHETIC-CASE-XLSX-MODEL-F9", self.nodes)

    def test_cycle_is_declared_unresolved_without_solver_fabrication(self) -> None:
        cycles = self.graph["cyclic_component_models"]
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0]["status"], "HUMAN_STOP")
        self.assertEqual(cycles[0]["component_type"], "UNRESOLVED_SCC")
        self.assertEqual(set(cycles[0]["member_ids"]), {
            "MN-SYNTHETIC-CASE-XLSX-MODEL-B3",
            "MN-SYNTHETIC-CASE-XLSX-MODEL-C3",
        })
        self.assertEqual(self.graph["cyclic_component_solver_configs"], [])

    def test_output_meets_v7_bridge_contract_with_honest_declarations(self) -> None:
        self.assertEqual(_validate_execution(self.graph), [])
        rule = self.graph["rule_switches"][0]
        self.assertEqual(rule["declaration_type"], "NO_INSTITUTIONAL_OVERRIDES_DECLARED")
        control = self.graph["model_controls"][0]
        self.assertEqual(control["fail_outcome"], "HUMAN_STOP")


if __name__ == "__main__":
    unittest.main()
