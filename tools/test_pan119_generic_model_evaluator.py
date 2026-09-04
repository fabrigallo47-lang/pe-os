#!/usr/bin/env python3
"""PAN-119: one evaluator for every deal, and honest about what it cannot do.

A deal's model must not be a hand-written Python module. The mapping already
declares formulas with input_ids, output_id, an expression and a
variable_binding — enough to execute without knowing anything about the
deal. These tests pin the engine and, just as importantly, pin the refusals:
a model that quietly invents the half it could not compute is worse than one
that says so.

    python3 tools/test_pan119_generic_model_evaluator.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.model_evaluator import (
    UnsupportedExpression, delta_for_claim, evaluate_expression, evaluate_mapping,
)


def _mapping(**overrides) -> dict:
    """A two-hop mapping: two given inputs, a sum, then a ratio of the sum."""
    base = {
        "model_nodes": [
            {"model_node_id": "MN-A", "computational_form": "DIRECT_INPUT", "initial_value": 10.0},
            {"model_node_id": "MN-B", "computational_form": "DIRECT_INPUT", "initial_value": 4.0},
            {"model_node_id": "MN-SUM", "computational_form": "DIRECT_FORMULA", "formula_id": "F-SUM"},
            {"model_node_id": "MN-HALF", "computational_form": "DIRECT_FORMULA", "formula_id": "F-HALF"},
        ],
        "formulas": [
            # Deliberately listed downstream-first: resolution must not depend
            # on the order the mapping happens to serialise them in.
            {"formula_id": "F-HALF", "evaluation_type": "ARITHMETIC",
             "output_id": "MN-HALF", "input_ids": ["MN-SUM"],
             "expression_or_function_ref": "total / 2",
             "variable_binding": {"total": "MN-SUM"}},
            {"formula_id": "F-SUM", "evaluation_type": "ARITHMETIC",
             "output_id": "MN-SUM", "input_ids": ["MN-A", "MN-B"],
             "expression_or_function_ref": "a + b",
             "variable_binding": {"a": "MN-A", "b": "MN-B"}},
        ],
    }
    base.update(overrides)
    return base


class ExpressionTests(unittest.TestCase):
    def test_arithmetic_evaluates(self):
        self.assertEqual(evaluate_expression("a + b * 2", {"a": 1.0, "b": 3.0}), 7.0)
        self.assertEqual(evaluate_expression("-(x) / 4", {"x": 8.0}), -2.0)

    def test_a_workbook_is_not_a_trust_boundary(self):
        """These expressions arrive from compiled spreadsheets. Anything that
        is not arithmetic over declared operands must be refused, not run."""
        for hostile in ("__import__('os').system('true')",
                        "open('/etc/passwd').read()",
                        "a.__class__",
                        "MAX(1, 2)"):
            with self.subTest(expression=hostile):
                with self.assertRaises(UnsupportedExpression):
                    evaluate_expression(hostile, {"a": 1.0})

    def test_an_unbound_operand_is_refused_not_defaulted(self):
        with self.assertRaises(UnsupportedExpression):
            evaluate_expression("firm_ebitda / 4", {})


class MappingTests(unittest.TestCase):
    def test_it_chains_without_knowing_the_deal(self):
        result = evaluate_mapping(_mapping())
        self.assertEqual(result["values"]["MN-SUM"], 14.0)
        self.assertEqual(result["values"]["MN-HALF"], 7.0)
        self.assertEqual(result["computed_count"], 2)

    def test_resolution_order_is_not_serialisation_order(self):
        """F-HALF is listed first but depends on F-SUM's output."""
        result = evaluate_mapping(_mapping())
        self.assertEqual(result["computed_order"], ["F-SUM", "F-HALF"])

    def test_an_unexecutable_type_becomes_a_declared_limit(self):
        mapping = _mapping()
        mapping["formulas"][0]["evaluation_type"] = "XIRR"
        result = evaluate_mapping(mapping)
        self.assertNotIn("MN-HALF", result["values"])
        reasons = [limit["reason"] for limit in result["declared_limits"]]
        self.assertTrue(any("XIRR" in reason for reason in reasons))

    def test_a_missing_input_starves_its_dependants_visibly(self):
        mapping = _mapping()
        mapping["model_nodes"][0].pop("initial_value")
        result = evaluate_mapping(mapping)
        self.assertNotIn("MN-SUM", result["values"])
        self.assertNotIn("MN-HALF", result["values"])
        blocked = {limit.get("node_id") for limit in result["declared_limits"]}
        self.assertIn("MN-A", blocked)      # the missing seed itself
        self.assertIn("MN-SUM", blocked)    # and what it starved

    def test_a_cycle_is_reported_not_looped_forever(self):
        mapping = _mapping()
        mapping["formulas"].append({
            "formula_id": "F-CYCLE-A", "evaluation_type": "ARITHMETIC",
            "output_id": "MN-C1", "input_ids": ["MN-C2"],
            "expression_or_function_ref": "x + 1", "variable_binding": {"x": "MN-C2"}})
        mapping["formulas"].append({
            "formula_id": "F-CYCLE-B", "evaluation_type": "ARITHMETIC",
            "output_id": "MN-C2", "input_ids": ["MN-C1"],
            "expression_or_function_ref": "y + 1", "variable_binding": {"y": "MN-C1"}})
        result = evaluate_mapping(mapping)
        self.assertEqual(result["values"]["MN-HALF"], 7.0)   # unaffected
        cycle_limits = [l for l in result["declared_limits"]
                        if l.get("formula_id", "").startswith("F-CYCLE")]
        self.assertEqual(len(cycle_limits), 2)


class DeltaTests(unittest.TestCase):
    def test_applying_a_claim_moves_only_what_depends_on_it(self):
        delta = delta_for_claim(_mapping(), "MN-A", 20.0)
        moved = {item["node_id"]: (item["old"], item["new"])
                 for item in delta["updated_nodes"]}
        self.assertEqual(moved["MN-A"], (10.0, 20.0))
        self.assertEqual(moved["MN-SUM"], (14.0, 24.0))
        self.assertEqual(moved["MN-HALF"], (7.0, 12.0))
        self.assertNotIn("MN-B", moved)


class RealMappingTests(unittest.TestCase):
    """Proof it is generic: a real deal's mapping, no deal-specific code."""

    BUNDLE = ROOT / "pipeline_out/e3/K-PRE/adapter_alpha/execution_mapping.json"

    def test_it_runs_a_real_compiled_mapping(self):
        if not self.BUNDLE.exists():
            self.skipTest("compiled bundle not present in this checkout")
        mapping = json.loads(self.BUNDLE.read_text())
        result = evaluate_mapping(mapping)
        # Whatever it computes, it must account for every formula: computed,
        # or declared as a limit with a reason. Silence is the failure mode.
        accounted = set(result["computed_order"]) | {
            limit.get("formula_id") for limit in result["declared_limits"]}
        for formula in mapping.get("formulas", []):
            self.assertIn(formula["formula_id"], accounted,
                          f"{formula['formula_id']} was neither computed nor declared")


if __name__ == "__main__":
    unittest.main(verbosity=2)
