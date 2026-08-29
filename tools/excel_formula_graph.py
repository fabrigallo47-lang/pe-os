#!/usr/bin/env python3
"""Compile a lossless Excel source capture into a V20 semantic model graph.

This compiler preserves formula text, locators, dependencies and the workbook's
displayed/cached value. It evaluates only a bounded, token-whitelisted acyclic
subset. When evaluation is unsupported or a workbook link is external, the
output carries an explicit Human Stop instead of a guessed number.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.source_graph import CellRecord, SourceGraph, capture


class FormulaEvaluationError(ValueError):
    """A preserved formula cannot be evaluated by the bounded local subset."""


def _flatten(values: tuple[Any, ...] | list[Any]) -> list[Any]:
    output: list[Any] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            output.extend(_flatten(list(value)))
        else:
            output.append(value)
    return output


def _formula_functions() -> dict[str, Any]:
    def numeric(values: tuple[Any, ...]) -> list[float]:
        return [float(value) for value in _flatten(values) if isinstance(value, (int, float))]

    def excel_sum(*values: Any) -> float:
        return sum(numeric(values))

    def excel_average(*values: Any) -> float:
        items = numeric(values)
        if not items:
            raise FormulaEvaluationError("AVERAGE has no numeric inputs")
        return sum(items) / len(items)

    def excel_min(*values: Any) -> float:
        items = numeric(values)
        if not items:
            raise FormulaEvaluationError("MIN has no numeric inputs")
        return min(items)

    def excel_max(*values: Any) -> float:
        items = numeric(values)
        if not items:
            raise FormulaEvaluationError("MAX has no numeric inputs")
        return max(items)

    def excel_vlookup(lookup: Any, table: Any, column: Any, approximate: Any = True) -> Any:
        if not isinstance(table, list) or not table or not isinstance(table[0], list):
            raise FormulaEvaluationError("VLOOKUP requires a two-dimensional range")
        column_index = int(column) - 1
        if column_index < 0:
            raise FormulaEvaluationError("VLOOKUP column index must be positive")
        candidates = []
        for row in table:
            if not row or column_index >= len(row):
                continue
            if row[0] == lookup:
                return row[column_index]
            if approximate and isinstance(row[0], (int, float)) and row[0] <= lookup:
                candidates.append(row)
        if approximate and candidates:
            return candidates[-1][column_index]
        raise FormulaEvaluationError(f"VLOOKUP key not found: {lookup!r}")

    def excel_hlookup(lookup: Any, table: Any, row_number: Any, approximate: Any = True) -> Any:
        if not isinstance(table, list) or not table:
            raise FormulaEvaluationError("HLOOKUP requires a two-dimensional range")
        row_index = int(row_number) - 1
        if row_index < 0 or row_index >= len(table):
            raise FormulaEvaluationError("HLOOKUP row index is outside the table")
        for column, value in enumerate(table[0]):
            if value == lookup:
                return table[row_index][column]
        if approximate:
            candidates = [
                index for index, value in enumerate(table[0])
                if isinstance(value, (int, float)) and value <= lookup
            ]
            if candidates:
                return table[row_index][candidates[-1]]
        raise FormulaEvaluationError(f"HLOOKUP key not found: {lookup!r}")

    return {
        "ABS": abs,
        "AND": lambda *values: all(_flatten(values)),
        "AVERAGE": excel_average,
        "COUNT": lambda *values: len(numeric(values)),
        "HLOOKUP": excel_hlookup,
        "IF": lambda condition, when_true, when_false: when_true if condition else when_false,
        "IFERROR": lambda value, fallback: fallback if isinstance(value, Exception) else value,
        "MAX": excel_max,
        "MIN": excel_min,
        "NOT": lambda value: not value,
        "OR": lambda *values: any(_flatten(values)),
        "ROUND": lambda value, digits=0: round(value, int(digits)),
        "SUM": excel_sum,
        "VLOOKUP": excel_vlookup,
    }


def _translate_formula(formula: str) -> str:
    """Translate only validated Excel tokens into a sandboxed Python expression."""
    from openpyxl.formula import Tokenizer

    functions = _formula_functions()
    expression: list[str] = []
    operators = {
        "+": "+", "-": "-", "*": "*", "/": "/", "^": "**",
        "=": "==", "<>": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">=",
    }
    for token in Tokenizer(formula).items:
        if token.type == "WSPACE":
            continue
        if token.type == "OPERAND":
            if token.subtype == "RANGE":
                expression.append(f"ref({token.value!r})")
            elif token.subtype == "NUMBER":
                expression.append(token.value)
            elif token.subtype == "LOGICAL":
                expression.append("True" if token.value.upper() == "TRUE" else "False")
            elif token.subtype == "TEXT":
                value = token.value[1:-1].replace('""', '"')
                expression.append(repr(value))
            else:
                raise FormulaEvaluationError(
                    f"unsupported operand {token.value!r} ({token.subtype})"
                )
        elif token.type == "FUNC":
            if token.subtype == "OPEN":
                name = token.value[:-1].upper()
                if name not in functions:
                    raise FormulaEvaluationError(f"unsupported Excel function: {name}")
                expression.append(f"fn_{name}(")
            else:
                expression.append(")")
        elif token.type == "PAREN":
            expression.append(token.value)
        elif token.type == "SEP" and token.subtype == "ARG":
            expression.append(",")
        elif token.type in {"OPERATOR-INFIX", "OPERATOR-PREFIX"}:
            if token.value not in operators:
                raise FormulaEvaluationError(f"unsupported Excel operator: {token.value}")
            expression.append(operators[token.value])
        elif token.type == "OPERATOR-POSTFIX" and token.value == "%":
            expression.append("*0.01")
        else:
            raise FormulaEvaluationError(
                f"unsupported formula token {token.value!r} ({token.type}/{token.subtype})"
            )
    return "".join(expression)


def _evaluate_formulas(graph: SourceGraph) -> tuple[dict[str, Any], dict[str, str]]:
    """Evaluate the bounded acyclic subset; every other output gets a reason."""
    functions = _formula_functions()
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    visiting: set[str] = set()

    def normalize_reference(reference: str, own_sheet: str) -> str:
        reference = reference.replace("$", "").strip()
        if reference in graph.defined_names:
            destination = str(graph.defined_names[reference]).removeprefix("=")
            if "," in destination:
                raise FormulaEvaluationError(
                    f"multi-area defined name is not executable: {reference}"
                )
            reference = destination
        if "[" in reference and "]" in reference:
            raise FormulaEvaluationError(f"external workbook reference: {reference}")
        if "!" not in reference:
            reference = f"{own_sheet}!{reference}"
        sheet, cell_ref = reference.rsplit("!", 1)
        return f"{sheet.strip(chr(39)).upper()}!{cell_ref.upper()}"

    def resolve(reference: str, own_sheet: str) -> Any:
        normalized = normalize_reference(reference, own_sheet)
        sheet, cell_ref = normalized.rsplit("!", 1)
        range_match = re.fullmatch(
            r"([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)", cell_ref
        )
        if range_match:
            first_col, first_row, last_col, last_row = range_match.groups()

            def number(column: str) -> int:
                result = 0
                for character in column:
                    result = result * 26 + ord(character) - ord("A") + 1
                return result

            def letters(column: int) -> str:
                result = ""
                while column:
                    column, remainder = divmod(column - 1, 26)
                    result = chr(ord("A") + remainder) + result
                return result

            min_col, max_col = sorted((number(first_col), number(last_col)))
            min_row, max_row = sorted((int(first_row), int(last_row)))
            return [
                [evaluate(f"{sheet}!{letters(column)}{row}") for column in range(min_col, max_col + 1)]
                for row in range(min_row, max_row + 1)
            ]
        return evaluate(normalized)

    def evaluate(locator: str) -> Any:
        locator = locator.replace("$", "").upper()
        if locator in values:
            return values[locator]
        if locator in errors:
            raise FormulaEvaluationError(errors[locator])
        cell = graph.cells.get(locator)
        if cell is None:
            raise FormulaEvaluationError(f"referenced cell is absent: {locator}")
        if cell.kind != "formula":
            values[locator] = cell.value
            return cell.value
        if locator in visiting:
            raise FormulaEvaluationError(f"cyclic formula dependency at {locator}")
        if cell.formula_status == "EXTERNAL_LINK":
            raise FormulaEvaluationError(cell.human_stop_reason or "external workbook dependency")
        if cell.formula_status == "UNSUPPORTED_FUNCTION":
            raise FormulaEvaluationError(cell.human_stop_reason or "unsupported Excel function")
        visiting.add(locator)
        try:
            expression = _translate_formula(str(cell.value))
            environment = {"__builtins__": {}, "ref": lambda ref: resolve(ref, cell.sheet)}
            environment.update({f"fn_{name}": function for name, function in functions.items()})
            value = eval(expression, environment, {})  # noqa: S307 - token whitelist above
            if isinstance(value, float) and not math.isfinite(value):
                raise FormulaEvaluationError("formula returned a non-finite number")
            values[locator] = value
            return value
        except FormulaEvaluationError:
            raise
        except Exception as exc:
            raise FormulaEvaluationError(f"{type(exc).__name__}: {exc}") from exc
        finally:
            visiting.discard(locator)

    for locator, cell in sorted(graph.cells.items()):
        if cell.kind != "formula":
            continue
        try:
            evaluate(locator)
        except FormulaEvaluationError as exc:
            errors[locator] = str(exc)
    return (
        {locator: value for locator, value in values.items() if graph.cells[locator].kind == "formula"},
        errors,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _id(prefix: str, digest: str, identity: str) -> str:
    stable = hashlib.sha256(f"{digest}\0{identity}".encode("utf-8")).hexdigest()[:20]
    return f"excel-{prefix}:{stable}"


def _range_members(reference: str, cells: dict[str, CellRecord]) -> list[str]:
    """Expand a preserved range only into cells that the workbook actually has."""
    match = re.fullmatch(
        r"(.+)!([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)",
        reference.upper(),
    )
    if not match:
        return []
    sheet, first_col, first_row, last_col, last_row = match.groups()

    def number(column: str) -> int:
        result = 0
        for character in column:
            result = result * 26 + ord(character) - ord("A") + 1
        return result

    min_col, max_col = sorted((number(first_col), number(last_col)))
    min_row, max_row = sorted((int(first_row), int(last_row)))
    return sorted(
        locator
        for locator, cell in cells.items()
        if cell.sheet == sheet
        and min_col <= cell.col <= max_col
        and min_row <= cell.row <= max_row
    )


def _cell_node(
    cell: CellRecord,
    graph: SourceGraph,
    evaluated_values: dict[str, Any],
    evaluation_errors: dict[str, str],
) -> dict[str, Any]:
    model_node_id = _id("cell", graph.digest, cell.locator)
    is_formula = cell.kind == "formula"
    if is_formula and cell.locator in evaluated_values:
        value = _json_value(evaluated_values[cell.locator])
        value_origin = "DETERMINISTIC_FORMULA_EVALUATION"
        evaluation_status = "EVALUATED"
        unknown = False
        human_stop_reason = None
    elif is_formula:
        value = _json_value(cell.cached_value)
        value_origin = "WORKBOOK_DISPLAYED_CACHE" if cell.cached_value is not None else "UNKNOWN"
        evaluation_status = "HUMAN_STOP"
        unknown = True
        human_stop_reason = evaluation_errors.get(cell.locator) or cell.human_stop_reason
    else:
        value = _json_value(cell.value)
        value_origin = "WORKBOOK_LITERAL"
        evaluation_status = None
        unknown = False
        human_stop_reason = None
    return {
        "id": model_node_id,
        "model_node_id": model_node_id,
        "type": "model_node",
        "label": f"{graph.workbook}::{cell.locator}",
        "source_id": graph.workbook,
        "source_digest": graph.digest,
        "workbook_ref": f"{graph.workbook}::{cell.locator}",
        "locator": cell.locator,
        "sheet": cell.sheet,
        "cell_ref": cell.ref,
        "cell_kind": cell.kind,
        "value": value,
        "value_origin": value_origin,
        "formula_text": str(cell.value) if is_formula else None,
        "cached_value": _json_value(cell.cached_value) if is_formula else None,
        "evaluated_value": _json_value(evaluated_values.get(cell.locator)) if is_formula else None,
        "formula_status": cell.formula_status,
        "evaluation_status": evaluation_status,
        "unknown": unknown,
        "human_stop_reason": human_stop_reason,
        "function_names": list(cell.function_names),
        "unsupported_functions": list(cell.unsupported_functions),
        "external_references": list(cell.external_references),
        "named_references": dict(cell.named_references),
        "number_format": cell.number_format,
        "coverage_status": "unknown" if unknown else "mapped",
    }


def compile_source_graph(graph: SourceGraph) -> dict[str, Any]:
    """Return deterministic model nodes, dependency edges and coverage limits."""
    source_node_id = _id("source", graph.digest, graph.workbook)
    nodes: list[dict[str, Any]] = [{
        "id": source_node_id,
        "type": "source",
        "source_id": graph.workbook,
        "label": graph.workbook,
        "digest": graph.digest,
        "size_bytes": graph.size_bytes,
        "coverage_status": "mapped",
    }]
    edges: list[dict[str, Any]] = []
    formulas: list[dict[str, Any]] = []
    coverage_limits: list[dict[str, Any]] = []
    node_ids: set[str] = {source_node_id}
    cell_node_ids = {
        locator: _id("cell", graph.digest, locator)
        for locator in graph.cells
    }
    evaluated_values, evaluation_errors = _evaluate_formulas(graph)
    cell_nodes: dict[str, dict[str, Any]] = {}

    def add_node(node: dict[str, Any]) -> None:
        if node["id"] not in node_ids:
            nodes.append(node)
            node_ids.add(node["id"])

    for locator in sorted(graph.cells):
        cell = graph.cells[locator]
        node = _cell_node(cell, graph, evaluated_values, evaluation_errors)
        cell_nodes[locator] = node
        add_node(node)
        edges.append({
            "source": source_node_id,
            "target": node["id"],
            "rel": "CONTAINS_MODEL_NODE",
        })

    for locator in sorted(graph.cells):
        cell = graph.cells[locator]
        if cell.kind != "formula":
            continue
        output_id = cell_node_ids[locator]
        output_node = cell_nodes[locator]
        formula_id = _id("formula", graph.digest, locator)
        input_ids: list[str] = []

        for precedent in cell.precedents:
            input_id = cell_node_ids.get(precedent)
            if input_id is None:
                input_id = _id("reference", graph.digest, precedent)
                add_node({
                    "id": input_id,
                    "model_node_id": input_id,
                    "type": "model_reference",
                    "label": precedent,
                    "locator": precedent,
                    "source_id": graph.workbook,
                    "source_digest": graph.digest,
                    "coverage_status": "mapped",
                })
                for member in _range_members(precedent, graph.cells):
                    edges.append({
                        "source": cell_node_ids[member],
                        "target": input_id,
                        "rel": "RANGE_MEMBER",
                        "expressed_reference": precedent,
                    })
            input_ids.append(input_id)
            edges.append({
                "source": input_id,
                "target": output_id,
                "rel": "DIRECTED_MODEL_DEPENDENCY",
                "formula_id": formula_id,
                "expressed_reference": precedent,
            })

        for name, destination in sorted(cell.named_references.items()):
            name_id = _id("name", graph.digest, name)
            add_node({
                "id": name_id,
                "type": "defined_name",
                "label": name,
                "name": name,
                "destination": destination,
                "source_id": graph.workbook,
                "source_digest": graph.digest,
                "coverage_status": "mapped",
            })
            edges.append({
                "source": name_id,
                "target": output_id,
                "rel": "NAMED_MODEL_DEPENDENCY",
                "formula_id": formula_id,
            })

        for external in cell.external_references:
            external_id = _id("external", graph.digest, external)
            add_node({
                "id": external_id,
                "type": "external_model_reference",
                "label": external,
                "locator": external,
                "coverage_status": "human_stop",
                "unknown": True,
            })
            input_ids.append(external_id)
            edges.append({
                "source": external_id,
                "target": output_id,
                "rel": "EXTERNAL_MODEL_DEPENDENCY",
                "formula_id": formula_id,
            })

        formulas.append({
            "formula_id": formula_id,
            "source_id": graph.workbook,
            "source_digest": graph.digest,
            "locator": locator,
            "output_model_node_id": output_id,
            "input_model_node_ids": sorted(set(input_ids)),
            "formula_text": str(cell.value),
            "formula_status": cell.formula_status,
            "displayed_cached_value": _json_value(cell.cached_value),
            "evaluated_value": output_node.get("evaluated_value"),
            "evaluation_status": output_node.get("evaluation_status"),
            "human_stop_reason": output_node.get("human_stop_reason"),
        })
        if output_node.get("evaluation_status") == "HUMAN_STOP":
            coverage_limits.append({
                "limit_id": _id("limit", graph.digest, locator),
                "reason_code": (
                    "EXTERNAL_WORKBOOK_DEPENDENCY"
                    if cell.formula_status == "EXTERNAL_LINK"
                    else "UNSUPPORTED_EXCEL_FUNCTION"
                    if cell.formula_status == "UNSUPPORTED_FUNCTION"
                    else "FORMULA_EVALUATION_BLOCKED"
                ),
                "scope_ids": [output_id],
                "effect": output_node.get("human_stop_reason"),
                "resolution": "HUMAN_STOP",
            })

    nodes.sort(key=lambda item: str(item["id"]))
    edges.sort(key=lambda item: (
        str(item["source"]), str(item["rel"]), str(item["target"])
    ))
    formulas.sort(key=lambda item: str(item["locator"]))
    coverage_limits.sort(key=lambda item: str(item["limit_id"]))
    source_stats = graph.stats()
    return {
        "schema_version": "excel-formula-graph/1.0",
        "source": {
            "source_id": graph.workbook,
            "workbook": graph.workbook,
            "digest": graph.digest,
            "size_bytes": graph.size_bytes,
            "captured_at": graph.captured_at,
            "sheets": [record.name for record in graph.sheets],
            "defined_names": dict(graph.defined_names),
        },
        "status": "HUMAN_STOP" if coverage_limits else "READY",
        "nodes": nodes,
        "edges": edges,
        "formulas": formulas,
        "coverage_limits": coverage_limits,
        "stats": {
            **source_stats,
            "source_human_stops": source_stats["human_stops"],
            "human_stops": len(coverage_limits),
            "model_nodes": sum(node.get("type") == "model_node" for node in nodes),
            "formula_nodes": len(formulas),
            "dependency_edges": sum(
                edge.get("rel") in {
                    "DIRECTED_MODEL_DEPENDENCY",
                    "NAMED_MODEL_DEPENDENCY",
                    "EXTERNAL_MODEL_DEPENDENCY",
                }
                for edge in edges
            ),
            "coverage_limits": len(coverage_limits),
        },
    }


def compile_workbook(path: Path) -> dict[str, Any]:
    return compile_source_graph(capture(path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preserve an Excel workbook as a provenance-rich formula graph"
    )
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    graph = compile_workbook(args.workbook)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    stats = graph["stats"]
    print(
        f"[excel_formula_graph] {args.workbook.name}: "
        f"{stats['formula_nodes']} formulas, {stats['dependency_edges']} dependencies, "
        f"{stats['coverage_limits']} Human Stops"
    )
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
