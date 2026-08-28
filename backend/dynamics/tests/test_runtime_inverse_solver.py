import copy
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


def fixture():
    return next(item for item in suite()["synthetic_fixtures"] if item["fixture_id"] == "SF-INVERSE-SUPPORTED-PRICE")


def case():
    return next(item for item in suite()["cases"] if item["test_id"] == "TCE-022-INVERSE-SUPPORTED-PRICE")


def graph():
    return {
        "schema_version": "1.1.0",
        "case_id": "SF-INVERSE-SUPPORTED-PRICE",
        "canonical_as_of": "2026-01-01",
        "claims": [],
        "case_positions": [],
        "model_nodes": [
            {
                "model_node_id": "M-SUPPORTED-PRICE",
                "name": "Supported price",
                "kind": "inverse_solve",
                "period": "CURRENT_UNDERWRITING",
                "perimeter": "Deal",
                "value": None,
                "unit": "$mm",
                "solve_requested": False,
            }
        ],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def mapping(*, bounds=None, branches=None, branch_precedence="DEFAULT"):
    source = fixture()
    objective_bounds = bounds or source["objective"]["bounds"]
    financing_branches = branches or [source["base_branch"]]
    config = {
        "solver_id": "INV-SUPPORTED-PRICE",
        "objective": {
            "sense": source["objective"]["sense"],
            "variable_id": "M-SUPPORTED-PRICE",
            "variable_symbol": source["objective"]["variable"],
            "bounds": objective_bounds,
            "unit": source["objective"]["unit"],
        },
        "decision_variable_ids": ["M-SUPPORTED-PRICE"],
        "constraints": [
            {
                "constraint_id": item["constraint_id"],
                "expression_or_function_ref": item["expression"],
                "operator": item["operator"],
                "value": item["value"],
                "unit": item["unit"],
                "source_ref": "S-RETURN-POLICY",
            }
            for item in source["constraints"]
        ],
        "method": source["solver"]["method"],
        "initialization": source["solver"]["initialization"],
        "admissible_bounds": {"M-SUPPORTED-PRICE": objective_bounds},
        "absolute_residual_tolerance": source["solver"]["constraint_tolerance"],
        "relative_residual_tolerance": source["solver"]["constraint_tolerance"],
        "price_tolerance": source["solver"]["price_tolerance"],
        "constraint_tolerance": source["solver"]["constraint_tolerance"],
        "maximum_iterations": source["solver"]["maximum_iterations"],
        "uniqueness_condition": source["solver"]["uniqueness_condition"],
        "invariant_control_ids": [],
        "financing_branches": financing_branches,
    }
    if branch_precedence != "DEFAULT":
        config["branch_precedence"] = branch_precedence
    return {
        "mapping_version": "TEST-INVERSE",
        "canonical_graph_hash": "sha256:" + "0" * 64,
        "model_nodes": [],
        "directed_model_edges": [],
        "position_model_directions": [],
        "formulas": [],
        "rule_switches": [],
        "inverse_solver_configs": [config],
        "model_controls": [],
        "cyclic_component_solver_configs": [],
        "coverage_limits": [],
    }


def run(execution_mapping):
    return apply_state_transition(
        graph(),
        case()["event_batch"],
        execution_mapping,
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class RuntimeInverseSolverTests(unittest.TestCase):
    def test_tce022_a_unique_optimum_reports_binding_constraint(self):
        output = run(mapping())["transition_output"]
        result = output["inverse_solver_results"][0]

        self.assertEqual(result["solver_outcome"], "UNIQUE_OPTIMUM")
        self.assertEqual(Decimal(result["decision_value"]), Decimal("115"))
        selected = result["selected_solution"]
        self.assertEqual(Decimal(selected["variables"]["entry_debt"]), Decimal("40"))
        self.assertEqual(Decimal(selected["variables"]["entry_equity"]), Decimal("75"))
        self.assertEqual(Decimal(selected["variables"]["exit_equity_proceeds"]), Decimal("150"))
        self.assertEqual(
            {item["constraint_id"] for item in result["binding_constraints"]},
            {"MIN-MOIC"},
        )
        self.assertTrue(all(item["source_ref"] for item in result["binding_constraints"]))
        self.assertEqual(output["partial_settlement_status"]["candidate"], "FULL")

    def test_tce022_b_no_solution_is_partial_not_exception(self):
        result = run(mapping(bounds=["120", "200"]))
        output = result["transition_output"]
        solver = output["inverse_solver_results"][0]

        self.assertEqual(solver["solver_outcome"], "NO_ADMISSIBLE_SOLUTION")
        self.assertIsNone(solver["selected_solution"])
        self.assertEqual(output["partial_settlement_status"]["candidate"], "PARTIAL")
        self.assertIn(
            "NO_ADMISSIBLE_SOLUTION",
            {item["reason_code"] for item in output["blocked_components"]},
        )

    def test_tce022_c_equal_branch_optima_are_not_selected_arbitrarily(self):
        overrides = case()["subcases"][2]["fixture_overrides"]
        output = run(
            mapping(
                branches=overrides["financing_branches"],
                branch_precedence=overrides["branch_precedence"],
            )
        )["transition_output"]
        result = output["inverse_solver_results"][0]

        self.assertEqual(result["solver_outcome"], "MULTIPLE_OPTIMAL_SOLUTIONS")
        self.assertIsNone(result["selected_solution"])
        self.assertEqual([Decimal(item) for item in result["supported_price_candidates"]], [Decimal("115"), Decimal("115")])
        self.assertEqual(set(result["solution_branch_ids"]), {"FINANCING-A", "FINANCING-B"})
        self.assertIn(
            "MULTIPLE_OPTIMAL_SOLUTIONS",
            {item["reason_code"] for item in output["human_stops"]},
        )

    def test_tce022_d_repeated_runs_are_deterministic(self):
        results = [run(mapping()) for _ in range(10)]
        outputs = [item["transition_output"] for item in results]

        self.assertTrue(all(item == outputs[0] for item in outputs[1:]))
        self.assertEqual({item["replay_hash"] for item in outputs}, {outputs[0]["replay_hash"]})
        self.assertEqual(
            {Decimal(item["inverse_solver_results"][0]["decision_value"]) for item in outputs},
            {Decimal("115")},
        )


if __name__ == "__main__":
    unittest.main()
