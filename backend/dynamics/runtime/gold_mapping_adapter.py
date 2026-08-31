#!/usr/bin/env python3
"""Adapter for the compiled Keystone Financial Gold execution mapping.

The Gold package is already downstream of extraction: it contains workbook
cells as model nodes, explicit directed dependencies, exact Excel formulas and
semantic reconstruction formulas.  This adapter converts that compiler output
to the stable scalar execution contract consumed by the transition engine.

It does not mutate the Gold files and does not invent missing economic rules.
Scalar formulas, dated cash-flow vectors and their deterministic XIRR consumers
are compiled into typed runtime operations.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from collections import defaultdict, deque
from typing import Any, Mapping, Sequence

from .panta_transition_engine import (
    _equivalent,
    _execute_formula,
    _topologically_order_formulas,
    apply_state_transition as _run_transition,
)


GOLD_ADAPTER_VERSION = "0.3.0"

_RESOLVED_TOPOLOGY_LIMITS = {
    "MISSING_MODEL_DEPENDENCY",
    "MISSING_EXECUTABLE_DIRECTION",
}


class GoldMappingInputError(ValueError):
    """Raised when the compiled Gold mapping is structurally inconsistent."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _baseline_value(node: Mapping[str, Any]) -> Any:
    for field in ("baseline_value_decimal", "baseline_value_evaluated", "baseline_value"):
        value = node.get(field)
        if value is not None:
            return copy.deepcopy(value)
    return None


def _column_number(column: str) -> int:
    value = 0
    for character in column:
        value = value * 26 + (ord(character) - ord("A") + 1)
    return value


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


_REF_TOKEN = r"(?:(?:'[^']+'|[A-Za-z_][A-Za-z0-9_ &.]*)!)?\$?[A-Z]{1,3}\$?\d+"
_RANGE_RE = re.compile(f"({_REF_TOKEN}):({_REF_TOKEN})")
_SINGLE_REF_RE = re.compile(_REF_TOKEN)


def _parse_cell_ref(
    raw_ref: str,
    *,
    current_sheet: str,
    inherited_sheet: str | None = None,
) -> tuple[str, str]:
    if "!" in raw_ref:
        raw_sheet, raw_cell = raw_ref.rsplit("!", 1)
        sheet = raw_sheet.strip("'")
    else:
        sheet = inherited_sheet or current_sheet
        raw_cell = raw_ref
    cell = raw_cell.replace("$", "").upper()
    if not re.fullmatch(r"[A-Z]{1,3}\d+", cell):
        raise GoldMappingInputError(f"invalid A1 reference: {raw_ref!r}")
    return sheet, cell


def _expand_range(
    start_ref: str,
    end_ref: str,
    *,
    current_sheet: str,
) -> list[str]:
    start_sheet, start_cell = _parse_cell_ref(start_ref, current_sheet=current_sheet)
    end_sheet, end_cell = _parse_cell_ref(
        end_ref,
        current_sheet=current_sheet,
        inherited_sheet=start_sheet,
    )
    if start_sheet != end_sheet:
        raise GoldMappingInputError(
            f"3D/cross-sheet range is unsupported: {start_ref}:{end_ref}"
        )
    start_match = re.fullmatch(r"([A-Z]+)(\d+)", start_cell)
    end_match = re.fullmatch(r"([A-Z]+)(\d+)", end_cell)
    assert start_match is not None and end_match is not None
    start_column, start_row = _column_number(start_match.group(1)), int(start_match.group(2))
    end_column, end_row = _column_number(end_match.group(1)), int(end_match.group(2))
    row_low, row_high = sorted((start_row, end_row))
    column_low, column_high = sorted((start_column, end_column))
    return [
        f"CELL:{start_sheet}!{_column_name(column)}{row}"
        for row in range(row_low, row_high + 1)
        for column in range(column_low, column_high + 1)
    ]


def _output_sheet(formula: Mapping[str, Any]) -> str:
    locator = str(formula.get("workbook_locator") or formula.get("output_id", ""))
    locator = locator.removeprefix("CELL:")
    if "!" not in locator:
        raise GoldMappingInputError(
            f"formula {formula.get('formula_id')} has no workbook sheet context"
        )
    return locator.rsplit("!", 1)[0]


def _compile_excel_formula(
    formula: Mapping[str, Any],
    valid_node_ids: set[str],
) -> dict[str, Any]:
    expression = str(formula.get("expression", "")).strip()
    if expression.startswith("="):
        expression = expression[1:]
    current_sheet = _output_sheet(formula)
    declared_inputs = [str(item) for item in formula.get("input_ids", [])]
    referenced_ids: list[str] = []
    alias_by_id: dict[str, str] = {}

    def alias_for(object_id: str) -> str:
        if object_id not in valid_node_ids:
            raise GoldMappingInputError(
                f"formula {formula.get('formula_id')} references unknown node {object_id}"
            )
        if object_id not in alias_by_id:
            alias_by_id[object_id] = f"v{len(alias_by_id):05d}"
            referenced_ids.append(object_id)
        return alias_by_id[object_id]

    def replace_range(match: re.Match[str]) -> str:
        members = _expand_range(
            match.group(1),
            match.group(2),
            current_sheet=current_sheet,
        )
        return ",".join(alias_for(member) for member in members)

    translated = _RANGE_RE.sub(replace_range, expression)

    def replace_ref(match: re.Match[str]) -> str:
        sheet, cell = _parse_cell_ref(match.group(0), current_sheet=current_sheet)
        return alias_for(f"CELL:{sheet}!{cell}")

    translated = _SINGLE_REF_RE.sub(replace_ref, translated)
    translated = re.sub(
        r"(?<![A-Za-z0-9_.])(\d+(?:\.\d+)?)%",
        lambda match: f"({match.group(1)}/100)",
        translated,
    )
    translated = translated.replace("<>", "!=")
    translated = re.sub(r"(?<![<>=])=(?!=)", "==", translated)

    undeclared = sorted(set(referenced_ids) - set(declared_inputs))
    missing_refs = sorted(set(declared_inputs) - set(referenced_ids))
    if undeclared or missing_refs:
        raise GoldMappingInputError(
            f"formula {formula.get('formula_id')} reference/input mismatch: "
            f"undeclared={undeclared}, missing={missing_refs}"
        )
    try:
        ast.parse(translated, mode="eval")
    except SyntaxError as exc:
        raise GoldMappingInputError(
            f"formula {formula.get('formula_id')} did not compile: {translated}"
        ) from exc

    compiled = copy.deepcopy(dict(formula))
    compiled["gold_expression"] = expression
    compiled["expression_or_function_ref"] = translated
    compiled["operand_bindings"] = {
        alias: object_id for object_id, alias in alias_by_id.items()
    }
    compiled["input_ids"] = referenced_ids
    return compiled


def _semantic_scalar_expression(formula: Mapping[str, Any]) -> str | None:
    expression = str(formula.get("expression", "")).strip()
    input_ids = [str(item) for item in formula.get("input_ids", [])]
    variables = [f"v{index:05d}" for index in range(len(input_ids))]

    if expression in {
        "annual_assumption_for_calendar_year",
        "annual_SOFR_assumption_for_calendar_year",
        "Opening sponsor cash equity",
        "Opening cash",
        "First-lien debt",
        "Seller rollover",
        "Seller equity purchase price",
        "Sponsor cash equity",
    } and len(variables) == 1:
        return variables[0]
    if expression == "quarter_revenue * annual_firm_ebitda_margin" and len(variables) == 2:
        return f"{variables[0]}*{variables[1]}"
    if expression == "annual_revenue * quarter_seasonality" and len(variables) == 2:
        return f"{variables[0]}*{variables[1]}"
    if expression == "prior_year_revenue * (1 + annual_growth)" and len(variables) == 2:
        return f"{variables[0]}*(1+{variables[1]})"
    if expression in {
        "Sponsor proceeds / sponsor invested",
        "Enterprise value / Firm-underwritten EBITDA",
    } and len(variables) == 2:
        return f"{variables[0]}/{variables[1]}"
    if expression == "Sponsor invested / (Sponsor invested + rollover)" and len(variables) == 2:
        return f"{variables[0]}/({variables[0]}+{variables[1]})"
    if expression == "MIN(10%, MAX(6%, 4% × pre-MIP sponsor MOIC))" and len(variables) == 1:
        return f"MIN(0.10,MAX(0.06,0.04*{variables[0]}))"
    if expression == "Exit equity × pre-MIP sponsor ownership × (1 - vested MIP)" and len(variables) == 3:
        return f"{variables[0]}*{variables[1]}*(1-{variables[2]})"
    if expression == "Exit equity × pre-MIP sponsor ownership / sponsor invested" and len(variables) == 3:
        return f"{variables[0]}*{variables[1]}/{variables[2]}"
    if expression in {
        "Exit equity = Exit EV - Exit economic net debt",
        "Seller equity value - seller rollover",
        "Seller equity - rollover",
        "Enterprise value - seller net debt and debt-like items",
        "EV - seller net debt/debt-like",
        "Total sources - total uses",
    } and len(variables) == 2:
        return f"{variables[0]}-{variables[1]}"
    if expression == "(Opening first-lien debt - opening cash) / Firm-underwritten EBITDA" and len(variables) == 3:
        return f"({variables[0]}-{variables[1]})/{variables[2]}"
    if expression in {
        "Exit economic net debt = final-quarter economic net debt",
        "Exit LTM revenue = final-quarter LTM revenue",
        "Exit LTM Firm EBITDA = final-quarter LTM Firm EBITDA",
    } and len(variables) == 1:
        return variables[0]
    if expression == "Exit EV = Exit LTM Firm EBITDA × Exit Multiple" and len(variables) == 2:
        return f"{variables[0]}*{variables[1]}"
    if expression.startswith("Opening sponsor cash equity +") and variables:
        return "+".join(variables)
    if expression in {"SUM(sources)", "SUM(uses)"} and variables:
        return f"SUM({','.join(variables)})"
    return None


def _compile_dated_cash_flow_formula(
    formula: Mapping[str, Any],
) -> dict[str, Any]:
    expression = str(formula.get("expression", ""))
    input_ids = [str(item) for item in formula.get("input_ids", [])]
    if len(input_ids) != 2:
        raise GoldMappingInputError(
            f"formula {formula.get('formula_id')} must bind invested and proceeds"
        )
    opening_match = re.search(
        r"opening investment at (\d{4}-\d{2}-\d{2})", expression
    )
    exit_match = re.search(r"exit proceeds at (\d{4}-\d{2}-\d{2})", expression)
    if opening_match is None or exit_match is None:
        raise GoldMappingInputError(
            f"formula {formula.get('formula_id')} has incomplete dated cash-flow provenance"
        )
    interim = [
        {"amount": amount, "date": flow_date}
        for amount, flow_date in re.findall(
            r"contribution (\d+(?:\.\d+)?) at (\d{4}-\d{2}-\d{2})",
            expression,
        )
    ]
    compiled = copy.deepcopy(dict(formula))
    compiled.update(
        {
            "gold_expression": expression,
            "evaluation_type": "BUILD_DATED_CASH_FLOW_VECTOR",
            "expression_or_function_ref": "DATED_CASH_FLOW_VECTOR",
            "value_type": "DATED_CASH_FLOW_VECTOR",
            "dated_cash_flow_spec": {
                "total_invested_input_id": input_ids[0],
                "exit_proceeds_input_id": input_ids[1],
                "opening_date": opening_match.group(1),
                "exit_date": exit_match.group(1),
                "interim_investments": interim,
            },
        }
    )
    return compiled


def _compile_xirr_formula(formula: Mapping[str, Any]) -> dict[str, Any]:
    input_ids = [str(item) for item in formula.get("input_ids", [])]
    if len(input_ids) != 1:
        raise GoldMappingInputError(
            f"formula {formula.get('formula_id')} must bind one cash-flow vector"
        )
    compiled = copy.deepcopy(dict(formula))
    compiled.update(
        {
            "gold_expression": formula.get("expression"),
            "evaluation_type": "XIRR",
            "expression_or_function_ref": "XIRR",
            "value_type": "DECIMAL_RATE",
            "xirr_config": {
                "day_count_basis": "ACT_365",
                "tolerance": "1e-24",
                "residual_tolerance": "1e-28",
                "max_iterations": 256,
                "root_selection": "UNIQUE_SIGN_CHANGE_ONLY",
            },
        }
    )
    return compiled


def _compile_semantic_formula(formula: Mapping[str, Any]) -> dict[str, Any] | None:
    source_type = str(formula.get("source_type", ""))
    if source_type == "DERIVED_CASH_FLOW_VECTOR":
        return _compile_dated_cash_flow_formula(formula)
    if source_type == "DETERMINISTIC_FINANCIAL_FUNCTION" and str(
        formula.get("expression", "")
    ).startswith("XIRR("):
        return _compile_xirr_formula(formula)
    expression = _semantic_scalar_expression(formula)
    if expression is None:
        return None
    input_ids = [str(item) for item in formula.get("input_ids", [])]
    compiled = copy.deepcopy(dict(formula))
    compiled["gold_expression"] = formula.get("expression")
    compiled["expression_or_function_ref"] = expression
    compiled["operand_bindings"] = {
        f"v{index:05d}": object_id for index, object_id in enumerate(input_ids)
    }
    return compiled


def _is_acyclic(node_ids: set[str], edges: Sequence[Mapping[str, Any]]) -> bool:
    indegree = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source = str(edge.get("from_model_node_id", ""))
        target = str(edge.get("to_model_node_id", ""))
        if source not in indegree or target not in indegree or target in adjacency[source]:
            continue
        adjacency[source].add(target)
        indegree[target] += 1
    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        source = queue.popleft()
        visited += 1
        for target in sorted(adjacency.get(source, ())):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited == len(indegree)


def _compile_drives_edges(
    raw_edges: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Type Gold model dependencies and expose them to the canonical graph."""

    typed_edges: list[dict[str, Any]] = []
    position_dependencies: list[dict[str, Any]] = []
    seen_edge_ids: set[str] = set()
    for index, raw_edge in enumerate(raw_edges):
        edge_id = str(raw_edge.get("edge_id", "")).strip()
        if not edge_id:
            raise GoldMappingInputError(
                f"directed_model_edges[{index}] has no edge_id"
            )
        if edge_id in seen_edge_ids:
            raise GoldMappingInputError(f"duplicate Gold edge: {edge_id}")
        seen_edge_ids.add(edge_id)

        declared_relation = str(raw_edge.get("relation_type") or "DRIVES")
        if declared_relation != "DRIVES":
            raise GoldMappingInputError(
                f"Gold edge {edge_id} has incompatible relation_type "
                f"{declared_relation!r}"
            )

        source = str(raw_edge["from_model_node_id"])
        target = str(raw_edge["to_model_node_id"])
        typed_edge = copy.deepcopy(dict(raw_edge))
        typed_edge["relation_type"] = "DRIVES"
        typed_edges.append(typed_edge)
        position_dependencies.append(
            {
                "edge_id": edge_id,
                # The canonical dependency contract predates model-node edges;
                # the endpoint names are retained for schema compatibility.
                "from_position_id": source,
                "to_position_id": target,
                "relation_type": "DRIVES",
                "semantic_role": "drives_model_calculation",
                "traversal_rule": (
                    "propagate downstream through the executable model graph"
                ),
            }
        )
    return typed_edges, position_dependencies


def _close_resolved_topology_limits(
    raw_limits: Sequence[Mapping[str, Any]],
    *,
    typed_edges: Sequence[Mapping[str, Any]],
    compiled_formulas: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop only coverage limits proven obsolete by the compiled topology."""

    resolved_reason_codes: set[str] = set()
    if typed_edges:
        resolved_reason_codes.add("MISSING_MODEL_DEPENDENCY")
    if typed_edges and compiled_formulas:
        resolved_reason_codes.add("MISSING_EXECUTABLE_DIRECTION")

    remaining: list[dict[str, Any]] = []
    closed: set[str] = set()
    for limit in raw_limits:
        copied = copy.deepcopy(dict(limit))
        reason_code = str(copied.get("reason_code", ""))
        if (
            reason_code in _RESOLVED_TOPOLOGY_LIMITS
            and reason_code in resolved_reason_codes
        ):
            closed.add(reason_code)
            continue
        remaining.append(copied)
    return remaining, sorted(closed)


def compile_gold_to_runtime_inputs(
    gold_mapping: Mapping[str, Any],
    semantic_graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a Financial Gold mapping into a typed runtime graph and mapping."""

    if not isinstance(gold_mapping, Mapping):
        raise GoldMappingInputError("gold mapping must be an object")
    raw_nodes = gold_mapping.get("model_nodes")
    raw_edges = gold_mapping.get("directed_model_edges")
    raw_formulas = gold_mapping.get("formulas")
    raw_limits = gold_mapping.get("coverage_limits", [])
    if (
        not isinstance(raw_nodes, list)
        or not isinstance(raw_edges, list)
        or not isinstance(raw_formulas, list)
        or not isinstance(raw_limits, list)
    ):
        raise GoldMappingInputError(
            "gold mapping must contain model_nodes[], directed_model_edges[], "
            "formulas[] and optional coverage_limits[]"
        )

    node_by_id: dict[str, Mapping[str, Any]] = {}
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, Mapping) or not node.get("model_node_id"):
            raise GoldMappingInputError(f"model_nodes[{index}] has no model_node_id")
        node_id = str(node["model_node_id"])
        if node_id in node_by_id:
            raise GoldMappingInputError(f"duplicate Gold model node: {node_id}")
        node_by_id[node_id] = node
    node_ids = set(node_by_id)

    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, Mapping):
            raise GoldMappingInputError(f"directed_model_edges[{index}] must be an object")
        source = str(edge.get("from_model_node_id", ""))
        target = str(edge.get("to_model_node_id", ""))
        if source not in node_ids or target not in node_ids:
            raise GoldMappingInputError(f"Gold edge {index} has a dangling endpoint")

    typed_edges, position_dependencies = _compile_drives_edges(raw_edges)

    for index, limit in enumerate(raw_limits):
        if not isinstance(limit, Mapping):
            raise GoldMappingInputError(
                f"coverage_limits[{index}] must be an object"
            )

    compiled_formulas: list[dict[str, Any]] = []
    skipped_formulas: list[dict[str, Any]] = []
    for formula in raw_formulas:
        if not isinstance(formula, Mapping):
            raise GoldMappingInputError("every Gold formula must be an object")
        if formula.get("output_id") not in node_ids:
            raise GoldMappingInputError(
                f"formula {formula.get('formula_id')} has an unknown output"
            )
        missing_inputs = sorted(
            str(item) for item in formula.get("input_ids", []) if str(item) not in node_ids
        )
        if missing_inputs:
            raise GoldMappingInputError(
                f"formula {formula.get('formula_id')} has unknown inputs {missing_inputs}"
            )
        if formula.get("source_type") == "WORKBOOK_FORMULA":
            compiled = _compile_excel_formula(formula, node_ids)
        elif re.search(r"(?:'[^']+'|[A-Za-z_][A-Za-z0-9_]*)!\$?[A-Z]+\$?\d+", str(formula.get("expression", ""))):
            compiled = _compile_excel_formula(formula, node_ids)
        else:
            compiled = _compile_semantic_formula(formula)
        if compiled is None:
            skipped_formulas.append(
                {
                    "formula_id": str(formula.get("formula_id")),
                    "output_id": str(formula.get("output_id")),
                    "source_type": str(formula.get("source_type")),
                    "reason_code": "NON_SCALAR_FORMULA_VALUE_UNSUPPORTED",
                }
            )
        else:
            compiled_formulas.append(compiled)

    coverage_limits, closed_coverage_limit_reason_codes = (
        _close_resolved_topology_limits(
            raw_limits,
            typed_edges=typed_edges,
            compiled_formulas=compiled_formulas,
        )
    )

    runtime_nodes = [
        {
            "model_node_id": node_id,
            "name": str(node.get("name") or node_id),
            "kind": str(node.get("computational_form") or "MODEL_NODE"),
            "period": str(node.get("period") or "UNSPECIFIED"),
            "perimeter": str(node.get("perimeter") or "UNSPECIFIED"),
            "unit": node.get("unit"),
            "value": _baseline_value(node),
            "source_baseline_value": _baseline_value(node),
            "workbook_locator": node.get("workbook_locator"),
            "scenario_id": node.get("scenario_id"),
            "semantic_line_item": node.get("semantic_line_item"),
        }
        for node_id, node in sorted(node_by_id.items())
    ]
    runtime_node_by_id = {node["model_node_id"]: node for node in runtime_nodes}
    hydration_registry = {
        node_id: {"object_type": "MODEL_NODE", "object": node}
        for node_id, node in runtime_node_by_id.items()
    }
    hydrated_helper_ids: list[str] = []
    normalized_formula_output_ids: list[str] = []
    hydration_errors: list[dict[str, str]] = []
    for formula in _topologically_order_formulas(compiled_formulas):
        output_id = str(formula.get("output_id", ""))
        output_node = runtime_node_by_id.get(output_id)
        if output_node is None:
            continue
        source_value = copy.deepcopy(output_node.get("value"))
        candidate_value, error = _execute_formula(formula, hydration_registry)
        if error is None:
            output_node["value"] = candidate_value
            if source_value is None:
                hydrated_helper_ids.append(output_id)
            elif not _equivalent(source_value, candidate_value):
                normalized_formula_output_ids.append(output_id)
        else:
            hydration_errors.append(
                {
                    "formula_id": str(formula.get("formula_id", "")),
                    "output_id": output_id,
                    "reason_code": error,
                }
            )
    case_id = str(gold_mapping.get("case_id") or "KEYSTONE-CIC")
    current_graph = {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "canonical_as_of": "2026-03-10",
        "claims": [],
        "case_positions": [],
        "model_nodes": runtime_nodes,
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": position_dependencies,
        "position_model_bindings": [],
        "decision_snapshot": {},
        "coverage_gaps": copy.deepcopy(coverage_limits),
    }

    adapter_limits = [
        {
            "limit_id": f"GOLD-ADAPTER-{index:03d}",
            "reason_code": item["reason_code"],
            "scope_ids": [item["output_id"]],
            "effect": (
                "The Gold formula could not be compiled by the current runtime adapter."
            ),
            "formula_id": item["formula_id"],
        }
        for index, item in enumerate(skipped_formulas, start=1)
    ]
    execution_mapping = {
        "mapping_version": f"{gold_mapping.get('mapping_version', 'GOLD')}+adapter-{GOLD_ADAPTER_VERSION}",
        "canonical_graph_hash": str(
            gold_mapping.get("canonical_graph_hash") or _hash(semantic_graph or current_graph)
        ),
        "model_nodes": [
            {
                "model_node_id": node["model_node_id"],
                "unit": node.get("unit"),
                "period": node.get("period"),
                "perimeter": node.get("perimeter"),
                "computational_form": node.get("kind"),
            }
            for node in runtime_nodes
        ],
        "directed_model_edges": typed_edges,
        "position_model_directions": [],
        "formulas": sorted(
            compiled_formulas, key=lambda item: str(item.get("formula_id", ""))
        ),
        "rule_switches": copy.deepcopy(gold_mapping.get("rule_switches", [])),
        "cyclic_component_solver_configs": copy.deepcopy(
            gold_mapping.get("cyclic_component_solver_configs", [])
        ),
        "inverse_solver_configs": copy.deepcopy(
            gold_mapping.get("inverse_solver_configs", [])
        ),
        "model_controls": copy.deepcopy(gold_mapping.get("model_controls", [])),
        "coverage_limits": copy.deepcopy(coverage_limits) + adapter_limits,
        "source_gold_mapping_hash": _hash(gold_mapping),
        "source_semantic_graph_hash": _hash(semantic_graph) if semantic_graph else None,
    }

    report = {
        "adapter_version": GOLD_ADAPTER_VERSION,
        "case_id": case_id,
        "model_node_count": len(runtime_nodes),
        "directed_model_edge_count": len(raw_edges),
        "position_dependency_count": len(position_dependencies),
        "drives_edge_count": len(typed_edges),
        "gold_formula_count": len(raw_formulas),
        "compiled_formula_count": len(compiled_formulas),
        "compiled_scalar_formula_count": sum(
            item.get("evaluation_type")
            not in {"BUILD_DATED_CASH_FLOW_VECTOR", "XIRR"}
            for item in compiled_formulas
        ),
        "compiled_typed_formula_count": sum(
            item.get("evaluation_type")
            in {"BUILD_DATED_CASH_FLOW_VECTOR", "XIRR"}
            for item in compiled_formulas
        ),
        "skipped_non_scalar_formula_count": len(skipped_formulas),
        "skipped_formulas": skipped_formulas,
        "hydrated_semantic_helper_count": len(hydrated_helper_ids),
        "normalized_formula_output_count": len(normalized_formula_output_ids),
        "normalized_formula_output_ids": sorted(normalized_formula_output_ids),
        "hydration_error_count": len(hydration_errors),
        "hydration_errors": hydration_errors,
        "closed_coverage_limit_reason_codes": (
            closed_coverage_limit_reason_codes
        ),
        "directed_graph_acyclic": _is_acyclic(node_ids, raw_edges),
        "current_graph_hash": _hash(current_graph),
        "runtime_mapping_hash": _hash(execution_mapping),
    }
    return {
        "current_graph": current_graph,
        "execution_mapping": execution_mapping,
        "adapter_report": report,
    }


def apply_gold_transition(
    gold_mapping: Mapping[str, Any],
    event_batch: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    materiality_policy: Mapping[str, Any],
    authority_policy: Mapping[str, Any],
    *,
    semantic_graph: Mapping[str, Any] | None = None,
    execution_mode: str = "INCREMENTAL_SCC",
) -> dict[str, Any]:
    """Compile the Gold mapping and execute one immutable Candidate transition."""

    compiled = compile_gold_to_runtime_inputs(gold_mapping, semantic_graph)
    events = [event_batch] if isinstance(event_batch, Mapping) else list(event_batch)
    result = _run_transition(
        compiled["current_graph"],
        events,
        compiled["execution_mapping"],
        materiality_policy,
        authority_policy,
        execution_mode=execution_mode,
    )
    result["gold_adapter_report"] = compiled["adapter_report"]
    return result
