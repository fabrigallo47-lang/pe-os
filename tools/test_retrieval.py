#!/usr/bin/env python3
"""
Retrieval and staleness cascade test.

Simulates the full monitoring pipeline:
  1. Retrieval: given a monitoring claim (realized EBITDA = $10.8m),
     find the IC baseline claim, compute divergence.
  2. Model graph lookup: identify which model node it affects.
  3. Staleness cascade: mark that node and downstream nodes stale.
  4. Pipeline agent: rebuild PIPELINE.md.
  5. Report: show what was found, what went stale, what the human sees.

Run: .venv/bin/python3 tools/test_retrieval.py [--deal keystone] [--reset]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "tools"))

import runtime as rt
import indexer

VAULT = indexer.VAULT


def _bar(frac: float, width: int = 20) -> str:
    filled = round(min(1.0, frac) * width)
    return "█" * filled + "░" * (width - filled)


def _jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


def test_retrieval(deal: str, reset: bool = False) -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║    PE OS — Retrieval & Staleness Cascade Test                    ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"\nDeal: {deal}")

    # ── 1. Claim retrieval ──────────────────────────────────────────────────
    print("\n── 1. Claim Retrieval ─────────────────────────────────────────────")

    indexer.build()

    # Load all claims for this deal
    cdir = VAULT / "deals" / deal / "claims"
    all_claims = []
    for f in sorted(cdir.glob("c-*.md")):
        txt = f.read_text(encoding="utf-8")
        ep_m = re.search(r'^epistemic:\s*(\w+)', txt, re.MULTILINE)
        subj_m = re.search(r'^subject:\s*"?([^"\n]+)"?', txt, re.MULTILINE)
        val_m  = re.search(r'^value:\s*"?([^"\n]+)"?', txt, re.MULTILINE)
        art_m  = re.search(r'^artifact:\s*"?([^"\n]+)"?', txt, re.MULTILINE)
        per_m  = re.search(r'^period:\s*"?([^"\n]+)"?', txt, re.MULTILINE)
        perim_m= re.search(r'^perimeter:\s*"?([^"\n]+)"?', txt, re.MULTILINE)
        if not (subj_m and val_m):
            continue
        all_claims.append({
            "id": f.stem,
            "epistemic": ep_m.group(1) if ep_m else "",
            "subject": subj_m.group(1).strip(),
            "value": val_m.group(1).strip(),
            "artifact": art_m.group(1).lower() if art_m else "",
            "period": per_m.group(1).strip() if per_m else "",
            "perimeter": perim_m.group(1).strip() if perim_m else "",
        })

    print(f"  Loaded {len(all_claims)} claims from vault")

    # Simulate a monitoring claim arriving (from CL-M14 — August 2027 amendment, 34% divergence)
    MONITORING_CLAIM = {
        "subject": "QoE-normalized EBITDA",
        "value": "7.5",
        "period": "LTM as of 2027-08-15 (amendment review)",
        "perimeter": "Alderstone consolidated EBITDA",
        "source": "keystone_monitoring_augustamendment2027.md",
        "epistemic": "attested",
    }
    print(f"\n  Incoming monitoring claim:")
    print(f"    subject   : {MONITORING_CLAIM['subject']}")
    print(f"    value     : ${MONITORING_CLAIM['value']}m  ({MONITORING_CLAIM['period']})")
    print(f"    perimeter : {MONITORING_CLAIM['perimeter']}")

    # Find best matching IC baseline claim
    IC_SOURCES = ["ic_memo", "initial_assessment", "firm"]
    baseline_claims = [c for c in all_claims
                       if c["epistemic"] in ("attested", "asserted")
                       and any(k in c["artifact"] for k in IC_SOURCES)]

    print(f"\n  IC baseline pool: {len(baseline_claims)} claims from IC/firm sources")

    best_match = None
    best_score = 0.0
    for c in baseline_claims:
        score = _jaccard(MONITORING_CLAIM["subject"], c["subject"])
        if score > best_score:
            best_score = score
            best_match = c

    if best_match:
        print(f"\n  Best baseline match (score={best_score:.2f}):")
        print(f"    id        : {best_match['id']}")
        print(f"    subject   : {best_match['subject']}")
        print(f"    value     : {best_match['value']}")
        print(f"    artifact  : {best_match['artifact'].split('/')[-1]}")

        # Compute divergence
        try:
            mon_v = float(MONITORING_CLAIM["value"])
            ic_v  = float(re.sub(r"[^0-9.\-]", "", best_match["value"].split()[0]) or "0")
            divergence = abs(mon_v - ic_v) / abs(ic_v) if ic_v else 0
            direction = "↓" if mon_v < ic_v else "↑"
            print(f"\n  Divergence: {direction} {divergence*100:.1f}%  "
                  f"(IC={ic_v}, realized={mon_v})")
            alert = divergence >= 0.10
            print(f"  PERFORMANCE_ALERT: {'YES ⚠' if alert else 'no (< 10% threshold)'}")
        except (ValueError, ZeroDivisionError):
            divergence = 0
            print("  (value parsing failed)")
    else:
        print("  No baseline match found")
        divergence = 0

    # ── 2. As-of retrieval ──────────────────────────────────────────────────
    print("\n── 2. As-Of Retrieval (temporal filter) ───────────────────────────")
    # Retrieve EBITDA claims known as of IC date (2026-03-10)
    AS_OF = "2026-03-10"
    EBITDA_TERMS = {"ebitda", "adjusted"}

    ebitda_claims_at_ic = []
    for c in all_claims:
        subj_words = set(re.findall(r"[a-z]+", c["subject"].lower()))
        if not (subj_words & EBITDA_TERMS):
            continue
        # Use period field if available, else check artifact date signals
        period = c["period"].lower()
        artifact = c["artifact"]
        # Exclude monitoring/post-IC sources
        if any(k in artifact for k in ["boardpack", "monitoring", "compliance", "amendment", "exit"]):
            continue
        ebitda_claims_at_ic.append(c)

    print(f"  EBITDA claims known as of IC ({AS_OF}): {len(ebitda_claims_at_ic)}")
    for c in ebitda_claims_at_ic[:8]:
        ep_tag = f"[{c['epistemic'][:3]}]" if c["epistemic"] else ""
        print(f"    {c['id']} {ep_tag:5} {c['subject'][:45]:<45} = {c['value'][:20]}")

    # ── 3. Model graph dependency lookup ────────────────────────────────────
    print("\n── 3. Model Graph — Dependency Lookup ─────────────────────────────")

    graph = rt._model_graph(deal)
    if not graph:
        print("  ERROR: model_graph.json not found — run xlsx_parser first")
        return

    print(f"  Graph: {graph['node_count']} nodes, {graph['edge_count']} edges")

    # Find which model node the monitoring EBITDA claim relates to
    node_id = rt._node_for_subject(graph, MONITORING_CLAIM["subject"])
    print(f"  Subject → model node: {MONITORING_CLAIM['subject']!r} → {node_id}")

    # Show dependency chain
    if node_id:
        deps = graph.get("dependencies", {})
        downstream = deps.get(node_id, [])
        print(f"  Downstream from {node_id} ({len(downstream)} direct):")
        for d in downstream[:6]:
            print(f"    → {d}")
        if len(downstream) > 6:
            print(f"    ... +{len(downstream)-6} more")

    # ── 4. Staleness cascade ────────────────────────────────────────────────
    print("\n── 4. Staleness Cascade ───────────────────────────────────────────")

    if reset:
        graph.pop("stale_nodes", None)
        (VAULT / "deals" / deal / "models" / "model_graph.json").write_text(
            json.dumps(graph, indent=2), encoding="utf-8")
        print("  [reset] Cleared previous stale markers")

    if node_id and divergence >= 0.10:
        stale_chain = rt._mark_model_node_stale(deal, graph, node_id)
        print(f"  Marked stale: {len(stale_chain)} nodes")
        for nid in stale_chain:
            node_info = next((n for n in graph["nodes"] if n["model_node_id"] == nid), {})
            print(f"    ⚠ {nid:<45} [{node_info.get('kind', '?')}]")
    elif not node_id:
        print("  No model node matched — staleness cascade skipped")
    else:
        print("  Divergence below threshold — no staleness cascade")

    # Show current stale_nodes in graph
    stale_now = graph.get("stale_nodes", [])
    print(f"\n  Current stale model nodes: {len(stale_now)}")
    if stale_now:
        for nid in stale_now[:5]:
            print(f"    · {nid}")

    # ── 5. Pipeline agent ───────────────────────────────────────────────────
    print("\n── 5. Pipeline Agent — Portfolio Brief ────────────────────────────")
    agent = rt.PipelineAgent()
    content = agent.rebuild()
    lines = [l for l in content.splitlines() if l.startswith("|") and deal in l]
    if lines:
        print(f"  {lines[0]}")
    else:
        print(f"  (deal {deal} not in pipeline — no deal.md state?)")

    # ── 6. Summary ──────────────────────────────────────────────────────────
    print("\n── Summary ────────────────────────────────────────────────────────")
    print(f"  Claims in vault:      {len(all_claims)}")
    print(f"  EBITDA claims at IC:  {len(ebitda_claims_at_ic)}")
    print(f"  Best baseline match:  {best_match['id'] if best_match else 'none'} ({best_score:.0%} sim)")
    print(f"  EBITDA divergence:    {divergence*100:.1f}%  {'⚠ ALERT' if divergence >= 0.10 else 'OK'}")
    print(f"  Model node affected:  {node_id or 'none matched'}")
    print(f"  Stale model nodes:    {len(stale_now)}")
    print(f"  PIPELINE.md updated:  {'yes' if (VAULT / 'PIPELINE.md').exists() else 'no'}")
    print()


def main():
    ap = argparse.ArgumentParser(description="PE OS retrieval + staleness cascade test")
    ap.add_argument("--deal", default="keystone")
    ap.add_argument("--reset", action="store_true", help="Reset stale markers before test")
    args = ap.parse_args()
    test_retrieval(args.deal, args.reset)


if __name__ == "__main__":
    main()
