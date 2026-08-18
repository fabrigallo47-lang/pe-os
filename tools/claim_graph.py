#!/usr/bin/env python3
"""Convert extracted claims to a typed semantic knowledge graph.

Node types
----------
subject   — unique entity being described (e.g. "Alderstone", "Riverton")
claim     — individual extracted fact (has metric, value, period, perimeter, epistemic)
question  — diligence question from bears_on links
topic     — macro area grouping (Revenue, Earnings, Customer, …)

Structural edges
----------------
HAS_CLAIM   subject → claim    entity owns the claim
IN_AREA     claim   → topic    claim belongs to a macro area (used for clustering)
BEARS_ON    claim   → question claim bears on this diligence question

Semantic edges  (rule-based, no LLM)
--------------------------------------
CONTRADICTS  claim → claim  direction=supports vs direction=contradicts, same subject
CHALLENGES   claim → claim  higher-trust claim has materially different numeric value
                            from lower-trust claim on the same metric (>5% delta)
TRACKS       claim → claim  same metric, same subject, different period — time series link
REFINES      claim → claim  same metric + subject, different perimeter — narrower scope
CORROBORATES claim → claim  two claims both support same question, from different sources
DERIVES_FROM claim → claim  derived claim whose derivation text names another claim's metric
"""
from __future__ import annotations

import re

# ── Macro area taxonomy ──────────────────────────────────────────────────────
# Ordered list of (keyword, area); first keyword match in topic field wins.

_AREA_RULES: list[tuple[str, str]] = [
    # Revenue
    ("revenue",          "Revenue"),
    ("recurring",        "Revenue"),
    ("backlog",          "Revenue"),
    ("pipeline",         "Revenue"),
    ("billing",          "Revenue"),
    # Earnings
    ("ebitda",           "Earnings"),
    ("earnings",         "Earnings"),
    ("margin",           "Earnings"),
    ("adjustment",       "Earnings"),
    ("normaliz",         "Earnings"),
    ("qoe",              "Earnings"),
    # Customer
    ("customer",         "Customer"),
    ("concentration",    "Customer"),
    ("churn",            "Customer"),
    ("retention",        "Customer"),
    ("contract",         "Customer"),
    ("account",          "Customer"),
    # Market
    ("market",           "Market"),
    ("position",         "Market"),
    ("regulatory",       "Market"),
    ("competitive",      "Market"),
    ("technology",       "Market"),
    # Operations
    ("operations",       "Operations"),
    ("operational",      "Operations"),
    ("integration",      "Operations"),
    ("systems",          "Operations"),
    ("working capital",  "Operations"),
    ("wip",              "Operations"),
    ("utilization",      "Operations"),
    ("headcount",        "Operations"),
    # Structure
    ("debt",             "Structure"),
    ("leverage",         "Structure"),
    ("covenant",         "Structure"),
    ("capital structure","Structure"),
    ("loan",             "Structure"),
    ("revolver",         "Structure"),
    ("lien",             "Structure"),
    # Governance
    ("governance",       "Governance"),
    ("management",       "Governance"),
    ("board",            "Governance"),
    ("incentive",        "Governance"),
    ("retention",        "Governance"),
    # Returns
    ("exit",             "Returns"),
    ("returns",          "Returns"),
    ("moic",             "Returns"),
    ("irr",              "Returns"),
    ("xirr",             "Returns"),
    ("multiple",         "Returns"),
    ("acquisition",      "Returns"),
]

# Background fill colors for each macro area (semi-transparent dark tints)
AREA_COLORS: dict[str, str] = {
    "Revenue":    "#0d2236",
    "Earnings":   "#0d2218",
    "Customer":   "#2a1010",
    "Market":     "#1a0d2a",
    "Operations": "#2a1d0d",
    "Structure":  "#0d1a2a",
    "Governance": "#1a2a0d",
    "Returns":    "#2a180d",
    "Other":      "#161b22",
}

AREA_BORDER_COLORS: dict[str, str] = {
    "Revenue":    "#1e4d7a",
    "Earnings":   "#1e5c30",
    "Customer":   "#5c2020",
    "Market":     "#3d1a6e",
    "Operations": "#6e4a1a",
    "Structure":  "#1a4a6e",
    "Governance": "#4a6e1a",
    "Returns":    "#6e3a1a",
    "Other":      "#30363d",
}


def _topic_to_area(topic: str) -> str:
    t = (topic or "").lower()
    for kw, area in _AREA_RULES:
        if kw in t:
            return area
    return "Other"


def _metrics_conflict(m1: str, m2: str) -> bool:
    """True when two metric strings refer to the same axis being disputed.

    Stricter than substring containment: rejects 'EBITDA' vs 'EBITDA Margin'
    (different KPIs) while accepting 'Customer Concentration' vs
    'Top-3 Customer Concentration' (refinement of same axis).
    """
    if not m1 or not m2:
        return False
    if m1 == m2:
        return True
    s, l = sorted([m1, m2], key=len)
    # Length ratio gate: if shorter is less than 60% of longer, treat as different axes.
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
    "attested": 3,
    "observed": 2,
    "derived":  2,
    "asserted": 1,
}


def claims_to_graph(claims: list[dict], source_name: str = "") -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def upsert(nid: str, **kw) -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, **kw}

    claim_ids: list[str | None] = []

    # ── 1. Subject / claim / question / topic nodes ───────────────────────────
    for i, c in enumerate(claims):
        subject = (c.get("subject") or "").strip()
        if not subject:
            claim_ids.append(None)
            continue

        s_id = f"subj:{subject}"
        upsert(s_id, type="subject", label=subject)

        c_id = f"claim:{i:03d}"
        claim_ids.append(c_id)

        metric = c.get("metric", "")
        topic  = c.get("topic", "")
        area   = _topic_to_area(topic)

        label = metric or subject
        if c.get("value"):
            label = f"{metric or subject} = {c['value']}"

        upsert(
            c_id,
            type="claim",
            label=label,
            metric=metric,
            unit=c.get("unit", ""),
            as_of=c.get("as_of", ""),
            topic=topic,
            area=area,
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
        )

        edges.append({"source": s_id, "target": c_id, "rel": "HAS_CLAIM"})

        # Topic node + IN_AREA edge
        t_id = f"topic:{area}"
        upsert(t_id, type="topic", label=area, area=area)
        edges.append({"source": c_id, "target": t_id, "rel": "IN_AREA"})

        # Question nodes from bears_on
        for q in (c.get("bears_on") or []):
            q = (q or "").strip()
            if not q:
                continue
            q_id = f"q:{q}"
            upsert(q_id, type="question", label=q)
            edges.append({"source": c_id, "target": q_id, "rel": "BEARS_ON"})

    # ── 2. CONTRADICTS  (direction-based, metric-gated) ───────────────────────
    # A "supports" claim CONTRADICTS a "contradicts" claim only when they share the
    # same subject AND the same metric axis — prevents cross-metric spurious edges.
    by_subject: dict[str, list[tuple[str, str, str, str]]] = {}
    for nid, node in nodes.items():
        if node["type"] != "claim":
            continue
        for e in edges:
            if e["rel"] == "HAS_CLAIM" and e["target"] == nid:
                metric = (node.get("metric") or node.get("subject") or "").lower().strip()
                by_subject.setdefault(e["source"], []).append(
                    (nid, node.get("direction", "context"), metric,
                     node.get("epistemic", "asserted"))
                )
                break

    seen_dir: set[tuple[str, str, str]] = set()

    def _add_dir(src: str, tgt: str, rel: str) -> None:
        key = (src, tgt, rel)
        if key not in seen_dir:
            seen_dir.add(key)
            edges.append({"source": src, "target": tgt, "rel": rel})

    for _, claim_list in by_subject.items():
        supports_l    = [(cid, m, ep) for cid, d, m, ep in claim_list if d == "supports"]
        contradicts_l = [(cid, m, ep) for cid, d, m, ep in claim_list if d == "contradicts"]
        for s_cid, s_met, s_ep in supports_l:
            for c_cid, c_met, c_ep in contradicts_l:
                if not s_met or not c_met:
                    continue
                # Only fire when metrics are on the same axis (strict length-ratio check)
                if _metrics_conflict(s_met, c_met):
                    _add_dir(s_cid, c_cid, "CONTRADICTS")
                    # SUPERSEDES: higher-trust contradicts claim displaces lower-trust supports claim
                    # (EvoKG pattern: confidence-based belief update made explicit in the graph)
                    if _TRUST.get(c_ep, 1) > _TRUST.get(s_ep, 1):
                        _add_dir(c_cid, s_cid, "SUPERSEDES")

    # ── 3. Semantic edges between claim pairs ─────────────────────────────────
    n = len(claims)

    # Index by bears_on target for CORROBORATES
    bears_index: dict[str, list[int]] = {}
    for i, c in enumerate(claims):
        for q in (c.get("bears_on") or []):
            q = (q or "").strip()
            if q:
                bears_index.setdefault(q, []).append(i)

    seen_sem: set[tuple[str, str, str]] = set()

    def _add_sem(src: str, tgt: str, rel: str) -> None:
        key = (src, tgt, rel)
        if key not in seen_sem:
            seen_sem.add(key)
            edges.append({"source": src, "target": tgt, "rel": rel})

    for i in range(n):
        a   = claims[i]
        a_id = claim_ids[i]
        if not a_id:
            continue

        m_a   = (a.get("metric") or a.get("subject") or "").lower().strip()
        p_a   = (a.get("period")   or a.get("as_of") or "").strip()
        per_a = (a.get("perimeter") or "").strip()
        ep_a  = a.get("epistemic", "asserted")
        s_a   = (a.get("subject") or "").lower().strip()

        for j in range(i + 1, n):
            b   = claims[j]
            b_id = claim_ids[j]
            if not b_id:
                continue

            m_b   = (b.get("metric") or b.get("subject") or "").lower().strip()
            p_b   = (b.get("period")   or b.get("as_of") or "").strip()
            per_b = (b.get("perimeter") or "").strip()
            ep_b  = b.get("epistemic", "asserted")
            s_b   = (b.get("subject") or "").lower().strip()

            # Subject similarity (substring match)
            same_subj = bool(
                s_a and s_b and (s_a == s_b or s_a in s_b or s_b in s_a)
            )
            # Metric similarity (substring match, min 4 chars)
            same_met = bool(
                m_a and m_b and len(m_a) >= 4 and len(m_b) >= 4 and
                (m_a == m_b or m_a in m_b or m_b in m_a)
            )

            if same_subj and same_met:
                # TRACKS: same metric + subject, different period
                if p_a and p_b and p_a != p_b:
                    _add_sem(a_id, b_id, "TRACKS")

                # REFINES: same metric + subject, different perimeter
                elif per_a and per_b and per_a != per_b:
                    _add_sem(a_id, b_id, "REFINES")

                # CHALLENGES: same metric + subject, different trust level,
                #             numeric values differ by >5%
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

    # CORROBORATES: same bears_on target + direction=supports + different source_doc
    for q, idxs in bears_index.items():
        supporters = [
            idx for idx in idxs
            if claims[idx].get("direction") == "supports" and claim_ids[idx]
        ]
        for ii in range(len(supporters)):
            for jj in range(ii + 1, len(supporters)):
                ia, ib = supporters[ii], supporters[jj]
                src_a = (claims[ia].get("source_doc") or "").strip()
                src_b = (claims[ib].get("source_doc") or "").strip()
                if src_a != src_b:
                    _add_sem(claim_ids[ia], claim_ids[ib], "CORROBORATES")

    # DERIVES_FROM: computed claims (epistemic=derived) whose derivation text names
    # another claim's metric — strictly for mathematical/computational derivations.
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

    # SUPPORTS: a narrative/thesis claim (no value) in the same area + overlapping
    # subject as a quantitative claim → quantitative claims SUPPORT the thesis.
    # This makes the causal chain visible: data points → narrative finding.
    for i in range(n):
        a = claims[i]
        a_id = claim_ids[i]
        if not a_id or (a.get("value") or "").strip():
            continue  # skip — this is a quantitative claim
        s_a = (a.get("subject") or "").lower().strip()
        area_a = _topic_to_area(a.get("topic") or "")
        if not s_a or area_a == "Other":
            continue
        for j in range(n):
            if i == j:
                continue
            b = claims[j]
            b_id = claim_ids[j]
            if not b_id or not (b.get("value") or "").strip():
                continue  # skip — also a narrative claim
            s_b = (b.get("subject") or "").lower().strip()
            area_b = _topic_to_area(b.get("topic") or "")
            same_subj = bool(s_a and s_b and (s_a == s_b or s_a in s_b or s_b in s_a))
            same_area = area_a == area_b
            if same_subj and same_area:
                _add_sem(b_id, a_id, "SUPPORTS")  # quantitative → thesis

    # ── 4. Stats ──────────────────────────────────────────────────────────────
    edge_type_counts: dict[str, int] = {}
    for e in edges:
        edge_type_counts[e["rel"]] = edge_type_counts.get(e["rel"], 0) + 1

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "area_colors":        AREA_COLORS,
        "area_border_colors": AREA_BORDER_COLORS,
        "stats": {
            "subjects":   sum(1 for nd in nodes.values() if nd["type"] == "subject"),
            "claims":     sum(1 for nd in nodes.values() if nd["type"] == "claim"),
            "questions":  sum(1 for nd in nodes.values() if nd["type"] == "question"),
            "topics":     sum(1 for nd in nodes.values() if nd["type"] == "topic"),
            "edges":      len(edges),
            "edge_types": edge_type_counts,
        },
    }
