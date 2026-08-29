"""Instantiate governed runtime bundles from an archetype and case mapping.

This module intentionally cannot infer financial formulas.  A case supplies
its own model nodes/formulas; the archetype supplies only the stable grammar
and governance contract.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


class RuntimeTemplateError(ValueError):
    pass


def load_template(archetype_id: str) -> dict[str, Any]:
    path = ROOT / "vault" / "policy" / "archetypes" / f"{archetype_id}.json"
    if not path.exists():
        raise RuntimeTemplateError(f"Unknown runtime archetype: {archetype_id}")
    template = json.loads(path.read_text(encoding="utf-8"))
    if template.get("schema_version") != "panta.archetype-runtime/1.0":
        raise RuntimeTemplateError("Unsupported runtime archetype schema")
    return template


def instantiate(case_id: str, case_config: dict[str, Any]) -> dict[str, Any]:
    """Return a case-owned V7 execution graph from declared mapping only."""
    template = load_template(str(case_config.get("archetype_id") or ""))
    nodes = case_config.get("model_nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise RuntimeTemplateError("Runtime mapping requires at least one declared model node")
    formulas = case_config.get("formulas", [])
    if not isinstance(formulas, list):
        raise RuntimeTemplateError("Runtime mapping formulas must be a list")
    required = (template.get("runtime_contract") or {}).get("required_case_artifacts", [])
    return {
        "format_version": "v7", "schema_version": "1.0",
        "deal": {"slug": case_id, "name": case_config.get("name") or case_id,
                 "company": case_config.get("company") or case_id},
        "compiler": {"source": "archetype-runtime", "archetype_id": template["archetype_id"]},
        "model_nodes": copy.deepcopy(nodes), "formulas": copy.deepcopy(formulas),
        "directed_model_edges": copy.deepcopy(case_config.get("directed_model_edges", [])),
        "rule_switches": copy.deepcopy(case_config.get("rule_switches", [])),
        "model_controls": copy.deepcopy(case_config.get("model_controls", [])),
        "runtime_contract": {"archetype_id": template["archetype_id"],
                             "required_case_artifacts": required,
                             "mapping_declared": True},
    }
