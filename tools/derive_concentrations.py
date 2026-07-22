#!/usr/bin/env python3
"""
Aggregation/Derivation Pass — Customer Concentration (general-purpose).

Reads any data-room artifact that contains a customer schedule table
(detected by "Ultimate Parent" + "% Revenue" columns), groups billing accounts
by ultimate parent, sums revenue percentages, and writes DERIVED claims with a
full derivation chain.

This is the capability that produces machine-computed DERIVED facts — values
not stated in any single document but computable from disclosed granular data.

Usage:
    .venv/bin/python3 tools/derive_concentrations.py                      # all deals
    .venv/bin/python3 tools/derive_concentrations.py --deal keystone      # one deal
    .venv/bin/python3 tools/derive_concentrations.py --file vault/inbox/keystone_data_room_extract.md

Called automatically by tools/extract.py when a customer schedule is detected.
Can also be imported and called as derive_for_artifact(deal, path).
"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents"))

import tools.indexer as indexer
import runtime as rt

VAULT = indexer.VAULT


# ---------------------------------------------------------------------------
# Customer schedule parser — deal-agnostic
# ---------------------------------------------------------------------------

def parse_customer_schedule(text: str) -> list[dict]:
    """Parse any markdown table containing 'Ultimate Parent' and '% Revenue' columns.

    Returns list of {billing_id, billing_account, ultimate_parent, revenue_mm, pct_revenue}.
    Handles multiple table sections; takes the first one with at least 3 data rows.
    """
    rows = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        # Detect header row
        if "| Billing Account ID |" not in line and "billing account id" not in line.lower():
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        # Find column indices
        try:
            id_col = next(j for j, p in enumerate(parts)
                          if "billing account id" in p.lower())
            name_col = next(j for j, p in enumerate(parts)
                            if "billing account" in p.lower() and "id" not in p.lower())
            parent_col = next(j for j, p in enumerate(parts)
                              if "ultimate parent" in p.lower())
            rev_col = next(j for j, p in enumerate(parts)
                           if "revenue" in p.lower() and "$" in p.lower())
            pct_col = next(j for j, p in enumerate(parts)
                           if "% revenue" in p.lower() or "pct" in p.lower())
        except StopIteration:
            continue

        # Parse data rows until we hit a non-table line or a summary/metric row
        batch = []
        for row_line in lines[i + 1:]:
            if not row_line.startswith("|"):
                if batch:
                    break
                continue
            rparts = [p.strip() for p in row_line.split("|") if p.strip() != ""]
            if not rparts or all(set(p) <= {"-", " ", ":"} for p in rparts):
                continue  # separator row
            if len(rparts) <= max(id_col, parent_col, pct_col):
                continue
            billing_id = rparts[id_col] if id_col < len(rparts) else ""
            if not billing_id or billing_id.lower() in ("metric", "| metric"):
                break  # hit a summary section
            try:
                pct = float(rparts[pct_col])
            except (ValueError, IndexError):
                continue
            try:
                rev = float(rparts[rev_col])
            except (ValueError, IndexError):
                rev = 0.0
            batch.append({
                "billing_id": billing_id,
                "billing_account": rparts[name_col] if name_col < len(rparts) else "",
                "ultimate_parent": rparts[parent_col] if parent_col < len(rparts) else "",
                "revenue_mm": rev,
                "pct_revenue": pct,
            })

        if len(batch) >= 3:  # at least 3 rows = a real schedule, not a header artefact
            rows = batch
            break  # take the first valid schedule

    return rows


def group_by_parent(rows: list[dict]) -> dict:
    parents: dict[str, dict] = {}
    for r in rows:
        p = r["ultimate_parent"].strip() or "Unknown"
        if p not in parents:
            parents[p] = {"revenue_mm": 0.0, "pct_total": 0.0, "accounts": []}
        parents[p]["revenue_mm"] += r["revenue_mm"]
        parents[p]["pct_total"] += r["pct_revenue"]
        parents[p]["accounts"].append(r["billing_id"])
    return parents


def has_concentration_table(text: str) -> bool:
    head = text[:8_000].lower()
    return "ultimate parent" in head and ("% revenue" in head or "pct" in head)


# ---------------------------------------------------------------------------
# Claim writer
# ---------------------------------------------------------------------------

def next_claim_id(deal: str) -> str:
    cdir = VAULT / "deals" / deal / "claims"
    existing = sorted(cdir.glob("c-*.md")) if cdir.exists() else []
    if not existing:
        return f"c-{deal}-001"
    n = int(existing[-1].stem.split("-")[-1]) + 1
    return f"c-{deal}-{n:03d}"


def write_concentration_claim(deal: str, parent: str, pct: float, rev: float,
                               accounts: list[str], source_path: pathlib.Path) -> str:
    cid = next_claim_id(deal)
    pct_pct = round(pct * 100, 1)
    accounts_str = ", ".join(accounts)
    parent_slug = re.sub(r"[^a-z0-9]+", "-", parent.lower()).strip("-")
    derivation = (
        f"Sum of {len(accounts)} billing accounts under ultimate parent '{parent}': "
        f"{accounts_str}. "
        f"Individual '% Revenue' values from customer schedule summed: "
        f"{round(pct, 6):.4f} ≈ {pct_pct}%."
    )
    content = f"""---
type: claim
id: {cid}
epistemic: derived
subject: "ultimate-parent customer concentration - {parent_slug}"
value: "{pct_pct}%"
direction: context
bears-on:
  []
rests-on:
  - "vault/inbox/{source_path.name}"
locator: "Customer Revenue Schedule — Ultimate Parent aggregation"
author: "PE OS aggregation/derivation pass"
artifact: "vault/inbox/{source_path.name}"
derivation: "{derivation}"
written-by: extractor-aggregation
---

# ultimate-parent customer concentration — {parent}

Computed by summing {len(accounts)} billing accounts ({accounts_str}) from the customer schedule
in `{source_path.name}`. Total FY revenue: ${rev:.2f}mm representing {pct_pct}% of total.

**Derivation**: {derivation}
"""
    cdir = VAULT / "deals" / deal / "claims"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / f"{cid}.md").write_text(content, encoding="utf-8")
    return cid


# ---------------------------------------------------------------------------
# Public API (called by extract.py and directly)
# ---------------------------------------------------------------------------

def derive_for_artifact(deal: str, artifact: pathlib.Path,
                        min_accounts: int = 2) -> list[str]:
    """Parse artifact, derive concentration claims for multi-account parents.
    Returns list of written claim IDs.
    """
    text = artifact.read_text(encoding="utf-8")
    if not has_concentration_table(text):
        return []

    rows = parse_customer_schedule(text)
    if not rows:
        print(f"  [derive] no parseable schedule in {artifact.name}")
        return []
    print(f"  [derive] parsed {len(rows)} customer rows from {artifact.name}")

    parents = group_by_parent(rows)
    written = []
    for parent, info in sorted(parents.items(), key=lambda x: -x[1]["pct_total"]):
        if len(info["accounts"]) < min_accounts:
            continue
        if info["pct_total"] < 0.005:
            continue
        cid = write_concentration_claim(
            deal, parent, info["pct_total"], info["revenue_mm"],
            info["accounts"], artifact)
        written.append(cid)
        pct_pct = round(info["pct_total"] * 100, 1)
        rt.audit("extractor", "HVA_COMMERCIAL_01", "claims-derived",
                 f"concentration: {parent} = {pct_pct}% ({len(info['accounts'])} accounts) "
                 f"from {artifact.name}", [cid])
        print(f"  [derive] {cid}: {parent} = {pct_pct}%  "
              f"({len(info['accounts'])} accounts: {info['accounts']})")
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deal", help="Only process files for this deal slug")
    parser.add_argument("--file", help="Process exactly this file path")
    parser.add_argument("--min-accounts", type=int, default=2,
                        help="Minimum accounts under one parent to write a derived claim")
    args = parser.parse_args()

    if args.file:
        artifact = pathlib.Path(args.file)
        if not artifact.exists():
            sys.exit(f"File not found: {artifact}")
        deal = rt.deal_for(artifact.name) if not args.deal else args.deal
        if not deal:
            sys.exit(f"Cannot route {artifact.name} to a deal — use --deal")
        written = derive_for_artifact(deal, artifact, args.min_accounts)
        print(f"\nWrote {len(written)} claims. Rebuilding index...")
        indexer.build()
        return

    # Auto-scan inbox for any file with a customer schedule
    inbox = VAULT / "inbox"
    found_any = False
    for f in sorted(inbox.glob("*.md")):
        deal = rt.deal_for(f.name)
        if not deal:
            continue
        if args.deal and deal != args.deal:
            continue
        text = f.read_text(encoding="utf-8")
        if not has_concentration_table(text):
            continue
        print(f"\n--- [{deal}] {f.name} ---")
        written = derive_for_artifact(deal, f, args.min_accounts)
        print(f"  Wrote {len(written)} derived claims")
        found_any = True

    if not found_any:
        print("No inbox files with a customer concentration schedule found.")
        return

    print("\nRebuilding index...")
    indexer.build()
    print("Done.")


if __name__ == "__main__":
    main()
