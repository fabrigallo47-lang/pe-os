#!/usr/bin/env python3
"""Vault -> SQLite derived index. Rebuilt from scratch on every run; never authoritative.

Usage:
    python3 tools/indexer.py            # rebuild .index/vault.db
    python3 tools/indexer.py --report   # rebuild + print open questions, contradiction candidates, unbound claims

Canned queries (sqlite3 .index/vault.db):
    -- open questions for a deal
    SELECT id, title, state FROM nodes WHERE type='question' AND state IN ('open','reducing') AND deal='<deal>';
    -- contradiction candidates: same subject, >1 distinct value
    SELECT deal, subject, COUNT(DISTINCT value) FROM nodes WHERE type='claim'
      GROUP BY deal, subject HAVING COUNT(DISTINCT value) > 1;
    -- unbound claims
    SELECT n.id, n.subject FROM nodes n WHERE n.type='claim'
      AND NOT EXISTS (SELECT 1 FROM edges e WHERE e.src=n.id AND e.rel='bears-on');
    -- dependency fan-in: which open questions the structure leans on
    SELECT dst, COUNT(*) c FROM edges WHERE rel IN ('depends-on','parent') GROUP BY dst ORDER BY c DESC;
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: run `make setup` (or: python3 -m pip install pyyaml)")

import os

ROOT = Path(__file__).resolve().parent.parent
# On serverless the repo is read-only: the vault lives in a /tmp mirror synced
# from Blob storage, and the derived index in /tmp too.
VAULT = Path(os.environ["PEOS_VAULT"]) if os.environ.get("PEOS_VAULT") else ROOT / "vault"
DB = Path(os.environ["PEOS_DB"]) if os.environ.get("PEOS_DB") else ROOT / ".index" / "vault.db"

# frontmatter field -> edge relation
LINK_FIELDS = {
    "parent": "parent",
    "deal": "deal",
    "question-type": "question-type",
    "depends-on": "depends-on",
    "decomposes-into": "decomposes-into",
    "bears-on": "bears-on",
    "rests-on": "rests-on",
    "supersedes": "supersedes",
    "relates-to": "relates-to",
    "tests": "tests",
    "tied-to": "tied-to",
    "basis": "basis",
    "uses": "uses",
    "decision": "decision",
    "company": "company",
    "owner": "owner",
}

WIKILINK = re.compile(r"\[\[([^\]|#]+)")


def parse_note(path: Path) -> tuple[dict, str] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as exc:
        print(f"  ! bad frontmatter in {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
        return None
    return fm, text[end + 4 :]


def links_of(value) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        m = WIKILINK.search(str(item))
        out.append(m.group(1).strip() if m else str(item).strip())
    return [x for x in out if x]


def build() -> sqlite3.Connection:
    """Atomic rebuild: write to a temp DB, then os.replace — concurrent readers
    (server + agents) never see a half-built index."""
    import os
    DB.parent.mkdir(exist_ok=True)
    tmp = DB.with_suffix(f".tmp{os.getpid()}")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(
        """
        CREATE TABLE nodes (id TEXT PRIMARY KEY, type TEXT, path TEXT, title TEXT,
                            state TEXT, epistemic TEXT, subject TEXT, value TEXT,
                            deal TEXT, frontmatter TEXT);
        CREATE TABLE edges (src TEXT, dst TEXT, rel TEXT);
        CREATE INDEX idx_edges_src ON edges(src, rel);
        CREATE INDEX idx_edges_dst ON edges(dst, rel);
        CREATE INDEX idx_nodes_subject ON nodes(deal, subject);
        """
    )
    skipped = 0
    for path in sorted(VAULT.rglob("*.md")):
        if path.is_relative_to(VAULT / "ontology"):
            continue  # schemas describe the graph; they are not in it
        parsed = parse_note(path)
        if parsed is None:
            skipped += 1
            continue
        fm, body = parsed
        node_id = str(fm.get("id") or path.stem)
        title_m = re.search(r"^# (.+)$", body, re.MULTILINE)
        deal = links_of(fm.get("deal"))
        if not deal and path.is_relative_to(VAULT / "deals"):
            deal = [path.relative_to(VAULT / "deals").parts[0]]
        source = fm.get("source") or {}
        con.execute(
            "INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                node_id,
                fm.get("type"),
                str(path.relative_to(VAULT)),
                title_m.group(1).strip() if title_m else path.stem,
                fm.get("state"),
                fm.get("epistemic"),
                fm.get("subject"),
                str(fm.get("value")) if fm.get("value") is not None else None,
                deal[0] if deal else None,
                json.dumps({**fm, "source": source}, default=str),
            ),
        )
        for field, rel in LINK_FIELDS.items():
            for dst in links_of(fm.get(field)):
                con.execute("INSERT INTO edges VALUES (?,?,?)", (node_id, dst, rel))
    con.commit()
    n_nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    n_edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    con.close()
    import os
    os.replace(tmp, DB)
    loc = str(DB.relative_to(ROOT)) if DB.is_relative_to(ROOT) else str(DB)
    print(f"indexed {n_nodes} nodes, {n_edges} edges -> {loc}"
          + (f" ({skipped} files without frontmatter skipped)" if skipped else ""))
    return sqlite3.connect(DB)


def report(con: sqlite3.Connection) -> None:
    print("\n## Open questions")
    for row in con.execute(
        "SELECT deal, id, title, state FROM nodes WHERE type='question' "
        "AND state IN ('open','reducing') ORDER BY deal, id"
    ):
        print(f"  [{row[0]}] {row[1]} ({row[3]}): {row[2]}")

    print("\n## Contradiction candidates (same subject, differing values)")
    for row in con.execute(
        "SELECT deal, subject, GROUP_CONCAT(id || '=' || COALESCE(value,'?'), ' | ') "
        "FROM nodes WHERE type='claim' AND subject IS NOT NULL "
        "GROUP BY deal, subject HAVING COUNT(DISTINCT value) > 1"
    ):
        print(f"  [{row[0]}] {row[1]}: {row[2]}")

    print("\n## Unbound claims (bear on no question — possible missing question)")
    for row in con.execute(
        "SELECT id, subject FROM nodes WHERE type='claim' AND id NOT IN "
        "(SELECT src FROM edges WHERE rel='bears-on')"
    ):
        print(f"  {row[0]}: {row[1]}")


if __name__ == "__main__":
    connection = build()
    if "--report" in sys.argv:
        report(connection)
