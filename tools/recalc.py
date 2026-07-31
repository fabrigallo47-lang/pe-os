#!/usr/bin/env python3
"""Deterministic recalculation engine — zero LLM.

When a claim value changes, this engine:
  1. Finds all derived claims that rest-on the changed claim (directly or transitively).
  2. Marks them stale.
  3. For claims with a machine-executable formula, recomputes the value.
  4. Returns the full propagation report.

Machine-executable formulas are recognised by the `formula-key` field on a claim.
Unknown/narrative derivations are marked stale but not recalculated (human review needed).

Usage:
    from recalc import recalc, FORMULAS
    result = recalc(con, deal, changed_claim_id, new_value)
    # result.stale  → list of (claim_id, old_value, new_value|None)
    # result.order  → topological order of propagation
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


# ─── registered formulas ───────────────────────────────────────────────────────
# Each formula receives a dict of {claim_id: numeric_value} for its rests-on
# inputs and returns the new numeric value (or None if cannot compute).

FORMULAS: dict[str, Any] = {
    # opening firm EBITDA = reported_ebitda + add_backs - reserves
    "c-keystone-178": lambda v: (
        v.get("c-keystone-039", 0)
        + v.get("c-keystone-173", 0)
        + v.get("c-keystone-174", 0)   # negative
        + v.get("c-keystone-175", 0)   # negative
        + v.get("c-keystone-176", 0)   # negative
        + v.get("c-keystone-177", 0)   # negative
    ),
    # firm view EBITDA = QoE EBITDA − reserves (values stored as negative via parens notation)
    "c-keystone-076": lambda v: (
        v.get("c-keystone-075", 0)
        + v.get("c-keystone-174", 0)   # parsed as negative: ($0.20m)
        + v.get("c-keystone-175", 0)   # parsed as negative: ($0.15m)
        + v.get("c-keystone-176", 0)   # parsed as negative: ($0.10m)
        + v.get("c-keystone-177", 0)   # parsed as negative: ($0.05m)
    ),
    # opening equity = sponsor equity + rollover - fees
    "c-keystone-058": lambda v: (
        v.get("c-keystone-031", 0)
        + v.get("c-keystone-030", 0)
        - v.get("c-keystone-057", 0)
    ),
    # opening net leverage = net debt / firm EBITDA
    "c-keystone-125": lambda v: (
        v.get("c-keystone-126", 0) / v.get("c-keystone-178", 1)
        if v.get("c-keystone-178", 0) != 0 else None
    ),
    # exit EV = exit EBITDA × exit multiple
    "c-keystone-365": lambda v: (
        v.get("c-keystone-362", 0) * v.get("c-keystone-062", 0)
    ),
    # seller equity = EV - net debt
    "c-keystone-029": lambda v: (
        v.get("c-keystone-025", 0) - v.get("c-keystone-028", 0)
    ),
    "c-keystone-080": lambda v: (
        v.get("c-keystone-025", 0) - v.get("c-keystone-028", 0)
    ),
}


# ─── numeric value parser ──────────────────────────────────────────────────────

def _parse_numeric(value: str | None) -> float | None:
    """Extract a leading numeric from a claim value string, or None.

    Accounting negatives in parens — e.g. ($0.20m) or (0.20) — are returned as negative.
    """
    if value is None:
        return None
    import re
    s = str(value).replace(",", "").replace("$", "").replace("mm", "").replace("m", "")
    # Parenthetical accounting negative: ($0.20) or (0.20)
    paren = re.search(r"\(\s*([\d.]+)\s*\)", s)
    if paren:
        try:
            return -float(paren.group(1))
        except ValueError:
            pass
    # Plain signed numeric
    m = re.search(r"[-+]?\d[\d]*\.?\d*", s)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None


# ─── graph helpers ─────────────────────────────────────────────────────────────

def _build_rests_on_graph(con: sqlite3.Connection, deal: str) -> dict[str, list[str]]:
    """Return {claim_id: [claim_ids it rests on]}."""
    rows = con.execute(
        "SELECT id, frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,)
    ).fetchall()
    graph: dict[str, list[str]] = {}
    for cid, fm_raw in rows:
        fm = json.loads(fm_raw)
        rests = fm.get("rests-on", []) or []
        deps = []
        for r in rests:
            rid = str(r).strip("[] ").replace("[[", "").replace("]]", "")
            if rid:
                deps.append(rid)
        graph[cid] = deps
    return graph


def _reverse_graph(g: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return {claim_id: [claims that depend on it]}."""
    rev: dict[str, list[str]] = {k: [] for k in g}
    for node, deps in g.items():
        for dep in deps:
            rev.setdefault(dep, []).append(node)
    return rev


def _topo_descendants(start: str, rev: dict[str, list[str]]) -> list[str]:
    """BFS downstream from start, returns list in propagation order."""
    visited, queue, order = set(), [start], []
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        queue.extend(rev.get(node, []))
    return order[1:]  # exclude start itself


# ─── main entry point ──────────────────────────────────────────────────────────

@dataclass
class PropagationResult:
    changed: str
    old_value: str | None
    new_value: str
    stale: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    recomputed: list[tuple[str, float | None]] = field(default_factory=list)
    order: list[str] = field(default_factory=list)


def recalc(
    con: sqlite3.Connection,
    deal: str,
    changed_claim_id: str,
    new_value: str,
) -> PropagationResult:
    """Propagate a claim value change, recomputing derived claims where possible."""
    graph = _build_rests_on_graph(con, deal)
    rev = _reverse_graph(graph)

    # Get old value
    row = con.execute("SELECT frontmatter FROM nodes WHERE id=?", (changed_claim_id,)).fetchone()
    old_value = json.loads(row[0]).get("value") if row else None

    order = _topo_descendants(changed_claim_id, rev)
    result = PropagationResult(
        changed=changed_claim_id,
        old_value=str(old_value) if old_value else None,
        new_value=new_value,
        order=order,
    )

    # Build current value map (parse numerics)
    value_map: dict[str, float | None] = {}
    for cid, _ in con.execute("SELECT id, frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,)).fetchall():
        row2 = con.execute("SELECT frontmatter FROM nodes WHERE id=?", (cid,)).fetchone()
        if row2:
            val = json.loads(row2[0]).get("value")
            value_map[cid] = _parse_numeric(val)
    # Override with the new value
    value_map[changed_claim_id] = _parse_numeric(new_value)

    for cid in order:
        row3 = con.execute("SELECT frontmatter FROM nodes WHERE id=?", (cid,)).fetchone()
        if not row3:
            continue
        fm = json.loads(row3[0])
        old = fm.get("value")
        ep = fm.get("epistemic", "")

        if ep != "derived":
            result.stale.append((cid, str(old) if old else None, None))
            continue

        formula = FORMULAS.get(cid)
        if formula:
            try:
                new_num = formula(value_map)
                value_map[cid] = new_num
                new_val = f"{new_num:.2f}" if new_num is not None else None
            except Exception:
                new_val = None
        else:
            new_val = None  # cannot auto-recompute; mark stale

        result.stale.append((cid, str(old) if old else None, new_val))
        if new_val is not None:
            result.recomputed.append((cid, float(new_val)))

    return result


def report(result: PropagationResult) -> str:
    """Human-readable propagation report."""
    lines = [
        f"Changed: {result.changed}",
        f"  {result.old_value!r} → {result.new_value!r}",
        f"Propagation order ({len(result.order)} descendants):",
    ]
    for cid, old, new in result.stale:
        if new is not None:
            lines.append(f"  ✓ {cid}: {old!r} → {new!r} (recomputed)")
        else:
            lines.append(f"  ⚠ {cid}: {old!r} → STALE (formula not registered)")
    return "\n".join(lines)


def mark_stale(deal: str, changed_claim_id: str, vault_root=None) -> list[str]:
    """Write stale:true into all derived descendants in the vault.

    Returns list of claim IDs marked stale.
    """
    import sys
    from pathlib import Path as _Path

    if vault_root is None:
        vault_root = ROOT / "vault"

    sys.path.insert(0, str(ROOT / "tools"))
    import indexer
    con = sqlite3.connect(indexer.DB)

    graph = _build_rests_on_graph(con, deal)
    rev = _reverse_graph(graph)
    order = _topo_descendants(changed_claim_id, rev)

    claims_dir = _Path(vault_root) / "deals" / deal / "claims"
    marked = []

    for cid in order:
        row = con.execute("SELECT frontmatter, path FROM nodes WHERE id=? AND type='claim'", (cid,)).fetchone()
        if not row:
            continue
        fm = json.loads(row[0])
        if fm.get("epistemic") != "derived":
            continue
        path_str = row[1]  # 'deals/keystone/claims/c-keystone-076.md'
        if path_str:
            fpath = _Path(vault_root) / path_str
        else:
            fpath = claims_dir / f"{cid}.md"
        if not fpath.exists():
            continue

        text = fpath.read_text(encoding="utf-8")
        if "stale: true" in text:
            marked.append(cid)
            continue
        # Insert stale: true before written-by or before closing ---
        if "stale:" in text:
            import re as _re
            text = _re.sub(r"stale:\s*\S+", "stale: true", text)
        elif "written-by:" in text:
            text = text.replace("written-by:", "stale: true\nwritten-by:", 1)
        else:
            text = text.replace("---\n\n#", "stale: true\n---\n\n#", 1)
        fpath.write_text(text, encoding="utf-8")
        marked.append(cid)

    return marked


def clear_stale(deal: str, claim_id: str, vault_root=None) -> bool:
    """Remove stale: true from a claim file (after human review/acceptance)."""
    from pathlib import Path as _Path
    if vault_root is None:
        vault_root = ROOT / "vault"
    fpath = _Path(vault_root) / "deals" / deal / "claims" / f"{claim_id}.md"
    if not fpath.exists():
        return False
    text = fpath.read_text(encoding="utf-8")
    import re as _re
    new_text = _re.sub(r"\nstale: true", "", text)
    if new_text != text:
        fpath.write_text(new_text, encoding="utf-8")
        return True
    return False


def query_stale(con: sqlite3.Connection, deal: str) -> list[dict]:
    """Return all stale claims for a deal (reads from index)."""
    rows = con.execute(
        "SELECT id, frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,)
    ).fetchall()
    stale = []
    for cid, fm_raw in rows:
        fm = json.loads(fm_raw)
        if fm.get("stale") is True or fm.get("stale") == "true":
            stale.append({
                "id": cid,
                "subject": fm.get("subject"),
                "value": fm.get("value"),
                "epistemic": fm.get("epistemic"),
                "derivation": fm.get("derivation"),
            })
    return stale


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, str(Path(__file__).parent))
    import indexer

    p = argparse.ArgumentParser()
    p.add_argument("deal")
    p.add_argument("claim_id")
    p.add_argument("new_value")
    args = p.parse_args()

    if not indexer.DB.exists():
        sys.exit("no index — run `make index` first")
    con = sqlite3.connect(indexer.DB)
    result = recalc(con, args.deal, args.claim_id, args.new_value)
    print(report(result))
    print(json.dumps({
        "changed": result.changed,
        "order": result.order,
        "recomputed": result.recomputed,
        "stale_count": len(result.stale),
    }, indent=2))
