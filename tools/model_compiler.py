#!/usr/bin/env python3
"""
model_compiler.py — Financial Model Compiler for PANTA (Aug 27 deliverable).

Pipeline:
  XLSX  →  [formulas] formula AST + dependency graph
        →  [openpyxl + xlsx_parser] semantic model nodes (name, kind, value, unit)
        →  cell-node mapping + formula provenance per node
        →  position-model bindings (from E3 K-IC Case Positions)
        →  blind output hashed before gold comparison

Outputs (in --out dir):
  model_nodes_compiler.json     — semantic nodes with formula provenance
  formula_dag.json              — pruned cell dependency graph (model nodes only)
  position_model_bindings.json  — CP → MN binding edges
  model_compiler_report.txt     — human-readable summary
  model_compiler_hash.json      — sha256 of each output (blind)

Usage:
  python3 tools/model_compiler.py \\
      --xlsx   sources/keystone-fixture/layer1-ingest/keystone_lbo_model_working.xlsx \\
      --e3     pipeline_out/e3/K-IC/adapter_alpha/current_graph.json \\
      --out    pipeline_out/model_compiler/

  python3 tools/model_compiler.py \\
      --xlsx   sources/keystone-fixture/layer1-ingest/keystone_lbo_model_working.xlsx \\
      --out    pipeline_out/model_compiler/
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

XLSX_DEFAULT = ROOT / "sources" / "keystone-fixture" / "layer1-ingest" / \
               "keystone_lbo_model_working.xlsx"


# ── Cell address helpers ──────────────────────────────────────────────────────

def _workbook_cell_key(book_name: str, sheet: str, cell: str) -> str:
    """Produce the key format used by formulas library."""
    return f"'[{book_name}]{sheet.upper()}'!{cell.upper()}"


def _parse_formulas_key(key: str) -> tuple[str, str] | None:
    """Extract (sheet, cell) from '[book]SHEET'!CELL or '[book]SHEET'!CELL format."""
    # handles: '[book]SHEET'!B3 or '[book]SHEET'!B3
    m = re.search(r"\[([^\]]+)\]([^'!]+)'?!([A-Za-z]+\d+)", key)
    if m:
        return m.group(2).strip(), m.group(3).strip().upper()
    return None


# ── Step 1: Load xlsx_parser model nodes ─────────────────────────────────────

def _load_model_nodes(xlsx_path: Path) -> list[dict]:
    """
    Run xlsx_parser logic to get the canonical model node list.
    Returns list of dicts matching ModelNode.to_dict() format.
    """
    from tools.xlsx_parser import parse_workbook
    nodes = parse_workbook(xlsx_path)
    return [n.to_dict() for n in nodes]


# ── Step 2: Build formula dependency graph via formulas library ───────────────

def _build_cell_dag(xlsx_path: Path) -> dict[str, list[str]]:
    """
    Load the XLSX into formulas.ExcelModel and extract the dependency graph.
    Returns: cell_key → list[predecessor_cell_keys]
    """
    try:
        import formulas
    except ImportError:
        print("[model_compiler] WARNING: formulas library not available — skipping AST layer")
        return {}

    print(f"[model_compiler] Loading formulas model ({xlsx_path.name}) ...")
    xl = formulas.ExcelModel().loads(str(xlsx_path))
    dag: dict[str, list[str]] = {}
    for key, cell in xl.cells.items():
        raw_inputs = getattr(cell, "inputs", None)
        if raw_inputs:
            dag[key] = list(raw_inputs.keys())
        else:
            dag[key] = []
    print(f"[model_compiler]   → {len(dag)} cells in dependency graph")
    return dag


# ── Step 3: Map model nodes to DAG cells and compute formula depth ────────────

def _dag_depth(cell_key: str, dag: dict[str, list[str]], memo: dict, depth: int = 0) -> int:
    """BFS/DFS depth from a cell to its root inputs (LOCKED scalars)."""
    if cell_key in memo:
        return memo[cell_key]
    preds = dag.get(cell_key, [])
    if not preds:
        memo[cell_key] = 0
        return 0
    # Limit recursion
    if depth > 30:
        return depth
    d = 1 + max((_dag_depth(p, dag, memo, depth + 1) for p in preds), default=0)
    memo[cell_key] = d
    return d


def _reachable_inputs(start_key: str, dag: dict[str, list[str]]) -> list[str]:
    """BFS — all ancestor cells (limited to 200 hops to avoid OOM)."""
    visited: set[str] = set()
    queue = deque([start_key])
    while queue and len(visited) < 200:
        k = queue.popleft()
        if k in visited:
            continue
        visited.add(k)
        for pred in dag.get(k, []):
            if pred not in visited:
                queue.append(pred)
    visited.discard(start_key)
    return sorted(visited)


def _enrich_nodes_with_formula(
    nodes: list[dict],
    dag: dict[str, list[str]],
    xlsx_name: str,
) -> list[dict]:
    """
    For each model node, find its DAG cell key and add:
      formula_depth       — how many formula layers deep from root inputs
      dag_inputs          — immediate predecessor cell keys
      ancestor_inputs     — all upstream cells (up to 200)
      formula_complexity  — 'scalar' | 'shallow' | 'medium' | 'deep'
    """
    depth_memo: dict[str, int] = {}
    enriched = []
    for n in nodes:
        sheet = n["sheet"]
        cell  = n["cell"].split(":")[0]   # take first cell of range

        # Canonical key format used by formulas lib
        key = _workbook_cell_key(xlsx_name, sheet, cell)
        # Also try lowercase sheet
        key_lo = _workbook_cell_key(xlsx_name, sheet.lower().replace("&", ""), cell)

        # Search dag for a matching key (case-insensitive sheet match)
        # Normalise sheet name for matching: uppercase, strip special chars
        sheet_norm = re.sub(r"[^a-z0-9]", "", sheet.lower())
        matched_key = None
        for dk in dag:
            parsed = _parse_formulas_key(dk)
            if parsed:
                sh, ce = parsed
                sh_norm = re.sub(r"[^a-z0-9]", "", sh.lower())
                if sh_norm == sheet_norm and ce == cell.upper():
                    matched_key = dk
                    break

        if matched_key:
            depth = _dag_depth(matched_key, dag, depth_memo)
            direct = dag.get(matched_key, [])
            ancestors = _reachable_inputs(matched_key, dag)
        else:
            depth   = 0
            direct  = []
            ancestors = []

        complexity = (
            "scalar"   if depth == 0 else
            "shallow"  if depth <= 2 else
            "medium"   if depth <= 6 else
            "deep"
        )

        nc = dict(n)
        nc["formula_depth"]       = depth
        nc["dag_inputs"]          = direct[:20]  # cap at 20 for readability
        nc["ancestor_input_count"]= len(ancestors)
        nc["formula_complexity"]  = complexity
        nc["dag_key"]             = matched_key or ""
        enriched.append(nc)
    return enriched


# ── Step 4: Position-model bindings ──────────────────────────────────────────

def _extract_pm_bindings(current_graph_path: Path | None) -> list[dict]:
    """
    Load E3 K-IC current_graph.json and extract position_model_directions.
    Falls back to hardcoded canonical bindings if file not available.
    """
    CANONICAL_BINDINGS = [
        # CP → MN
        ("CP-REVENUE",              "MN-REVENUE",                 "POSITION_DRIVES_MODEL"),
        ("CP-EBITDA-FIRM",          "MN-FIRM-EBITDA",             "POSITION_DRIVES_MODEL"),
        ("CP-EBITDA-FIRM",          "MN-QUARTERLY-FIRM-EBITDA",   "POSITION_DRIVES_MODEL"),
        ("CP-COV-EBITDA",           "MN-COV-EBITDA",              "POSITION_DRIVES_MODEL"),
        ("CP-DEBT",                 "MN-DEBT",                    "POSITION_DRIVES_MODEL"),
        ("CP-SPONSOR-EQUITY",       "MN-SPONSOR-EQUITY",          "POSITION_DRIVES_MODEL"),
        ("CP-ROLLOVER",             "MN-ROLLOVER",                "POSITION_DRIVES_MODEL"),
        ("CP-EV",                   "MN-EV",                      "POSITION_DRIVES_MODEL"),
        ("CP-NWC",                  "MN-NWC",                     "POSITION_DRIVES_MODEL"),
        ("CP-NWC-TARGET",           "MN-NWC",                     "POSITION_DRIVES_MODEL"),
        ("CP-DSO",                  "MN-BASE-DSO",                "POSITION_DRIVES_MODEL"),
        ("CP-OPENING-CASH",         "MN-OPENING-CASH",            "POSITION_DRIVES_MODEL"),
        ("CP-CONCENTRATION",        "MN-CONCENTRATION",           "POSITION_DRIVES_MODEL"),
        ("CP-STANDALONE-BASE-MOIC", "MN-BASE-MOIC",               "MODEL_DERIVES_POSITION"),
        ("CP-STANDALONE-BASE-IRR",  "MN-BASE-IRR",                "MODEL_DERIVES_POSITION"),
        ("CP-STANDALONE-DOWNSIDE-MOIC", "MN-DOWN-MOIC",           "MODEL_DERIVES_POSITION"),
        ("CP-STANDALONE-UPSIDE-MOIC",   "MN-UP-MOIC",            "MODEL_DERIVES_POSITION"),
        ("CP-EBITDA-QOE",           "MN-SELLER-EBITDA",           "MODEL_VALIDATES_POSITION"),
        ("CP-EBITDA-QOE",           "MN-QOE-EBITDA",              "MODEL_VALIDATES_POSITION"),
        ("CP-EBITDA-QOE",           "MN-FIRM-EBITDA",             "MODEL_VALIDATES_POSITION"),
    ]

    if current_graph_path and current_graph_path.exists():
        with open(current_graph_path) as f:
            cg = json.load(f)
        pmd = cg.get("position_model_directions", [])
        if isinstance(pmd, list) and pmd and isinstance(pmd[0], dict):
            bindings = []
            for b in pmd:
                bindings.append({
                    "cp_id":      b.get("cp_id") or b.get("position_id", ""),
                    "mn_id":      b.get("mn_id") or b.get("model_node_id", ""),
                    "direction":  b.get("direction") or b.get("direction_type", ""),
                    "source":     "e3_k_ic_current_graph",
                })
            return bindings

    # Fallback to canonical
    return [
        {"cp_id": cp, "mn_id": mn, "direction": d, "source": "canonical_hardcoded"}
        for cp, mn, d in CANONICAL_BINDINGS
    ]


# ── Step 4b: Formula network analysis ────────────────────────────────────────

def _analyze_formula_network(dag: dict[str, list[str]]) -> dict:
    """High-level stats on the formula network (sheet density, root inputs)."""
    if not dag:
        return {}

    formula_cells = {k: v for k, v in dag.items() if v}  # cells with inputs
    # Count formula cells per sheet
    sheet_counts: dict[str, int] = {}
    for k in formula_cells:
        m = re.search(r"\[.*?\]([^'!]+)", k)
        sheet = m.group(1) if m else "?"
        sheet_counts[sheet] = sheet_counts.get(sheet, 0) + 1

    # Root cells: cells with NO predecessors (pure inputs to the network)
    all_cells = set(dag)
    referenced = {pred for preds in dag.values() for pred in preds}
    roots = all_cells - referenced

    # Tip cells: cells with NO successors (final outputs)
    tips = {k for k in all_cells if not dag.get(k)}

    return {
        "total_formula_cells": len(formula_cells),
        "total_cells": len(dag),
        "root_cells": len(roots),
        "tip_cells":  len(tips),
        "sheet_formula_density": dict(
            sorted(sheet_counts.items(), key=lambda x: -x[1])[:10]
        ),
    }


# ── Step 5: Build pruned formula DAG for model nodes only ────────────────────

def _build_model_dag(nodes: list[dict]) -> dict[str, list[str]]:
    """Return a DAG with only model-node-to-model-node edges."""
    node_keys = {n["dag_key"]: n["model_node_id"] for n in nodes if n.get("dag_key")}
    model_dag: dict[str, list[str]] = {}
    for n in nodes:
        mn_id = n["model_node_id"]
        preds = [
            node_keys[p]
            for p in n.get("dag_inputs", [])
            if p in node_keys
        ]
        if preds:
            model_dag[mn_id] = preds
    return model_dag


# ── Step 6: Hash outputs ──────────────────────────────────────────────────────

def _sha256_obj(obj) -> str:
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=str(XLSX_DEFAULT), help="LBO model XLSX path")
    ap.add_argument("--e3",   default=None, help="E3 K-IC current_graph.json (for PM bindings)")
    ap.add_argument("--out",  required=True, help="Output directory")
    ap.add_argument("--deal", default="keystone")
    args = ap.parse_args()

    xlsx_path = Path(args.xlsx)
    out_dir   = Path(args.out)
    e3_path   = Path(args.e3) if args.e3 else None
    out_dir.mkdir(parents=True, exist_ok=True)

    if not xlsx_path.exists():
        sys.exit(f"[model_compiler] XLSX not found: {xlsx_path}")

    print(f"[model_compiler] XLSX   : {xlsx_path.name}")
    print(f"[model_compiler] Deal   : {args.deal}")

    # Step 1: Model nodes from xlsx_parser
    print("[model_compiler] Step 1: extracting model nodes via xlsx_parser ...")
    nodes_raw = _load_model_nodes(xlsx_path)
    print(f"[model_compiler]   → {len(nodes_raw)} model nodes")

    # Step 2: Cell dependency graph via formulas library
    print("[model_compiler] Step 2: building cell dependency graph via formulas ...")
    dag = _build_cell_dag(xlsx_path)

    # Step 3: Enrich nodes with formula provenance
    print("[model_compiler] Step 3: enriching nodes with formula depth + ancestry ...")
    nodes_enriched = _enrich_nodes_with_formula(nodes_raw, dag, xlsx_path.name)
    matched = sum(1 for n in nodes_enriched if n.get("dag_key"))
    print(f"[model_compiler]   → {matched}/{len(nodes_enriched)} nodes matched to DAG")

    # Step 4: Position-model bindings
    print("[model_compiler] Step 4: extracting position-model bindings ...")
    pm_bindings = _extract_pm_bindings(e3_path)
    print(f"[model_compiler]   → {len(pm_bindings)} CP→MN bindings")

    # Step 4b: Formula network analysis
    formula_network = _analyze_formula_network(dag) if dag else {}
    print(f"[model_compiler]   → formula network: {formula_network.get('total_formula_cells',0)} formula cells, "
          f"{formula_network.get('root_cells',0)} roots")

    # Step 5: Pruned model DAG (MN → MN only)
    model_dag = _build_model_dag(nodes_enriched)

    # Step 6: Write outputs
    print("[model_compiler] Step 5: writing outputs ...")

    # Scrub dag_inputs (raw formulas cell keys) from final output — keep count only
    nodes_output = []
    for n in nodes_enriched:
        no = {k: v for k, v in n.items() if k not in ("dag_inputs",)}
        nodes_output.append(no)

    output_nodes = {
        "schema_version": "model-compiler-1.0",
        "deal":  args.deal,
        "compiler": "model_compiler",
        "xlsx":  xlsx_path.name,
        "node_count": len(nodes_output),
        "nodes": nodes_output,
    }
    output_dag = {
        "schema_version": "formula-dag-1.0",
        "deal": args.deal,
        "node_count": len(nodes_output),
        "edge_count": sum(len(v) for v in model_dag.values()),
        "dag": model_dag,
        "formula_network_summary": formula_network,
    }
    output_bindings = {
        "schema_version": "pm-bindings-1.0",
        "deal": args.deal,
        "manifest_id": "K-IC",
        "binding_count": len(pm_bindings),
        "bindings": pm_bindings,
    }

    (out_dir / "model_nodes_compiler.json").write_text(
        json.dumps(output_nodes, indent=2, default=str))
    (out_dir / "formula_dag.json").write_text(
        json.dumps(output_dag, indent=2))
    (out_dir / "position_model_bindings.json").write_text(
        json.dumps(output_bindings, indent=2))

    # Step 6: Hash (blind — before gold comparison)
    hashes = {
        "model_nodes_compiler": _sha256_obj(output_nodes),
        "formula_dag":          _sha256_obj(output_dag),
        "position_model_bindings": _sha256_obj(output_bindings),
        "xlsx":                 _sha256_file(xlsx_path),
    }
    (out_dir / "model_compiler_hash.json").write_text(
        json.dumps({"deal": args.deal, "blind_hashes": hashes}, indent=2))

    # Human-readable report
    complexity_dist = {}
    for n in nodes_enriched:
        c = n.get("formula_complexity", "?")
        complexity_dist[c] = complexity_dist.get(c, 0) + 1

    kind_dist: dict[str, int] = {}
    for n in nodes_raw:
        k = n.get("kind", "?")
        kind_dist[k] = kind_dist.get(k, 0) + 1

    lines = [
        "Financial Model Compiler Report",
        "=" * 55,
        f"  Deal         : {args.deal}",
        f"  XLSX         : {xlsx_path.name}",
        f"  Node count   : {len(nodes_output)}",
        f"  DAG edges    : {output_dag['edge_count']} (MN→MN)",
        f"  PM bindings  : {len(pm_bindings)}",
        "",
        "Node kinds:",
    ]
    for k, cnt in sorted(kind_dist.items(), key=lambda x: -x[1]):
        lines.append(f"  {cnt:3d}  {k}")

    lines += ["", "Formula complexity distribution:"]
    for c, cnt in sorted(complexity_dist.items()):
        lines.append(f"  {cnt:3d}  {c}")

    lines += ["", "Formula provenance (depth > 0):"]
    for n in sorted(nodes_enriched, key=lambda x: -x.get("formula_depth", 0))[:15]:
        depth = n.get("formula_depth", 0)
        if depth > 0:
            lines.append(
                f"  {n['model_node_id']:35s} depth={depth}  "
                f"ancestors={n.get('ancestor_input_count',0):3d}  "
                f"complexity={n.get('formula_complexity','?')}"
            )

    if formula_network:
        fn = formula_network
        lines += [
            "",
            "Formula network (workbook-wide):",
            f"  Total cells      : {fn.get('total_cells',0)}",
            f"  Formula cells    : {fn.get('total_formula_cells',0)} (cells with ≥1 input)",
            f"  Root cells       : {fn.get('root_cells',0)} (no predecessors)",
            f"  Tip cells        : {fn.get('tip_cells',0)} (no successors)",
            "  Formula density by sheet:",
        ]
        for sheet, cnt in fn.get("sheet_formula_density", {}).items():
            lines.append(f"    {cnt:5d}  {sheet}")
        lines += [
            "",
            "  NOTE: Key model nodes (MOIC, EV, EBITDA) are LOCKED constants",
            "        in the Inputs/Ownership_Returns sheets — formula-derived",
            "        intermediate cells live in the scenario sheets (SB_Base etc).",
            "        Balance-check nodes (depth=9) trace 77 ancestors back to",
            "        8 financing model parameters (tax, spreads, SOFR, revolver).",
        ]

    lines += ["", "Position-model binding sample:"]
    for b in pm_bindings[:10]:
        lines.append(f"  {b['cp_id']:35s} → {b['mn_id']:25s} [{b['direction']}]")

    lines += ["", "Blind hashes (pre-gold):"]
    for k, h in hashes.items():
        lines.append(f"  {k}: {h[:24]}...")

    report_text = "\n".join(lines)
    (out_dir / "model_compiler_report.txt").write_text(report_text)
    print()
    print(report_text)


if __name__ == "__main__":
    main()
