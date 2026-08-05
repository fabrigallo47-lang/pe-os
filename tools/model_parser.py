#!/usr/bin/env python3
"""Deterministic model parser — zero LLM.

Reads markdown model files (vault/inbox/keystone-model-part*.md) and extracts
the Excel formula dependency graph as typed claims.

Each cell → one claim node. DERIVED cells get:
  - rests-on: [claim_ids of their inputs]
  - derivation: the formula text

Multi-column tables (QoE bridge, scenario sheets) produce one claim per
(field × column/perimeter) pair. Multi-year tables produce one claim per
(field × year) pair.

Usage:
    python3 tools/model_parser.py keystone vault/inbox/keystone-model-part1.md [part2 ...]
    python3 tools/model_parser.py keystone --all     # parse all model files for deal
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

PERIMETER_COLS = {"Reported", "Seller View", "QoE View", "Firm View", "Covenant View"}

METRIC_MAP: list[tuple[str, str]] = [
    ("adjusted ebitda", "ebitda"), ("firm ebitda", "ebitda"),
    ("covenant ebitda", "ebitda"), ("ebitda", "ebitda"),
    ("revenue", "revenue"), ("sales", "revenue"), ("bookings", "revenue"),
    ("term loan", "debt"), ("net debt", "debt"), ("first-lien", "debt"), ("debt", "debt"),
    ("sponsor equity", "equity"), ("equity value", "equity"), ("equity", "equity"),
    ("irr", "irr"), ("moic", "irr"), ("return", "irr"),
    ("net leverage", "leverage"), ("leverage", "leverage"),
    ("exit multiple", "multiple"), ("multiple", "multiple"),
    ("headcount", "headcount"), ("employee", "headcount"), ("fte", "headcount"),
    ("gross margin", "margin"), ("ebitda margin", "margin"), ("margin", "margin"),
    ("growth", "growth"), ("capex", "capex"), ("capital expenditure", "capex"),
    ("free cash", "cash"), ("cash", "cash"),
    ("working capital", "working-capital"), ("nwc", "working-capital"),
    ("concentration", "customer-concentration"), ("churn", "churn"),
    ("dso", "working-capital"), ("wip", "working-capital"),
]

YEAR_RE = re.compile(r'\b(FY\s*)?(\d{4}[A-Z]?)\b')

# Sheets containing individual-level roster data — too granular for epistemic claims
ROSTER_SHEETS = {"employees", "employee", "headcount_detail", "roster", "personnel", "staff"}


@dataclass
class ModelCell:
    sheet: str
    field: str
    value: str
    unit: str = ""
    status: str = "LOCKED"        # LOCKED | DERIVED | MODEL ASSUMPTION
    derivation_text: str = ""
    period: Optional[str] = None
    perimeter: Optional[str] = None
    artifact_path: str = ""
    # resolved after full parse
    claim_id: str = ""
    rests_on: list[str] = field(default_factory=list)


def _slug(s: str, max_len: int = 40) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:max_len]


def _stable_id(deal: str, sheet: str, f: str, perimeter: str = "") -> str:
    key = f"{deal}|{sheet}|{f}|{perimeter}"
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"mp-{deal}-{_slug(sheet)}-{h}"


def _detect_metric(field_name: str) -> Optional[str]:
    fl = field_name.lower()
    for kw, cat in METRIC_MAP:
        if kw in fl:
            return cat
    return None


def _parse_year(h: str) -> Optional[str]:
    h = h.strip()
    if re.search(r'\bLTM\b', h, re.I):
        return "LTM"
    if re.search(r'\bOpening\b', h, re.I):
        return "Opening"
    m = YEAR_RE.search(h)
    if m:
        return f"FY{m.group(2)}" if not m.group(1) else f"FY{m.group(2)}"
    return None


def _status_epistemic(status: str) -> str:
    s = (status or "").upper()
    if "DERIVED" in s:
        return "derived"
    return "asserted"


# ─── table parsers ─────────────────────────────────────────────────────────────

def _rows(table_text: str) -> list[list[str]]:
    out = []
    for line in table_text.strip().splitlines():
        line = line.strip()
        if line.startswith('|'):
            parts = [c.strip() for c in line.split('|')[1:-1]]
            out.append(parts)
    return out


def _parse_inputs_table(rows: list[list[str]], sheet: str, artifact: str) -> list[ModelCell]:
    if len(rows) < 2:
        return []
    headers = [h.lower() for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers)}

    def col(row, name):
        i = idx.get(name, -1)
        return row[i] if 0 <= i < len(row) else ""

    cells = []
    for row in rows[1:]:
        f = col(row, 'field') or (row[0] if row else "")
        v = col(row, 'value') or (row[1] if len(row) > 1 else "")
        if not f or not v:
            continue
        # skip section headers (no numeric value, no LOCKED/DERIVED)
        status = col(row, 'status')
        source = next((row[i] for i, h in enumerate(headers)
                       if ('source' in h or 'ledger' in h or 'notes' in h) and i < len(row)), "")
        unit = col(row, 'unit')
        if not status and not re.search(r'[\d.,$%-]', v):
            continue

        cells.append(ModelCell(
            sheet=sheet, field=f, value=v, unit=unit,
            status=status or "LOCKED", derivation_text=source,
            period="Opening", perimeter="Firm View",
            artifact_path=artifact,
        ))
    return cells


def _parse_multiview_table(rows: list[list[str]], sheet: str, artifact: str) -> list[ModelCell]:
    """Table where columns = perimeter views: Reported | Seller View | QoE View | Firm | Covenant."""
    if len(rows) < 2:
        return []
    headers = rows[0]
    view_cols: dict[int, str] = {}
    source_col: Optional[int] = None
    for i, h in enumerate(headers):
        if h in PERIMETER_COLS:
            view_cols[i] = h
        elif 'source' in h.lower() or 'treatment' in h.lower():
            source_col = i

    if not view_cols:
        return []

    # Detect period from sheet context
    period = "FY2025 LTM"

    cells = []
    is_bridge = "Bridge" in sheet or "QoE" in sheet
    for row in rows[1:]:
        f = row[0] if row else ""
        if not f or f.lower() in ('adjustment', 'description', 'field'):
            continue
        is_total = any(t in f.lower() for t in ('adjusted ebitda', 'total adjusted', 'total'))
        source = row[source_col] if source_col is not None and source_col < len(row) else ""

        for col_i, perimeter in view_cols.items():
            val = row[col_i] if col_i < len(row) else ""
            if not val:
                continue
            # In bridges, skip pure-zero adjustment rows (no information)
            if is_bridge and val == '0' and not is_total:
                continue

            cells.append(ModelCell(
                sheet=sheet, field=f, value=val,
                status="DERIVED" if is_total else "LOCKED",
                derivation_text=source if is_total else source,
                period=period, perimeter=perimeter,
                artifact_path=artifact,
            ))
    return cells


def _parse_multiyear_table(rows: list[list[str]], headers: list[str], sheet: str, artifact: str) -> list[ModelCell]:
    """Table where columns = fiscal years."""
    year_cols: dict[int, str] = {}
    for i, h in enumerate(headers[1:], 1):
        yr = _parse_year(h)
        if yr:
            year_cols[i] = yr

    if not year_cols:
        return []

    cells = []
    for row in rows[1:]:
        f = row[0] if row else ""
        if not f or f.lower() in ('field', 'driver', 'case / driver', ''):
            continue
        for col_i, period in year_cols.items():
            val = row[col_i] if col_i < len(row) else ""
            if not val:
                continue
            cells.append(ModelCell(
                sheet=sheet, field=f, value=val,
                status="LOCKED", period=period,
                artifact_path=artifact,
            ))
    return cells


def _find_header_row(rows: list[list[str]]) -> int:
    """Return the index of the actual column header row (may not be row 0 if row 0 is a title)."""
    for i, row in enumerate(rows[:3]):
        non_empty = [c for c in row if c]
        joined = " ".join(non_empty).lower()
        # Header rows contain known column labels
        if any(k in joined for k in ('field', 'status', 'adjustment', 'driver', 'case')):
            return i
        if any(h in PERIMETER_COLS for h in row):
            return i
        if sum(1 for h in row[1:] if _parse_year(h)) >= 2:
            return i
    return 0  # fallback to first row


def _parse_table(table_text: str, sheet: str, artifact: str) -> list[ModelCell]:
    all_rows = _rows(table_text)
    if len(all_rows) < 2:
        return []

    hdr_idx = _find_header_row(all_rows)
    headers = all_rows[hdr_idx]
    rows = all_rows[hdr_idx:]  # header + data rows

    # Detect type
    is_inputs = any('status' in h.lower() for h in headers)
    is_multiview = any(h in PERIMETER_COLS for h in headers)
    has_years = sum(1 for h in headers[1:] if _parse_year(h)) >= 2

    if is_inputs:
        return _parse_inputs_table(rows, sheet, artifact)
    elif is_multiview:
        return _parse_multiview_table(rows, sheet, artifact)
    elif has_years:
        return _parse_multiyear_table(rows, headers, sheet, artifact)
    else:
        return []  # AR detail / invoice tables — too granular for claims


# ─── main parser ───────────────────────────────────────────────────────────────

def parse_file(path: Path, deal: str) -> list[ModelCell]:
    text = path.read_text(encoding="utf-8")
    cells: list[ModelCell] = []

    # Split into sheet blocks
    blocks = re.split(r'^##\s+Sheet:\s*', text, flags=re.MULTILINE)
    for block in blocks[1:]:
        lines = block.split('\n')
        sheet_name = lines[0].strip()
        if sheet_name.lower() in ROSTER_SHEETS:
            continue  # skip individual-level roster sheets — too granular for claims
        body = '\n'.join(lines[1:])

        # Find tables
        for table_text in re.findall(r'\|.+(?:\n\|.+)+', body):
            cells.extend(_parse_table(table_text, sheet_name, str(path)))

    return cells


# ─── dependency resolution ─────────────────────────────────────────────────────

def _cell_key(c: ModelCell) -> str:
    return f"{c.sheet}||{c.field}||{c.perimeter or ''}"


def resolve_dependencies(cells: list[ModelCell], deal: str) -> list[ModelCell]:
    """
    Assign stable IDs and resolve rests-on for DERIVED cells.

    For QoE bridge totals: the "Adjusted EBITDA" row depends on all non-zero
    adjustment rows in the same perimeter column.

    For Inputs DERIVED cells: parse derivation text to find referenced fields.
    """
    # Assign stable IDs
    for c in cells:
        c.claim_id = _stable_id(deal, c.sheet, c.field, c.perimeter or "")

    # Build lookups
    key_to_id: dict[str, str] = {_cell_key(c): c.claim_id for c in cells}
    field_lower_to_cells: dict[str, list[ModelCell]] = {}
    for c in cells:
        field_lower_to_cells.setdefault(c.field.lower(), []).append(c)

    # Common abbreviations used in derivation text
    ALIASES: dict[str, list[str]] = {
        "ev": ["enterprise value"],
        "ebitda": ["adjusted ebitda", "firm ebitda", "opening firm ebitda", "opening covenant ebitda"],
        "seller net debt": ["seller net debt and debt-like items"],
        "rollover": ["seller rollover"],
        "net debt": ["seller net debt and debt-like items"],
        "financing fees": ["financing fees and oid"],
    }

    for c in cells:
        if "DERIVED" not in c.status.upper():
            continue
        deriv = c.derivation_text.lower()

        # QoE bridge total: depends on all adjustment rows in same perimeter
        is_qoe_total = ("Adjusted EBITDA" in c.field or "total" in c.field.lower()) and c.perimeter
        if is_qoe_total:
            same_view = [
                x for x in cells
                if x.sheet == c.sheet and x.perimeter == c.perimeter
                and x.field != c.field and "DERIVED" not in x.status.upper()
            ]
            c.rests_on = [x.claim_id for x in same_view]
            c.derivation_text = (
                f"Sum of adjustments in {c.perimeter} column: "
                + " + ".join(x.field for x in same_view[:6])
                + ("..." if len(same_view) > 6 else "")
            )
            continue

        # Text-based reference resolution
        found: list[str] = []
        for candidate_field, dep_cells in field_lower_to_cells.items():
            if len(candidate_field) < 3 or candidate_field == c.field.lower():
                continue
            # Check direct name match in derivation text
            if candidate_field in deriv:
                same_view = [x for x in dep_cells if x.perimeter == c.perimeter or x.perimeter is None]
                if same_view:
                    found.append(same_view[0].claim_id)
                    continue
            # Check aliases
            for alias, targets in ALIASES.items():
                if alias in deriv and candidate_field in targets:
                    same_view = [x for x in dep_cells if x.perimeter == c.perimeter or x.perimeter is None]
                    if same_view:
                        found.append(same_view[0].claim_id)

        c.rests_on = list(dict.fromkeys(found))  # deduplicate, preserve order

    return cells


# ─── vault writer ──────────────────────────────────────────────────────────────

def write_claims(cells: list[ModelCell], deal: str, artifact_id: str, vault: Path) -> list[str]:
    """Write claim files; update last-seen if already exists. Returns IDs written."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    claims_dir = vault / "deals" / deal / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for c in cells:
        if not c.claim_id:
            continue
        fpath = claims_dir / f"{c.claim_id}.md"

        if fpath.exists():
            # Update last-seen only
            text = fpath.read_text(encoding="utf-8")
            if f"last-seen: {today}" not in text:
                text = re.sub(r"last-seen:\s*\S+", f"last-seen: {today}", text)
                fpath.write_text(text, encoding="utf-8")
            written.append(c.claim_id)
            continue

        epistemic = _status_epistemic(c.status)
        rests_str = ", ".join(f'"[[{r}]]"' for r in c.rests_on)
        metric = _detect_metric(c.field)
        art_line = f'"[[{artifact_id}]]"' if artifact_id else "null"
        period_line = f'"{c.period}"' if c.period else "null"
        perimeter_line = f'"{c.perimeter}"' if c.perimeter else "null"
        metric_line = metric if metric else "null"
        derivation_line = json.dumps(c.derivation_text) if epistemic == "derived" and c.derivation_text else "null"

        body = f"""---
type: claim
id: {c.claim_id}
epistemic: {epistemic}
subject: "{c.sheet} / {c.field}"
value: "{c.value}"
bears-on: []
direction: context
source:
  artifact: "{c.artifact_path}"
  locator: "Sheet: {c.sheet}"
  author: "model"
  date: null
artifact-id: {art_line}
company: null
author-entity: null
digital-source: null
metric-category: {metric_line}
period: {period_line}
perimeter: {perimeter_line}
perimeter-note: null
part-of: null
derivation: {derivation_line}
rests-on: [{rests_str}]
supersedes: null
extracted-by: model-parser
extracted: {today}
last-seen: {today}
stale: false
---

{c.sheet} / {c.field}: {c.value}{(" " + c.unit) if c.unit else ""}
"""
        fpath.write_text(body, encoding="utf-8")
        written.append(c.claim_id)

    return written


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import os
    sys.path.insert(0, str(ROOT / "tools"))

    VAULT = Path(os.environ["PEOS_VAULT"]) if os.environ.get("PEOS_VAULT") else ROOT / "vault"

    p = argparse.ArgumentParser(description="Parse markdown model files into vault claims")
    p.add_argument("deal", help="Deal ID e.g. keystone")
    p.add_argument("files", nargs="*", help="Markdown model files to parse")
    p.add_argument("--all", action="store_true", help="Parse all model files in vault/inbox/")
    p.add_argument("--artifact-id", default="", help="Artifact node ID to link claims to")
    p.add_argument("--dry-run", action="store_true", help="Parse but do not write")
    args = p.parse_args()

    files = []
    if args.all:
        inbox = VAULT / "inbox"
        files = sorted(inbox.glob(f"{args.deal}-model-part*.md"))
        if not files:
            files = sorted(inbox.glob("*model*.md"))
    else:
        files = [Path(f) for f in args.files]

    if not files:
        sys.exit("No files to parse. Specify files or use --all.")

    all_cells: list[ModelCell] = []
    for f in files:
        print(f"Parsing {f.name}...")
        cells = parse_file(f, args.deal)
        print(f"  {len(cells)} cells from {f.name}")
        all_cells.extend(cells)

    print(f"\nTotal cells before dedup: {len(all_cells)}")
    all_cells = resolve_dependencies(all_cells, args.deal)

    # Summary
    by_epistemic = {}
    for c in all_cells:
        ep = _status_epistemic(c.status)
        by_epistemic[ep] = by_epistemic.get(ep, 0) + 1
    print(f"Epistemic breakdown: {by_epistemic}")
    derived_with_deps = [c for c in all_cells if c.rests_on]
    print(f"Derived cells with resolved dependencies: {len(derived_with_deps)}")

    if args.dry_run:
        for c in derived_with_deps[:5]:
            print(f"  {c.claim_id} [{c.sheet}/{c.field}] rests-on: {c.rests_on}")
        return

    written = write_claims(all_cells, args.deal, args.artifact_id, VAULT)
    print(f"\nWrote {len(written)} claim files.")

    # Rebuild index
    try:
        import indexer
        indexer.build()
    except Exception as exc:
        print(f"Index rebuild failed: {exc} — run `make index` manually")


if __name__ == "__main__":
    main()
