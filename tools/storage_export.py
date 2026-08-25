#!/usr/bin/env python3
"""
storage_export — write nodes.csv, edges.csv and graph.db from one graph.json.

The V7 bundle contract requires the extraction graph in three representations
that reconcile *row by row*, not merely in counts. PANTA's independent
validator (validate_bundle.py, check_storage) enforces:

  nodes.csv   columns exactly  id,type,label,data
              data = JSON of the whole node; data["id"] == id
                                              data["type"] == type
  edges.csv   columns exactly  src,tgt,rel,data
              data = JSON of the whole edge; data source/target/rel == key
  graph.db    table nodes(id, type, label, data)   PK: id
              table edges(src, tgt, rel, data)     PK: (src, tgt, rel)
              column order and PK positions are checked, not just presence

and then compares canonical_hash of every payload across the three. So the
only safe way to produce them is from a single in-memory snapshot, which is
what this module does — hence "esportare dalla stessa snapshot atomica".

The previous exports had flattened per-attribute CSV columns and no `data`
field at all, and graph.db held only a `graph_meta` table, so every row
reconciliation check failed.

Usage
-----
  python3 tools/storage_export.py --bundle pipeline_out/e3/K-IC/adapter_alpha
  python3 tools/storage_export.py --graph path/to/graph.json --out DIR
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

NODE_COLUMNS = ["id", "type", "label", "data"]
EDGE_COLUMNS = ["src", "tgt", "rel", "data"]


def _dumps(obj) -> str:
    # sort_keys so the same logical row serialises identically everywhere.
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _node_key(node: dict) -> str:
    return str(node.get("id", ""))


def _edge_key(edge: dict) -> tuple[str, str, str]:
    return (str(edge.get("source", "")),
            str(edge.get("target", "")),
            str(edge.get("rel", "")))


def validate_graph(graph: dict) -> list[str]:
    """Reject a graph that cannot produce a reconcilable export."""
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    seen_nodes: set[str] = set()
    for i, n in enumerate(nodes):
        nid = _node_key(n)
        if not nid:
            errors.append(f"nodes[{i}]: id mancante")
        elif nid in seen_nodes:
            errors.append(f"nodes[{i}]: id duplicato {nid!r}")
        seen_nodes.add(nid)

    seen_edges: set[tuple[str, str, str]] = set()
    for i, e in enumerate(edges):
        key = _edge_key(e)
        if not all(key):
            errors.append(f"edges[{i}]: chiave incompleta {key}")
        elif key in seen_edges:
            errors.append(f"edges[{i}]: chiave duplicata {key}")
        seen_edges.add(key)
        for endpoint in key[:2]:
            if endpoint and endpoint not in seen_nodes:
                errors.append(f"edges[{i}]: endpoint {endpoint!r} non è un nodo")
    return errors


def export(graph: dict, out_dir: Path) -> dict:
    """Write the three representations from a single snapshot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes = list(graph.get("nodes", []))
    edges = list(graph.get("edges", []))

    # Rows are built once and reused for all three sinks, so they cannot drift.
    node_rows = [
        {
            "id": _node_key(n),
            "type": str(n.get("type", "")),
            "label": str(n.get("label", "")),
            "data": _dumps(n),
        }
        for n in nodes
    ]
    edge_rows = []
    for e in edges:
        src, tgt, rel = _edge_key(e)
        edge_rows.append({"src": src, "tgt": tgt, "rel": rel, "data": _dumps(e)})

    # ── CSV ──────────────────────────────────────────────────────────────────
    with (out_dir / "nodes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=NODE_COLUMNS)
        w.writeheader()
        w.writerows(node_rows)
    with (out_dir / "edges.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=EDGE_COLUMNS)
        w.writeheader()
        w.writerows(edge_rows)

    # ── SQLite ───────────────────────────────────────────────────────────────
    db_path = out_dir / "graph.db"
    if db_path.exists():
        db_path.unlink()          # rebuild, never append onto an old schema
    con = sqlite3.connect(db_path)
    try:
        con.execute("""
            CREATE TABLE nodes (
                id    TEXT PRIMARY KEY,
                type  TEXT,
                label TEXT,
                data  TEXT
            )
        """)
        con.execute("""
            CREATE TABLE edges (
                src  TEXT,
                tgt  TEXT,
                rel  TEXT,
                data TEXT,
                PRIMARY KEY (src, tgt, rel)
            )
        """)
        con.executemany(
            "INSERT INTO nodes (id, type, label, data) VALUES (?, ?, ?, ?)",
            [(r["id"], r["type"], r["label"], r["data"]) for r in node_rows],
        )
        con.executemany(
            "INSERT INTO edges (src, tgt, rel, data) VALUES (?, ?, ?, ?)",
            [(r["src"], r["tgt"], r["rel"], r["data"]) for r in edge_rows],
        )
        con.commit()
    finally:
        con.close()

    return {"nodes": len(node_rows), "edges": len(edge_rows), "out_dir": str(out_dir)}


def verify(out_dir: Path, graph: dict) -> list[str]:
    """Re-read the three sinks and reconcile them the way the validator does."""
    problems: list[str] = []

    with (out_dir / "nodes.csv").open(newline="", encoding="utf-8-sig") as fh:
        csv_nodes = list(csv.DictReader(fh))
    with (out_dir / "edges.csv").open(newline="", encoding="utf-8-sig") as fh:
        csv_edges = list(csv.DictReader(fh))

    con = sqlite3.connect(f"file:{out_dir / 'graph.db'}?mode=ro", uri=True)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"nodes", "edges"}.issubset(tables):
        problems.append(f"graph.db: tabelle {sorted(tables)}")
    node_schema = con.execute("PRAGMA table_info(nodes)").fetchall()
    edge_schema = con.execute("PRAGMA table_info(edges)").fetchall()
    if [c[1] for c in node_schema] != NODE_COLUMNS:
        problems.append(f"graph.db nodes colonne: {[c[1] for c in node_schema]}")
    if [c[1] for c in edge_schema] != EDGE_COLUMNS:
        problems.append(f"graph.db edges colonne: {[c[1] for c in edge_schema]}")
    if [c[5] for c in node_schema] != [1, 0, 0, 0]:
        problems.append(f"graph.db nodes PK: {[c[5] for c in node_schema]}")
    if [c[5] for c in edge_schema] != [1, 2, 3, 0]:
        problems.append(f"graph.db edges PK: {[c[5] for c in edge_schema]}")
    db_nodes = con.execute("SELECT id, type, label, data FROM nodes ORDER BY id").fetchall()
    db_edges = con.execute(
        "SELECT src, tgt, rel, data FROM edges ORDER BY src, tgt, rel").fetchall()
    con.close()

    g_nodes = {_node_key(n): n for n in graph.get("nodes", [])}
    g_edges = {_edge_key(e): e for e in graph.get("edges", [])}

    c_nodes = {r["id"]: json.loads(r["data"]) for r in csv_nodes}
    d_nodes = {r[0]: json.loads(r[3]) for r in db_nodes}
    c_edges = {(r["src"], r["tgt"], r["rel"]): json.loads(r["data"]) for r in csv_edges}
    d_edges = {(r[0], r[1], r[2]): json.loads(r[3]) for r in db_edges}

    for label, left, right in (
        ("graph.json↔nodes.csv", g_nodes, c_nodes),
        ("nodes.csv↔graph.db", c_nodes, d_nodes),
        ("graph.json↔edges.csv", g_edges, c_edges),
        ("edges.csv↔graph.db", c_edges, d_edges),
    ):
        if set(left) != set(right):
            problems.append(f"{label}: key set diverso")
            continue
        bad = [k for k in left if _dumps(left[k]) != _dumps(right[k])]
        if bad:
            problems.append(f"{label}: {len(bad)} righe con contenuto diverso")

    # metadata triples must agree too
    g_meta = {k: (str(v.get("type", "")), str(v.get("label", "")))
              for k, v in g_nodes.items()}
    c_meta = {r["id"]: (r["type"], r["label"]) for r in csv_nodes}
    d_meta = {r[0]: (str(r[1]), str(r[2])) for r in db_nodes}
    if g_meta != c_meta:
        problems.append("metadata graph.json↔nodes.csv diverso")
    if c_meta != d_meta:
        problems.append("metadata nodes.csv↔graph.db diverso")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Export V7 storage trio from graph.json")
    ap.add_argument("--bundle", type=Path,
                    help="bundle dir containing graph.json; outputs written here")
    ap.add_argument("--graph", type=Path, help="explicit graph.json path")
    ap.add_argument("--out", type=Path, help="explicit output dir")
    a = ap.parse_args()

    if a.bundle:
        graph_path, out_dir = a.bundle / "graph.json", a.bundle
    elif a.graph and a.out:
        graph_path, out_dir = a.graph, a.out
    else:
        ap.error("serve --bundle, oppure --graph e --out")

    graph = json.loads(graph_path.read_text(encoding="utf-8"))

    errs = validate_graph(graph)
    if errs:
        print("graph.json non esportabile:")
        for e in errs[:20]:
            print("   -", e)
        return 1

    stats = export(graph, out_dir)
    print(f"[storage_export] {stats['nodes']} nodi / {stats['edges']} archi → {out_dir}")

    problems = verify(out_dir, graph)
    if problems:
        print("[storage_export] RICONCILIAZIONE FALLITA:")
        for p in problems:
            print("   -", p)
        return 1
    print("[storage_export] riconciliazione OK — graph.json ↔ CSV ↔ SQLite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
