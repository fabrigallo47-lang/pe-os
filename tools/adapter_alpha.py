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
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.bridge_v7 import compile_v7_bundle

EXECUTION_DEFAULT = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"


class E3AdapterInputError(ValueError):
    """Raised when an E3 manifest cannot cross the runtime boundary safely."""


@dataclass(frozen=True)
class E3RuntimeArtifacts:
    """The explicit E3 → runtime adapter result used by CLI and live intake."""

    extraction_graph: dict[str, Any]
    bundle: dict[str, Any]

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


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_e3_manifest(e3: Mapping[str, Any]) -> None:
    """Validate the fields the semantic/runtime compiler relies on.

    The extractor schema is deliberately wider than the runtime boundary. This
    check pins the small contract between them so malformed or ambiguous E3
    payloads fail before they can become an institutional graph.
    """
    if not isinstance(e3, Mapping):
        raise E3AdapterInputError("E3 manifest must be an object")
    claims = e3.get("claims")
    if not isinstance(claims, list):
        raise E3AdapterInputError("E3 manifest must contain claims[]")

    required = (
        "claim_id",
        "statement",
        "source_id",
        "locator",
        "epistemic_class",
        "period",
        "perimeter",
    )
    claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            raise E3AdapterInputError(f"claims[{index}] must be an object")
        missing = [field for field in required if field not in claim]
        if missing:
            raise E3AdapterInputError(
                f"claims[{index}] is missing required fields: {', '.join(missing)}"
            )
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise E3AdapterInputError(f"claims[{index}].claim_id must be a non-empty string")
        if claim_id in claim_ids:
            raise E3AdapterInputError(f"duplicate E3 claim_id: {claim_id}")
        claim_ids.add(claim_id)
        epistemic = claim.get("epistemic_class")
        if epistemic not in {"asserted", "observed", "derived", "attested"}:
            raise E3AdapterInputError(
                f"claims[{index}].epistemic_class is invalid: {epistemic!r}"
            )

    metadata = e3.get("extraction_metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        raise E3AdapterInputError("extraction_metadata must be an object")
    compiler_fields = metadata.get("compiler_fields_per_claim", [])
    if not isinstance(compiler_fields, list):
        raise E3AdapterInputError("compiler_fields_per_claim must be an array")
    seen_compiler_ids: set[str] = set()
    for index, fields in enumerate(compiler_fields):
        if not isinstance(fields, Mapping):
            raise E3AdapterInputError(
                f"compiler_fields_per_claim[{index}] must be an object"
            )
        claim_id = fields.get("claim_id")
        if claim_id not in claim_ids:
            raise E3AdapterInputError(
                f"compiler fields reference unknown claim_id: {claim_id!r}"
            )
        if claim_id in seen_compiler_ids:
            raise E3AdapterInputError(f"duplicate compiler fields for claim_id: {claim_id}")
        seen_compiler_ids.add(str(claim_id))


def e3_to_extraction_graph(
    e3: Mapping[str, Any],
    *,
    e3_claims_sha256: str | None = None,
) -> dict[str, Any]:
    """
    Convert E3 CAP-003 JSON to the NetworkX extraction graph format
    expected by bridge_v7._enrich_claims().

    Claim node fields used by bridge_v7:
      type, id, value, unit, epistemic, direction, statement, locator,
      derivation, deal, metric, period (optional), source_doc (optional)
    """
    validate_e3_manifest(e3)
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
            "e3_claims_sha256": e3_claims_sha256 or _canonical_sha256(e3),
        },
        "nodes": nodes,
        "edges": [],   # metric/period edges not needed — fields are on nodes
    }
    return graph


def compile_e3_runtime_bundle(
    e3: Mapping[str, Any],
    execution_path: Path,
    *,
    status: str = "ALPHA",
    deal: str | None = None,
    e3_claims_sha256: str | None = None,
    extraction_graph_path: Path | None = None,
) -> E3RuntimeArtifacts:
    """Compile a validated E3 manifest into the definitive V7 runtime inputs.

    Callers receive both the auditable intermediate graph and the compiled
    Current/mapping/manifest bundle. When ``extraction_graph_path`` is given,
    the exact graph compiled by the bridge is persisted there.
    """
    graph = e3_to_extraction_graph(e3, e3_claims_sha256=e3_claims_sha256)
    resolved_deal = deal or str(e3.get("deal") or "unknown")
    if extraction_graph_path is not None:
        extraction_graph_path.parent.mkdir(parents=True, exist_ok=True)
        _write(extraction_graph_path, graph)
        bundle = compile_v7_bundle(
            extraction_graph_path,
            execution_path,
            status=status,
            deal=resolved_deal,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="panta-e3-adapter-") as tmp:
            graph_path = Path(tmp) / "extraction_graph.json"
            _write(graph_path, graph)
            bundle = compile_v7_bundle(
                graph_path,
                execution_path,
                status=status,
                deal=resolved_deal,
            )
    return E3RuntimeArtifacts(extraction_graph=graph, bundle=bundle)


# Compatibility for older local callers; new code must use the public contract.
_e3_to_extraction_graph = e3_to_extraction_graph


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
    e3_sha = hashlib.sha256(e3_path.read_bytes()).hexdigest()
    eg_path = out_dir / "extraction_graph.json"
    try:
        artifacts = compile_e3_runtime_bundle(
            e3,
            exec_path,
            status=args.status,
            deal=args.deal,
            e3_claims_sha256=e3_sha,
            extraction_graph_path=eg_path,
        )
    except (E3AdapterInputError, ValueError) as exc:
        sys.exit(f"[adapter_alpha] Bridge validation error:\n{exc}")
    extraction_graph = artifacts.extraction_graph
    eg_size = eg_path.stat().st_size
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
    print("[adapter_alpha] Step 2: V7 bundle compiled via the public E3 runtime contract.")
    bundle = artifacts.bundle
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
        assemble(out_dir, bundle, event_src, kit=None, execution_src=exec_path)
    except Exception as exc:
        sys.exit(f"[adapter_alpha] Bundle assembly error: {exc}")

    cg = bundle["current_graph"]
    mf = bundle["manifest"]

    def _count(value: Any) -> int:
        if isinstance(value, (list, tuple, dict, set)):
            return len(value)
        return int(value or 0)

    admitted_count  = mf.get("admitted_claim_count", 0)
    position_count  = _count(cg.get("case_positions"))
    edge_count      = _count(cg.get("claim_position_edges"))
    pm_dir_count    = _count(cg.get("position_model_directions"))

    # Step 4 — human-readable report
    cp_dict = bundle.get("_cp_dict", {})
    unbound_mn = _count(cg.get("unbound_model_nodes"))
    pm_bindings = _count(cg.get("position_model_bindings"))
    model_node_count = _count(cg.get("model_nodes"))

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
        f"  Unbound MN      : {unbound_mn} of {model_node_count} total",
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
