#!/usr/bin/env python3
"""Claim input feeds illuminate only supported external model inputs."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.claim_input_feed import build_overrides
from tools.model_evaluator import evaluate_mapping


def _mapping() -> dict:
    return {
        "model_nodes": [
            {"model_node_id": "MN-A", "computational_form": "DIRECT_INPUT",
             "initial_value": None, "unit": "MM_USD"},
            {"model_node_id": "MN-B", "computational_form": "DIRECT_INPUT",
             "initial_value": None, "unit": "MM_USD"},
            {"model_node_id": "MN-SUM", "computational_form": "DIRECT_FORMULA",
             "unit": "MM_USD"},
        ],
        "formulas": [
            {"formula_id": "F-SUM", "evaluation_type": "ARITHMETIC",
             "output_id": "MN-SUM", "expression_or_function_ref": "a + b",
             "variable_binding": {"a": "MN-A", "b": "MN-B"}},
        ],
    }


def _claim(claim_id: str, value: object, unit: str = "MM_USD") -> dict:
    return {"claim_id": claim_id, "value": value, "unit": unit}


class ClaimInputFeedTests(unittest.TestCase):
    def test_claim_feeds_direct_input_and_reaches_evaluator_output(self):
        mapping = _mapping()
        claims = [_claim("C-A", "12.5"), _claim("C-B", 2.5)]
        bindings = [
            {"claim_id": "C-A", "model_node_id": "MN-A"},
            {"claim_id": "C-B", "model_node_id": "MN-B"},
        ]
        overrides, unfed = build_overrides(claims, mapping, bindings)

        self.assertEqual(overrides, {"MN-A": 12.5, "MN-B": 2.5})
        self.assertEqual(unfed, [])
        self.assertEqual(evaluate_mapping(mapping, overrides)["values"]["MN-SUM"], 15.0)

    def test_node_without_claim_is_reported_and_absent(self):
        overrides, unfed = build_overrides(
            [_claim("C-A", 1)], _mapping(),
            [{"claim_id": "C-A", "model_node_id": "MN-A"}],
        )

        self.assertNotIn("MN-B", overrides)
        record = next(item for item in unfed if item["node_id"] == "MN-B")
        self.assertEqual(record["reason"], "no claim bound to this node")

    def test_disagreeing_claims_feed_nothing_and_name_both(self):
        claims = [_claim("C-1", 10), _claim("C-2", 11)]
        bindings = [
            {"claim_id": "C-1", "model_node_id": "MN-A"},
            {"claim_id": "C-2", "model_node_id": "MN-A"},
        ]
        overrides, unfed = build_overrides(claims, _mapping(), bindings)

        self.assertNotIn("MN-A", overrides)
        records = [item for item in unfed if item["node_id"] == "MN-A"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["claim_ids"], ["C-1", "C-2"])
        self.assertEqual(
            [item["value"] for item in records[0]["competing_claims"]],
            [10.0, 11.0],
        )

    def test_computed_node_is_never_overridden(self):
        overrides, unfed = build_overrides(
            [_claim("C-OUT", 999)], _mapping(),
            [{"claim_id": "C-OUT", "model_node_id": "MN-SUM"}],
        )

        self.assertNotIn("MN-SUM", overrides)
        self.assertEqual({item["node_id"] for item in unfed}, {"MN-A", "MN-B"})

    def test_unit_mismatch_is_reported_not_silently_converted(self):
        overrides, unfed = build_overrides(
            [_claim("C-A", 12.5, "EUR")], _mapping(),
            [{"claim_id": "C-A", "model_node_id": "MN-A"}],
        )

        self.assertNotIn("MN-A", overrides)
        record = next(item for item in unfed if item["node_id"] == "MN-A")
        self.assertEqual(record["reason"], "unit mismatch")
        self.assertEqual(record["claims"][0]["unit"], "EUR")

    def test_declared_million_dollar_conversion_is_applied(self):
        overrides, _ = build_overrides(
            [_claim("C-A", 12.5, "$m")], _mapping(),
            {"claim_id": "C-A", "model_node_id": "MN-A"},
        )
        self.assertEqual(overrides["MN-A"], 12.5)

    def test_non_numeric_claim_keeps_node_unfed(self):
        overrides, unfed = build_overrides(
            [_claim("C-A", "10-12")], _mapping(),
            [{"claim_id": "C-A", "model_node_id": "MN-A"}],
        )
        self.assertNotIn("MN-A", overrides)
        record = next(item for item in unfed if item["node_id"] == "MN-A")
        self.assertEqual(record["reason"], "claim value non-numeric")
        self.assertEqual(record["claims"][0]["claim_id"], "C-A")

    def test_claim_position_and_position_node_bindings_compose(self):
        claims = [_claim("C-A", 3)]
        bindings = [
            {"claim_id": "C-A", "position_id": "CP-A"},
            {"position_id": "CP-A", "model_node_id": "MN-A"},
        ]
        overrides, _ = build_overrides(claims, _mapping(), bindings)
        self.assertEqual(overrides, {"MN-A": 3.0})


class RealBundleTests(unittest.TestCase):
    BUNDLE = ROOT / "pipeline_out/e3/K-PRE/adapter_alpha/execution_mapping.json"
    CLAIMS = ROOT / "pipeline_out/e3/K-PRE/e3_claims.json"

    def test_every_real_direct_input_is_fed_or_explained(self):
        mapping = json.loads(self.BUNDLE.read_text(encoding="utf-8"))
        claims = json.loads(self.CLAIMS.read_text(encoding="utf-8"))
        overrides, unfed = build_overrides(claims, mapping)
        direct = [node for node in mapping["model_nodes"]
                  if node.get("computational_form") == "DIRECT_INPUT"]

        self.assertEqual(len(overrides), 2)
        self.assertEqual(len(overrides) + len(unfed), len(direct))
        self.assertTrue(set(overrides).isdisjoint(
            item["node_id"] for item in unfed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
