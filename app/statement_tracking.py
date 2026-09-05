"""Lossless, read-only statement context for cards and durable indexing.

CAP-003 records and their identities remain unchanged. Normalization is delegated
to the existing identity module; missing dimensions are never filled by prose AI.
"""
from __future__ import annotations

import math
import re
from typing import Any

from tools.object_identity import metric_identity


def statement_context(claim: dict[str, Any]) -> dict[str, Any]:
    dimensions = metric_identity(claim)
    names = ("entity", "metric", "period", "scope", "basis", "measurement", "scenario", "unit", "currency")
    context = dict(zip(names, dimensions))
    context["definition"] = claim.get("definition_id") or None
    context["metric"] = claim.get("metric_label") or context["metric"] or None
    raw = claim.get("value_raw", claim.get("value"))
    value = claim.get("value")
    # Ranges, dates, booleans and arbitrary text cannot become a point estimate.
    numeric = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = value if math.isfinite(value) else None
    elif isinstance(value, str) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
        parsed = float(value)
        numeric = parsed if math.isfinite(parsed) else None
    bound = claim.get("bound") or None
    if bound == "RANGE":
        numeric = None
    context.update(
        value=numeric if numeric is not None else value if isinstance(value, (str, bool)) else None,
        valueType="NUMBER" if numeric is not None else "BOOLEAN" if isinstance(value, bool) else "TEXT" if isinstance(value, str) and value else "MISSING",
        rawValue=raw if raw is None or isinstance(raw, (str, bool)) or isinstance(raw, (int, float)) and math.isfinite(raw) else str(raw),
        bound=bound,
        claimKind=claim.get("claim_kind") or None,
        derivation=claim.get("derivation") or None,
        validationNotes=list(claim.get("nonblocking_validation_errors") or []),
    )
    context["missingFields"] = [name for name in ("definition", "period", "scope", "basis", "unit") if not context.get(name)]
    return context
