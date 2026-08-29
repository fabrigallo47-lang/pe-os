#!/usr/bin/env python3
"""Credential-free structural quality score for an E3 extraction manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

EPISTEMIC = {"asserted", "observed", "derived", "attested"}
EXCEL_LOCATOR = re.compile(r"^[^:]+::[^!]+!\d+:\d+(?::.*)?$")


def _present(value: Any) -> bool:
    return value not in (None, "", "unknown", "UNKNOWN")


def score_e3(
    manifest: Mapping[str, Any],
    *,
    source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Measure identity-field completeness without an answer key."""
    claims = manifest.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("E3 manifest must contain claims[]")
    selected_ids = set(source_ids or [])
    if selected_ids:
        claims = [claim for claim in claims if claim.get("source_id") in selected_ids]

    compiler_fields = {
        item.get("claim_id"): item
        for item in manifest.get("extraction_metadata", {}).get(
            "compiler_fields_per_claim", []
        )
        if isinstance(item, Mapping)
    }
    total = len(claims)

    def count(field: str) -> int:
        return sum(_present(claim.get(field)) for claim in claims)

    counts = {
        "period": count("period"),
        "perimeter": count("perimeter"),
        "epistemic": sum(claim.get("epistemic_class") in EPISTEMIC for claim in claims),
        "locator": count("locator"),
        "excel_locator": sum(
            bool(EXCEL_LOCATOR.match(str(claim.get("locator") or ""))) for claim in claims
        ),
        "complete_identity": sum(
            _present(claim.get("period"))
            and _present(claim.get("perimeter"))
            and claim.get("epistemic_class") in EPISTEMIC
            and _present(claim.get("locator"))
            for claim in claims
        ),
    }
    derived = [claim for claim in claims if claim.get("epistemic_class") == "derived"]
    counts["derived_with_derivation"] = sum(
        _present(compiler_fields.get(claim.get("claim_id"), {}).get("derivation"))
        for claim in derived
    )

    rates = {
        key: round(value / total, 4) if total else 0.0
        for key, value in counts.items()
        if key != "derived_with_derivation"
    }
    rates["derived_with_derivation"] = (
        round(counts["derived_with_derivation"] / len(derived), 4) if derived else 1.0
    )
    return {
        "total_claims": total,
        "source_ids": sorted(selected_ids),
        "counts": counts,
        "rates": rates,
        "derived_claims": len(derived),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = score_e3(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        source_ids=args.source_id,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Claims: {report['total_claims']}")
        for field, rate in report["rates"].items():
            print(f"  {field:<26} {rate:>7.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
