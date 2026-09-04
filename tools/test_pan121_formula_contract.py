#!/usr/bin/env python3
"""PAN-121: an unexecutable mapping must be visibly unexecutable.

The execution mapping's shape promises a specification — expression,
variable_binding, input_ids, output_id — but Keystone's was reverse-
documented from tools/keystone_model.py (each formula's source_ref points
back into it), so its bindings hold workbook cells, other formulas' ids,
sub-expressions, Python source and bare literals rather than model node
ids. Two formulas out of twenty-two satisfy the contract, by coincidence.

That is not "a few broken formulas": it is a mapping that describes a
hand-written module instead of specifying a computation. These tests pin
the classifier that keeps the difference measurable, so nobody concludes
from a passing FORMULAS_EXECUTABLE check that a generic evaluator can be
any deal's default yet.

    python3 tools/test_pan121_formula_contract.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.formula_contract import audit_formula, audit_mapping

NODES = {"MN-A", "MN-B", "MN-QUARTERLY-CASH"}
FORMULAS = {"F-GOOD", "F-NET-INCOME"}


def _formula(**overrides) -> dict:
    base = {
        "formula_id": "F-GOOD",
        "output_id": "MN-OUT",
        "evaluation_type": "ARITHMETIC",
        "expression_or_function_ref": "a + b",
        "variable_binding": {"a": "MN-A", "b": "MN-B"},
    }
    base.update(overrides)
    return base


class ExecutableTests(unittest.TestCase):
    def test_a_well_formed_formula_passes(self):
        result = audit_formula(_formula(), NODES, FORMULAS)
        self.assertTrue(result["executable"], result["reasons"])


class RefusalTests(unittest.TestCase):
    """Each refusal must name what is wrong, not just fail."""

    def _reasons(self, **overrides) -> str:
        return " | ".join(audit_formula(_formula(**overrides), NODES, FORMULAS)["reasons"])

    def test_an_operand_with_no_binding(self):
        """F-QUARTERLY-FIRM-EBITDA: "firm_ebitda / 4" with an empty binding."""
        reasons = self._reasons(expression_or_function_ref="firm_ebitda / 4",
                                variable_binding={})
        self.assertIn("used but not bound", reasons)
        self.assertIn("firm_ebitda", reasons)

    def test_a_binding_that_is_a_workbook_cell(self):
        """F-SOURCES-USES-EQUITY binds financing_fees to Inputs!B31."""
        reasons = self._reasons(expression_or_function_ref="a + fees",
                                variable_binding={"a": "MN-A", "fees": "Inputs!B31"})
        self.assertIn("WORKBOOK_REFERENCE", reasons)

    def test_a_binding_that_is_a_workbook_range(self):
        reasons = self._reasons(expression_or_function_ref="a + sofr",
                                variable_binding={"a": "MN-A",
                                                  "sofr": "Scenario_Drivers!C33:V33"})
        self.assertIn("WORKBOOK_REFERENCE", reasons)

    def test_a_node_with_a_temporal_qualifier_is_not_a_scalar_node(self):
        """MN-QUARTERLY-CASH[prior] is a real concept the scalar evaluator
        has no notion of — it must not be mistaken for the bare node."""
        reasons = self._reasons(expression_or_function_ref="a + prior",
                                variable_binding={"a": "MN-A",
                                                  "prior": "MN-QUARTERLY-CASH[prior]"})
        self.assertIn("TEMPORAL_QUALIFIER", reasons)

    def test_a_binding_that_names_another_formula(self):
        reasons = self._reasons(expression_or_function_ref="a + ni",
                                variable_binding={"a": "MN-A", "ni": "F-NET-INCOME"})
        self.assertIn("FORMULA_ID", reasons)

    def test_a_binding_that_is_a_sub_expression(self):
        reasons = self._reasons(
            expression_or_function_ref="a + cff",
            variable_binding={"a": "MN-A", "cff": "sponsor_contrib + term_amort"})
        self.assertIn("EXPRESSION_OR_PROSE", reasons)

    def test_a_binding_that_is_python_source(self):
        reasons = self._reasons(
            expression_or_function_ref="a + amort",
            variable_binding={"a": "MN-A",
                              "amort": "min(0.015, beg) if beg > 0 else 0"})
        self.assertIn("EXPRESSION_OR_PROSE", reasons)

    def test_a_binding_that_is_a_bare_literal(self):
        reasons = self._reasons(expression_or_function_ref="a * mip",
                                variable_binding={"a": "MN-A", "mip": "0.0875"})
        self.assertIn("BARE_LITERAL", reasons)

    def test_a_binding_that_looks_like_a_node_but_is_not_one(self):
        reasons = self._reasons(expression_or_function_ref="a + ghost",
                                variable_binding={"a": "MN-A", "ghost": "MN-DOES-NOT-EXIST"})
        self.assertIn("UNKNOWN_NODE", reasons)

    def test_a_spreadsheet_function_call(self):
        """F-REVOLVER-DRAW-REPAY uses MAX(); the evaluator is arithmetic only."""
        reasons = self._reasons(
            expression_or_function_ref="MAX(0, a - b)",
            variable_binding={"a": "MN-A", "b": "MN-B"})
        self.assertIn("MAX()", reasons)

    def test_a_non_arithmetic_evaluation_type(self):
        reasons = self._reasons(evaluation_type="DATED_VECTOR_ARITHMETIC")
        self.assertIn("DATED_VECTOR_ARITHMETIC", reasons)

    def test_a_binding_nothing_reads_is_reported_too(self):
        """Bound-but-unused means the expression and the binding table
        disagree about what the formula computes — silence would hide it."""
        reasons = self._reasons(variable_binding={"a": "MN-A", "b": "MN-B",
                                                  "unused": "MN-QUARTERLY-CASH"})
        self.assertIn("never used", reasons)

    def test_prose_that_is_not_valid_python_still_gets_a_reason(self):
        """F-GROSS-XIRR's binding is prose with a × character. A parse error
        must not become a crash — it is still an auditable formula."""
        result = audit_formula(
            _formula(expression_or_function_ref="[-invested, 0 × (n-1), +proceeds]"),
            NODES, FORMULAS)
        self.assertFalse(result["executable"])
        self.assertTrue(result["reasons"])


class RealMappingTests(unittest.TestCase):
    BUNDLE = ROOT / "pipeline_out/e3/K-PRE/adapter_alpha/execution_mapping.json"

    def test_every_formula_gets_a_verdict(self):
        if not self.BUNDLE.exists():
            self.skipTest("compiled bundle not present in this checkout")
        report = audit_mapping(json.loads(self.BUNDLE.read_text()))
        self.assertEqual(len(report["formulas"]), report["formula_count"])
        for entry in report["formulas"]:
            if not entry["executable"]:
                self.assertTrue(entry["reasons"],
                                f"{entry['formula_id']} refused without a reason")

    def test_the_measured_gap_is_still_the_gap(self):
        """Pins the finding itself: if this number moves, the mapping's
        provenance changed and G1/G3 need re-reading, not a test edit."""
        if not self.BUNDLE.exists():
            self.skipTest("compiled bundle not present in this checkout")
        report = audit_mapping(json.loads(self.BUNDLE.read_text()))
        self.assertLess(report["executable_count"], report["formula_count"] / 2,
                        "mapping became mostly executable — re-read PAN-121")


if __name__ == "__main__":
    unittest.main(verbosity=2)
