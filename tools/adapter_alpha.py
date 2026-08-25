#!/usr/bin/env python3
"""
adapter_alpha.py — Adapter Alpha for PANTA.

Converts E3 CAP-003 claims (extract_v2 output) into the V7 bundle format
expected by Anto's runtime kernel, using bridge_v7.compile_v7_bundle().

Pipeline:
  E3 e3_claims.json  →  [adapter_alpha]  →  extraction_graph (NetworkX fmt)
  extraction_graph + execution_graph_v7.json  →  [bridge_v7]  →  V7 bundle

V7 bundle outputs:
  current_graph.json          — admitted claims + Case Positions + model values
  execution_mapping.json      — runtime contract (normalised)
  adapter_report.json         — coverage limits + identity migration map
  admission_manifest.json     — stable admitted claim IDs + hashes
  extraction_graph.json       — intermediate graph (auditable)
  adapter_alpha_report.txt    — human-readable summary

Usage:
  python3 tools/adapter_alpha.py \\
      --e3       pipeline_out/e3/K-IC/e3_claims.json \\
      --execution vault/deals/keystone/models/execution_graph_v7.json \\
      --out      pipeline_out/e3/K-IC/adapter_alpha/

  python3 tools/adapter_alpha.py --manifest K-PRE \\
      --e3       pipeline_out/e3/K-PRE/e3_claims.json \\
      --execution vault/deals/keystone/models/execution_graph_v7.json \\
      --out      pipeline_out/e3/K-PRE/adapter_alpha/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.bridge_v7 import compile_v7_bundle

EXECUTION_DEFAULT = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"

# Source ID → source_doc string used by bridge_v7._known_at()
_SRC_TO_SOURCE_DOC: dict[str, str] = {
    "SRC-CIM":       "Seller CIM",
    "SRC-DR":        "Data Room Extract",
    "SRC-IA":        "Firm Initial Assessment",
    "SRC-QL":        "Seller CIM",        # question list — treat as CIM-era
    "SRC-QOE":       "QoE Report",
    "SRC-MODEL-SUM": "Firm Model Summary",
    "SRC-MODEL":     "Firm Model Summary",
    "SRC-IC":        "IC Memo",
    "SRC-BP1":       "Board Pack",
    "SRC-BP2":       "Board Pack",
    "SRC-AMEND":     "Board Pack",
    "SRC-COMP1":     "Board Pack",
    "SRC-COMP2":     "Board Pack",
    "SRC-EXIT":      "Board Pack",
}


def _e3_to_extraction_graph(e3: dict) -> dict:
    """
    Convert E3 CAP-003 JSON to the NetworkX extraction graph format
    expected by bridge_v7._enrich_claims().

    Claim node fields used by bridge_v7:
      type, id, value, unit, epistemic, direction, statement, locator,
      derivation, deal, metric, period (optional), source_doc (optional)
    """
    claims = e3["claims"]
    compiler_fields = {
        cf["claim_id"]: cf
        for cf in e3.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
    }

    nodes = []
    for i, c in enumerate(claims):
        cid = c["claim_id"]
        meta = compiler_fields.get(cid, {})

        src_id = c.get("source_id", "")
        source_doc = _SRC_TO_SOURCE_DOC.get(src_id, "")

        node = {
            "type":         "claim",
            "id":           f"claim:{i:04d}",       # ordinal for bridge compatibility
            "stable_id":    cid,                     # carry E3 stable_id through
            "value":        c.get("value") or "",
            "unit":         c.get("unit") or "",
            "epistemic":    c.get("epistemic_class") or "asserted",
            "direction":    meta.get("direction") or "supports",
            "statement":    c.get("statement") or "",
            "locator":      c.get("locator") or "",
            "derivation":   meta.get("derivation"),
            "deal":         e3.get("deal", "keystone"),
            # Fields bridge_v7 checks inline (no edge needed when present):
            "metric":       meta.get("metric") or "",
            "period":       c.get("period") or "",
            "perimeter":    c.get("perimeter") or "",
            "source_doc":   source_doc,
            "source_id":    src_id,
            # CAP-003 passthrough (preserved in extraction_metadata)
            "definition_id":       c.get("definition_id"),
            "ground_truth_flag":   c.get("ground_truth_flag", False),
            "validation_only":     c.get("validation_only", False),
            "notes":               c.get("notes"),
        }
        nodes.append(node)

    graph = {
        "directed":   True,
        "multigraph": False,
        "graph":      {
            "deal":          e3.get("deal", "keystone"),
            "manifest_id":   e3.get("manifest_id"),
            "schema_version": e3.get("schema_version"),
            "extractor":     "extract_v2",
            "e3_claims_sha256": None,  # filled below
        },
        "nodes": nodes,
        "edges": [],   # metric/period edges not needed — fields are on nodes
    }
    return graph


def _write(path: Path, obj: dict, indent: int = 2) -> int:
    text = json.dumps(obj, indent=indent, ensure_ascii=False)
    path.write_text(text)
    return len(text.encode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--e3",        required=True, help="E3 e3_claims.json path")
    ap.add_argument("--execution", default=str(EXECUTION_DEFAULT),
                    help="execution_graph_v7.json path")
    ap.add_argument("--out",       required=True, help="Output directory")
    ap.add_argument("--manifest",  default=None, help="Manifest label (K-IC/K-PRE/K-LIVE)")
    ap.add_argument("--status",    default="ALPHA", help="Bundle status tag")
    ap.add_argument("--deal",      default="keystone",
                    help="Deal slug — selects vault/deals/<slug>/deal_profile.json")
    ap.add_argument("--event",     default=None,
                    help="Correction event JSON (default: event_ebitda_correction.json)")
    args = ap.parse_args()

    e3_path   = Path(args.e3)
    exec_path = Path(args.execution)
    out_dir   = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not e3_path.exists():
        sys.exit(f"[adapter_alpha] E3 file not found: {e3_path}")
    if not exec_path.exists():
        sys.exit(f"[adapter_alpha] Execution graph not found: {exec_path}")

    print(f"[adapter_alpha] Reading E3  : {e3_path}")
    with open(e3_path) as f:
        e3 = json.load(f)

    manifest_label = args.manifest or e3.get("manifest_id", "UNKNOWN")
    claim_count = len(e3.get("claims", []))
    print(f"[adapter_alpha] Manifest    : {manifest_label}")
    print(f"[adapter_alpha] Claims      : {claim_count}")

    # Step 1 — convert E3 → extraction graph
    print("[adapter_alpha] Step 1: converting E3 → extraction graph ...")
    extraction_graph = _e3_to_extraction_graph(e3)

    # Embed e3 sha256 in graph metadata
    e3_sha = hashlib.sha256(e3_path.read_bytes()).hexdigest()
    extraction_graph["graph"]["e3_claims_sha256"] = e3_sha

    # Write intermediate extraction graph (auditable)
    eg_path = out_dir / "extraction_graph.json"
    eg_size = _write(eg_path, extraction_graph)
    print(f"[adapter_alpha]   → extraction_graph.json ({eg_size // 1024}KB, {claim_count} claim nodes)")

    # Step 1b — grounding gate. Reports what could not be verified against the
    # cited sources; it never drops or rewrites a claim (agents do not adjudicate).
    print("[adapter_alpha] Step 1b: grounding gate ...")
    try:
        from tools.grounding_gate import run as _gg_run
        gg_rep = _gg_run(e3_path, args.deal)
        _write(out_dir / "grounding_review.json", gg_rep)
        print(f"[adapter_alpha]   → {gg_rep['claims_clean']}/{gg_rep['claims_total']} clean, "
              f"{gg_rep['blocking_total']} blocking, "
              f"{gg_rep['claims_flagged']} flagged → grounding_review.json")
    except Exception as exc:            # never block the bundle on the gate
        gg_rep = {"error": str(exc)}
        print(f"[adapter_alpha]   grounding gate skipped: {exc}")

    # Step 2 — run bridge_v7.compile_v7_bundle()
    print("[adapter_alpha] Step 2: running bridge_v7.compile_v7_bundle() ...")
    try:
        bundle = compile_v7_bundle(eg_path, exec_path, status=args.status,
                                   deal=args.deal)
    except ValueError as exc:
        sys.exit(f"[adapter_alpha] Bridge validation error:\n{exc}")
    bundle["adapter_report"]["grounding"] = {
        k: v for k, v in gg_rep.items() if k != "review_queue"
    }

    # Step 3 — write V7 bundle outputs
    print("[adapter_alpha] Step 3: writing V7 bundle ...")

    cg_size   = _write(out_dir / "current_graph.json",       bundle["current_graph"])
    em_size   = _write(out_dir / "execution_mapping.json",   bundle["execution_mapping"])
    ar_size   = _write(out_dir / "adapter_report.json",      bundle["adapter_report"])
    mf_size   = _write(out_dir / "admission_manifest.json",  bundle["manifest"])

    # Step 3b — assemble the remaining 12 bundle files from THIS run.
    # Previously only the 4 above were written and the rest were carried over by
    # hand, so graph.json described a different extraction than claims.json.
    print("[adapter_alpha] Step 3b: assembling full V7 bundle ...")
    from tools.bundle_assemble import assemble
    bundle["_deal"] = args.deal
    event_src = Path(args.event) if getattr(args, "event", None) else ROOT / "event_ebitda_correction.json"
    try:
        assemble(out_dir, bundle, event_src, kit=None)
    except Exception as exc:
        sys.exit(f"[adapter_alpha] Bundle assembly error: {exc}")

    cg = bundle["current_graph"]
    mf = bundle["manifest"]

    admitted_count  = mf.get("admitted_claim_count", 0)
    position_count  = cg.get("case_positions", 0)
    edge_count      = cg.get("claim_position_edges", 0)
    pm_dir_count    = cg.get("position_model_directions", 0)

    # Step 4 — human-readable report
    cp_dict = bundle.get("_cp_dict", {})
    unbound_mn = cg.get("unbound_model_nodes", 0)
    pm_bindings = cg.get("position_model_bindings", 0)

    lines = [
        f"Adapter Alpha Report — {manifest_label}",
        "=" * 55,
        f"  Deal            : {e3.get('deal', 'keystone')}",
        f"  Manifest        : {manifest_label}",
        f"  E3 sha256       : {e3_sha[:16]}...",
        f"  Status          : {args.status}",
        "",
        "E3 → extraction graph:",
        f"  Input claims    : {claim_count}",
        f"  Claim nodes     : {len(extraction_graph['nodes'])}",
        "",
        "V7 bridge output:",
        f"  Admitted        : {admitted_count}",
        f"  Case Positions  : {position_count}",
        f"  CP edges        : {edge_count}",
        f"  PM directions   : {pm_dir_count}",
        f"  PM bindings     : {pm_bindings}",
        f"  Unbound MN      : {unbound_mn} of {cg.get('model_nodes', 0)} total",
        "",
        "Output files:",
        f"  extraction_graph.json     {eg_size // 1024}KB",
        f"  current_graph.json        {cg_size // 1024}KB",
        f"  execution_mapping.json    {em_size // 1024}KB",
        f"  adapter_report.json       {ar_size // 1024}KB",
        f"  admission_manifest.json   {mf_size // 1024}KB",
        "",
        "Case Positions admitted:",
    ]

    for cp_id, cp in cp_dict.items():
        claim_ids = cp.get("claim_ids", [])
        mn_ids    = cp.get("model_node_ids", [])
        lines.append(f"  {cp_id}: {len(claim_ids)} claims → {len(mn_ids)} model nodes")

    report_text = "\n".join(lines)
    (out_dir / "adapter_alpha_report.txt").write_text(report_text)
    print()
    print(report_text)


if __name__ == "__main__":
    main()
