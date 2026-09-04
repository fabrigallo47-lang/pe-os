#!/usr/bin/env python3
"""PAN-122: a deal with no workbook still gets a model, from declared rows.

Compiling a workbook covers a deal that already has one. A deal that does
not — an early venture case — still has an analyst who can declare the
nodes as rows. Those rows must compile into the same mapping shape the
generic evaluator runs, so that "no workbook" never means "needs bespoke
Python".

The two refusals pinned here are the point of the module. The Silexara
corpus marks one row `unadmitted` (an analyst hypothesis) and gives it the
value "4-8" months; admitting either the row or the number would launder a
guess into a fact.

    python3 tools/test_pan122_model_nodes_to_mapping.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.model_nodes_to_mapping import rows_to_mapping


def _row(**overrides) -> dict:
    base = {
        "node_id": "M-001", "metric": "instrumented_area", "period": "2026-06-06/07",
        "perimeter": "observed test zone", "entity": "one field cell",
        "scenario": "independent controlled test", "version": "build 0.8.4",
        "value": "18", "unit": "ha", "source": "SRC-19",
        "epistemic_status": "observed", "admission_status": "proposed",
    }
    base.update(overrides)
    return base


class AdmissionTests(unittest.TestCase):
    def test_a_proposed_row_becomes_a_node(self):
        mapping = rows_to_mapping([_row()], "CASE-X")
        self.assertEqual(len(mapping["model_nodes"]), 1)
        node = mapping["model_nodes"][0]
        self.assertEqual(node["model_node_id"], "M-001")
        self.assertEqual(node["initial_value"], 18.0)
        self.assertEqual(node["computational_form"], "DIRECT_INPUT")

    def test_an_unadmitted_row_is_kept_out_and_said_so(self):
        """The corpus marks an analyst hypothesis `unadmitted`. Loading it
        would turn a guess into a node other numbers get computed from."""
        mapping = rows_to_mapping([_row(node_id="M-008", admission_status="unadmitted",
                                        value="4-8")], "CASE-X")
        self.assertEqual(mapping["model_nodes"], [])
        self.assertEqual(len(mapping["declared_exclusions"]), 1)
        self.assertIn("unadmitted", mapping["declared_exclusions"][0]["reason"])

    def test_a_row_without_an_id_is_reported_not_invented(self):
        mapping = rows_to_mapping([_row(node_id="")], "CASE-X")
        self.assertEqual(mapping["model_nodes"], [])
        self.assertTrue(mapping["declared_exclusions"])


class ValueTests(unittest.TestCase):
    def test_a_non_numeric_value_leaves_the_node_uncomputable(self):
        """"4-8 months" is a real answer. Coercing it to 4, 8 or 6 would
        invent precision the analyst deliberately withheld."""
        mapping = rows_to_mapping([_row(value="4-8")], "CASE-X")
        node = mapping["model_nodes"][0]
        self.assertIsNone(node["initial_value"])
        self.assertEqual(node["value_raw"], "4-8")
        self.assertTrue(any("not a number" in item["reason"]
                            for item in mapping["declared_exclusions"]))

    def test_zero_is_a_value_not_a_missing_one(self):
        """production_revenue = 0 is a deterministic classification in the
        corpus, not an absence. Treating 0 as falsy would erase it."""
        mapping = rows_to_mapping([_row(node_id="M-006", value="0")], "CASE-X")
        self.assertEqual(mapping["model_nodes"][0]["initial_value"], 0.0)
        self.assertEqual(mapping["declared_exclusions"], [])


class IdentityTests(unittest.TestCase):
    def test_one_metric_two_perimeters_stays_two_nodes(self):
        """detection_recall is 0.94 for a heavy vehicle at 300m on dry
        ground and 0.41 for a quiet crawler at 120m on mixed ground. The
        corpus's own note: rows with different identities must not be
        compared as though they were the same number."""
        rows = [
            _row(node_id="M-003", metric="detection_recall", value="0.94",
                 perimeter="heavy vehicle <=300m, dry ground", unit="ratio"),
            _row(node_id="M-004", metric="detection_recall", value="0.41",
                 perimeter="quiet crawler <=120m, mixed ground", unit="ratio"),
        ]
        mapping = rows_to_mapping(rows, "CASE-X")
        self.assertEqual(len(mapping["model_nodes"]), 2)
        perimeters = {n["perimeter"] for n in mapping["model_nodes"]}
        self.assertEqual(len(perimeters), 2)
        values = {n["initial_value"] for n in mapping["model_nodes"]}
        self.assertEqual(values, {0.94, 0.41})

    def test_declared_rows_carry_no_formulas(self):
        """Rows state what is known, never how to compute it. Guessing a
        relationship between rows that merely look related is the failure
        this whole exercise exists to avoid."""
        mapping = rows_to_mapping([_row()], "CASE-X")
        self.assertEqual(mapping["formulas"], [])


class EvaluatorHandoffTests(unittest.TestCase):
    def test_the_output_runs_on_the_generic_evaluator(self):
        """The whole point: no bespoke Python between rows and a running
        model."""
        from tools.model_evaluator import evaluate_mapping
        mapping = rows_to_mapping([_row(), _row(node_id="M-002", value="70")], "CASE-X")
        mapping["model_nodes"].append({
            "model_node_id": "M-CALC", "computational_form": "DIRECT_FORMULA",
            "formula_id": "F-GAP"})
        mapping["formulas"] = [{
            "formula_id": "F-GAP", "evaluation_type": "ARITHMETIC",
            "output_id": "M-CALC", "input_ids": ["M-001", "M-002"],
            "expression_or_function_ref": "envelope - measured",
            "variable_binding": {"envelope": "M-002", "measured": "M-001"}}]
        result = evaluate_mapping(mapping)
        self.assertEqual(result["values"]["M-CALC"], 52.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
