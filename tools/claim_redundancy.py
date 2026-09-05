#!/usr/bin/env python3
"""Measure self-redundancy in an extraction. Reports; never deletes.

Why this exists
---------------
The blind Silexara run produced 259 claims where the answer key has 76 — 3.4x.
The obvious reading is that the extractor repeats itself, and the obvious repair
is a uniqueness filter: the decompose-then-verify literature builds exactly that
(CORE, arXiv:2407.03572, filters sub-claims "according to their uniqueness and
informativeness" because factual-precision metrics "can be manipulated by adding
obvious or repetitive subclaims").

Measured here on that exact run, the obvious reading is wrong:

    exact duplicate statements                     4 / 259
    pairs where one statement's tokens ⊆ another   0
    pairs at jaccard ≥ 0.75                        6   (one of them a real
                                                        distinction: "at least
                                                        twenty months" vs "at
                                                        most thirty months")

So a uniqueness filter would remove about four claims and leave the 3.4x intact.
The gap is not repetition — it is granularity. Gold states one claim per atomic
subject/predicate/value at a coarser grain than we emit, which is precisely the
confound the same literature warns about: valid claims extracted more atomically
"may not match reference claims simply because the reference set uses a less
granular approach". Chasing precision by deleting claims would therefore delete
correct, distinct facts to improve a number.

This module exists to keep that conclusion measurable rather than remembered,
and to catch the day it stops being true — if a prompt change ever does start
producing duplicates, this is what notices.

On identity collisions
----------------------
Two claims sharing a complete identity are only redundant if they also agree.
Same identity + DIFFERENT value is not a duplicate at all: it is the
CONTRADICTS test that tools/relation_rules.py already owns. Redundancy and
contradiction are the same identity comparison read for opposite purposes, so
this module reports them separately and adjudicates neither.

    python3 tools/claim_redundancy.py <extraction.json> [...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Deliberately not a tunable knob. It is a review threshold for a human, not a
# deletion threshold for a machine: nothing in this module removes a claim.
NEAR_DUPLICATE_JACCARD = 0.75

# The identity a claim asserts against. Missing dimensions are the reason this
# cannot be used to dedup on its own -- on a venture corpus most claims collapse
# onto (unspecified, Other, <period>), which describes the extractor's blind
# spots rather than the claims' sameness.
IDENTITY_FIELDS = ("entity", "metric", "period_canonical", "period", "perimeter",
                   "measurement", "scope", "basis", "scenario")

_WORD = re.compile(r"[^a-z0-9]+")


def _tokens(text: Any) -> frozenset[str]:
    return frozenset(w for w in _WORD.split(str(text or "").lower()) if w)


def _normalised(text: Any) -> str:
    return " ".join(sorted(_tokens(text)))


def _identity(claim: Mapping[str, Any]) -> tuple:
    return tuple(claim.get(f) for f in IDENTITY_FIELDS)


def _identity_completeness(claim: Mapping[str, Any]) -> float:
    """How much of the identity this claim actually pins down, 0.0-1.0.

    A claim identified only as (unspecified, Other) is not comparable to
    anything; reporting a "collision" between two such claims would be noise.
    """
    present = 0
    for field in IDENTITY_FIELDS:
        value = claim.get(field)
        if value in (None, "", "unspecified", "unknown", "Other", "none"):
            continue
        present += 1
    return present / len(IDENTITY_FIELDS)


def redundancy_report(claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every deterministic redundancy signal, with the claims that triggered it."""
    statements = [_normalised(c.get("statement")) for c in claims]
    token_sets = [_tokens(c.get("statement")) for c in claims]

    exact: dict[str, list[int]] = {}
    for i, text in enumerate(statements):
        if text:
            exact.setdefault(text, []).append(i)
    exact_groups = [idxs for idxs in exact.values() if len(idxs) > 1]

    subsumed: list[dict] = []
    near: list[dict] = []
    for i in range(len(claims)):
        a = token_sets[i]
        if not a:
            continue
        for j in range(i + 1, len(claims)):
            b = token_sets[j]
            if not b or statements[i] == statements[j]:
                continue          # already counted as an exact duplicate
            overlap = len(a & b)
            if overlap == min(len(a), len(b)):
                subsumed.append({"claims": [i, j],
                                 "statements": [claims[i].get("statement"),
                                                claims[j].get("statement")]})
            elif overlap / len(a | b) >= NEAR_DUPLICATE_JACCARD:
                near.append({"claims": [i, j],
                             "jaccard": round(overlap / len(a | b), 3),
                             "statements": [claims[i].get("statement"),
                                            claims[j].get("statement")]})

    # Identity collisions, split by whether the claims agree. Only claims that
    # actually pin an identity down take part; see _identity_completeness.
    by_identity: dict[tuple, list[int]] = {}
    for i, claim in enumerate(claims):
        if _identity_completeness(claim) >= 0.5:
            by_identity.setdefault(_identity(claim), []).append(i)

    agreeing: list[dict] = []
    disagreeing: list[dict] = []
    for identity, idxs in by_identity.items():
        if len(idxs) < 2:
            continue
        values = {str(claims[i].get("value")) for i in idxs}
        record = {"identity": [str(v) for v in identity], "claims": idxs,
                  "values": sorted(values)}
        (agreeing if len(values) == 1 else disagreeing).append(record)

    return {
        "claim_count": len(claims),
        "exact_duplicate_groups": exact_groups,
        "exact_duplicate_surplus": sum(len(g) - 1 for g in exact_groups),
        "subsumed_pairs": subsumed,
        "near_duplicate_pairs": near,
        "identity_collisions_agreeing": agreeing,
        "identity_collisions_disagreeing": disagreeing,
        "redundancy_rate": round(
            sum(len(g) - 1 for g in exact_groups) / len(claims), 4) if claims else 0.0,
    }


def _load_claims(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("claims", "admitted", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []


def format_report(report: Mapping[str, Any], label: str = "") -> str:
    lines = [f"{label or 'extraction'}: {report['claim_count']} claims",
             f"  exact duplicate statements     {report['exact_duplicate_surplus']:4d}"
             f"  ({report['redundancy_rate']:.1%})",
             f"  subsumed pairs                 {len(report['subsumed_pairs']):4d}",
             f"  near-duplicate pairs (≥{NEAR_DUPLICATE_JACCARD})    "
             f"{len(report['near_duplicate_pairs']):4d}   review, never auto-drop",
             f"  identity collisions, agreeing  "
             f"{len(report['identity_collisions_agreeing']):4d}   candidate duplicates",
             f"  identity collisions, disagreeing "
             f"{len(report['identity_collisions_disagreeing']):4d}   CONTRADICTS candidates,"
             f" not duplicates"]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    for path in paths:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 1
        claims = _load_claims(path)
        print(format_report(redundancy_report(claims), path.name))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
