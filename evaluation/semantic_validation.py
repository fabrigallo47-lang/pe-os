"""Cross-field integrity checks for semantic gold cases."""

from __future__ import annotations

import ast
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _eval_arithmetic(expression: str) -> float:
    """Evaluate the tiny arithmetic language allowed in gold derivations."""
    operators = {
        ast.Add: lambda left, right: left + right,
        ast.Sub: lambda left, right: left - right,
        ast.Mult: lambda left, right: left * right,
        ast.Div: lambda left, right: left / right,
    }

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](visit(node.left), visit(node.right))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "round"
            and not node.keywords
            and len(node.args) in {1, 2}
        ):
            value = visit(node.args[0])
            digits = int(visit(node.args[1])) if len(node.args) == 2 else 0
            return float(round(value, digits))
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    return visit(ast.parse(expression, mode="eval"))


def validate_semantic_integrity(
    case: Mapping[str, Any], *, asset_root: Path, inspect_files: bool = False,
) -> list[str]:
    if case.get("task") != "semantic_claim_extraction":
        return []

    findings: list[str] = []
    inputs = {str(item["input_id"]): item for item in case.get("inputs", [])}
    claims = [item for item in case.get("gold", {}).get("claims", []) if isinstance(item, Mapping)]
    relations = [item for item in case.get("gold", {}).get("relations", []) if isinstance(item, Mapping)]
    no_claim_spans = [
        item for item in case.get("gold", {}).get("no_claim_spans", [])
        if isinstance(item, Mapping)
    ]

    claim_ids = [str(claim.get("claim_id", "")) for claim in claims]
    duplicate_claim_ids = sorted({claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1})
    if duplicate_claim_ids:
        findings.append("duplicate gold claim_id(s): " + ", ".join(duplicate_claim_ids))
    claim_by_id = {str(claim["claim_id"]): claim for claim in claims}

    relation_keys: list[tuple[str, str, str, str]] = []
    derived_edges: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        key = (
            str(relation.get("source_claim_id", "")),
            str(relation.get("relation", "")),
            str(relation.get("target_type", "")),
            str(relation.get("target_id", "")),
        )
        relation_keys.append(key)
        source_id, relation_name, target_type, target_id = key
        if source_id not in claim_by_id:
            findings.append(f"relation source does not exist: {source_id}")
        if target_type == "claim" and target_id not in claim_by_id:
            findings.append(f"relation target does not exist: {target_id}")
        if relation_name.casefold() == "derived_from" and target_type == "claim":
            derived_edges[source_id].add(target_id)
    duplicate_relations = sorted({key for key in relation_keys if relation_keys.count(key) > 1})
    if duplicate_relations:
        findings.append(f"duplicate gold relation(s): {duplicate_relations}")

    contents: dict[str, tuple[Path, str]] = {}
    if inspect_files:
        for input_id, item in inputs.items():
            path_value = item.get("path")
            if not path_value:
                continue
            path = Path(str(path_value))
            path = path if path.is_absolute() else asset_root / path
            if path.is_file() and str(item.get("format", "")).casefold() in {
                "md", "txt", "csv", "tsv", "json", "html",
            }:
                contents[input_id] = (path, path.read_text(encoding="utf-8-sig"))

    def validate_quote_and_locator(
        *, input_id: str, quote: str, locator: Mapping[str, Any], label: str,
    ) -> None:
        if input_id not in inputs:
            findings.append(f"{label} references unknown input_id: {input_id}")
            return
        if not inspect_files or input_id not in contents:
            return
        path, content = contents[input_id]
        if _normalized_text(quote) not in _normalized_text(content):
            findings.append(f"{label} quote is not present in {path.name}")
        if locator.get("type") == "generic":
            locator_value = str(locator.get("value", ""))
            if not locator_value.startswith(path.name):
                findings.append(f"{label} locator does not start with {path.name}")
            if "::" in locator_value:
                section = locator_value.split("::", 1)[1]
                if not re.search(rf"^{re.escape(section)}\s*$", content, flags=re.MULTILINE):
                    findings.append(f"{label} locator section is absent from {path.name}: {section}")

    for claim in claims:
        claim_id = str(claim["claim_id"])
        input_id = str(claim.get("input_id", ""))
        quote = str(claim.get("source_quote", ""))
        if not quote:
            findings.append(f"claim {claim_id} has no source_quote")
        validate_quote_and_locator(
            input_id=input_id,
            quote=quote,
            locator=claim.get("locator", {}),
            label=f"claim {claim_id}",
        )

        source_known_at = (inputs.get(input_id, {}).get("metadata") or {}).get("known_at")
        if source_known_at and claim.get("known_at") != source_known_at:
            findings.append(
                f"claim {claim_id} known_at {claim.get('known_at')!r} "
                f"does not match source known_at {source_known_at!r}"
            )

        derivation = claim.get("derivation")
        is_derived = str(claim.get("epistemic_class", "")).casefold() == "derived"
        if is_derived and not derivation:
            findings.append(f"derived claim {claim_id} has no derivation")
            continue
        if derivation:
            operands = {str(item) for item in derivation.get("operand_claim_ids", [])}
            unknown = sorted(operands - set(claim_by_id))
            if unknown:
                findings.append(f"claim {claim_id} has unknown derivation operands: {unknown}")
            if claim_id in operands:
                findings.append(f"claim {claim_id} derives from itself")
            if operands != derived_edges.get(claim_id, set()):
                findings.append(
                    f"claim {claim_id} derivation operands do not match DERIVED_FROM edges"
                )
            expression = derivation.get("expression")
            if expression and isinstance(claim.get("value"), (int, float)):
                try:
                    calculated = _eval_arithmetic(str(expression))
                except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
                    findings.append(f"claim {claim_id} has invalid derivation expression: {exc}")
                else:
                    if not math.isclose(calculated, float(claim["value"]), rel_tol=1e-9, abs_tol=1e-9):
                        findings.append(
                            f"claim {claim_id} derivation evaluates to {calculated}, "
                            f"not {claim['value']}"
                        )

    for index, span in enumerate(no_claim_spans):
        validate_quote_and_locator(
            input_id=str(span.get("input_id", "")),
            quote=str(span.get("quote", "")),
            locator=span.get("locator", {}),
            label=f"no_claim_span[{index}]",
        )

    return findings
