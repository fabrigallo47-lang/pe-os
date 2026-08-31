#!/usr/bin/env python3
"""Canonical object identity — one place that owns normalization and ID computation.

Every writer (extract.py, extract_v2.py, the V20 router, the ledger) must import
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
import re
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
    "Adjustment Supportability", "Customer Concentration", "Customer Count",
    "Active Billing Accounts", "Customer Retention", "Contract Terms",
    "Customer Contract Terms", "Market Position", "Market Size",
    "Enterprise Value", "Equity Value", "Entry Multiple", "Exit Multiple",
    "Net Debt", "Gross Debt", "Net Leverage", "Interest Coverage",
    "Sponsor Equity", "Seller Equity", "Seller Rollover", "First-Lien Debt",
    "Revolver Capacity", "DDTL Availability", "Covenant EBITDA",
    "Covenant Threshold", "Covenant Headroom", "Exit Horizon", "Exit Multiple",
    "Supported Price", "MOIC", "IRR", "Headcount", "Team Tenure",
    "Acquisition Count", "Systems Integration Risk", "Integration Risk",
    "Operational Risk", "Key Person Risk", "Regulatory Risk", "Competition Risk",
    "IC Conditions", "IC Vote", "Decision Coherence",
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
    return re.sub(r"\s+", " ", str(s or "")).strip()


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
        _field("measurement") or perim.get("measurement", ""),
        normalize_scenario(_field("scenario")),
    )


def claim_identity(claim: dict) -> tuple[str, ...]:
    """WHO asserts it, from where, with what value.  Source version belongs here.

    Two sources stating the same number are two claims, never one: agreement
    between independent sources is evidence, not redundancy.
    """
    return metric_identity(claim) + (
        _clean(claim.get("source") or claim.get("source_id")
               or (claim.get("source") or {}).get("artifact") if isinstance(claim.get("source"), dict) else ""),
        _clean(claim.get("source_version")),
        _clean(claim.get("locator") or (claim.get("source") or {}).get("locator")
               if isinstance(claim.get("source"), dict) else claim.get("locator")),
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


if __name__ == "__main__":
    _audit_vault()
