#!/usr/bin/env python3
"""
minigraph — the slice of the networkx DiGraph API that graph_store needs,
implemented in the standard library.

Why not just depend on networkx
-------------------------------
CLAUDE.md pins v1 to "stdlib + PyYAML only". graph_store.py had quietly taken a
networkx dependency, which both broke that invariant and made tools/test_ui.py
unrunnable on a clean checkout (ModuleNotFoundError). The graph here is small —
tens of nodes, hundreds of edges — so the pure-Python cost is irrelevant.

Scope is deliberately narrow: exactly the calls graph_store makes, nothing more.
If the graph outgrows this, that is one of the migration triggers in
docs/01-spec.md, and swapping back to networkx is a one-line import change.

Algorithms follow the same definitions networkx uses:
  pagerank               damping 0.85, dangling mass redistributed uniformly
  betweenness_centrality Brandes, normalised by (n-1)(n-2) for directed graphs
  hits                   power iteration on the adjacency matrix
"""
from __future__ import annotations

from collections import deque
from typing import Any, Iterator


class NetworkXNoPath(Exception):
    pass


class NetworkXError(Exception):
    pass


class NodeNotFound(Exception):
    pass


class _NodeView:
    """Supports g.nodes[nid] and g.nodes(data=True)."""

    def __init__(self, store: dict[str, dict]):
        self._store = store

    def __getitem__(self, nid: str) -> dict:
        return self._store[nid]

    def __contains__(self, nid: object) -> bool:
        return nid in self._store

    def __iter__(self) -> Iterator[str]:
        return iter(self._store)

    def __len__(self) -> int:
        return len(self._store)

    def __call__(self, data: bool = False):
        if data:
            return list(self._store.items())
        return list(self._store)


class DiGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._succ: dict[str, dict[str, dict]] = {}
        self._pred: dict[str, dict[str, dict]] = {}

    # ── construction ─────────────────────────────────────────────────────────

    def add_node(self, nid: str, **attrs: Any) -> None:
        if nid not in self._nodes:
            self._nodes[nid] = {}
            self._succ[nid] = {}
            self._pred[nid] = {}
        self._nodes[nid].update(attrs)

    def add_edge(self, src: str, tgt: str, **attrs: Any) -> None:
        self.add_node(src)
        self.add_node(tgt)
        self._succ[src][tgt] = attrs
        self._pred[tgt][src] = attrs

    def has_edge(self, src: str, tgt: str) -> bool:
        return src in self._succ and tgt in self._succ[src]

    def has_node(self, nid: str) -> bool:
        return nid in self._nodes

    # ── views ────────────────────────────────────────────────────────────────

    @property
    def nodes(self) -> _NodeView:
        return _NodeView(self._nodes)

    def edges(self, data: bool = False):
        out = []
        for src, targets in self._succ.items():
            for tgt, attrs in targets.items():
                out.append((src, tgt, attrs) if data else (src, tgt))
        return out

    def successors(self, nid: str) -> list[str]:
        return list(self._succ.get(nid, {}))

    def predecessors(self, nid: str) -> list[str]:
        return list(self._pred.get(nid, {}))

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def number_of_edges(self) -> int:
        return sum(len(t) for t in self._succ.values())

    def __contains__(self, nid: object) -> bool:
        return nid in self._nodes

    def __iter__(self) -> Iterator[str]:
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def to_undirected(self) -> "Graph":
        g = Graph()
        for nid, attrs in self._nodes.items():
            g.add_node(nid, **attrs)
        for src, tgt, attrs in self.edges(data=True):
            g.add_edge(src, tgt, **attrs)
        return g


class Graph(DiGraph):
    """Undirected: every edge is stored both ways."""

    def add_edge(self, src: str, tgt: str, **attrs: Any) -> None:
        super().add_edge(src, tgt, **attrs)
        super().add_edge(tgt, src, **attrs)

    def number_of_edges(self) -> int:
        return super().number_of_edges() // 2


# ── algorithms ───────────────────────────────────────────────────────────────

def pagerank(G: DiGraph, alpha: float = 0.85, weight: str | None = None,
             max_iter: int = 100, tol: float = 1.0e-6) -> dict[str, float]:
    n = G.number_of_nodes()
    if n == 0:
        return {}
    nodes = list(G)
    x = {v: 1.0 / n for v in nodes}

    def edge_weight(src: str, tgt: str) -> float:
        if weight is None:
            return 1.0
        return float(G._succ[src][tgt].get(weight, 1.0) or 1.0)

    out_w = {v: sum(edge_weight(v, t) for t in G._succ[v]) for v in nodes}

    for _ in range(max_iter):
        prev = x
        x = dict.fromkeys(nodes, 0.0)
        dangling = sum(prev[v] for v in nodes if out_w[v] == 0.0)
        for v in nodes:
            if out_w[v] == 0.0:
                continue
            share = alpha * prev[v] / out_w[v]
            for t in G._succ[v]:
                x[t] += share * edge_weight(v, t)
        leak = alpha * dangling / n + (1.0 - alpha) / n
        for v in nodes:
            x[v] += leak
        if sum(abs(x[v] - prev[v]) for v in nodes) < n * tol:
            break
    return x


def betweenness_centrality(G: DiGraph, normalized: bool = True) -> dict[str, float]:
    """Brandes' algorithm on unweighted edges."""
    nodes = list(G)
    bc = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        stack: list[str] = []
        preds: dict[str, list[str]] = {v: [] for v in nodes}
        sigma = dict.fromkeys(nodes, 0.0)
        dist = dict.fromkeys(nodes, -1)
        sigma[s] = 1.0
        dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in G._succ.get(v, {}):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            w = stack.pop()
            for v in preds[w]:
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                bc[w] += delta[w]

    if normalized:
        n = len(nodes)
        if n > 2:
            scale = 1.0 / ((n - 1) * (n - 2))
            for v in bc:
                bc[v] *= scale
    return bc


def hits(G: DiGraph, max_iter: int = 100, tol: float = 1.0e-8
         ) -> tuple[dict[str, float], dict[str, float]]:
    nodes = list(G)
    if not nodes:
        return {}, {}
    hubs = dict.fromkeys(nodes, 1.0 / len(nodes))
    auth: dict[str, float] = {}
    for _ in range(max_iter):
        auth = dict.fromkeys(nodes, 0.0)
        for v in nodes:
            for t in G._succ.get(v, {}):
                auth[t] += hubs[v]
        s = sum(auth.values()) or 1.0
        auth = {k: v / s for k, v in auth.items()}

        new_hubs = dict.fromkeys(nodes, 0.0)
        for v in nodes:
            for t in G._succ.get(v, {}):
                new_hubs[v] += auth[t]
        s = sum(new_hubs.values()) or 1.0
        new_hubs = {k: v / s for k, v in new_hubs.items()}

        if sum(abs(new_hubs[v] - hubs[v]) for v in nodes) < tol:
            hubs = new_hubs
            break
        hubs = new_hubs
    return hubs, auth


def shortest_path(G: DiGraph, source: str, target: str) -> list[str]:
    if source not in G or target not in G:
        raise NodeNotFound(f"{source!r} or {target!r} not in graph")
    if source == target:
        return [source]
    prev: dict[str, str | None] = {source: None}
    q = deque([source])
    while q:
        v = q.popleft()
        for w in G._succ.get(v, {}):
            if w in prev:
                continue
            prev[w] = v
            if w == target:
                path = [w]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])  # type: ignore[index]
                return list(reversed(path))
            q.append(w)
    raise NetworkXNoPath(f"no path between {source!r} and {target!r}")


def node_link_data(G: DiGraph, edges: str = "edges") -> dict:
    return {
        "directed": not isinstance(G, Graph),
        "multigraph": False,
        "graph": {},
        "nodes": [{**attrs, "id": nid} for nid, attrs in G.nodes(data=True)],
        edges: [{**attrs, "source": s, "target": t} for s, t, attrs in G.edges(data=True)],
    }


def node_link_graph(data: dict, edges: str = "edges") -> DiGraph:
    G = DiGraph() if data.get("directed", True) else Graph()
    for n in data.get("nodes", []):
        attrs = {k: v for k, v in n.items() if k != "id"}
        G.add_node(n["id"], **attrs)
    for e in data.get(edges, data.get("links", [])):
        attrs = {k: v for k, v in e.items() if k not in ("source", "target")}
        G.add_edge(e["source"], e["target"], **attrs)
    return G
