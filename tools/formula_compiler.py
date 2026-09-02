#!/usr/bin/env python3
"""Compile Excel formulas into PANTA's bounded execution grammar.

PAN-51 preserves the workbook literally and PAN-65 resolves workbook locators
to semantic model-node identities.  This module joins those two facts without
adding financial interpretation:

* cell references become explicit ``operand_bindings`` and ``input_ids``;
* ``SUM`` ranges are expanded into scalar additions;
* ``IF`` expressions also emit governed ``rule_switches``;
* ``MIN`` and ``MAX`` remain calls understood by the decimal runtime;
* formula cycles become fixed-point solver configurations;
* every formula that cannot be translated becomes a coverage limit, and every
  formula depending on such an output is stopped as well.

The compiler accepts JSON dictionaries or paths.  Its result is deterministic
under input ordering and contains no evaluated value copied into an executable
formula.  ``recalculate_compilation`` is an acceptance/diagnostic helper: it
executes the emitted grammar, uses ``tools.extract_v3.solve_component`` for
cycles, and compares the result with L1's ``evaluated_value`` where available.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.relation_rules import annotate_edge  # noqa: E402


SCHEMA_VERSION = "excel-formula-compilation/1.0"
COMPILER_VERSION = "pan66-1.0"
SUPPORTED_FUNCTIONS = frozenset({"IF", "MAX", "MIN", "SUM"})

_CELL_REF_RE = re.compile(
    r"^(?:(?P<sheet>'(?:[^']|'')+'|[^!]+)!)?"
    r"(?P<c1>\$?[A-Z]{1,3}\$?\d+)"
    r"(?::(?P<c2>\$?[A-Z]{1,3}\$?\d+))?$",
    re.IGNORECASE,
)
_CELL_ONLY_RE = re.compile(r"^\$?(?P<column>[A-Z]{1,3})\$?(?P<row>\d+)$", re.I)
_SAFE_ID_RE = re.compile(r"[^A-Z0-9]+")


class FormulaCompileError(ValueError):
    """One formula cannot be represented honestly by the runtime grammar."""

    def __init__(self, reason_code: str, detail: str):
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class Expression:
    kind: str
    value: str = ""
    children: tuple["Expression", ...] = ()


@dataclass
class _FormulaState:
    locator: str
    output_id: str
    formula_id: str
    source_ref: str
    original_formula: str
    own_sheet: str
    cell: Mapping[str, Any]
    compiler: "FormulaCompiler"
    operand_bindings: dict[str, str] = field(default_factory=dict)
    input_ids: list[str] = field(default_factory=list)
    referenced_locators: list[str] = field(default_factory=list)
    rule_switches: list[dict[str, Any]] = field(default_factory=list)
    function_names: set[str] = field(default_factory=set)
    if_index: int = 0

    def bind(self, locator: str) -> str:
        model_node_id = self.compiler.binding_for(locator)
        variable = self.compiler.variable_for(locator)
        existing = self.operand_bindings.get(variable)
        if existing is not None and existing != model_node_id:
            raise FormulaCompileError(
                "AMBIGUOUS_FORMULA_OPERAND_BINDING",
                f"{self.locator} maps {variable} to two model nodes.",
            )
        self.operand_bindings[variable] = model_node_id
        if model_node_id not in self.input_ids:
            self.input_ids.append(model_node_id)
        if locator not in self.referenced_locators:
            self.referenced_locators.append(locator)
        return variable


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _safe(value: str) -> str:
    return _SAFE_ID_RE.sub("-", str(value).upper()).strip("-")


def _stable_id(prefix: str, value: Any, *, label: str = "") -> str:
    stem = f"-{_safe(label)[:48]}" if label else ""
    return f"{prefix}{stem}-{_digest(value)[:12].upper()}"


def _load_json(value: Mapping[str, Any] | Sequence[Any] | str | Path) -> Any:
    if isinstance(value, (str, Path)):
        return json.loads(Path(value).read_text(encoding="utf-8"))
    return value


def _normalize_sheet(value: str) -> str:
    sheet = str(value).strip()
    if sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    return sheet.upper()


def _strip_cell(value: str) -> str:
    return value.replace("$", "").upper()


def normalize_locator(value: str, own_sheet: str = "") -> str:
    """Return the L1 ``SHEET!A1`` form, rejecting workbook-qualified refs."""

    raw = str(value or "").strip()
    if "::" in raw:
        raw = raw.rsplit("::", 1)[1]
    elif ":" in raw and "!" in raw:
        prefix, rest = raw.split(":", 1)
        if prefix.lower().endswith((".xlsx", ".xlsm", ".xlsb", ".ods")):
            raw = rest
    if "[" in raw or "]" in raw:
        raise FormulaCompileError(
            "EXTERNAL_WORKBOOK_REFERENCE",
            f"External workbook reference is not locally executable: {value}",
        )
    match = _CELL_REF_RE.fullmatch(raw)
    if not match:
        raise FormulaCompileError(
            "UNSUPPORTED_EXCEL_REFERENCE",
            f"Unsupported Excel reference: {value}",
        )
    sheet = _normalize_sheet(match.group("sheet") or own_sheet)
    if not sheet:
        raise FormulaCompileError(
            "MISSING_REFERENCE_SHEET",
            f"Reference {value} has no owning sheet.",
        )
    ref = _strip_cell(match.group("c1"))
    if match.group("c2"):
        ref += ":" + _strip_cell(match.group("c2"))
    return f"{sheet}!{ref}"


def _column_number(column: str) -> int:
    number = 0
    for character in column.upper():
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _binding_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("bindings", "admitted", "resolved_bindings"):
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]
    # A direct locator -> model-node dictionary is useful for mechanical tests
    # and for the PAN-55 cell-address compiler.
    if payload and all(isinstance(value, str) for value in payload.values()):
        return [
            {"locator": locator, "model_node_id": model_node_id}
            for locator, model_node_id in payload.items()
        ]
    return []


def _source_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("source_graph must be a JSON object or path")
    if isinstance(payload.get("cells"), Mapping):
        return dict(payload)
    workbooks = payload.get("workbooks")
    if isinstance(workbooks, Sequence):
        usable = [
            item.get("graph")
            for item in workbooks
            if isinstance(item, Mapping)
            and isinstance(item.get("graph"), Mapping)
            and isinstance(item["graph"].get("cells"), Mapping)
        ]
        if len(usable) == 1:
            return dict(usable[0])
        if len(usable) > 1:
            raise FormulaCompileError(
                "MULTIPLE_WORKBOOKS_REQUIRE_SEPARATE_COMPILATION",
                "Compile each workbook independently so cell locators remain unambiguous.",
            )
    raise FormulaCompileError(
        "MISSING_SOURCE_CELLS",
        "The source graph contains no L1 cells.",
    )


class _Parser:
    """Small Pratt parser over openpyxl's lexical Excel tokens."""

    _PRECEDENCE = {
        "=": 1,
        "<>": 1,
        "<": 1,
        ">": 1,
        "<=": 1,
        ">=": 1,
        "+": 2,
        "-": 2,
        "*": 3,
        "/": 3,
        "^": 4,
    }

    def __init__(self, formula: str):
        try:
            from openpyxl.formula import Tokenizer
        except ImportError as exc:  # pragma: no cover - dependency contract
            raise FormulaCompileError(
                "FORMULA_TOKENIZER_UNAVAILABLE",
                "openpyxl is required to tokenize Excel formulas.",
            ) from exc
        try:
            self.tokens = [token for token in Tokenizer(formula).items if token.type != "WSPACE"]
        except Exception as exc:
            raise FormulaCompileError(
                "INVALID_EXCEL_FORMULA",
                f"Excel tokenizer rejected {formula!r}: {exc}",
            ) from exc
        self.position = 0

    def parse(self) -> Expression:
        if not self.tokens:
            raise FormulaCompileError("EMPTY_EXCEL_FORMULA", "Formula contains no expression.")
        expression = self._expression(0)
        if self.position != len(self.tokens):
            token = self.tokens[self.position]
            raise FormulaCompileError(
                "UNSUPPORTED_EXCEL_SYNTAX",
                f"Unexpected token {token.value!r} ({token.type}/{token.subtype}).",
            )
        return expression

    def _peek(self) -> Any | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _take(self) -> Any:
        token = self._peek()
        if token is None:
            raise FormulaCompileError("INVALID_EXCEL_FORMULA", "Unexpected end of formula.")
        self.position += 1
        return token

    def _expression(self, minimum_precedence: int) -> Expression:
        left = self._prefix()
        while True:
            token = self._peek()
            if token is not None and token.type == "OPERATOR-POSTFIX":
                if token.value != "%":
                    raise FormulaCompileError(
                        "UNSUPPORTED_EXCEL_OPERATOR",
                        f"Unsupported postfix operator {token.value!r}.",
                    )
                self._take()
                left = Expression("postfix", "%", (left,))
                continue
            if token is None or token.type != "OPERATOR-INFIX":
                break
            operator = token.value
            precedence = self._PRECEDENCE.get(operator)
            if precedence is None:
                raise FormulaCompileError(
                    "UNSUPPORTED_EXCEL_OPERATOR",
                    f"Unsupported infix operator {operator!r}.",
                )
            if precedence < minimum_precedence:
                break
            self._take()
            # Excel exponentiation is right-associative; the rest are left-associative.
            right = self._expression(precedence if operator == "^" else precedence + 1)
            left = Expression("binary", operator, (left, right))
        return left

    def _prefix(self) -> Expression:
        token = self._take()
        if token.type == "OPERATOR-PREFIX":
            if token.value not in {"+", "-"}:
                raise FormulaCompileError(
                    "UNSUPPORTED_EXCEL_OPERATOR",
                    f"Unsupported prefix operator {token.value!r}.",
                )
            return Expression("unary", token.value, (self._expression(5),))
        if token.type == "OPERAND":
            subtype = token.subtype.upper()
            if subtype == "RANGE":
                return Expression("reference", token.value)
            if subtype == "NUMBER":
                return Expression("number", token.value)
            if subtype == "LOGICAL":
                return Expression("logical", token.value.upper())
            if subtype == "TEXT":
                return Expression("text", token.value)
            raise FormulaCompileError(
                "UNSUPPORTED_EXCEL_OPERAND",
                f"Unsupported operand {token.value!r} ({token.subtype}).",
            )
        if token.type == "PAREN" and token.subtype == "OPEN":
            value = self._expression(0)
            close = self._take()
            if close.type != "PAREN" or close.subtype != "CLOSE":
                raise FormulaCompileError("INVALID_EXCEL_FORMULA", "Unclosed parenthesis.")
            return Expression("group", children=(value,))
        if token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].strip().upper()
            if name.startswith("_XLFN."):
                name = name[6:]
            arguments: list[Expression] = []
            next_token = self._peek()
            if next_token is not None and next_token.type == "FUNC" and next_token.subtype == "CLOSE":
                self._take()
                return Expression("function", name, ())
            while True:
                arguments.append(self._expression(0))
                separator = self._take()
                if separator.type == "FUNC" and separator.subtype == "CLOSE":
                    break
                if separator.type != "SEP" or separator.subtype != "ARG":
                    raise FormulaCompileError(
                        "INVALID_EXCEL_FORMULA",
                        f"Expected function argument separator, got {separator.value!r}.",
                    )
            return Expression("function", name, tuple(arguments))
        raise FormulaCompileError(
            "UNSUPPORTED_EXCEL_SYNTAX",
            f"Unexpected token {token.value!r} ({token.type}/{token.subtype}).",
        )


class FormulaCompiler:
    def __init__(
        self,
        source_graph: Mapping[str, Any] | str | Path,
        binding_resolution: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
        *,
        absolute_residual_tolerance: str = "0.000000001",
        relative_residual_tolerance: str = "0.000000001",
        maximum_iterations: int = 500,
        damping: str = "0.5",
    ):
        self.source = _source_payload(_load_json(source_graph))
        self.binding_payload = _load_json(binding_resolution)
        self.absolute_residual_tolerance = str(absolute_residual_tolerance)
        self.relative_residual_tolerance = str(relative_residual_tolerance)
        self.maximum_iterations = int(maximum_iterations)
        self.damping = str(damping)
        if self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be positive")

        self.cells: dict[str, Mapping[str, Any]] = {}
        for raw_locator, raw_cell in self.source.get("cells", {}).items():
            if not isinstance(raw_cell, Mapping):
                continue
            try:
                locator = normalize_locator(str(raw_locator))
            except FormulaCompileError:
                continue
            self.cells[locator] = raw_cell

        by_locator: dict[str, set[str]] = defaultdict(set)
        for item in _binding_items(self.binding_payload):
            locator = item.get("locator") or item.get("cell") or item.get("workbook_cell_ref")
            model_node_id = item.get("model_node_id") or item.get("mn_id") or item.get("id")
            if not locator or not model_node_id:
                continue
            try:
                normalized = normalize_locator(str(locator))
            except FormulaCompileError:
                continue
            by_locator[normalized].add(str(model_node_id))
        self.binding_candidates = {
            locator: tuple(sorted(model_ids)) for locator, model_ids in by_locator.items()
        }

        defined = self.source.get("defined_names")
        self.defined_names = {
            str(name).upper(): str(destination)
            for name, destination in (defined.items() if isinstance(defined, Mapping) else [])
        }
        source_identity = {
            "digest": self.source.get("digest"),
            "workbook": self.source.get("workbook"),
            "cells": self.source.get("cells", {}),
        }
        self.source_digest = str(self.source.get("digest") or _digest(source_identity))
        self.binding_digest = str(
            self.binding_payload.get("input_digest")
            if isinstance(self.binding_payload, Mapping) and self.binding_payload.get("input_digest")
            else "sha256:" + _digest(self.binding_candidates)
        )
        self.input_digest = "sha256:" + _digest(
            {
                "compiler": COMPILER_VERSION,
                "source": source_identity,
                "bindings": self.binding_candidates,
                "solver": {
                    "absolute": self.absolute_residual_tolerance,
                    "relative": self.relative_residual_tolerance,
                    "iterations": self.maximum_iterations,
                    "damping": self.damping,
                },
            }
        )

    def variable_for(self, locator: str) -> str:
        return "cell_" + _digest(normalize_locator(locator))[:12]

    def binding_for(self, locator: str) -> str:
        normalized = normalize_locator(locator)
        candidates = self.binding_candidates.get(normalized, ())
        if not candidates:
            raise FormulaCompileError(
                "MISSING_R6_BINDING",
                f"No PAN-65 binding resolves referenced cell {normalized}.",
            )
        if len(candidates) != 1:
            raise FormulaCompileError(
                "AMBIGUOUS_R6_BINDING",
                f"Cell {normalized} maps to multiple model nodes: {', '.join(candidates)}.",
            )
        return candidates[0]

    def _resolve_reference(
        self,
        token: str,
        own_sheet: str,
        cell: Mapping[str, Any],
        *,
        depth: int = 0,
    ) -> str:
        if depth > 8:
            raise FormulaCompileError(
                "CYCLIC_DEFINED_NAME",
                f"Defined-name expansion is cyclic at {token}.",
            )
        try:
            return normalize_locator(token, own_sheet)
        except FormulaCompileError as original:
            names: dict[str, str] = dict(self.defined_names)
            local_names = cell.get("named_references")
            if isinstance(local_names, Mapping):
                names.update({str(name).upper(): str(value) for name, value in local_names.items()})
            destination = names.get(str(token).upper())
            if destination is None:
                raise original
            destination = destination.removeprefix("=").strip()
            if "," in destination or ";" in destination:
                raise FormulaCompileError(
                    "UNSUPPORTED_MULTI_AREA_NAME",
                    f"Defined name {token} points to multiple areas.",
                )
            return self._resolve_reference(
                destination,
                own_sheet,
                cell,
                depth=depth + 1,
            )

    def _range_members(self, locator: str, *, numeric_only: bool = True) -> list[str]:
        sheet, reference = locator.rsplit("!", 1)
        if ":" not in reference:
            return [locator]
        start, end = reference.split(":", 1)
        first = _CELL_ONLY_RE.fullmatch(start)
        last = _CELL_ONLY_RE.fullmatch(end)
        if not first or not last:
            raise FormulaCompileError(
                "UNSUPPORTED_EXCEL_REFERENCE",
                f"Cannot expand range {locator}.",
            )
        first_col, last_col = sorted(
            (_column_number(first.group("column")), _column_number(last.group("column")))
        )
        first_row, last_row = sorted((int(first.group("row")), int(last.group("row"))))
        members: list[str] = []
        for row in range(first_row, last_row + 1):
            for column in range(first_col, last_col + 1):
                member = f"{sheet}!{_column_name(column)}{row}"
                cell = self.cells.get(member)
                # Excel aggregate functions ignore blank, text and logical cells
                # reached through a range.  A missing L1 cell is an empty cell.
                if cell is None:
                    continue
                if numeric_only and str(cell.get("kind", "")).lower() not in {
                    "number",
                    "formula",
                    "date",
                }:
                    continue
                members.append(member)
        return members

    def _reference_locators(
        self, expression: Expression, state: _FormulaState
    ) -> list[str]:
        output: list[str] = []

        def visit(node: Expression) -> None:
            if node.kind == "reference":
                resolved = self._resolve_reference(
                    node.value, state.own_sheet, state.cell
                )
                for member in self._range_members(resolved):
                    if member not in output:
                        output.append(member)
            for child in node.children:
                visit(child)

        visit(expression)
        return output

    def _compile_reference(self, expression: Expression, state: _FormulaState) -> str:
        locator = self._resolve_reference(expression.value, state.own_sheet, state.cell)
        if ":" in locator.rsplit("!", 1)[1]:
            raise FormulaCompileError(
                "RANGE_OUTSIDE_AGGREGATE_FUNCTION",
                f"Range {locator} is only executable inside SUM, MIN or MAX.",
            )
        if locator not in self.cells:
            raise FormulaCompileError(
                "MISSING_SOURCE_REFERENCE",
                f"Formula {state.locator} references absent cell {locator}.",
            )
        return state.bind(locator)

    def _compile_condition(
        self, expression: Expression, state: _FormulaState
    ) -> tuple[str, str, list[str], str, dict[str, str]]:
        """Return true condition, complement, selectors and evaluation mode.

        The current transition runtime has a fast path for one selector against
        a numeric threshold.  Excel also permits constants, arithmetic and
        cell-to-cell comparisons.  Those remain deterministic: they are stored
        as complete bounded expressions and evaluated with the formula rather
        than being reduced to a false single-selector threshold.
        """

        if expression.kind == "reference":
            variable = self._compile_reference(expression, state)
            model_node_id = state.operand_bindings[variable]
            return (
                f"{variable} != 0",
                f"{variable} == 0",
                [model_node_id],
                "SINGLE_SELECTOR_THRESHOLD",
                {variable: model_node_id},
            )

        if expression.kind == "binary" and expression.value in {
            "=", "<>", "<", ">", "<=", ">="
        }:
            left, right = expression.children
            operator = expression.value
            if left.kind == "number" and right.kind == "reference":
                left, right = right, left
                operator = {
                    "<": ">", ">": "<", "<=": ">=", ">=": "<=",
                    "=": "=", "<>": "<>",
                }[operator]
            if left.kind == "reference" and right.kind == "number":
                variable = self._compile_reference(left, state)
                number = _decimal_literal(right.value)
                python_operator = {"=": "==", "<>": "!="}.get(operator, operator)
                complement = {
                    "==": "!=", "!=": "==", "<": ">=", ">": "<=",
                    "<=": ">", ">=": "<",
                }[python_operator]
                return (
                    f"{variable} {python_operator} {number}",
                    f"{variable} {complement} {number}",
                    [state.operand_bindings[variable]],
                    "SINGLE_SELECTOR_THRESHOLD",
                    {variable: state.operand_bindings[variable]},
                )

        true_expression = self._compile_expression(expression, state)
        if expression.kind == "binary" and expression.value in {
            "=", "<>", "<", ">", "<=", ">="
        }:
            complement_operator = {
                "=": "<>", "<>": "=", "<": ">=", ">": "<=",
                "<=": ">", ">=": "<",
            }[expression.value]
            false_expression = self._compile_expression(
                Expression("binary", complement_operator, expression.children), state
            )
        else:
            false_expression = f"({true_expression}) == 0"
        selector_ids = []
        condition_bindings: dict[str, str] = {}
        for locator in self._reference_locators(expression, state):
            model_node_id = self.binding_for(locator)
            condition_bindings[self.variable_for(locator)] = model_node_id
            if model_node_id not in selector_ids:
                selector_ids.append(model_node_id)
        return (
            true_expression,
            false_expression,
            selector_ids,
            "GENERAL_EXPRESSION",
            dict(sorted(condition_bindings.items())),
        )

    def _compile_expression(self, expression: Expression, state: _FormulaState) -> str:
        if expression.kind == "number":
            return _decimal_literal(expression.value)
        if expression.kind == "logical":
            return "1" if expression.value == "TRUE" else "0"
        if expression.kind == "text":
            raise FormulaCompileError(
                "NON_NUMERIC_FORMULA_RESULT",
                f"Text operands are not part of the decimal runtime grammar at {state.locator}.",
            )
        if expression.kind == "reference":
            return self._compile_reference(expression, state)
        if expression.kind == "group":
            return f"({self._compile_expression(expression.children[0], state)})"
        if expression.kind == "unary":
            return f"({expression.value}{self._compile_expression(expression.children[0], state)})"
        if expression.kind == "postfix":
            return f"({self._compile_expression(expression.children[0], state)} * 0.01)"
        if expression.kind == "binary":
            left = self._compile_expression(expression.children[0], state)
            right = self._compile_expression(expression.children[1], state)
            operator = {"^": "**", "=": "==", "<>": "!="}.get(
                expression.value, expression.value
            )
            return f"({left} {operator} {right})"
        if expression.kind != "function":
            raise FormulaCompileError(
                "UNSUPPORTED_EXCEL_SYNTAX",
                f"Unsupported expression node {expression.kind} at {state.locator}.",
            )

        function_name = expression.value.upper()
        state.function_names.add(function_name)
        if function_name not in SUPPORTED_FUNCTIONS:
            raise FormulaCompileError(
                "UNSUPPORTED_EXCEL_FUNCTION",
                f"Function {function_name} is not in PAN-66's declared grammar.",
            )
        if function_name == "IF":
            if len(expression.children) != 3:
                raise FormulaCompileError(
                    "INVALID_IF_ARITY",
                    f"IF at {state.locator} must have exactly three arguments.",
                )
            condition, when_true, when_false = expression.children
            (
                true_condition,
                false_condition,
                selectors,
                condition_evaluation_type,
                condition_bindings,
            ) = self._compile_condition(condition, state)
            true_expression = self._compile_expression(when_true, state)
            false_expression = self._compile_expression(when_false, state)
            state.if_index += 1
            switch_id = _stable_id(
                "RS-EXCEL",
                [state.formula_id, state.if_index, true_condition, false_condition],
                label=state.locator,
            )
            state.rule_switches.append(
                {
                    "rule_switch_id": switch_id,
                    "selector_input_ids": selectors,
                    "branches": [
                        {
                            "branch_id": f"{switch_id}-TRUE",
                            "condition": true_condition,
                            "value_expression": true_expression,
                        },
                        {
                            "branch_id": f"{switch_id}-FALSE",
                            "condition": false_condition,
                            "value_expression": false_expression,
                        },
                    ],
                    "dependent_ids": [state.output_id],
                    "source_ref": state.source_ref,
                    "formula_id": state.formula_id,
                    "output_id": state.output_id,
                    "condition_evaluation_type": condition_evaluation_type,
                    "operand_bindings": condition_bindings,
                    "minimum_materiality_class": "M1_PROFESSIONAL_REVIEW",
                    "reason_codes": ["EXCEL_IF_COMPILED_TO_RULE_SWITCH"],
                }
            )
            return f"IF({true_condition}, {true_expression}, {false_expression})"

        if not expression.children:
            raise FormulaCompileError(
                "EMPTY_AGGREGATE_FUNCTION",
                f"{function_name} at {state.locator} has no operands.",
            )
        compiled_arguments: list[str] = []
        for argument in expression.children:
            if argument.kind != "reference":
                compiled_arguments.append(self._compile_expression(argument, state))
                continue
            locator = self._resolve_reference(argument.value, state.own_sheet, state.cell)
            if ":" not in locator.rsplit("!", 1)[1]:
                compiled_arguments.append(self._compile_reference(argument, state))
                continue
            members = self._range_members(locator)
            for member in members:
                compiled_arguments.append(state.bind(member))
        if function_name == "SUM":
            return "(" + " + ".join(compiled_arguments or ["0"]) + ")"
        if not compiled_arguments:
            raise FormulaCompileError(
                "EMPTY_NUMERIC_RANGE",
                f"{function_name} at {state.locator} has no numeric range members.",
            )
        return f"{function_name}({', '.join(compiled_arguments)})"

    def _coverage_limit(
        self,
        locator: str,
        reason_code: str,
        effect: str,
        *,
        output_id: str | None = None,
        formula: str | None = None,
        upstream_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        scope_ids = sorted({item for item in [output_id, *upstream_ids] if item})
        return {
            "limit_id": _stable_id(
                "CL-EXCEL",
                [self.source_digest, locator, reason_code, effect, scope_ids],
                label=locator,
            ),
            "reason_code": reason_code,
            "scope_ids": scope_ids,
            "effect": effect,
            "locator": locator,
            "formula": formula,
            "source_ref": f"{self.source.get('workbook', 'workbook.xlsx')}:{locator}",
            "resolution": "HUMAN_STOP",
        }

    def _compile_formula(self, locator: str, cell: Mapping[str, Any]) -> dict[str, Any]:
        output_id = self.binding_for(locator)
        raw_formula = cell.get("value")
        if not isinstance(raw_formula, str) or not raw_formula.startswith("="):
            raise FormulaCompileError(
                "MISSING_EXCEL_FORMULA_TEXT",
                f"Formula cell {locator} has no preserved Excel expression.",
            )
        formula_id = _stable_id(
            "F-EXCEL",
            [self.source_digest, locator, raw_formula],
            label=locator,
        )
        own_sheet = locator.rsplit("!", 1)[0]
        source_ref = f"{self.source.get('workbook', 'workbook.xlsx')}:{locator}"
        state = _FormulaState(
            locator=locator,
            output_id=output_id,
            formula_id=formula_id,
            source_ref=source_ref,
            original_formula=raw_formula,
            own_sheet=own_sheet,
            cell=cell,
            compiler=self,
        )
        tree = _Parser(raw_formula).parse()
        expression = self._compile_expression(tree, state)
        item = {
            "formula_id": formula_id,
            "input_ids": state.input_ids,
            "output_id": output_id,
            "expression_or_function_ref": expression,
            "operand_bindings": dict(sorted(state.operand_bindings.items())),
            "evaluation_type": "SAFE_DECIMAL_EXPRESSION",
            "source_ref": source_ref,
            "workbook_cell_ref": locator,
            "original_excel_formula": raw_formula,
            "expected_evaluated_value": cell.get("evaluated_value"),
            "expected_cached_value": cell.get("cached_value"),
            "reason_codes": ["EXCEL_FORMULA_COMPILED", "R6_OPERANDS_BOUND"],
            "compiler_version": COMPILER_VERSION,
            "_referenced_locators": state.referenced_locators,
            "_rule_switches": state.rule_switches,
            "_function_names": sorted(state.function_names),
        }
        return item

    def compile(self) -> dict[str, Any]:
        formula_cells = {
            locator: cell
            for locator, cell in self.cells.items()
            if str(cell.get("kind", "")).lower() == "formula"
        }
        compiled: dict[str, dict[str, Any]] = {}
        limits: list[dict[str, Any]] = []
        failed_outputs: dict[str, str] = {}

        for locator in sorted(formula_cells):
            cell = formula_cells[locator]
            try:
                compiled[locator] = self._compile_formula(locator, cell)
            except FormulaCompileError as exc:
                output_id = None
                candidates = self.binding_candidates.get(locator, ())
                if len(candidates) == 1:
                    output_id = candidates[0]
                    failed_outputs[output_id] = locator
                limits.append(
                    self._coverage_limit(
                        locator,
                        exc.reason_code,
                        exc.detail,
                        output_id=output_id,
                        formula=str(cell.get("value") or ""),
                    )
                )

        # Reading a cached value from a formula that failed compilation would
        # silently turn a live dependency into a constant.  Stop every compiled
        # descendant instead, iterating until the graph is closed.
        changed = True
        while changed:
            changed = False
            for locator in sorted(list(compiled)):
                item = compiled[locator]
                blocked = sorted(set(item["input_ids"]) & set(failed_outputs))
                if not blocked:
                    continue
                failed_outputs[item["output_id"]] = locator
                limits.append(
                    self._coverage_limit(
                        locator,
                        "UPSTREAM_FORMULA_NOT_COMPILED",
                        "Formula depends on an output that is under Human Stop; cached values are not substituted.",
                        output_id=item["output_id"],
                        formula=item["original_excel_formula"],
                        upstream_ids=blocked,
                    )
                )
                del compiled[locator]
                changed = True

        formulas = [compiled[key] for key in sorted(compiled)]
        cycles = self._cyclic_components(formulas)
        cyclic_ids = {member for component in cycles for member in component}
        solver_configs = self._solver_configs(cycles, formulas)
        component_by_member = {
            member: config["component_id"]
            for config in solver_configs
            for member in config["member_ids"]
        }
        rule_switches: list[dict[str, Any]] = []
        function_counts: dict[str, int] = defaultdict(int)
        for formula in formulas:
            for name in formula.pop("_function_names"):
                function_counts[name] += 1
            rule_switches.extend(formula.pop("_rule_switches"))
            formula["referenced_locators"] = formula.pop("_referenced_locators")
            if formula["output_id"] in component_by_member:
                formula["cyclic_component_id"] = component_by_member[formula["output_id"]]

        directed_edges = []
        for formula in formulas:
            for input_id in formula["input_ids"]:
                directed_edges.append(annotate_edge(
                    {
                        "edge_id": _stable_id(
                            "E-EXCEL",
                            [input_id, formula["output_id"], formula["formula_id"]],
                        ),
                        "from_model_node_id": input_id,
                        "to_model_node_id": formula["output_id"],
                        "relation_type": "DRIVES",
                        "formula_or_function_ref": formula["formula_id"],
                        "control_ids": [],
                        "scenario": None,
                    },
                    "FORMULA_PRECEDENT_DRIVES",
                    evidence={"formula_or_function_ref": formula["formula_id"]},
                ))

        unique_limits = {item["limit_id"]: item for item in limits}
        limits = [unique_limits[key] for key in sorted(unique_limits)]
        status = "COMPILED"
        if limits:
            status = "COMPILED_WITH_COVERAGE_LIMITS" if formulas else "HUMAN_STOP"
        return {
            "schema_version": SCHEMA_VERSION,
            "compiler_version": COMPILER_VERSION,
            "status": status,
            "source_digest": self.source_digest,
            "binding_resolution_digest": self.binding_digest,
            "input_digest": self.input_digest,
            "formulas": formulas,
            "directed_model_edges": directed_edges,
            "rule_switches": sorted(rule_switches, key=lambda item: item["rule_switch_id"]),
            "cyclic_component_solver_configs": solver_configs,
            "coverage_limits": limits,
            "stats": {
                "source_formula_count": len(formula_cells),
                "compiled_formula_count": len(formulas),
                "acyclic_formula_count": len(formulas) - len(cyclic_ids),
                "cyclic_formula_count": len(cyclic_ids),
                "cyclic_component_count": len(cycles),
                "rule_switch_count": len(rule_switches),
                "coverage_limit_count": len(limits),
                "function_counts": dict(sorted(function_counts.items())),
            },
        }

    @staticmethod
    def _cyclic_components(formulas: Sequence[Mapping[str, Any]]) -> list[list[str]]:
        formula_outputs = {str(item["output_id"]) for item in formulas}
        adjacency = {
            str(item["output_id"]): sorted(
                {str(input_id) for input_id in item.get("input_ids", [])} & formula_outputs
            )
            for item in formulas
        }
        index = 0
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        components: list[list[str]] = []

        def visit(node: str) -> None:
            nonlocal index
            indices[node] = lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for target in adjacency.get(node, []):
                if target not in indices:
                    visit(target)
                    lowlinks[node] = min(lowlinks[node], lowlinks[target])
                elif target in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[target])
            if lowlinks[node] == indices[node]:
                component: list[str] = []
                while True:
                    target = stack.pop()
                    on_stack.remove(target)
                    component.append(target)
                    if target == node:
                        break
                if len(component) > 1 or node in adjacency.get(node, []):
                    components.append(sorted(component))

        for node in sorted(adjacency):
            if node not in indices:
                visit(node)
        return sorted(components, key=lambda item: tuple(item))

    def _solver_configs(
        self,
        components: Sequence[Sequence[str]],
        formulas: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        formula_by_output = {str(item["output_id"]): item for item in formulas}
        configs: list[dict[str, Any]] = []
        for members_raw in components:
            members = sorted(str(item) for item in members_raw)
            member_set = set(members)
            component_id = _stable_id("SCC-EXCEL", members)
            equations = []
            activation_ids: set[str] = set()
            for member in members:
                formula = formula_by_output[member]
                equations.append(
                    {
                        "output_id": member,
                        "expression_or_function_ref": formula["expression_or_function_ref"],
                        "operand_bindings": formula["operand_bindings"],
                        "formula_id": formula["formula_id"],
                    }
                )
                activation_ids.update(set(formula["input_ids"]) - member_set)
            dependent_ids = sorted(
                output_id
                for output_id, formula in formula_by_output.items()
                if output_id not in member_set
                and set(str(item) for item in formula.get("input_ids", [])) & member_set
            )
            configs.append(
                {
                    "component_id": component_id,
                    "component_type": "NUMERICAL_SCC",
                    "member_ids": members,
                    "method": "DAMPED_FIXED_POINT",
                    "initialization": {member: "0" for member in members},
                    "admissible_bounds": {},
                    "absolute_residual_tolerance": self.absolute_residual_tolerance,
                    "relative_residual_tolerance": self.relative_residual_tolerance,
                    "maximum_iterations": self.maximum_iterations,
                    "damping": self.damping,
                    "uniqueness_condition": "CONVERGED_FROM_DECLARED_INITIALIZATION_WITHIN_TOLERANCE",
                    "invariant_control_ids": [],
                    "activation_input_ids": sorted(activation_ids),
                    "dependent_ids": dependent_ids,
                    "equations": equations,
                    "source_ref": "tools/formula_compiler.py",
                    "reason_codes": ["EXCEL_FORMULA_SCC_COMPILED"],
                }
            )
        return configs


def _decimal_literal(value: Any) -> str:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FormulaCompileError(
            "INVALID_NUMERIC_LITERAL", f"Invalid Excel numeric literal: {value!r}."
        ) from exc
    if not decimal.is_finite():
        raise FormulaCompileError(
            "INVALID_NUMERIC_LITERAL", f"Non-finite Excel numeric literal: {value!r}."
        )
    text = format(decimal, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _safe_decimal_expression(expression: str, variables: Mapping[str, Decimal]) -> Decimal:
    """Mirror the production runtime's bounded decimal expression grammar."""

    tree = ast.parse(expression, mode="eval")

    def evaluate(node: ast.AST) -> Decimal | bool:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"unbound formula variable: {node.id}")
            return variables[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(left, bool) or isinstance(right, bool):
                raise ValueError("boolean arithmetic is unsupported")
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left**right
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            left, right = evaluate(node.left), evaluate(node.comparators[0])
            operator = node.ops[0]
            if isinstance(operator, ast.Eq):
                return left == right
            if isinstance(operator, ast.NotEq):
                return left != right
            if isinstance(operator, ast.Lt):
                return left < right
            if isinstance(operator, ast.LtE):
                return left <= right
            if isinstance(operator, ast.Gt):
                return left > right
            if isinstance(operator, ast.GtE):
                return left >= right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id.upper()
            if name == "IF" and len(node.args) == 3:
                condition = evaluate(node.args[0])
                return evaluate(node.args[1]) if bool(condition) else evaluate(node.args[2])
            arguments = [evaluate(argument) for argument in node.args]
            if any(isinstance(argument, bool) for argument in arguments):
                raise ValueError("boolean aggregate argument is unsupported")
            if name == "MIN" and arguments:
                return min(arguments)
            if name == "MAX" and arguments:
                return max(arguments)
            if name == "SUM":
                return sum(arguments, Decimal("0"))
        raise ValueError(f"unsupported formula syntax: {ast.dump(node)}")

    result = evaluate(tree)
    return Decimal("1") if result is True else Decimal("0") if result is False else result


def _numeric_cell_value(cell: Mapping[str, Any], *, formula: bool = False) -> Decimal | None:
    fields = ("evaluated_value", "cached_value") if formula else ("value", "evaluated_value", "cached_value")
    for field_name in fields:
        raw = cell.get(field_name)
        if isinstance(raw, bool) or raw is None:
            continue
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            continue
        if value.is_finite():
            return value
    return None


def recalculate_compilation(
    compilation: Mapping[str, Any],
    source_graph: Mapping[str, Any] | str | Path,
    binding_resolution: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
    *,
    absolute_tolerance: str = "0.000001",
    relative_tolerance: str = "0.000001",
) -> dict[str, Any]:
    """Execute compiled formulas and compare every available L1 expected value."""

    source = _source_payload(_load_json(source_graph))
    bindings_payload = _load_json(binding_resolution)
    locator_to_nodes: dict[str, set[str]] = defaultdict(set)
    for item in _binding_items(bindings_payload):
        locator = item.get("locator") or item.get("cell") or item.get("workbook_cell_ref")
        model_node_id = item.get("model_node_id") or item.get("mn_id") or item.get("id")
        if locator and model_node_id:
            try:
                locator_to_nodes[normalize_locator(str(locator))].add(str(model_node_id))
            except FormulaCompileError:
                pass
    cells = {
        normalize_locator(str(locator)): cell
        for locator, cell in source.get("cells", {}).items()
        if isinstance(cell, Mapping)
    }
    values: dict[str, Decimal] = {}
    locator_by_node: dict[str, str] = {}
    for locator, candidates in locator_to_nodes.items():
        if len(candidates) != 1 or locator not in cells:
            continue
        node_id = next(iter(candidates))
        locator_by_node[node_id] = locator
        cell = cells[locator]
        if str(cell.get("kind", "")).lower() != "formula":
            value = _numeric_cell_value(cell)
            if value is not None:
                values[node_id] = value

    formulas = [item for item in compilation.get("formulas", []) if isinstance(item, Mapping)]
    formula_by_output = {str(item["output_id"]): item for item in formulas}
    configs = [
        item
        for item in compilation.get("cyclic_component_solver_configs", [])
        if isinstance(item, Mapping)
    ]
    cyclic_ids = {
        str(member) for config in configs for member in config.get("member_ids", [])
    }
    limits: list[dict[str, Any]] = [
        dict(item)
        for item in compilation.get("coverage_limits", [])
        if isinstance(item, Mapping)
    ]

    def execute(formula: Mapping[str, Any], overrides: Mapping[str, Decimal] | None = None) -> Decimal:
        variables: dict[str, Decimal] = {}
        for name, model_node_id in formula.get("operand_bindings", {}).items():
            object_id = str(model_node_id)
            if overrides is not None and object_id in overrides:
                variables[str(name)] = overrides[object_id]
            elif object_id in values:
                variables[str(name)] = values[object_id]
            else:
                raise ValueError(f"missing compiled input {object_id}")
        return _safe_decimal_expression(str(formula["expression_or_function_ref"]), variables)

    # Schedule scalar formulas and SCCs together.  This handles all three
    # directions honestly: formula -> SCC, SCC -> formula, and SCC -> formula ->
    # another SCC.  A component is ready only when all external formula outputs
    # are settled; source inputs that are missing are allowed through so the
    # executor emits their explicit coverage limit instead of deadlocking.
    from tools.extract_v3 import solve_component

    pending_formulas = {
        output: formula
        for output, formula in formula_by_output.items()
        if output not in cyclic_ids
    }
    pending_configs = {
        str(config.get("component_id")): config for config in configs
    }
    while pending_formulas or pending_configs:
        progressed = False
        pending_output_ids = set(pending_formulas) | {
            str(member)
            for config in pending_configs.values()
            for member in config.get("member_ids", [])
        }

        for output_id in sorted(list(pending_formulas)):
            formula = pending_formulas[output_id]
            dependencies = {str(item) for item in formula.get("input_ids", [])}
            if (dependencies - set(values)) & pending_output_ids:
                continue
            try:
                values[output_id] = execute(formula)
            except (ArithmeticError, InvalidOperation, ValueError) as exc:
                limits.append(
                    {
                        "limit_id": _stable_id("CL-RECALC", [output_id, str(exc)]),
                        "reason_code": "FORMULA_RECALCULATION_FAILED",
                        "scope_ids": sorted(dependencies | {output_id}),
                        "effect": str(exc),
                        "resolution": "HUMAN_STOP",
                    }
                )
            del pending_formulas[output_id]
            progressed = True

        for component_id in sorted(list(pending_configs)):
            config = pending_configs[component_id]
            members = [str(item) for item in config.get("member_ids", [])]
            activation_ids = {
                str(item) for item in config.get("activation_input_ids", [])
            }
            if (activation_ids - set(values)) & pending_output_ids:
                continue
            equation_by_output = {
                str(item.get("output_id")): item
                for item in config.get("equations", [])
                if isinstance(item, Mapping) and item.get("output_id")
            }
            # Initial values come only from the declared solver configuration.
            # L1 evaluated/cached values are comparison evidence, never seeds.
            seed = {
                member: float(
                    Decimal(str(config.get("initialization", {}).get(member, "0")))
                )
                for member in members
            }

            def evaluator(member: str, current: dict[str, float]) -> float:
                equation = equation_by_output[member]
                overrides = {key: Decimal(str(value)) for key, value in current.items()}
                return float(execute(equation, overrides))

            report = solve_component(
                members,
                evaluator,
                seed,
                float(Decimal(str(config.get("absolute_residual_tolerance", "1e-9")))),
                int(config.get("maximum_iterations", 500)),
                float(Decimal(str(config.get("damping", "0.5")))),
            )
            if report.converged:
                values.update(
                    {key: Decimal(str(value)) for key, value in report.values.items()}
                )
            else:
                limits.append(
                    {
                        "limit_id": _stable_id(
                            "CL-RECALC-SCC", [report.component_id, report.reason]
                        ),
                        "reason_code": "CYCLIC_COMPONENT_NON_CONVERGENT",
                        "scope_ids": sorted(members),
                        "effect": report.reason or "Fixed-point iteration did not converge.",
                        "iterations": report.iterations,
                        "residual": report.residual,
                        "resolution": "HUMAN_STOP",
                    }
                )
            del pending_configs[component_id]
            progressed = True

        if progressed:
            continue
        unresolved_outputs = sorted(
            set(pending_formulas)
            | {
                str(member)
                for config in pending_configs.values()
                for member in config.get("member_ids", [])
            }
        )
        limits.append(
            {
                "limit_id": _stable_id("CL-RECALC", [unresolved_outputs, "ORDER"]),
                "reason_code": "UNRESOLVED_FORMULA_ORDER",
                "scope_ids": unresolved_outputs,
                "effect": "Formula/component scheduler could not resolve every dependency.",
                "resolution": "HUMAN_STOP",
            }
        )
        break

    absolute = Decimal(str(absolute_tolerance))
    relative = Decimal(str(relative_tolerance))
    comparisons: list[dict[str, Any]] = []
    for output_id, formula in sorted(formula_by_output.items()):
        locator = str(formula.get("workbook_cell_ref") or locator_by_node.get(output_id, ""))
        cell = cells.get(locator, {})
        expected = _numeric_cell_value(cell, formula=True)
        actual = values.get(output_id)
        if expected is None:
            comparisons.append(
                {
                    "formula_id": formula.get("formula_id"),
                    "output_id": output_id,
                    "locator": locator,
                    "status": "NO_EXPECTED_VALUE",
                    "expected": None,
                    "actual": _plain_decimal(actual) if actual is not None else None,
                }
            )
            continue
        if actual is None:
            status = "NOT_RECALCULATED"
            error = None
        else:
            error = abs(actual - expected)
            threshold = max(absolute, relative * max(abs(expected), Decimal("1")))
            status = "MATCH" if error <= threshold else "MISMATCH"
        comparison = {
            "formula_id": formula.get("formula_id"),
            "output_id": output_id,
            "locator": locator,
            "status": status,
            "expected": _plain_decimal(expected),
            "actual": _plain_decimal(actual) if actual is not None else None,
            "absolute_error": _plain_decimal(error) if error is not None else None,
        }
        comparisons.append(comparison)
        if status == "MISMATCH":
            limits.append(
                {
                    "limit_id": _stable_id("CL-RECALC-MISMATCH", [output_id, expected, actual]),
                    "reason_code": "RECALCULATION_MISMATCH",
                    "scope_ids": [output_id],
                    "effect": (
                        f"Compiled value {_plain_decimal(actual)} does not match L1 "
                        f"evaluated value {_plain_decimal(expected)} at {locator}."
                    ),
                    "resolution": "HUMAN_STOP",
                }
            )

    unique_limits = {str(item["limit_id"]): item for item in limits}
    limits = [unique_limits[key] for key in sorted(unique_limits)]
    matched = sum(item["status"] == "MATCH" for item in comparisons)
    mismatched = sum(item["status"] == "MISMATCH" for item in comparisons)
    expected_count = sum(item["status"] != "NO_EXPECTED_VALUE" for item in comparisons)
    if expected_count == 0 and not limits:
        status = "NO_EXPECTED_VALUES"
    elif expected_count == matched and not limits:
        status = "MATCH"
    else:
        status = "HUMAN_STOP"
    return {
        "schema_version": "excel-formula-recalculation/1.0",
        "status": status,
        "values": {key: _plain_decimal(value) for key, value in sorted(values.items())},
        "comparisons": comparisons,
        "coverage_limits": limits,
        "stats": {
            "compiled_formula_count": len(formulas),
            "recalculated_formula_count": sum(output in values for output in formula_by_output),
            "expected_value_count": expected_count,
            "matched_value_count": matched,
            "mismatched_value_count": mismatched,
        },
    }


def _plain_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text + ".0" if "." not in text else text


def compile_formulas(
    source_graph: Mapping[str, Any] | str | Path,
    binding_resolution: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
    **solver_options: Any,
) -> dict[str, Any]:
    """Public functional API for PAN-67 and command-line callers."""

    return FormulaCompiler(source_graph, binding_resolution, **solver_options).compile()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile L1 Excel formulas through PAN-65 bindings into PANTA runtime expressions"
    )
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args(argv)

    compilation = compile_formulas(arguments.source_graph, arguments.bindings)
    if arguments.verify:
        compilation["recalculation"] = recalculate_compilation(
            compilation, arguments.source_graph, arguments.bindings
        )
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        json.dumps(compilation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    stats = compilation["stats"]
    print(
        f"[formula_compiler] {stats['compiled_formula_count']}/"
        f"{stats['source_formula_count']} formulas compiled; "
        f"{stats['cyclic_component_count']} cycles; "
        f"{stats['coverage_limit_count']} coverage limits"
    )
    return 0 if compilation["status"] != "HUMAN_STOP" else 2


if __name__ == "__main__":
    raise SystemExit(main())
