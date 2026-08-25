#!/usr/bin/env python3
"""
PE OS Graph Store — NetworkX-based decomposed property graph.

Every claim dimension becomes its own node; shared dimensions (metric, period,
perimeter, source, author, area) are shared nodes.  This enables real graph
algorithms: PageRank, betweenness centrality, shortest path, community detection,
contradiction traversal — without a graph database server.

Node types
----------
claim      — the fact itself; carries value, unit, epistemic, direction, statement
entity     — the company/entity being measured  (e.g. "Keystone")
metric     — the KPI axis                       (e.g. "EBITDA")
period     — time reference                     (e.g. "FY2025A")
perimeter  — economic boundary                  (e.g. "consolidated")
source     — document                           (e.g. "QoE Report")
author     — claiming party                     (e.g. "management")
area       — macro area                         (e.g. "Earnings")
question   — diligence question                 (e.g. "qt-ebitda-quality")

Structural edges  (claim → dimension)
--------------------------------------
ABOUT        claim → entity
MEASURES     claim → metric
IN_PERIOD    claim → period
SCOPED_TO    claim → perimeter
FROM_SOURCE  claim → source
BY_AUTHOR    claim → author
IN_AREA      claim → area
BEARS_ON     claim → question

Semantic edges  (claim → claim, derived by rules)
--------------------------------------------------
CONTRADICTS   CHALLENGES   TRACKS   REFINES   CORROBORATES
DERIVES_FROM  SUPPORTS     SUPERSEDES
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# v1 is stdlib-only (CLAUDE.md). tools/minigraph implements the DiGraph slice
# this module uses; networkx is used only if it happens to be installed, and the
# two are interchangeable here.
try:
    import networkx as nx           # type: ignore
except ModuleNotFoundError:
    from tools import minigraph as nx

# ── Node type constants ────────────────────────────────────────────────────────
CLAIM     = "claim"
ENTITY    = "entity"
METRIC    = "metric"
PERIOD    = "period"
PERIMETER = "perimeter"
SOURCE    = "source"
AUTHOR    = "author"
AREA      = "area"
QUESTION  = "question"
# V2 node types
MODEL_NODE    = "model_node"
CASE_POSITION = "case_position"
SUPPORT_ROUTE = "support_route"
ARTIFACT      = "artifact"
DECISION      = "decision"
RULE_SWITCH   = "rule_switch"
SOLVER_CFG    = "solver_config"
MODEL_CONTROL = "model_control"
POLICY        = "policy"
ROLE          = "role"
INST_STATE    = "institutional_state"

# ── Edge type constants ────────────────────────────────────────────────────────
# Structural (V1)
ABOUT       = "ABOUT"
MEASURES    = "MEASURES"
IN_PERIOD   = "IN_PERIOD"
SCOPED_TO   = "SCOPED_TO"
FROM_SOURCE = "FROM_SOURCE"
BY_AUTHOR   = "BY_AUTHOR"
IN_AREA_E   = "IN_AREA"
BEARS_ON    = "BEARS_ON"
# Semantic (V1) — TRAVERSAL_RELS: SUPPORTS, CONTRADICTS, DERIVES_FROM, DRIVES, CONDITIONS
# REFINES/TRACKS/SUPERSEDES are informational only (not traversed by transition engine)
CONTRADICTS  = "CONTRADICTS"
CHALLENGES   = "CHALLENGES"
TRACKS       = "TRACKS"
REFINES      = "REFINES"
CORROBORATES = "CORROBORATES"
DERIVES_FROM = "DERIVES_FROM"
SUPPORTS     = "SUPPORTS"
SUPERSEDES   = "SUPERSEDES"
# Structural (V2)
SUPPORTS_ROUTE     = "SUPPORTS_ROUTE"
ROUTE_FOR_POSITION = "ROUTE_FOR_POSITION"
BINDS_TO           = "BINDS_TO"
PRODUCES           = "PRODUCES"
REQUIRES_SOLVER    = "REQUIRES_SOLVER"
HAS_CONTROL_E      = "HAS_CONTROL"
GOVERNED_BY        = "GOVERNED_BY"
ASSIGNED_TO        = "ASSIGNED_TO"
UPDATES_STATE      = "UPDATES_STATE"

SEMANTIC_RELS = {CONTRADICTS, CHALLENGES, TRACKS, REFINES,
                 CORROBORATES, DERIVES_FROM, SUPPORTS, SUPERSEDES}
STRUCTURAL_RELS = {ABOUT, MEASURES, IN_PERIOD, SCOPED_TO,
                   FROM_SOURCE, BY_AUTHOR, IN_AREA_E, BEARS_ON}
V2_STRUCTURAL_RELS = {SUPPORTS_ROUTE, ROUTE_FOR_POSITION, BINDS_TO,
                      PRODUCES, REQUIRES_SOLVER, HAS_CONTROL_E,
                      GOVERNED_BY, ASSIGNED_TO, UPDATES_STATE}

# ── Area taxonomy (mirrored from claim_graph.py) ─────────────────────────────
_AREA_RULES: list[tuple[str, str]] = [
    ("revenue",         "Revenue"),   ("recurring",     "Revenue"),
    ("backlog",         "Revenue"),   ("billing",       "Revenue"),
    ("ebitda",          "Earnings"),  ("earnings",      "Earnings"),
    ("margin",          "Earnings"),  ("adjustment",    "Earnings"),
    ("normaliz",        "Earnings"),  ("qoe",           "Earnings"),
    ("customer",        "Customer"),  ("concentration", "Customer"),
    ("churn",           "Customer"),  ("retention",     "Customer"),
    ("contract",        "Customer"),  ("account",       "Customer"),
    ("market",          "Market"),    ("position",      "Market"),
    ("regulatory",      "Market"),    ("competitive",   "Market"),
    ("operations",      "Operations"),("operational",   "Operations"),
    ("integration",     "Operations"),("systems",       "Operations"),
    ("working capital", "Operations"),("wip",           "Operations"),
    ("utilization",     "Operations"),("headcount",     "Operations"),
    ("debt",            "Structure"), ("leverage",      "Structure"),
    ("covenant",        "Structure"), ("capital structure","Structure"),
    ("loan",            "Structure"), ("revolver",      "Structure"),
    ("governance",      "Governance"),("management",    "Governance"),
    ("board",           "Governance"),("incentive",     "Governance"),
    ("exit",            "Returns"),   ("returns",       "Returns"),
    ("moic",            "Returns"),   ("irr",           "Returns"),
    ("multiple",        "Returns"),   ("acquisition",   "Returns"),
]


def _topic_to_area(topic: str) -> str:
    t = (topic or "").lower()
    for kw, area in _AREA_RULES:
        if kw in t:
            return area
    return "Other"


def _nid(type_: str, label: str) -> str:
    """Stable, deterministic node ID from type + normalised label."""
    norm = re.sub(r"\s+", "_", label.strip().lower())
    return f"{type_}:{norm}"


def _cid(idx: int) -> str:
    return f"claim:{idx:04d}"


# ── DealGraph ─────────────────────────────────────────────────────────────────

class DealGraph:
    """
    Decomposed property graph for a single PE deal.

    Every claim expands into 1 claim node + up to 8 dimension nodes,
    each connected by a typed structural edge.  Dimension nodes are
    shared: all EBITDA claims connect to the SAME metric:ebitda node.
    Semantic edges (CONTRADICTS, TRACKS, …) connect claim nodes directly.
    """

    def __init__(self, deal: str = ""):
        self.deal = deal
        self.G: nx.DiGraph = nx.DiGraph()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _upsert(self, nid: str, **attrs) -> str:
        if nid not in self.G:
            self.G.add_node(nid, **attrs)
        return nid

    def _edge(self, src: str, tgt: str, rel: str) -> None:
        if not self.G.has_edge(src, tgt):
            self.G.add_edge(src, tgt, rel=rel)

    # ── Public: build ──────────────────────────────────────────────────────────

    def add_claim(self, claim: dict, idx: int) -> str:
        # Keep the claim's own ordinal id when it has one. Re-indexing by
        # position renames claims whenever the admitted subset differs from the
        # extraction (claim:0012 became claim:0010 once 296 claims narrowed to
        # 257), which breaks lineage reconciliation against claims.json.
        c_id = str(claim.get("ordinal_id") or claim.get("id") or _cid(idx))

        self._upsert(c_id,
            type      = CLAIM,
            value     = claim.get("value", ""),
            unit      = claim.get("unit", ""),
            epistemic = claim.get("epistemic")
                        or claim.get("epistemic_class", "asserted"),
            direction = claim.get("direction", "context"),
            statement = claim.get("statement", ""),
            locator   = claim.get("locator", ""),
            derivation= claim.get("derivation"),
            deal      = self.deal,
        )

        def _dim(raw: str, type_: str, rel: str) -> None:
            v = raw.strip() if raw else ""
            if not v:
                return
            d_id = _nid(type_, v)
            self._upsert(d_id, type=type_, label=v)
            self._edge(c_id, d_id, rel)

        _dim(claim.get("subject", ""),    ENTITY,    ABOUT)
        _dim(claim.get("metric", ""),     METRIC,    MEASURES)
        _dim(claim.get("period") or claim.get("as_of", ""), PERIOD, IN_PERIOD)
        _dim(claim.get("perimeter", ""),  PERIMETER, SCOPED_TO)
        _dim(claim.get("source_doc", ""), SOURCE,    FROM_SOURCE)
        _dim(claim.get("author", ""),     AUTHOR,    BY_AUTHOR)

        area = _topic_to_area(claim.get("topic") or "")
        if area != "Other":
            _dim(area, AREA, IN_AREA_E)

        for q in (claim.get("bears_on") or []):
            q = (q or "").strip()
            if q:
                q_id = _nid(QUESTION, q)
                self._upsert(q_id, type=QUESTION, label=q)
                self._edge(c_id, q_id, BEARS_ON)

        return c_id

    def add_semantic_edge(self, src_id: str, tgt_id: str, rel: str) -> None:
        if src_id in self.G and tgt_id in self.G:
            self._edge(src_id, tgt_id, rel)

    def load_from_claims_graph(self, claims: list[dict], graph_dict: dict) -> None:
        """
        Populate from the output of claim_graph.claims_to_graph():
        - adds all claims as decomposed nodes
        - adds semantic edges (CONTRADICTS, TRACKS, …) that were already detected
        """
        for idx, claim in enumerate(claims):
            self.add_claim(claim, idx)

        # Map old claim_graph IDs (claim:000) to new IDs (claim:0000)
        def _remap(old_id: str) -> str:
            m = re.match(r"claim:(\d+)$", old_id)
            if m:
                return _cid(int(m.group(1)))
            return old_id

        for edge in graph_dict.get("edges", []):
            rel = edge.get("rel", "")
            if rel in SEMANTIC_RELS:
                self.add_semantic_edge(_remap(edge["source"]), _remap(edge["target"]), rel)

    # ── Public: analytics ────────────────────────────────────────────────────

    def pagerank(self, weight: str | None = None) -> dict[str, float]:
        """Standard PageRank. Identifies the most-connected claims."""
        return nx.pagerank(self.G, weight=weight)

    def betweenness(self, normalized: bool = True) -> dict[str, float]:
        """Betweenness centrality. High = bridges between clusters."""
        return nx.betweenness_centrality(self.G, normalized=normalized)

    def hubs_and_authorities(self) -> tuple[dict, dict]:
        """HITS algorithm — hubs point to many authorities."""
        return nx.hits(self.G)

    def contradictions(self) -> list[dict]:
        """All CONTRADICTS edges with full node data."""
        result = []
        for src, tgt, data in self.G.edges(data=True):
            if data.get("rel") == CONTRADICTS:
                result.append({
                    "source": {**self.G.nodes[src], "id": src},
                    "target": {**self.G.nodes[tgt], "id": tgt},
                })
        return result

    def claims_sharing_metric(self, metric_label: str) -> list[str]:
        """All claim IDs that measure a given metric (exact label match)."""
        m_id = _nid(METRIC, metric_label)
        if m_id not in self.G:
            return []
        return [n for n in self.G.predecessors(m_id)
                if self.G.nodes[n].get("type") == CLAIM]

    def shortest_path(self, src: str, tgt: str) -> list[str] | None:
        """Shortest undirected path between two nodes (or None)."""
        try:
            return nx.shortest_path(self.G.to_undirected(), src, tgt)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def top_by_pagerank(self, n: int = 10, types: set[str] | None = None) -> list[dict]:
        pr = self.pagerank()
        nodes = [(nid, score) for nid, score in pr.items()
                 if types is None or self.G.nodes[nid].get("type") in types]
        nodes.sort(key=lambda x: x[1], reverse=True)
        return [{"id": nid, "score": round(score, 5), **self.G.nodes[nid]}
                for nid, score in nodes[:n]]

    def stats(self) -> dict:
        node_types: dict[str, int] = {}
        for _, d in self.G.nodes(data=True):
            t = d.get("type", "?")
            node_types[t] = node_types.get(t, 0) + 1
        edge_types: dict[str, int] = {}
        for _, _, d in self.G.edges(data=True):
            r = d.get("rel", "?")
            edge_types[r] = edge_types.get(r, 0) + 1
        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def to_json(self) -> dict:
        """Serialise to NetworkX node-link format (round-trips perfectly)."""
        return nx.node_link_data(self.G, edges="edges")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2))

    @classmethod
    def load(cls, path: Path, deal: str = "") -> "DealGraph":
        dg = cls(deal=deal)
        data = json.loads(path.read_text())
        dg.G = nx.node_link_graph(data, edges="edges")
        return dg

    # ── Serialise for browser ──────────────────────────────────────────────────

    def to_vis_json(self, show_types: set[str] | None = None) -> dict:
        """
        Convert to the {nodes, edges} format expected by the test_ui graph renderer.
        show_types: which node types to include (default: all except perimeter/author).
        """
        if show_types is None:
            show_types = {CLAIM, ENTITY, METRIC, PERIOD, AREA, QUESTION, SOURCE}

        pr = self.pagerank()

        nodes = []
        for nid, data in self.G.nodes(data=True):
            if data.get("type") not in show_types:
                continue
            nodes.append({
                "id":        nid,
                "type":      data.get("type", "?"),
                "label":     data.get("label", nid),
                "value":     data.get("value", ""),
                "unit":      data.get("unit", ""),
                "epistemic": data.get("epistemic", ""),
                "direction": data.get("direction", ""),
                "statement": data.get("statement", ""),
                "derivation":data.get("derivation"),
                "deal":      data.get("deal", ""),
                "pagerank":  round(pr.get(nid, 0), 5),
            })

        visible = {n["id"] for n in nodes}
        edges = []
        for src, tgt, data in self.G.edges(data=True):
            if src in visible and tgt in visible:
                edges.append({"source": src, "target": tgt, "rel": data.get("rel", "")})

        return {"nodes": nodes, "edges": edges}


# ── Module-level helpers ───────────────────────────────────────────────────────

def build_from_extraction(claims: list[dict], graph_dict: dict,
                          deal: str = "") -> DealGraph:
    """One-shot builder: claims list + claim_graph output → DealGraph."""
    dg = DealGraph(deal=deal)
    dg.load_from_claims_graph(claims, graph_dict)
    return dg


def graph_path(deal: str) -> Path:
    root = Path(__file__).parent.parent
    return root / ".index" / "graphs" / f"{deal}.json"
