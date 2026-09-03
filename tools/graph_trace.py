#!/usr/bin/env python3
"""Replay a claim corpus one claim at a time and record what the graph did.

Why
---
The identity rules are easy to state and hard to feel. "Two sources saying the
same thing remain two Claims", "same category never establishes sameness",
"unresolved identity becomes a coverage limit" — each is one line in the kernel
and none of them is visible in a finished graph, because a finished graph shows
only the result.

The moment that carries the meaning is the *second* claim of an identity. Alone,
a claim is a node. It is the arrival of another claim about the same quantity
that decides whether the case gained corroboration or a contradiction — and that
moment is invisible unless you watch the graph being built.

This produces the trace; tools/graph_trace.html plays it back.

What each step records
----------------------
Only what actually happened, never a prediction: the claim, its resolved identity
tuple, which of four things occurred, and the running totals after it.

    NEW_IDENTITY   first claim of a quantity — a node, no meaning yet
    CORROBORATES   another source, same identity, same value
    CONTRADICTS    another source, same identity, divergent value
    SAME_SOURCE_DETAIL  another row/detail from the same source; visible, but
                        never promoted to independent corroboration/conflict
    UNRESOLVABLE   identity incomplete; a declared coverage limit, never guessed

Usage
-----
    python3 tools/graph_trace.py pipeline_out/trace/kic_claims.json
    python3 tools/graph_trace.py <e3_claims.json> --out trace.json --limit 300
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.object_identity import (  # noqa: E402
    is_resolvable,
    metric_identity,
    values_conflict,
)


def load_claims(path: Path) -> list[dict[str, Any]]:
    """Join the E3 claim list with its compiler sidecar.

    The identity dimensions live in the sidecar because the frozen CAP-003 claim
    schema has no room for them; reading either half alone yields claims that
    look identity-less.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    claims = payload.get("claims") or []
    sidecar = {
        str(item.get("claim_id")): item
        for item in payload.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
    }
    return [{**claim, **sidecar.get(str(claim.get("claim_id")), {})} for claim in claims]


def _comparable_value(claim: dict[str, Any]) -> str:
    """A value normalized enough to tell agreement from divergence.

    Deliberately crude: this decides what a *reader* is shown, not what the engine
    admits. Real contradiction detection belongs to the transition engine, which
    also weighs materiality — a trace that quietly disagreed with it would be
    worse than no trace.
    """
    value = claim.get("value")
    if value is None:
        return ""
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value).strip().lower()


def _trace_identity(claim: dict[str, Any], *, measurement: bool) -> tuple[str, ...]:
    identity = list(metric_identity(claim))
    if not measurement:
        identity[5] = ""
    return tuple(identity)


def _claims_conflict(a: dict[str, Any], b: dict[str, Any], *, bound: bool) -> tuple[bool, str]:
    if bound:
        return values_conflict(a, b)
    left, right = _comparable_value(a), _comparable_value(b)
    if not left or not right:
        return False, "almeno un claim non è quantitativo"
    if left == right:
        return False, "stesso valore"
    return True, f"valori trattati come esatti: {left} contro {right}"


def _source_identity(claim: dict[str, Any]) -> tuple[str, str]:
    return (
        str(claim.get("source_id") or ""),
        str(claim.get("source_version_id") or ""),
    )


def _contradiction_count(
    claims: list[dict[str, Any]],
    *,
    measurement: bool,
    bound: bool,
    independent_sources: bool = False,
) -> int:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    contradictions = 0
    for claim in claims:
        if not is_resolvable(claim):
            continue
        identity = _trace_identity(claim, measurement=measurement)
        peers = groups[identity]
        if independent_sources:
            peers = [
                peer for peer in peers
                if _source_identity(peer) != _source_identity(claim)
            ]
        if peers and all(_claims_conflict(peer, claim, bound=bound)[0] for peer in peers):
            contradictions += 1
        groups[identity].append(claim)
    return contradictions


def build_trace(claims: list[dict[str, Any]], limit: int | None = None) -> dict[str, Any]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    unresolvable: list[str] = []
    steps: list[dict[str, Any]] = []
    contradictions = 0
    corroborations = 0
    same_source_details = 0
    residual_conflicts: list[dict[str, Any]] = []

    selected = claims[: limit or len(claims)]

    for index, claim in enumerate(selected, start=1):
        claim_id = str(claim.get("claim_id") or f"claim-{index}")
        statement = str(claim.get("statement") or "")[:150]
        value = _comparable_value(claim)

        if not is_resolvable(claim):
            unresolvable.append(claim_id)
            steps.append({
                "n": index, "claim_id": claim_id, "statement": statement,
                "event": "UNRESOLVABLE", "identity": None, "group_key": None,
                "group_size": 0, "value": value, "peers": [],
                "why": "identity incomplete — kept as a declared coverage limit, "
                       "never matched to anything by guesswork",
                "totals": _totals(groups, unresolvable, contradictions, corroborations),
            })
            continue

        identity = _trace_identity(claim, measurement=True)
        key = "|".join(identity)
        all_peers = groups[identity]
        peers = [
            peer for peer in all_peers
            if _source_identity(peer) != _source_identity(claim)
        ]

        if not all_peers:
            event = "NEW_IDENTITY"
            why = "first claim of this quantity — a node, with no meaning yet"
        elif not peers:
            event = "SAME_SOURCE_DETAIL"
            same_source_details += 1
            why = (
                "same source/version contributes another row or detail — kept "
                "visible, but it is not independent corroboration or conflict"
            )
        else:
            relationships = [
                (peer, *_claims_conflict(peer, claim, bound=True))
                for peer in peers
            ]

        if peers and any(not conflict for _, conflict, _ in relationships):
            event = "CORROBORATES"
            corroborations += 1
            compatible_reason = next(
                reason for _, conflict, reason in relationships if not conflict
            )
            why = ("another source states a compatible value for the same identity — "
                   f"{compatible_reason}; two claims are kept, never merged")
        elif peers:
            event = "CONTRADICTS"
            contradictions += 1
            others = ", ".join(sorted({_comparable_value(p) for p in peers if _comparable_value(p)}))
            conflict_reason = "; ".join(
                sorted({reason for _, conflict, reason in relationships if conflict})
            )
            why = (f"same identity, divergent value ({value} vs {others}) — "
                   f"{conflict_reason}")
            residual_conflicts.append({
                "claim_id": claim_id,
                "peer_claim_ids": [str(peer.get("claim_id")) for peer in peers],
                "identity": list(identity),
                "measurement": identity[5],
                "bound": str(claim.get("bound") or "EXACT").upper(),
                "peer_bounds": sorted({
                    str(peer.get("bound") or "EXACT").upper() for peer in peers
                }),
                "reason": conflict_reason,
            })

        relation_peers = all_peers if event == "SAME_SOURCE_DETAIL" else peers
        peer_ids = [str(p.get("claim_id")) for p in relation_peers]
        groups[identity].append(claim)

        steps.append({
            "n": index, "claim_id": claim_id, "statement": statement,
            "event": event, "identity": list(identity), "group_key": key,
            "group_size": len(groups[identity]), "value": value,
            "peers": peer_ids, "why": why,
            "totals": _totals(
                groups, unresolvable, contradictions, corroborations,
                same_source_details,
            ),
        })

    baseline = _contradiction_count(selected, measurement=False, bound=False)
    after_measurement = _contradiction_count(selected, measurement=True, bound=False)
    after_bound = _contradiction_count(selected, measurement=True, bound=True)
    cross_source_residuals = _contradiction_count(
        selected,
        measurement=True,
        bound=True,
        independent_sources=True,
    )

    return {
        "generated_from": "tools/graph_trace.py",
        "claim_count": len(steps),
        "steps": steps,
        "final": _totals(
            groups, unresolvable, contradictions, corroborations,
            same_source_details,
        ),
        "conflict_ablation": {
            "without_measurement_or_bound": baseline,
            "with_measurement_without_bound": after_measurement,
            "with_measurement_and_bound": after_bound,
            "cross_source_residuals": cross_source_residuals,
            "removed_by_measurement": max(0, baseline - after_measurement),
            "removed_by_bound": max(0, after_measurement - after_bound),
            "removed_as_same_source_detail": max(0, after_bound - cross_source_residuals),
        },
        "residual_conflicts": residual_conflicts,
    }


def _totals(
    groups,
    unresolvable,
    contradictions,
    corroborations,
    same_source_details=0,
) -> dict[str, int]:
    multi = [g for g in groups.values() if len(g) > 1]
    return {
        "identities": len(groups),
        "claims_placed": sum(len(g) for g in groups.values()),
        "identities_with_peers": len(multi),
        "comparable_claims": sum(len(g) for g in multi),
        "contradictions": contradictions,
        "corroborations": corroborations,
        "same_source_details": same_source_details,
        "unresolvable": len(unresolvable),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Record how a claim graph is built")
    parser.add_argument("claims", type=Path, help="an e3_claims.json")
    parser.add_argument("--out", type=Path, default=ROOT / "pipeline_out/trace/trace.json")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N claims (the viewer stays readable well under 1000)")
    args = parser.parse_args()

    if not args.claims.exists():
        print(f"not found: {args.claims}", file=sys.stderr)
        return 1

    claims = load_claims(args.claims)
    trace = build_trace(claims, args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")

    final = trace["final"]
    print(f"claims replayed     : {trace['claim_count']}")
    print(f"identities formed   : {final['identities']}")
    print(f"with more than one  : {final['identities_with_peers']}  "
          f"({final['comparable_claims']} comparable claims)")
    print(f"contradictions      : {final['contradictions']}")
    ablation = trace["conflict_ablation"]
    print(f"removed measurement : {ablation['removed_by_measurement']}")
    print(f"removed bound       : {ablation['removed_by_bound']}")
    print(f"same-source details : {ablation['removed_as_same_source_detail']}")
    print(f"corroborations      : {final['corroborations']}")
    print(f"unresolvable        : {final['unresolvable']}")
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
