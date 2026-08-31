#!/usr/bin/env python3
"""Populate a PANTA execution mapping from resolved workbook formulas.

PAN-65 owns semantic model-node identity and PAN-66 owns translation of Excel
formula text into the bounded decimal runtime grammar.  PAN-67 is the narrow
composition boundary between those artifacts and ``execution_mapping``:

* every admitted binding becomes one runtime model node;
* compiled formula inputs become explicit ``DRIVES`` dependencies;
* Excel ``IF`` switches and numerical SCC configurations are carried through;
* resolver/compiler Human Stops remain top-level coverage limits;
* existing institutional directions, controls and inverse solvers are kept.

No financial meaning or policy is inferred here.  Missing identity dimensions
are labelled ``UNSPECIFIED_*`` and remain visible instead of being guessed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.formula_compiler import compile_formulas, normalize_locator


SCHEMA_VERSION = "execution-mapping-compilation/1.0"
COMPILER_VERSION = "pan67-1.0"
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ExecutionMappingCompileError(ValueError):
    """The supplied artifacts cannot be composed without ambiguity."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load_json(value: Any) -> Any:
    if isinstance(value, (str, Path)):
        return json.loads(Path(value).read_text(encoding="utf-8"))
    return copy.deepcopy(value)


def _source_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("source_graph must be a JSON object or path")
    if isinstance(payload.get("cells"), Mapping):
        return dict(payload)
    workbooks = payload.get("workbooks")
    if isinstance(workbooks, Sequence) and not isinstance(workbooks, (str, bytes)):
        usable = [
            item.get("graph")
            for item in workbooks
            if isinstance(item, Mapping)
            and isinstance(item.get("graph"), Mapping)
            and isinstance(item["graph"].get("cells"), Mapping)
        ]
        if len(usable) == 1:
            return dict(usable[0])
        if len(usable) > 1:
            raise ExecutionMappingCompileError(
                "Multiple workbooks must be populated separately because PAN-65 locators "
                "do not carry a workbook-qualified identity."
            )
    raise ExecutionMappingCompileError("Source graph contains no L1 workbook cells")


def _binding_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("bindings", "admitted", "resolved_bindings"):
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    if payload and all(isinstance(value, str) for value in payload.values()):
        return [
            {"locator": locator, "model_node_id": model_node_id}
            for locator, model_node_id in payload.items()
        ]
    return []


def _binding_index(payload: Any) -> dict[str, dict[str, Any]]:
    by_locator: dict[str, dict[str, Any]] = {}
    model_by_locator: dict[str, str] = {}
    locator_by_model: dict[str, str] = {}
    for raw in _binding_items(payload):
        locator = raw.get("locator") or raw.get("cell") or raw.get("workbook_cell_ref")
        model_node_id = raw.get("model_node_id") or raw.get("mn_id") or raw.get("id")
        if not locator or not model_node_id:
            continue
        try:
            normalized = normalize_locator(str(locator))
        except ValueError:
            continue
        prior_model = model_by_locator.get(normalized)
        if prior_model is not None and prior_model != str(model_node_id):
            raise ExecutionMappingCompileError(
                f"Binding locator {normalized} maps to both {prior_model} and {model_node_id}"
            )
        model_node_id = str(model_node_id)
        prior_locator = locator_by_model.get(model_node_id)
        if prior_locator is not None and prior_locator != normalized:
            raise ExecutionMappingCompileError(
                f"Model node {model_node_id} is bound to both {prior_locator} and {normalized}"
            )
        model_by_locator[normalized] = model_node_id
        locator_by_model[model_node_id] = normalized
        by_locator[normalized] = raw
    return by_locator


def _empty_mapping(
    source: Mapping[str, Any],
    bindings: Any,
    canonical_graph_hash: str | None,
) -> dict[str, Any]:
    graph_hash = canonical_graph_hash or _hash(
        {
            "kind": "PAN-67-STANDALONE-COMPILER-INPUT",
            "source_digest": source.get("digest"),
            "binding_resolution": bindings,
        }
    )
    if not _HASH_RE.fullmatch(str(graph_hash)):
        raise ExecutionMappingCompileError(
            "canonical_graph_hash must use the sha256:<64 lowercase hex> form"
        )
    return {
        "mapping_version": COMPILER_VERSION,
        "canonical_graph_hash": str(graph_hash),
        "model_nodes": [],
        "directed_model_edges": [],
        "position_model_directions": [],
        "formulas": [],
        "rule_switches": [],
        "inverse_solver_configs": [],
        "model_controls": [],
        "cyclic_component_solver_configs": [],
        "coverage_limits": [],
    }


def _collection(mapping: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = mapping.setdefault(name, [])
    if not isinstance(value, list):
        raise ExecutionMappingCompileError(f"execution_mapping.{name} must be a list")
    if not all(isinstance(item, Mapping) for item in value):
        raise ExecutionMappingCompileError(
            f"execution_mapping.{name} may contain only objects"
        )
    return [dict(item) for item in value]


def _merge_by_id(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
    key: str,
    collection_name: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in [*existing, *incoming]:
        item = dict(raw)
        identity = str(item.get(key) or "")
        if not identity:
            raise ExecutionMappingCompileError(
                f"{collection_name} item is missing required identity {key}"
            )
        prior = merged.get(identity)
        if prior is not None and _canonical(prior) != _canonical(item):
            raise ExecutionMappingCompileError(
                f"Conflicting {collection_name} entries for {key}={identity}"
            )
        merged[identity] = item
    return [merged[identity] for identity in sorted(merged)]


def _normalise_resolver_limit(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(dict(raw))
    limit_id = str(item.pop("coverage_limit_id", None) or item.get("limit_id") or "")
    if not limit_id:
        limit_id = "CL-PAN65-" + hashlib.sha256(_canonical(item).encode()).hexdigest()[:16].upper()
    item["limit_id"] = limit_id
    candidates = [str(value) for value in item.get("candidate_locators", []) if value]
    if not isinstance(item.get("scope_ids"), list):
        identity = item.get("identity") if isinstance(item.get("identity"), Mapping) else {}
        concept_id = str(identity.get("concept_id") or "")
        item["scope_ids"] = candidates or ([concept_id] if concept_id else [])
    if not item.get("effect"):
        item["effect"] = str(item.get("message") or "PAN-65 binding resolution stopped")
    item.setdefault("reason_code", "UNRESOLVED_MODEL_BINDING")
    item.setdefault("resolution", "HUMAN_STOP")
    item.setdefault("source_ref", "tools/model_resolver.py")
    return item


def _node_from_binding(
    binding: Mapping[str, Any],
    locator: str,
    cell: Mapping[str, Any],
    workbook: str,
    formulas_by_output: Mapping[str, Mapping[str, Any]],
    cyclic_members: set[str],
) -> dict[str, Any]:
    model_node_id = str(
        binding.get("model_node_id") or binding.get("mn_id") or binding.get("id")
    )
    identity = binding.get("identity") if isinstance(binding.get("identity"), Mapping) else {}
    formula = formulas_by_output.get(model_node_id)
    is_formula = str(cell.get("kind") or "").lower() == "formula"
    if model_node_id in cyclic_members:
        computational_form = "NUMERICAL_CYCLE"
    elif formula is not None:
        computational_form = "DIRECT_FORMULA"
    elif is_formula:
        computational_form = "MONITOR_ONLY"
    else:
        computational_form = "DIRECT_INPUT"
    initial_value = binding.get("value")
    if initial_value is None:
        initial_value = (
            cell.get("evaluated_value")
            if is_formula and cell.get("evaluated_value") is not None
            else cell.get("value")
        )
    period = str(binding.get("period") or identity.get("period") or "UNSPECIFIED_PERIOD")
    perimeter = str(
        binding.get("perimeter")
        or binding.get("scope")
        or identity.get("scope")
        or identity.get("entity")
        or "UNSPECIFIED_PERIMETER"
    )
    return {
        "model_node_id": model_node_id,
        "label": binding.get("label") or binding.get("concept_id") or model_node_id,
        "computational_form": computational_form,
        "unit": binding.get("unit"),
        "period": period,
        "perimeter": perimeter,
        "initial_value": initial_value,
        "workbook_ref": f"{workbook}:{locator}",
        "formula_id": formula.get("formula_id") if formula else None,
        "directed_deps": list(formula.get("input_ids", [])) if formula else [],
        "binding_id": binding.get("binding_id"),
        "concept_id": binding.get("concept_id"),
        "binding_reason_codes": list(binding.get("reason_codes") or []),
    }


def _merge_nodes(
    existing: Sequence[Mapping[str, Any]],
    generated: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw in existing:
        node = copy.deepcopy(dict(raw))
        node_id = str(node.get("model_node_id") or "")
        if not node_id:
            raise ExecutionMappingCompileError("model_nodes item is missing model_node_id")
        if node_id in by_id:
            raise ExecutionMappingCompileError(f"Duplicate model node {node_id}")
        by_id[node_id] = node
    for raw in generated:
        node = copy.deepcopy(dict(raw))
        node_id = str(node["model_node_id"])
        prior = by_id.get(node_id)
        if prior is None:
            by_id[node_id] = node
            continue
        # Institutional labels and Current values belong to the existing
        # mapping.  PAN-67 owns only executable topology and fills absent facts.
        for field in ("computational_form", "formula_id", "directed_deps", "workbook_ref"):
            prior[field] = node[field]
        for field, value in node.items():
            if field not in prior or prior[field] in (None, ""):
                prior[field] = value
    return [by_id[node_id] for node_id in sorted(by_id)]


def _validate_population(
    mapping: Mapping[str, Any],
    generated_formula_ids: set[str],
) -> None:
    node_ids = {
        str(item.get("model_node_id"))
        for item in mapping.get("model_nodes", [])
        if isinstance(item, Mapping) and item.get("model_node_id")
    }
    formulas = {
        str(item.get("formula_id")): item
        for item in mapping.get("formulas", [])
        if isinstance(item, Mapping) and item.get("formula_id")
    }
    formula_outputs: dict[str, str] = {}
    for formula_id in sorted(generated_formula_ids):
        formula = formulas.get(formula_id)
        if formula is None:
            raise ExecutionMappingCompileError(f"Generated formula disappeared: {formula_id}")
        output_id = str(formula.get("output_id") or "")
        prior = formula_outputs.get(output_id)
        if prior is not None and prior != formula_id:
            raise ExecutionMappingCompileError(
                f"Model node {output_id} has multiple generated formulas: {prior}, {formula_id}"
            )
        formula_outputs[output_id] = formula_id
        endpoints = [output_id, *[str(value) for value in formula.get("input_ids", [])]]
        missing = sorted({value for value in endpoints if value not in node_ids})
        if missing:
            raise ExecutionMappingCompileError(
                f"Formula {formula_id} references undeclared model nodes: {', '.join(missing)}"
            )

    expected_edges = {
        (str(input_id), str(formula["output_id"]), formula_id)
        for formula_id, formula in formulas.items()
        if formula_id in generated_formula_ids
        for input_id in formula.get("input_ids", [])
    }
    actual_edges = {
        (
            str(edge.get("from_model_node_id")),
            str(edge.get("to_model_node_id")),
            str(edge.get("formula_or_function_ref")),
        )
        for edge in mapping.get("directed_model_edges", [])
        if isinstance(edge, Mapping)
        and str(edge.get("formula_or_function_ref")) in generated_formula_ids
        and edge.get("relation_type") == "DRIVES"
    }
    if actual_edges != expected_edges:
        raise ExecutionMappingCompileError(
            "Generated DRIVES edges do not exactly match compiled formula operands"
        )


def populate_execution_mapping(
    source_graph: Mapping[str, Any] | str | Path,
    binding_resolution: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
    execution_mapping: Mapping[str, Any] | str | Path | None = None,
    *,
    canonical_graph_hash: str | None = None,
    **solver_options: Any,
) -> dict[str, Any]:
    """Return an execution mapping populated with PAN-65/PAN-66 artifacts.

    ``execution_mapping`` may be an existing runtime mapping.  Its position
    directions, model controls, inverse solvers and unrelated formulas/edges
    are preserved.  Calling this function twice with identical inputs returns
    the same object.
    """

    raw_source = _load_json(source_graph)
    source = _source_payload(raw_source)
    bindings_payload = _load_json(binding_resolution)
    bindings_by_locator = _binding_index(bindings_payload)
    compilation = compile_formulas(source, bindings_payload, **solver_options)

    if execution_mapping is None:
        mapping = _empty_mapping(source, bindings_payload, canonical_graph_hash)
    else:
        raw_mapping = _load_json(execution_mapping)
        if not isinstance(raw_mapping, Mapping):
            raise TypeError("execution_mapping must be a JSON object or path")
        mapping = dict(raw_mapping)
        if canonical_graph_hash is not None:
            mapping["canonical_graph_hash"] = canonical_graph_hash
    graph_hash = str(mapping.get("canonical_graph_hash") or "")
    if not _HASH_RE.fullmatch(graph_hash):
        raise ExecutionMappingCompileError(
            "execution_mapping requires canonical_graph_hash in sha256:<64 lowercase hex> form"
        )
    mapping.setdefault("mapping_version", COMPILER_VERSION)

    formulas = [copy.deepcopy(item) for item in compilation["formulas"]]
    generated_formula_ids = {str(item["formula_id"]) for item in formulas}
    formulas_by_output = {str(item["output_id"]): item for item in formulas}
    if len(formulas_by_output) != len(formulas):
        raise ExecutionMappingCompileError(
            "PAN-65 bindings collapse multiple compiled formulas onto one model node"
        )
    cyclic_members = {
        str(member)
        for config in compilation["cyclic_component_solver_configs"]
        for member in config.get("member_ids", [])
    }

    cells = {
        normalize_locator(str(locator)): cell
        for locator, cell in source.get("cells", {}).items()
        if isinstance(cell, Mapping)
    }
    generated_nodes = [
        _node_from_binding(
            binding,
            locator,
            cells.get(locator, {}),
            str(source.get("workbook") or "workbook.xlsx"),
            formulas_by_output,
            cyclic_members,
        )
        for locator, binding in sorted(bindings_by_locator.items())
    ]
    mapping["model_nodes"] = _merge_nodes(
        _collection(mapping, "model_nodes"), generated_nodes
    )

    existing_formulas = _collection(mapping, "formulas")
    existing_outputs = {
        str(item.get("output_id")): str(item.get("formula_id"))
        for item in existing_formulas
        if item.get("output_id") and item.get("formula_id")
    }
    for formula in formulas:
        prior = existing_outputs.get(str(formula["output_id"]))
        if prior is not None and prior != str(formula["formula_id"]):
            raise ExecutionMappingCompileError(
                f"Output {formula['output_id']} already belongs to formula {prior}"
            )
    mapping["formulas"] = _merge_by_id(
        existing_formulas, formulas, "formula_id", "formulas"
    )

    drives_edges = []
    for raw in compilation["directed_model_edges"]:
        edge = copy.deepcopy(raw)
        edge["relation_type"] = "DRIVES"
        edge["source_ref"] = "tools/execution_mapping_compiler.py"
        drives_edges.append(edge)
    mapping["directed_model_edges"] = _merge_by_id(
        _collection(mapping, "directed_model_edges"),
        drives_edges,
        "edge_id",
        "directed_model_edges",
    )
    mapping["rule_switches"] = _merge_by_id(
        _collection(mapping, "rule_switches"),
        compilation["rule_switches"],
        "rule_switch_id",
        "rule_switches",
    )
    mapping["cyclic_component_solver_configs"] = _merge_by_id(
        _collection(mapping, "cyclic_component_solver_configs"),
        compilation["cyclic_component_solver_configs"],
        "component_id",
        "cyclic_component_solver_configs",
    )

    for required in (
        "position_model_directions",
        "inverse_solver_configs",
        "model_controls",
    ):
        mapping[required] = _collection(mapping, required)

    resolver_limits = []
    if isinstance(bindings_payload, Mapping):
        resolver_limits = [
            _normalise_resolver_limit(item)
            for item in bindings_payload.get("coverage_limits", [])
            if isinstance(item, Mapping)
        ]
    mapping["coverage_limits"] = _merge_by_id(
        _collection(mapping, "coverage_limits"),
        [*resolver_limits, *compilation["coverage_limits"]],
        "limit_id",
        "coverage_limits",
    )

    mapping["formula_compilation"] = {
        "schema_version": SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "status": compilation["status"],
        "source_digest": compilation["source_digest"],
        "binding_resolution_digest": compilation["binding_resolution_digest"],
        "input_digest": compilation["input_digest"],
        "stats": copy.deepcopy(compilation["stats"]),
        "edge_semantics": "DRIVES",
    }
    _validate_population(mapping, generated_formula_ids)
    return mapping


def compile_execution_mapping(
    source_graph: Mapping[str, Any] | str | Path,
    binding_resolution: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | Path,
    execution_mapping: Mapping[str, Any] | str | Path | None = None,
    **options: Any,
) -> dict[str, Any]:
    """Compatibility alias for callers that name the composition as a compile."""

    return populate_execution_mapping(
        source_graph, binding_resolution, execution_mapping, **options
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Populate a PANTA execution mapping with compiled Excel formulas"
    )
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--canonical-graph-hash")
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    result = populate_execution_mapping(
        arguments.source_graph,
        arguments.bindings,
        arguments.mapping,
        canonical_graph_hash=arguments.canonical_graph_hash,
    )
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    stats = result["formula_compilation"]["stats"]
    print(
        f"[execution_mapping_compiler] {stats['compiled_formula_count']}/"
        f"{stats['source_formula_count']} formulas, "
        f"{len(result['directed_model_edges'])} DRIVES edges, "
        f"{len(result['coverage_limits'])} coverage limits -> {arguments.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
