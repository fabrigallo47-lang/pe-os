#!/usr/bin/env python3
"""Build honest evaluator inputs from admitted claims.

The evaluator deliberately accepts overrides separately from the mapping.  This
module is that boundary: it lets admitted evidence illuminate external inputs,
while keeping computed nodes and unresolved evidence out of the value graph.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

try:
    from tools.position_model_binder import _propose_for_position
except ModuleNotFoundError:  # Direct script execution puts tools/ on sys.path.
    from position_model_binder import _propose_for_position


# Conversions live in one deliberately small declaration.  Adding a pair is a
# policy change; unknown or absent units never become compatible by inference.
_UNIT_CONVERSIONS: dict[tuple[str, str], float] = {
    ("$m", "MM_USD"): 1.0,
}


def _claims_list(claims: Any) -> list[Mapping[str, Any]]:
    """Accept either an admitted-claims envelope or its claims array."""
    if isinstance(claims, Mapping):
        claims = claims.get("claims", [])
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        raise ValueError("claims must be an object containing claims or a claims array")
    return [claim for claim in claims if isinstance(claim, Mapping)]


def _binding_list(bindings: Any) -> list[Mapping[str, Any]]:
    """Flatten the binding containers used by the compiler and bridge."""
    if bindings is None:
        return []
    if isinstance(bindings, Mapping):
        if "model_node_id" in bindings or (
                "claim_id" in bindings and "position_id" in bindings):
            return [bindings]
        records: list[Mapping[str, Any]] = []
        for key in ("bindings", "claim_position_edges", "position_model_bindings",
                    "position_model_directions"):
            value = bindings.get(key, [])
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                records.extend(item for item in value if isinstance(item, Mapping))
        return records
    if not isinstance(bindings, Sequence) or isinstance(bindings, (str, bytes)):
        raise ValueError("bindings must be a binding object or array")
    return [binding for binding in bindings if isinstance(binding, Mapping)]


def _claim_label(claim: Mapping[str, Any], index: int) -> str:
    """Keep diagnostics useful even for a malformed claim without an id."""
    for key in ("claim_id", "stable_id", "position_id", "id", "ordinal_id"):
        value = claim.get(key)
        if isinstance(value, str) and value:
            return value
    return f"claims[{index}]"


def _claim_identifiers(claim: Mapping[str, Any], label: str) -> set[str]:
    identifiers = {label}
    for key in ("claim_id", "stable_id", "position_id", "id", "ordinal_id"):
        value = claim.get(key)
        if isinstance(value, str) and value:
            identifiers.add(value)
    return identifiers


def _target_ids(value: Any) -> set[str]:
    if isinstance(value, str) and value:
        return {value}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {item for item in value if isinstance(item, str) and item}
    return set()


def _numeric(value: Any) -> float | None:
    """Return a finite scalar without interpreting ranges or formatted text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _converted_value(value: float, claim_unit: Any, node_unit: Any) -> float | None:
    """Convert only through the declared table; missing units are not guesses."""
    source = claim_unit.strip() if isinstance(claim_unit, str) else claim_unit
    target = node_unit.strip() if isinstance(node_unit, str) else node_unit
    if source == target:
        return value
    factor = _UNIT_CONVERSIONS.get((source, target))
    return value * factor if factor is not None else None


def _binding_indexes(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """Index direct bindings plus the claim -> position -> node bridge."""
    direct: dict[str, set[str]] = defaultdict(set)
    claim_positions: dict[str, set[str]] = defaultdict(set)
    position_nodes: dict[str, set[str]] = defaultdict(set)
    for record in records:
        node_id = record.get("model_node_id")
        claim_id = record.get("claim_id") or record.get("claim_stable_id")
        position_id = record.get("position_id")
        if isinstance(node_id, str) and node_id:
            if isinstance(claim_id, str) and claim_id:
                direct[claim_id].add(node_id)
            if isinstance(position_id, str) and position_id:
                position_nodes[position_id].add(node_id)
        elif (isinstance(claim_id, str) and claim_id
              and isinstance(position_id, str) and position_id):
            claim_positions[claim_id].add(position_id)
    return direct, claim_positions, position_nodes


def build_overrides(
    claims: Any,
    mapping: Mapping[str, Any],
    bindings: Any = None,
) -> tuple[dict[str, float], list[dict]]:
    """Return claim-backed DIRECT_INPUT overrides and every node left unfed.

    Claims passed here are already admitted; this function performs no
    authority decision.  Multiple agreeing claims may supply one input, but a
    malformed value, incompatible unit, or disagreement keeps that input dark
    because resolving any of those conditions would be adjudication.
    """
    direct_nodes: dict[str, Mapping[str, Any]] = {}
    for node in mapping.get("model_nodes", []):
        if (isinstance(node, Mapping)
                and node.get("computational_form") == "DIRECT_INPUT"):
            node_id = node.get("model_node_id")
            if isinstance(node_id, str) and node_id:
                direct_nodes[node_id] = node

    records = _binding_list(bindings)
    if bindings is None:
        records.extend(_binding_list({
            "position_model_directions": mapping.get("position_model_directions", []),
        }))
    direct, claim_positions, position_nodes = _binding_indexes(records)

    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, claim in enumerate(_claims_list(claims)):
        label = _claim_label(claim, index)
        identifiers = _claim_identifiers(claim, label)
        node_ids = _target_ids(claim.get("model_node_id"))
        node_ids.update(_target_ids(claim.get("model_node_ids")))
        for identifier in identifiers:
            node_ids.update(direct.get(identifier, set()))
            node_ids.update(position_nodes.get(identifier, set()))
            for position_id in claim_positions.get(identifier, set()):
                node_ids.update(position_nodes.get(position_id, set()))

        if (bindings is None and not node_ids
                and isinstance(claim.get("statement"), str)):
            for proposal in _propose_for_position(
                    claim["statement"], set(direct_nodes)):
                if proposal.get("binding_type") == "DIRECT":
                    node_ids.add(proposal["model_node_id"])

        for node_id in node_ids:
            if node_id not in direct_nodes:
                continue
            candidates[node_id].append({
                "claim_id": label,
                "value": claim.get("value"),
                "unit": claim.get("unit"),
            })

    overrides: dict[str, float] = {}
    unfed: list[dict] = []
    for node_id in sorted(direct_nodes):
        node = direct_nodes[node_id]
        bound = candidates.get(node_id, [])
        if not bound:
            # A DIRECT_INPUT that already carries a seeded initial_value is not
            # dark -- the evaluator computes with it today. Reporting it in the
            # same breath as a genuinely empty node would overstate the gap:
            # on the real K-PRE bundle that is 16 nodes out of 43, and the
            # measurement G2 rests on is the 28 that have no value at all.
            initial = node.get("initial_value")
            seeded = (isinstance(initial, (int, float))
                      and not isinstance(initial, bool))
            unfed.append({
                "node_id": node_id,
                "reason": "no claim bound to this node",
                "dark": not seeded,
                "seeded_initial_value": initial if seeded else None,
            })
            continue

        non_numeric = [item for item in bound if _numeric(item["value"]) is None]
        if non_numeric:
            unfed.append({
                "node_id": node_id,
                "reason": "claim value non-numeric",
                "claims": non_numeric,
            })
            continue

        converted: list[dict[str, Any]] = []
        mismatched: list[dict[str, Any]] = []
        for item in bound:
            number = _numeric(item["value"])
            assert number is not None
            value = _converted_value(number, item["unit"], node.get("unit"))
            if value is None:
                mismatched.append(item)
            else:
                converted.append({"claim_id": item["claim_id"], "value": value})
        if mismatched:
            unfed.append({
                "node_id": node_id,
                "reason": "unit mismatch",
                "node_unit": node.get("unit"),
                "claims": mismatched,
            })
            continue

        values = {item["value"] for item in converted}
        if len(values) != 1:
            unfed.append({
                "node_id": node_id,
                "reason": "more than one admitted claim disagrees",
                "claim_ids": [item["claim_id"] for item in converted],
                "competing_claims": converted,
            })
            continue
        overrides[node_id] = converted[0]["value"]

    return overrides, unfed
