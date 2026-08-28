import json
import unittest
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

from runtime import apply_state_transition


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path):
    with (ROOT / relative_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def graph(*, vector=None, irr="0.0844"):
    return {
        "schema_version": "1.1.0",
        "case_id": "SF-DATED-CASH-FLOW",
        "canonical_as_of": "2026-03-31",
        "claims": [],
        "case_positions": [],
        "model_nodes": [
            {
                "model_node_id": "M-INVESTED",
                "name": "Sponsor invested",
                "kind": "INPUT",
                "period": "OPENING",
                "perimeter": "Deal",
                "value": "100",
                "unit": "$mm",
            },
            {
                "model_node_id": "M-PROCEEDS",
                "name": "Exit proceeds",
                "kind": "INPUT",
                "period": "EXIT",
                "perimeter": "Deal",
                "value": "150",
                "unit": "$mm",
            },
            {
                "model_node_id": "M-CASH-FLOWS",
                "name": "Dated sponsor cash flows",
                "kind": "DATED_CASH_FLOW_VECTOR",
                "period": "HOLD",
                "perimeter": "Deal",
                "value": vector
                or {
                    "value_type": "DATED_CASH_FLOW_VECTOR",
                    "day_count_basis": "ACT_365",
                    "cash_flows": [
                        {"date": "2026-03-31", "amount": "-100.0"},
                        {"date": "2031-03-31", "amount": "150.0"},
                    ],
                },
                "unit": "$mm",
            },
            {
                "model_node_id": "M-XIRR",
                "name": "Sponsor XIRR",
                "kind": "XIRR",
                "period": "HOLD",
                "perimeter": "Deal",
                "value": irr,
                "unit": "%",
            },
        ],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


def mapping(*, include_builder=True):
    formulas = []
    if include_builder:
        formulas.append(
            {
                "formula_id": "F-CASH-FLOWS",
                "output_id": "M-CASH-FLOWS",
                "input_ids": ["M-INVESTED", "M-PROCEEDS"],
                "evaluation_type": "BUILD_DATED_CASH_FLOW_VECTOR",
                "expression_or_function_ref": "DATED_CASH_FLOW_VECTOR",
                "dated_cash_flow_spec": {
                    "total_invested_input_id": "M-INVESTED",
                    "exit_proceeds_input_id": "M-PROCEEDS",
                    "opening_date": "2026-03-31",
                    "exit_date": "2031-03-31",
                    "interim_investments": [],
                },
            }
        )
    formulas.append(
        {
            "formula_id": "F-XIRR",
            "output_id": "M-XIRR",
            "input_ids": ["M-CASH-FLOWS"],
            "evaluation_type": "XIRR",
            "expression_or_function_ref": "XIRR",
            "xirr_config": {
                "day_count_basis": "ACT_365",
                "tolerance": "1e-24",
                "residual_tolerance": "1e-28",
                "max_iterations": 256,
                "root_selection": "UNIQUE_SIGN_CHANGE_ONLY",
            },
        }
    )
    return {
        "mapping_version": "TEST-DATED-CASH-FLOW",
        "canonical_graph_hash": "sha256:" + "0" * 64,
        "model_nodes": [],
        "directed_model_edges": [],
        "position_model_directions": [],
        "formulas": formulas,
        "rule_switches": [],
        "inverse_solver_configs": [],
        "model_controls": [],
        "cyclic_component_solver_configs": [],
        "coverage_limits": [],
    }


def run(case_graph, event, execution_mapping):
    return apply_state_transition(
        case_graph,
        [event],
        execution_mapping,
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


class RuntimeDatedCashFlowTests(unittest.TestCase):
    def test_dated_cash_flow_and_xirr_recompute_deterministically(self):
        event = {
            "event_id": "DCF-001",
            "event": "Increase exit proceeds",
            "effective_date": "2031-03-31",
            "known_at": "2026-08-24T12:00:00Z",
            "source_ids": ["TEST"],
            "trigger_claim_ids": [],
            "mutations": [
                {
                    "operation": "CORRECT",
                    "object_type": "MODEL_NODE",
                    "object_id": "M-PROCEEDS",
                    "field": "value",
                    "from": "150",
                    "to": "200",
                    "unit": "$mm",
                }
            ],
        }
        results = [run(graph(), event, mapping()) for _ in range(3)]
        self.assertTrue(all(result == results[0] for result in results[1:]))

        output = results[0]["transition_output"]
        values = {
            node["model_node_id"]: node.get("value")
            for node in results[0]["candidate_state"]["current_graph"]["model_nodes"]
        }
        self.assertEqual(
            values["M-CASH-FLOWS"]["cash_flows"],
            [
                {"date": "2026-03-31", "amount": "-100.0"},
                {"date": "2031-03-31", "amount": "200.0"},
            ],
        )
        self.assertGreater(Decimal(values["M-XIRR"]), Decimal("0.14"))
        self.assertLess(Decimal(values["M-XIRR"]), Decimal("0.15"))
        holding_days = (date(2031, 3, 31) - date(2026, 3, 31)).days
        with localcontext() as context:
            context.prec = 50
            expected_xirr = context.power(
                Decimal("2"), Decimal("365") / Decimal(holding_days)
            ) - Decimal("1")
        self.assertLess(
            abs(Decimal(values["M-XIRR"]) - expected_xirr), Decimal("1e-23")
        )
        self.assertEqual(output["partial_settlement_status"]["candidate"], "FULL")
        self.assertFalse(
            any("XIRR" in item["reason_code"] for item in output["coverage_limits"])
        )

    def test_xirr_with_multiple_sign_changes_is_not_selected_arbitrarily(self):
        original_vector = {
            "value_type": "DATED_CASH_FLOW_VECTOR",
            "day_count_basis": "ACT_365",
            "cash_flows": [
                {"date": "2026-03-31", "amount": "-100"},
                {"date": "2027-03-31", "amount": "230"},
                {"date": "2028-03-31", "amount": "-132"},
            ],
        }
        candidate_vector = json.loads(json.dumps(original_vector))
        candidate_vector["cash_flows"][1]["amount"] = "231"
        event = {
            "event_id": "DCF-002",
            "event": "Introduce ambiguous non-conventional cash flows",
            "effective_date": "2027-03-31",
            "known_at": "2026-08-24T12:01:00Z",
            "source_ids": ["TEST"],
            "trigger_claim_ids": [],
            "mutations": [
                {
                    "operation": "CORRECT",
                    "object_type": "MODEL_NODE",
                    "object_id": "M-CASH-FLOWS",
                    "field": "value",
                    "from": original_vector,
                    "to": candidate_vector,
                    "unit": "$mm",
                }
            ],
        }
        result = run(
            graph(vector=original_vector, irr="UNCHANGED"),
            event,
            mapping(include_builder=False),
        )
        output = result["transition_output"]
        values = {
            node["model_node_id"]: node.get("value")
            for node in result["candidate_state"]["current_graph"]["model_nodes"]
        }
        self.assertEqual(values["M-XIRR"], "UNCHANGED")
        self.assertIn(
            "AMBIGUOUS_XIRR_MULTIPLE_SIGN_CHANGES",
            {item["reason_code"] for item in output["coverage_limits"]},
        )
        self.assertEqual(output["partial_settlement_status"]["candidate"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()
