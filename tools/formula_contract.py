#!/usr/bin/env python3
"""Say precisely which formulas in a mapping can actually be executed.

An execution mapping looks executable: each formula carries an expression,
a variable_binding, input_ids and an output_id. The generic evaluator
(tools/model_evaluator.py) needs exactly that, so a deal should be able to
run with no bespoke Python.

Measured on the real Keystone mapping, it cannot. Not because the evaluator
is weak — because the mapping does not mean what its shape implies. The
`variable_binding` values are not model_node_ids. They are a mix of:

    MN-QUARTERLY-TERM-LOAN[prior]      a node plus a temporal qualifier
    Inputs!B23                          a workbook cell
    Scenario_Drivers!C33:V33            a workbook range
    F-NET-INCOME                        another formula's id, not its node
    sponsor_contrib + term_amort        a sub-expression
    min(0.015, beg_ddtl) if ... else 0  Python source
    0.0875                              a bare literal

and each formula's `source_ref` points back into keystone_model.py. The
mapping was reverse-documented FROM the hand-written module, so it describes
that module rather than specifying a computation. One formula out of
twenty-two happens to satisfy the contract by coincidence.

That distinction matters more than the count: "fix a few formulas" is the
wrong repair. Until mappings are produced BY a compiler that emits real node
references (workbook_model_compiler already works this way), a generic
evaluator cannot be any deal's default — and this module is how that claim
stays measurable instead of being argued about.

Nothing here rewrites a mapping. It classifies, with a reason per formula,
so an unexecutable mapping is visibly unexecutable rather than quietly
producing a third of a model.

    python3 tools/formula_contract.py [path/to/execution_mapping.json]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

# A binding target that is a workbook address rather than a model node:
# "Inputs!B23", "Scenario_Drivers!C33:V33".
_WORKBOOK_REF = re.compile(r"^[A-Za-z_][\w ]*![A-Z]+\d+(:[A-Z]+\d+)?$")
# A node id carrying a qualifier the scalar evaluator has no notion of:
# "MN-QUARTERLY-CASH[prior]", "MN-QUARTERLY-DDTL[period=2031-03-31]".
_QUALIFIED_NODE = re.compile(r"^(?P<node>MN-[A-Z0-9-]+)\[(?P<qualifier>[^\]]+)\]$")
_NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")

EXECUTABLE = "EXECUTABLE"


def _classify_target(target: str, node_ids: set[str], formula_ids: set[str]) -> str:
    """What kind of thing a variable_binding actually points at."""
    target = (target or "").strip()
    if target in node_ids:
        return EXECUTABLE
    if _QUALIFIED_NODE.match(target):
        return "TEMPORAL_QUALIFIER"      # real concept, no scalar equivalent
    if _WORKBOOK_REF.match(target):
        return "WORKBOOK_REFERENCE"      # a cell, never resolved to a node
    if target in formula_ids:
        return "FORMULA_ID"              # should name the formula's output node
    if _NUMERIC.match(target):
        return "BARE_LITERAL"            # a constant with no node behind it
    if target.startswith("MN-"):
        return "UNKNOWN_NODE"            # looks like a node, is not one
    return "EXPRESSION_OR_PROSE"         # sub-expression, Python, or a note


def _free_names(expression: str) -> tuple[set[str], set[str]]:
    """Operand names an expression reads, and any functions it calls.

    Falls back to a token scan when the expression is not valid Python at
    all — some are prose, and prose still deserves a specific reason rather
    than a parse error.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)), set()
    names: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names - calls, calls


def audit_formula(formula: dict[str, Any], node_ids: set[str],
                  formula_ids: set[str]) -> dict[str, Any]:
    """Classify one formula: executable, or why not."""
    formula_id = formula.get("formula_id")
    expression = formula.get("expression_or_function_ref") or ""
    bindings = formula.get("variable_binding") or {}
    reasons: list[str] = []

    if formula.get("evaluation_type") != "ARITHMETIC":
        reasons.append(f"evaluation_type is {formula.get('evaluation_type')!r}, "
                       f"not ARITHMETIC")

    names, calls = _free_names(expression)
    if calls:
        reasons.append("expression calls " + ", ".join(sorted(f"{c}()" for c in calls))
                       + " — the evaluator permits arithmetic only")
    unbound = sorted(names - set(bindings))
    if unbound:
        reasons.append("operands used but not bound: " + ", ".join(unbound))
    unused = sorted(set(bindings) - names)
    if unused:
        reasons.append("bound but never used in the expression: " + ", ".join(unused))

    bad_targets = {}
    for name, target in bindings.items():
        kind = _classify_target(str(target), node_ids, formula_ids)
        if kind != EXECUTABLE:
            bad_targets[name] = kind
    if bad_targets:
        reasons.append("bindings that are not model nodes: " + ", ".join(
            f"{name} ({kind})" for name, kind in sorted(bad_targets.items())))

    if not expression.strip():
        reasons.append("no expression")

    return {
        "formula_id": formula_id,
        "output_id": formula.get("output_id"),
        "executable": not reasons,
        "reasons": reasons,
    }


def audit_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Audit every formula. Reports; never rewrites."""
    node_ids = {n.get("model_node_id") for n in mapping.get("model_nodes", [])}
    formulas = mapping.get("formulas", [])
    formula_ids = {f.get("formula_id") for f in formulas}
    audited = [audit_formula(f, node_ids, formula_ids) for f in formulas]
    executable = [a for a in audited if a["executable"]]
    return {
        "formula_count": len(audited),
        "executable_count": len(executable),
        "executable_ids": [a["formula_id"] for a in executable],
        "formulas": audited,
    }


def main(argv: list[str]) -> int:
    default = Path("pipeline_out/e3/K-PRE/adapter_alpha/execution_mapping.json")
    path = Path(argv[1]) if len(argv) > 1 else default
    if not path.exists():
        print(f"no mapping at {path}", file=sys.stderr)
        return 1
    report = audit_mapping(json.loads(path.read_text()))
    print(f"{path}")
    print(f"  executable: {report['executable_count']} / {report['formula_count']}")
    for entry in report["formulas"]:
        if entry["executable"]:
            print(f"  [OK]   {entry['formula_id']}")
        else:
            print(f"  [NO]   {entry['formula_id']}")
            for reason in entry["reasons"]:
                print(f"           - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
