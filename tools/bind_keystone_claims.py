#!/usr/bin/env python3
"""
Retroactively bind isolated keystone claims to their questions.

Layer-1 batch-extracted claims (c-keystone-001 to ~270) were extracted with
empty bears-on. This script maps each claim's subject string to the correct
question ID and writes bears-on into the frontmatter.

Run: .venv/bin/python3 tools/bind_keystone_claims.py [--dry-run]
"""

import pathlib, sys, yaml, re, sqlite3

VAULT = pathlib.Path("vault")
DB = pathlib.Path(".index/vault.db")
DRY_RUN = "--dry-run" in sys.argv

# Subject string → keystone question ID
# Derived from claim subjects vs the 12 keystone questions.
SUBJECT_MAP: dict[str, str | None] = {
    # kq-01: Which billing accounts share parent-company relationships?
    "customer parent-company relationships across billing accounts": "kq-01-parent-concentration",
    "largest parent customer share of revenue": "kq-01-parent-concentration",
    "largest parent customer share of revenue - billing-account basis": "kq-01-parent-concentration",
    "top-five customer concentration - billing-account basis": "kq-01-parent-concentration",
    "top-five customer concentration - ultimate-parent basis": "kq-01-parent-concentration",
    "top-ten customer concentration - billing-account basis": "kq-01-parent-concentration",
    "top-ten customer concentration - ultimate-parent basis": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - apex-manufacturing": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - cityworks-municipal-group": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - clinica-health": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - harbor-utilities": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - medcore-health": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - metro-utility-holdings": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - precision-components": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - riverton-industrial-group": "kq-01-parent-concentration",
    "ultimate-parent customer concentration - state-infrastructure-authority": "kq-01-parent-concentration",

    # kq-02: Is revenue recurring/durable?
    "FY2025E revenue": "kq-02-revenue-durability",
    "revenue mix: scheduled vs repeat-project vs new project work": "kq-02-revenue-durability",
    "recurring-or-repeat revenue share": "kq-02-revenue-durability",
    "non-standard pricing, margin and service-level terms among top customers": "kq-02-revenue-durability",
    "ownership-stub revenue": "kq-02-revenue-durability",

    # kq-03: Minimum-volume commitments and termination notice periods?
    "customer minimum-volume commitments and termination rights": "kq-03-contract-protections",

    # kq-04: What is the correct EBITDA basis?
    "EBITDA adjustment supportability": "kq-04-ebitda-adjustments",
    "QoE-normalized EBITDA": "kq-04-ebitda-adjustments",
    "opening firm EBITDA": "kq-04-ebitda-adjustments",
    "FY2025 reported EBITDA": "kq-04-ebitda-adjustments",
    "seller-adjusted EBITDA": "kq-04-ebitda-adjustments",
    "seller-adjusted EBITDA basis": "kq-04-ebitda-adjustments",
    "gross margin trend": "kq-04-ebitda-adjustments",
    "pricing and utilization initiative add-back": "kq-04-ebitda-adjustments",
    "founder-related headquarters lease treatment": "kq-04-ebitda-adjustments",
    "firm initial assessment recommendation": "kq-04-ebitda-adjustments",
    "initial assessment information basis": "kq-04-ebitda-adjustments",
    # Financial model outputs — EBITDA basis drives the returns model
    "enterprise value": "kq-04-ebitda-adjustments",
    "entry firm multiple and base exit assumption": "kq-04-ebitda-adjustments",
    "entry multiple assumption": "kq-04-ebitda-adjustments",
    "exit multiple assumption": "kq-04-ebitda-adjustments",
    "exit multiple assumption - combined risk case": "kq-04-ebitda-adjustments",
    "exit multiple assumption - downside case": "kq-04-ebitda-adjustments",
    "exit multiple assumption - upside case": "kq-04-ebitda-adjustments",
    "sponsor gross MOIC and XIRR - Acquisition Base": "kq-04-ebitda-adjustments",
    "sponsor gross MOIC and XIRR - Combined Risk": "kq-04-ebitda-adjustments",
    "sponsor gross MOIC and XIRR - Standalone Base": "kq-04-ebitda-adjustments",
    "sponsor gross MOIC and XIRR - Standalone Downside": "kq-04-ebitda-adjustments",
    "sponsor gross MOIC and XIRR - Standalone Upside": "kq-04-ebitda-adjustments",
    "sponsor gross proceeds": "kq-04-ebitda-adjustments",
    "vested MIP by case": "kq-04-ebitda-adjustments",
    "vested MIP proceeds": "kq-04-ebitda-adjustments",

    # kq-05: Normalized working-capital target?
    "normalized working-capital target": "kq-05-working-capital",

    # kq-06: WIP quality?
    "unbilled WIP aging, disputes and customer approval": "kq-06-wip-quality",
    "unbilled WIP aging, disputes and customer approval - project-level detail": "kq-06-wip-quality",

    # kq-07: Debt-like items vs ordinary working capital?
    "debt-like items vs ordinary working-capital classification": "kq-07-debt-classification",
    "opening net debt": "kq-07-debt-classification",
    "first-lien opening debt": "kq-07-debt-classification",
    "financing fees and OID": "kq-07-debt-classification",
    "deferred tax liability": "kq-07-debt-classification",
    "buyer transaction expenses": "kq-07-debt-classification",
    "opening net leverage ratio": "kq-07-debt-classification",
    "opening equity after transaction expense": "kq-07-debt-classification",
    "seller equity value": "kq-07-debt-classification",
    "seller rollover": "kq-07-debt-classification",
    "total invested capital by case": "kq-07-debt-classification",
    "sponsor initial cash equity": "kq-07-debt-classification",
    "sponsor invested capital by case": "kq-07-debt-classification",
    "exit economic net debt by case": "kq-07-debt-classification",
    "ownership structure at closing": "kq-07-debt-classification",

    # kq-08: Integration systems?
    "active time-entry, billing, ERP and customer-master systems": "kq-08-integration-systems",
    "KPI definitions across branches (utilization, rework, project profitability)": "kq-08-integration-systems",

    # kq-09: Integration history and execution?
    "acquisitions history": "kq-09-integration-history",
    "acquisitions history - employee origin": "kq-09-integration-history",
    "executive and branch-leader retention arrangements": "kq-09-integration-history",
    "prior integration and systems-migration failures": "kq-09-integration-history",
    "post-close integration program ownership and cash budget": "kq-09-integration-history",

    # kq-10: Covenant EBITDA definition?
    "covenant limits on add-backs, cash netting, acquisition capacity and minimum liquidity": "kq-10-covenant-definition",
    "lender covenant EBITDA basis": "kq-10-covenant-definition",

    # kq-11: Change-of-control notice or consent?
    "change-of-control notice and consent requirements": "kq-11-change-of-control",

    # kq-12: Governance and board approvals?
    "board approvals for acquisitions and major systems cutovers": "kq-12-governance",
    "ownership structure after amendment": "kq-12-governance",
    "sponsor amendment contribution": "kq-12-governance",

    # Truly meta — no specific analytical question
    "diligence question list scope": None,
}


def load_isolated_claims() -> list[str]:
    con = sqlite3.connect(DB)
    linked = set(
        r[0] for r in con.execute("SELECT src FROM edges WHERE rel='bears-on'")
    )
    all_ks = set(
        r[0]
        for r in con.execute(
            "SELECT id FROM nodes WHERE type='claim' AND deal='keystone'"
        )
    )
    con.close()
    return sorted(all_ks - linked)


def patch_claim(path: pathlib.Path, question_id: str) -> bool:
    text = path.read_text()
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    fm_text = text[3:end]
    body = text[end + 4:]
    fm = yaml.safe_load(fm_text) or {}

    # Already has bears-on set to something non-empty — skip
    bo = fm.get("bears-on")
    if bo and bo != [] and bo != [None]:
        return False

    fm["bears-on"] = [question_id]

    # Reserialise frontmatter preserving key order
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    new_text = f"---\n{new_fm}---{body}"

    if not DRY_RUN:
        path.write_text(new_text)
    return True


def main() -> None:
    if DRY_RUN:
        print("DRY RUN — no files will be modified\n")

    isolated = load_isolated_claims()
    print(f"Isolated keystone claims: {len(isolated)}")

    patched = 0
    skipped_no_map = []
    skipped_already_bound = []

    for cid in isolated:
        p = VAULT / "deals" / "keystone" / "claims" / f"{cid}.md"
        if not p.exists():
            continue

        fm_text = p.read_text()
        end = fm_text.find("\n---", 3)
        if end == -1:
            continue
        fm = yaml.safe_load(fm_text[3:end]) or {}
        subject = str(fm.get("subject", "")).strip()

        qid = SUBJECT_MAP.get(subject)
        if qid is None:
            if subject in SUBJECT_MAP:  # explicitly mapped to None (meta)
                skipped_no_map.append((cid, subject))
            else:
                skipped_no_map.append((cid, f"(unmapped) {subject}"))
            continue

        ok = patch_claim(p, qid)
        if ok:
            patched += 1
            if DRY_RUN:
                print(f"  would bind {cid} → {qid}  [{subject[:50]}]")
        else:
            skipped_already_bound.append(cid)

    print(f"\nPatched:  {patched}")
    print(f"Skipped (already bound): {len(skipped_already_bound)}")
    print(f"Skipped (no mapping):    {len(skipped_no_map)}")
    if skipped_no_map:
        print("\nUnmapped subjects:")
        for cid, s in skipped_no_map:
            print(f"  {cid}: {s}")


if __name__ == "__main__":
    main()
