#!/usr/bin/env python3
"""State-resolution engine — v1 of the workflow backbone executor.

Derives a deal's primary state by REPLAYING its immutable events through the
transition register (sources/workflow-backbone-v1/state_transitions_v1.csv),
per the backbone rules: state comes from authoritative events and unresolved
blockers — never from file recency or labels (spec section 4).

Implemented guards (v1 — the ones our objects can evaluate):
  * T10 gate: no entry into S7_INVESTMENT_DECISION while a critical question
    is open/reducing without risk acceptance (accepted-unresolved).
  * SX entry only via explicit terminal-trigger events (T22).

Usage:
    python3 tools/engine.py <deal-id>            # derive + report
    python3 tools/engine.py <deal-id> --write    # also update deal.md state field
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / ".index" / "vault.db"
BACKBONE = ROOT / "sources" / "workflow-backbone-v1"


def load_transitions() -> list[dict]:
    """Unified table from the machine contracts (final package + v1 aliases)."""
    import contracts
    return contracts.transitions()


def deal_objects(con: sqlite3.Connection, deal: str, obj_type: str) -> list[dict]:
    rows = con.execute(
        "SELECT frontmatter FROM nodes WHERE type=? AND deal=?", (obj_type, deal)
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def open_critical_questions(con: sqlite3.Connection, deal: str) -> list[dict]:
    out = []
    for fm in deal_objects(con, deal, "question"):
        if fm.get("critical") and fm.get("state") in ("open", "reducing"):
            out.append(fm)
    return out


def contradiction_candidates(con: sqlite3.Connection, deal: str) -> list[tuple]:
    return con.execute(
        "SELECT subject, GROUP_CONCAT(id || ' [' || COALESCE(epistemic,'?') || '] = ' || COALESCE(value,'?'), '  |  ') "
        "FROM nodes WHERE type='claim' AND deal=? AND subject IS NOT NULL "
        "GROUP BY subject HAVING COUNT(DISTINCT value) > 1",
        (deal,),
    ).fetchall()


def resolve(deal: str, write: bool = False) -> None:
    if not DB.exists():
        sys.exit("no index — run `make index` first")
    con = sqlite3.connect(DB)
    transitions = load_transitions()

    events = deal_objects(con, deal, "event")
    events.sort(key=lambda e: str(e.get("at", "")))
    if not events:
        sys.exit(f"no events found for deal '{deal}' — the state machine starts at DEAL_REGISTERED")

    crit_open = open_critical_questions(con, deal)

    state, trail, held = "START", [], []
    for ev in events:
        kind = ev.get("kind")
        candidates = [t for t in transitions if t["from"] in (state, "ANY") and kind in t["triggers"]]
        if not candidates:
            trail.append(f"  {ev.get('at','?')}  {kind:<40} (no transition from {state} — recorded, no move)")
            continue
        t = candidates[0]
        # Guard T10: block entry to S7 while critical questions are open and unaccepted.
        if t["to"] == "S7_INVESTMENT_DECISION" and crit_open:
            held.append(
                f"transition {t['id']} → S7 HELD by guard: {len(crit_open)} critical question(s) "
                "open without risk acceptance"
            )
            trail.append(f"  {ev.get('at','?')}  {kind:<40} BLOCKED at guard ({t['id']} → {t['to']})")
            continue
        state = t["to"]
        trail.append(f"  {ev.get('at','?')}  {kind:<40} {t['from']} → {state}   ({t['id']})")

    print(f"\n# Deal: {deal}")
    print(f"\n## Derived primary state: {state}\n")
    print("## Event replay")
    print("\n".join(trail))

    if held:
        print("\n## Held transitions (guards)")
        for h in held:
            print(f"  ! {h}")

    print("\n## Unresolved blockers")
    if crit_open:
        for q in crit_open:
            print(f"  critical question {q['id']} [{q.get('state')}]: routes to {q.get('target-workstream','?')}")
    contras = contradiction_candidates(con, deal)
    for subject, detail in contras:
        print(f"  contradiction on '{subject}': {detail}")
    if not crit_open and not contras:
        print("  none")

    nxt = [t for t in transitions if t["from"] == state]
    print("\n## Available transitions from here")
    for t in nxt:
        print(f"  {t['id']}: --[{' | '.join(t['triggers'])}]--> {t['to']}")

    if write:
        deal_file = ROOT / "vault" / "deals" / deal / "deal.md"
        text = deal_file.read_text(encoding="utf-8")
        new = re.sub(r"^state: .*$", f"state: {state}", text, count=1, flags=re.MULTILINE)
        if new != text:
            deal_file.write_text(new, encoding="utf-8")
            print(f"\n[written] deal.md state ← {state} (derived, per invariant 10)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: engine.py <deal-id> [--write]")
    resolve(args[0], write="--write" in sys.argv)
