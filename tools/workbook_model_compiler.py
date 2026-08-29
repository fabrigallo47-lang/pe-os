"""Mechanically compile a captured workbook formula graph into V7 runtime data.

This module deliberately assigns no financial meaning to cells.  Its identities
are workbook addresses, formula text is preserved verbatim, and anything that
cannot be represented as a local dependency remains a declared coverage limit.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.archetype_runtime import instantiate


class WorkbookModelCompilerError(ValueError):
    """A source graph cannot honestly satisfy the minimum V7 model contract."""


_CELL_RANGE_RE = re.compile(
    r"^(?P<sheet>[^!]+)!(?P<start>[A-Z]+[0-9]+)(?::(?P<end>[A-Z]+[0-9]+))?$"
)
_CELL_REF_RE = re.compile(r"^(?P<column>[A-Z]+)(?P<row>[0-9]+)$")


def compile_workbook_formula_graphs(
    source: dict[str, Any] | str | Path,
    case_id: str,
    archetype_id: str = "buyout-v1",
) -> dict[str, Any]:
    """Return a V7 execution graph from source-graph-1 workbook records.

    ``source`` accepts either one ``SourceGraph.to_json()`` payload or the
    ``workbook_formula_graphs.json`` envelope written by ``extract_v2``.  This
    compiler never maps workbook cells to institutional concepts.
    """
    payload = _load_source(source)
    workbooks = _workbooks(payload)
    if not workbooks:
        raise WorkbookModelCompilerError("HUMAN_STOP: no captured workbook graph was supplied")

    model_nodes: dict[str, dict[str, Any]] = {}
    formulas: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    coverage_limits: list[dict[str, Any]] = []
    formula_infos: list[dict[str, Any]] = []

    # First pass establishes every formula node and every raw local operand.
    for workbook in workbooks:
        filename, cells = workbook["filename"], workbook["cells"]
        referenced = {
            item
            for cell in cells.values()
            if cell.get("kind") == "formula"
            for precedent in cell.get("precedents", [])
            for item in _expand_local_precedent(str(precedent), cells)
        }
        for locator, cell in sorted(cells.items()):
            if cell.get("kind") == "formula" or (
                locator in referenced and cell.get("kind") != "formula"
            ):
                node_id = _node_id(filename, locator)
                model_nodes[node_id] = _node(
                    node_id, filename, locator, cell,
                    "DERIVED" if cell.get("kind") == "formula" else "INPUT",
                    cells,
                )
        for locator, cell in sorted(cells.items()):
            if cell.get("kind") == "formula":
                formula_infos.append({"filename": filename, "locator": locator, "cell": cell,
                                      "cells": cells})

    if not formula_infos:
        raise WorkbookModelCompilerError(
            "HUMAN_STOP: captured workbook has no formula cells; no runtime model can be compiled"
        )

    # Second pass creates only source-declared operand bindings and edges.
    for info in formula_infos:
        filename, locator, cell, cells = (
            info["filename"], info["locator"], info["cell"], info["cells"]
        )
        output_id = _node_id(filename, locator)
        formula_id = _formula_id(filename, locator)
        input_ids: list[str] = []
        bindings: dict[str, str | list[str]] = {}
        for precedent in cell.get("precedents", []):
            precedent = str(precedent)
            members = _expand_local_precedent(precedent, cells)
            node_ids = [
                _node_id(filename, member) for member in members
                if _node_id(filename, member) in model_nodes
            ]
            if not node_ids:
                coverage_limits.append(_unresolved_precedent_limit(
                    filename, locator, precedent, output_id
                ))
                continue
            bindings[precedent] = node_ids[0] if len(node_ids) == 1 else node_ids
            for input_id in node_ids:
                if input_id not in input_ids:
                    input_ids.append(input_id)
                    edges.append({
                        "edge_id": _edge_id(input_id, output_id, formula_id),
                        "from_model_node_id": input_id,
                        "to_model_node_id": output_id,
                        "formula_or_function_ref": formula_id,
                        "control_ids": [],
                        "scenario": None,
                    })
        formula = {
            "formula_id": formula_id,
            "description": f"Workbook formula at {locator}",
            "input_ids": input_ids,
            "output_id": output_id,
            "expression_or_function_ref": cell.get("value"),
            "operand_bindings": bindings,
            "evaluation_type": "WORKBOOK_FORMULA",
            "workbook_cell_ref": f"{filename}:{locator}",
            "unit": None,
            "period": None,
            "perimeter": None,
            "source_ref": f"{filename}:{locator}",
            "variable_binding": {},
            "tolerances": {},
        }
        formulas.append(formula)
        model_nodes[output_id]["formula_id"] = formula_id
        model_nodes[output_id]["directed_deps"] = input_ids
        coverage_limits.extend(_formula_coverage_limits(filename, locator, cell, output_id))

    if not edges:
        raise WorkbookModelCompilerError(
            "HUMAN_STOP: formula cells contain no resolvable local precedent relationship; "
            "V7 requires directed model edges and the compiler will not invent one"
        )

    cycles = _cyclic_components(formula_infos, model_nodes)
    case_config = {
        "archetype_id": archetype_id,
        "name": case_id,
        "company": case_id,
        "model_nodes": model_nodes,
        "formulas": formulas,
        "directed_model_edges": edges,
        # These declarations are deliberately inert.  No institutional rule or
        # economic control can be inferred from a cell-address graph.
        "rule_switches": [_no_overrides_declaration()],
        "model_controls": [_coverage_control(sorted(model_nodes))],
    }
    graph = instantiate(case_id, case_config)
    graph["compiler"] = {
        "source": "tools/workbook_model_compiler.py",
        "archetype_id": archetype_id,
        "mode": "MECHANICAL_CELL_ADDRESS_COMPILATION",
    }
    graph["cyclic_component_models"] = cycles
    graph["cyclic_component_solver_configs"] = []
    graph["inverse_solver_configs"] = []
    graph["inverse_solver_models"] = []
    graph["coverage_limits"] = coverage_limits
    graph["admission_manifest"] = {
        "status": "HUMAN_STOP" if coverage_limits or cycles else "MECHANICAL_COMPILE_COMPLETE",
        "reason": (
            "Workbook formulas are mechanically represented; semantic mapping, "
            "institutional rules, and executable solver configuration are not inferred."
        ),
    }
    return graph


def _load_source(source: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, (str, Path)):
        return json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise TypeError("source must be a workbook graph dictionary or JSON path")
    return source


def _workbooks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("cells"), dict):
        return [{"filename": str(payload.get("workbook") or "workbook.xlsx"),
                 "cells": payload["cells"]}]
    out = []
    for item in payload.get("workbooks", []):
        if not isinstance(item, dict) or not isinstance(item.get("graph"), dict):
            continue
        graph = item["graph"]
        if isinstance(graph.get("cells"), dict):
            out.append({"filename": str(item.get("source_filename") or graph.get("workbook")
                                        or "workbook.xlsx"), "cells": graph["cells"]})
    return out


def _node(node_id: str, filename: str, locator: str, cell: dict[str, Any], form: str,
          cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    value = cell.get("value") if form == "INPUT" else cell.get("evaluated_value")
    if form == "DERIVED" and value is None:
        value = cell.get("cached_value")
    label = _adjacent_text_label(cell, cells)
    limits = _formula_coverage_limits(filename, locator, cell, node_id) if form == "DERIVED" else []
    return {
        "id": node_id,
        "label": label,
        "computational_form": form,
        "unit": None,
        "period": None,
        "perimeter": None,
        "epistemic_class": "derived" if form == "DERIVED" else "observed",
        "value_current": value,
        "workbook_ref": f"{filename}:{locator}",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": limits,
    }


def _adjacent_text_label(cell: dict[str, Any], cells: dict[str, dict[str, Any]]) -> str | None:
    row, col, sheet = cell.get("row"), cell.get("col"), cell.get("sheet")
    if not isinstance(row, int) or not isinstance(col, int) or not sheet:
        return None
    # Directly adjacent only; the value is copied verbatim rather than interpreted.
    for candidate_row, candidate_col in ((row, col - 1), (row - 1, col), (row, col + 1), (row + 1, col)):
        if candidate_col < 1 or candidate_row < 1:
            continue
        locator = f"{str(sheet).upper()}!{_column_name(candidate_col)}{candidate_row}"
        candidate = cells.get(locator)
        if candidate and candidate.get("kind") == "text" and isinstance(candidate.get("value"), str):
            return candidate["value"]
    return None


def _expand_local_precedent(precedent: str, cells: dict[str, dict[str, Any]]) -> list[str]:
    match = _CELL_RANGE_RE.match(precedent.upper())
    if not match:
        return []
    start, end, sheet = match.group("start"), match.group("end") or match.group("start"), match.group("sheet")
    start_match, end_match = _CELL_REF_RE.match(start), _CELL_REF_RE.match(end)
    if not start_match or not end_match:
        return []
    first_col, last_col = _column_number(start_match.group("column")), _column_number(end_match.group("column"))
    first_row, last_row = int(start_match.group("row")), int(end_match.group("row"))
    if first_col > last_col or first_row > last_row:
        return []
    return [
        locator for locator in (
            f"{sheet}!{_column_name(col)}{row}"
            for row in range(first_row, last_row + 1)
            for col in range(first_col, last_col + 1)
        ) if locator in cells
    ]


def _cyclic_components(formulas: list[dict[str, Any]], nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    formula_by_key = {(item["filename"], item["locator"]): item for item in formulas}
    adjacency: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for key, info in formula_by_key.items():
        adjacency[key] = [
            (info["filename"], member)
            for precedent in info["cell"].get("precedents", [])
            for member in _expand_local_precedent(str(precedent), info["cells"])
            if (info["filename"], member) in formula_by_key
        ]
    components = _tarjan(adjacency)
    flagged = {
        (item["filename"], item["locator"]) for item in formulas
        if item["cell"].get("evaluation_status") == "CYCLIC_COMPONENT"
    }
    output = []
    for component in components:
        is_loop = len(component) > 1 or any(key in adjacency.get(key, []) for key in component)
        if not is_loop and not set(component) & flagged:
            continue
        members = sorted(_node_id(filename, locator) for filename, locator in component)
        output.append({
            "component_id": "SCC-" + hashlib.sha256("|".join(members).encode()).hexdigest()[:12].upper(),
            "member_ids": members,
            "component_type": "UNRESOLVED_SCC",
            "status": "HUMAN_STOP",
            "reason": "Workbook capture marked this formula component CYCLIC_COMPONENT; no solver method, bounds, or initialization can be inferred mechanically.",
            "workbook_refs": [nodes[member]["workbook_ref"] for member in members],
        })
    # Capture may flag cells individually even where the graph supplied to us
    # omitted enough edges to reconstruct the full SCC.
    included = {member for component in output for member in component["member_ids"]}
    for filename, locator in sorted(flagged):
        node_id = _node_id(filename, locator)
        if node_id not in included:
            output.append({
                "component_id": "SCC-" + hashlib.sha256(node_id.encode()).hexdigest()[:12].upper(),
                "member_ids": [node_id], "component_type": "UNRESOLVED_SCC", "status": "HUMAN_STOP",
                "reason": "Workbook capture marked this cell CYCLIC_COMPONENT; component membership could not be expanded from the supplied source graph.",
                "workbook_refs": [nodes[node_id]["workbook_ref"]],
            })
    return output


def _tarjan(adjacency: dict[tuple[str, str], list[tuple[str, str]]]) -> list[list[tuple[str, str]]]:
    index = 0
    stack: list[tuple[str, str]] = []
    indices: dict[tuple[str, str], int] = {}
    lowlinks: dict[tuple[str, str], int] = {}
    on_stack: set[tuple[str, str]] = set()
    result: list[list[tuple[str, str]]] = []
    def visit(node: tuple[str, str]) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1; stack.append(node); on_stack.add(node)
        for target in adjacency.get(node, []):
            if target not in indices:
                visit(target); lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
            component = []
            while True:
                target = stack.pop(); on_stack.remove(target); component.append(target)
                if target == node:
                    break
            result.append(component)
    for node in sorted(adjacency):
        if node not in indices:
            visit(node)
    return result


def _formula_coverage_limits(filename: str, locator: str, cell: dict[str, Any], scope_id: str) -> list[dict[str, Any]]:
    status = cell.get("evaluation_status")
    if status in {None, "CALCULATED_ACYCLIC", "CACHED_VALUE_AVAILABLE"}:
        return []
    return [{"limit_id": f"CELL-STATUS-{_safe(filename)}-{_safe(locator)}", "scope_ids": [scope_id],
             "reason_code": str(status), "effect": cell.get("human_stop_reason") or "Formula value is unresolved in the captured workbook."}]


def _unresolved_precedent_limit(filename: str, locator: str, precedent: str, output_id: str) -> dict[str, Any]:
    return {"limit_id": f"UNRESOLVED-PRECEDENT-{_safe(filename)}-{_safe(locator)}-{_safe(precedent)}",
            "scope_ids": [output_id], "reason_code": "UNRESOLVED_WORKBOOK_PRECEDENT",
            "effect": f"{filename}:{locator} references {precedent}, which has no local captured cell node; HUMAN_STOP required."}


def _no_overrides_declaration() -> dict[str, Any]:
    return {"rule_switch_id": "RS-NO-INSTITUTIONAL-OVERRIDES-DECLARED", "selector_input_ids": [],
            "branches": [], "dependent_ids": [], "source_ref": "workbook_formula_graphs.json",
            "declaration_type": "NO_INSTITUTIONAL_OVERRIDES_DECLARED",
            "description": "Mechanical workbook compilation found no separately declared institutional rule switches. This is a coverage declaration, not a business rule."}


def _coverage_control(scope_ids: list[str]) -> dict[str, Any]:
    return {"control_id": "CTRL-WORKBOOK-DEPENDENCY-COVERAGE", "scope_ids": scope_ids,
            "input_ids": scope_ids, "pass_condition_type": "coverage_declaration",
            "pass_condition": "Every source-declared formula precedent must resolve to a compiled local model node; unresolved precedents remain HUMAN_STOP coverage limits.",
            "fail_outcome": "HUMAN_STOP", "pass_outcome": "DECLARED", "blocks_on_fail": scope_ids,
            "description": "A provenance coverage control, not an inferred financial covenant or institutional policy."}


def _node_id(filename: str, locator: str) -> str:
    return "MN-" + _safe(filename) + "-" + _safe(locator)


def _formula_id(filename: str, locator: str) -> str:
    return "F-" + _safe(filename) + "-" + _safe(locator)


def _edge_id(source: str, target: str, formula: str) -> str:
    return "E-" + hashlib.sha256(f"{source}|{target}|{formula}".encode()).hexdigest()[:16].upper()


def _safe(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", str(value).upper()).strip("-")


def _column_number(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result
