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

from tools.object_identity import is_resolvable, metric_identity  # noqa: E402


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


def build_trace(claims: list[dict[str, Any]], limit: int | None = None) -> dict[str, Any]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    unresolvable: list[str] = []
    steps: list[dict[str, Any]] = []
    contradictions = 0
    corroborations = 0

    for index, claim in enumerate(claims[: limit or len(claims)], start=1):
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

        identity = metric_identity(claim)
        key = "|".join(identity)
        peers = groups[identity]

        if not peers:
            event = "NEW_IDENTITY"
            why = "first claim of this quantity — a node, with no meaning yet"
        elif any(_comparable_value(p) == value and value for p in peers):
            event = "CORROBORATES"
            corroborations += 1
            why = ("another source states the same value for the same identity — "
                   "two claims are kept, never merged; the agreement is the information")
        else:
            event = "CONTRADICTS"
            contradictions += 1
            others = ", ".join(sorted({_comparable_value(p) for p in peers if _comparable_value(p)}))
            why = (f"same identity, divergent value ({value} vs {others}) — "
                   "this is the moment the case gains a conflict")

        peer_ids = [str(p.get("claim_id")) for p in peers]
        groups[identity].append(claim)

        steps.append({
            "n": index, "claim_id": claim_id, "statement": statement,
            "event": event, "identity": list(identity), "group_key": key,
            "group_size": len(groups[identity]), "value": value,
            "peers": peer_ids, "why": why,
            "totals": _totals(groups, unresolvable, contradictions, corroborations),
        })

    return {
        "generated_from": "tools/graph_trace.py",
        "claim_count": len(steps),
        "steps": steps,
        "final": _totals(groups, unresolvable, contradictions, corroborations),
    }


def _totals(groups, unresolvable, contradictions, corroborations) -> dict[str, int]:
    multi = [g for g in groups.values() if len(g) > 1]
    return {
        "identities": len(groups),
        "claims_placed": sum(len(g) for g in groups.values()),
        "identities_with_peers": len(multi),
        "comparable_claims": sum(len(g) for g in multi),
        "contradictions": contradictions,
        "corroborations": corroborations,
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
    print(f"corroborations      : {final['corroborations']}")
    print(f"unresolvable        : {final['unresolvable']}")
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
