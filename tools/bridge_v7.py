#!/usr/bin/env python3
"""
V7 Bridge — connects extraction graph (graph.json) to execution graph
(execution_graph_v7.json) producing a unified Live Case bundle.

Architecture
------------
  extraction graph  → claims (raw facts, ordinal IDs)
  execution graph   → model nodes, formulas, solvers
  bridge            → Case Positions + support routes + position_model_directions
                      → Current graph (admitted, stable IDs)
                      → execution_mapping (runtime contract)
                      → adapter_report (coverage limits, identity map)

Identity strategy
-----------------
  Ordinal IDs (claim:0000) are NEVER used as persistent identifiers.
  Every claim gets a stable_id = "ks-" + sha256(metric+value+period+perimeter)[:12].
  The identity_migration_map documents the ordinal → stable mapping for this
  extraction so manifest, events and history always resolve the same object.

Separation of concerns
----------------------
  - bridge never modifies the raw extraction
  - Current graph is built by the bridge; never mutated by events
  - Events produce a Candidate; Candidate never becomes Current without human act
  - Approved is untouched
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

# ── Period normalisation ──────────────────────────────────────────────────────

_PERIOD_MAP: dict[str, str] = {
    # FY-style
    "FY2025A": "2025-12-31", "FY2025":  "2025-12-31",
    "FY2026E": "2026-12-31", "FY2026":  "2026-12-31",
    "FY2027E": "2027-12-31", "FY2027":  "2027-12-31",
    "FY2028E": "2028-12-31", "FY2028":  "2028-12-31",
    "FY2029E": "2029-12-31", "FY2030E": "2030-12-31",
    "FY2031E": "2031-12-31",
    "LTM":     "2025-12-31",
    # Underwriting anchor points
    "CLOSING": "2026-03-10", "OPENING": "2026-03-10",
    "Entry":   "2026-03-10", "ENTRY":   "2026-03-10",
    "Entry / later lender-defined": "2026-03-10",
    # Monitoring / post-close periods → ISO date in monitoring range
    "Post-close":         "2026-04-01",
    "Dec 2026":           "2026-12-31",
    "prior to Dec 2026":  "2026-11-30",
    # Historical / hold
    "since 2020":  "2020-01-01",
    "Hold period": "2031-03-31",  # exit horizon
}

# Sources whose claims are always monitoring (post-close, not underwriting)
_MONITORING_SOURCES: set[str] = {
    "Board Pack", "board pack",
    "Monitoring", "monitoring",
}

def _norm_period(raw: str) -> str:
    """Normalise period strings to ISO dates."""
    raw = (raw or "").strip()
    if raw in _PERIOD_MAP:
        return _PERIOD_MAP[raw]
    # Already ISO YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    # FY20XXA or FY20XXE → YYYY-12-31
    m = re.match(r"FY(\d{4})[AE]?$", raw, re.I)
    if m:
        return f"{m.group(1)}-12-31"
    # FY20XX–FY20YY range → take first year's fiscal year end (underwriting basis)
    m = re.match(r"FY(\d{4})[AE]?\s*[-–]\s*FY(\d{4})", raw, re.I)
    if m:
        return f"{m.group(1)}-12-31"
    # "Dec YYYY" → YYYY-12-31
    m = re.match(r"Dec\s+(\d{4})", raw, re.I)
    if m:
        return f"{m.group(1)}-12-31"
    return raw  # return as-is; will be flagged as coverage limit


def _is_iso(s: str) -> bool:
    return bool(s) and re.match(r"^\d{4}-\d{2}-\d{2}", s) is not None


# ── Metric → Case Position → Model Node map ───────────────────────────────────
#
# Three EBITDA objects are semantically distinct — do NOT merge them:
#   CP-EBITDA-FIRM  ($11.4m Firm Model)   → POSITION_DRIVES_MODEL (model input)
#   CP-COV-EBITDA   ($12.2m Covenant def) → POSITION_DRIVES_MODEL (leverage covenant)
#   CP-EBITDA-QOE   ($11.9m QoE view)     → MODEL_VALIDATES_POSITION (analytical ref)
#
# Because the extractor labels all five EBITDA claims with metric="EBITDA",
# we dispatch to the right CP by value (pragmatic until extractor v2 uses distinct labels).
# Known EBITDA value anchors for Keystone: 11.4 → FIRM, 12.2 → COV, all others → QOE.
_EBITDA_FIRM_VALUE = 11.4
_EBITDA_COV_VALUE  = 12.2

# (metric_pattern_lower) → (CP_ID, [MN_IDs], support_route_type)
# Order matters — more specific patterns must come before general ones.
_METRIC_TO_CP: list[tuple[str, str, list[str], str]] = [
    # Revenue — two semantically distinct objects
    ("recurring revenue",  "CP-RECURRING-REV",   [],                                      "MONITOR_ONLY"),
    ("revenue",            "CP-REVENUE",          ["MN-REVENUE"],                          "OR"),
    # EBITDA — explicit sub-types resolved by metric name; catch-all uses value dispatch
    ("covenant ebitda",    "CP-COV-EBITDA",       ["MN-COV-EBITDA"],                       "AND"),
    ("firm ebitda",        "CP-EBITDA-FIRM",      ["MN-FIRM-EBITDA", "MN-QUARTERLY-FIRM-EBITDA"], "AND"),
    ("normalized ebitda",  "CP-EBITDA-QOE",       [],                                      "MODEL_VALIDATES_POSITION"),
    ("ebitda margin",      "CP-EBITDA-MARGIN",    [],                                      "MONITOR_ONLY"),
    ("ebitda add-back",    "CP-EBITDA-ADJ",       [],                                      "MONITOR_ONLY"),
    ("ebitda adjustment",  "CP-EBITDA-ADJ",       [],                                      "MONITOR_ONLY"),
    # "ebitda" catch-all → dispatched by value inside _metric_to_cp
    # NWC — target (model input) ≠ adjustment (purchase price item)
    ("net working capital adjustment", "CP-NWC-ADJ",    [],            "MONITOR_ONLY"),
    ("net working capital target",     "CP-NWC-TARGET", ["MN-NWC"],    "AND"),
    ("net working capital",            "CP-NWC",        ["MN-NWC"],    "OR"),
    ("nwc",                            "CP-NWC",        ["MN-NWC"],    "OR"),
    # Structural / deal economics
    ("enterprise value",   "CP-EV",              ["MN-EV"],                               "OR"),
    ("entry multiple",     "CP-EV",              ["MN-EV"],                               "OR"),
    ("sponsor equity",     "CP-SPONSOR-EQUITY",  ["MN-SPONSOR-EQUITY"],                   "OR"),
    ("rollover",           "CP-ROLLOVER",         ["MN-ROLLOVER"],                         "OR"),
    ("term loan",          "CP-DEBT",            ["MN-DEBT"],                             "OR"),
    ("first-lien debt",    "CP-DEBT",            ["MN-DEBT"],                             "OR"),
    ("debt",               "CP-DEBT",            ["MN-DEBT"],                             "OR"),
    # Operational / qualitative
    ("customer concentration","CP-CONCENTRATION", ["MN-CONCENTRATION"],                   "OR"),
    ("concentration risk", "CP-CONCENTRATION",   ["MN-CONCENTRATION"],                   "OR"),
    ("concentration",      "CP-CONCENTRATION",   ["MN-CONCENTRATION"],                   "OR"),
    ("dso",                "CP-DSO",             ["MN-BASE-DSO"],                         "OR"),
    ("days sales",         "CP-DSO",             ["MN-BASE-DSO"],                         "OR"),
    ("wip",                "CP-WIP",             ["MN-BASE-WIP"],                         "OR"),
    # Integration risk — qualitative, tracked but no model node
    ("systems integration risk",  "CP-INTEGRATION-RISK", [], "MONITOR_ONLY"),
    ("systems integration",       "CP-INTEGRATION-RISK", [], "MONITOR_ONLY"),
    ("integration failure risk",  "CP-INTEGRATION-RISK", [], "MONITOR_ONLY"),
    ("acquisition integration",   "CP-INTEGRATION-RISK", [], "MONITOR_ONLY"),
    ("integration",               "CP-INTEGRATION-RISK", [], "MONITOR_ONLY"),
    # E3 v2 metrics — qualitative / operational, no direct model node
    ("headcount",          "CP-INTEGRATION-RISK", [],              "MONITOR_ONLY"),
    ("team tenure",        "CP-INTEGRATION-RISK", [],              "MONITOR_ONLY"),
    ("key person",         "CP-INTEGRATION-RISK", [],              "MONITOR_ONLY"),
    ("acquisition count",  "CP-INTEGRATION-RISK", [],              "MONITOR_ONLY"),
    ("gross margin",       "CP-EBITDA-QOE",       [],              "MODEL_VALIDATES_POSITION"),
    ("working capital",    "CP-NWC",              ["MN-NWC"],      "OR"),
    ("capex",              "CP-EBITDA-QOE",       [],              "MONITOR_ONLY"),
    ("exit multiple",      "CP-EV",               ["MN-EV"],       "OR"),
    ("exit ev",            "CP-EV",               ["MN-EV"],       "OR"),
    ("exit horizon",       "CP-STANDALONE-BASE-MOIC", ["MN-BASE-MOIC"], "MODEL_DERIVES_POSITION"),
    ("revolver",           "CP-DEBT",             ["MN-DEBT"],     "OR"),
    ("leverage",           "CP-DEBT",             ["MN-DEBT"],     "OR"),
    ("covenant threshold", "CP-DEBT",             ["MN-DEBT"],       "MONITOR_ONLY"),
    ("covenant ebitda",    "CP-COV-EBITDA",       ["MN-COV-EBITDA"], "AND"),
    ("seller rollover",    "CP-ROLLOVER",         ["MN-ROLLOVER"], "OR"),
    ("gross debt",         "CP-DEBT",             ["MN-DEBT"],     "OR"),
    ("first-lien",         "CP-DEBT",             ["MN-DEBT"],     "OR"),
    ("sponsor equity",     "CP-SPONSOR-EQUITY",   ["MN-SPONSOR-EQUITY"], "OR"),
    # Returns — each scenario is a distinct CP; value dispatch in _metric_to_cp
    # "gross moic"/"gross xirr" patterns → Base scenario (explicit extractor label)
    ("gross moic",  "CP-STANDALONE-BASE-MOIC", ["MN-BASE-MOIC"], "MODEL_DERIVES_POSITION"),
    ("gross xirr",  "CP-STANDALONE-BASE-IRR",  ["MN-BASE-IRR"],  "MODEL_DERIVES_POSITION"),
    # bare "moic" / "irr" → dispatched by value inside _metric_to_cp
    # Cash
    ("opening cash",       "CP-OPENING-CASH",    ["MN-OPENING-CASH"],                     "OR"),
    ("cash",               "CP-OPENING-CASH",    ["MN-OPENING-CASH"],                     "OR"),
]


# MOIC scenario dispatch: (value_anchor, cp_id, mn_id) — tolerance ±0.1
_MOIC_SCENARIOS: list[tuple[float, str, str]] = [
    (2.00, "CP-STANDALONE-BASE-MOIC",     "MN-BASE-MOIC"),
    (2.08, "CP-ACQUISITION-BASE-MOIC",    "MN-ACQ-MOIC"),
    (2.43, "CP-STANDALONE-UPSIDE-MOIC",   "MN-UP-MOIC"),
    (1.28, "CP-STANDALONE-DOWNSIDE-MOIC", "MN-DOWN-MOIC"),
]
# IRR scenario dispatch: (value_anchor, cp_id, mn_id) — tolerance ±0.5 ppt
_IRR_SCENARIOS: list[tuple[float, str, str]] = [
    (14.8, "CP-STANDALONE-BASE-IRR",      "MN-BASE-IRR"),
    (16.0, "CP-ACQUISITION-BASE-IRR",     "MN-ACQ-IRR"),
    (19.5, "CP-STANDALONE-UPSIDE-IRR",    "MN-UP-IRR"),
    (5.1,  "CP-STANDALONE-DOWNSIDE-IRR",  "MN-DOWN-IRR"),
]


def _metric_to_cp(metric: str, value: Any = None) -> tuple[str, list[str], str] | None:
    """Return (CP_ID, [MN_IDs], route_type) for a metric string, or None.

    Value dispatch for:
      bare 'ebitda': 11.4→FIRM, 12.2→COV, other→QOE
      'moic': dispatched by scenario value (±0.1 tolerance)
      'irr':  dispatched by scenario value (±0.5 ppt tolerance)
    """
    m = metric.lower().strip()

    # Value-dispatch for bare "ebitda" (extractor does not yet emit distinct labels)
    if m == "ebitda":
        v = _parse_float(value)
        if v is not None and abs(v - _EBITDA_FIRM_VALUE) < 0.05:
            return "CP-EBITDA-FIRM", ["MN-FIRM-EBITDA", "MN-QUARTERLY-FIRM-EBITDA"], "AND"
        if v is not None and abs(v - _EBITDA_COV_VALUE) < 0.05:
            return "CP-COV-EBITDA", ["MN-COV-EBITDA"], "AND"
        return "CP-EBITDA-QOE", [], "MODEL_VALIDATES_POSITION"

    # Value-dispatch for MOIC — each scenario is a distinct position
    if m == "moic":
        v = _parse_float(value)
        if v is not None:
            for anchor, cp_id, mn_id in _MOIC_SCENARIOS:
                if abs(v - anchor) <= 0.1:
                    return cp_id, [mn_id], "MODEL_DERIVES_POSITION"
        return "CP-STANDALONE-BASE-MOIC", ["MN-BASE-MOIC"], "MODEL_DERIVES_POSITION"

    # Value-dispatch for IRR — each scenario is a distinct position
    if m == "irr":
        v = _parse_float(value)
        if v is not None:
            for anchor, cp_id, mn_id in _IRR_SCENARIOS:
                if abs(v - anchor) <= 0.5:
                    return cp_id, [mn_id], "MODEL_DERIVES_POSITION"
        return "CP-STANDALONE-BASE-IRR", ["MN-BASE-IRR"], "MODEL_DERIVES_POSITION"

    for pat, cp_id, mn_ids, route_type in _METRIC_TO_CP:
        if pat in m:
            return cp_id, mn_ids, route_type
    return None


# ── Stable claim ID ───────────────────────────────────────────────────────────

def stable_claim_id(claim: dict) -> str:
    """
    Content-addressed stable ID — survives extraction reordering.
    Format: "ks-" + sha256(metric|value|period|perimeter)[:12]
    """
    key = "|".join([
        (claim.get("metric") or "").lower().strip(),
        str(claim.get("value") or ""),
        (claim.get("period") or "").strip(),
        (claim.get("perimeter") or "").strip(),
    ])
    return "ks-" + hashlib.sha256(key.encode()).hexdigest()[:12]


# ── Temporal class ────────────────────────────────────────────────────────────

_MONITORING_PERIODS = {
    "2026-12-31", "2027-03-31", "2027-06-30", "2027-09-30",
    "2027-12-31", "2028-03-31", "2026-04-01", "2026-11-30",
}
_UNDERWRITING_CUTOFF = "2026-03-10"

# known_at per source: date at which this source was available to the deal team
_SOURCE_KNOWN_AT: dict[str, str] = {
    "CIM":                    "2026-01-15T00:00:00Z",
    "Seller CIM":             "2026-01-15T00:00:00Z",
    "Data Room Extract":      "2026-02-01T00:00:00Z",
    "QoE Report":             "2026-02-20T00:00:00Z",
    "Firm Model Summary":     "2026-03-10T00:00:00Z",
    "Firm Initial Assessment":"2026-03-10T00:00:00Z",
    "IC Memo":                "2026-03-10T00:00:00Z",
    "Board Pack":             "2026-12-31T00:00:00Z",
}
_DEFAULT_KNOWN_AT_UNDERWRITING = "2026-03-10T00:00:00Z"
_DEFAULT_KNOWN_AT_MONITORING   = "2026-12-31T00:00:00Z"


def _known_at(claim: dict) -> str:
    """Derive known_at from source_doc."""
    src = (claim.get("source_doc") or claim.get("locator") or "").strip()
    for key, ts in _SOURCE_KNOWN_AT.items():
        if key.lower() in src.lower():
            return ts
    return _DEFAULT_KNOWN_AT_UNDERWRITING


def _temporal_class(claim: dict, period_iso: str) -> str:
    """
    Classify as 'underwriting' or 'monitoring'.
    Two signals — source and period — both gate admission.
    Board Pack source is always monitoring.
    Periods after the IC closing date are monitoring.
    """
    src = (claim.get("source_doc") or claim.get("locator") or "").lower()
    if any(ms.lower() in src for ms in _MONITORING_SOURCES):
        return "monitoring"
    if period_iso in _MONITORING_PERIODS:
        return "monitoring"
    # Exit-horizon projections (MOIC/IRR at "Hold period" → 2031) were KNOWN at IC date.
    # The period being future does NOT make them monitoring — classify by known_at.
    if period_iso == "2031-03-31":
        return "underwriting"
    if _is_iso(period_iso) and period_iso > _UNDERWRITING_CUTOFF:
        return "monitoring"
    return "underwriting"


# ── Claim enrichment ──────────────────────────────────────────────────────────

def _enrich_claims(extraction: dict) -> list[dict]:
    """
    Enrich each claim node with stable_id, period_iso, temporal_class,
    and epistemic_class (runtime field name).
    Returns list of enriched claim dicts.
    """
    nodes = {n["id"]: n for n in extraction.get("nodes", [])}
    edges = extraction.get("edges", [])

    # Build claim → metric/period lookup from edges
    claim_metric: dict[str, str] = {}
    claim_period: dict[str, str] = {}
    for e in edges:
        if e["rel"] == "MEASURES":
            nid = e["target"]
            if nid in nodes:
                claim_metric[e["source"]] = nodes[nid].get("label", "")
        if e["rel"] == "IN_PERIOD":
            nid = e["target"]
            if nid in nodes:
                claim_period[e["source"]] = nodes[nid].get("label", "")

    enriched = []
    for n in extraction.get("nodes", []):
        if n.get("type") != "claim":
            continue
        c = dict(n)
        # Pull metric/period from graph edges if not on node
        if not c.get("metric"):
            c["metric"] = claim_metric.get(n["id"], "")
        if not c.get("period"):
            c["period_raw"] = claim_period.get(n["id"], "")
        else:
            c["period_raw"] = c["period"]

        c["period_iso"] = _norm_period(c.get("period_raw") or c.get("period", ""))
        c["temporal_class"] = _temporal_class(c, c["period_iso"])
        c["known_at"] = _known_at(c)
        c["effective_date"] = c["period_iso"] if _is_iso(c["period_iso"]) else None
        c["stable_id"] = stable_claim_id(c)
        c["ordinal_id"] = n["id"]
        c["epistemic_class"] = c.get("epistemic", "asserted")
        enriched.append(c)
    return enriched


# ── Case Positions ────────────────────────────────────────────────────────────

def _build_case_positions(claims: list[dict]) -> dict[str, dict]:
    """
    Build CP-* nodes. Each CP consolidates all claims for one metric position.
    Multiple claims for the same CP become separate support routes (OR).
    """
    cp_claims: dict[str, list[dict]] = {}
    cp_meta: dict[str, dict] = {}

    for c in claims:
        metric = c.get("metric", "")
        result = _metric_to_cp(metric, c.get("value"))
        if not result:
            continue
        cp_id, mn_ids, route_type = result
        cp_claims.setdefault(cp_id, []).append(c)
        if cp_id not in cp_meta:
            cp_meta[cp_id] = {
                "cp_id": cp_id,
                "model_node_ids": mn_ids,
                "route_type": route_type,
            }
        else:
            # Merge MN IDs
            existing = set(cp_meta[cp_id]["model_node_ids"])
            for mn in mn_ids:
                if mn not in existing:
                    cp_meta[cp_id]["model_node_ids"].append(mn)

    case_positions: dict[str, dict] = {}
    for cp_id, meta in cp_meta.items():
        claims_for_cp = cp_claims[cp_id]
        # Pick the highest-confidence value:
        # attested > asserted; highest numeric value for EBITDA adjustments
        primary = _pick_primary(claims_for_cp)
        period_iso = primary.get("period_iso", "")

        support_routes = [
            {
                "route_id": f"SR-{cp_id}-{i:02d}",
                "claim_stable_id": c["stable_id"],
                "claim_ordinal_id": c["ordinal_id"],
                "source": c.get("source_doc", ""),
                "epistemic_class": c.get("epistemic_class", "asserted"),
                "route_type": meta["route_type"],
                "value": c.get("value"),
                "unit": c.get("unit", ""),
            }
            for i, c in enumerate(claims_for_cp)
        ]

        inst = _CP_INSTITUTIONAL.get(cp_id, {})
        case_positions[cp_id] = {
            "cp_id": cp_id,
            "metric": primary.get("metric", ""),
            "value": _parse_float(primary.get("value")),
            "value_raw": primary.get("value"),
            "unit": inst.get("unit") if inst.get("unit") is not None else primary.get("unit", ""),
            "epistemic_class": primary.get("epistemic_class", "asserted"),
            "period_iso": period_iso,
            "period_raw": primary.get("period_raw", ""),
            "effective_date": period_iso if _is_iso(period_iso) else None,
            "known_at": primary.get("known_at") or f"{_UNDERWRITING_CUTOFF}T00:00:00Z",
            "perimeter": inst.get("perimeter") or primary.get("perimeter") or "Alderstone standalone",
            "model_node_ids": meta["model_node_ids"],
            "route_type": meta["route_type"],
            "support_routes": support_routes,
            "bound": True,
        }

    return case_positions


def _pick_primary(claims: list[dict]) -> dict:
    """Pick the claim to use as the primary value for a CP."""
    # Prefer attested over asserted
    attested = [c for c in claims if c.get("epistemic_class") == "attested"]
    pool = attested if attested else claims
    # Among those, pick the one with a numeric value
    numeric = [c for c in pool if _parse_float(c.get("value")) is not None]
    return (numeric or pool)[0]


def _parse_float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ── Claim → Position edges ────────────────────────────────────────────────────

def _build_claim_position_edges(claims: list[dict],
                                 case_positions: dict[str, dict]) -> list[dict]:
    edges = []
    cp_by_metric: dict[str, str] = {}
    for cp_id, cp in case_positions.items():
        for route in cp["support_routes"]:
            cp_by_metric[route["claim_stable_id"]] = cp_id

    for c in claims:
        cp_id = cp_by_metric.get(c["stable_id"])
        if cp_id:
            edges.append({
                "rel": "SUPPORTS_ROUTE",
                "claim_stable_id": c["stable_id"],
                "claim_ordinal_id": c["ordinal_id"],
                "to_cp_id": cp_id,
            })
    return edges


# ── Position → Model Node directions ─────────────────────────────────────────

# Runtime direction semantics:
#   POSITION_DRIVES_MODEL  — the CP value is the primary input to the model node
#   MODEL_DERIVES_POSITION — model node is the compute source; CP is an output label
#   MODEL_VALIDATES_POSITION — model node result is checked against CP value
#   MONITOR_ONLY — traversal stops here; no executable propagation

_CP_DIRECTION: dict[str, str] = {
    # Model inputs (drive computation)
    "CP-REVENUE":          "POSITION_DRIVES_MODEL",
    "CP-EBITDA-FIRM":      "POSITION_DRIVES_MODEL",   # operative model input (11.4)
    "CP-COV-EBITDA":       "POSITION_DRIVES_MODEL",   # covenant leverage test (12.2)
    "CP-DEBT":             "POSITION_DRIVES_MODEL",
    "CP-SPONSOR-EQUITY":   "POSITION_DRIVES_MODEL",
    "CP-ROLLOVER":         "POSITION_DRIVES_MODEL",
    "CP-EV":               "POSITION_DRIVES_MODEL",
    "CP-NWC":              "POSITION_DRIVES_MODEL",
    "CP-NWC-TARGET":       "POSITION_DRIVES_MODEL",
    "CP-DSO":              "POSITION_DRIVES_MODEL",
    "CP-WIP":              "POSITION_DRIVES_MODEL",
    "CP-OPENING-CASH":     "POSITION_DRIVES_MODEL",
    "CP-CONCENTRATION":    "POSITION_DRIVES_MODEL",
    # Analytical references — model result is checked against these
    "CP-EBITDA-QOE":       "MODEL_VALIDATES_POSITION",  # QoE view (11.9); not a direct input
    # Returns — model derives; each scenario is a separate position
    "CP-STANDALONE-BASE-MOIC":     "MODEL_DERIVES_POSITION",
    "CP-STANDALONE-BASE-IRR":      "MODEL_DERIVES_POSITION",
    "CP-STANDALONE-DOWNSIDE-MOIC": "MODEL_DERIVES_POSITION",
    "CP-STANDALONE-DOWNSIDE-IRR":  "MODEL_DERIVES_POSITION",
    "CP-STANDALONE-UPSIDE-MOIC":   "MODEL_DERIVES_POSITION",
    "CP-STANDALONE-UPSIDE-IRR":    "MODEL_DERIVES_POSITION",
    "CP-ACQUISITION-BASE-MOIC":    "MODEL_DERIVES_POSITION",
    "CP-ACQUISITION-BASE-IRR":     "MODEL_DERIVES_POSITION",
    # Qualitative / monitoring — no executable propagation
    "CP-RECURRING-REV":    "MONITOR_ONLY",
    "CP-EBITDA-MARGIN":    "MONITOR_ONLY",
    "CP-EBITDA-ADJ":       "MONITOR_ONLY",
    "CP-NWC-ADJ":          "MONITOR_ONLY",
    "CP-INTEGRATION-RISK": "MONITOR_ONLY",
}


# ── Institutional perimeter + unit per CP (contract with the event layer) ────
# These values must match the mutations in event_ebitda_correction.json and
# any future PANTA events.  They define the SEMANTIC IDENTITY of each position
# (not the raw claim label), so they override the claim's perimeter/unit.
_CP_INSTITUTIONAL: dict[str, dict] = {
    "CP-EBITDA-FIRM":           {"perimeter": "Alderstone standalone, firm underwriting definition", "unit": "$m/year"},
    "CP-EBITDA-QOE":            {"perimeter": "Alderstone standalone, QoE definition",              "unit": "$m/year"},
    "CP-EBITDA-MARGIN":         {"perimeter": "Alderstone standalone",                              "unit": "%"},
    "CP-EBITDA-ADJ":            {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-COV-EBITDA":            {"perimeter": "Alderstone standalone, covenant definition",         "unit": "$m/year"},
    "CP-REVENUE":               {"perimeter": "Alderstone consolidated",                            "unit": "$m/year"},
    "CP-RECURRING-REV":         {"perimeter": "Alderstone consolidated",                            "unit": "%"},
    "CP-CONCENTRATION":         {"perimeter": "Alderstone consolidated",                            "unit": "%"},
    "CP-DSO":                   {"perimeter": "Alderstone standalone",                              "unit": "days"},
    "CP-WIP":                   {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-NWC":                   {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-NWC-TARGET":            {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-NWC-ADJ":               {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-DEBT":                  {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-EV":                    {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-SPONSOR-EQUITY":        {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-ROLLOVER":              {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-OPENING-CASH":          {"perimeter": "Alderstone standalone",                              "unit": "$m"},
    "CP-INTEGRATION-RISK":      {"perimeter": "Alderstone consolidated",                            "unit": ""},
    "CP-STANDALONE-BASE-MOIC":  {"perimeter": "Alderstone standalone",                              "unit": "x"},
    "CP-STANDALONE-BASE-IRR":   {"perimeter": "Alderstone standalone",                              "unit": "%"},
    "CP-STANDALONE-DOWNSIDE-MOIC": {"perimeter": "Alderstone standalone",                           "unit": "x"},
    "CP-STANDALONE-DOWNSIDE-IRR":  {"perimeter": "Alderstone standalone",                           "unit": "%"},
    "CP-STANDALONE-UPSIDE-MOIC":   {"perimeter": "Alderstone standalone",                           "unit": "x"},
    "CP-STANDALONE-UPSIDE-IRR":    {"perimeter": "Alderstone standalone",                           "unit": "%"},
    "CP-ACQUISITION-BASE-MOIC":    {"perimeter": "Alderstone standalone",                           "unit": "x"},
    "CP-ACQUISITION-BASE-IRR":     {"perimeter": "Alderstone standalone",                           "unit": "%"},
}

# Period override for nodes whose execution-graph period is a forecast range
# but whose semantic identity for event applicability is the opening snapshot date.
_MN_PERIOD_OVERRIDE: dict[str, str] = {
    "MN-QUARTERLY-FIRM-EBITDA": "2025-12-31",  # opening snapshot; event targets this date
}

# Quarterly model nodes: (annual_source_mn, divisor) — value = annual / divisor
_MN_QUARTERLY_DERIVE: dict[str, tuple[str, int]] = {
    "MN-QUARTERLY-FIRM-EBITDA": ("MN-FIRM-EBITDA", 4),
}

# Canonical time-frequency units for model nodes (overrides raw unit from claims)
_MN_UNIT_CANONICAL: dict[str, str] = {
    "MN-FIRM-EBITDA":            "$m/year",
    "MN-QUARTERLY-FIRM-EBITDA":  "$m/quarter",
    "MN-COV-EBITDA":             "$m/year",
    "MN-REVENUE":                "$m/year",
    "MN-FIRM-EBITDA-MARGIN":     "%",
    "MN-BASE-DSO":               "days",
    "MN-NWC":                    "$m",
    "MN-DEBT":                   "$m",
    "MN-EV":                     "$m",
    "MN-ROLLOVER":               "$m",
    "MN-SPONSOR-EQUITY":         "$m",
    "MN-CONCENTRATION":          "%",
    "MN-BASE-MOIC":              "x",
    "MN-BASE-IRR":               "%",
    "MN-DOWN-MOIC":              "x",
    "MN-DOWN-IRR":               "%",
    "MN-UP-MOIC":                "x",
    "MN-UP-IRR":                 "%",
}


def _build_position_model_directions(case_positions: dict[str, dict],
                                      execution: dict) -> list[dict]:
    model_nodes = execution.get("model_nodes", {})
    directions = []
    counter = 0
    for cp_id, cp in case_positions.items():
        direction = _CP_DIRECTION.get(cp_id, "POSITION_DRIVES_MODEL")
        for mn_id in cp["model_node_ids"]:
            mn = model_nodes.get(mn_id, {})
            if not mn:
                continue
            counter += 1
            directions.append({
                "binding_id": f"PMD-{counter:03d}",
                "position_id": cp_id,
                "model_node_id": mn_id,
                "direction": direction,
                "value": cp["value"],
                "unit": cp["unit"],
                "period_iso": cp["period_iso"],
                "epistemic_class": cp["epistemic_class"],
                "model_node_computational_form": mn.get("computational_form", ""),
            })
    return directions


# ── Schema-conformant helpers ─────────────────────────────────────────────────

_SOURCE_ID_MAP: dict[str, str] = {
    "2026-01-15": "CIM-2026-01-15",
    "2026-02-20": "QOE-REPORT-2026-02-20",
    "2026-03-10": "IC-MEMO-2026-03-10",
    "2026-12-31": "BOARD-PACK-2026-12-31",
}


def _normalize_claim_for_schema(c: dict) -> dict:
    """Return claim dict with all fields required by canonical_investment_case.schema.json."""
    known_at = c.get("known_at", "")
    date_part = known_at[:10] if known_at else ""
    source_id = _SOURCE_ID_MAP.get(date_part, f"SOURCE-{date_part}" if date_part else "UNKNOWN")
    period = c.get("period_iso") or c.get("period_raw") or "unknown"
    perimeter = c.get("perimeter") or "Alderstone standalone"
    out = {
        "claim_id": c.get("stable_id") or c.get("id", ""),
        "statement": c.get("statement", ""),
        "source_id": source_id,
        "locator": c.get("locator", ""),
        "epistemic_class": c.get("epistemic_class", "asserted"),
        "period": period,
        "perimeter": perimeter,
        "ground_truth_flag": c.get("epistemic_class") == "attested",
        "validation_only": False,
    }
    # Carry extra fields that downstream code may read
    for k, v in c.items():
        if k not in out:
            out[k] = v
    return out


_CP_IC_ATTRS: dict[str, tuple[str, str, str]] = {
    # (statement, epistemic_status_at_ic, decision_status_at_ic)
    "CP-REVENUE":
        ("The firm underwrites FY2025A standalone revenue at $74.0m.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-RECURRING-REV":
        ("The firm underwrites 72% of FY2025A revenue as recurring under long-term contracts.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-EBITDA-FIRM":
        ("The firm underwrites FY2025A EBITDA at $11.4m on a standalone, fully-loaded basis.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-EBITDA-QOE":
        ("QoE concluded FY2025A EBITDA at $11.9m; firm treats this as independent "
         "validation of the underwriting EBITDA.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-COV-EBITDA":
        ("Covenant EBITDA is $12.2m including contractual add-backs per the credit agreement.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-EBITDA-MARGIN":
        ("The firm underwrites FY2025A EBITDA margin at 17.2% on a standalone basis.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-EBITDA-ADJ":
        ("The firm accepts $0.5m in EBITDA add-backs as recurring and defensible.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-NWC-TARGET":
        ("The firm accepts a normalised NWC peg of $8.4m for completion accounts.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-NWC-ADJ":
        ("The NWC adjustment at close is expected to be $0.7m favourable to the buyer.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-CONCENTRATION":
        ("No single parent entity exceeds 15% of FY2025A revenue; "
         "step-down financing terms unconfirmed pending policy owner review.",
         "CONTESTED", "ACCEPTED_WITH_CONDITIONS"),
    "CP-INTEGRATION-RISK":
        ("Systems integration risk from the prior acquisition remains unresolved "
         "and requires active monitoring post-close.",
         "CONTESTED", "ACCEPTED_WITH_CONDITIONS"),
    "CP-EV":
        ("The firm underwrites entry enterprise value at $108.0m (9.5× FY2025A EBITDA).",
         "ESTABLISHED", "ACCEPTED"),
    "CP-SPONSOR-EQUITY":
        ("The firm commits $62.0m of sponsor equity at close.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-ROLLOVER":
        ("The seller rolls over $12.0m of equity into the new structure.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-DEBT":
        ("First-lien debt is sized at $42.8m, implying ~3.8× entry leverage on firm EBITDA.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-STANDALONE-BASE-MOIC":
        ("The firm underwrites a standalone base-case MOIC of 2.00× over the 5-year hold.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-STANDALONE-BASE-IRR":
        ("The firm underwrites a standalone base-case IRR of 14.8%.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-STANDALONE-DOWNSIDE-MOIC":
        ("The firm underwrites a standalone downside-case MOIC of 1.28×.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-STANDALONE-DOWNSIDE-IRR":
        ("The firm underwrites a standalone downside-case IRR of 5.1%.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-STANDALONE-UPSIDE-MOIC":
        ("The firm underwrites a standalone upside-case MOIC of 2.43×.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-STANDALONE-UPSIDE-IRR":
        ("The firm underwrites a standalone upside-case IRR of 19.5%.",
         "ESTABLISHED", "ACCEPTED"),
    "CP-ACQUISITION-BASE-IRR":
        ("The firm underwrites an acquisition base-case IRR of 16.0%.",
         "ESTABLISHED", "ACCEPTED"),
}


def _cp_ic_attrs(cp_id: str, cp: dict) -> tuple[str, str, str]:
    """Return (statement, epistemic_status_at_ic, decision_status_at_ic) for a CP."""
    if cp_id in _CP_IC_ATTRS:
        return _CP_IC_ATTRS[cp_id]
    metric = cp.get("metric", cp_id)
    value  = cp.get("value")
    unit   = cp.get("unit", "")
    stmt = f"The firm underwrites {metric} at {value} {unit}.".strip()
    return (stmt, "ESTABLISHED", "ACCEPTED")


# ── Current graph ─────────────────────────────────────────────────────────────

def _build_current_graph(
    admitted: list[dict],
    case_positions: dict[str, dict],
    cp_edges: list[dict],
    pm_directions: list[dict],
    execution: dict,
) -> dict:
    """
    Current graph in PANTA Live Case format.
    NEVER mutated by events — events produce a Candidate.

    case_positions is an ARRAY per PANTA spec; each item retains all
    internal fields (value, support_routes, …) so callers can still access
    them after rebuilding a dict: {p["position_id"]: p for p in …}.
    """
    model_nodes_raw = execution.get("model_nodes", {})

    def _mn_period(mn_id: str, fallback_period_iso: str | None = None) -> str:
        """Return period string for a model node (schema requires non-empty)."""
        if mn_id in _MN_PERIOD_OVERRIDE:
            return _MN_PERIOD_OVERRIDE[mn_id]
        raw = model_nodes_raw.get(mn_id, {})
        return (raw.get("period") or raw.get("effective_date")
                or fallback_period_iso or "OPENING")

    def _mn_perimeter(mn_id: str) -> str:
        raw = model_nodes_raw.get(mn_id, {})
        p = raw.get("perimeter") or "Alderstone standalone"
        return p.replace("_", " ")

    def _mn_name(mn_id: str) -> str:
        raw = model_nodes_raw.get(mn_id, {})
        return raw.get("label") or mn_id

    def _mn_kind(mn_id: str) -> str:
        raw = model_nodes_raw.get(mn_id, {})
        cf = raw.get("computational_form", "")
        return {
            "INPUT": "input", "DERIVED": "derived",
            "CONTROL": "control", "SCC_MEMBER": "cyclic",
            "SOLVER_OUTPUT": "inverse_solve",
        }.get(cf, "derived")

    # Build model node values list from CP bindings
    node_values: dict[str, dict] = {}
    for d in pm_directions:
        mn_id = d["model_node_id"]
        cp_id = d["position_id"]
        if mn_id not in node_values:
            mn = model_nodes_raw.get(mn_id, {})
            _val = d.get("value")
            node_values[mn_id] = {
                "model_node_id": mn_id,
                "name": _mn_name(mn_id),
                "kind": _mn_kind(mn_id),
                "period": _mn_period(mn_id, d.get("period_iso")),
                "perimeter": _mn_perimeter(mn_id),
                "value": _val,
                "initial_value": _val,   # PANTA event contract: mutations target initial_value
                "unit": _MN_UNIT_CANONICAL.get(mn_id) or d.get("unit"),
                "period_iso": d.get("period_iso"),
                "epistemic_class": d.get("epistemic_class"),
                "bound_from_cp": cp_id,
                "workbook_ref": mn.get("workbook_ref"),
                "computational_form": mn.get("computational_form"),
            }
        elif d.get("epistemic_class") == "attested":
            node_values[mn_id].update({
                "value": d.get("value"),
                "epistemic_class": d.get("epistemic_class"),
                "bound_from_cp": cp_id,
            })

    # Derive quarterly model node values from their annual sources
    for mn_id, (src_mn_id, divisor) in _MN_QUARTERLY_DERIVE.items():
        if mn_id in node_values and src_mn_id in node_values:
            annual_val = node_values[src_mn_id].get("value")
            if isinstance(annual_val, (int, float)) and annual_val is not None:
                derived = round(annual_val / divisor, 4)
                node_values[mn_id]["value"] = derived
                node_values[mn_id]["initial_value"] = derived

    # Add workbook-bound values for unbound INPUT nodes
    for mn_id, mn in model_nodes_raw.items():
        if mn_id not in node_values and mn.get("computational_form") == "INPUT" and mn.get("value_current") is not None:
            _wb_val = mn.get("value_current")
            node_values[mn_id] = {
                "model_node_id": mn_id,
                "name": _mn_name(mn_id),
                "kind": _mn_kind(mn_id),
                "period": _mn_period(mn_id),
                "perimeter": _mn_perimeter(mn_id),
                "value": _wb_val,
                "initial_value": _wb_val,
                "unit": _MN_UNIT_CANONICAL.get(mn_id) or mn.get("unit"),
                "period_iso": mn.get("effective_date"),
                "epistemic_class": mn.get("epistemic_class", "asserted"),
                "bound_from_cp": None,
                "workbook_ref": mn.get("workbook_ref"),
                "computational_form": mn.get("computational_form"),
                "source": "workbook_direct",
            }

    # PANTA Live Case format: case_positions as array
    cp_array = []
    for cp_id, cp in case_positions.items():
        stmt, ep_status, dec_status = _cp_ic_attrs(cp_id, cp)
        bound = cp.get("bound", False)
        item = {
            "position_id": cp_id,
            "statement": stmt,
            "epistemic_status_at_ic": ep_status,
            "decision_status_at_ic": dec_status,
            "freshness_status_at_ic": "CURRENT",
            "outcome_status_at_ic": "NOT_TESTED",
            "model_binding_status": "BOUND" if bound else "UNBOUND",
            "definition_id": f"DEF-{cp_id}",
            **{k: v for k, v in cp.items() if k != "cp_id"},
        }
        cp_array.append(item)

    # Claim–position edges: schema requires edge_id, claim_id, position_id,
    # relation_type ∈ {SUPPORTS, CONTRADICTS}
    panta_edges = [
        {
            "edge_id": f"CPE-{e['claim_stable_id'][:8]}-{e['to_cp_id']}",
            "claim_id": e["claim_stable_id"],
            "position_id": e["to_cp_id"],
            "relation_type": "SUPPORTS",
        }
        for e in cp_edges
    ]

    # Top-level support_routes collection (all routes, all CPs)
    all_support_routes = [
        route
        for cp in case_positions.values()
        for route in cp.get("support_routes", [])
    ]

    unbound_mn = [mn_id for mn_id in model_nodes_raw if mn_id not in node_values]

    # Normalize claims to schema-required shape (claim_id, source_id, period, …)
    schema_claims = [_normalize_claim_for_schema(c) for c in admitted]

    # Position-model bindings (one per direction entry)
    position_model_bindings = [
        {
            "binding_id": f"PMB-{d['position_id']}-{d['model_node_id']}",
            "position_id": d["position_id"],
            "model_node_id": d["model_node_id"],
            "binding_type": d.get("direction", "POSITION_DRIVES_MODEL"),
            "status": "ACTIVE",
        }
        for d in pm_directions
    ]

    return {
        "schema_version": "1.1.0",
        "case_id": "PROJECT-KEYSTONE",
        "state_id": "KS-CURRENT-V7-001",
        "company": "Alderstone",
        "state": "CURRENT",
        "canonical_as_of": f"{_UNDERWRITING_CUTOFF}T23:59:59Z",
        "extraction_ref": "graph.json",
        "execution_ref": "execution_graph_v7.json",
        "admitted_claim_count": len(admitted),
        "claims": schema_claims,
        "case_positions": cp_array,
        "model_nodes": list(node_values.values()),
        "position_dependencies": [],
        "claim_position_edges": panta_edges,
        "position_model_bindings": position_model_bindings,
        "support_routes": all_support_routes,
        "coverage_gaps": [],
        "position_model_directions": pm_directions,
        "artifacts": [],
        "history": [],
        "unbound_model_nodes": unbound_mn,
    }


# ── Execution mapping normalisation ───────────────────────────────────────────

# Rename internal computational_form tokens to PANTA runtime contract names
_FORM_MAP: dict[str, str] = {
    "INPUT":        "DIRECT_INPUT",
    "DERIVED":      "DIRECT_FORMULA",
    "CONTROL":      "MODEL_CONTROL",
    "SCC_MEMBER":   "NUMERICAL_CYCLE",
    "SOLVER_OUTPUT":"INVERSE_SOLVE",
}


def _normalize_execution_mapping(execution: dict,
                                  case_positions: dict[str, dict],
                                  pm_directions: list[dict],
                                  canonical_current_hash: str,
                                  extraction_hash: str = "",
                                  execution_file_hash: str = "") -> dict:
    """
    Convert execution_graph_v7.json to the runtime contract format conformant
    with state_transition_execution_mapping.schema.json:
    - model_nodes as LIST (not dict), model_node_id as identity
    - value_current transferred to initial_value
    - position_model_directions from bridge (already schema-conformant)
    - coverage_limits as {limit_id, reason_code, scope_ids} objects
    - canonical_graph_hash as sha256:<64 hex chars>
    """
    raw_nodes = execution.get("model_nodes", {})

    nodes_list = []
    node_coverage_limits: list[dict] = []
    limit_counter = 100  # start after compiler's own limits
    for mn_id, mn in raw_nodes.items():
        raw_form = mn.get("computational_form", "")
        node = {
            "model_node_id": mn_id,
            "label": mn.get("label", mn_id),
            "computational_form": _FORM_MAP.get(raw_form, raw_form),
            "unit": mn.get("unit"),
            "period": mn.get("period"),
            "effective_date": mn.get("effective_date"),
            "perimeter": mn.get("perimeter", "Alderstone standalone"),
            "epistemic_class": mn.get("epistemic_class"),
            "initial_value": mn.get("value_current"),
            "workbook_ref": mn.get("workbook_ref"),
            "formula_id": mn.get("formula_id"),
            "directed_deps": mn.get("directed_deps", []),
        }
        nodes_list.append(node)
        # Promote node-level coverage_limits to top-level with schema-conformant shape
        for lim in mn.get("coverage_limits", []):
            limit_counter += 1
            text = lim if isinstance(lim, str) else str(lim)
            node_coverage_limits.append({
                "limit_id": f"KS-BRIDGE-CL-{limit_counter:03d}",
                "reason_code": "MISSING_MODEL_DEPENDENCY",
                "scope_ids": [mn_id],
                "effect": text,
                "source": "bridge_v7._normalize_execution_mapping",
            })

    # Promote admission_manifest coverage_limits
    manifest_limits = execution.get("admission_manifest", {}).get("coverage_limits", [])
    manifest_limits_normalized: list[dict] = []
    for i, lim in enumerate(manifest_limits):
        if isinstance(lim, dict) and "limit_id" in lim:
            normalized = dict(lim)
            # Ensure schema-required fields: reason_code, scope_ids, effect
            if not normalized.get("reason_code"):
                normalized["reason_code"] = "COVERAGE_LIMIT_DECLARED"
            if not normalized.get("scope_ids"):
                normalized["scope_ids"] = lim.get("affected_nodes", [])
            if not normalized.get("effect"):
                normalized["effect"] = (
                    lim.get("description") or lim.get("resolution") or ""
                )
            manifest_limits_normalized.append(normalized)
        else:
            manifest_limits_normalized.append({
                "limit_id": f"KS-MANIFEST-CL-{i+1:03d}",
                "reason_code": "MISSING_MODEL_DEPENDENCY",
                "scope_ids": [],
                "effect": str(lim),
                "source": "admission_manifest",
            })

    # Fix model controls: ensure scope_ids present (copy from input_ids if needed)
    controls = []
    for ctrl in execution.get("model_controls", []):
        c = dict(ctrl)
        if not c.get("scope_ids"):
            c["scope_ids"] = list(c.get("input_ids") or [c.get("control_id", "")])
        if not c.get("resolution"):
            c["resolution"] = "REQUIRES_MANUAL_REVIEW"
        controls.append(c)

    # Add resolution to coverage limits
    all_limits = []
    for lim in node_coverage_limits + manifest_limits_normalized:
        l = dict(lim)
        if not l.get("resolution"):
            l["resolution"] = "PARTIAL_SETTLEMENT"
        all_limits.append(l)

    return {
        "mapping_version": "v7",
        "deal": "PROJECT-KEYSTONE",
        "company": "Alderstone",
        "canonical_graph_hash": f"sha256:{canonical_current_hash}",
        "provenance": {
            "extraction_hash": f"sha256:{extraction_hash}" if extraction_hash else None,
            "execution_graph_hash": f"sha256:{execution_file_hash}" if execution_file_hash else None,
            "canonical_current_hash": f"sha256:{canonical_current_hash}",
            "admission_manifest_hash": None,  # computed after manifest is built
        },
        "lbo_runtime_module": "tools/keystone_model.py",
        "lbo_runtime_entrypoint": "propagate_claim",
        "model_nodes": nodes_list,
        "directed_model_edges": execution.get("directed_model_edges", []),
        "position_model_directions": pm_directions,
        # Exclude workbook-reference formulas: the reference runtime's AST
        # evaluator only handles Python arithmetic expressions.  WORKBOOK_READ /
        # WORKBOOK_FUNCTION_CALL entries become MISSING_EXECUTABLE_FORMULA limits.
        "formulas": [
            f for f in execution.get("formulas", [])
            if f.get("evaluation_type") not in {"WORKBOOK_READ", "WORKBOOK_FUNCTION_CALL"}
        ],
        "rule_switches": execution.get("rule_switches", []),
        "cyclic_component_solver_configs": execution.get("cyclic_component_solver_configs", []),
        "inverse_solver_configs": execution.get("inverse_solver_configs", []),
        "model_controls": controls,
        "coverage_limits": all_limits,
    }


# ── Adapter report ────────────────────────────────────────────────────────────

def _build_adapter_report(
    all_claims: list[dict],
    admitted: list[dict],
    case_positions: dict[str, dict],
    execution: dict,
) -> dict:
    unbound = [c for c in admitted if not any(
        route["claim_stable_id"] == c["stable_id"]
        for cp in case_positions.values()
        for route in cp["support_routes"]
    )]
    monitoring = [c for c in all_claims if c["temporal_class"] == "monitoring"]

    mn_ids = set(execution.get("model_nodes", {}).keys())
    bound_mn = set()
    for cp in case_positions.values():
        for mn_id in cp["model_node_ids"]:
            if mn_id in mn_ids:
                bound_mn.add(mn_id)

    return {
        "adapter_version": "v7",
        "total_claims_in_extraction": len(all_claims),
        "admitted_count": len(admitted),
        "monitoring_excluded_count": len(monitoring),
        "unbound_claim_count": len(unbound),
        "case_positions_built": len(case_positions),
        "model_nodes_bound": len(bound_mn),
        "model_nodes_total": len(mn_ids),
        "identity_migration_map": {
            c["ordinal_id"]: c["stable_id"] for c in all_claims
        },
        "unbound_claims": [
            {"stable_id": c["stable_id"], "metric": c.get("metric"), "reason": "no CP mapping for metric"}
            for c in unbound
        ],
        "monitoring_excluded": [
            {"stable_id": c["stable_id"], "metric": c.get("metric"), "period": c.get("period_iso")}
            for c in monitoring
        ],
        "coverage_limits": [
            {
                "limit_id": f"KS-BRIDGE-UNBOUND-{cp['cp_id']}-{mn}",
                "reason_code": "MISSING_EXECUTABLE_DIRECTION",
                "scope_ids": [cp["cp_id"], mn],
                "effect": f"{cp['cp_id']} has no model node binding for {mn} in execution graph",
            }
            for cp in case_positions.values()
            for mn in cp["model_node_ids"]
            if mn not in mn_ids
        ],
        "validation_errors": [],
    }


# ── Manifest ──────────────────────────────────────────────────────────────────

def _build_manifest(
    admitted: list[dict],
    extraction_hash: str,
    execution_hash: str,
    status: str = "TEST",
) -> dict:
    return {
        "manifest_version": "1.0",
        "case_id": "PROJECT-KEYSTONE",
        "as_of_known_at": "2026-08-24T00:00:00Z",
        "source_graph_hash": f"sha256:{extraction_hash}",
        "execution_graph_hash": f"sha256:{execution_hash}",
        "mapping_version_ref": "v7",
        "policy_refs": {
            "materiality": "vault/policy/keystone_materiality_policy_v0.json",
            "authority":   "vault/policy/keystone_authority_matrix_v0.json",
        },
        "admitted_claim_ids": [c["stable_id"] for c in admitted],
        "admitted_claim_count": len(admitted),
        "status": status,
        "temporal_class_filter": "underwriting",
        "underwriting_cutoff": _UNDERWRITING_CUTOFF,
        "known_at_cutoff": f"{_UNDERWRITING_CUTOFF}T23:59:59Z",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compiler": "tools/bridge_v7.py",
    }


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_extraction(g: dict) -> list[str]:
    errors = []
    if "nodes" not in g:
        errors.append("extraction: missing 'nodes'")
    if "edges" not in g:
        errors.append("extraction: missing 'edges'")
    claims = [n for n in g.get("nodes", []) if n.get("type") == "claim"]
    if not claims:
        errors.append("extraction: no claim nodes found")
    return errors


def _validate_execution(e: dict) -> list[str]:
    errors = []
    for k in ["model_nodes", "directed_model_edges", "formulas",
              "rule_switches", "cyclic_component_solver_configs",
              "inverse_solver_configs", "model_controls"]:
        if not e.get(k):
            errors.append(f"execution: missing or empty '{k}'")
    return errors


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Main public API ───────────────────────────────────────────────────────────

def compile_v7_bundle(
    extraction_path: Path,
    execution_path: Path,
    status: str = "TEST",
) -> dict:
    """
    Build the V7 bundle from extraction + execution graphs.

    Returns
    -------
    dict with keys:
      current_graph       – admitted claims bound to model nodes
      execution_mapping   – runtime contract (normalised)
      adapter_report      – coverage limits + identity migration map
      manifest            – admission manifest with stable IDs
    """
    # 1. Load
    extraction = json.loads(extraction_path.read_text())
    execution  = json.loads(execution_path.read_text())

    # 2. Validate
    errs = _validate_extraction(extraction) + _validate_execution(execution)
    if errs:
        raise ValueError("Validation errors:\n" + "\n".join(errs))

    # 3. Hashes
    extraction_hash = _hash_file(extraction_path)
    execution_hash  = _hash_file(execution_path)

    # 4. Enrich claims with stable IDs + temporal class
    all_claims = _enrich_claims(extraction)

    # 5. Admit: underwriting only
    admitted = [c for c in all_claims if c["temporal_class"] == "underwriting"]

    # 6. Case Positions
    case_positions = _build_case_positions(admitted)

    # 7. Edges
    cp_edges      = _build_claim_position_edges(admitted, case_positions)
    pm_directions = _build_position_model_directions(case_positions, execution)

    # 8. Current graph (immutable, PANTA Live Case format)
    current_graph = _build_current_graph(
        admitted, case_positions, cp_edges, pm_directions, execution
    )

    # Canonical graph hash — hash the canonical Current graph JSON (P0.5)
    canonical_graph_hash = hashlib.sha256(
        json.dumps(current_graph, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    # 9. Execution mapping (normalised) — canonical hash references Current graph
    execution_mapping = _normalize_execution_mapping(
        execution, case_positions, pm_directions,
        canonical_current_hash=canonical_graph_hash,
        extraction_hash=extraction_hash,
        execution_file_hash=execution_hash,
    )

    # 10. Adapter report
    adapter_report = _build_adapter_report(
        all_claims, admitted, case_positions, execution
    )

    # 11. Manifest
    manifest = _build_manifest(admitted, extraction_hash, execution_hash, status)

    # Backfill manifest hash into execution_mapping provenance
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    execution_mapping["provenance"]["admission_manifest_hash"] = f"sha256:{manifest_hash}"

    return {
        "current_graph":    current_graph,
        "execution_mapping": execution_mapping,
        "adapter_report":   adapter_report,
        "manifest":         manifest,
        "_cp_dict":         case_positions,   # internal dict access for apply_event and tests
    }


# ── State Transition Engine ───────────────────────────────────────────────────

def apply_event(
    event: dict,
    bundle: dict,
    scenario: str = "standalone_base",
) -> dict:
    """
    Apply a claim-correction event to the Current graph and return a Candidate.

    The Current graph is NEVER modified. The Candidate contains:
      - the delta on the affected Case Position
      - the full model delta (via propagate_claim)
      - a deterministic replay_hash
      - current_unchanged = True
      - approved_unchanged = True

    Parameters
    ----------
    event   : the correction event (see event_ebitda_correction.json)
    bundle  : output of compile_v7_bundle()
    """
    from tools.keystone_model import propagate_claim, SB_EBITDA, PERIODS

    current = bundle["current_graph"]
    cp_dict = bundle.get("_cp_dict", {})
    event_id = event.get("event_id", "EV-UNKNOWN")
    stable_claim_id_event = event.get("stable_claim_id", "")

    # Locate the CP this event affects (use internal dict for O(1) access)
    affected_cp_id = None
    for cp_id, cp in cp_dict.items():
        for route in cp["support_routes"]:
            if route["claim_stable_id"] == stable_claim_id_event:
                affected_cp_id = cp_id
                break

    # Map event metric to propagate_claim parameters
    metric    = event.get("metric", "").lower().strip()
    new_value = float(event.get("to_value", 0))
    from_val  = event.get("from_value")
    period    = event.get("period", "2026-06-30")

    # Pass from_value so propagate_claim can compute ratio without mixing
    # annual and quarterly magnitudes (e.g., $11.4m annual ≠ $2.85m quarterly).
    claim_payload = {"metric": metric, "value": new_value, "period": period,
                     "from_value": from_val}
    result = propagate_claim(claim_payload, scenario=scenario)

    # Build CP delta
    cp_delta: dict[str, dict] = {}
    if affected_cp_id:
        cp = cp_dict.get(affected_cp_id, {})
        cp_delta[affected_cp_id] = {
            "old_value": cp.get("value"),
            "new_value": new_value,
            "delta": new_value - (cp.get("value") or 0),
            "unit": event.get("unit", cp.get("unit", "")),
        }

    # Build model node deltas from propagation result
    mn_deltas: dict[str, dict] = {}
    for node in result.get("updated_nodes", []):
        mn_id = node["node_id"].replace("mn:", "MN-").upper().replace("_", "-")
        mn_deltas[mn_id] = {
            "old": node["old"],
            "new": node["new"],
            "delta": node["delta"],
            "delta_pct": node.get("delta_pct"),
            "period": node.get("period"),
        }

    # Key financial outputs
    mn_deltas["MN-BASE-MOIC"] = {
        "old": result.get("moic_baseline"),
        "new": result.get("moic_updated"),
        "delta": result.get("moic_delta"),
        "period": "2031-03-31",
    }
    mn_deltas["MN-BASE-IRR"] = {
        "old": result.get("irr_baseline_pct"),
        "new": result.get("irr_updated_pct"),
        "delta": result.get("irr_delta_ppt"),
        "period": "2031-03-31",
        "unit": "ppt",
    }
    mn_deltas["MN-EXIT-EV"] = {
        "old": result.get("exit_ev_baseline"),
        "new": result.get("exit_ev_updated"),
        "delta": round((result.get("exit_ev_updated") or 0) - (result.get("exit_ev_baseline") or 0), 4),
        "period": "2031-03-31",
    }

    # Replay hash: deterministic over (event_id + new_value + period + MOIC + IRR)
    replay_content = json.dumps({
        "event_id": event_id,
        "metric": metric,
        "value": new_value,
        "period": period,
        "moic_updated": result.get("moic_updated"),
        "irr_updated_pct": result.get("irr_updated_pct"),
    }, sort_keys=True)
    replay_hash = "sha256:" + hashlib.sha256(replay_content.encode()).hexdigest()

    candidate = {
        "candidate_id": f"CAND-{event_id}",
        "base_state": "CURRENT",
        "base_case_id": "PROJECT-KEYSTONE",
        "event_id": event_id,
        "event_metric": metric,
        "event_period": period,
        "scenario": scenario,
        "claim_applied": result.get("claim_applied", False),
        "cp_delta": cp_delta,
        "model_node_deltas": mn_deltas,
        "covenant_alerts": result.get("covenant_alerts", []),
        "propagation_chain": [
            "claim EBITDA",
            "→ CP-FIRM-EBITDA",
            "→ MN-FIRM-EBITDA / MN-QUARTERLY-FIRM-EBITDA",
            "→ MN-NET-LEVERAGE (F-NET-LEVERAGE)",
            "→ MN-DEBT-CAPACITY",
            "→ MN-CHECK-SOURCES-USES → MN-SPONSOR-EQUITY",
            "→ SCC: MN-QUARTERLY-CFO ↔ MN-QUARTERLY-INTEREST ↔ MN-QUARTERLY-REVOLVER",
            "→ MN-EXIT-EV (exit_ltm_ebitda × exit_multiple)",
            "→ MN-EXIT-EQUITY (exit_ev - exit_net_debt)",
            "→ MN-BASE-MOIC / MN-BASE-IRR",
            "→ MN-SUPPORTED-PRICE (inverse solver)",
        ],
        "replay_hash": replay_hash,
        "current_unchanged": True,
        "approved_unchanged": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    return candidate


if __name__ == "__main__":
    import sys
    extraction_p = ROOT / "pipeline_out" / "keystone_qoe" / "graph.json"
    execution_p  = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"
    bundle = compile_v7_bundle(extraction_p, execution_p)
    print(f"admitted={bundle['manifest']['admitted_claim_count']}  "
          f"CPs={len(bundle['current_graph']['case_positions'])}  "
          f"pm_directions={len(bundle['current_graph']['position_model_directions'])}")
