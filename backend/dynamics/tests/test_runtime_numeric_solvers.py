import json
import unittest
from decimal import Decimal
from pathlib import Path

from runtime import apply_state_transition


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def suite():
    return load_json("benchmark/transition_engine_conformance_cases_v1.json")


def fixture(fixture_id):
    return next(item for item in suite()["synthetic_fixtures"] if item["fixture_id"] == fixture_id)


def case(test_id):
    return next(item for item in suite()["cases"] if item["test_id"] == test_id)


def base_graph(case_id, node_ids):
    return {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "canonical_as_of": "2026-01-01",
        "claims": [],
        "case_positions": [],
        "model_nodes": [
            {
                "model_node_id": node_id,
                "name": node_id,
                "kind": "derived",
                "period": "TEST",
                "perimeter": "TEST",
                "value": None,
                "unit": None,
                "active": False,
            }
            for node_id in node_ids
        ],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def empty_mapping():
    return {
        "mapping_version": "TEST-NUMERIC",
        "canonical_graph_hash": "sha256:" + "0" * 64,
        "model_nodes": [],
        "directed_model_edges": [],
        "position_model_directions": [],
        "formulas": [],
        "rule_switches": [],
        "inverse_solver_configs": [],
        "model_controls": [],
        "cyclic_component_solver_configs": [],
        "coverage_limits": [],
    }


def run(graph, event_batch, mapping):
    return apply_state_transition(
        graph,
        event_batch,
        mapping,
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )["transition_output"]


def cycle_edges(member_ids):
    return [
        {
            "edge_id": f"E-{source}-{target}",
            "from_model_node_id": source,
            "to_model_node_id": target,
            "formula_or_function_ref": "DECLARED_COMPONENT_EQUATIONS",
        }
        for source, target in zip(member_ids, member_ids[1:] + member_ids[:1])
    ]


class RuntimeNumericSolverTests(unittest.TestCase):
    def test_tce010_unique_numeric_scc_settles(self):
        source = fixture("SF-NUMERIC-CONVERGENT")
        graph = base_graph(source["fixture_id"], source["variables"])
        mapping = empty_mapping()
        mapping["directed_model_edges"] = cycle_edges(source["variables"])
        mapping["cyclic_component_solver_configs"] = [
            {
                "component_id": "SCC-XY",
                "component_type": "NUMERICAL_SCC",
                "member_ids": source["variables"],
                "equations": source["equations"],
                **source["solver"],
                "invariant_control_ids": ["INV-NUMERIC-XY"],
            }
        ]
        output = run(graph, case("TCE-010-NUMERIC-SCC-CONVERGES")["event_batch"], mapping)

        component = next(item for item in output["ordered_transitions"] if item["component_id"] == "SCC-XY")
        self.assertEqual(component["component_type"], "NUMERICAL_SCC")
        self.assertEqual(component["result"], "SETTLED")
        values = {item["object_id"]: Decimal(item["candidate_value"]) for item in output["recomputed_values"]}
        self.assertLess(abs(values["X"] - Decimal("2.2857142857142857")), Decimal("1e-9"))
        self.assertLess(abs(values["Y"] - Decimal("2.5714285714285714")), Decimal("1e-9"))
        self.assertIn("PASS", {item["status"] for item in output["invariant_checks"] if item["invariant_id"] == "INV-NUMERIC-XY"})

    def test_tce011_no_solution_blocks_only_cycle_and_z_settles(self):
        source = fixture("SF-NUMERIC-NO-SOLUTION")
        graph = base_graph(source["fixture_id"], source["variables"] + ["INPUT_Z"])
        for node in graph["model_nodes"]:
            if node["model_node_id"] == "INPUT_Z":
                node["value"] = "2"
            elif node["model_node_id"] == "Z":
                node["value"] = "4"
        mapping = empty_mapping()
        mapping["directed_model_edges"] = cycle_edges(["X", "Y"])
        mapping["formulas"] = [
            {
                "formula_id": "F-Z",
                "input_ids": ["INPUT_Z"],
                "output_id": "Z",
                "expression_or_function_ref": "INPUT_Z * 2",
                "operand_bindings": {"INPUT_Z": "INPUT_Z"},
            }
        ]
        mapping["cyclic_component_solver_configs"] = [
            {
                "component_id": "SCC-XY",
                "component_type": "NUMERICAL_SCC",
                "member_ids": ["X", "Y"],
                "equations": source["equations"][:2],
                "method": "LINEAR_RANK_CLASSIFICATION",
                "initialization": {"X": "0", "Y": "0"},
                "admissible_bounds": {},
                "absolute_residual_tolerance": "1e-9",
                "relative_residual_tolerance": "1e-9",
                "maximum_iterations": 10,
                "uniqueness_condition": "FULL_COLUMN_RANK",
                "invariant_control_ids": [],
                "activation_input_ids": ["INPUT_Z"],
            }
        ]
        output = run(
            graph,
            case("TCE-011-NUMERIC-SCC-NO-SOLUTION-PARTIAL-SETTLEMENT")["event_batch"],
            mapping,
        )

        blocked = next(item for item in output["blocked_components"] if item["component_id"] == "SCC-XY")
        self.assertEqual(blocked["reason_code"], "NO_ADMISSIBLE_SOLUTION")
        z = next(item for item in output["recomputed_values"] if item["object_id"] == "Z")
        self.assertEqual(Decimal(z["candidate_value"]), Decimal("6"))
        self.assertEqual(output["partial_settlement_status"]["candidate"], "PARTIAL")
        self.assertFalse(output["global_block"])

    def test_tce012_multiple_solutions_selects_nothing(self):
        source = fixture("SF-NUMERIC-MULTIPLE")
        graph = base_graph(source["fixture_id"], source["variables"])
        mapping = empty_mapping()
        mapping["directed_model_edges"] = cycle_edges(source["variables"])
        mapping["cyclic_component_solver_configs"] = [
            {
                "component_id": "SCC-XY",
                "component_type": "NUMERICAL_SCC",
                "member_ids": source["variables"],
                "equations": source["equations"],
                "method": "LINEAR_RANK_CLASSIFICATION",
                "initialization": {"X": "0", "Y": "0"},
                "admissible_bounds": source["admissible_bounds"],
                "absolute_residual_tolerance": "1e-9",
                "relative_residual_tolerance": "1e-9",
                "maximum_iterations": 10,
                "uniqueness_condition": "FULL_COLUMN_RANK",
                "invariant_control_ids": [],
            }
        ]
        output = run(graph, case("TCE-012-NUMERIC-SCC-MULTIPLE-SOLUTIONS")["event_batch"], mapping)

        component = next(item for item in output["ordered_transitions"] if item["component_id"] == "SCC-XY")
        self.assertEqual(component["result"], "BLOCKED")
        self.assertIn("MULTIPLE_SOLUTIONS", component["reason_codes"])
        self.assertFalse(any(item["object_id"] in {"X", "Y"} and item.get("formula_or_solver_ref") == "SCC-XY" for item in output["recomputed_values"]))
        self.assertIn("MULTIPLE_SOLUTIONS", {item["reason_code"] for item in output["human_stops"]})


if __name__ == "__main__":
    unittest.main()
