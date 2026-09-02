from __future__ import annotations

import sys
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.graph_store import DealGraph  # noqa: E402
from tools.pipeline import e3_to_claims  # noqa: E402
from tools.relation_rules import (  # noqa: E402
    RUNTIME_RELATIONS,
    annotate_edge,
    audit_relation_outputs,
    orchestrate_claim_relations,
)
from vercel.api._claim_graph import claims_to_graph  # noqa: E402


def claim(
    claim_id: str,
    value,
    *,
    metric: str = "Revenue",
    source_id: str | None = None,
    measurement: str = "total",
    derivation=None,
    derivation_claim_ids=None,
):
    return {
        "claim_id": claim_id,
        "subject": "Keystone",
        "entity": "Keystone",
        "metric": metric,
        "value": value,
        "unit": "$m",
        "currency": "USD",
        "period": "FY2025",
        "period_canonical": "FY2025",
        "scope": "consolidated",
        "basis": "ReportedView",
        "measurement": measurement,
        "scenario": "base",
        "bound": "EXACT",
        "perimeter": "Keystone consolidated reported revenue",
        "source_id": source_id or f"SRC-{claim_id}",
        "source_doc": source_id or f"SRC-{claim_id}",
        "epistemic": "derived" if derivation else "asserted",
        "epistemic_class": "derived" if derivation else "asserted",
        "direction": "supports",
        "topic": "COMMERCIAL_AND_MARKET",
        "statement": f"{metric} is {value}.",
        "derivation": derivation,
        "derivation_claim_ids": derivation_claim_ids or [],
    }


class Pan68RelationRuleTests(unittest.TestCase):
    def test_identity_and_value_materialize_a_governed_conflict(self):
        result = orchestrate_claim_relations([
            claim("claim:a", 100, source_id="SRC-A"),
            claim("claim:b", 90, source_id="SRC-B"),
            claim("claim:service", 40, source_id="SRC-C", measurement="service a"),
        ])

        self.assertEqual(len(result["edges"]), 1)
        edge = result["edges"][0]
        self.assertEqual(edge["rel"], "CONTRADICTS")
        self.assertEqual(
            edge["relation_rule"]["rule_id"], "IDENTITY_VALUE_CONFLICT"
        )
        self.assertEqual(edge["relation_rule"]["mode"], "DETERMINISTIC")
        self.assertEqual(result["audit"]["deterministic_edge_pct"], 100.0)

    def test_explicit_derivation_is_an_edge_but_prose_match_is_only_a_proposal(self):
        source = claim("claim:source", 100, metric="Revenue")
        explicit = claim(
            "claim:explicit",
            20,
            metric="EBITDA",
            derivation={"formula": "revenue - costs"},
            derivation_claim_ids=["claim:source"],
        )
        prose = claim(
            "claim:prose",
            10,
            metric="Free Cash Flow",
            derivation="Revenue less cash costs",
        )

        result = orchestrate_claim_relations([source, explicit, prose])

        derives = [edge for edge in result["edges"] if edge["rel"] == "DERIVES_FROM"]
        self.assertEqual(len(derives), 1)
        self.assertEqual(derives[0]["source"], "claim:explicit")
        self.assertEqual(derives[0]["target"], "claim:source")
        proposals = [
            item for item in result["proposals"]
            if item["relation_type"] == "DERIVES_FROM"
        ]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["proposal_status"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(proposals[0]["llm_authority"], "PROPOSE_ONLY")
        self.assertEqual(proposals[0]["adjudication"], "HUMAN_REQUIRED")
        self.assertFalse(proposals[0]["canonical"])

    def test_formula_drives_rule_is_measured_as_deterministic(self):
        edge = annotate_edge(
            {
                "edge_id": "DME-1",
                "from_model_node_id": "MN-REVENUE",
                "to_model_node_id": "MN-EBITDA",
                "relation_type": "DRIVES",
                "formula_or_function_ref": "FORMULA-EBITDA",
            },
            "FORMULA_PRECEDENT_DRIVES",
        )
        audit = audit_relation_outputs([edge])

        self.assertEqual(audit["materialized_edge_count"], 1)
        self.assertEqual(audit["deterministic_edge_count"], 1)
        self.assertEqual(audit["deterministic_edge_pct"], 100.0)

    def test_e3_pipeline_preserves_identity_dimensions_for_relation_rules(self):
        payload = {
            "claims": [{
                "claim_id": "claim:a",
                "statement": "Revenue was $100m.",
                "source_id": "SRC-A",
                "locator": "source.md::revenue",
                "epistemic_class": "asserted",
                "value": "100.0",
                "unit": "$m",
                "period": "FY2025",
                "perimeter": "Keystone consolidated revenue",
            }],
            "extraction_metadata": {
                "compiler_fields_per_claim": [{
                    "claim_id": "claim:a",
                    "entity": "Keystone",
                    "metric": "Revenue",
                    "period_canonical": "FY2025",
                    "scope": "consolidated",
                    "basis": "ReportedView",
                    "measurement": "total",
                    "scenario": "base",
                    "bound": "EXACT",
                    "currency": "USD",
                }]
            },
        }

        converted = e3_to_claims(payload)[0]

        self.assertEqual(converted["claim_id"], "claim:a")
        self.assertEqual(converted["entity"], "Keystone")
        self.assertEqual(converted["measurement"], "total")
        self.assertEqual(converted["bound"], "EXACT")

    def test_claim_graph_materializes_only_governed_runtime_edges(self):
        claims = [
            claim("claim:a", 100, source_id="SRC-A"),
            claim("claim:b", 90, source_id="SRC-B"),
        ]
        graph = claims_to_graph(claims, deal="keystone")
        runtime_edges = [
            edge for edge in graph["edges"] if edge["rel"] in RUNTIME_RELATIONS
        ]

        self.assertTrue(runtime_edges)
        self.assertTrue(all(edge.get("relation_rule") for edge in runtime_edges))
        self.assertEqual(graph["relation_audit"]["unclassified_edge_count"], 0)
        self.assertEqual(graph["relation_audit"]["deterministic_edge_pct"], 100.0)

        stored = DealGraph(deal="keystone")
        stored.load_from_claims_graph(claims, graph)
        governed = [
            data
            for _, _, data in stored.G.edges(data=True)
            if data.get("rel") in RUNTIME_RELATIONS
        ]
        self.assertTrue(governed)
        self.assertTrue(all(data.get("relation_rule") for data in governed))

    def test_serverless_claim_graph_imports_without_repository_tools_package(self):
        result = subprocess.run(
            [sys.executable, "-c", "import _claim_graph; print('ok')"],
            cwd=ROOT / "vercel" / "api",
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
