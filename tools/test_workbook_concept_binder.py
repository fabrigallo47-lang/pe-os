#!/usr/bin/env python3
"""G7: propose cell -> concept bindings, and never admit one.

The safety property is the important one. A wrong binding produces a wrong
number that looks exactly like a right one, so no path through this module may
turn a proposal into a binding the compiler will consume.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.workbook_concept_binder import (  # noqa: E402
    binding_resolution, is_unit_only, parse_ref, propose, row_label,
    score_proposals, verify_refs,
)

GRAPHS = ROOT / "pipeline_out/e3/K-IC/adapter_alpha/workbook_formula_graphs.json"
MAPPING = ROOT / "pipeline_out/e3/K-IC/adapter_alpha/execution_mapping.json"


def _sheet(rows: dict[tuple[int, int], tuple[str, str]]):
    return {pos: {"value": v, "kind": k} for pos, (v, k) in rows.items()}


class LabelTests(unittest.TestCase):
    def test_nearest_label_to_the_left_is_used(self) -> None:
        cells = _sheet({(5, 1): ("Revenue", "text"), (5, 2): ("$mm", "text")})
        self.assertEqual(row_label(cells, 5, before_col=3), "Revenue")

    def test_a_units_column_is_not_a_concept_name(self) -> None:
        """The single correction that moved agreement 28.6% -> 71.4% on the real
        workbook: 10 of 28 rows were resolving to '$mm', 'days' or '%'."""
        for unit in ("$mm", "%", "days", "x", "bps"):
            with self.subTest(unit=unit):
                self.assertTrue(is_unit_only(unit))
        self.assertFalse(is_unit_only("Revenue"))
        self.assertFalse(is_unit_only("Exit multiple"))

    def test_numbers_are_not_labels(self) -> None:
        cells = _sheet({(5, 1): ("Revenue", "text"), (5, 2): ("12.4", "number")})
        self.assertEqual(row_label(cells, 5, before_col=3), "Revenue")

    def test_scan_stops_rather_than_reaching_across_the_sheet(self) -> None:
        cells = _sheet({(5, 1): ("Revenue", "text")})
        self.assertIsNone(row_label(cells, 5, before_col=40))


class RefParsingTests(unittest.TestCase):
    def test_cell_and_range_are_both_understood(self) -> None:
        self.assertEqual(parse_ref("Inputs!B3"), ("Inputs", 3, 2, 3))
        self.assertEqual(parse_ref("Scenario_Drivers!C5:V5"),
                         ("Scenario_Drivers", 5, 3, 5))
        self.assertEqual(parse_ref("book.xlsx:Inputs!B3"), ("Inputs", 3, 2, 3))

    def test_prose_is_refused_rather_than_guessed(self) -> None:
        """37 of compiler_v7's 74 workbook_refs are prose, not references:
        'Scenario_Drivers (down row)', 'QoE report', 'CIM / management accounts'.
        Guessing a cell from those is exactly what must not happen."""
        for ref in ("Scenario_Drivers (down row)", "QoE report",
                    "CIM / management accounts", "S&U_Opening!BS_check", ""):
            with self.subTest(ref=ref):
                self.assertIsNone(parse_ref(ref))


class AdmissionTests(unittest.TestCase):
    def test_proposals_are_never_born_admitted(self) -> None:
        graph = {"cells": {"Inputs!A3": {"sheet": "Inputs", "row": 3, "col": 1,
                                         "kind": "text", "value": "Enterprise value"}}}
        concepts = [{"model_node_id": "MN-EV", "label": "Enterprise Value (entry)"}]
        proposals = propose(graph, concepts, {"MN-EV": "Inputs!B3"})
        self.assertTrue(proposals)
        self.assertTrue(all(p["status"] == "PROPOSED" for p in proposals))
        self.assertEqual(binding_resolution(proposals), [],
                         "a PROPOSED binding must never reach the compiler")

    def test_only_an_admitted_proposal_becomes_a_binding(self) -> None:
        admitted = [{"model_node_id": "MN-EV", "workbook_ref": "book.xlsx:Inputs!B3",
                     "status": "ADMITTED"}]
        self.assertEqual(binding_resolution(admitted),
                         [{"locator": "Inputs!B3", "model_node_id": "MN-EV"}])

    def test_a_proposal_carries_the_evidence_it_was_made_from(self) -> None:
        """A human admitting one must see what it was based on, not a score."""
        graph = {"cells": {"Inputs!A3": {"sheet": "Inputs", "row": 3, "col": 1,
                                         "kind": "text", "value": "Enterprise value"}}}
        concepts = [{"model_node_id": "MN-EV", "label": "Enterprise Value (entry)"}]
        p = propose(graph, concepts, {"MN-EV": "Inputs!B3"})[0]
        for field in ("cell_label", "concept_label", "workbook_ref", "reason", "score"):
            self.assertIn(field, p)
        self.assertEqual(p["cell_label"], "Enterprise value")


class RefVerificationTests(unittest.TestCase):
    """A ref is worthless unless the cell holds the number the concept claims."""

    def _graph(self, b_value, c_value):
        return {"cells": {
            "Inputs!A46": {"sheet": "Inputs", "row": 46, "col": 1, "kind": "text",
                           "value": "Standalone Base - Exit multiple", "locator": "Inputs!A46"},
            "Inputs!B46": {"sheet": "Inputs", "row": 46, "col": 2, "kind": "text",
                           "value": b_value, "locator": "Inputs!B46"},
            "Inputs!C46": {"sheet": "Inputs", "row": 46, "col": 3, "kind": "number",
                           "value": c_value, "locator": "Inputs!C46"},
        }}

    def test_a_ref_landing_on_the_unit_cell_is_caught(self) -> None:
        """The real defect: Inputs row 3 is label|value|unit but row 46 is
        label|unit|value, so every scenario ref written as column B hit 'x'."""
        concepts = [{"model_node_id": "MN-BASE-EXIT-MULT", "workbook_ref": "Inputs!B46",
                     "initial_value": 9.0, "label": "Standalone Base Exit Multiple"}]
        found = verify_refs(self._graph("x", 9.0), concepts)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["cell_is_unit"])
        self.assertIn("Inputs!C46", found[0]["value_found_at"],
                      "the report must say where the value actually sits")

    def test_a_correct_ref_reports_nothing(self) -> None:
        concepts = [{"model_node_id": "MN-BASE-EXIT-MULT", "workbook_ref": "Inputs!C46",
                     "initial_value": 9.0, "label": "Standalone Base Exit Multiple"}]
        self.assertEqual(verify_refs(self._graph("x", 9.0), concepts), [])

    def test_a_real_value_disagreement_is_reported_not_reconciled(self) -> None:
        """Once the ref is right, four Keystone multiples genuinely disagree with
        the workbook (7.5 vs 8.0, 10.0 vs 9.5, 9.5 vs 9.0, 8.0 vs 8.5). Whether
        the workbook is stale or the underwriting is deliberately different is a
        human question; overwriting either side would erase the evidence."""
        concepts = [{"model_node_id": "MN-X", "workbook_ref": "Inputs!C46",
                     "initial_value": 7.5, "label": "Exit Multiple"}]
        found = verify_refs(self._graph("x", 8.0), concepts)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["verdict"], "cell holds a different number")
        self.assertEqual(found[0]["declared_value"], 7.5)
        self.assertEqual(found[0]["cell_value"], 8.0)


class RealWorkbookTests(unittest.TestCase):
    @unittest.skipUnless(GRAPHS.exists() and MAPPING.exists(), "K-IC bundle absent")
    def test_label_adjacency_carries_most_of_the_resolvable_bindings(self) -> None:
        graph = json.loads(GRAPHS.read_text())["workbooks"][0]["graph"]
        mapping = json.loads(MAPPING.read_text())
        refs = {c["model_node_id"]: c.get("workbook_ref") or ""
                for c in mapping["model_nodes"] if c.get("workbook_ref")}
        report = score_proposals(propose(graph, mapping["model_nodes"], refs))
        self.assertGreaterEqual(
            report["agreement_rate"], 0.65,
            "label adjacency regressed; the units-column skip is the load-bearing part",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
