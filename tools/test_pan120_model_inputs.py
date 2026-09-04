#!/usr/bin/env python3
"""PAN-120: admitted claims fill only directly supported model inputs.

    python3 tools/test_pan120_model_inputs.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.model_inputs import build_model_inputs


def _mapping() -> dict:
    return {"model_nodes": [
        {"model_node_id": "MN-QOE-EBITDA", "computational_form": "DIRECT_INPUT", "initial_value": None},
        {"model_node_id": "MN-BASE-GROWTH", "computational_form": "DIRECT_INPUT", "initial_value": None},
        {"model_node_id": "MN-EV", "computational_form": "DIRECT_INPUT", "initial_value": 108.0},
        {"model_node_id": "MN-OUTPUT", "computational_form": "DIRECT_FORMULA"},
    ]}


def _claim(claim_id: str, statement: str, value: object) -> dict:
    return {"claim_id": claim_id, "statement": statement, "value": value}


class ModelInputsTests(unittest.TestCase):
    def test_string_number_becomes_override_for_direct_input(self):
        result = build_model_inputs(_mapping(), [_claim("C-1", "QoE normalized EBITDA is $11.9m.", "11.9")])
        self.assertEqual(result["overrides"], {"MN-QOE-EBITDA": 11.9})
        self.assertEqual(result["unfilled_nodes"], [{"node_id": "MN-BASE-GROWTH", "reason": "no numeric DIRECT claim bound"}])

    def test_non_numeric_range_is_refused_not_coerced(self):
        result = build_model_inputs(_mapping(), [_claim("C-1", "QoE normalized EBITDA is $8-12m.", "8-12")])
        self.assertEqual(result["overrides"], {})
        self.assertEqual(result["unbound_claims"][0]["reason"], "claim value is not a finite numeric scalar")
        self.assertEqual(result["unfilled_nodes"][0]["node_id"], "MN-BASE-GROWTH")
        self.assertEqual(result["unfilled_nodes"][1]["node_id"], "MN-QOE-EBITDA")

    def test_different_values_conflict_and_leave_node_empty(self):
        claims = [
            _claim("C-1", "QoE normalized EBITDA is $11.9m.", "11.9"),
            _claim("C-2", "QoE normalized EBITDA is $12.1m.", "12.1"),
        ]
        result = build_model_inputs(_mapping(), claims)
        self.assertEqual(result["overrides"], {})
        self.assertEqual({item["claim_id"] for item in result["unbound_claims"]}, {"C-1", "C-2"})
        self.assertEqual(result["unfilled_nodes"][1]["reason"], "conflicting numeric claims")

    def test_same_value_is_not_a_conflict(self):
        claims = [
            _claim("C-1", "QoE normalized EBITDA is $11.9m.", "11.9"),
            _claim("C-2", "QoE normalized EBITDA is $11.9m.", 11.9),
        ]
        result = build_model_inputs(_mapping(), claims)
        self.assertEqual(result["overrides"], {"MN-QOE-EBITDA": 11.9})
        self.assertEqual(result["unbound_claims"], [])

    def test_preseeded_input_is_not_overridden_or_silently_matched(self):
        result = build_model_inputs(_mapping(), [_claim("C-1", "Enterprise value is $108m.", "108")])
        self.assertEqual(result["overrides"], {})
        self.assertEqual(result["unbound_claims"][0]["reason"], "no DIRECT_INPUT binding proposed")

    def test_compiler_metric_blocks_a_broad_textual_false_positive(self):
        claims = {"claims": [_claim("C-1", "Seller-adjusted EBITDA margin is 17.2%.", "17.2")],
                  "extraction_metadata": {"compiler_fields_per_claim": [
                      {"claim_id": "C-1", "metric": "EBITDA Margin"}]}}
        result = build_model_inputs(_mapping(), claims)
        self.assertEqual(result["overrides"], {})
        self.assertEqual(result["unbound_claims"][0]["reason"], "no DIRECT_INPUT binding proposed")


class RealBundleTests(unittest.TestCase):
    BUNDLE = ROOT / "pipeline_out/e3/K-PRE/adapter_alpha/execution_mapping.json"
    CLAIMS = ROOT / "pipeline_out/e3/K-PRE/e3_claims.json"

    def test_real_bundle_accounts_for_every_empty_direct_input(self):
        if not self.BUNDLE.exists() or not self.CLAIMS.exists():
            self.skipTest("real E3 bundle not present in this checkout")
        result = build_model_inputs(json.loads(self.BUNDLE.read_text()), json.loads(self.CLAIMS.read_text()))
        empty = [node for node in json.loads(self.BUNDLE.read_text())["model_nodes"]
                 if node.get("computational_form") == "DIRECT_INPUT"
                 and not isinstance(node.get("initial_value"), (int, float))]
        self.assertEqual(len(result["overrides"]) + len(result["unfilled_nodes"]), len(empty))


if __name__ == "__main__":
    unittest.main(verbosity=2)
