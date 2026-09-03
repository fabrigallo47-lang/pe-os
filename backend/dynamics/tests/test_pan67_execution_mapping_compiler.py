from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.execution_mapping_compiler import (  # noqa: E402
    ExecutionMappingCompileError,
    populate_execution_mapping,
)
from tools.formula_compiler import recalculate_compilation  # noqa: E402
from tools.bridge_v7 import _normalize_execution_mapping, _validate_execution  # noqa: E402
from tools.workbook_model_compiler import compile_workbook_formula_graphs  # noqa: E402


class PAN67ExecutionMappingCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = {
            "schema": "source-graph-1",
            "workbook": "pan67.xlsx",
            "digest": "sha256:pan67-fixture",
            "defined_names": {},
            "cells": {
                "INPUTS!A1": {"kind": "number", "value": 100},
                "INPUTS!A2": {"kind": "number", "value": 20},
                "MODEL!B1": {
                    "kind": "formula",
                    "value": "=Inputs!A1+Inputs!A2",
                    "evaluated_value": 120,
                    "precedents": ["INPUTS!A1", "INPUTS!A2"],
                },
                "MODEL!B2": {
                    "kind": "formula",
                    "value": "=IF(Inputs!A1>50,B1,Inputs!A2)",
                    "evaluated_value": 120,
                    "precedents": ["INPUTS!A1", "MODEL!B1", "INPUTS!A2"],
                },
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
                "MODEL!D1": {
                    "kind": "formula",
                    "value": "=ROUND(Inputs!A1,0)",
                    "evaluated_value": 100,
                    "precedents": ["INPUTS!A1"],
                },
                "MODEL!D2": {
                    "kind": "formula",
                    "value": "=D1+1",
                    "evaluated_value": 101,
                    "precedents": ["MODEL!D1"],
                },
            },
        }
        self.bindings = {
            "schema_version": "model-binding-resolution/1.0",
            "input_digest": "sha256:pan65-fixture",
            "status": "RESOLVED_WITH_WARNINGS",
            "bindings": [
                {
                    "binding_id": f"BIND-{index:02d}",
                    "locator": locator,
                    "model_node_id": self.node_id(locator),
                    "concept_id": f"CONCEPT-{index:02d}",
                    "identity": {
                        "period": "FY2026",
                        "scope": "ALDERSTONE",
                    },
                    "unit": "USD_M",
                    "reason_codes": ["PAN65_RESOLVED"],
                }
                for index, locator in enumerate(self.source["cells"], start=1)
            ],
            "coverage_limits": [
                {
                    "coverage_limit_id": "COVERAGE-PAN65-DECLARED",
                    "reason_code": "AMBIGUOUS_IDENTITY",
                    "message": "A separate semantic proposal remains unresolved.",
                    "identity": {"concept_id": "CONCEPT-UNRESOLVED"},
                    "candidate_locators": ["MODEL!Z99"],
                    "resolution": "HUMAN_STOP",
                }
            ],
        }
        self.base = {
            "mapping_version": "v7",
            "canonical_graph_hash": "sha256:" + "1" * 64,
            "model_nodes": [
                {
                    "model_node_id": self.node_id("INPUTS!A1"),
                    "label": "Institutional revenue driver",
                    "computational_form": "DIRECT_INPUT",
                    "unit": "USD_M",
                    "period": "FY2026",
                    "perimeter": "Alderstone consolidated",
                    "initial_value": "100.0",
                }
            ],
            "directed_model_edges": [],
            "position_model_directions": [
                {
                    "binding_id": "PMB-REVENUE",
                    "position_id": "CP-REVENUE",
                    "model_node_id": self.node_id("INPUTS!A1"),
                    "direction": "POSITION_DRIVES_MODEL",
                }
            ],
            "formulas": [],
            "rule_switches": [],
            "inverse_solver_configs": [],
            "model_controls": [
                {
                    "control_id": "CTRL-PAN67",
                    "scope_ids": [self.node_id("MODEL!B2")],
                    "pass_condition": "Compiled output is finite",
                }
            ],
            "cyclic_component_solver_configs": [],
            "coverage_limits": [],
        }

    @staticmethod
    def node_id(locator: str) -> str:
        return "MN-" + locator.replace("!", "-")

    def populate(self, mapping=None, bindings=None):
        return populate_execution_mapping(
            self.source,
            bindings if bindings is not None else self.bindings,
            self.base if mapping is None else mapping,
        )

    def test_populates_formulas_drives_switches_scc_and_preserves_governance(self) -> None:
        result = self.populate()

        self.assertEqual(result["formula_compilation"]["status"], "COMPILED_WITH_COVERAGE_LIMITS")
        self.assertEqual(result["formula_compilation"]["stats"]["compiled_formula_count"], 4)
        self.assertEqual(len(result["rule_switches"]), 1)
        self.assertEqual(len(result["cyclic_component_solver_configs"]), 1)
        self.assertEqual(result["position_model_directions"], self.base["position_model_directions"])
        self.assertEqual(result["model_controls"], self.base["model_controls"])

        formula_ids = {formula["formula_id"] for formula in result["formulas"]}
        self.assertTrue(result["directed_model_edges"])
        for edge in result["directed_model_edges"]:
            self.assertEqual(edge["relation_type"], "DRIVES")
            self.assertIn(edge["formula_or_function_ref"], formula_ids)
            self.assertEqual(
                edge["relation_rule"]["rule_id"],
                "FORMULA_PRECEDENT_DRIVES",
            )
            self.assertEqual(edge["relation_rule"]["mode"], "DETERMINISTIC")
        self.assertEqual(result["relation_audit"]["unclassified_edge_count"], 0)
        self.assertEqual(result["relation_audit"]["deterministic_edge_pct"], 100.0)
        expected = {
            (input_id, formula["output_id"], formula["formula_id"])
            for formula in result["formulas"]
            for input_id in formula["input_ids"]
        }
        actual = {
            (
                edge["from_model_node_id"],
                edge["to_model_node_id"],
                edge["formula_or_function_ref"],
            )
            for edge in result["directed_model_edges"]
        }
        self.assertEqual(actual, expected)

        nodes = {item["model_node_id"]: item for item in result["model_nodes"]}
        self.assertEqual(
            nodes[self.node_id("INPUTS!A1")]["label"],
            "Institutional revenue driver",
        )
        self.assertEqual(
            nodes[self.node_id("INPUTS!A1")]["initial_value"], "100.0"
        )
        self.assertEqual(
            nodes[self.node_id("MODEL!B1")]["computational_form"],
            "DIRECT_FORMULA",
        )
        self.assertEqual(
            nodes[self.node_id("MODEL!C1")]["computational_form"],
            "NUMERICAL_CYCLE",
        )
        self.assertEqual(
            nodes[self.node_id("MODEL!D1")]["computational_form"],
            "MONITOR_ONLY",
        )

    def test_human_stops_from_resolver_and_formula_compiler_are_explicit(self) -> None:
        result = self.populate()
        limits = {item["reason_code"]: item for item in result["coverage_limits"]}

        self.assertIn("AMBIGUOUS_IDENTITY", limits)
        self.assertEqual(
            limits["AMBIGUOUS_IDENTITY"]["limit_id"],
            "COVERAGE-PAN65-DECLARED",
        )
        self.assertEqual(limits["AMBIGUOUS_IDENTITY"]["scope_ids"], ["MODEL!Z99"])
        self.assertIn("UNSUPPORTED_EXCEL_FUNCTION", limits)
        self.assertIn("UPSTREAM_FORMULA_NOT_COMPILED", limits)
        compiled_outputs = {item["output_id"] for item in result["formulas"]}
        self.assertNotIn(self.node_id("MODEL!D1"), compiled_outputs)
        self.assertNotIn(self.node_id("MODEL!D2"), compiled_outputs)

    def test_existing_formula_edges_are_migrated_to_governed_drives(self) -> None:
        mapping = {
            **self.base,
            "directed_model_edges": [{
                "edge_id": "DME-LEGACY",
                "from_model_node_id": self.node_id("INPUTS!A1"),
                "to_model_node_id": self.node_id("MODEL!B1"),
                "formula_or_function_ref": "FORMULA-LEGACY",
                "control_ids": [],
            }],
        }

        result = self.populate(mapping=mapping)
        migrated = next(
            edge
            for edge in result["directed_model_edges"]
            if edge["edge_id"] == "DME-LEGACY"
        )

        self.assertEqual(migrated["relation_type"], "DRIVES")
        self.assertEqual(
            migrated["relation_rule"]["rule_id"],
            "FORMULA_PRECEDENT_DRIVES",
        )

    def test_result_is_idempotent_and_schema_conformant(self) -> None:
        first = self.populate()
        second = self.populate(mapping=first)
        self.assertEqual(first, second)

        schema_path = (
            ROOT
            / "backend"
            / "dynamics"
            / "schemas"
            / "state_transition_execution_mapping.schema.json"
        )
        try:
            import jsonschema
        except ImportError:  # pragma: no cover - optional in minimal public installs
            jsonschema = None
        if jsonschema is not None:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            errors = sorted(
                jsonschema.Draft202012Validator(schema).iter_errors(first),
                key=lambda error: list(error.path),
            )
            self.assertEqual([error.message for error in errors], [])

    def test_populated_mapping_recalculates_every_executable_formula(self) -> None:
        source = json.loads(json.dumps(self.source))
        del source["cells"]["MODEL!D1"]
        del source["cells"]["MODEL!D2"]
        bindings = json.loads(json.dumps(self.bindings))
        bindings["coverage_limits"] = []
        bindings["bindings"] = [
            item
            for item in bindings["bindings"]
            if item["locator"] not in {"MODEL!D1", "MODEL!D2"}
        ]
        result = populate_execution_mapping(source, bindings, self.base)
        recalculation = recalculate_compilation(result, source, bindings)

        self.assertEqual(recalculation["status"], "MATCH")
        self.assertEqual(recalculation["stats"]["matched_value_count"], 4)
        self.assertEqual(recalculation["stats"]["mismatched_value_count"], 0)

    def test_existing_formula_for_same_output_is_never_silently_overwritten(self) -> None:
        mapping = json.loads(json.dumps(self.base))
        mapping["formulas"] = [
            {
                "formula_id": "F-INSTITUTIONAL",
                "input_ids": [self.node_id("INPUTS!A1")],
                "output_id": self.node_id("MODEL!B1"),
                "expression_or_function_ref": "institutional_formula()",
            }
        ]
        with self.assertRaisesRegex(ExecutionMappingCompileError, "already belongs"):
            self.populate(mapping=mapping)

    def test_two_locators_cannot_collapse_to_one_model_node(self) -> None:
        bindings = json.loads(json.dumps(self.bindings))
        bindings["bindings"][1]["model_node_id"] = bindings["bindings"][0][
            "model_node_id"
        ]

        with self.assertRaisesRegex(ExecutionMappingCompileError, "bound to both"):
            self.populate(bindings=bindings)

    def test_pan55_live_compiler_uses_pan67_when_bindings_are_available(self) -> None:
        envelope = {
            "schema": "workbook-formula-graphs-1.0",
            "workbooks": [
                {
                    "source_filename": "pan67.xlsx",
                    "graph": self.source,
                }
            ],
        }
        graph = compile_workbook_formula_graphs(
            envelope,
            "pan67-case",
            binding_resolution=self.bindings,
        )

        self.assertEqual(
            graph["compiler"]["mode"], "PAN67_RESOLVED_FORMULA_COMPILATION"
        )
        self.assertEqual(_validate_execution(graph), [])
        self.assertTrue(
            all(
                formula["evaluation_type"] == "SAFE_DECIMAL_EXPRESSION"
                for formula in graph["formulas"]
            )
        )
        self.assertTrue(
            all(
                edge["relation_type"] == "DRIVES"
                for edge in graph["directed_model_edges"]
            )
        )

        runtime_mapping = _normalize_execution_mapping(
            graph,
            case_positions={},
            pm_directions=[],
            canonical_current_hash="2" * 64,
        )
        self.assertFalse(
            any(
                switch.get("declaration_type")
                == "NO_INSTITUTIONAL_OVERRIDES_DECLARED"
                for switch in runtime_mapping["rule_switches"]
            )
        )

    def test_cli_writes_the_populated_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source_path = directory / "source.json"
            bindings_path = directory / "bindings.json"
            mapping_path = directory / "mapping.json"
            output_path = directory / "execution_mapping.json"
            source_path.write_text(json.dumps(self.source), encoding="utf-8")
            bindings_path.write_text(json.dumps(self.bindings), encoding="utf-8")
            mapping_path.write_text(json.dumps(self.base), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "execution_mapping_compiler.py"),
                    "--source-graph",
                    str(source_path),
                    "--bindings",
                    str(bindings_path),
                    "--mapping",
                    str(mapping_path),
                    "--out",
                    str(output_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["formula_compilation"]["compiler_version"], "pan67-1.0")
            self.assertIn("DRIVES edges", completed.stdout)


if __name__ == "__main__":
    unittest.main()
