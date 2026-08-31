from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "dynamics"))

from runtime.panta_transition_engine import (  # noqa: E402
    _evaluate_rule_switches,
    _execute_formula,
)
from tools.formula_compiler import (  # noqa: E402
    compile_formulas,
    recalculate_compilation,
)


class PAN66FormulaCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = {
            "schema": "source-graph-1",
            "workbook": "pan66.xlsx",
            "digest": "sha256:pan66-fixture",
            "defined_names": {},
            "cells": {
                "INPUTS!A1": {"kind": "number", "value": 100},
                "INPUTS!A2": {"kind": "number", "value": 20},
                # Aggregate ranges ignore text cells, just as Excel does.
                "INPUTS!A3": {"kind": "text", "value": "n/a"},
                "MODEL!B1": {
                    "kind": "formula",
                    "value": "=Inputs!A1+Inputs!A2*2",
                    "evaluated_value": 140,
                    "precedents": ["INPUTS!A1", "INPUTS!A2"],
                },
                "MODEL!B2": {
                    "kind": "formula",
                    "value": "=SUM(Inputs!A1:A3)",
                    "evaluated_value": 120,
                    "precedents": ["INPUTS!A1:A3"],
                },
                "MODEL!B3": {
                    "kind": "formula",
                    "value": "=MAX(Inputs!A1,Inputs!A2)",
                    "evaluated_value": 100,
                    "precedents": ["INPUTS!A1", "INPUTS!A2"],
                },
                "MODEL!B4": {
                    "kind": "formula",
                    "value": "=MIN(Inputs!A1,Inputs!A2)",
                    "evaluated_value": 20,
                    "precedents": ["INPUTS!A1", "INPUTS!A2"],
                },
                "MODEL!B5": {
                    "kind": "formula",
                    "value": "=IF(Inputs!A1>90,Inputs!A2,0)",
                    "evaluated_value": 20,
                    "precedents": ["INPUTS!A1", "INPUTS!A2"],
                },
                "MODEL!B6": {
                    "kind": "formula",
                    "value": "=B1+B2",
                    "evaluated_value": 260,
                    "precedents": ["MODEL!B1", "MODEL!B2"],
                },
                # Fixed point C1=C2*.5+1; C2=C1*.5+1 has the unique solution 2,2.
                "MODEL!C1": {
                    "kind": "formula",
                    "value": "=C2*0.5+1",
                    "evaluated_value": 2,
                    "precedents": ["MODEL!C2"],
                },
                "MODEL!C2": {
                    "kind": "formula",
                    "value": "=C1*0.5+1",
                    "evaluated_value": 2,
                    "precedents": ["MODEL!C1"],
                },
            },
        }
        self.bindings = {
            "schema_version": "model-binding-resolution/1.0",
            "input_digest": "sha256:pan65-fixture",
            "bindings": [
                {"locator": locator, "model_node_id": self._node_id(locator)}
                for locator, cell in self.source["cells"].items()
                if cell["kind"] in {"number", "formula"}
            ],
        }

    @staticmethod
    def _node_id(locator: str) -> str:
        return "MN-" + locator.replace("!", "-")

    def compile(self, source=None, bindings=None):
        return compile_formulas(source or self.source, bindings or self.bindings)

    def test_all_declared_functions_compile_and_sum_range_is_expanded(self) -> None:
        result = self.compile()

        self.assertEqual(result["status"], "COMPILED")
        self.assertEqual(result["stats"]["source_formula_count"], 8)
        self.assertEqual(result["stats"]["compiled_formula_count"], 8)
        self.assertEqual(result["stats"]["function_counts"], {
            "IF": 1, "MAX": 1, "MIN": 1, "SUM": 1,
        })
        formulas = {item["workbook_cell_ref"]: item for item in result["formulas"]}
        sum_formula = formulas["MODEL!B2"]
        self.assertNotIn("SUM", sum_formula["expression_or_function_ref"])
        self.assertIn(" + ", sum_formula["expression_or_function_ref"])
        self.assertEqual(
            sum_formula["input_ids"],
            [self._node_id("INPUTS!A1"), self._node_id("INPUTS!A2")],
        )
        self.assertNotIn(self._node_id("INPUTS!A3"), sum_formula["input_ids"])
        self.assertIn("MAX(", formulas["MODEL!B3"]["expression_or_function_ref"])
        self.assertIn("MIN(", formulas["MODEL!B4"]["expression_or_function_ref"])

    def test_if_emits_runtime_formula_and_governed_rule_switch(self) -> None:
        result = self.compile()
        formula = next(
            item for item in result["formulas"] if item["workbook_cell_ref"] == "MODEL!B5"
        )
        switch = result["rule_switches"][0]

        self.assertIn("IF(", formula["expression_or_function_ref"])
        self.assertEqual(switch["selector_input_ids"], [self._node_id("INPUTS!A1")])
        self.assertEqual(switch["dependent_ids"], [self._node_id("MODEL!B5")])
        self.assertEqual(len(switch["branches"]), 2)
        self.assertIn("> 90", switch["branches"][0]["condition"])
        self.assertIn("<= 90", switch["branches"][1]["condition"])
        self.assertEqual(switch["source_ref"], "pan66.xlsx:MODEL!B5")

    def test_general_if_condition_is_evaluated_without_reducing_it_to_one_selector(self) -> None:
        source = json.loads(json.dumps(self.source))
        source["cells"]["MODEL!D1"] = {
            "kind": "formula",
            "value": "=IF(Inputs!A1+Inputs!A2>100,Inputs!A1,Inputs!A2)",
            "evaluated_value": 100,
            "precedents": ["INPUTS!A1", "INPUTS!A2"],
        }
        bindings = json.loads(json.dumps(self.bindings))
        bindings["bindings"].append({
            "locator": "MODEL!D1", "model_node_id": self._node_id("MODEL!D1")
        })
        compilation = self.compile(source, bindings)
        switch = next(
            item for item in compilation["rule_switches"]
            if item["output_id"] == self._node_id("MODEL!D1")
        )

        self.assertEqual(switch["condition_evaluation_type"], "GENERAL_EXPRESSION")
        self.assertEqual(set(switch["selector_input_ids"]), {
            self._node_id("INPUTS!A1"), self._node_id("INPUTS!A2"),
        })
        evaluation = _evaluate_rule_switches(
            [{
                "object_id": self._node_id("INPUTS!A1"),
                "field": "value",
                "from": 100,
                "to": 70,
            }],
            compilation,
            {
                self._node_id("INPUTS!A1"): {"object": {"value": 70}},
                self._node_id("INPUTS!A2"): {"object": {"value": 20}},
            },
        )
        self.assertEqual(evaluation["coverage_limits"], [])
        result = next(
            item for item in evaluation["results"]
            if item["rule_id"] == switch["rule_switch_id"]
        )
        self.assertTrue(result["from"].endswith("-TRUE"))
        self.assertTrue(result["to"].endswith("-FALSE"))

    def test_compiled_expressions_execute_in_the_production_decimal_runtime(self) -> None:
        result = self.compile()
        formulas = {item["workbook_cell_ref"]: item for item in result["formulas"]}
        registry = {
            self._node_id("INPUTS!A1"): {"object": {"value": 100}},
            self._node_id("INPUTS!A2"): {"object": {"value": 20}},
        }

        for locator, expected in (("MODEL!B2", "120.0"), ("MODEL!B3", "100.0"),
                                  ("MODEL!B4", "20.0"), ("MODEL!B5", "20.0")):
            with self.subTest(locator=locator):
                actual, error = _execute_formula(formulas[locator], registry)
                self.assertIsNone(error)
                self.assertEqual(actual, expected)

    def test_recalculation_matches_every_available_l1_value(self) -> None:
        compilation = self.compile()
        result = recalculate_compilation(compilation, self.source, self.bindings)

        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["coverage_limits"], [])
        self.assertEqual(result["stats"], {
            "compiled_formula_count": 8,
            "recalculated_formula_count": 8,
            "expected_value_count": 8,
            "matched_value_count": 8,
            "mismatched_value_count": 0,
        })
        self.assertTrue(all(item["status"] == "MATCH" for item in result["comparisons"]))

        no_oracle = json.loads(json.dumps(self.source))
        for cell in no_oracle["cells"].values():
            cell.pop("evaluated_value", None)
            cell.pop("cached_value", None)
        without_expected = recalculate_compilation(
            compilation, no_oracle, self.bindings
        )
        self.assertEqual(without_expected["status"], "NO_EXPECTED_VALUES")

    def test_formula_cycle_becomes_extract_v3_fixed_point_config(self) -> None:
        result = self.compile()

        self.assertEqual(result["stats"]["cyclic_component_count"], 1)
        config = result["cyclic_component_solver_configs"][0]
        self.assertEqual(config["component_type"], "NUMERICAL_SCC")
        self.assertEqual(config["method"], "DAMPED_FIXED_POINT")
        self.assertEqual(set(config["member_ids"]), {
            self._node_id("MODEL!C1"), self._node_id("MODEL!C2"),
        })
        self.assertEqual(len(config["equations"]), 2)
        self.assertEqual(
            config["uniqueness_condition"],
            "CONVERGED_FROM_DECLARED_INITIALIZATION_WITHIN_TOLERANCE",
        )

    def test_formula_downstream_of_cycle_runs_only_after_component_settles(self) -> None:
        source = json.loads(json.dumps(self.source))
        source["cells"]["MODEL!C3"] = {
            "kind": "formula",
            "value": "=C1+C2",
            "evaluated_value": 4,
            "precedents": ["MODEL!C1", "MODEL!C2"],
        }
        bindings = json.loads(json.dumps(self.bindings))
        bindings["bindings"].append({
            "locator": "MODEL!C3", "model_node_id": self._node_id("MODEL!C3")
        })

        compilation = self.compile(source, bindings)
        result = recalculate_compilation(compilation, source, bindings)

        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["coverage_limits"], [])
        self.assertAlmostEqual(
            float(result["values"][self._node_id("MODEL!C3")]), 4.0, places=6
        )

    def test_unsupported_formula_and_every_downstream_formula_are_human_stops(self) -> None:
        source = json.loads(json.dumps(self.source))
        source["cells"]["MODEL!D1"] = {
            "kind": "formula", "value": "=AVERAGE(Inputs!A1:Inputs!A2)",
            "precedents": ["INPUTS!A1:INPUTS!A2"],
        }
        source["cells"]["MODEL!D2"] = {
            "kind": "formula", "value": "=D1+1", "precedents": ["MODEL!D1"],
        }
        bindings = json.loads(json.dumps(self.bindings))
        bindings["bindings"].extend([
            {"locator": "MODEL!D1", "model_node_id": self._node_id("MODEL!D1")},
            {"locator": "MODEL!D2", "model_node_id": self._node_id("MODEL!D2")},
        ])

        result = self.compile(source, bindings)
        reasons = {item["reason_code"] for item in result["coverage_limits"]}
        compiled_outputs = {item["output_id"] for item in result["formulas"]}

        self.assertEqual(result["status"], "COMPILED_WITH_COVERAGE_LIMITS")
        self.assertIn("UNSUPPORTED_EXCEL_FUNCTION", reasons)
        self.assertIn("UPSTREAM_FORMULA_NOT_COMPILED", reasons)
        self.assertNotIn(self._node_id("MODEL!D1"), compiled_outputs)
        self.assertNotIn(self._node_id("MODEL!D2"), compiled_outputs)

    def test_missing_or_ambiguous_r6_binding_is_never_guessed(self) -> None:
        missing = json.loads(json.dumps(self.bindings))
        missing["bindings"] = [
            item for item in missing["bindings"] if item["locator"] != "INPUTS!A2"
        ]
        missing_result = self.compile(bindings=missing)
        self.assertIn(
            "MISSING_R6_BINDING",
            {item["reason_code"] for item in missing_result["coverage_limits"]},
        )

        ambiguous = json.loads(json.dumps(self.bindings))
        ambiguous["bindings"].append({
            "locator": "INPUTS!A1", "model_node_id": "MN-SECOND-A1",
        })
        ambiguous_result = self.compile(bindings=ambiguous)
        self.assertIn(
            "AMBIGUOUS_R6_BINDING",
            {item["reason_code"] for item in ambiguous_result["coverage_limits"]},
        )

    def test_defined_name_cross_sheet_absolute_refs_and_percent_compile(self) -> None:
        source = {
            "schema": "source-graph-1",
            "workbook": "names.xlsx",
            "defined_names": {"RevenueBase": "'Inputs'!$A$1"},
            "cells": {
                "INPUTS!A1": {"kind": "number", "value": 100},
                "INPUTS!A2": {"kind": "number", "value": 20},
                "MODEL!A1": {
                    "kind": "formula",
                    "value": "=RevenueBase*(1+'Inputs'!$A$2%)",
                    "evaluated_value": 120,
                },
            },
        }
        bindings = [
            {"locator": locator, "model_node_id": self._node_id(locator)}
            for locator in source["cells"]
        ]

        compilation = compile_formulas(source, bindings)
        verification = recalculate_compilation(compilation, source, bindings)

        self.assertEqual(compilation["status"], "COMPILED")
        self.assertEqual(verification["status"], "MATCH")
        self.assertEqual(
            verification["values"][self._node_id("MODEL!A1")], "120.0"
        )

    def test_compilation_is_deterministic_under_cell_and_binding_order(self) -> None:
        first = self.compile()
        source = {**self.source, "cells": dict(reversed(list(self.source["cells"].items())))}
        bindings = {
            **self.bindings,
            "bindings": list(reversed(self.bindings["bindings"])),
        }
        second = self.compile(source, bindings)

        self.assertEqual(first, second)

    def test_cli_writes_versioned_contract_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_path = directory / "source.json"
            bindings_path = directory / "bindings.json"
            output_path = directory / "compiled.json"
            source_path.write_text(json.dumps(self.source), encoding="utf-8")
            bindings_path.write_text(json.dumps(self.bindings), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "formula_compiler.py"),
                    "--source-graph", str(source_path),
                    "--bindings", str(bindings_path),
                    "--out", str(output_path),
                    "--verify",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["schema_version"], "excel-formula-compilation/1.0")
        self.assertEqual(payload["recalculation"]["status"], "MATCH")
        self.assertIn("8/8 formulas compiled", result.stdout)


if __name__ == "__main__":
    unittest.main()
