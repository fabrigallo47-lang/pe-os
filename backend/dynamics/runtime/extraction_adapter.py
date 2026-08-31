"""Stable adapter from a compiler extraction graph to the PANTA runtime.

The extraction graph is evidence produced by a compiler; it is not itself the
institutional Live Investment Case.  This module performs the explicit
boundary step:

    extraction + admission manifest -> Current Live Case + execution mapping

It never mutates the extraction input and never invents formulas, model
dependencies, policy bindings or institutional approval state.  Missing
execution information is carried forward as deterministic coverage limits.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from . import ledger_store
from .panta_transition_engine import apply_state_transition as _run_transition


ADAPTER_VERSION = "1.0.0"
CANONICAL_RELATIONS = frozenset(
    {"SUPPORTS", "CONTRADICTS", "DERIVES_FROM", "DRIVES", "CONDITIONS"}
)
MODEL_DIRECTIONS = frozenset(
    {
        "POSITION_DRIVES_MODEL",
        "MODEL_DERIVES_POSITION",
        "MODEL_VALIDATES_POSITION",
        "MONITOR_ONLY",
    }
)
ROUTE_LOGICS = frozenset(
    {"AND", "FORMULA", "INDEPENDENT", "AND_WITH_COUNTEREVIDENCE"}
)


class ExtractionInputError(ValueError):
    """Raised when the compiler extraction is structurally invalid."""


class AdmissionInputError(ValueError):
    """Raised when institutional admission is missing or inconsistent."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(_canonical_json(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _node_type(node: Mapping[str, Any]) -> str:
    return str(node.get("type", "")).strip().lower()


def _text(value: Any, fallback: str) -> str:
    return str(value) if value not in (None, "") else fallback


def _normalize_epistemic_class(value: Any) -> str:
    normalized = str(value or "asserted").strip().lower()
    return normalized if normalized in {"asserted", "observed", "derived", "attested"} else "asserted"


def _reason_code(reason: Any) -> str:
    text = str(reason or "").lower()
    if "formula" in text:
        return "MISSING_EXECUTABLE_FORMULA"
    if "dependency" in text or "directed" in text:
        return "MISSING_MODEL_DEPENDENCY"
    if "institution" in text or "current_value" in text or "append_only" in text:
        return "MISSING_INSTITUTIONAL_STATE"
    if "policy" in text or "authority" in text:
        return "MISSING_POLICY_BINDING"
    if "rule" in text or "branch" in text:
        return "MISSING_RULE_SWITCH_CONFIG"
    if "inverse" in text or "objective" in text:
        return "MISSING_INVERSE_SOLVER_CONFIG"
    if "solver" in text or "equation" in text:
        return "MISSING_NUMERICAL_SOLVER_CONFIG"
    if "control" in text or "coherence" in text or "covenant" in text:
        return "MISSING_MODEL_CONTROL"
    if "role" in text or "assignment" in text:
        return "MISSING_ROLE_ASSIGNMENT"
    if "artifact" in text:
        return "MISSING_ARTIFACT_REFERENCE"
    if "decision" in text or "/ic-record" in text:
        return "MISSING_DECISION_RECORD"
    return "MISSING_EXECUTABLE_MAPPING"


def validate_extraction_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Validate node/edge integrity and return deterministic indexes."""

    if not isinstance(graph, Mapping):
        raise ExtractionInputError("extraction graph must be an object")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ExtractionInputError("extraction graph must contain nodes[] and edges[]")

    node_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, Mapping):
            raise ExtractionInputError(f"nodes[{index}] must be an object")
        node = copy.deepcopy(dict(raw_node))
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ExtractionInputError(f"nodes[{index}].id must be a non-empty string")
        if node_id in node_by_id:
            raise ExtractionInputError(f"duplicate node id: {node_id}")
        node_by_id[node_id] = node

    normalized_edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw_edge in enumerate(edges):
        if not isinstance(raw_edge, Mapping):
            raise ExtractionInputError(f"edges[{index}] must be an object")
        edge = copy.deepcopy(dict(raw_edge))
        source, target, relation = edge.get("source"), edge.get("target"), edge.get("rel")
        if not all(isinstance(item, str) and item for item in (source, target, relation)):
            raise ExtractionInputError(
                f"edges[{index}] must have non-empty source, target and rel strings"
            )
        if source not in node_by_id or target not in node_by_id:
            raise ExtractionInputError(
                f"dangling edge {source!r} -[{relation}]-> {target!r}"
            )
        key = (source, relation, target)
        if key not in seen:
            seen.add(key)
            normalized_edges.append(edge)

    normalized_edges.sort(
        key=lambda item: (str(item["source"]), str(item["rel"]), str(item["target"]))
    )
    return {"node_by_id": node_by_id, "edges": normalized_edges}


def analyze_extraction_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Describe what the extraction can execute and what remains unmapped."""

    indexes = validate_extraction_graph(graph)
    node_by_id = indexes["node_by_id"]
    edges = indexes["edges"]
    node_counts = Counter(_node_type(node) or "unknown" for node in node_by_id.values())
    edge_counts = Counter(str(edge["rel"]) for edge in edges)
    extraction_mapping = graph.get("execution_mapping", {})
    if not isinstance(extraction_mapping, Mapping):
        extraction_mapping = {}

    noncanonical_claim_relations = []
    for edge in edges:
        if edge["rel"] not in {"SUPPORTS", "CONTRADICTS"}:
            continue
        if (
            _node_type(node_by_id[edge["source"]]) == "claim"
            and _node_type(node_by_id[edge["target"]]) == "claim"
        ):
            noncanonical_claim_relations.append(
                f'{edge["source"]}:{edge["rel"]}:{edge["target"]}'
            )

    missing = []
    checks = (
        (not node_counts.get("case_position"), "CASE_POSITIONS"),
        (not node_counts.get("support_route"), "SUPPORT_ROUTES"),
        (not node_counts.get("model_node"), "MODEL_NODES"),
        (not extraction_mapping.get("directed_model_edges"), "DIRECTED_MODEL_DEPENDENCIES"),
        (not extraction_mapping.get("formulas"), "EXECUTABLE_FORMULAS"),
        (not extraction_mapping.get("rule_switches"), "RULE_SWITCH_CONFIGS"),
        (
            not extraction_mapping.get("cyclic_component_solver_configs"),
            "NUMERICAL_SOLVER_CONFIGS",
        ),
        (not extraction_mapping.get("inverse_solver_configs"), "INVERSE_SOLVER_CONFIGS"),
        (not extraction_mapping.get("model_controls"), "MODEL_CONTROLS"),
        (True, "INSTITUTIONAL_ADMISSION_AND_BITEMPORAL_STATE"),
        (True, "VERSIONED_POLICY_BINDINGS"),
    )
    for condition, item in checks:
        if condition:
            missing.append(item)

    executable_financial_chain = not any(
        item in missing
        for item in (
            "DIRECTED_MODEL_DEPENDENCIES",
            "EXECUTABLE_FORMULAS",
            "RULE_SWITCH_CONFIGS",
            "NUMERICAL_SOLVER_CONFIGS",
            "INVERSE_SOLVER_CONFIGS",
            "MODEL_CONTROLS",
        )
    )
    return {
        "adapter_version": ADAPTER_VERSION,
        "source_graph_hash": _hash(
            {
                "nodes": sorted(node_by_id.values(), key=lambda item: str(item["id"])),
                "edges": edges,
                "execution_mapping": extraction_mapping,
            }
        ),
        "node_count": len(node_by_id),
        "edge_count": len(edges),
        "node_type_counts": dict(sorted(node_counts.items())),
        "edge_type_counts": dict(sorted(edge_counts.items())),
        "applicability": {
            "structural_validation": True,
            "live_case_compilation_with_manifest": True,
            "candidate_transition_on_mapped_scope": bool(
                node_counts.get("claim") and node_counts.get("case_position")
            ),
            "full_financial_recomputation": executable_financial_chain,
        },
        "missing_for_full_runtime": missing,
        "noncanonical_claim_to_claim_relations": sorted(noncanonical_claim_relations),
    }


def _validate_manifest(
    manifest: Mapping[str, Any],
    indexes: Mapping[str, Any],
    source_graph_hash: str,
) -> tuple[str, set[str]]:
    if not isinstance(manifest, Mapping):
        raise AdmissionInputError(
            "an explicit admission_manifest is required before runtime execution"
        )
    case_id = manifest.get("case_id")
    known_at = manifest.get("as_of_known_at")
    admitted = manifest.get("admitted_claim_ids")
    if not isinstance(case_id, str) or not case_id:
        raise AdmissionInputError("admission_manifest.case_id is required")
    if not isinstance(known_at, str) or not known_at:
        raise AdmissionInputError("admission_manifest.as_of_known_at is required")
    if not isinstance(admitted, list):
        raise AdmissionInputError("admission_manifest.admitted_claim_ids must be an array")
    declared_hash = manifest.get("source_graph_hash")
    if declared_hash is not None and declared_hash != source_graph_hash:
        raise AdmissionInputError("admission_manifest.source_graph_hash does not match input")

    node_by_id = indexes["node_by_id"]
    admitted_ids = {str(item) for item in admitted}
    unknown = sorted(
        item
        for item in admitted_ids
        if item not in node_by_id or _node_type(node_by_id[item]) != "claim"
    )
    if unknown:
        raise AdmissionInputError("unknown admitted claim ids: " + ", ".join(unknown))
    return case_id, admitted_ids


def _append_admission_event(
    manifest: Mapping[str, Any],
    case_id: str,
    admitted_ids: set[str],
    node_by_id: Mapping[str, Mapping[str, Any]],
    source_graph_hash: str,
) -> None:
    """Persist the institutional boundary once its manifest is valid.

    The manifest hash is the complete admission decision, including its claim
    set and cutoff. It is therefore the idempotency input, rather than a
    request-scoped or wall-clock identifier.
    """

    known_at = str(manifest["as_of_known_at"])
    manifest_hash = _hash(manifest)
    source_ids = sorted(
        {
            _text(
                node_by_id[claim_id].get(
                    "source_id", node_by_id[claim_id].get("source_doc")
                ),
                "UNSPECIFIED_SOURCE",
            )
            for claim_id in admitted_ids
        }
    )
    event: dict[str, Any] = {
        "event_id": ledger_store.compute_event_id(
            manifest.get("source_version_id", manifest.get("source_graph_hash")),
            manifest.get("extractor_version", manifest.get("manifest_version")),
            manifest_hash,
        ),
        "event": "CLAIM_ADMISSION",
        "effective_date": known_at[:10],
        "known_at": known_at,
        "source_ids": source_ids,
        "trigger_claim_ids": sorted(admitted_ids),
        "mutations": [
            {
                "operation": "ADD",
                "object_type": "CLAIM",
                "object_id": claim_id,
                "field": "admission_status",
                "to": "ADMITTED",
            }
            for claim_id in sorted(admitted_ids)
        ],
        "admission_manifest_hash": manifest_hash,
        "source_graph_hash": manifest.get("source_graph_hash", source_graph_hash),
    }
    actor = manifest.get("actor_id", manifest.get("actor"))
    if actor not in (None, ""):
        event["actor_id"] = actor

    # append_event raises on I/O failure; allowing that failure through keeps
    # runtime execution from claiming an admission that has no durable record.
    ledger_store.append_event(case_id, event)


def _coverage_limit(
    reason_code: str,
    scope_ids: Sequence[str],
    effect: str,
    *,
    discriminator: str = "",
) -> dict[str, Any]:
    scope = sorted(set(str(item) for item in scope_ids))
    return {
        "limit_id": _stable_id("ADAPTER-LIMIT", reason_code, discriminator, scope),
        "reason_code": reason_code,
        "scope_ids": scope,
        "effect": effect,
    }


def compile_extraction_to_runtime_inputs(
    graph: Mapping[str, Any],
    admission_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile extraction output into immutable runtime inputs.

    Claims not present in the admission manifest remain visible for coverage
    and route topology, but are marked ``validation_only`` and cannot count as
    institutional support.
    """

    indexes = validate_extraction_graph(graph)
    report = analyze_extraction_graph(graph)
    node_by_id = indexes["node_by_id"]
    edges = indexes["edges"]
    case_id, admitted_ids = _validate_manifest(
        admission_manifest, indexes, report["source_graph_hash"]
    )
    _append_admission_event(
        admission_manifest,
        case_id,
        admitted_ids,
        node_by_id,
        report["source_graph_hash"],
    )

    claims = []
    for node_id, node in sorted(node_by_id.items()):
        if _node_type(node) != "claim":
            continue
        claims.append(
            {
                "claim_id": node_id,
                "statement": _text(node.get("statement"), _text(node.get("label"), node_id)),
                "source_id": _text(node.get("source_id", node.get("source_doc")), "UNSPECIFIED_SOURCE"),
                "locator": _text(node.get("locator"), f"extraction:{node_id}"),
                "epistemic_class": _normalize_epistemic_class(node.get("epistemic_class")),
                "period": _text(node.get("period", node.get("as_of")), "UNSPECIFIED_PERIOD"),
                "perimeter": _text(node.get("perimeter"), "UNSPECIFIED_PERIMETER"),
                "definition_id": node.get("definition_id"),
                "value": copy.deepcopy(node.get("value")),
                "unit": node.get("unit") or None,
                "validation_only": node_id not in admitted_ids,
                "admission_status": "ADMITTED" if node_id in admitted_ids else "NOT_ADMITTED",
                "extraction_coverage_status": node.get("coverage_status"),
                "effective_date": node.get("effective_date", node.get("as_of")),
                "known_at": node.get("known_at"),
            }
        )

    positions = []
    for node_id, node in sorted(node_by_id.items()):
        if _node_type(node) not in {"case_position", "position"}:
            continue
        decision = str(node.get("decision_status") or "PENDING").upper()
        positions.append(
            {
                "position_id": node_id,
                "statement": _text(node.get("statement"), _text(node.get("label"), node_id)),
                "epistemic_status_at_ic": "UNEXAMINED",
                "decision_status_at_ic": decision,
                "decision_status": decision,
                "freshness_status_at_ic": "CURRENT",
                "outcome_status_at_ic": "NOT_TESTED",
                "model_binding_status": str(node.get("coverage_status") or "partial").upper(),
                "value": copy.deepcopy(node.get("value")),
                "unit": node.get("unit") or None,
                "period": _text(node.get("period"), "UNSPECIFIED_PERIOD"),
                "perimeter": _text(node.get("perimeter"), "UNSPECIFIED_PERIMETER"),
                "criticality": node.get("criticality"),
                "compiler_note": node.get("note"),
            }
        )

    model_nodes = []
    for node_id, node in sorted(node_by_id.items()):
        if _node_type(node) != "model_node":
            continue
        model_nodes.append(
            {
                "model_node_id": node_id,
                "name": _text(node.get("label"), node_id),
                "kind": _text(node.get("kind"), "unresolved"),
                "period": _text(node.get("period"), "UNSPECIFIED_PERIOD"),
                "perimeter": _text(node.get("perimeter"), "UNSPECIFIED_PERIMETER"),
                "value": copy.deepcopy(node.get("value")),
                "unit": node.get("unit") or None,
                "coverage_status": node.get("coverage_status"),
                "formula_ref": node.get("formula_ref"),
            }
        )

    claims_set = {item["claim_id"] for item in claims}
    positions_set = {item["position_id"] for item in positions}
    models_set = {item["model_node_id"] for item in model_nodes}
    routes_set = {
        node_id for node_id, node in node_by_id.items() if _node_type(node) == "support_route"
    }

    route_members: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"claims": set(), "positions": set(), "counter": set(), "targets": set()}
    )
    claim_position_edges = []
    position_dependencies = []
    position_model_bindings = []
    noncanonical_scopes: set[str] = set()

    for edge in edges:
        source, target, relation = str(edge["source"]), str(edge["target"]), str(edge["rel"])
        if relation == "SUPPORTS_ROUTE" and target in routes_set:
            if source in claims_set:
                route_members[target]["claims"].add(source)
            elif source in positions_set:
                route_members[target]["positions"].add(source)
            continue
        if relation == "CONTRADICTS_ROUTE" and target in routes_set and source in claims_set:
            route_members[target]["counter"].add(source)
            continue
        if relation == "ROUTE_FOR_POSITION" and source in routes_set and target in positions_set:
            route_members[source]["targets"].add(target)
            continue
        if relation in {"SUPPORTS", "CONTRADICTS"}:
            if source in claims_set and target in positions_set:
                claim_position_edges.append(
                    {
                        "edge_id": _stable_id("CPE", source, relation, target),
                        "claim_id": source,
                        "position_id": target,
                        "relation_type": relation,
                    }
                )
            elif source in claims_set and target in claims_set:
                noncanonical_scopes.update({source, target})
            elif source in positions_set and target in positions_set:
                position_dependencies.append(
                    {
                        "edge_id": _stable_id("PDE", source, relation, target),
                        "from_position_id": source,
                        "to_position_id": target,
                        "relation_type": relation,
                    }
                )
            continue
        if relation in CANONICAL_RELATIONS and source in positions_set and target in positions_set:
            position_dependencies.append(
                {
                    "edge_id": _stable_id("PDE", source, relation, target),
                    "from_position_id": source,
                    "to_position_id": target,
                    "relation_type": relation,
                }
            )
            continue
        if relation == "BINDS_TO" and source in positions_set and target in models_set:
            direction = str(edge.get("binding_direction") or "MONITOR_ONLY")
            if direction not in MODEL_DIRECTIONS:
                direction = "MONITOR_ONLY"
            position_model_bindings.append(
                {
                    "binding_id": _stable_id("PMB", source, target),
                    "position_id": source,
                    "model_node_id": target,
                    "binding_type": "DIRECT",
                    "direction": direction,
                    "status": "PARTIAL",
                }
            )

    support_routes = []
    malformed_route_scopes = []
    unconfirmed_route_ids = []
    for route_id in sorted(routes_set):
        node = node_by_id[route_id]
        targets = sorted(route_members[route_id]["targets"])
        if len(targets) != 1:
            malformed_route_scopes.append(route_id)
            continue
        logic = str(node.get("logic") or "INDEPENDENT").upper()
        if logic not in ROUTE_LOGICS:
            logic = "INDEPENDENT"
        if str(node.get("coverage_status") or "").lower() != "complete" or "default" in str(
            node.get("note") or ""
        ).lower():
            unconfirmed_route_ids.append(route_id)
        support_routes.append(
            {
                "route_id": route_id,
                "target_position_id": targets[0],
                "logic": logic,
                "member_claim_ids": sorted(route_members[route_id]["claims"]),
                "member_position_ids": sorted(route_members[route_id]["positions"]),
                "counter_claim_ids": sorted(route_members[route_id]["counter"]),
                "coverage_status": node.get("coverage_status"),
                "compiler_note": node.get("note"),
            }
        )

    artifacts = []
    for node_id, node in sorted(node_by_id.items()):
        if _node_type(node) != "artifact":
            continue
        artifacts.append(
            {
                "artifact_id": node_id,
                "name": _text(node.get("label"), node_id),
                "artifact_type": _text(node.get("artifact_type"), "UNRESOLVED"),
                "reference": node.get("reference"),
            }
        )

    coverage_limits = []
    extraction_mapping = graph.get("execution_mapping", {})
    if not isinstance(extraction_mapping, Mapping):
        extraction_mapping = {}
    for index, raw_limit in enumerate(extraction_mapping.get("coverage_limits", [])):
        if not isinstance(raw_limit, Mapping):
            continue
        scope_id = str(raw_limit.get("node_id") or f"EXTRACTION-LIMIT-{index:03d}")
        coverage_limits.append(
            _coverage_limit(
                _reason_code(raw_limit.get("reason")),
                [scope_id],
                _text(raw_limit.get("reason"), "Compiler mapping is incomplete."),
                discriminator=str(index),
            )
        )
    if not extraction_mapping.get("directed_model_edges"):
        coverage_limits.append(
            _coverage_limit(
                "MISSING_MODEL_DEPENDENCY",
                sorted(models_set),
                "No directed model dependencies were supplied; propagation stops at the mapped boundary.",
            )
        )
    if not extraction_mapping.get("formulas"):
        coverage_limits.append(
            _coverage_limit(
                "MISSING_EXECUTABLE_FORMULA",
                sorted(models_set),
                "Model values cannot be recomputed until workbook formulas are compiled.",
                discriminator="GLOBAL",
            )
        )
    missing_known_at = [item["claim_id"] for item in claims if not item.get("known_at")]
    if missing_known_at:
        coverage_limits.append(
            _coverage_limit(
                "MISSING_BITEMPORAL_ADMISSION",
                missing_known_at,
                "Claim-level known_at is absent; the manifest cutoff controls admission conservatively.",
            )
        )
    unadmitted = sorted(claims_set - admitted_ids)
    if unadmitted:
        coverage_limits.append(
            _coverage_limit(
                "CLAIM_NOT_IN_ADMISSION_MANIFEST",
                unadmitted,
                "These extracted claims remain validation-only and cannot support Current positions.",
            )
        )
    if noncanonical_scopes:
        coverage_limits.append(
            _coverage_limit(
                "NON_CANONICAL_CLAIM_TO_CLAIM_RELATION",
                sorted(noncanonical_scopes),
                "Claim-to-claim semantic edges are not traversed by the Live Case runtime.",
            )
        )
    if unconfirmed_route_ids:
        coverage_limits.append(
            _coverage_limit(
                "UNCONFIRMED_SUPPORT_ROUTE_LOGIC",
                unconfirmed_route_ids,
                "Compiler-default route logic requires confirmation before institutional reliance.",
            )
        )
    if malformed_route_scopes:
        coverage_limits.append(
            _coverage_limit(
                "MALFORMED_SUPPORT_ROUTE",
                malformed_route_scopes,
                "Each executable support route requires exactly one target position.",
            )
        )

    current_graph = {
        "schema_version": "1.1.0",
        "case_id": case_id,
        "canonical_as_of": str(admission_manifest["as_of_known_at"]),
        "claims": claims,
        "case_positions": positions,
        "model_nodes": model_nodes,
        "support_routes": support_routes,
        "claim_position_edges": sorted(claim_position_edges, key=lambda item: item["edge_id"]),
        "position_dependencies": sorted(position_dependencies, key=lambda item: item["edge_id"]),
        "position_model_bindings": sorted(
            position_model_bindings, key=lambda item: item["binding_id"]
        ),
        "artifacts": artifacts,
        "decision_snapshot": {},
        "coverage_gaps": copy.deepcopy(coverage_limits),
        "source_extraction_hash": report["source_graph_hash"],
        "admission_manifest_hash": _hash(admission_manifest),
    }

    binding_by_pair = {
        (item["position_id"], item["model_node_id"]): item
        for item in position_model_bindings
    }
    mapped_directions = []
    for raw_binding in extraction_mapping.get("position_model_directions", []):
        if not isinstance(raw_binding, Mapping):
            continue
        position_id = raw_binding.get("position_id", raw_binding.get("case_position_id"))
        model_id = raw_binding.get("model_node_id")
        if position_id not in positions_set or model_id not in models_set:
            continue
        direction = str(raw_binding.get("direction") or "MONITOR_ONLY")
        if direction not in MODEL_DIRECTIONS:
            direction = "MONITOR_ONLY"
        binding = binding_by_pair.get((str(position_id), str(model_id)))
        mapped_directions.append(
            {
                "binding_id": (
                    binding["binding_id"]
                    if binding
                    else _stable_id("PMB", position_id, model_id)
                ),
                "position_id": str(position_id),
                "model_node_id": str(model_id),
                "direction": direction,
                "coverage_status": raw_binding.get("coverage_status"),
            }
        )

    mapping_models_by_id = {
        str(item.get("id")): item
        for item in extraction_mapping.get("model_nodes", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    runtime_mapping_nodes = []
    for node in model_nodes:
        raw = mapping_models_by_id.get(node["model_node_id"], {})
        formula_present = bool(raw.get("formula") or raw.get("formula_ref"))
        runtime_mapping_nodes.append(
            {
                "model_node_id": node["model_node_id"],
                "unit": node.get("unit"),
                "period": node["period"],
                "perimeter": node["perimeter"],
                "computational_form": "DIRECT_FORMULA" if formula_present else "MONITOR_ONLY",
            }
        )

    def _safe_collection(name: str) -> list[Any]:
        value = extraction_mapping.get(name, [])
        return copy.deepcopy(value) if isinstance(value, list) else []

    execution_mapping = {
        "mapping_version": _text(
            extraction_mapping.get("mapping_version"), f"EXTRACTION-ADAPTER-{ADAPTER_VERSION}"
        ),
        "canonical_graph_hash": _hash(current_graph),
        "model_nodes": runtime_mapping_nodes,
        "directed_model_edges": _safe_collection("directed_model_edges"),
        "position_model_directions": sorted(
            mapped_directions, key=lambda item: item["binding_id"]
        ),
        "formulas": _safe_collection("formulas"),
        "rule_switches": _safe_collection("rule_switches"),
        "cyclic_component_solver_configs": _safe_collection(
            "cyclic_component_solver_configs"
        ),
        "inverse_solver_configs": _safe_collection("inverse_solver_configs"),
        "model_controls": _safe_collection("model_controls"),
        "coverage_limits": sorted(coverage_limits, key=lambda item: item["limit_id"]),
        "source_extraction_hash": report["source_graph_hash"],
        "admission_manifest_hash": _hash(admission_manifest),
    }

    adapter_report = copy.deepcopy(report)
    adapter_report.update(
        {
            "case_id": case_id,
            "admitted_claim_count": len(admitted_ids),
            "validation_only_claim_count": len(claims_set - admitted_ids),
            "compiled_support_route_count": len(support_routes),
            "compiled_binding_count": len(mapped_directions),
            "coverage_limit_count": len(coverage_limits),
            "current_graph_hash": _hash(current_graph),
            "execution_mapping_hash": _hash(execution_mapping),
        }
    )
    return {
        "current_graph": current_graph,
        "execution_mapping": execution_mapping,
        "adapter_report": adapter_report,
    }


def apply_extraction_transition(
    graph: Mapping[str, Any],
    event_batch: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    admission_manifest: Mapping[str, Any],
    materiality_policy: Mapping[str, Any],
    authority_policy: Mapping[str, Any],
    *,
    execution_mode: str = "INCREMENTAL_SCC",
) -> dict[str, Any]:
    """Compile an extraction graph and run the definitive transition engine."""

    compiled = compile_extraction_to_runtime_inputs(graph, admission_manifest)
    events = [event_batch] if isinstance(event_batch, Mapping) else list(event_batch)
    admitted_ids = set(str(item) for item in admission_manifest.get("admitted_claim_ids", []))
    referenced_ids = {
        str(item)
        for event in events
        for item in event.get("trigger_claim_ids", [])
    } | {
        str(mutation.get("object_id"))
        for event in events
        for mutation in event.get("mutations", [])
        if mutation.get("object_type") == "CLAIM"
    }
    not_admitted = sorted(referenced_ids - admitted_ids)
    if not_admitted:
        raise AdmissionInputError(
            "event references claims not admitted to the Live Case: " + ", ".join(not_admitted)
        )

    result = _run_transition(
        compiled["current_graph"],
        events,
        compiled["execution_mapping"],
        materiality_policy,
        authority_policy,
        execution_mode=execution_mode,
    )
    result["adapter_report"] = compiled["adapter_report"]
    return result
