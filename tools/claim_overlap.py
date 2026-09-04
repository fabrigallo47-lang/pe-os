#!/usr/bin/env python3
"""Mechanically report corroborating and disagreeing E3 claims, never resolve them.

The vault contradiction skill reasons over already-typed vault claims.  This is
earlier and narrower: it joins E3's compiler fields back onto its admitted
claims, groups only exact metric identities, and makes overlap visible before a
claim is admitted to the vault.

Run: ``python3 tools/claim_overlap.py pipeline_out/e3/K-PRE/e3_claims.json``
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.object_identity import (  # noqa: E402
    IDENTITY_DIMENSION_NAMES,
    is_resolvable,
    metric_identity,
)

# Values in E3 are display strings, and a comparison that insists that a
# transcribed ``11.9`` equal only another byte-for-byte ``11.9`` would turn
# harmless rounding/serialization noise into a contradiction.  Half a percent
# (with a 0.01 floor for small values) matches derivation_verifier's documented
# tolerance: it is narrow enough not to hide material financial differences,
# while avoiding binary-float and ordinary reporting-precision false alarms.
NUMERIC_TOLERANCE_FRACTION = 0.005
NUMERIC_TOLERANCE_FLOOR = 0.01
_NUMERIC_VALUE_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")


def _compiler_fields_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Use E3's claim_id join, rather than guessing fields from statement prose."""
    return {
        row["claim_id"]: row
        for row in payload.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
        if row.get("claim_id")
    }


def _joined_claim(claim: dict[str, Any], compiler_fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # The top-level claim owns provenance and value.  Compiler fields supply
    # identity dimensions that E3 deliberately keeps in its metadata sidecar.
    return {**compiler_fields.get(claim.get("claim_id"), {}), **claim}


def _unresolvable_reason(claim: dict[str, Any]) -> str:
    identity = metric_identity(claim)
    missing = [name for name, value in zip(IDENTITY_DIMENSION_NAMES[:3], identity[:3]) if not value]
    return "missing " + ", ".join(missing)


def _numeric_value(value: Any) -> float | None:
    """Parse only a whole plain number; ranges and approximations stay text.

    In particular, ``8-12`` is not silently turned into either endpoint or a
    midpoint.  That would manufacture a comparison the source did not state,
    the same reason derivation_verifier refuses to coerce it to float.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _NUMERIC_VALUE_RE.fullmatch(text):
        return None
    return float(text.replace(",", ""))


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def compare_values(left: Any, right: Any) -> dict[str, Any]:
    """State whether two values agree, without inferring a value from text."""
    left_number = _numeric_value(left)
    right_number = _numeric_value(right)
    if left_number is not None and right_number is not None:
        tolerance = max(
            max(abs(left_number), abs(right_number)) * NUMERIC_TOLERANCE_FRACTION,
            NUMERIC_TOLERANCE_FLOOR,
        )
        difference = abs(left_number - right_number)
        return {
            "agree": difference <= tolerance,
            "reason": "numeric values compared within 0.5% (minimum 0.01) tolerance",
            "difference": difference,
            "tolerance": tolerance,
        }

    # A non-numeric string and a numeric value have no honest common numeric
    # representation.  The one exception is identical normalized text, which
    # lets harmless case/whitespace differences corroborate without coercion.
    same_text = _normalized_text(left) == _normalized_text(right)
    if left_number is None and right_number is None:
        reason = "non-numeric values compared as normalized text"
    else:
        reason = (
            "numeric and non-numeric values disagree unless their normalized "
            "strings match exactly; ranges/approximations are not coerced"
        )
    return {"agree": same_text, "reason": reason}


def _shows_working_rank(claim: dict[str, Any]) -> tuple[int, str]:
    derivation = claim.get("derivation")
    # Ordering exposes the claim with executable-looking support first, but is
    # deliberately not a truth score: a derivation can be wrong or unparseable.
    shows_working = claim.get("epistemic_class") == "derived" and bool(
        isinstance(derivation, str) and derivation.strip()
    )
    return (0 if shows_working else 1, str(claim.get("claim_id") or ""))


def _report_claim(claim: dict[str, Any]) -> dict[str, Any]:
    source = claim.get("source_id") or claim.get("source")
    return {
        "claim_id": claim.get("claim_id"),
        "statement": claim.get("statement"),
        "value": claim.get("value"),
        "source_id": source,
        "locator": claim.get("locator"),
        "epistemic_class": claim.get("epistemic_class"),
        "derivation": claim.get("derivation"),
        "shows_working": _shows_working_rank(claim)[0] == 0,
    }


def analyze_claims(payload: dict[str, Any]) -> dict[str, Any]:
    """Return overlap findings for E3's admitted ``claims`` list.

    E3 has already performed admission/deduplication before serializing this
    list.  This pass neither rejects nor edits those claims; it only excludes
    identities too incomplete for a safe mechanical comparison.
    """
    fields_by_id = _compiler_fields_by_id(payload)
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    skipped: Counter[str] = Counter()
    for raw_claim in payload.get("claims", []):
        claim = _joined_claim(raw_claim, fields_by_id)
        if not is_resolvable(claim):
            skipped[_unresolvable_reason(claim)] += 1
            continue
        groups[metric_identity(claim)].append(claim)

    findings = []
    for identity, claims in groups.items():
        if len(claims) < 2:
            continue
        ordered = sorted(claims, key=_shows_working_rank)
        comparisons = [compare_values(ordered[0].get("value"), other.get("value")) for other in ordered[1:]]
        status = "CORROBORATION" if all(item["agree"] for item in comparisons) else "CONTRADICTION CANDIDATE"
        findings.append({
            "status": status,
            "identity": dict(zip(IDENTITY_DIMENSION_NAMES, identity)),
            "claims": [_report_claim(claim) for claim in ordered],
            "comparisons_to_first_claim": comparisons,
        })

    findings.sort(key=lambda finding: (finding["status"], tuple(finding["identity"].values())))
    corroborations = [f for f in findings if f["status"] == "CORROBORATION"]
    contradictions = [f for f in findings if f["status"] == "CONTRADICTION CANDIDATE"]
    return {
        "claims_seen": len(payload.get("claims", [])),
        "claims_resolvable": sum(len(claims) for claims in groups.values()),
        "claims_skipped_unresolvable": sum(skipped.values()),
        "skipped_by_reason": dict(sorted(skipped.items())),
        "identity_groups": len(groups),
        "overlap_groups": len(findings),
        "corroboration_groups": len(corroborations),
        "contradiction_candidate_groups": len(contradictions),
        "findings": findings,
    }


def _print_report(report: dict[str, Any], contradiction_limit: int | None = None) -> None:
    print(f"{report['claims_seen']} admitted claims seen")
    print(f"{report['claims_resolvable']} resolvable; {report['claims_skipped_unresolvable']} skipped as unresolvable")
    for reason, count in report["skipped_by_reason"].items():
        print(f"  {count:>4}  {reason}")
    print(f"{report['overlap_groups']} identity groups have >1 claim")
    print(f"  {report['corroboration_groups']:>4}  CORROBORATION")
    print(f"  {report['contradiction_candidate_groups']:>4}  CONTRADICTION CANDIDATE")

    contradictions = [f for f in report["findings"] if f["status"] == "CONTRADICTION CANDIDATE"]
    if contradiction_limit is not None:
        contradictions = contradictions[:contradiction_limit]
    for finding in contradictions:
        print(f"\n[{finding['status']}] {finding['identity']}")
        for claim in finding["claims"]:
            print(f"  {claim['claim_id']} ({claim['epistemic_class']}; shows_working={claim['shows_working']})")
            print(f"    statement: {claim['statement']}")
            print(f"    value: {claim['value']!r}")
            print(f"    source: {claim['source_id']} @ {claim['locator']}")
            if claim["derivation"]:
                print(f"    derivation: {claim['derivation']}")
        for comparison in finding["comparisons_to_first_claim"]:
            if not comparison["agree"]:
                print(f"  comparison: {comparison['reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("claims_path", type=Path)
    parser.add_argument("--contradictions", type=int, default=5,
                        help="number of contradiction candidates to print (default: 5)")
    parser.add_argument("--json", action="store_true", help="print the complete report as JSON")
    args = parser.parse_args()
    report = analyze_claims(json.loads(args.claims_path.read_text()))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report, args.contradictions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
