#!/usr/bin/env python3
"""Coverage report — the honesty layer.

'Of 423 claims I bound 380; 43 remain unplaced, here they are.'

Without this, the system is dangerous: it appears to answer questions
but silently omits evidence it couldn't classify.

Usage:
    python3 tools/coverage_report.py keystone
    python3 tools/coverage_report.py keystone --json
    python3 tools/coverage_report.py --all
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def coverage(con: sqlite3.Connection, deal: str) -> dict:
    def q(sql, *params):
        return con.execute(sql, params).fetchone()[0]

    def rows(sql, *params):
        return con.execute(sql, params).fetchall()

    total = q("SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=?", deal)
    if total == 0:
        return {"deal": deal, "total": 0}

    # Bound vs unbound
    bound = q(
        "SELECT COUNT(DISTINCT n.id) FROM nodes n "
        "JOIN edges e ON e.src=n.id AND e.rel='bears-on' "
        "WHERE n.type='claim' AND n.deal=?", deal)
    unbound = total - bound

    # By epistemic
    epi_rows = rows(
        "SELECT epistemic, COUNT(*) FROM nodes WHERE type='claim' AND deal=? GROUP BY epistemic", deal)
    by_epistemic = {r[0] or "unknown": r[1] for r in epi_rows}

    # By metric-category
    mc_rows = rows(
        "SELECT metric_category, COUNT(*) FROM nodes WHERE type='claim' AND deal=? "
        "GROUP BY metric_category", deal)
    by_metric = {r[0] or "untagged": r[1] for r in mc_rows}

    # Period/perimeter coverage
    with_period = q(
        "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=? "
        "AND metric_category IS NOT NULL", deal)  # using metric as proxy until period col exists
    has_last_seen = q(
        "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=? AND last_seen IS NOT NULL", deal)

    # Temporal health: claims not seen in last 90 days (last_seen < 90d ago)
    import datetime as _dt
    cutoff_90 = (_dt.date.today() - _dt.timedelta(days=90)).isoformat()
    stale_temporal = q(
        "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=? "
        "AND last_seen IS NOT NULL AND last_seen < ?", deal, cutoff_90)

    # From model parser
    from_model = q(
        "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=? AND id LIKE 'mp-%'", deal)

    # Part-of hierarchy
    in_hierarchy = q(
        "SELECT COUNT(DISTINCT src) FROM edges e "
        "JOIN nodes n ON e.src=n.id "
        "WHERE e.rel='part-of' AND n.type='claim' AND n.deal=?", deal)

    # Stale (recalc stale)
    stale_recalc = q(
        "SELECT COUNT(*) FROM nodes WHERE type='claim' AND deal=? "
        "AND frontmatter LIKE '%\"stale\": true%'", deal)

    # Unbound claim list (top 20 by epistemic rank)
    unbound_rows = con.execute(
        "SELECT n.id, n.subject, n.epistemic, n.metric_category "
        "FROM nodes n "
        "WHERE n.type='claim' AND n.deal=? "
        "AND NOT EXISTS (SELECT 1 FROM edges e WHERE e.src=n.id AND e.rel='bears-on') "
        "ORDER BY "
        "  CASE n.epistemic WHEN 'attested' THEN 0 WHEN 'observed' THEN 1 "
        "    WHEN 'derived' THEN 2 ELSE 3 END, "
        "  n.id LIMIT 20",
        (deal,),
    ).fetchall()

    # Artifacts
    n_artifacts = q(
        "SELECT COUNT(*) FROM nodes WHERE type='artifact' AND deal=?", deal)
    artifact_rows = rows(
        "SELECT n.id, n.title, COUNT(e.src) as claim_count "
        "FROM nodes n LEFT JOIN edges e ON e.dst=n.id AND e.rel='artifact-id' "
        "WHERE n.type='artifact' AND n.deal=? GROUP BY n.id ORDER BY claim_count DESC LIMIT 10",
        deal)

    return {
        "deal": deal,
        "total": total,
        "bound": bound,
        "unbound": unbound,
        "bound_pct": round(bound / total * 100, 1) if total else 0,
        "by_epistemic": by_epistemic,
        "by_metric_category": by_metric,
        "with_metric_tag": total - by_metric.get("untagged", 0),
        "from_model_parser": from_model,
        "in_hierarchy": in_hierarchy,
        "stale_recalc": stale_recalc,
        "has_last_seen": has_last_seen,
        "stale_temporal_90d": stale_temporal,
        "artifacts": n_artifacts,
        "artifact_detail": [
            {"id": r[0], "title": r[1], "claim_count": r[2]} for r in artifact_rows
        ],
        "unbound_claims": [
            {"id": r[0], "subject": r[1], "epistemic": r[2], "metric_category": r[3]}
            for r in unbound_rows
        ],
    }


def print_report(data: dict) -> None:
    deal = data["deal"]
    total = data["total"]
    bound = data["bound"]
    unbound = data["unbound"]
    pct = data["bound_pct"]

    w = 52
    print("=" * w)
    print(f"  Coverage Report — {deal}")
    print("=" * w)
    print(f"  Total claims   : {total:>5}")
    print(f"  Bound          : {bound:>5}  ({pct}%)")
    print(f"  Unbound        : {unbound:>5}  ({100-pct:.1f}%)")
    print()

    print("  By epistemic type:")
    for ep, cnt in sorted(data["by_epistemic"].items()):
        bar = "█" * min(int(cnt / max(total, 1) * 30), 30)
        print(f"    {ep:<12} {cnt:>4}  {bar}")

    print()
    print("  By metric category:")
    for mc, cnt in sorted(data["by_metric_category"].items(), key=lambda x: -x[1]):
        print(f"    {mc:<25} {cnt:>4}")

    print()
    print("  Graph enrichment:")
    print(f"    From model parser  : {data['from_model_parser']}")
    print(f"    In part-of tree    : {data['in_hierarchy']}")
    print(f"    With last-seen     : {data['has_last_seen']}")
    print(f"    Stale (temporal)   : {data['stale_temporal_90d']}  (not seen in 90d)")
    print(f"    Stale (recalc)     : {data['stale_recalc']}  (rests-on input changed)")
    print(f"    Artifacts          : {data['artifacts']}")

    if data["artifact_detail"]:
        print()
        print("  Artifacts (by claim count):")
        for a in data["artifact_detail"][:8]:
            title = (a["title"] or a["id"])[:40]
            print(f"    {title:<42} {a['claim_count']:>3} claims")

    if data["unbound_claims"]:
        print()
        print(f"  Unbound claims (top {len(data['unbound_claims'])} by epistemic priority):")
        for c in data["unbound_claims"]:
            ep = (c["epistemic"] or "?")[:3]
            mc = c["metric_category"] or "-"
            subj = (c["subject"] or "(no subject)")[:55]
            print(f"    [{ep}] {c['id']:<22} {mc:<22} {subj}")

    print("=" * w)


def main() -> None:
    import argparse, os
    sys.path.insert(0, str(ROOT / "tools"))
    import indexer

    p = argparse.ArgumentParser()
    p.add_argument("deal", nargs="?", help="Deal ID, or omit with --all")
    p.add_argument("--all", action="store_true", help="Report all deals")
    p.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = p.parse_args()

    if not indexer.DB.exists():
        sys.exit("No index — run `make index` first")

    con = sqlite3.connect(indexer.DB)

    if args.all:
        deal_rows = con.execute("SELECT id FROM nodes WHERE type='deal' ORDER BY id").fetchall()
        deals = [r[0] for r in deal_rows]
    else:
        deals = [args.deal]

    for deal in deals:
        data = coverage(con, deal)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print_report(data)

    con.close()


if __name__ == "__main__":
    main()
