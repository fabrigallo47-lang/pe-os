#!/usr/bin/env python3
"""Turn admitted claims into explicit inputs for ``model_evaluator``.

An execution mapping deliberately distinguishes a missing direct input from a
numeric one.  This module preserves that distinction: it returns only values
that an admitted claim directly supports, and makes every other gap visible.
"""
from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from tools.position_model_binder import _propose_for_position
except ModuleNotFoundError:  # Direct script execution makes tools/ sys.path[0].
    from position_model_binder import _propose_for_position


def _numeric_value(value: Any) -> float | None:
    """Return a finite float only when the claim already states one exactly."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _claims_and_fields(admitted_claims: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """Accept the E3 envelope or its claims list without losing claim identity."""
    if isinstance(admitted_claims, Mapping):
        claims = admitted_claims.get("claims", [])
        metadata = admitted_claims.get("extraction_metadata", {})
        fields = metadata.get("compiler_fields_per_claim", []) if isinstance(metadata, Mapping) else []
    else:
        claims = admitted_claims
        fields = []
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        raise ValueError("admitted claims must be an E3 object or claims array")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes)):
        raise ValueError("compiler_fields_per_claim must be an array")
    return (
        [claim for claim in claims if isinstance(claim, Mapping)],
        {str(field.get("claim_id")): field for field in fields if isinstance(field, Mapping)},
    )


def _metric_matches_node(fields: Mapping[str, Any], node_id: str) -> bool:
    """Reject the binder's broad textual hit when metadata states another metric."""
    metric = fields.get("metric")
    if not isinstance(metric, str) or not metric.strip():
        return True
    metric_words = {word for word in metric.upper().replace("-", " ").split() if word}
    node_words = set(node_id.upper().replace("MN-", "").split("-"))
    # The signal matcher is intentionally recall-oriented, so "seller EBITDA
    # margin" can textually hit seller EBITDA.  Compiler metadata is the
    # structured disambiguator; without this check a percentage could replace
    # a currency input solely because two statements share a noun.
    if "MARGIN" in metric_words:
        return "MARGIN" in node_words
    if "EBITDA" in metric_words:
        return "EBITDA" in node_words and "MARGIN" not in node_words
    if "CONCENTRATION" in metric_words:
        return "CONCENTRATION" in node_words
    if "CAPEX" in metric_words:
        return "CAPEX" in node_words
    if "GROWTH" in metric_words:
        return "GROWTH" in node_words
    return True


def build_model_inputs(
    mapping: Mapping[str, Any],
    admitted_claims: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build evaluator overrides and account for every unbound claim/input gap.

    The position binder is intentionally the sole matcher.  Re-implementing
    its signal table here would let a claim reach a model node under a policy
    the rest of the pipeline cannot reproduce.  Only its DIRECT proposals are
    usable values; a scenario/output proposal says a claim is relevant, not
    that it supplies that model input.
    """
    claims, compiler_fields = _claims_and_fields(admitted_claims)
    empty_nodes: set[str] = set()
    for node in mapping.get("model_nodes", []):
        if not isinstance(node, Mapping) or node.get("computational_form") != "DIRECT_INPUT":
            continue
        node_id = node.get("model_node_id")
        if isinstance(node_id, str) and _numeric_value(node.get("initial_value")) is None:
            empty_nodes.add(node_id)

    candidates: dict[str, list[tuple[str, float]]] = {}
    unbound: list[dict[str, Any]] = []
    for index, claim in enumerate(claims):
        claim_id = claim.get("claim_id")
        label = claim_id if isinstance(claim_id, str) and claim_id else f"claims[{index}]"
        statement = claim.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            unbound.append({"claim_id": label, "reason": "claim has no statement for binding"})
            continue
        proposals = _propose_for_position(statement, empty_nodes)
        fields = compiler_fields.get(str(claim_id), {})
        node_ids = [
            p["model_node_id"] for p in proposals
            if p["binding_type"] == "DIRECT" and _metric_matches_node(fields, p["model_node_id"])
        ]
        if not node_ids:
            # Compiler fields remain provenance in this output.  They do not
            # broaden matching: a generic metric alone cannot safely select a
            # particular basis, scenario, or perimeter-specific model node.
            detail = {key: fields[key] for key in ("metric", "entity", "scope", "basis", "measurement", "scenario") if key in fields}
            entry: dict[str, Any] = {"claim_id": label, "reason": "no DIRECT_INPUT binding proposed"}
            if detail:
                entry["compiler_fields"] = detail
            unbound.append(entry)
            continue
        number = _numeric_value(claim.get("value"))
        if number is None:
            unbound.append({
                "claim_id": label,
                "node_ids": sorted(node_ids),
                "reason": "claim value is not a finite numeric scalar",
                "value": claim.get("value"),
            })
            continue
        for node_id in node_ids:
            candidates.setdefault(node_id, []).append((label, number))

    overrides: dict[str, float] = {}
    conflict_nodes: dict[str, list[tuple[str, float]]] = {}
    for node_id, proposals in candidates.items():
        values = {value for _, value in proposals}
        if len(values) == 1:
            overrides[node_id] = proposals[0][1]
        else:
            conflict_nodes[node_id] = proposals
            for claim_id, value in proposals:
                unbound.append({
                    "claim_id": claim_id,
                    "node_ids": [node_id],
                    "reason": "conflicting numeric claims for the same node",
                    "value": value,
                })

    unfilled = []
    for node_id in sorted(empty_nodes - set(overrides)):
        if node_id in conflict_nodes:
            proposals = conflict_nodes[node_id]
            unfilled.append({
                "node_id": node_id,
                "reason": "conflicting numeric claims",
                "claim_ids": [claim_id for claim_id, _ in proposals],
            })
        else:
            unfilled.append({"node_id": node_id, "reason": "no numeric DIRECT claim bound"})

    return {
        "overrides": dict(sorted(overrides.items())),
        "unbound_claims": unbound,
        "unfilled_nodes": unfilled,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build model evaluator overrides from E3 claims")
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="write JSON here (otherwise stdout)")
    args = parser.parse_args()
    result = build_model_inputs(
        json.loads(args.mapping.read_text(encoding="utf-8")),
        json.loads(args.claims.read_text(encoding="utf-8")),
    )
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
