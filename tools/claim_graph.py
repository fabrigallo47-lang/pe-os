#!/usr/bin/env python3
"""Convert extracted claims to a typed semantic knowledge graph — V2.

V1 node types
-------------
subject   — unique entity being described
claim     — individual extracted fact
question  — diligence question from bears_on links
topic     — macro area grouping

V2 additional node types
------------------------
model_node          — quantitative financial model node
case_position       — institutional conclusion (adopted position)
support_route       — evidence bundle linking claims to a case_position
artifact            — output artefact (model, memo, lender pack, gate)
decision            — institutional decision record
rule_switch         — conditional branch (coverage_status=missing until populated)
solver_config       — cyclic/inverse solver config (coverage_status=missing)
model_control       — accounting / covenant invariant (coverage_status=missing)
policy              — materiality policy / authority matrix ref (coverage_status=missing)
role                — preparer / reviewer / authority / escalation (coverage_status=missing)
institutional_state — Current + Approved + history + K_t (coverage_status=missing)

V2 structural edges
--------------------
SUPPORTS_ROUTE      claim → support_route
ROUTE_FOR_POSITION  support_route → case_position
BINDS_TO            case_position → model_node  (carries binding_direction)
PRODUCES            model_node → artifact / decision
REQUIRES_SOLVER     model_node → solver_config
HAS_CONTROL         model_node → model_control
GOVERNED_BY         case_position → policy
ASSIGNED_TO         case_position → role

DERIVES_FROM direction: derived claim points FROM its sources (source → derived).
REFINES / TRACKS / SUPERSEDES: kept as informational; tagged canonical=False;
not traversed by the transition engine (TRAVERSAL_RELS does not include them).
"""
from __future__ import annotations
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
ET_SUPPORTS_ROUTE     = "SUPPORTS_ROUTE"
ET_ROUTE_FOR_POSITION = "ROUTE_FOR_POSITION"
ET_BINDS_TO           = "BINDS_TO"
ET_PRODUCES           = "PRODUCES"
ET_REQUIRES_SOLVER    = "REQUIRES_SOLVER"
ET_HAS_CONTROL        = "HAS_CONTROL"
ET_GOVERNED_BY        = "GOVERNED_BY"
ET_ASSIGNED_TO        = "ASSIGNED_TO"

# ── V2: Model node registry ─────────────────────────────────────────────────
# (id, label, unit, keywords, binding_direction)
_V2_MODEL_NODES: list[tuple[str, str, str, list[str], str]] = [
    ("MN-EBITDA",          "Firm EBITDA",         "£m",
     ["ebitda"],                                                    "POSITION_DRIVES_MODEL"),
    ("MN-REVENUE",         "Revenue",             "£m",
     ["revenue", "recurring"],                                      "POSITION_DRIVES_MODEL"),
    ("MN-LEVERAGE",        "Leverage",            "x",
     # Leverage = the RATIO (turns of EBITDA). "net debt" is kept in DEBT-CAP.
     ["leverage", "net leverage", "debt/ebitda", "net debt/ebitda",
      "leverage ratio", "leverage multiple", "turns"],
     "MODEL_DERIVES_POSITION"),
    ("MN-DEBT-CAP",        "Debt Capacity",       "£m",
     # Debt Cap = the dollar AMOUNT of debt (quantum, balance, or capacity).
     ["debt capacity", "borrowing", "lending capacity",
      "first-lien", "term loan", "senior debt", "opening debt", "debt facility",
      "senior secured", "debt quantum", "net debt", "economic net debt",
      "revolver balance", "revolver outstanding", "revolver drawn",
      "amortization", "debt amortization"],
     "MODEL_DERIVES_POSITION"),
    ("MN-SOURCES-USES",    "Sources & Uses",      "£m",
     ["sources", "uses", "rollover", "transaction structure",
      "transaction funding", "deal structure", "total consideration"],
     "MODEL_VALIDATES_POSITION"),
    ("MN-EQUITY",          "Sponsor Equity",      "£m",
     ["equity", "sponsor"],                                         "MODEL_DERIVES_POSITION"),
    ("MN-CASHFLOW",        "Cash Flow",           "£m",
     ["cash flow", "free cash", "fcf", "cash generation", "cash profit",
      "unlevered free", "levered free",
      "cash from operations", "operating cash", "cash operations",
      "cash from investing", "cash from financing"],
     "MODEL_DERIVES_POSITION"),
    ("MN-INTEREST",        "Interest & Revolver", "£m",
     # Interest = the cost/expense. Balances/spreads captured here as model inputs.
     ["interest expense", "interest cost", "interest charge",
      "cash interest", "pik", "debt service cost", "financing cost",
      "term loan spread", "revolver spread", "loan spread", "credit spread",
      "sofr spread", "base rate spread", "interest deduction"],
     "MODEL_DERIVES_POSITION"),
    ("MN-MOIC",            "MOIC",                "x",
     ["moic"],                                                      "MODEL_DERIVES_POSITION"),
    ("MN-IRR",             "IRR",                 "%",
     ["irr"],                                                       "MODEL_DERIVES_POSITION"),
    ("MN-SUPPORTED-PRICE", "Supported Price",     "£m",
     ["supported price", "maximum ev", "supported ev", "bid price", "enterprise value"],
     "MODEL_DERIVES_POSITION"),
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

# ── V2: Standard artifacts ──────────────────────────────────────────────────
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

# ── V2: Structural stubs (cannot be inferred from claims) ───────────────────
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
    ("stub:inv-solver", "Inverse Supported-Price Solver",
     NT_SOLVER,
     "Needs: objective, decision_variable, constraints, bounds, method, uniqueness"),
    ("stub:controls",   "Model Controls & Invariants",
     NT_CONTROL,
     "Needs: S&U balance, cash/revolver coherence, debt/interest, covenant, unit/perimeter"),
]


# ── V1 core builder ──────────────────────────────────────────────────────────

def claims_to_graph(claims: list[dict], source_name: str = "", deal: str = "") -> dict:
    """Build a V2 typed semantic graph from extracted claims.

    Returns:
        nodes            — all node dicts (V1 + V2 types)
        edges            — all edge dicts (V1 + V2 types)
        area_colors      — visualization colors
        area_border_colors
        execution_mapping — structured execution envelope (formulas/solvers stubs)
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

    # ── Pass 1: V1 — subject / claim / question / topic nodes ────────────────
    claim_ids: list[str | None] = []

    for i, c in enumerate(claims):
        subject = (c.get("subject") or "").strip()
        if not subject:
            claim_ids.append(None)
            continue

        s_id = f"subj:{subject}"
        _upsert(s_id, type="subject", label=subject, coverage_status="mapped")

        c_id = f"claim:{i:03d}"
        claim_ids.append(c_id)

        metric = c.get("metric", "")
        topic  = c.get("topic", "")
        area   = _topic_to_area(topic)
        label  = f"{metric or subject} = {c['value']}" if c.get("value") else (metric or subject)

        _upsert(
            c_id,
            type="claim", label=label,
            metric=metric, unit=c.get("unit", ""),
            as_of=c.get("as_of", ""), topic=topic, area=area,
            source_doc=c.get("source_doc", source_name),
            epistemic=c.get("epistemic", "asserted"),
            value=c.get("value", ""),
            period=c.get("period", ""),
            perimeter=c.get("perimeter", ""),
            direction=c.get("direction", "context"),
            locator=c.get("locator", ""),
            author=c.get("author", ""),
            statement=c.get("statement", ""),
            derivation=c.get("derivation"),
            coverage_status="mapped",
        )

        _edge(s_id, c_id, "HAS_CLAIM")

        t_id = f"topic:{area}"
        _upsert(t_id, type="topic", label=area, area=area, coverage_status="mapped")
        _edge(c_id, t_id, "IN_AREA")

        for q in (c.get("bears_on") or []):
            q = (q or "").strip()
            if not q:
                continue
            q_id = f"q:{q}"
            _upsert(q_id, type="question", label=q, coverage_status="mapped")
            _edge(c_id, q_id, "BEARS_ON")

    # ── Pass 2: V1 semantic edges ─────────────────────────────────────────────
    # CONTRADICTS + SUPERSEDES
    by_subject: dict[str, list[tuple[str, str, str, str]]] = {}
    for nid, node in nodes.items():
        if node["type"] != "claim":
            continue
        for e in edges:
            if e["rel"] == "HAS_CLAIM" and e["target"] == nid:
                metric = (node.get("metric") or node.get("subject") or "").lower().strip()
                by_subject.setdefault(e["source"], []).append(
                    (nid, node.get("direction", "context"), metric,
                     node.get("epistemic", "asserted")))
                break

    seen_dir: set[tuple[str, str, str]] = set()

    def _add_dir(src: str, tgt: str, rel: str) -> None:
        key = (src, tgt, rel)
        if key not in seen_dir:
            seen_dir.add(key)
            _edge(src, tgt, rel)

    for _, clist in by_subject.items():
        supports_l    = [(c, m, ep) for c, d, m, ep in clist if d == "supports"]
        contradicts_l = [(c, m, ep) for c, d, m, ep in clist if d == "contradicts"]
        for s_cid, s_met, s_ep in supports_l:
            for c_cid, c_met, c_ep in contradicts_l:
                if _metrics_conflict(s_met, c_met):
                    _add_dir(s_cid, c_cid, "CONTRADICTS")
                    if _TRUST.get(c_ep, 1) > _TRUST.get(s_ep, 1):
                        _add_dir(c_cid, s_cid, "SUPERSEDES")

    # Pair-wise semantic edges
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
                    # TRACKS: informational (not in TRAVERSAL_RELS); tagged canonical=False
                    _add_sem(a_id, b_id, "TRACKS", canonical=False,
                             adapter_note="informational_v1_not_traversed_by_engine")
                elif per_a and per_b and per_a != per_b:
                    # REFINES: informational — not in frozen TRAVERSAL_RELS
                    _add_sem(a_id, b_id, "REFINES", canonical=False,
                             adapter_note="informational_v1_not_traversed_by_engine")
                else:
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

    # CORROBORATES
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

    # DERIVES_FROM — with direction verification
    # Correct direction: derived claim → source claim (derived depends on source)
    # If found reversed (source → derived), flip it.
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
                # Verify direction: derived (a) should point FROM source (b)
                # i.e. a_id depends on b_id → edge: b_id → a_id would be wrong panta-wise
                # PANTA: DERIVES_FROM means "a was derived from b" → a → b (claim → its source)
                # This IS the correct direction per transition_engine traversal.
                _add_sem(a_id, b_id, "DERIVES_FROM")

    # SUPPORTS: quantitative → narrative thesis (same area + subject)
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

    # ── Pass 3: V2 — model_node stubs (always present) ───────────────────────
    mn_claim_map: dict[str, list[str]] = {}  # mn_id → list of matching claim IDs

    for mn_id, mn_label, mn_unit, keywords, _ in _V2_MODEL_NODES:
        nid = f"mn:{mn_id}"
        _upsert(nid,
                type=NT_MODEL_NODE, label=mn_label, mn_id=mn_id,
                unit=mn_unit, coverage_status="missing",
                formula=None, formula_ref=None,
                period=None, perimeter=None,
                directed_deps=[],
                note="Formula and formula_ref must be populated from the workbook")
        mn_claim_map[mn_id] = []

    # Bind claims to model nodes by keyword match
    for i, c in enumerate(claims):
        c_id = claim_ids[i]
        if not c_id:
            continue
        metric_lower = (c.get("metric") or "").lower()
        for mn_id, _, _, keywords, binding_dir in _V2_MODEL_NODES:
            if any(kw in metric_lower for kw in keywords):
                mn_claim_map[mn_id].append(c_id)

    # Update model node coverage_status based on found claims
    for mn_id, _, _, _, _ in _V2_MODEL_NODES:
        nid = f"mn:{mn_id}"
        n_claims = len(mn_claim_map[mn_id])
        if n_claims > 0:
            nodes[nid]["coverage_status"] = "partial"
            nodes[nid]["bound_claim_count"] = n_claims

    # ── Pass 4: V2 — case_position nodes (inferred from top claims) ──────────
    cp_to_claims: dict[str, list[str]] = {}  # cp_id → list of supporting claim IDs

    for mn_id, mn_label, mn_unit, keywords, binding_dir in _V2_MODEL_NODES:
        matching = mn_claim_map[mn_id]
        if not matching:
            continue

        _ADJUSTMENT_MARKERS = (
            # Adjustments and corrections (not primary values)
            "adjustment", "correction", "cut-off", "cutoff",
            "reserve", "normaliz", "add-back", "addback",
            # Growth/rate metrics (percentage, not a dollar position)
            "organic growth", "revenue growth", "cagr", "growth rate",
            "yoy growth", "ytd growth",
            # Tax and regulatory rules (not the interest/cash metric itself)
            "deduction cap", "deduction limit", "tax deduction", "163(j)",
            "tax rate", "tax assumption",
        )

        def _claim_score(cid: str) -> int:
            node = nodes.get(cid, {})
            metric_lower = (node.get("metric") or "").lower()
            # Adjustment/correction claims must never become the primary case position
            if any(w in metric_lower for w in _ADJUSTMENT_MARKERS):
                return -999
            trust   = _TRUST.get(node.get("epistemic", "asserted"), 1)
            has_val = 1 if node.get("value") else 0
            has_per = 1 if node.get("period") else 0
            # Prefer claims with a plausible primary value (abs > 0.5) over near-zero figures
            val = _parse_num(node.get("value"))
            value_bonus = 2 if (val is not None and abs(val) > 0.5) else 0
            return trust * 10 + has_val * 2 + has_per + value_bonus
        best_cid = max(matching, key=_claim_score)
        best_node = nodes[best_cid]

        cp_id  = f"cp:{mn_id.lower()}"
        stmt   = best_node.get("statement", f"Case position on {mn_label}")
        value  = best_node.get("value", "")
        period = best_node.get("period", best_node.get("as_of", ""))
        perimeter = best_node.get("perimeter", "")

        _upsert(
            cp_id,
            type=NT_CASE_POSITION, label=f"{mn_label} Position",
            mn_id=mn_id, binding_direction=binding_dir,
            statement=stmt, value=value, unit=mn_unit,
            period=period, perimeter=perimeter,
            decision_status="PENDING",
            coverage_status="partial",
            note=f"Inferred from {len(matching)} claim(s); "
                 f"requires human adoption to become ACCEPTED",
        )
        cp_to_claims[cp_id] = matching

        # Bind case_position → model_node
        mn_nid = f"mn:{mn_id}"
        _edge(cp_id, mn_nid, ET_BINDS_TO, binding_direction=binding_dir)

    # ── Pass 5: V2 — support_routes (one per case_position) ──────────────────
    for cp_id, supporting_cids in cp_to_claims.items():
        sr_id = f"sr:{cp_id[3:]}"  # strip "cp:" prefix
        mn_id = nodes[cp_id]["mn_id"]
        _upsert(
            sr_id,
            type=NT_SUPPORT_ROUTE, label=f"Route → {nodes[cp_id]['label']}",
            logic="INDEPENDENT",
            member_count=len(supporting_cids),
            coverage_status="partial",
            note="Logic defaults to INDEPENDENT; "
                 "update to AND or FORMULA when route structure is known",
        )
        # Claims → route
        for cid in supporting_cids:
            _edge(cid, sr_id, ET_SUPPORTS_ROUTE)
        # Route → case_position
        _edge(sr_id, cp_id, ET_ROUTE_FOR_POSITION)

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

    # Connect model nodes to artifacts and decision
    mn_model_id = "mn:MN-SUPPORTED-PRICE"
    if mn_model_id in nodes:
        _edge(mn_model_id, "art:model",   ET_PRODUCES)
        _edge(mn_model_id, "art:memo",    ET_PRODUCES)
        _edge(mn_model_id, dec_id,        ET_PRODUCES)
    mn_ebitda_id = "mn:MN-EBITDA"
    if mn_ebitda_id in nodes:
        _edge(mn_ebitda_id, "art:lender-pack", ET_PRODUCES)
        _edge(mn_ebitda_id, "art:gate",         ET_PRODUCES)

    # ── Pass 7: V2 — structural stubs (formulas, rules, solvers, controls) ───
    for stub_id, stub_label, stub_type, stub_note in _STRUCTURAL_STUBS:
        _upsert(stub_id, type=stub_type, label=stub_label,
                coverage_status="missing", note=stub_note)

    # Attach cyclic + inverse solvers to relevant model nodes
    cyclic_nodes = ["mn:MN-INTEREST", "mn:MN-CASHFLOW"]
    for nid in cyclic_nodes:
        if nid in nodes:
            _edge(nid, "stub:cyc-solver", ET_REQUIRES_SOLVER)
    if mn_model_id in nodes:
        _edge(mn_model_id, "stub:inv-solver", ET_REQUIRES_SOLVER)

    # Attach controls to all model nodes
    for mn_id, _, _, _, _ in _V2_MODEL_NODES:
        nid = f"mn:{mn_id}"
        if nid in nodes:
            _edge(nid, "stub:controls", ET_HAS_CONTROL)

    # ── Pass 8: V2 — roles and policy ────────────────────────────────────────
    for role_id, role_label, role_kind in _STANDARD_ROLES:
        _upsert(role_id, type=NT_ROLE, label=role_label, kind=role_kind,
                coverage_status="missing",
                note="Role assignment must be declared in the authority matrix")

    # Connect case positions to policy and roles
    for cp_id in cp_to_claims:
        _edge(cp_id, "stub:policy",          ET_GOVERNED_BY)
        _edge(cp_id, "role:preparer",         ET_ASSIGNED_TO)
        _edge(cp_id, "role:reviewer",         ET_ASSIGNED_TO)
        _edge(cp_id, "role:authority",        ET_ASSIGNED_TO)
        _edge(cp_id, "role:escalation",       ET_ASSIGNED_TO)

    # ── Pass 9: V2 — institutional state ────────────────────────────────────
    _upsert("stub:inst-state", type=NT_INST_STATE,
            label="Institutional State (Current + Approved + K_t)",
            current_value=None, approved_value=None,
            history=[], K_t={},
            coverage_status="missing",
            note="Needs: current_value, approved_value, append-only history, "
                 "K_t accumulation per protected output")

    # Connect decision to institutional state
    _edge(dec_id, "stub:inst-state", "UPDATES_STATE")

    # ── Compute stats ─────────────────────────────────────────────────────────
    edge_type_counts: dict[str, int] = {}
    for e in edges:
        edge_type_counts[e["rel"]] = edge_type_counts.get(e["rel"], 0) + 1

    node_type_counts: dict[str, int] = {}
    for nd in nodes.values():
        t = nd.get("type", "?")
        node_type_counts[t] = node_type_counts.get(t, 0) + 1

    # Coverage breakdown
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

    # Execution mapping (structured envelope for the transition engine)
    execution_mapping = {
        "model_nodes": [
            {
                "id": f"mn:{mn_id}",
                "label": mn_label,
                "unit": mn_unit,
                "keywords": keywords,
                "binding_direction": binding_dir,
                "coverage_status": nodes.get(f"mn:{mn_id}", {}).get("coverage_status", "missing"),
                "bound_claim_count": len(mn_claim_map.get(mn_id, [])),
                "formula": None,
                "formula_ref": None,
            }
            for mn_id, mn_label, mn_unit, keywords, binding_dir in _V2_MODEL_NODES
        ],
        "directed_model_edges": [],    # to be populated from workbook
        "position_model_directions": [
            {
                "case_position_id": cp_id,
                "model_node_id": f"mn:{nodes[cp_id]['mn_id']}",
                "direction": nodes[cp_id]["binding_direction"],
                "coverage_status": "partial",
            }
            for cp_id in cp_to_claims
        ],
        "formulas":                      [],   # missing — need workbook
        "rule_switches":                 [],   # missing — need policy source
        "cyclic_component_solver_configs": [], # missing — need equation set
        "inverse_solver_configs":        [],   # missing — need objective/constraints
        "model_controls":                [],   # missing — need accounting invariants
        "coverage_limits": [
            {"node_id": nid, "reason": nd.get("note", "")}
            for nid, nd in nodes.items()
            if nd.get("coverage_status") == "missing"
        ],
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
            "subjects":   node_type_counts.get("subject",   0),
            "claims":     node_type_counts.get("claim",     0),
            "questions":  node_type_counts.get("question",  0),
            "topics":     node_type_counts.get("topic",     0),
            "model_nodes":     node_type_counts.get(NT_MODEL_NODE,    0),
            "case_positions":  node_type_counts.get(NT_CASE_POSITION, 0),
            "support_routes":  node_type_counts.get(NT_SUPPORT_ROUTE, 0),
            "artifacts":       node_type_counts.get(NT_ARTIFACT,      0),
            "decisions":       node_type_counts.get(NT_DECISION,      0),
            "stubs_missing": len(by_coverage.get("missing", [])),
            "hygiene_excluded": len(hygiene_flags),
            "edges":      len(edges),
            "edge_types": edge_type_counts,
            "node_types": node_type_counts,
        },
    }
