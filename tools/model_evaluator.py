#!/usr/bin/env python3
"""Evaluate any deal's execution mapping, with no per-deal Python.

Today a deal's model is a hand-written module: tools/keystone_model.py is
1198 lines transcribing keystone_lbo_model_working.xlsx cell by cell, and
bridge_v7 named it as every deal's runtime. That does not scale past one
deal, and for a deal whose model is not that workbook it is not a missing
model but the WRONG one.

It is also unnecessary. An execution mapping already carries everything an
evaluator needs, declaratively:

    formula_id, input_ids, output_id, evaluation_type,
    expression_or_function_ref   "firm_ebitda + related_party_rent_norm"
    variable_binding             {"firm_ebitda": "MN-FIRM-EBITDA", ...}

So the deal-specific part is DATA (a graph produced from the deal's own
workbook by workbook_model_compiler, or declared by an analyst) and the
generic part is this: one engine, every deal, zero bespoke Python.

Honesty over coverage, following workbook_model_compiler's own rule that
"anything that cannot be represented as a local dependency remains a
declared coverage limit": an evaluation_type this module cannot execute
does not produce a guessed number. The node stays uncomputed and the
reason is reported. A model that admits what it could not compute is
usable; one that quietly invents the missing half is not.

Stdlib only, per CLAUDE.md's v1 constraint. Expressions are walked as an
AST over a whitelist — never eval() — because these expressions arrive from
compiled workbooks, and a spreadsheet is not a trust boundary.
"""
from __future__ import annotations

import ast
import operator
from typing import Any

# Arithmetic only. No calls, no attribute access, no names beyond the
# formula's own declared bindings — a compiled workbook must not be able to
# reach anything in this process.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# What this evaluator can actually execute. The rest are real evaluation
# types in the mapping (dated vectors, XIRR, solvers) that need a runtime
# this module does not have; they are declared, not faked.
EXECUTABLE_TYPES = frozenset({"ARITHMETIC"})


class UnsupportedExpression(ValueError):
    """The expression uses something outside the arithmetic whitelist."""


def evaluate_expression(expression: str, values: dict[str, float]) -> float:
    """Evaluate one arithmetic expression against named operand values."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsupportedExpression(f"cannot parse {expression!r}: {exc}") from exc

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise UnsupportedExpression(f"non-numeric constant {node.value!r}")
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise UnsupportedExpression(f"unbound operand {node.id!r}")
            return float(values[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](walk(node.operand))
        raise UnsupportedExpression(
            f"{type(node).__name__} is not permitted in a model expression"
        )

    return walk(tree)


def _seed_values(mapping: dict[str, Any]) -> tuple[dict[str, float], list[dict]]:
    """Starting values: the nodes the model takes as given, not computed."""
    values: dict[str, float] = {}
    limits: list[dict] = []
    for node in mapping.get("model_nodes", []):
        node_id = node.get("model_node_id")
        if node.get("computational_form") != "DIRECT_INPUT":
            continue
        initial = node.get("initial_value")
        if isinstance(initial, (int, float)) and not isinstance(initial, bool):
            values[node_id] = float(initial)
        else:
            limits.append({
                "node_id": node_id,
                "reason": "DIRECT_INPUT carries no numeric initial_value",
            })
    return values, limits


def evaluate_mapping(mapping: dict[str, Any],
                     overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Compute every node this mapping can honestly compute.

    `overrides` replaces input values before evaluation — this is how a new
    claim is applied: bind it to the node it bears on, re-evaluate, and the
    difference against an unoverridden run is the economic delta. The
    evaluator itself holds no state and makes no decision about whether that
    delta may be accepted; that is the dynamics runtime's job, under the
    materiality and authority policies.

    Returns values, the order they were computed in, and — as first-class
    output, not an error log — everything it declined to compute and why.
    """
    values, limits = _seed_values(mapping)
    values.update(overrides or {})

    formulas = list(mapping.get("formulas", []))
    pending = []
    for formula in formulas:
        if formula.get("evaluation_type") not in EXECUTABLE_TYPES:
            limits.append({
                "node_id": formula.get("output_id"),
                "formula_id": formula.get("formula_id"),
                "reason": f"evaluation_type {formula.get('evaluation_type')!r} "
                          f"is not executable by this evaluator",
            })
            continue
        pending.append(formula)

    # Resolve by repeated passes rather than a topological sort: a formula
    # becomes computable once its operands exist, whatever order the mapping
    # lists them in, and whatever is still unresolved when no pass makes
    # progress is a genuine cycle or a missing input — reported, not guessed.
    order: list[str] = []
    progress = True
    while pending and progress:
        progress = False
        still_pending = []
        for formula in pending:
            bindings = formula.get("variable_binding") or {}
            operands = {}
            missing = [node_id for node_id in bindings.values() if node_id not in values]
            if missing:
                still_pending.append(formula)
                continue
            for name, node_id in bindings.items():
                operands[name] = values[node_id]
            try:
                result = evaluate_expression(
                    formula.get("expression_or_function_ref") or "", operands)
            except UnsupportedExpression as exc:
                limits.append({
                    "node_id": formula.get("output_id"),
                    "formula_id": formula.get("formula_id"),
                    "reason": str(exc),
                })
                progress = True          # resolved, as a declared limit
                continue
            values[formula["output_id"]] = result
            order.append(formula["formula_id"])
            progress = True
        pending = still_pending

    for formula in pending:
        bindings = formula.get("variable_binding") or {}
        limits.append({
            "node_id": formula.get("output_id"),
            "formula_id": formula.get("formula_id"),
            "reason": "inputs never became available (cycle or missing input): "
                      + ", ".join(sorted(
                          node_id for node_id in bindings.values() if node_id not in values)),
        })

    return {
        "values": values,
        "computed_order": order,
        "declared_limits": limits,
        "computed_count": len(order),
        "limit_count": len(limits),
    }


def delta_for_claim(mapping: dict[str, Any], node_id: str, value: float) -> dict[str, Any]:
    """What changes downstream if this node takes this value.

    The generic equivalent of a per-deal propagate_claim(): evaluate twice,
    report which nodes moved. It states the difference and stops there — it
    does not decide whether the change is material or who may accept it.
    """
    base = evaluate_mapping(mapping)
    after = evaluate_mapping(mapping, overrides={node_id: value})
    moved = []
    for key, new_value in after["values"].items():
        old_value = base["values"].get(key)
        if old_value is None or old_value != new_value:
            moved.append({"node_id": key, "old": old_value, "new": new_value})
    return {
        "applied": {"node_id": node_id, "value": value},
        "updated_nodes": sorted(moved, key=lambda item: item["node_id"]),
        "declared_limits": after["declared_limits"],
    }
