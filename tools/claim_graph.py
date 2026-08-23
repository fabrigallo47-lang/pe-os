#!/usr/bin/env python3
"""Convert extracted claims to a typed semantic knowledge graph — V5.

V1 node types
-------------
subject   — unique entity being described (ui_hidden=True — index only)
claim     — individual extracted fact
question  — underwriting question (formed in Pass 5.5 from claim landscape)
topic     — macro area grouping (ui_hidden=True — grouping only)

V2 additional node types
------------------------
model_node          — quantitative financial model node
case_position       — institutional conclusion (adopted position)
support_route       — evidence bundle linking claims to a case_position
artifact            — output artefact (model, memo, lender pack, gate)
decision            — institutional decision record
rule_switch         — conditional branch
solver_config       — cyclic/inverse solver config
model_control       — accounting / covenant invariant
policy              — materiality policy / authority matrix ref (ui_hidden=True)
role                — preparer / reviewer / authority / escalation (ui_hidden=True)
institutional_state — Current + Approved + history + K_t (ui_hidden=True)

V2 structural edges
--------------------
SUPPORTS_ROUTE        claim → support_route
ROUTE_FOR_POSITION    support_route → case_position
BINDS_TO              case_position → model_node  (carries binding_direction)
PRODUCES              model_node → artifact / decision
REQUIRES_SOLVER       model_node → solver_config
HAS_CONTROL           model_node → model_control
GOVERNED_BY           case_position → policy
ASSIGNED_TO           case_position → role
SUPPORTS              claim → case_position  (direct; canonical=True — shared with Pass 2c quant→qual)
CONTRADICTS           claim → case_position  (blocked claim; canonical=True — shared with Pass 2a value conflict)
BEARS_ON              claim → question
ANSWERS_TO            question → model_node
CHALLENGES_QUESTION   claim → question  (counterevidence)

DERIVES_FROM direction: derived claim points FROM its sources (source → derived).
SUPERSEDES: version replacement only — same metric/period/perimeter, later as_of.
REFINES / TRACKS: informational; tagged canonical=False; not traversed by engine.
"""
from __future__ import annotations
import hashlib as _hashlib
import json as _json
import re

# ── Macro area taxonomy ──────────────────────────────────────────────────────
_AREA_RULES: list[tuple[str, str]] = [
    ("revenue",          "Revenue"),    ("recurring",     "Revenue"),
    ("backlog",          "Revenue"),    ("pipeline",      "Revenue"),
    ("billing",          "Revenue"),
    ("ebitda",           "Earnings"),   ("earnings",      "Earnings"),
    ("margin",           "Earnings"),   ("adjustment",    "Earnings"),
    ("normaliz",         "Earnings"),   ("qoe",           "Earnings"),
    ("customer",         "Customer"),   ("concentration", "Customer"),
    ("churn",            "Customer"),   ("retention",     "Customer"),
    ("contract",         "Customer"),   ("account",       "Customer"),
    ("market",           "Market"),     ("position",      "Market"),
    ("regulatory",       "Market"),     ("competitive",   "Market"),
    ("technology",       "Market"),
    ("operations",       "Operations"), ("operational",   "Operations"),
    ("integration",      "Operations"), ("systems",       "Operations"),
    ("working capital",  "Operations"), ("wip",           "Operations"),
    ("utilization",      "Operations"), ("headcount",     "Operations"),
    ("debt",             "Structure"),  ("leverage",      "Structure"),
    ("covenant",         "Structure"),  ("capital structure", "Structure"),
    ("loan",             "Structure"),  ("revolver",      "Structure"),
    ("lien",             "Structure"),
    ("governance",       "Governance"), ("management",    "Governance"),
    ("board",            "Governance"), ("incentive",     "Governance"),
    ("exit",             "Returns"),    ("returns",       "Returns"),
    ("moic",             "Returns"),    ("irr",           "Returns"),
    ("xirr",             "Returns"),    ("multiple",      "Returns"),
    ("acquisition",      "Returns"),
]

AREA_COLORS: dict[str, str] = {
    "Revenue":    "#0d2236", "Earnings":   "#0d2218",
    "Customer":   "#2a1010", "Market":     "#1a0d2a",
    "Operations": "#2a1d0d", "Structure":  "#0d1a2a",
    "Governance": "#1a2a0d", "Returns":    "#2a180d",
    "Other":      "#161b22",
}
AREA_BORDER_COLORS: dict[str, str] = {
    "Revenue":    "#1e4d7a", "Earnings":   "#1e5c30",
    "Customer":   "#5c2020", "Market":     "#3d1a6e",
    "Operations": "#6e4a1a", "Structure":  "#1a4a6e",
    "Governance": "#4a6e1a", "Returns":    "#6e3a1a",
    "Other":      "#30363d",
}


def _topic_to_area(topic: str) -> str:
    t = (topic or "").lower()
    for kw, area in _AREA_RULES:
        if kw in t:
            return area
    return "Other"


def _metrics_conflict(m1: str, m2: str) -> bool:
    if not m1 or not m2:
        return False
    if m1 == m2:
        return True
    s, l = sorted([m1, m2], key=len)
    if len(s) < 0.6 * len(l):
        return False
    return s in l


def _parse_num(v: object) -> float | None:
    if not v:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(v))
    try:
        f = float(s)
        return f if -1e12 < f < 1e12 else None
    except ValueError:
        return None


_TRUST: dict[str, int] = {
    "attested": 3, "observed": 2, "derived": 2, "asserted": 1,
}

# ── Unit normalization ────────────────────────────────────────────────────────
# Maps claim units to canonical deal-currency units.
# Applied in Pass 1 when deal_currency is known.
_UNIT_ALIASES: dict[str, str] = {
    "£m":   "$m",  "€m":   "$m",
    "$mm":  "$m",  "mm":   "$m",
    "£bn":  "$bn", "€bn":  "$bn",
    "£":    "$",   "€":    "$",
}


def _normalize_unit(u: str, deal_currency: str = "USD") -> str:
    """Normalize unit string to deal currency. £m → $m for USD deals."""
    u = (u or "").strip()
    if deal_currency == "USD":
        normalized = _UNIT_ALIASES.get(u)
        if normalized:
            return normalized
        u_lower = u.lower()
        for alias, target in _UNIT_ALIASES.items():
            if u_lower == alias.lower():
                return target
    return u


# ── V2: Node type constants ───────────────────────────────────────────────────
NT_MODEL_NODE    = "model_node"
NT_CASE_POSITION = "case_position"
NT_SUPPORT_ROUTE = "support_route"
NT_ARTIFACT      = "artifact"
NT_DECISION      = "decision"
NT_RULE_SWITCH   = "rule_switch"
NT_SOLVER        = "solver_config"
NT_CONTROL       = "model_control"
NT_POLICY        = "policy"
NT_ROLE          = "role"
NT_INST_STATE    = "institutional_state"

# V2 edge types
ET_SUPPORTS_ROUTE      = "SUPPORTS_ROUTE"
ET_ROUTE_FOR_POSITION  = "ROUTE_FOR_POSITION"
ET_BINDS_TO            = "BINDS_TO"
ET_PRODUCES            = "PRODUCES"
ET_REQUIRES_SOLVER     = "REQUIRES_SOLVER"
ET_HAS_CONTROL         = "HAS_CONTROL"
ET_GOVERNED_BY         = "GOVERNED_BY"
ET_ASSIGNED_TO         = "ASSIGNED_TO"
ET_BEARS_ON            = "BEARS_ON"             # claim → question
ET_ANSWERS_TO          = "ANSWERS_TO"           # question → model_node
ET_CHALLENGES_QUESTION = "CHALLENGES_QUESTION"  # counterevidence → question

# ── V2: Model node registry ──────────────────────────────────────────────────
# (id, label, unit, keywords, binding_direction)
_V2_MODEL_NODES: list[tuple[str, str, str, list[str], str]] = [
    ("MN-EBITDA",          "Firm EBITDA",         "$m",
     ["ebitda"],                                                    "POSITION_DRIVES_MODEL"),
    ("MN-REVENUE",         "Revenue",             "$m",
     ["revenue", "recurring revenue"],                             "POSITION_DRIVES_MODEL"),
    ("MN-LEVERAGE",        "Leverage",            "x",
     ["leverage", "net leverage", "debt/ebitda", "net debt/ebitda",
      "leverage ratio", "leverage multiple", "turns"],
     "MODEL_DERIVES_POSITION"),
    ("MN-DEBT-CAP",        "Debt Capacity",       "$m",
     ["debt capacity", "borrowing", "lending capacity",
      "first-lien", "term loan", "senior debt", "opening debt", "debt facility",
      "senior secured", "debt quantum", "net debt", "economic net debt",
      "revolver balance", "revolver outstanding", "revolver drawn",
      "amortization", "debt amortization"],
     "MODEL_DERIVES_POSITION"),
    ("MN-SOURCES-USES",    "Sources & Uses",      "$m",
     ["sources", "uses", "rollover", "transaction structure",
      "transaction funding", "deal structure", "total consideration"],
     "MODEL_VALIDATES_POSITION"),
    ("MN-EQUITY",          "Sponsor Equity",      "$m",
     ["equity", "sponsor"],                                         "MODEL_DERIVES_POSITION"),
    ("MN-CASHFLOW",        "Cash Flow",           "$m",
     ["cash flow", "free cash", "fcf", "cash generation", "cash profit",
      "unlevered free", "levered free",
      "cash from operations", "operating cash", "cash operations",
      "cash from investing", "cash from financing"],
     "MODEL_DERIVES_POSITION"),
    ("MN-INTEREST",        "Interest & Revolver", "$m",
     ["interest expense", "interest cost", "interest charge",
      "cash interest", "pik", "debt service cost", "financing cost",
      "term loan spread", "revolver spread", "loan spread", "credit spread",
      "sofr spread", "base rate spread", "interest deduction"],
     "MODEL_DERIVES_POSITION"),
    ("MN-MOIC",            "MOIC",                "x",
     ["moic"],                                                      "MODEL_DERIVES_POSITION"),
    ("MN-IRR",             "IRR",                 "%",
     ["irr"],                                                       "MODEL_DERIVES_POSITION"),
]

# ── V2: Hygiene noise patterns (non-PE content filter) ───────────────────────
_HYGIENE_NOISE: list[str] = [
    "mnist", "fashion-mnist", "fashion mnist",
    "neural network", "convolutional", "training accuracy",
    "test accuracy", "validation loss", "validation accuracy",
    "epoch", "batch size", "learning rate",
    "machine learning", "deep learning", "image classification",
    "gradient boost", "random forest", "xgboost",
    "sklearn", "pytorch", "tensorflow",
    "f1 score", "precision recall", "roc auc",
    "dataset", "data augmentation", "overfitting",
    "summary-2", "summary_2",
]

# ── V2: Standard artifacts ───────────────────────────────────────────────────
_STANDARD_ARTIFACTS: list[tuple[str, str, str]] = [
    ("art:model",       "Financial Model",   "model"),
    ("art:memo",        "IC Memo",           "memo"),
    ("art:lender-pack", "Lender Pack",       "lender_pack"),
    ("art:gate",        "Gate Decision",     "gate"),
]

# ── V2: Standard roles ───────────────────────────────────────────────────────
_STANDARD_ROLES: list[tuple[str, str, str]] = [
    ("role:preparer",    "Preparer",              "preparer"),
    ("role:reviewer",    "Professional Reviewer", "reviewer"),
    ("role:authority",   "Authority Holder",       "authority_holder"),
    ("role:escalation",  "Escalation Holder",      "escalation_holder"),
]

# ── V2: Structural stubs (cannot be inferred from claims) ────────────────────
_STRUCTURAL_STUBS: list[tuple[str, str, str, str]] = [
    # (id, label, type, missing_note)
    ("stub:inst-state", "Institutional State (Current + Approved + K_t)",
     NT_INST_STATE,
     "Needs: current_value, approved_value, append_only_history, K_t per output"),
    ("stub:policy",     "Materiality Policy + Authority Matrix",
     NT_POLICY,
     "Needs: version/hash of materiality_policy, authority_matrix, execution_mapping"),
    ("stub:rule-sw",    "Rule Switches",
     NT_RULE_SWITCH,
     "Needs: condition, true_branch, false_branch, versioned source for each switch"),
    ("stub:cyc-solver", "Cyclic Numerical Solver",
     NT_SOLVER,
     "Needs: variables, equations, method, init, limits, tolerance, max_iter, uniqueness"),
    ("stub:controls",   "Model Controls & Invariants",
     NT_CONTROL,
     "Needs: S&U balance, cash/revolver coherence, debt/interest, covenant, unit/perimeter"),
]

# ── Claim scoring markers (module-level, used by _claim_score) ────────────────
_ADJUSTMENT_MARKERS: tuple[str, ...] = (
    "adjustment", "correction", "cut-off", "cutoff",
    "reserve", "normaliz", "add-back", "addback",
    "organic growth", "revenue growth", "cagr", "growth rate",
    "yoy growth", "ytd growth",
    "deduction cap", "deduction limit", "tax deduction", "163(j)",
    "tax rate", "tax assumption",
)

_EXIT_PROJECTION_MARKERS: tuple[str, ...] = (
    "exit ltm", "exit ebitda", "exit revenue", "exit lm",
    "exit net debt", "exit economic net debt", "exit equity",
    "standalone base case", "standalone downside", "standalone upside",
    "acquisition case",
    "projected at", "is projected", "projected to be",
    "projects alderstone exit", "projects exit",
    "hold period", "investment hold",
    "at march 31, 203", "fy203",
)

_SOURCE_PRIORITY: dict[str, int] = {
    "firm model summary":      4,
    "firm initial assessment": 3,
    "ic memo":                 2,
    "qoe report":              1,
    "data room":               0,
    "cim":                    -5,
}

_MONITORING_SOURCES: tuple[str, ...] = (
    "board pack", "board update",
    "monitoring report", "monitoring",
    "compliance report", "compliance certificate",
    "waiver notice", "waiver",
    "lender report", "lender certificate",
    "management accounts", "management report",
    "quarterly update", "monthly update",
)

# ── V5: Semantic identity — definition markers ────────────────────────────────
# Used in Pass 1 to tag each claim with a definition dimension.
# "firm" = the fund's underwriting view; "covenant" = credit-agreement EBITDA;
# "qoe" = Quality-of-Earnings adjusted figure; "seller" = management / seller view.
_DEFINITION_MARKERS: dict[str, list[str]] = {
    "firm":     ["firm ebitda", "firm's view", "firm-underwritten", "firm underwritten",
                 "firm initial assessment", "firm model", "firm model summary",
                 "opening ebitda", "entry ebitda", "ic memo", "underwriting"],
    "covenant": ["covenant ebitda", "covenant", "credit agreement", "lender",
                 "maintenance covenant", "springing covenant"],
    "qoe":      ["qoe", "quality of earnings", "quality-of-earnings", "qoe report",
                 "qoe ebitda", "adjusted ebitda"],
    "seller":   ["seller", "management", "mgmt", "company provided", "cim",
                 "seller view", "management view"],
}


def _extract_definition(metric: str, stmt: str, source: str) -> str:
    combined = (metric + " " + stmt + " " + source).lower()
    for defn, markers in _DEFINITION_MARKERS.items():
        if any(m in combined for m in markers):
            return defn
    return ""


# ── V5: Semantic identity — scenario markers ──────────────────────────────────
_SCENARIO_MARKERS: dict[str, list[str]] = {
    # acquisition_base must be checked BEFORE standalone_base:
    # "Acquisition Base case" contains "base case" — if standalone_base fires first it wins.
    "acquisition_base":    ["acquisition base", "acquisition case", "with acquisition",
                            "with m&a", "m&a case"],
    "standalone_base":     ["standalone base", "standalone base case", "base scenario"],
    "standalone_downside": ["standalone downside", "downside case", "downside scenario",
                            "stress", "stressed"],
    "standalone_upside":   ["standalone upside", "upside case", "upside scenario"],
}


def _extract_scenario(metric: str, stmt: str) -> str:
    combined = (metric + " " + stmt).lower()
    for scen, markers in _SCENARIO_MARKERS.items():
        if any(m in combined for m in markers):
            return scen
    return ""


# ── V5: Computational forms per model node ────────────────────────────────────
# Replaces binding_direction as the computational characterization in execution_mapping.
_COMPUTATIONAL_FORMS: dict[str, str] = {
    "MN-EBITDA":       "DIRECT_INPUT",
    "MN-REVENUE":      "DIRECT_INPUT",
    "MN-LEVERAGE":     "DIRECT_FORMULA",
    "MN-DEBT-CAP":     "DIRECT_FORMULA",
    "MN-SOURCES-USES": "MODEL_CONTROL",
    "MN-EQUITY":       "DIRECT_FORMULA",
    "MN-CASHFLOW":     "NUMERICAL_CYCLE",
    "MN-INTEREST":     "NUMERICAL_CYCLE",
    "MN-MOIC":         "DIRECT_FORMULA",
    "MN-IRR":          "DIRECT_FORMULA",
}

# ── V5: Qualitative case positions (not model-node-bound) ─────────────────────
# Each entry: (id_suffix, label, trigger_area, keywords)
# These represent fund beliefs that are often qualitative and do not map 1:1 to
# a model node. Support routes are logic-level, not per-period.
_QUALITATIVE_POSITIONS: list[tuple[str, str, str, list[str]]] = [
    (
        "QL-CUSTOMER-CONCENTRATION",
        "Customer Concentration Risk",
        "Customer",
        ["customer concentration", "customer durability", "customer retention",
         "customer run-rate", "customer durability", "customer mix"],
    ),
    (
        "QL-INTEGRATION-RISK",
        "Integration & Operational Risk",
        "Operations",
        ["integration risk", "operational risk", "integration execution",
         "process integration", "operational fragmentation",
         "integration and operational", "integration program"],
    ),
    (
        "QL-NWC",
        "Net Working Capital",
        "Operations",
        ["net working capital", "working capital", "nwc", "working capital gap",
         "working capital risk", "nwc target"],
    ),
    (
        "QL-MANAGEMENT-QUALITY",
        "Management Capability",
        "Governance",
        ["management capability", "management quality", "management execution",
         "management capability risk", "management capable"],
    ),
]

# ── Question formation: one question per model node ──────────────────────────
# Each entry: mn_id → (question_text, question_type_slug)
_MN_QUESTION_TEMPLATES: dict[str, tuple[str, str]] = {
    "MN-EBITDA": (
        "What is the firm's view of sustainable EBITDA at entry, and which adjustments are accepted?",
        "qt-ebitda-basis",
    ),
    "MN-REVENUE": (
        "What is the quality, recurrence, and sustainability of the revenue base?",
        "qt-revenue-quality",
    ),
    "MN-LEVERAGE": (
        "What opening leverage is being underwritten, and is it consistent with the EBITDA basis?",
        "qt-leverage-opening",
    ),
    "MN-DEBT-CAP": (
        "Is the debt structure sized to support the investment thesis under stress?",
        "qt-debt-capacity",
    ),
    "MN-SOURCES-USES": (
        "Does the transaction structure balance, with all sources and uses accounted for?",
        "qt-transaction-structure",
    ),
    "MN-EQUITY": (
        "What sponsor equity is committed, and is the equity cushion sufficient at entry?",
        "qt-equity-cushion",
    ),
    "MN-CASHFLOW": (
        "Can the business generate sufficient free cash flow to service debt and support the exit case?",
        "qt-free-cash-flow",
    ),
    "MN-INTEREST": (
        "What is the all-in cost of debt, and does the business have adequate interest coverage?",
        "qt-interest-coverage",
    ),
    "MN-MOIC": (
        "What gross MOIC does the base case project, and which assumptions drive it most?",
        "qt-moic-construction",
    ),
    "MN-IRR": (
        "What is the projected gross IRR, and how does it hold under downside assumptions?",
        "qt-irr-sensitivity",
    ),
}

# Cross-cutting questions triggered by claim-area presence.
# Each entry: (question_text, question_type_slug, trigger_area)
_CROSS_CUTTING_QUESTIONS: list[tuple[str, str, str]] = [
    (
        "What is the customer concentration risk, and how durable is the revenue base?",
        "qt-customer-concentration", "Customer",
    ),
    (
        "What integration and operational risks are material to the investment thesis?",
        "qt-integration-risk", "Operations",
    ),
    (
        "Is management capable of executing the operational plan and any M&A strategy?",
        "qt-management-quality", "Governance",
    ),
    (
        "What is the competitive and regulatory positioning of the business?",
        "qt-market-position", "Market",
    ),
]


# ── Core builder ─────────────────────────────────────────────────────────────

def claims_to_graph(
    claims: list[dict],
    source_name: str = "",
    deal: str = "",
    deal_currency: str = "USD",
) -> dict:
    """Build a V3 typed semantic graph from extracted claims.

    Args:
        claims:        raw extracted claim dicts
        source_name:   fallback source label if claim.source_doc is missing
        deal:          deal slug for provenance
        deal_currency: ISO currency code for unit normalization (default USD)

    Returns:
        nodes            — all node dicts (V1 + V2 types)
        edges            — all edge dicts (V1 + V2 types)
        area_colors      — visualization palette
        area_border_colors
        execution_mapping — structured execution envelope
        coverage_report  — per-item coverage_status breakdown
        stats            — node/edge counts + hygiene flags
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def _upsert(nid: str, **kw) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, **kw}

    def _edge(src: str, tgt: str, rel: str, **kw) -> None:
        edges.append({"source": src, "target": tgt, "rel": rel, **kw})

    # ── Pass 0: Input hygiene — flag and filter non-deal claims ──────────────
    hygiene_flags: list[str] = []
    clean_claims: list[dict] = []
    for i, c in enumerate(claims):
        combined = " ".join([
            str(c.get("subject", "")), str(c.get("metric", "")),
            str(c.get("statement", "")), str(c.get("source_doc", "")),
        ]).lower()
        is_noise = any(pat in combined for pat in _HYGIENE_NOISE)
        if is_noise:
            hygiene_flags.append(
                f"claim[{i}] excluded — non-PE content detected "
                f"(subject={c.get('subject','')!r}, metric={c.get('metric','')!r})"
            )
        else:
            clean_claims.append(c)
    claims = clean_claims

    # ── Pass 1: V1 — subject / claim / topic nodes ────────────────────────────
    # Unit normalization applied here: £m → $m for USD deals.
    # Subject and topic nodes are ui_hidden — index/grouping use only.
    claim_ids: list[str | None] = []

    for i, c in enumerate(claims):
        subject = (c.get("subject") or "").strip()
        if not subject:
            claim_ids.append(None)
            continue

        s_id = f"subj:{subject}"
        _upsert(s_id, type="subject", label=subject,
                coverage_status="mapped", ui_hidden=True)

        c_id = f"claim:{i:03d}"
        claim_ids.append(c_id)

        metric = c.get("metric", "")
        topic  = c.get("topic", "")
        # Use topic if set by extractor; fall back to metric for area classification
        # so cross-cutting questions trigger even when topic field is empty.
        area   = _topic_to_area(topic or metric)
        label  = f"{metric or subject} = {c['value']}" if c.get("value") else (metric or subject)

        src_doc_raw   = c.get("source_doc", source_name)
        src_doc_lower = (src_doc_raw or "").lower()
        temporal_class = (
            "monitoring"
            if any(w in src_doc_lower for w in _MONITORING_SOURCES)
            else "entry"
        )

        # Normalize unit to deal currency
        raw_unit = c.get("unit", "")
        unit     = _normalize_unit(raw_unit, deal_currency)

        stmt_raw = c.get("statement", "")
        definition = _extract_definition(metric, stmt_raw, src_doc_raw)
        scenario   = _extract_scenario(metric, stmt_raw)

        _upsert(
            c_id,
            type="claim", label=label,
            metric=metric, unit=unit,
            as_of=c.get("as_of", ""), topic=topic, area=area,
            source_doc=src_doc_raw,
            epistemic=c.get("epistemic", "asserted"),
            value=c.get("value", ""),
            period=c.get("period", ""),
            perimeter=c.get("perimeter", ""),
            direction=c.get("direction", "context"),
            locator=c.get("locator", ""),
            author=c.get("author", ""),
            statement=stmt_raw,
            derivation=c.get("derivation"),
            temporal_class=temporal_class,
            definition=definition,
            scenario=scenario,
            coverage_status="mapped",
        )

        _edge(s_id, c_id, "HAS_CLAIM")

        # Topic nodes: ui_hidden — not traversed by engine, grouping only.
        # Suppress topic:Other entirely (no useful grouping signal).
        if area != "Other":
            t_id = f"topic:{area}"
            _upsert(t_id, type="topic", label=area, area=area,
                    coverage_status="mapped", ui_hidden=True)
            _edge(c_id, t_id, "IN_AREA")

        for q in (c.get("bears_on") or []):
            q = (q or "").strip()
            if not q:
                continue
            q_id = f"q:{q}"
            _upsert(q_id, type="question", label=q, coverage_status="mapped",
                    formation_basis="extractor_bears_on")
            _edge(c_id, q_id, ET_BEARS_ON)

    # ── Pass 2a: V1 semantic edges — CONTRADICTS (applicability-gated) ────────
    # CONTRADICTS is emitted only when two claims:
    #   (a) are about the same subject and conflicting metric, and
    #   (b) one is direction="supports", the other direction="contradicts", and
    #   (c) they share compatible period AND compatible perimeter.
    # Different periods or perimeters = different applicability domains → not a contradiction.
    #
    # SUPERSEDES: removed from this loop. Version-based SUPERSEDES is handled
    # in Pass 2d using as_of dates, not trust levels.

    by_subject: dict[str, list[tuple[str, str, str]]] = {}
    for nid, node in nodes.items():
        if node["type"] != "claim":
            continue
        for e in edges:
            if e["rel"] == "HAS_CLAIM" and e["target"] == nid:
                metric = (node.get("metric") or node.get("subject") or "").lower().strip()
                by_subject.setdefault(e["source"], []).append(
                    (nid, node.get("direction", "context"), metric))
                break

    seen_dir: set[tuple[str, str, str]] = set()

    def _add_dir(src: str, tgt: str, rel: str) -> None:
        key = (src, tgt, rel)
        if key not in seen_dir:
            seen_dir.add(key)
            _edge(src, tgt, rel)

    for _, clist in by_subject.items():
        supports_l    = [(c, m) for c, d, m in clist if d == "supports"]
        contradicts_l = [(c, m) for c, d, m in clist if d == "contradicts"]
        for s_cid, s_met in supports_l:
            for c_cid, c_met in contradicts_l:
                if not _metrics_conflict(s_met, c_met):
                    continue
                # Applicability gate: check period compatibility
                s_node = nodes.get(s_cid, {})
                c_node = nodes.get(c_cid, {})
                s_per    = (s_node.get("period")    or "").strip()
                c_per    = (c_node.get("period")    or "").strip()
                s_perim  = (s_node.get("perimeter") or "").strip()
                c_perim  = (c_node.get("perimeter") or "").strip()
                # Different non-empty periods = different domains, not contradiction
                if s_per and c_per and s_per != c_per:
                    continue
                # Different non-empty perimeters = different scopes, not contradiction
                if s_perim and c_perim and s_perim != c_perim:
                    continue
                _add_dir(s_cid, c_cid, "CONTRADICTS")

    # ── Pass 2b: V1 pair-wise semantic edges — TRACKS / REFINES / CHALLENGES ──
    n = len(claims)
    bears_index: dict[str, list[int]] = {}
    for i, c in enumerate(claims):
        for q in (c.get("bears_on") or []):
            q = (q or "").strip()
            if q:
                bears_index.setdefault(q, []).append(i)

    seen_sem: set[tuple[str, str, str]] = set()

    def _add_sem(src: str, tgt: str, rel: str, **kw) -> None:
        key = (src, tgt, rel)
        if key not in seen_sem:
            seen_sem.add(key)
            _edge(src, tgt, rel, **kw)

    for i in range(n):
        a    = claims[i]
        a_id = claim_ids[i]
        if not a_id:
            continue
        m_a   = (a.get("metric") or a.get("subject") or "").lower().strip()
        p_a   = (a.get("period") or a.get("as_of") or "").strip()
        per_a = (a.get("perimeter") or "").strip()
        ep_a  = a.get("epistemic", "asserted")
        s_a   = (a.get("subject") or "").lower().strip()

        for j in range(i + 1, n):
            b    = claims[j]
            b_id = claim_ids[j]
            if not b_id:
                continue
            m_b   = (b.get("metric") or b.get("subject") or "").lower().strip()
            p_b   = (b.get("period") or b.get("as_of") or "").strip()
            per_b = (b.get("perimeter") or "").strip()
            ep_b  = b.get("epistemic", "asserted")
            s_b   = (b.get("subject") or "").lower().strip()

            same_subj = bool(s_a and s_b and (s_a == s_b or s_a in s_b or s_b in s_a))
            same_met  = bool(m_a and m_b and len(m_a) >= 4 and len(m_b) >= 4 and
                             (m_a == m_b or m_a in m_b or m_b in m_a))

            if same_subj and same_met:
                if p_a and p_b and p_a != p_b:
                    # Different periods: same thing measured at different times
                    _add_sem(a_id, b_id, "TRACKS", canonical=False,
                             adapter_note="informational_v1_not_traversed_by_engine",
                             adapter_version="v1.0")
                elif per_a and per_b and per_a != per_b:
                    # Different perimeters: different scopes of the same metric
                    _add_sem(a_id, b_id, "REFINES", canonical=False,
                             adapter_note="informational_v1_not_traversed_by_engine",
                             adapter_version="v1.0")
                else:
                    # Same period, same perimeter: genuine value conflict if values differ
                    t_a, t_b = _TRUST.get(ep_a, 1), _TRUST.get(ep_b, 1)
                    if t_a != t_b:
                        v_a = _parse_num(a.get("value"))
                        v_b = _parse_num(b.get("value"))
                        if v_a is not None and v_b is not None:
                            denom = max(abs(v_a), abs(v_b), 1e-9)
                            if abs(v_a - v_b) / denom > 0.05:
                                if t_a > t_b:
                                    _add_sem(a_id, b_id, "CHALLENGES")
                                else:
                                    _add_sem(b_id, a_id, "CHALLENGES")

    # ── Pass 2c: CORROBORATES / DERIVES_FROM / SUPPORTS ──────────────────────
    # CORROBORATES: two supporting claims from different sources on the same question
    for q, idxs in bears_index.items():
        supporters = [idx for idx in idxs
                      if claims[idx].get("direction") == "supports" and claim_ids[idx]]
        for ii in range(len(supporters)):
            for jj in range(ii + 1, len(supporters)):
                ia, ib = supporters[ii], supporters[jj]
                src_a  = (claims[ia].get("source_doc") or "").strip()
                src_b  = (claims[ib].get("source_doc") or "").strip()
                if src_a != src_b:
                    _add_sem(claim_ids[ia], claim_ids[ib], "CORROBORATES")

    # DERIVES_FROM: derived claim → the claims it was computed from
    for i, c in enumerate(claims):
        a_id = claim_ids[i]
        if not a_id or c.get("epistemic") != "derived":
            continue
        deriv = (c.get("derivation") or "").lower()
        if len(deriv) < 5:
            continue
        for j, b in enumerate(claims):
            if i == j:
                continue
            b_id = claim_ids[j]
            if not b_id:
                continue
            m_b = (b.get("metric") or b.get("subject") or "").lower().strip()
            if m_b and len(m_b) >= 5 and m_b in deriv:
                _add_sem(a_id, b_id, "DERIVES_FROM")

    # SUPPORTS: quantitative claim supports a qualitative narrative on same subject+area
    for i in range(n):
        a    = claims[i]
        a_id = claim_ids[i]
        if not a_id or (a.get("value") or "").strip():
            continue
        s_a    = (a.get("subject") or "").lower().strip()
        area_a = _topic_to_area(a.get("topic") or "")
        if not s_a or area_a == "Other":
            continue
        for j in range(n):
            if i == j:
                continue
            b    = claims[j]
            b_id = claim_ids[j]
            if not b_id or not (b.get("value") or "").strip():
                continue
            s_b    = (b.get("subject") or "").lower().strip()
            area_b = _topic_to_area(b.get("topic") or "")
            if (s_a and s_b and (s_a == s_b or s_a in s_b or s_b in s_a)
                    and area_a == area_b):
                _add_sem(b_id, a_id, "SUPPORTS")

    # ── Pass 2d: Version-based SUPERSEDES ─────────────────────────────────────
    # SUPERSEDES is only emitted when:
    #   - same metric, same period, same perimeter (same object)
    #   - later as_of date (genuine version replacement)
    # NOT emitted based on trust level — a stronger source does not supersede a weaker one.
    for i in range(n):
        a    = claims[i]
        a_id = claim_ids[i]
        if not a_id:
            continue
        a_as_of = (a.get("as_of") or "").strip()
        if not a_as_of:
            continue
        m_a   = (a.get("metric") or a.get("subject") or "").lower().strip()
        p_a   = (a.get("period")    or "").strip()
        per_a = (a.get("perimeter") or "").strip()

        for j in range(i + 1, n):
            b    = claims[j]
            b_id = claim_ids[j]
            if not b_id:
                continue
            b_as_of = (b.get("as_of") or "").strip()
            if not b_as_of or a_as_of == b_as_of:
                continue
            m_b   = (b.get("metric") or b.get("subject") or "").lower().strip()
            p_b   = (b.get("period")    or "").strip()
            per_b = (b.get("perimeter") or "").strip()

            # Must be same object: same metric, same period, same perimeter
            if not _metrics_conflict(m_a, m_b):
                continue
            if p_a != p_b:
                continue    # different periods = different objects
            if per_a and per_b and per_a != per_b:
                continue    # different perimeters = different objects

            # Emit SUPERSEDES from the later-dated claim to the earlier
            if b_as_of > a_as_of:
                _add_sem(b_id, a_id, "SUPERSEDES")
            else:
                _add_sem(a_id, b_id, "SUPERSEDES")

    # ── Pass 3: V2 — model_node stubs (always present) ───────────────────────
    mn_claim_map: dict[str, list[str]] = {}

    for mn_id, mn_label, mn_unit, keywords, binding_dir in _V2_MODEL_NODES:
        nid = f"mn:{mn_id}"
        _upsert(nid,
                type=NT_MODEL_NODE, label=mn_label, mn_id=mn_id,
                unit=mn_unit, coverage_status="missing",
                computational_form=binding_dir,
                formula=None, formula_ref=None,
                period=None, perimeter=None,
                directed_deps=[],
                note="Formula and formula_ref must be populated from the workbook")
        mn_claim_map[mn_id] = []

    for i, c in enumerate(claims):
        c_id = claim_ids[i]
        if not c_id:
            continue
        metric_lower = (c.get("metric") or "").lower()
        for mn_id, _, _, keywords, binding_dir in _V2_MODEL_NODES:
            if any(kw in metric_lower for kw in keywords):
                mn_claim_map[mn_id].append(c_id)

    for mn_id, _, _, _, _ in _V2_MODEL_NODES:
        nid = f"mn:{mn_id}"
        n_claims = len(mn_claim_map[mn_id])
        if n_claims > 0:
            nodes[nid]["coverage_status"] = "partial"
            nodes[nid]["bound_claim_count"] = n_claims

    # ── Pass 4: V2 — case_position nodes ─────────────────────────────────────
    cp_to_claims: dict[str, list[str]] = {}

    def _claim_score(cid: str, binding_dir: str = "", mn_unit: str = "",
                     mn_id: str = "") -> int:
        node = nodes.get(cid, {})
        metric_lower = (node.get("metric") or "").lower()
        stmt_lower   = (node.get("statement") or "").lower()
        if node.get("temporal_class") == "monitoring":
            return -9999
        if any(w in metric_lower for w in _ADJUSTMENT_MARKERS):
            return -999
        if binding_dir == "POSITION_DRIVES_MODEL":
            combined = metric_lower + " " + stmt_lower
            if any(w in combined for w in _EXIT_PROJECTION_MARKERS):
                return -800
        claim_unit = (node.get("unit") or "").strip().lower()
        if mn_unit == "$m" and claim_unit in ("%", "percent", "pct", "% of ebitda"):
            return -700
        # V5: exit projection penalty for entry-quantity nodes.
        # Debt capacity, equity, leverage, and S&U positions represent entry values.
        # Exit projections (standalone base case, projected at, exit net debt, …)
        # must not displace entry figures for these nodes.
        _ENTRY_QUANTITY_NODES = frozenset(
            {"MN-DEBT-CAP", "MN-EQUITY", "MN-LEVERAGE", "MN-SOURCES-USES"}
        )
        if mn_id in _ENTRY_QUANTITY_NODES:
            combined_ep = metric_lower + " " + stmt_lower
            if any(w in combined_ep for w in _EXIT_PROJECTION_MARKERS):
                return -800
        # V5: definition-aware penalty — non-primary definitions don't compete for
        # the primary position. Firm EBITDA slot is for "firm" definition only;
        # covenant/qoe/seller EBITDA are secondary views.
        defn = node.get("definition", "")
        if mn_id == "MN-EBITDA" and defn and defn != "firm":
            return -600
        # V5: scenario penalty — primary positions are standalone_base.
        # Equity entry position must not be the acquisition-case figure.
        scen = node.get("scenario", "")
        if mn_id in ("MN-MOIC", "MN-IRR", "MN-EQUITY") and scen and scen != "standalone_base":
            return -400
        trust       = _TRUST.get(node.get("epistemic", "asserted"), 1)
        has_val     = 20 if node.get("value") else 0
        has_per     = 1 if node.get("period") else 0
        val         = _parse_num(node.get("value"))
        value_bonus = 2 if (val is not None and abs(val) > 0.5) else 0
        source_lower = (node.get("source_doc") or "").lower()
        source_bonus = max(
            (v for k, v in _SOURCE_PRIORITY.items() if k in source_lower),
            default=0,
        )
        base_bonus = (
            3 if ("base case" in stmt_lower
                  and "downside" not in stmt_lower
                  and "upside" not in stmt_lower)
            else 0
        )
        return trust * 10 + has_val + has_per + value_bonus + source_bonus + base_bonus

    def _same_context(cid1: str, cid2: str) -> bool:
        """V5: CONTESTED only when runner-up shares same definition AND same scenario."""
        n1, n2 = nodes.get(cid1, {}), nodes.get(cid2, {})
        return (n1.get("definition", "") == n2.get("definition", "")
                and n1.get("scenario", "") == n2.get("scenario", ""))

    for mn_id, mn_label, mn_unit, keywords, binding_dir in _V2_MODEL_NODES:
        matching = mn_claim_map[mn_id]
        if not matching:
            continue

        scored: list[tuple[str, int]] = sorted(
            ((c, _claim_score(c, binding_dir, mn_unit, mn_id)) for c in matching),
            key=lambda x: -x[1],
        )
        best_cid, best_score = scored[0]

        if best_score <= -500:
            continue

        best_node = nodes[best_cid]

        is_contested = (
            len(scored) >= 2
            and scored[1][1] > -500
            and (best_score - scored[1][1]) <= 3
            and _same_context(scored[0][0], scored[1][0])
        )

        candidates_info = [
            {
                "claim_id":      cid,
                "score":         sc,
                "value":         nodes[cid].get("value", ""),
                "unit":          nodes[cid].get("unit", ""),
                "source_doc":    nodes[cid].get("source_doc", ""),
                "epistemic":     nodes[cid].get("epistemic", ""),
                "temporal_class": nodes[cid].get("temporal_class", "entry"),
                "statement":     nodes[cid].get("statement", "")[:120],
            }
            for cid, sc in scored[:4]
            if sc > -9999
        ]

        cp_id       = f"cp:{mn_id.lower()}"
        stmt        = best_node.get("statement", f"Case position on {mn_label}")
        value       = best_node.get("value", "")
        period      = best_node.get("period", best_node.get("as_of", ""))
        perimeter   = best_node.get("perimeter", "")
        unit_actual = best_node.get("unit") or mn_unit

        _upsert(
            cp_id,
            type=NT_CASE_POSITION, label=f"{mn_label} Position",
            mn_id=mn_id, binding_direction=binding_dir,
            statement=stmt, value=value, unit=unit_actual,
            period=period, perimeter=perimeter,
            decision_status="CONTESTED" if is_contested else "PENDING",
            coverage_status="partial",
            candidates=candidates_info,
            note=(
                "HUMAN REVIEW REQUIRED — multiple candidates within 3-point scoring threshold"
                if is_contested else
                f"Inferred from {len(matching)} claim(s); "
                f"requires human adoption to become ACCEPTED"
            ),
        )
        cp_to_claims[cp_id] = matching

        mn_nid = f"mn:{mn_id}"
        if mn_nid in nodes:
            nodes[mn_nid]["unit"] = unit_actual

        if binding_dir == "MODEL_DERIVES_POSITION":
            _edge(mn_nid, cp_id, ET_BINDS_TO, binding_direction=binding_dir)
        else:
            _edge(cp_id, mn_nid, ET_BINDS_TO, binding_direction=binding_dir)

    # ── Pass 4.5: Direct claim → case_position edges ─────────────────────────
    # SUPPORTS: claim supports the case position (not blocked).
    # CONTRADICTS: claim is blocked from the position (score ≤ -500) but still bound.
    # Edge type names are shared with Pass 2c (SUPPORTS) and Pass 2a (CONTRADICTS);
    # the runtime distinguishes by target node type (case_position vs claim).
    for cp_id, supporting_cids in cp_to_claims.items():
        cp_node       = nodes[cp_id]
        bd            = cp_node.get("binding_direction", "")
        mn_id_local   = cp_node.get("mn_id", "")
        mn_unit_local = nodes.get(f"mn:{mn_id_local}", {}).get("unit", "")
        winner_id     = (
            cp_node.get("candidates", [{}])[0].get("claim_id")
            if cp_node.get("candidates") else None
        )
        for cid in supporting_cids:
            sc = _claim_score(cid, bd, mn_unit_local, mn_id_local)
            if sc <= -500:
                _edge(cid, cp_id, "CONTRADICTS", score=sc, canonical=True)
            else:
                _edge(cid, cp_id, "SUPPORTS",
                      score=sc, is_selected=(cid == winner_id), canonical=True)

    # ── Pass 4.8: Qualitative case positions (not model-node-bound) ─────────────
    # Fund beliefs that are inherently qualitative — customer concentration,
    # integration risk, NWC, management quality. Not every position comes from a
    # model node; support routes represent the logic, not a per-period quantity.
    for ql_suffix, ql_label, ql_area, ql_keywords in _QUALITATIVE_POSITIONS:
        ql_matching: list[str] = []
        for qi, qc in enumerate(claims):
            qc_id = claim_ids[qi]
            if not qc_id:
                continue
            combined_ql = (
                (qc.get("metric") or "") + " " +
                (qc.get("statement") or "") + " " +
                (qc.get("subject") or "")
            ).lower()
            if any(kw in combined_ql for kw in ql_keywords):
                ql_matching.append(qc_id)
        if not ql_matching:
            continue

        ql_cp_id = f"cp:{ql_suffix.lower()}"
        _upsert(
            ql_cp_id,
            type=NT_CASE_POSITION,
            label=ql_label,
            mn_id=None,
            is_qualitative=True,
            area=ql_area,
            binding_direction="QUALITATIVE",
            statement=(
                f"Fund position on {ql_label.lower()} — "
                "requires human articulation of thesis"
            ),
            value=None, unit=None, period=None, perimeter=None,
            decision_status="OPEN",
            coverage_status="partial",
            candidates=[],
            note=(
                f"Qualitative position: {len(ql_matching)} supporting claim(s). "
                "No model node binding. Requires human articulation."
            ),
        )
        cp_to_claims[ql_cp_id] = ql_matching

        # Direct claim → qualitative position edges
        for cid in ql_matching:
            sc = _claim_score(cid)
            if sc > -500:
                _edge(cid, ql_cp_id, "SUPPORTS", score=sc, canonical=True)

    # ── Pass 5: V2 — support_routes (per-period grouping) ────────────────────
    for cp_id, supporting_cids in cp_to_claims.items():
        cp_label = nodes[cp_id]["label"]

        period_groups: dict[str, list[str]] = {}
        for cid in supporting_cids:
            per = (nodes[cid].get("period") or nodes[cid].get("as_of") or "").strip()
            period_groups.setdefault(per, []).append(cid)

        for period_key, group_cids in period_groups.items():
            safe_per = re.sub(r"[^A-Za-z0-9_-]", "-", period_key)[:24] if period_key else "unperioded"
            sr_id = f"sr:{cp_id[3:]}-{safe_per}"

            has_addbacks = any(
                any(w in (nodes[c].get("metric") or "").lower()
                    for w in ("addback", "adjustment", "add-back"))
                for c in group_cids
            )
            if has_addbacks and len(group_cids) > 1:
                logic = "FORMULA"
            elif len(group_cids) == 1:
                logic = "INDEPENDENT"
            else:
                logic = "AND"

            _upsert(
                sr_id,
                type=NT_SUPPORT_ROUTE,
                label=f"Route → {cp_label} [{period_key or 'unperioded'}]",
                logic=logic,
                member_count=len(group_cids),
                period=period_key,
                coverage_status="partial",
                note=f"logic={logic}; {len(group_cids)} member(s); period={period_key!r}",
            )
            for cid in group_cids:
                _edge(cid, sr_id, ET_SUPPORTS_ROUTE)
            _edge(sr_id, cp_id, ET_ROUTE_FOR_POSITION)

    # ── Pass 5.5: Question formation ─────────────────────────────────────────
    # Deterministic — no LLM call. One question per model node, plus cross-cutting
    # questions triggered by claim-area presence.
    # Evidence = claims bound to the model node.
    # Counterevidence = claims that CHALLENGE those evidence claims.

    # Build CHALLENGES lookup (from Pass 2b)
    challenges_by_target: dict[str, list[str]] = {}
    for e in edges:
        if e["rel"] == "CHALLENGES":
            challenges_by_target.setdefault(e["target"], []).append(e["source"])

    # Build area → claim IDs lookup (excluding topic:Other)
    area_claims_map: dict[str, list[str]] = {}
    for nid, nd in nodes.items():
        if nd.get("type") == "claim":
            area = nd.get("area", "Other")
            if area != "Other":
                area_claims_map.setdefault(area, []).append(nid)

    formed_question_ids: list[str] = []

    # Model-node questions
    for mn_id, mn_label, mn_unit, keywords, binding_dir in _V2_MODEL_NODES:
        if mn_id not in _MN_QUESTION_TEMPLATES:
            continue
        q_text, qt_slug = _MN_QUESTION_TEMPLATES[mn_id]
        q_id = f"q:{qt_slug}"

        mn_node   = nodes.get(f"mn:{mn_id}", {})
        cp_id_key = f"cp:{mn_id.lower()}"
        cp_node   = nodes.get(cp_id_key, {})

        evidence_ids = mn_claim_map.get(mn_id, [])
        counter_ids  = list({
            challenger
            for ev_id in evidence_ids
            for challenger in challenges_by_target.get(ev_id, [])
            if challenger not in evidence_ids
        })

        coverage   = mn_node.get("coverage_status", "missing")
        is_contested = cp_node.get("decision_status") == "CONTESTED"

        decision_status = (
            "OPEN_CONTESTED"  if is_contested   else
            "OPEN_UNCOVERED"  if coverage == "missing" else
            "OPEN"
        )

        _upsert(
            q_id,
            type="question",
            label=q_text,
            question_type=qt_slug,
            model_node_id=mn_id,
            coverage_status="mapped",
            evidence_claim_ids=evidence_ids,
            counterevidence_claim_ids=counter_ids,
            requires_human_review=(is_contested or coverage == "missing"),
            formation_basis="model_node_coverage",
            decision_status=decision_status,
        )

        # question → model node
        _edge(q_id, f"mn:{mn_id}", ET_ANSWERS_TO)

        # evidence claims → question
        for ev_id in evidence_ids:
            _add_sem(ev_id, q_id, ET_BEARS_ON)

        # counterevidence → question
        for ct_id in counter_ids:
            _add_sem(ct_id, q_id, ET_CHALLENGES_QUESTION)

        formed_question_ids.append(q_id)

    # Cross-cutting questions (triggered by area presence)
    for q_text, qt_slug, trigger_area in _CROSS_CUTTING_QUESTIONS:
        area_claims = area_claims_map.get(trigger_area, [])
        if not area_claims:
            continue
        q_id = f"q:{qt_slug}"
        if q_id in nodes:
            continue
        _upsert(
            q_id,
            type="question",
            label=q_text,
            question_type=qt_slug,
            model_node_id=None,
            coverage_status="mapped",
            evidence_claim_ids=area_claims,
            counterevidence_claim_ids=[],
            requires_human_review=True,
            formation_basis="claim_area_coverage",
            decision_status="OPEN",
        )
        for cid in area_claims:
            _add_sem(cid, q_id, ET_BEARS_ON)
        formed_question_ids.append(q_id)

    # ── Pass 6: V2 — artifacts and decision ──────────────────────────────────
    for art_id, art_label, art_kind in _STANDARD_ARTIFACTS:
        _upsert(art_id, type=NT_ARTIFACT, label=art_label, kind=art_kind,
                coverage_status="missing",
                note="Artifact reference must be populated from deal outputs")

    dec_id = "dec:main"
    _upsert(dec_id, type=NT_DECISION, label="Main IC Decision",
            decision_status="PENDING",
            coverage_status="missing",
            note="Decision record must be written via /ic-record; append-only")

    # V5: MOIC and IRR produce the IC artifacts; EBITDA produces lender pack and gate.
    mn_moic_id = "mn:MN-MOIC"
    mn_irr_id  = "mn:MN-IRR"
    if mn_moic_id in nodes:
        _edge(mn_moic_id, "art:model", ET_PRODUCES)
        _edge(mn_moic_id, "art:memo",  ET_PRODUCES)
        _edge(mn_moic_id, dec_id,      ET_PRODUCES)
    if mn_irr_id in nodes:
        _edge(mn_irr_id,  dec_id,      ET_PRODUCES)
    mn_ebitda_id = "mn:MN-EBITDA"
    if mn_ebitda_id in nodes:
        _edge(mn_ebitda_id, "art:lender-pack", ET_PRODUCES)
        _edge(mn_ebitda_id, "art:gate",        ET_PRODUCES)

    # ── Pass 7: V2 — structural stubs (ui_hidden — runtime contract only) ─────
    # These stubs are required by the execution_mapping schema and the runtime,
    # but carry no claim-derived data. They are hidden from visualization.
    for stub_id, stub_label, stub_type, stub_note in _STRUCTURAL_STUBS:
        _upsert(stub_id, type=stub_type, label=stub_label,
                coverage_status="missing", note=stub_note, ui_hidden=True)

    cyclic_nodes = ["mn:MN-INTEREST", "mn:MN-CASHFLOW"]
    for nid in cyclic_nodes:
        if nid in nodes:
            _edge(nid, "stub:cyc-solver", ET_REQUIRES_SOLVER)

    for mn_id, _, _, _, _ in _V2_MODEL_NODES:
        nid = f"mn:{mn_id}"
        if nid in nodes:
            _edge(nid, "stub:controls", ET_HAS_CONTROL)

    # ── Pass 8: V2 — roles and policy (ui_hidden — authority matrix only) ─────
    # Role and policy nodes represent the authority matrix.
    # They are structural stubs awaiting real human assignments.
    for role_id, role_label, role_kind in _STANDARD_ROLES:
        _upsert(role_id, type=NT_ROLE, label=role_label, kind=role_kind,
                coverage_status="missing",
                note="Role assignment must be declared in the authority matrix",
                ui_hidden=True)

    for cp_id in cp_to_claims:
        _edge(cp_id, "stub:policy",   ET_GOVERNED_BY)
        _edge(cp_id, "role:preparer",  ET_ASSIGNED_TO)
        _edge(cp_id, "role:reviewer",  ET_ASSIGNED_TO)
        _edge(cp_id, "role:authority", ET_ASSIGNED_TO)
        _edge(cp_id, "role:escalation", ET_ASSIGNED_TO)

    # ── Pass 9: V2 — institutional state ─────────────────────────────────────
    _upsert("stub:inst-state", type=NT_INST_STATE,
            label="Institutional State (Current + Approved + K_t)",
            current_value=None, approved_value=None,
            history=[], K_t={},
            coverage_status="missing",
            note="Needs: current_value, approved_value, append-only history, "
                 "K_t accumulation per protected output",
            ui_hidden=True)
    _edge(dec_id, "stub:inst-state", "UPDATES_STATE")

    # ── Compute stats ─────────────────────────────────────────────────────────
    edge_type_counts: dict[str, int] = {}
    for e in edges:
        edge_type_counts[e["rel"]] = edge_type_counts.get(e["rel"], 0) + 1

    node_type_counts: dict[str, int] = {}
    for nd in nodes.values():
        t = nd.get("type", "?")
        node_type_counts[t] = node_type_counts.get(t, 0) + 1

    by_coverage: dict[str, list[str]] = {
        "mapped": [], "partial": [], "ambiguous": [], "missing": [],
    }
    for nid, nd in nodes.items():
        cs = nd.get("coverage_status", "missing")
        by_coverage.setdefault(cs, []).append(nid)

    coverage_report = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "mapped":    by_coverage.get("mapped",    []),
        "partial":   by_coverage.get("partial",   []),
        "ambiguous": by_coverage.get("ambiguous", []),
        "missing":   by_coverage.get("missing",   []),
        "hygiene_flags": hygiene_flags,
        "v1_only_relations": [
            "REFINES (canonical=False — not traversed by transition engine)",
            "TRACKS (canonical=False — not traversed by transition engine)",
        ],
    }

    # ── Canonical graph hash (sha256 of sorted node IDs + edge triples) ───────
    _digest_payload = _json.dumps(
        {
            "nodes": sorted(nodes.keys()),
            "edges": sorted(
                (e["source"], e["target"], e["rel"]) for e in edges
            ),
        },
        sort_keys=True,
    ).encode()
    canonical_graph_hash = "sha256:" + _hashlib.sha256(_digest_payload).hexdigest()

    # ── Execution mapping — V5, schema-compliant ──────────────────────────────
    # Verified section: claim-derived, ready for runtime consumption.
    # lbo_grammar_scaffold: proposed LBO structure — PENDING workbook formula derivation.
    # These are strictly separated so the runtime never treats scaffold as executable.

    _em_model_nodes = []
    for _mn_id, _mn_label, _mn_unit_v, _x1, _x2 in _V2_MODEL_NODES:
        _nid_v    = f"mn:{_mn_id}"
        _cp_key_v = f"cp:{_mn_id.lower()}"
        _cp_v     = nodes.get(_cp_key_v, {})
        _em_model_nodes.append({
            "id":                f"mn:{_mn_id}",
            "label":             _mn_label,
            "unit":              nodes.get(_nid_v, {}).get("unit", _mn_unit_v),
            "period":            _cp_v.get("period", ""),
            "perimeter":         _cp_v.get("perimeter", ""),
            "computational_form": _COMPUTATIONAL_FORMS.get(_mn_id, "DIRECT_INPUT"),
            "coverage_status":   nodes.get(_nid_v, {}).get("coverage_status", "missing"),
            "bound_claim_count": len(mn_claim_map.get(_mn_id, [])),
            "formula_id":        None,
        })

    _em_positions = []
    for _em_idx, _em_cp_id in enumerate(cp_to_claims):
        _em_cp_node    = nodes[_em_cp_id]
        _em_mn_id_loc  = _em_cp_node.get("mn_id")
        _em_is_qual    = _em_cp_node.get("is_qualitative", False)
        _em_positions.append({
            "binding_id":     f"PMB-{_em_idx + 1:03d}",
            "case_position_id": _em_cp_id,
            "model_node_id":  f"mn:{_em_mn_id_loc}" if _em_mn_id_loc else None,
            "direction":      _em_cp_node.get("binding_direction", "QUALITATIVE"),
            "is_qualitative": _em_is_qual,
        })

    _model_controls = [
        {
            "control_id":     "CTL-001",
            "label":          "Sources & Uses Balance",
            "scope_ids":      ["mn:MN-SOURCES-USES", "mn:MN-EQUITY", "mn:MN-DEBT-CAP"],
            "pass_condition": "sum(sources) == sum(uses) within $0.01m",
        },
        {
            "control_id":     "CTL-002",
            "label":          "Cash / Revolver Coherence",
            "scope_ids":      ["mn:MN-CASHFLOW", "mn:MN-DEBT-CAP"],
            "pass_condition": "revolver_drawn_period_end <= revolver_commitment ($7.5m)",
        },
        {
            "control_id":     "CTL-003",
            "label":          "Debt / Interest Coherence",
            "scope_ids":      ["mn:MN-DEBT-CAP", "mn:MN-INTEREST"],
            "pass_condition": (
                "interest_expense == avg_period_debt * effective_rate; "
                "effective_rate = max(SOFR_floor, SOFR_actual) + applicable_spread"
            ),
        },
        {
            "control_id":     "CTL-004",
            "label":          "Leverage Covenant Compliance",
            "scope_ids":      ["mn:MN-LEVERAGE", "mn:MN-EBITDA", "mn:MN-DEBT-CAP"],
            "pass_condition": (
                "net_debt / covenant_ebitda <= max_leverage_covenant "
                "(threshold from credit agreement)"
            ),
        },
    ]

    _coverage_limits: list[dict] = []
    _clt_idx = 1

    for _mn_id, _, _, _, _ in _V2_MODEL_NODES:
        _nid = f"mn:{_mn_id}"
        if nodes.get(_nid, {}).get("coverage_status") == "missing":
            _coverage_limits.append({
                "limit_id":    f"CLT-{_clt_idx:03d}",
                "reason_code": "MISSING_WORKBOOK_DEPENDENCY",
                "scope_ids":   [f"mn:{_mn_id}"],
            })
            _clt_idx += 1

    for _stub_id, _, _, _ in _STRUCTURAL_STUBS:
        if nodes.get(_stub_id, {}).get("coverage_status") == "missing":
            _coverage_limits.append({
                "limit_id":    f"CLT-{_clt_idx:03d}",
                "reason_code": "PENDING_HUMAN_REVIEW",
                "scope_ids":   [_stub_id],
            })
            _clt_idx += 1

    _coverage_limits.extend([
        {
            "limit_id":    f"CLT-{_clt_idx:03d}",
            "reason_code": "MISSING_TEMPORAL_SEGREGATION",
            "scope_ids":   ["ALL_MONITORING_EVENTS"],
        },
        {
            "limit_id":    f"CLT-{_clt_idx + 1:03d}",
            "reason_code": "MISSING_INSTITUTIONAL_STATE",
            "scope_ids":   ["stub:inst-state"],
        },
        {
            "limit_id":    f"CLT-{_clt_idx + 2:03d}",
            "reason_code": "MISSING_POLICY_BINDING",
            "scope_ids":   ["stub:policy", "role:preparer", "role:reviewer", "role:authority"],
        },
    ])

    # ── Temporal partition summary ────────────────────────────────────────────
    _entry_count = sum(
        1 for nd in nodes.values()
        if nd.get("type") == "claim" and nd.get("temporal_class") == "entry"
    )
    _mon_count = sum(
        1 for nd in nodes.values()
        if nd.get("type") == "claim" and nd.get("temporal_class") == "monitoring"
    )
    _mon_sources = sorted(set(
        nd.get("source_doc", "")
        for nd in nodes.values()
        if nd.get("type") == "claim" and nd.get("temporal_class") == "monitoring"
        and nd.get("source_doc")
    ))
    _temporal_partition = {
        "entry_claim_count":           _entry_count,
        "monitoring_claim_count":      _mon_count,
        "monitoring_sources_detected": _mon_sources,
        "segregation_status": (
            "MONITORING_EVENTS_PRESENT_EXCLUDED_FROM_POSITIONS"
            if _mon_count > 0 else "clean"
        ),
        "note": (
            "Monitoring claims excluded from case position scoring. "
            "CLT (MISSING_TEMPORAL_SEGREGATION) remains open until "
            "bitemporal known_at ordering is enforced at ingestion time."
        ),
    }

    # ── Contested positions ───────────────────────────────────────────────────
    _contested_positions = [
        {
            "model_node_id":         f"mn:{nodes[cp_id]['mn_id']}" if nodes[cp_id].get("mn_id") else None,
            "position_id":           cp_id,
            "requires_human_review": True,
            "candidates":            nodes[cp_id].get("candidates", []),
            "auto_selected_claim_id": (
                nodes[cp_id].get("candidates", [{}])[0].get("claim_id")
                if nodes[cp_id].get("candidates") else None
            ),
            "reason": (
                "Multiple candidate claims within 3-point scoring threshold "
                "and same semantic context (definition + scenario). "
                "Human must confirm which figure to adopt."
            ),
        }
        for cp_id in cp_to_claims
        if nodes.get(cp_id, {}).get("decision_status") == "CONTESTED"
    ]

    # ── LBO grammar scaffold ──────────────────────────────────────────────────
    # PROPOSED structure — NOT verified executable mapping.
    # All items are PENDING workbook formula derivation.
    # The runtime must never treat this section as executable until each item
    # is promoted to the verified section with a real workbook_ref.
    _lbo_grammar_scaffold = {
        "scaffold_note": (
            "This section contains the proposed LBO computational structure. "
            "No item here is verified against the actual workbook. "
            "Each PENDING_WORKBOOK_FORMULA must be resolved by Anto's runtime team "
            "before promotion to the verified execution mapping."
        ),
        "directed_model_edges": [
            {"edge_id": "DME-001",
             "from": "mn:MN-REVENUE", "to": "mn:MN-EBITDA",
             "formula_or_function_ref": "ebitda = revenue * ebitda_margin_pct",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-002",
             "from": "mn:MN-EBITDA", "to": "mn:MN-LEVERAGE",
             "formula_or_function_ref": "leverage = net_debt / ebitda",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-003",
             "from": "mn:MN-LEVERAGE", "to": "mn:MN-DEBT-CAP",
             "formula_or_function_ref": "debt_capacity = leverage_target * ebitda",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-004",
             "from": "mn:MN-DEBT-CAP", "to": "mn:MN-SOURCES-USES",
             "formula_or_function_ref": "sources: debt + equity + rollover; uses: ev + fees + cash",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-005",
             "from": "mn:MN-SOURCES-USES", "to": "mn:MN-EQUITY",
             "formula_or_function_ref": "equity = uses - debt - rollover_equity",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-006",
             "from": "mn:MN-EBITDA", "to": "mn:MN-CASHFLOW",
             "formula_or_function_ref": "fcf = ebitda - interest - tax - capex - delta_nwc",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-007",
             "from": "mn:MN-CASHFLOW", "to": "mn:MN-INTEREST",
             "formula_or_function_ref": "CYCLIC: cash_available = fcf + revolver_draw",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-008",
             "from": "mn:MN-INTEREST", "to": "mn:MN-CASHFLOW",
             "formula_or_function_ref": "CYCLIC: interest = avg_debt * (max(sofr_floor, sofr) + spread)",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-009",
             "from": "mn:MN-CASHFLOW", "to": "mn:MN-MOIC",
             "formula_or_function_ref": "exit_equity = exit_ev - exit_net_debt; moic = exit_equity / invested_equity",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-010",
             "from": "mn:MN-CASHFLOW", "to": "mn:MN-IRR",
             "formula_or_function_ref": "xirr(cashflows=[equity_in, fcf_y1..y5, exit_equity], dates)",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-011",
             "from": "mn:MN-EQUITY", "to": "mn:MN-MOIC",
             "formula_or_function_ref": "moic_denominator = sponsor_equity_invested",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
            {"edge_id": "DME-012",
             "from": "mn:MN-EQUITY", "to": "mn:MN-IRR",
             "formula_or_function_ref": "irr_denominator = sponsor_equity_invested (day-0 outflow)",
             "workbook_status": "PENDING_WORKBOOK_FORMULA"},
        ],
        "formulas": [
            {
                "formula_id":   "FORM-EBITDA-FIRM-V0",
                "input_ids":    [],
                "output_id":    "mn:MN-EBITDA",
                "expression_or_function_ref": (
                    "reported_ebitda + accepted_historical_adjustments"
                    " - revenue_wip_quality_reserve - customer_run_rate_reserve"
                    " - integration_cost - finance_reporting_cost = firm_ebitda"
                    " ($10.2m + $1.7m - $0.2m - $0.15m - $0.10m - $0.05m = $11.4m)"
                ),
                "workbook_status": "PENDING_WORKBOOK_CELL_REF",
            },
        ],
        "rule_switches": [
            {
                "rule_switch_id":     "RSW-SCENARIO-001",
                "label":              "Deal Scenario Selection",
                "selector_input_ids": ["mn:MN-REVENUE", "mn:MN-EBITDA"],
                "branches": [
                    {"branch_id": "RSW-001-B1", "condition": "scenario == STANDALONE_BASE"},
                    {"branch_id": "RSW-001-B2", "condition": "scenario == STANDALONE_DOWNSIDE"},
                    {"branch_id": "RSW-001-B3", "condition": "scenario == STANDALONE_UPSIDE"},
                    {"branch_id": "RSW-001-B4", "condition": "scenario == ACQUISITION_BASE"},
                ],
                "source_ref": "keystone_materiality_policy_v0.json#scenarios",
                "workbook_status": "PENDING_WORKBOOK_FORMULA",
            },
        ],
        "cyclic_component_solver_configs": [
            {
                "solver_id":                     "CYC-SCC-001",
                "component_type":                "NUMERICAL_SCC",
                "member_ids":                    ["mn:MN-CASHFLOW", "mn:MN-INTEREST"],
                "admissible_bounds": {
                    "mn:MN-CASHFLOW": [-100.0, 100.0],
                    "mn:MN-INTEREST": [0.0, 50.0],
                },
                "absolute_residual_tolerance":   0.001,
                "relative_residual_tolerance":   0.001,
                "maximum_iterations":            100,
                "invariant_control_ids":         ["CTL-002", "CTL-003"],
                "workbook_status":               "PENDING_WORKBOOK_FORMULA",
            },
        ],
    }

    execution_mapping = {
        "mapping_version":           "0.3.0",
        "canonical_graph_hash":      canonical_graph_hash,
        "model_nodes":               _em_model_nodes,
        "position_model_directions": _em_positions,
        "model_controls":            _model_controls,
        "coverage_limits":           _coverage_limits,
        "temporal_partition":        _temporal_partition,
        "contested_positions":       _contested_positions,
        "formed_questions":          formed_question_ids,
        "lbo_grammar_scaffold":      _lbo_grammar_scaffold,
    }

    return {
        "deal":               deal,
        "nodes": list(nodes.values()),
        "edges": edges,
        "area_colors":        AREA_COLORS,
        "area_border_colors": AREA_BORDER_COLORS,
        "execution_mapping":  execution_mapping,
        "coverage_report":    coverage_report,
        "stats": {
            "subjects":        node_type_counts.get("subject",        0),
            "claims":          node_type_counts.get("claim",          0),
            "questions":       node_type_counts.get("question",       0),
            "topics":          node_type_counts.get("topic",          0),
            "model_nodes":     node_type_counts.get(NT_MODEL_NODE,    0),
            "case_positions":  node_type_counts.get(NT_CASE_POSITION, 0),
            "support_routes":  node_type_counts.get(NT_SUPPORT_ROUTE, 0),
            "artifacts":       node_type_counts.get(NT_ARTIFACT,      0),
            "decisions":       node_type_counts.get(NT_DECISION,      0),
            "formed_questions": len(formed_question_ids),
            "stubs_missing":   len(by_coverage.get("missing", [])),
            "hygiene_excluded": len(hygiene_flags),
            "edges":           len(edges),
            "edge_types":      edge_type_counts,
            "node_types":      node_type_counts,
        },
    }
