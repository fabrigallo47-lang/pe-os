#!/usr/bin/env python3
"""Pure compiler/Case Store bundle -> PANTA V20 frontend projection mapping.

This adapter is deliberately transport-neutral. It maps an already produced,
validated compiler bundle into a supplied projection shell. It does not call a
model, derive contradictions, compute economics, decide authority, or settle
state. Production transport/authentication remains an integration boundary.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

V20_ARRAYS = (
    "participants", "interactions", "utterances", "claims", "derivation_specs",
    "discrepancy_rules", "agent_missions", "spine_change_proposals",
    "condition_edges", "validation_envelopes",
)

class CompilerProjectionError(ValueError):
    pass

def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompilerProjectionError(f"{name} must be an object")
    return value

def _known(value: Mapping[str, Any], cutoff: dt.datetime | None) -> bool:
    if cutoff is None:
        return True
    raw = value.get("known_at")
    if not raw:
        return False
    return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")) <= cutoff

def map_compiler_bundle(base_projection: Mapping[str, Any], compiler_bundle: Mapping[str, Any], *, as_of_date: str | None = None) -> dict[str, Any]:
    """Merge a compiler bundle through explicit, typed collection boundaries."""
    base = copy.deepcopy(dict(_require_mapping(base_projection, "base_projection")))
    bundle = _require_mapping(compiler_bundle, "compiler_bundle")
    if bundle.get("schema_version") != "compiler-bundle/20.0":
        raise CompilerProjectionError("Unsupported compiler bundle version")
    deal = _require_mapping(base.get("deal"), "base_projection.deal")
    if bundle.get("case_id") != deal.get("case_id"):
        raise CompilerProjectionError("Compiler bundle case_id does not match projection")
    cutoff = None
    if as_of_date:
        cutoff = dt.datetime.fromisoformat(as_of_date + "T23:59:59.999999+00:00")
    for key in V20_ARRAYS:
        values = bundle.get(key, [])
        if not isinstance(values, list):
            raise CompilerProjectionError(f"compiler_bundle.{key} must be an array")
        deal[key] = [copy.deepcopy(item) for item in values if _known(item, cutoff)]
    for key in ("archetype", "venture_financing"):
        if key in bundle:
            deal[key] = copy.deepcopy(bundle[key])
    if "lenses" in bundle:
        if not isinstance(bundle["lenses"], list):
            raise CompilerProjectionError("compiler_bundle.lenses must be an array")
        deal["lenses"] = [copy.deepcopy(item) for item in bundle["lenses"] if _known(item, cutoff)]
    source_center = deal.setdefault("source_center", {})
    if "sources" in bundle:
        if not isinstance(bundle["sources"], list):
            raise CompilerProjectionError("compiler_bundle.sources must be an array")
        source_center["sources"] = [copy.deepcopy(item) for item in bundle["sources"] if _known(item, cutoff)]
    if "pipeline_issues" in bundle:
        source_center["pipeline_issues"] = copy.deepcopy(bundle["pipeline_issues"])
    # Generated proposals are intentionally empty at this boundary. A compiler
    # or governed proposal service may populate them separately.
    deal.setdefault("derivations", [])
    deal.setdefault("discrepancy_candidates", [])
    deal.setdefault("hypotheses", [])
    payload_hash = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    deal["projection_id"] = f"PROJ-COMPILER-{payload_hash[:16]}"
    if as_of_date:
        deal["as_of_date"] = as_of_date
        deal["as_of_state_id"] = f"ASOF-KNOWN-{as_of_date}"
    temporal = deal.setdefault("temporal", {})
    temporal.update({
        "basis": "KNOWN_AT",
        "effective_axis": "effective_date",
        "knowledge_axis": "known_at",
        "replay_source": "REGISTRY_EVENTS",
    })
    base["schema_version"] = "frontend-projection/20.0"
    base["package_version"] = "20.0.0"
    base["compiler_mapping"] = {
        "name": "compiler-bundle-to-frontend-projection", "version": "20.0.0",
        "bundle_hash": f"sha256:{payload_hash}", "pure_function": True,
        "generated_proposals_admitted": False,
    }
    return base

def compile_frontend_projection(base_projection: Mapping[str, Any], compiler_bundle: Mapping[str, Any], as_of_state_id: str | None = None) -> Mapping[str, Any]:
    """Compatibility entrypoint for integration callers."""
    output = map_compiler_bundle(base_projection, compiler_bundle)
    if as_of_state_id:
        output["deal"]["as_of_state_id"] = as_of_state_id
    return output

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_projection",type=Path)
    parser.add_argument("compiler_bundle",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--as-of-date")
    args=parser.parse_args()
    result=map_compiler_bundle(json.loads(args.base_projection.read_text()),json.loads(args.compiler_bundle.read_text()),as_of_date=args.as_of_date)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")

if __name__=="__main__": main()
