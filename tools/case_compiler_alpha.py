#!/usr/bin/env python3
"""
case_compiler_alpha.py — L5 Case Compiler Alpha for PANTA.

Inputs:
  - e3_claims.json       (K-IC manifest, 296 claims)
  - bindings.json        (claim_id → question_ids)

Outputs:
  - case_alpha.json      — Case Positions + claim-position edges + coverage gaps
  - case_alpha_report.txt

Case Positions: 10 thesis dimensions synthesized deterministically from
the 20 Keystone diligence questions.  NO answer keys.

Usage:
  python3 tools/case_compiler_alpha.py \\
      --e3   pipeline_out/e3/K-IC/e3_claims.json \\
      --bind pipeline_out/e3/K-IC/bindings/bindings.json \\
      --out  pipeline_out/e3/K-IC/case_alpha/
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── Case Position definitions ─────────────────────────────────────────────────
# Each position:
#   questions    : list of Q-xx IDs whose claims feed this position
#   polarity_pos : keyword patterns that SUPPORT the position (bullish signals)
#   polarity_neg : keyword patterns that CONTRADICT / raise risk (bearish signals)
# ─────────────────────────────────────────────────────────────────────────────

POSITIONS: list[dict] = [
    {
        "id": "CP-01",
        "title": "Customer concentration at billing-account level understates true parent-level exposure.",
        "question_ids": ["Q-01", "Q-02"],
        "thesis_dimension": "Commercial — Customer Concentration",
        "polarity_pos": [
            r"parent.{0,20}(customer|concentration)",
            r"ultimate.parent",
            r"riverton|apex.{0,10}manufactur|metro.{0,10}util",
            r"7\.6%|18\.2%",
        ],
        "polarity_neg": [
            r"top.{0,5}(ten|10|five|5).{0,20}customer.{0,30}(diversif|spread|granular)",
            r"no single.{0,20}customer.{0,20}(exceed|more than)",
            r"600.{0,20}(billing|account)",
        ],
    },
    {
        "id": "CP-02",
        "title": "Revenue quality is supported by recurring/repeat work but the 72% recurring claim requires verification.",
        "question_ids": ["Q-03", "Q-04", "Q-05"],
        "thesis_dimension": "Commercial — Revenue Quality & Durability",
        "polarity_pos": [
            r"recurring.{0,20}(revenue|work)",
            r"scheduled.{0,20}(revenue|work)",
            r"minimum.{0,20}volume",
            r"master.{0,20}agreement",
            r"long.term.{0,20}(contract|relationship)",
        ],
        "polarity_neg": [
            r"short.{0,10}notice.{0,20}terminat",
            r"termination.{0,20}(right|within|on\s+\d)",
            r"non.standard.{0,20}(pricing|margin)",
            r"project.based|discrete.project|new.project",
            r"unverified|not.verified|could.not",
        ],
    },
    {
        "id": "CP-03",
        "title": "EBITDA add-backs total ~$3.5m; QoE accepted the largest items but the run-rate benefit of the pricing initiative is forward-looking.",
        "question_ids": ["Q-06", "Q-07"],
        "thesis_dimension": "Financial — EBITDA Quality",
        "polarity_pos": [
            r"qoe.{0,20}(accept|confirm|validate)",
            r"non.recurring",
            r"market.replacement",
            r"supportable",
            r"normaliz",
        ],
        "polarity_neg": [
            r"(not|un).{0,10}(implement|achieved|realized)",
            r"forward.looking|run.rate",
            r"(unsupported|partial|limited|questionable)",
            r"pricing.{0,20}(initiative|utilization).{0,30}(not|unachiev|forward)",
            r"exceed.{0,10}(\$|million)|overstat",
        ],
    },
    {
        "id": "CP-04",
        "title": "Working-capital requirement is material and the normalized target is contested between seller and QoE.",
        "question_ids": ["Q-08", "Q-09"],
        "thesis_dimension": "Financial — Working Capital",
        "polarity_pos": [
            r"normaliz.{0,20}(working.capital|target)",
            r"qoe.{0,20}(target|recommend|normaliz)",
            r"cash.free.debt.free",
            r"wip.{0,20}(approv|collect|high)",
        ],
        "polarity_neg": [
            r"disputed|aged|missing.approv",
            r"unbilled.{0,20}(risk|collect|aged)",
            r"seller.{0,20}(higher|overstat|claim)",
            r"adjustment.{0,20}(purchase|price)",
        ],
    },
    {
        "id": "CP-05",
        "title": "Entry leverage is moderate but financing structure includes meaningful contingent capacity.",
        "question_ids": ["Q-10", "Q-17", "Q-18"],
        "thesis_dimension": "Financial — Debt Structure & Covenants",
        "polarity_pos": [
            r"first.lien",
            r"revolver.{0,20}(capacity|available)",
            r"ddtl",
            r"covenant.{0,20}(headroom|flexible|cushion)",
            r"interest.coverage",
        ],
        "polarity_neg": [
            r"debt.like.{0,20}(item|liabilit)",
            r"covenant.{0,20}(risk|tight|breach|trigger)",
            r"leverage.{0,20}(high|concern|risk)",
            r"deferred.tax",
            r"add.back.{0,20}limit",
        ],
    },
    {
        "id": "CP-06",
        "title": "Multi-system fragmentation across acquired branches is the primary integration execution risk.",
        "question_ids": ["Q-11", "Q-14"],
        "thesis_dimension": "Operational — Systems & KPI Comparability",
        "polarity_pos": [
            r"(erp|time.entry|billing).{0,20}(active|migrat|plan|roadmap)",
            r"integration.{0,20}(plan|ready|progress)",
            r"single.{0,10}(system|platform|erp)",
        ],
        "polarity_neg": [
            r"different.{0,20}system",
            r"fragment",
            r"inconsistent.{0,20}(kpi|definit|measur)",
            r"multiple.{0,20}(erp|system|platform)",
            r"not.yet.migrat|still.operat",
        ],
    },
    {
        "id": "CP-07",
        "title": "Acquisition track record demonstrates integration capability, but prior delays establish execution risk.",
        "question_ids": ["Q-12", "Q-13"],
        "thesis_dimension": "Operational — Integration Track Record",
        "polarity_pos": [
            r"four.{0,20}acquisitions|successful.{0,20}integrat",
            r"integration.{0,20}program.{0,20}(funded|govern|own)",
            r"\$2\.0m.{0,20}integrat|integration.{0,20}budget",
        ],
        "polarity_neg": [
            r"(fail|delay|overrun).{0,30}(integrat|system|migrat)",
            r"prior.{0,20}(integrat|migration).{0,20}(fail|delay|extend)",
            r"risk.{0,20}integrat",
        ],
    },
    {
        "id": "CP-08",
        "title": "Change-of-control exposure is limited to a subset of contracts; the founder lease is unquantified.",
        "question_ids": ["Q-15", "Q-16"],
        "thesis_dimension": "Legal — Change-of-Control & Related-Party Risk",
        "polarity_pos": [
            r"consent.{0,20}(obtained|waived|minor|limited)",
            r"change.of.control.{0,20}(limited|minor|few)",
            r"related.party.{0,20}(market|arm.length|normaliz)",
        ],
        "polarity_neg": [
            r"change.of.control.{0,20}(required|notice|clause)",
            r"headquarters.{0,20}lease|founder.{0,20}lease",
            r"related.party.{0,20}(above.market|excess|non.arm)",
        ],
    },
    {
        "id": "CP-09",
        "title": "Returns are achievable at base assumptions; covenant definitions are the key financing lever.",
        "question_ids": ["Q-06", "Q-17", "Q-18"],
        "thesis_dimension": "Returns — Model Outputs & Financing",
        "polarity_pos": [
            r"moic.{0,20}(2\.[5-9]|3\.|base)",
            r"irr.{0,20}(2[0-9]|30)%",
            r"exit.multiple.{0,20}(9|10|11)\.0x",
            r"covenant.{0,20}(headroom|complian)",
        ],
        "polarity_neg": [
            r"moic.{0,20}(1\.[0-9]|below)",
            r"downside.{0,20}(moic|case|scenario)",
            r"covenant.{0,20}(breach|risk|tight)",
            r"add.back.{0,20}(cap|limit|challenged)",
        ],
    },
    {
        "id": "CP-10",
        "title": "Management continuity and post-close governance require structured retention and defined board oversight.",
        "question_ids": ["Q-19", "Q-20"],
        "thesis_dimension": "Governance — Retention & Board Oversight",
        "polarity_pos": [
            r"retention.{0,20}(arrang|plan|package|incentive)",
            r"key.{0,20}person.{0,20}(retain|commit|arrang)",
            r"board.{0,20}(oversight|approv|govern)",
            r"mip|management.incentive",
        ],
        "polarity_neg": [
            r"key.person.{0,20}risk",
            r"depend.{0,20}(qualified|technical|personnel)",
            r"no.{0,20}(formal|written|defined).{0,20}retention",
            r"departure.{0,20}(risk|concern|execut)",
        ],
    },
]


def _compile_patterns(pat_list: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.I) for p in pat_list]


for pos in POSITIONS:
    pos["_pos_pats"] = _compile_patterns(pos["polarity_pos"])
    pos["_neg_pats"] = _compile_patterns(pos["polarity_neg"])


def classify_claim_for_position(stmt: str, pos: dict) -> str | None:
    """Return 'supports', 'contradicts', or None (neutral/not applicable)."""
    pos_hits = sum(1 for p in pos["_pos_pats"] if p.search(stmt))
    neg_hits = sum(1 for p in pos["_neg_pats"] if p.search(stmt))
    if pos_hits == 0 and neg_hits == 0:
        return "context"
    if neg_hits > pos_hits:
        return "contradicts"
    return "supports"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e3", required=True)
    ap.add_argument("--bind", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.e3) as f:
        e3 = json.load(f)
    with open(args.bind) as f:
        bind = json.load(f)

    # Index claims
    claims_by_id = {c["claim_id"]: c for c in e3["claims"]}
    compiler_meta = {
        cf["claim_id"]: cf
        for cf in e3.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
    }
    # Index bindings
    claim_to_qs: dict[str, list[str]] = {
        b["claim_id"]: b["question_ids"] for b in bind["bindings"]
    }

    # Build position → claims mapping
    positions_out = []
    all_edges = []
    coverage_gaps = []

    for pos in POSITIONS:
        qids = set(pos["question_ids"])
        relevant_claim_ids = [
            cid for cid, qs in claim_to_qs.items()
            if qids & set(qs)
        ]

        pos_edges = []
        support_cnt = contradiction_cnt = context_cnt = 0

        for cid in relevant_claim_ids:
            c = claims_by_id.get(cid)
            if not c:
                continue
            stmt = c["statement"]
            role = classify_claim_for_position(stmt, pos)
            edge = {
                "claim_id": cid,
                "position_id": pos["id"],
                "role": role,
                "source_id": c["source_id"],
                "epistemic_class": c["epistemic_class"],
                "statement": stmt,
            }
            pos_edges.append(edge)
            all_edges.append(edge)
            if role == "supports":
                support_cnt += 1
            elif role == "contradicts":
                contradiction_cnt += 1
            else:
                context_cnt += 1

        total_claims = len(pos_edges)
        if total_claims == 0:
            coverage_gaps.append({"position_id": pos["id"], "questions": pos["question_ids"]})

        # Thin evidence threshold: <3 supporting claims
        if support_cnt < 3:
            coverage_gaps.append({
                "position_id": pos["id"],
                "reason": "thin_evidence",
                "supporting_claims": support_cnt,
                "total_claims": total_claims,
            })

        positions_out.append({
            "position_id": pos["id"],
            "title": pos["title"],
            "thesis_dimension": pos["thesis_dimension"],
            "question_ids": pos["question_ids"],
            "claim_count": total_claims,
            "supports": support_cnt,
            "contradicts": contradiction_cnt,
            "context": context_cnt,
            "verdict": (
                "well_supported" if support_cnt >= 5 and contradiction_cnt <= 2 else
                "contested" if contradiction_cnt >= 2 else
                "thin" if support_cnt < 3 else
                "supported"
            ),
            "sample_supports": [
                e["statement"][:120]
                for e in pos_edges if e["role"] == "supports"
            ][:3],
            "sample_contradicts": [
                e["statement"][:120]
                for e in pos_edges if e["role"] == "contradicts"
            ][:3],
        })

    # Deduplicate coverage gaps
    seen = set()
    unique_gaps = []
    for g in coverage_gaps:
        k = g["position_id"] + g.get("reason", "zero")
        if k not in seen:
            seen.add(k)
            unique_gaps.append(g)

    # Proposed questions (from question_ids not richly addressed)
    proposed_questions = [
        {
            "question_id": "PQ-01",
            "text": "What is the ultimate-parent concentration as a percentage of revenue for the top 5 corporate families?",
            "bears_on": ["CP-01"],
            "gap_type": "depth",
        },
        {
            "question_id": "PQ-02",
            "text": "What proportion of revenue is contractually committed (minimum-volume) versus discretionary repeat?",
            "bears_on": ["CP-02"],
            "gap_type": "depth",
        },
        {
            "question_id": "PQ-03",
            "text": "What is the QoE-accepted normalized EBITDA and how does it differ from seller-adjusted EBITDA?",
            "bears_on": ["CP-03"],
            "gap_type": "depth",
        },
        {
            "question_id": "PQ-04",
            "text": "What is the lender's covenant EBITDA definition and how does it differ from reported EBITDA?",
            "bears_on": ["CP-05", "CP-09"],
            "gap_type": "depth",
        },
        {
            "question_id": "PQ-05",
            "text": "What is the treatment and quantification of the founder-related headquarters lease?",
            "bears_on": ["CP-08"],
            "gap_type": "zero_coverage",
            "note": "Q-16: no claims extracted — qualitative/legal, not captured by metric schema",
        },
        {
            "question_id": "PQ-06",
            "text": "What branch-by-branch systems migration milestones are committed in the integration plan?",
            "bears_on": ["CP-06", "CP-07"],
            "gap_type": "depth",
        },
        {
            "question_id": "PQ-07",
            "text": "Which executives and branch leaders have signed or agreed retention terms?",
            "bears_on": ["CP-10"],
            "gap_type": "depth",
        },
        {
            "question_id": "PQ-08",
            "text": "What post-close board approval requirements are documented for acquisitions and systems cutovers?",
            "bears_on": ["CP-10"],
            "gap_type": "zero_coverage",
            "note": "Q-20: no claims extracted — governance design question, not in source documents",
        },
    ]

    output = {
        "schema_version": "case-alpha-1.0",
        "manifest_id": e3.get("manifest_id"),
        "deal": e3.get("deal"),
        "compiler": "case_compiler_alpha",
        "positions": positions_out,
        "edges": all_edges,
        "proposed_questions": proposed_questions,
        "coverage_gaps": unique_gaps,
        "stats": {
            "positions_total": len(POSITIONS),
            "positions_well_supported": sum(1 for p in positions_out if p["verdict"] == "well_supported"),
            "positions_contested": sum(1 for p in positions_out if p["verdict"] == "contested"),
            "positions_thin": sum(1 for p in positions_out if p["verdict"] == "thin"),
            "total_edges": len(all_edges),
            "proposed_questions": len(proposed_questions),
            "coverage_gaps": len(unique_gaps),
        },
    }

    (out_dir / "case_alpha.json").write_text(json.dumps(output, indent=2))

    # ── Human-readable report ─────────────────────────────────────────────────
    lines = [
        "Case Compiler Alpha — E3 K-IC",
        "=" * 55,
        f"  Deal        : {e3.get('deal')}",
        f"  Manifest    : {e3.get('manifest_id')}",
        f"  Positions   : {len(POSITIONS)}",
        f"  Total edges : {len(all_edges)}",
        f"  Proposed Qs : {len(proposed_questions)}",
        f"  Coverage gaps: {len(unique_gaps)}",
        "",
    ]

    for p in positions_out:
        verdict_icon = {
            "well_supported": "✓",
            "supported": "~",
            "contested": "!",
            "thin": "?",
        }.get(p["verdict"], " ")
        lines.append(f"[{verdict_icon}] {p['position_id']}: {p['title'][:75]}")
        lines.append(f"    claims={p['claim_count']:3d}  supports={p['supports']}  contradicts={p['contradicts']}  context={p['context']}  verdict={p['verdict']}")
        if p["sample_supports"]:
            lines.append(f"    SUPPORTS: {p['sample_supports'][0][:90]}")
        if p["sample_contradicts"]:
            lines.append(f"    CONTRADICTS: {p['sample_contradicts'][0][:90]}")
        lines.append("")

    lines += ["Proposed questions (no answer key):"]
    for pq in proposed_questions:
        note = f"  [{pq['gap_type']}]" + (f" {pq.get('note','')}" if pq.get("note") else "")
        lines.append(f"  {pq['question_id']}: {pq['text']}")
        lines.append(f"    → bears on {pq['bears_on']}{note}")

    lines += ["", "Coverage gaps:"]
    for g in unique_gaps:
        lines.append(f"  {g['position_id']}: {g.get('reason','zero_coverage')} — supports={g.get('supporting_claims','0')} / total={g.get('total_claims','0')}")

    report = "\n".join(lines)
    (out_dir / "case_alpha_report.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
