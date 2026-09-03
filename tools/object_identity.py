#!/usr/bin/env python3
"""Canonical object identity — one place that owns normalization and ID computation.

Every writer (extract.py, extract_v2_physical.py, the V20 router, the ledger) must import
identity from here.  Today each computes its own, which is why the same fact can
land twice under two IDs.

The rule this module enforces:

    normalize first, hash second — never the reverse.

Why the vocabularies below are shaped the way they are
------------------------------------------------------
`perimeter` in the current vault is not an atomic token.  It is prose that packs
four dimensions into one sentence::

    "Keystone consolidated EBITDA under independent QoE adjustment perimeter"
     └ entity   └ scope      └ metric └ basis

So an exact-match alias table (the approach in ``identity_resolver.py``) cannot
work on it: the key space is unbounded natural language.  ``decompose_perimeter``
therefore *extracts* the four dimensions instead of looking up the whole string.

Target state: the extractor emits ``entity`` / ``scope`` / ``basis`` /
``measurement`` as separate bounded fields and decomposition becomes unnecessary.
``decompose_perimeter`` is the bridge for the 884 legacy claims until re-extraction.

Two tuples, not one
-------------------
metric identity  — WHAT is being measured; scenario belongs here
    (entity, metric, period, scope, basis, measurement, scenario)

claim identity   — WHO asserts it and from where; source version belongs here
    metric identity + (source, source_version, locator, epistemic, value)

Base case and downside are two metrics.  CIM v1 and CIM v2 are two claims about
one metric.  Collapsing these into one tuple makes scenarios look like
contradictions and versions look like duplicates.

Run ``python3 tools/object_identity.py`` to audit vault coverage.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent

# ── Vocabularies ──────────────────────────────────────────────────────────────
# Values observed in vault/deals/*/claims/*.md, not invented.  Each maps a
# surface form to a canonical token.  Extend by adding surface forms; never by
# adding a second canonical token for something already covered.

ENTITY_ALIASES: dict[str, str] = {
    "keystone": "Keystone",
    "alderstone": "Alderstone",
    "riverton": "Riverton",
    "riverton industrial group": "Riverton",
    "apex": "Apex",
    "apex manufacturing": "Apex",
}

# The "view" a number is stated under.  This is the dimension that makes
# 12.7m (seller) and 11.4m (firm) two legitimate facts rather than a conflict.
BASIS_ALIASES: dict[str, str] = {
    "seller": "SellerView",
    "seller adjustment": "SellerView",
    "seller adjusted": "SellerView",
    "seller-adjusted": "SellerView",
    "seller management forecast": "SellerView",
    "qoe": "QoEView",
    "quality of earnings": "QoEView",
    "independent qoe adjustment": "QoEView",
    "qoe adjustment": "QoEView",
    "firm": "FirmView",
    "firm adjustment": "FirmView",
    "firm valuation": "FirmView",
    "firm valuation, leverage and returns": "FirmView",
    "covenant": "CovenantView",
    "covenant adjustment": "CovenantView",
    "reported": "ReportedView",
    "statutory": "ReportedView",
}

SCOPE_ALIASES: dict[str, str] = {
    "consolidated": "consolidated",
    "standalone": "standalone",
    "customer": "customer",
    "segment": "segment",
    "deal consolidated": "consolidated",
    "proforma": "proforma",
    "pro forma": "proforma",
}

# How the quantity is cut — matters for concentration claims especially, where
# billing-account level and parent level give materially different answers.
MEASUREMENT_ALIASES: dict[str, str] = {
    "individual billing account": "billing_account",
    "billing account": "billing_account",
    "individual customer billing": "billing_account",
    "individual customer": "customer",
    "invoice": "invoice",
    "ultimate parent": "parent",
    "parent": "parent",
}

# The extractor can only emit values from extract_v2.METRIC_ENUM, so that list —
# not a hand-written table — is the authority on which metrics exist.  Mirrored
# here to keep this module importable on its own; _audit_vault() fails loudly if
# the two drift apart.
METRIC_VOCABULARY: tuple[str, ...] = (
    "Revenue", "Revenue Growth", "EBITDA", "EBITDA Margin", "EBITDA Adjustment",
    "Gross Profit", "Gross Margin", "EBIT", "Net Income", "Free Cash Flow",
    "Operating Cash Flow", "Capex", "Working Capital", "DSO", "DPO",
    "Inventory Days", "Recurring Revenue", "Earnings Quality Risk",
    "Revenue Quality", "Adjustment Supportability", "Customer Concentration", "Customer Count",
    "Active Billing Accounts", "Customer Retention", "Contract Terms",
    "Customer Contract Terms", "Market Position", "Market Size",
    "Enterprise Value", "Equity Value", "Entry Multiple", "Exit Multiple", "Exit EV",
    "Net Debt", "Gross Debt", "Leverage", "Interest Coverage",
    "Sponsor Equity", "Seller Rollover", "First-Lien Debt",
    "Revolver Capacity", "DDTL Availability", "Covenant EBITDA",
    "Covenant Threshold", "Covenant Headroom", "Exit Horizon",
    "Supported Price", "MOIC", "IRR", "Net Working Capital",
    "Net Working Capital Target", "Net Working Capital Adjustment",
    "Headcount", "Team Tenure",
    "Acquisition Count", "Systems Integration Risk", "Integration Risk",
    "Operational Risk", "Key Person Risk", "Regulatory Risk", "Competition Risk",
    "IC Conditions", "IC Vote", "Decision Coherence",
    "EBITDA Add-back",
)


def _canon_token(name: str) -> str:
    """'Free Cash Flow' -> 'FreeCashFlow'. Stable, hashable, human-readable."""
    return re.sub(r"[^A-Za-z0-9]+", "", name.title())


# Surface form -> canonical token.  Every vocabulary entry maps to itself; the
# hand-written entries below only cover phrasings the enum does not use, which
# is what legacy prose subjects need.
METRIC_ALIASES: dict[str, str] = {m.lower(): _canon_token(m) for m in METRIC_VOCABULARY}
METRIC_ALIASES |= {
    "ebitda": "EBITDA",
    "adjusted ebitda": "EBITDA",
    "adj ebitda": "EBITDA",
    "firm ebitda": "EBITDA",
    "reported ebitda": "EBITDA",
    "covenant ebitda": "EBITDA",
    "seller-adjusted ebitda": "EBITDA",
    "opening firm ebitda": "EBITDA",
    "ebitda margin": "EBITDAMargin",
    "revenue": "Revenue",
    "ltm revenue": "Revenue",
    "revenue growth": "RevenueGrowth",
    "gross profit": "GrossProfit",
    "gross margin": "GrossMargin",
    "enterprise value": "EnterpriseValue",
    "ev": "EnterpriseValue",
    "capital expenditure": "Capex",
    "capex": "Capex",
    "customer concentration": "CustomerConcentration",
    "concentration": "CustomerConcentration",
    "net leverage": "NetLeverage",
    "opening net leverage ratio": "NetLeverage",
    "leverage": "NetLeverage",
    "first-lien opening debt": "FirstLienDebt",
    "term loan": "FirstLienDebt",
    "first lien debt": "FirstLienDebt",
    "seller equity value": "SellerEquity",
    "seller equity": "SellerEquity",
    "sponsor initial cash equity": "SponsorEquity",
    "sponsor equity": "SponsorEquity",
    "moic": "MOIC",
    "irr": "IRR",
    "working capital": "WorkingCapital",
    "nwc": "WorkingCapital",
}

SCENARIO_ALIASES: dict[str, str] = {
    "base": "base",
    "base case": "base",
    "management case": "management",
    "management forecast": "management",
    "seller case": "seller",
    "seller management forecast": "seller",
    "upside": "upside",
    "upside case": "upside",
    "downside": "downside",
    "downside case": "downside",
    "stress": "downside",
    "": "base",          # unstated defaults to base — an assumption, see AUDIT
}

PERIOD_NORMALIZE: dict[str, str] = {
    "fy2025": "FY2025", "fy25": "FY2025", "2025a": "FY2025", "2025": "FY2025",
    "fy2025a": "FY2025", "fy2025e": "FY2025E", "fy25e": "FY2025E",
    "fy2024": "FY2024", "fy24": "FY2024", "2024a": "FY2024", "fy2024a": "FY2024",
    "fy2023": "FY2023", "fy23": "FY2023", "2023a": "FY2023", "fy2023a": "FY2023",
    "fy2026e": "FY2026E", "fy2027e": "FY2027E", "fy2030e": "FY2030E",
    "ltm": "LTM", "ltm dec-2025": "LTM", "ltm dec 2025": "LTM", "ltm 2025": "LTM",
    "exit ltm": "ExitLTM",
    "opening": "Opening", "entry basis": "Opening", "entry": "Opening",
    "entry to exit": "EntryToExit", "cross-period": "CrossPeriod",
}

# Period values that are NOT periods.  These are extraction artefacts: an ingest
# timestamp or a parser shrug written into a field that should carry when the
# fact was true.  They must not be normalized into something that looks valid —
# they must stay visible as missing, so the coverage report can count them.
PERIOD_NON_VALUES = ("unknown", "n/a", "none", "")
_EXTRACTION_DATE_RE = re.compile(r"^as of \d{4}-\d{2}-\d{2}$", re.I)

# Tokens this module itself emits — they must survive a second normalization
# pass unchanged, or a re-normalized claim silently loses its period.
PERIOD_CANONICAL = frozenset(
    {"LTM", "ExitLTM", "Opening", "EntryToExit", "CrossPeriod"}
)


# ── Normalization ─────────────────────────────────────────────────────────────

def _clean(s: Any) -> str:
    # Numeric zero is evidence, not absence. ``s or ""`` erased 0/0.0 before
    # hashing, so an ID computed from RawClaim(value=0) differed from the same
    # claim reloaded from E3, where the serialized value is "0.0".
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def normalize_metric(raw: Any) -> str:
    """Map a metric name (or a prose subject containing one) to a canonical token."""
    s = _clean(raw).lower().strip("\"'")
    if s in METRIC_ALIASES:
        return METRIC_ALIASES[s]
    # Longest alias first, so "ebitda margin" wins over "ebitda".
    for alias in sorted(METRIC_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", s):
            return METRIC_ALIASES[alias]
    return ""


def normalize_period(raw: Any) -> str:
    """Canonical period, or "" when the value is not a period at all.

    Returning "" for an extraction date is deliberate: a claim whose period is
    the day it was ingested has no period, and pretending otherwise would let it
    match other claims it has nothing temporally in common with.
    """
    s = _clean(raw).strip("\"'")
    if not s or s.lower() in PERIOD_NON_VALUES:
        return ""
    if _EXTRACTION_DATE_RE.match(s):
        return ""                                   # ingest stamp, not a period
    if s in PERIOD_CANONICAL:
        return s                                    # already canonical
    low = s.lower()
    if low in PERIOD_NORMALIZE:
        return PERIOD_NORMALIZE[low]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s                                    # ISO date is already canonical
    if re.match(r"^\d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}$", s):
        return s                                    # explicit range
    m = re.search(r"\bFY\s*(\d{4})\s*([AE])?\b", s, re.I)
    if m:
        return f"FY{m.group(1)}{(m.group(2) or '').upper()}"
    return ""                                       # prose — not a period


_UNIT_CANONICAL: dict[str, str] = {
    "$m": "mm", "$mm": "mm", "£m": "mm", "€m": "mm", "mm": "mm", "m": "mm",
    "$bn": "bn", "bn": "bn", "b": "bn",
    "%": "pct", "pct": "pct", "percent": "pct",
    "x": "x", "days": "days", "d": "days", "bps": "bps",
}

# The magnitude and the currency are separate dimensions: 11.4 $mm and 11.4 €mm
# share a magnitude and are not the same quantity. Splitting them keeps a
# currency change from reading as agreement.
_CURRENCY_SIGNS: tuple[tuple[str, str], ...] = (
    ("$", "USD"), ("usd", "USD"),
    ("£", "GBP"), ("gbp", "GBP"),
    ("€", "EUR"), ("eur", "EUR"),
)


def normalize_measurement(raw: Any) -> str:
    """Which slice of a quantity a figure covers. "total" means the whole.

    The distinction this preserves is between a breakdown and a disagreement.
    Three service lines reporting 30.3, 20.0 and 14.1 are components of one
    revenue; with this dimension empty on all three they share an identity and
    read as three claims contradicting each other — which is what the Keystone
    corpus actually produced, 374 conflicts of which most were breakdowns.

    An unstated slice normalizes to "" and NOT to "total": a claim that never
    said whether it was the whole is not the same as one that said it was. The
    first is a coverage limit; treating it as the second would silently merge a
    component into the total it belongs to.
    """
    text = _clean(raw).lower()
    if not text or text in ("unspecified", "unknown", "none", "n/a"):
        return ""
    if text in ("total", "whole", "aggregate", "consolidated total", "all"):
        return "total"
    known = _find_alias(text, MEASUREMENT_ALIASES)
    if known:
        return known
    # Otherwise keep the source's own words, normalized only for whitespace and
    # case. A named slice is worth more as itself than mapped into a small
    # controlled list that could not anticipate this deal's segments.
    return re.sub(r"\s+", " ", text)


def normalize_unit(raw: Any) -> str:
    """Magnitude only — millions, percent, multiple — never the currency."""
    s = _clean(raw).lower()
    if not s:
        return ""
    for sign, _ in _CURRENCY_SIGNS:
        s = s.replace(sign, "")
    s = s.strip()
    return _UNIT_CANONICAL.get(s, s)


def normalize_currency(raw: Any) -> str:
    """Currency only, read from an explicit field or from a unit like ``$mm``."""
    s = _clean(raw).lower()
    if not s:
        return ""
    for sign, code in _CURRENCY_SIGNS:
        if sign in s:
            return code
    return s.upper() if len(s) == 3 and s.isalpha() else ""


def normalize_scenario(raw: Any) -> str:
    s = _clean(raw).lower()
    if s in SCENARIO_ALIASES:
        return SCENARIO_ALIASES[s]
    for alias in sorted((a for a in SCENARIO_ALIASES if a), key=len, reverse=True):
        if alias in s:
            return SCENARIO_ALIASES[alias]
    return "base"


def _find_alias(text: str, table: dict[str, str]) -> str:
    """Longest-match lookup of any alias appearing inside free text."""
    for alias in sorted(table, key=len, reverse=True):
        if alias and re.search(rf"\b{re.escape(alias)}\b", text):
            return table[alias]
    return ""


def decompose_perimeter(raw: Any) -> dict[str, str]:
    """Split a prose perimeter into its atomic dimensions.

    Bridge for legacy claims.  Once the extractor emits these as separate fields
    this becomes a no-op passthrough.

    >>> decompose_perimeter("Keystone consolidated EBITDA under independent QoE adjustment perimeter")
    {'entity': 'Keystone', 'scope': 'consolidated', 'basis': 'QoEView', 'measurement': ''}
    """
    s = _clean(raw).lower()
    return {
        "entity": _find_alias(s, ENTITY_ALIASES),
        "scope": _find_alias(s, SCOPE_ALIASES),
        "basis": _find_alias(s, BASIS_ALIASES),
        "measurement": _find_alias(s, MEASUREMENT_ALIASES),
    }


# ── Identity tuples ───────────────────────────────────────────────────────────

def metric_identity(claim: dict) -> tuple[str, ...]:
    """WHAT is being measured.  Scenario belongs here; source does not.

    Two claims sharing this tuple are about the same quantity — they may
    corroborate or contradict.  Two claims differing in it are simply different
    facts, however similar their wording.

    Ordered to match ``metric_identity_dimensions`` in the Universal Investment
    Kernel v0.2 (vault/policy/archetypes/semantic_handoff_v0_2/). The kernel names
    the economic boundary ``perimeter``; this module calls the same dimension
    ``scope``, because the extractor field it comes from is named that and the
    prose column it is recovered from is a different, compound ``perimeter``.

    ``unit`` and ``currency`` close the tuple. Without them 11.4 in $mm and 11.4
    in €mm are one quantity with one value, and a currency change reads as
    agreement rather than as two different facts.
    """
    # Structured fields win when the extractor supplied them; prose decomposition
    # is the fallback for claims extracted before those fields existed.
    perim = claim.get("perimeter_parts") or decompose_perimeter(claim.get("perimeter"))

    def _field(name: str, fallback: str = "") -> str:
        raw = _clean(claim.get(name))
        if not raw or raw.lower() in ("unspecified", "unknown", "none"):
            return fallback
        return raw

    entity = _field("entity") or perim.get("entity", "")
    if entity:
        entity = ENTITY_ALIASES.get(entity.lower(), entity)

    period = normalize_period(_field("period_canonical") or claim.get("period"))
    metric = normalize_metric(claim.get("metric") or claim.get("subject"))

    return (
        entity,
        metric,
        period,
        _field("scope") or perim.get("scope", ""),
        _field("basis") or perim.get("basis", ""),
        normalize_measurement(_field("measurement") or perim.get("measurement", "")),
        normalize_scenario(_field("scenario")),
        normalize_unit(_field("unit")),
        normalize_currency(_field("currency") or _field("unit")),
    )


def claim_identity(claim: dict) -> tuple[str, ...]:
    """WHO asserts it, from where, with what value.  Source version belongs here.

    Two sources stating the same number are two claims, never one: agreement
    between independent sources is evidence, not redundancy.
    """
    source = claim.get("source")
    source_record = source if isinstance(source, dict) else {}
    source_id = (
        source_record.get("source_id")
        or source_record.get("artifact")
        or claim.get("source_id")
        or (source if isinstance(source, str) else "")
    )
    source_version = (
        claim.get("source_version_id")
        or claim.get("source_version")
        or source_record.get("source_version_id")
        or source_record.get("source_version")
    )
    locator = claim.get("locator") or source_record.get("locator")
    return metric_identity(claim) + (
        _clean(source_id),
        _clean(source_version),
        _clean(locator),
        _clean(claim.get("epistemic") or claim.get("epistemic_class") or "asserted"),
        _clean(claim.get("value")),
    )


def object_id(object_type: str, identity: Iterable[str]) -> str:
    """Stable content-addressed ID.  Same identity anywhere → same ID, always.

    Only normalized tokens reach the hash.  Raw LLM prose must never be hashed:
    a rephrasing of the same fact would silently become a different object.
    """
    payload = "|".join(_clean(p) for p in identity)
    return f"{object_type}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def metric_id(claim: dict) -> str:
    return object_id("metric", metric_identity(claim))


def claim_id(claim: dict) -> str:
    return object_id("claim", claim_identity(claim))


def is_resolvable(claim: dict) -> bool:
    """True when the metric identity is complete enough to compare against others.

    An unresolvable claim is not an error — it is a declared coverage limit.  It
    stays in the ledger, visible, and is never silently matched to anything.
    """
    ident = metric_identity(claim)
    return bool(ident[0] and ident[1] and ident[2])      # entity, metric, period


# ── Audit ─────────────────────────────────────────────────────────────────────

IDENTITY_DIMENSION_NAMES: tuple[str, ...] = (
    "entity",
    "metric",
    "period",
    "scope",
    "basis",
    "measurement",
    "scenario",
    "unit",
    "currency",
)

_TEMPORAL_HINT_RE = re.compile(
    r"\b(?:FY\s*\d{2,4}[AE]?|LTM|Q[1-4]\s*\d{2,4}|20\d{2}|"
    r"year\s+ended|as\s+of|entry|opening|exit)\b",
    re.IGNORECASE,
)


def claims_from_e3(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Join frozen CAP-003 claims to the structured compiler sidecar."""
    sidecar = {
        str(item.get("claim_id")): item
        for item in payload.get("extraction_metadata", {}).get(
            "compiler_fields_per_claim", []
        )
    }
    return [
        {**claim, **sidecar.get(str(claim.get("claim_id")), {})}
        for claim in payload.get("claims", [])
    ]


def _missing_classification(claim: dict[str, Any], dimension: str) -> str:
    """Classify a missing identity field without pretending source text says more.

    This is deliberately conservative. A structured cue that the extractor
    failed to carry is a defect; otherwise absence remains a declared source
    limitation. Qualitative statements legitimately lack several quantitative
    dimensions.
    """
    kind = _clean(claim.get("claim_kind") or "QUANTITATIVE").upper()
    text = " ".join(
        (_clean(claim.get("statement")), _clean(claim.get("perimeter")))
    ).lower()

    if dimension in {"entity", "metric"}:
        return "extractor_defect"
    if kind == "QUALITATIVE" and dimension in {
        "period", "scope", "basis", "measurement", "unit", "currency"
    }:
        return "legitimate_qualitative_claim"
    if dimension == "period":
        return (
            "extractor_defect"
            if _TEMPORAL_HINT_RE.search(text)
            else "legitimate_source_omission"
        )

    cue_tables = {
        "scope": SCOPE_ALIASES,
        "basis": BASIS_ALIASES,
        "measurement": MEASUREMENT_ALIASES,
        "scenario": {key: value for key, value in SCENARIO_ALIASES.items() if key},
    }
    if dimension in cue_tables and _find_alias(text, cue_tables[dimension]):
        return "extractor_defect"
    if dimension == "unit" and re.search(
        r"(?:[$£€]\s*\d|\d\s*(?:%|x|bps|days?)\b)", text, re.IGNORECASE
    ):
        return "extractor_defect"
    if dimension == "currency" and re.search(r"[$£€]\s*\d", text):
        return "extractor_defect"
    return "legitimate_source_omission"


def audit_claims(claims: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return reproducible identity coverage and classified missing dimensions."""
    items = list(claims)
    resolvable = 0
    missing: dict[str, Counter[str]] = {
        name: Counter() for name in IDENTITY_DIMENSION_NAMES
    }
    defect_examples: dict[str, list[dict[str, str]]] = {
        name: [] for name in IDENTITY_DIMENSION_NAMES
    }

    for claim in items:
        identity = metric_identity(claim)
        if is_resolvable(claim):
            resolvable += 1
        for name, value in zip(IDENTITY_DIMENSION_NAMES, identity):
            if value:
                continue
            classification = _missing_classification(claim, name)
            missing[name][classification] += 1
            if classification == "extractor_defect" and len(defect_examples[name]) < 10:
                defect_examples[name].append({
                    "claim_id": _clean(claim.get("claim_id")),
                    "locator": _clean(claim.get("locator")),
                    "statement": _clean(claim.get("statement"))[:180],
                })

    total = len(items)
    dimensions: dict[str, Any] = {}
    for name in IDENTITY_DIMENSION_NAMES:
        classifications = dict(sorted(missing[name].items()))
        dimensions[name] = {
            "missing": sum(classifications.values()),
            "classifications": classifications,
            "extractor_defect_examples": defect_examples[name],
        }

    structured_fields = {}
    for name in ("entity", "measurement", "bound"):
        missing_tokens = {"unspecified", "unknown", "none"}
        if name == "bound":
            # NONE is a real member of BOUND_ENUM: it means the claim carries
            # no numeric comparison, not that L2 omitted the field.
            missing_tokens.remove("none")
        absent = sum(
            1
            for claim in items
            if not _clean(claim.get(name))
            or _clean(claim.get(name)).lower() in missing_tokens
        )
        structured_fields[name] = {"present": total - absent, "missing": absent}

    return {
        "claim_count": total,
        "resolvable": resolvable,
        "unresolvable": total - resolvable,
        "resolvable_pct": round(100.0 * resolvable / total, 2) if total else 0.0,
        "identity_dimensions": dimensions,
        "structured_extraction_fields": structured_fields,
    }


def audit_e3_files(paths: Iterable[Path]) -> dict[str, Any]:
    manifests: list[dict[str, Any]] = []
    unique_claims: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        payload = json.loads(path.read_text(encoding="utf-8"))
        claims = claims_from_e3(payload)
        manifests.append({
            "path": str(path),
            "manifest_id": str(payload.get("manifest_id") or path.parent.name),
            "audit": audit_claims(claims),
        })
        for claim in claims:
            key = _clean(claim.get("claim_id")) or json.dumps(
                claim, sort_keys=True, ensure_ascii=False
            )
            unique_claims.setdefault(key, claim)
    return {
        "schema_version": "panta.identity-audit/1.0",
        "manifests": manifests,
        "unique_corpus": audit_claims(unique_claims.values()),
    }

def _audit_vault() -> None:
    """Report how much of the current vault has a resolvable identity."""
    import collections

    claims = sorted(ROOT.glob("vault/deals/*/claims/*.md"))
    if not claims:
        print("no vault claims found")
        return

    total = resolvable = 0
    missing: collections.Counter = collections.Counter()
    bases: collections.Counter = collections.Counter()

    for path in claims:
        fm: dict[str, Any] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:40]:
            m = re.match(r"^(subject|period|perimeter|value|epistemic):\s*(.*)$", line)
            if m:
                fm[m.group(1)] = m.group(2).strip().strip("\"'")
        if not fm:
            continue
        total += 1
        ident = metric_identity(fm)
        if is_resolvable(fm):
            resolvable += 1
        else:
            for name, val in zip(("entity", "metric", "period"), ident[:3]):
                if not val:
                    missing[name] += 1
        if ident[4]:
            bases[ident[4]] += 1

    pct = 100.0 * resolvable / total if total else 0.0
    print(f"vault claims scanned : {total}")
    print(f"resolvable identity  : {resolvable} ({pct:.1f}%)")
    print(f"unresolvable         : {total - resolvable}")
    print("\nmissing dimension (unresolvable claims):")
    for name, count in missing.most_common():
        print(f"  {name:<12} {count}")
    print("\nbasis/view recovered from prose perimeter:")
    for name, count in bases.most_common():
        print(f"  {name:<16} {count}")


def _print_audit(report: dict[str, Any]) -> None:
    for manifest in report["manifests"]:
        audit = manifest["audit"]
        print(
            f"{manifest['manifest_id']}: {audit['resolvable']}/"
            f"{audit['claim_count']} resolvable ({audit['resolvable_pct']:.2f}%)"
        )
        for name, result in audit["identity_dimensions"].items():
            if result["missing"]:
                classes = ", ".join(
                    f"{key}={value}"
                    for key, value in result["classifications"].items()
                )
                print(f"  {name:<12} missing={result['missing']} ({classes})")
    combined = report["unique_corpus"]
    print(
        f"unique corpus: {combined['resolvable']}/{combined['claim_count']} "
        f"resolvable ({combined['resolvable_pct']:.2f}%)"
    )


def _audit_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit canonical identity coverage")
    parser.add_argument("claims", nargs="*", type=Path, help="E3 e3_claims.json files")
    parser.add_argument("--json-out", type=Path, help="write the complete classified audit")
    args = parser.parse_args(argv)

    paths = args.claims or sorted((ROOT / "pipeline_out" / "e3").glob("*/e3_claims.json"))
    if not paths:
        _audit_vault()
        return 0
    missing = [path for path in paths if not path.exists()]
    if missing:
        print(f"not found: {missing[0]}", file=sys.stderr)
        return 1

    report = audit_e3_files(paths)
    _print_audit(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


# ── Comparing values that carry a bound ───────────────────────────────────────

def _as_number(value: Any) -> float | None:
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def values_conflict(a: dict, b: dict, *, tolerance: float = 0.005) -> tuple[bool, str]:
    """Do two claims about the SAME identity actually disagree?

    Returns (conflict, reason). Identity is the caller's job — this only answers
    whether the numbers are incompatible once they are known to describe the same
    quantity.

    Recording a bound is pointless unless comparison honours it. "More than 600"
    and "640" agree; stored as two exact figures they read as a contradiction,
    and the case gains a conflict that does not exist. That failure is worse than
    missing a real one, because someone then spends an afternoon reconciling two
    statements that never disagreed.
    """
    x, y = _as_number(a.get("value")), _as_number(b.get("value"))
    if x is None or y is None:
        return False, "almeno un claim non porta un numero — nessun confronto possibile"

    bound_a = str(a.get("bound") or "EXACT").upper()
    bound_b = str(b.get("bound") or "EXACT").upper()
    scale = max(abs(x), abs(y), 1.0)

    if abs(x - y) <= tolerance * scale:
        return False, "stesso valore entro tolleranza"

    # A lower bound is satisfied by anything at or above it, and vice versa. Only
    # a figure on the wrong side of the bound is a real disagreement.
    def satisfies(bound: str, limit: float, other: float) -> bool | None:
        if bound == "AT_LEAST":
            return other >= limit
        if bound == "AT_MOST":
            return other <= limit
        if bound == "APPROXIMATE":
            return abs(other - limit) <= 0.10 * max(abs(limit), 1.0)
        return None

    for bound, limit, other, who in ((bound_a, x, y, "primo"), (bound_b, y, x, "secondo")):
        verdict = satisfies(bound, limit, other)
        if verdict is True:
            return False, f"il {who} claim è {bound} {limit:g}, e {other:g} lo soddisfa"
        if verdict is False:
            return True, f"il {who} claim è {bound} {limit:g}, ma {other:g} lo viola"

    return True, f"due valori esatti divergenti: {x:g} contro {y:g}"


if __name__ == "__main__":
    raise SystemExit(_audit_main())
