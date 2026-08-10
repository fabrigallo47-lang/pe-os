#!/usr/bin/env python3
"""Identity and definition resolver — zero LLM.

Decides if two claims describe the same underlying quantity:
- Same subject (normalized, with alias expansion)?
- Same period (FY2025, LTM, Opening)?
- Same perimeter (Firm View, QoE View, consolidated)?

If yes, they should be linked. If not, they are two distinct quantities
that happen to share a name — the "five EBITDAs" problem.

Output:
  - IdentityScore per pair
  - Batch mode: find all candidate matches above threshold for a deal
  - Writes proposed-links as claims with rel 'aliases-with'

Usage:
    python3 tools/identity_resolver.py keystone --threshold 0.7
    python3 tools/identity_resolver.py keystone --pair c-keystone-039 mp-keystone-inputs-XXXX
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

PERIOD_NORMALIZE: dict[str, str] = {
    "fy2025": "FY2025", "fy25": "FY2025", "2025a": "FY2025",
    "fy2024": "FY2024", "fy24": "FY2024", "2024a": "FY2024",
    "fy2023": "FY2023", "fy23": "FY2023", "2023a": "FY2023",
    "ltm": "LTM", "ltm dec-2025": "LTM", "ltm dec 2025": "LTM",
    "ltm 2025": "LTM", "fy2025 ltm": "LTM",
    "opening": "Opening",
}

PERIMETER_NORMALIZE: dict[str, str] = {
    "firm view": "Firm View", "firm": "Firm View",
    "qoe view": "QoE View", "qoe": "QoE View", "quality of earnings": "QoE View",
    "seller view": "Seller View", "seller": "Seller View",
    "covenant view": "Covenant View", "covenant": "Covenant View",
    "reported": "Reported",
    "consolidated": "consolidated", "standalone": "standalone",
    "proforma": "proforma", "pro forma": "proforma",
}

# Subject aliases — normalized → canonical
SUBJECT_ALIASES: dict[str, str] = {
    "ebitda": "adjusted ebitda",
    "firm ebitda": "adjusted ebitda",
    "opening firm ebitda": "adjusted ebitda",
    "adj ebitda": "adjusted ebitda",
    "adjusted ebitda (firm view)": "adjusted ebitda",
    "ev": "enterprise value",
    "ltm revenue": "revenue",
    "fy25 revenue": "revenue",
    "seller equity": "seller equity value",
    "sponsor equity": "sponsor initial cash equity",
    "net leverage": "opening net leverage ratio",
    "term loan": "first-lien opening debt",
    "first lien debt": "first-lien opening debt",
}


@dataclass
class IdentityScore:
    claim_a: str
    claim_b: str
    score: float          # 0.0 – 1.0
    subject_score: float
    period_match: bool
    perimeter_match: bool
    same_metric_category: bool
    reasons: list[str]
    verdict: str          # "link" | "review" | "distinct"


def _normalize_subject(s: str) -> str:
    s = re.sub(r'[$%xm]+', '', s.lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return SUBJECT_ALIASES.get(s, s)


def _normalize_period(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    return PERIOD_NORMALIZE.get(p.lower().strip(), p)


def _normalize_perimeter(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    return PERIMETER_NORMALIZE.get(p.lower().strip(), p)


def _word_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word sets."""
    wa = set(re.findall(r'\w+', a.lower()))
    wb = set(re.findall(r'\w+', b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def score_pair(a: dict, b: dict) -> IdentityScore:
    """Score whether two claim dicts describe the same quantity."""
    subj_a = _normalize_subject(a.get("subject", ""))
    subj_b = _normalize_subject(b.get("subject", ""))

    # Subject score
    if subj_a == subj_b:
        subj_score = 1.0
        reasons = ["exact subject match"]
    else:
        overlap = _word_overlap(subj_a, subj_b)
        subj_score = overlap
        reasons = [f"subject word-overlap: {overlap:.2f}"]

    # Period
    period_a = _normalize_period(a.get("period") or _extract_period(a.get("subject", "")))
    period_b = _normalize_period(b.get("period") or _extract_period(b.get("subject", "")))
    period_match = bool(period_a and period_b and period_a == period_b)
    if period_a and period_b:
        if period_match:
            reasons.append(f"period match: {period_a}")
        else:
            reasons.append(f"period mismatch: {period_a} vs {period_b}")

    # Perimeter
    perim_a = _normalize_perimeter(a.get("perimeter"))
    perim_b = _normalize_perimeter(b.get("perimeter"))
    perimeter_match = bool(perim_a and perim_b and perim_a == perim_b)
    if perim_a and perim_b:
        if perimeter_match:
            reasons.append(f"perimeter match: {perim_a}")
        else:
            reasons.append(f"perimeter mismatch: {perim_a} vs {perim_b}")

    # Metric category
    mc_a = a.get("metric_category") or a.get("metric-category")
    mc_b = b.get("metric_category") or b.get("metric-category")
    same_mc = bool(mc_a and mc_b and mc_a == mc_b)
    if same_mc:
        reasons.append(f"same metric-category: {mc_a}")

    # Combine
    score = subj_score
    if period_match:
        score = min(1.0, score + 0.15)
    elif period_a and period_b and not period_match:
        score = max(0.0, score - 0.25)  # period mismatch is a strong signal
    if perimeter_match:
        score = min(1.0, score + 0.10)
    elif perim_a and perim_b and not perimeter_match:
        score = max(0.0, score - 0.15)
    if same_mc:
        score = min(1.0, score + 0.05)

    if score >= 0.80:
        verdict = "link"
    elif score >= 0.50:
        verdict = "review"
    else:
        verdict = "distinct"

    return IdentityScore(
        claim_a=a.get("id", ""), claim_b=b.get("id", ""),
        score=round(score, 3),
        subject_score=round(subj_score, 3),
        period_match=period_match, perimeter_match=perimeter_match,
        same_metric_category=same_mc,
        reasons=reasons, verdict=verdict,
    )


def _extract_period(subject: str) -> Optional[str]:
    """Try to extract period hint from subject string."""
    m = re.search(r'\b(FY\s*\d{4}[A-Z]?|LTM|Opening|Q[1-4]\s*\d{4})\b', subject, re.I)
    return m.group(0) if m else None


def batch_resolve(con: sqlite3.Connection, deal: str, threshold: float = 0.60) -> list[IdentityScore]:
    """
    Find candidate identity matches across all claims for a deal.
    Only compares claims with the same metric-category (to keep complexity manageable).
    """
    rows = con.execute(
        "SELECT id, subject, frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,)
    ).fetchall()

    claims: list[dict] = []
    for cid, subj, fm_raw in rows:
        fm = json.loads(fm_raw or "{}")
        claims.append({
            "id": cid,
            "subject": subj or fm.get("subject", ""),
            "period": fm.get("period"),
            "perimeter": fm.get("perimeter"),
            "metric_category": fm.get("metric-category"),
        })

    # Group by metric-category for efficiency
    by_mc: dict[str, list[dict]] = {}
    for c in claims:
        mc = c.get("metric_category") or "other"
        by_mc.setdefault(mc, []).append(c)

    results: list[IdentityScore] = []
    seen_pairs: set[frozenset] = set()

    def _add(a: dict, b: dict) -> None:
        pair = frozenset([a["id"], b["id"]])
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        # Skip mp-vs-mp (same Excel source, same origin) unless they have period/perimeter diff
        if a["id"].startswith("mp-") and b["id"].startswith("mp-"):
            if not (a.get("period") or a.get("perimeter")) and not (b.get("period") or b.get("perimeter")):
                return
        s = score_pair(a, b)
        if s.score >= threshold:
            results.append(s)

    # Same metric-category grouping (efficient path)
    for mc, group in by_mc.items():
        if mc == "other" or len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                _add(a, b)

    # Cross-source matching: model-parser claims vs manual claims with no metric_category
    mp_claims = [c for c in claims if c["id"].startswith("mp-") and c.get("metric_category")]
    untagged = [c for c in claims if not c.get("metric_category") and not c["id"].startswith("mp-")]
    high_threshold = max(threshold, 0.70)  # tighter threshold for broad scan
    for mp_c in mp_claims:
        for u in untagged:
            pair = frozenset([mp_c["id"], u["id"]])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            s = score_pair(mp_c, u)
            if s.score >= high_threshold:
                results.append(s)

    results.sort(key=lambda r: -r.score)
    return results


def print_report(results: list[IdentityScore], deal: str) -> None:
    if not results:
        print(f"No identity candidates found for {deal} above threshold.")
        return
    link = [r for r in results if r.verdict == "link"]
    review = [r for r in results if r.verdict == "review"]
    print(f"\nIdentity Resolution — {deal}")
    print(f"  Auto-link candidates (score≥0.80): {len(link)}")
    print(f"  Needs human review (0.50–0.80): {len(review)}")
    print()
    for r in results[:20]:
        badge = "🔗" if r.verdict == "link" else "❓"
        print(f"{badge} [{r.score:.2f}] {r.claim_a}")
        print(f"   ↔ {r.claim_b}")
        print(f"   {' · '.join(r.reasons)}")
        print()


def main() -> None:
    import argparse, os
    sys.path.insert(0, str(ROOT / "tools"))
    import indexer

    p = argparse.ArgumentParser()
    p.add_argument("deal")
    p.add_argument("--pair", nargs=2, metavar=("CLAIM_A", "CLAIM_B"),
                   help="Score a specific pair")
    p.add_argument("--threshold", type=float, default=0.60)
    args = p.parse_args()

    con = sqlite3.connect(indexer.DB)

    if args.pair:
        rows = {}
        for cid in args.pair:
            row = con.execute(
                "SELECT id, subject, frontmatter FROM nodes WHERE id=?", (cid,)
            ).fetchone()
            if row:
                fm = json.loads(row[2] or "{}")
                rows[cid] = {"id": row[0], "subject": row[1] or fm.get("subject", ""),
                             "period": fm.get("period"), "perimeter": fm.get("perimeter"),
                             "metric_category": fm.get("metric-category")}
        if len(rows) == 2:
            a, b = list(rows.values())
            s = score_pair(a, b)
            print(f"Score: {s.score:.3f}  verdict: {s.verdict}")
            for r in s.reasons:
                print(f"  {r}")
        else:
            print("One or both claim IDs not found in index.")
    else:
        results = batch_resolve(con, args.deal, args.threshold)
        print_report(results, args.deal)

    con.close()


if __name__ == "__main__":
    main()
