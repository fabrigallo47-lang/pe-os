"""Deterministic, decomposable ranking of decision-critical case positions.

The kernel explicitly forbids an opaque attention score.  This module keeps
each ordering factor visible and uses a documented lexicographic comparison.
When an execution mapping cannot provide a numerical sensitivity, the output
states that limitation and reports structural propagation only.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable


_GATE_STATUSES = {
    "ACCEPTED_WITH_CONDITIONS",
    "BLOCKED",
    "CONTESTED",
    "PENDING",
}
_UNSETTLED_EPISTEMIC_STATUSES = {"CONTESTED", "STALE", "UNKNOWN", "WEAK"}
_BINDING_STATUSES = {
    "BINDING",
    "BLOCKED",
    "FAIL",
    "FAILED",
    "INFEASIBLE",
    "VIOLATED",
}


def _dicts(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item not in (None, "")}
    return set()


def _first_id(record: dict, names: Iterable[str]) -> str:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _model_adjacency(mapping: dict) -> tuple[dict[str, set[str]], set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for edge in _dicts(mapping.get("directed_model_edges")):
        source = _first_id(edge, ("from_model_node_id", "source_model_node_id", "source", "from"))
        target = _first_id(edge, ("to_model_node_id", "target_model_node_id", "target", "to"))
        if source and target:
            adjacency[source].add(target)
            nodes.update((source, target))

    # Some mappings expose formulas before they materialize explicit DRIVES
    # edges.  Formula precedents are equally deterministic structural links.
    for formula in _dicts(mapping.get("formulas")):
        output_id = _first_id(formula, ("output_id", "output_model_node_id"))
        if not output_id:
            continue
        nodes.add(output_id)
        for input_id in sorted(_strings(formula.get("input_ids"))):
            adjacency[input_id].add(output_id)
            nodes.add(input_id)

    for node in _dicts(mapping.get("model_nodes")):
        node_id = _first_id(node, ("model_node_id", "id"))
        if node_id:
            nodes.add(node_id)
    return adjacency, nodes


def _constraint_scope(record: dict) -> set[str]:
    scope: set[str] = set()
    for key in (
        "scope_ids",
        "downstream_scope",
        "input_ids",
        "activation_input_ids",
        "blocks_on_fail",
        "member_ids",
        "model_node_ids",
        "constraint_ids",
        "binding_constraint_ids",
    ):
        scope.update(_strings(record.get(key)))
    for key in ("variable_id", "model_node_id", "output_id", "target_model_node_id"):
        scope.update(_strings(record.get(key)))
    for constraint in _dicts(record.get("constraints")):
        scope.update(_constraint_scope(constraint))
    return scope


def _root_selection(mapping: dict, adjacency: dict[str, set[str]], nodes: set[str]) -> tuple[dict, list[dict]]:
    explicit_roots = set()
    for key in ("decision_root_ids", "decision_roots"):
        value = mapping.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    explicit_roots.add(_first_id(item, ("decision_root_id", "model_node_id", "id")))
                elif item not in (None, ""):
                    explicit_roots.add(str(item))
    for node in _dicts(mapping.get("model_nodes")):
        node_id = _first_id(node, ("model_node_id", "id"))
        tags = {tag.upper() for tag in _strings(node.get("tags"))}
        if node_id and (node.get("decision_root") is True or "DECISION_ROOT" in tags):
            explicit_roots.add(node_id)
    explicit_roots.discard("")

    if explicit_roots:
        return ({
            "method": "EXPLICIT_MAPPING_DECLARATION",
            "explicit": True,
            "root_ids": sorted(explicit_roots),
            "basis": "execution mapping decision_root_ids or model-node decision_root marker",
        }, [])

    formula_outputs = {
        _first_id(formula, ("output_id", "output_model_node_id"))
        for formula in _dicts(mapping.get("formulas"))
    }
    formula_outputs.discard("")
    terminal_formula_outputs = {
        node_id for node_id in formula_outputs if not adjacency.get(node_id)
    }
    control_boundaries = set()
    for control in _dicts(mapping.get("model_controls")):
        control_boundaries.update(_strings(control.get("blocks_on_fail")))
    solver_outputs = set()
    for solver in _dicts(mapping.get("inverse_solver_configs")):
        if solver.get("binding_constraint_output"):
            solver_outputs.update(_strings(solver.get("variable_id")))
            solver_outputs.update(_strings(solver.get("output_id")))
            solver_outputs.update(_strings(solver.get("binding_constraint_output_ids")))

    derived_roots = (terminal_formula_outputs | control_boundaries | solver_outputs) & nodes
    if not derived_roots:
        derived_roots = {node_id for node_id in nodes if not adjacency.get(node_id)}

    limit = {
        "limit_id": "DECISION_ROOTS_NOT_EXPLICIT",
        "reason_code": "STRUCTURAL_ROOT_FALLBACK",
        "effect": (
            "The execution mapping does not declare decision roots; reachability uses "
            "terminal formula outputs, control failure boundaries and binding solver outputs."
        ),
        "resolution": "Declare decision_root_ids in the execution mapping.",
    }
    return ({
        "method": "DERIVED_STRUCTURAL_BOUNDARIES",
        "explicit": False,
        "root_ids": sorted(derived_roots),
        "basis": (
            "terminal formula outputs, control blocks_on_fail targets and binding solver outputs"
        ),
    }, [limit])


def _reachable(start_ids: set[str], adjacency: dict[str, set[str]]) -> tuple[set[str], dict[str, int]]:
    reached = set(start_ids)
    distance = {node_id: 0 for node_id in start_ids}
    queue = deque(sorted(start_ids))
    while queue:
        source = queue.popleft()
        for target in sorted(adjacency.get(source, ())):
            if target in reached:
                continue
            reached.add(target)
            distance[target] = distance[source] + 1
            queue.append(target)
    return reached, distance


def _position_model_nodes(position_id: str, position: dict, current_graph: dict, mapping: dict) -> set[str]:
    model_node_ids = _strings(position.get("model_node_ids"))
    bindings = _dicts(current_graph.get("position_model_bindings"))
    bindings.extend(_dicts(current_graph.get("position_model_directions")))
    bindings.extend(_dicts(mapping.get("position_model_directions")))
    for binding in bindings:
        if str(binding.get("position_id") or "") != position_id:
            continue
        if str(binding.get("status") or "ACTIVE").upper() not in {"ACTIVE", "BOUND"}:
            continue
        direction = str(binding.get("direction") or binding.get("binding_type") or "POSITION_DRIVES_MODEL").upper()
        if direction not in {"POSITION_DRIVES_MODEL", "BIDIRECTIONAL"}:
            continue
        node_id = _first_id(binding, ("model_node_id", "target_model_node_id"))
        if node_id:
            model_node_ids.add(node_id)
    return model_node_ids


def _support_routes(position_id: str, position: dict, current_graph: dict) -> list[dict]:
    routes = _dicts(position.get("support_routes"))
    if not routes:
        routes = [
            route
            for route in _dicts(current_graph.get("support_routes"))
            if str(route.get("position_id") or route.get("target_position_id") or "") == position_id
        ]
    if routes:
        return routes

    claim_ids = {
        str(edge.get("claim_id") or edge.get("claim_stable_id"))
        for edge in _dicts(current_graph.get("claim_position_edges"))
        if str(edge.get("position_id") or edge.get("target_position_id") or "") == position_id
        and str(edge.get("relation_type") or "SUPPORTS").upper() == "SUPPORTS"
        and (edge.get("claim_id") or edge.get("claim_stable_id"))
    }
    fallback = []
    for claim in _dicts(current_graph.get("claims")):
        claim_id = _first_id(claim, ("claim_id", "stable_id", "id"))
        if claim_id not in claim_ids:
            continue
        source_ids = claim.get("source_ids") or [
            claim.get("source_version_id")
            or claim.get("source_id")
            or claim.get("source_doc")
        ]
        for source_id in source_ids:
            if source_id:
                fallback.append({"claim_id": claim_id, "source_id": source_id})
    return fallback


def _support_factor(routes: list[dict]) -> dict:
    identities: set[str] = set()
    unidentified = 0
    route_ids = set()
    for index, route in enumerate(routes):
        route_id = _first_id(route, ("route_id", "claim_id", "claim_stable_id")) or f"route:{index}"
        route_ids.add(route_id)
        source_version_id = _first_id(route, ("source_version_id",))
        source_id = _first_id(route, ("source_id", "source_doc_id"))
        source_label = _first_id(route, ("source", "source_doc"))
        if source_version_id:
            identities.add(f"source_version:{source_version_id}")
        elif source_id:
            identities.add(f"source:{source_id}")
        elif source_label:
            identities.add(f"source_label:{source_label}")
        else:
            unidentified += 1
            identities.add(f"unidentified_route:{route_id}")
    independent_count = len(identities)
    return {
        "raw_route_count": len(route_ids),
        "independent_route_count": independent_count,
        "independent_source_identities": sorted(identities),
        "unidentified_route_count": unidentified,
        "identity_method": "source version, then source ID, then exact source label; route fallback when absent",
        "fragile": independent_count <= 1,
    }


def _declared_constraints(mapping: dict) -> list[dict]:
    records = []
    for kind, key, id_names in (
        ("MODEL_CONTROL", "model_controls", ("control_id", "id")),
        ("INVERSE_SOLVER", "inverse_solver_configs", ("solver_id", "config_id", "id")),
        ("MAPPING_COVERAGE_LIMIT", "coverage_limits", ("limit_id", "reason_code", "id")),
    ):
        for index, record in enumerate(_dicts(mapping.get(key))):
            records.append({
                "constraint_id": _first_id(record, id_names) or f"{kind}:{index}",
                "kind": kind,
                "scope_ids": sorted(_constraint_scope(record)),
            })
    return records


def _runtime_constraint_records(transition_output: dict) -> list[dict]:
    records = []
    for collection in (
        "blocked_components",
        "coverage_limits",
        "human_stops",
        "inverse_solver_results",
        "numerical_solver_results",
    ):
        for index, record in enumerate(_dicts(transition_output.get(collection))):
            status = str(
                record.get("status")
                or record.get("outcome")
                or record.get("result")
                or record.get("reason_code")
                or ""
            ).upper()
            binding_ids = _strings(record.get("binding_constraint_ids"))
            is_binding = bool(binding_ids) or status in _BINDING_STATUSES
            if collection in {"blocked_components", "human_stops"}:
                is_binding = True
            records.append({
                "constraint_id": _first_id(
                    record,
                    ("constraint_id", "limit_id", "stop_id", "component_id", "solver_id", "id", "reason_code"),
                ) or f"{collection}:{index}",
                "kind": f"RUNTIME_{collection.upper()}",
                "scope_ids": sorted(_constraint_scope(record)),
                "binding_or_failed": is_binding,
                "status": status or None,
            })
            for binding_id in sorted(binding_ids):
                records.append({
                    "constraint_id": binding_id,
                    "kind": "RUNTIME_BINDING_CONSTRAINT",
                    "scope_ids": sorted(_constraint_scope(record)),
                    "binding_or_failed": True,
                    "status": "BINDING",
                })
    return records


def _constraint_factor(
    position_id: str,
    reached_nodes: set[str],
    current_graph: dict,
    declared: list[dict],
    runtime: list[dict],
) -> dict:
    constraint_scope = reached_nodes | {position_id}
    relevant_declared = [
        record for record in declared if constraint_scope & set(record["scope_ids"])
    ]
    relevant_runtime = [
        record
        for record in runtime
        if constraint_scope & set(record["scope_ids"])
    ]

    # CONDITIONS is a governed edge, not evidence support.  It is relevant to
    # the position even when no model node carries the condition.
    condition_ids = set()
    for edge in _dicts(current_graph.get("claim_position_edges")):
        target_id = str(edge.get("position_id") or edge.get("target_position_id") or "")
        if target_id == position_id and str(edge.get("relation_type") or "").upper() == "CONDITIONS":
            condition_ids.add(_first_id(edge, ("edge_id", "claim_id", "id")) or "CONDITIONS")
    for edge in _dicts(current_graph.get("condition_edges")):
        target_id = str(edge.get("target_position_id") or edge.get("position_id") or edge.get("target") or "")
        if target_id == position_id:
            condition_ids.add(_first_id(edge, ("edge_id", "condition_id", "id")) or "CONDITIONS")

    declared_ids = {record["constraint_id"] for record in relevant_declared} | condition_ids
    binding_ids = {
        record["constraint_id"]
        for record in relevant_runtime
        if record.get("binding_or_failed")
    }
    if binding_ids:
        state = "BINDING_OR_FAILED"
    elif declared_ids:
        state = "DECLARED_NOT_EVALUATED"
    else:
        state = "NONE"
    return {
        "state": state,
        "binding_or_failed_count": len(binding_ids),
        "binding_or_failed_ids": sorted(binding_ids),
        "declared_count": len(declared_ids),
        "declared_ids": sorted(declared_ids),
        "runtime_record_count": len(relevant_runtime),
    }


def rank_decision_criticality(
    current_graph: dict,
    execution_mapping: dict,
    transition_output: dict | None = None,
) -> dict:
    """Return a deterministic, fully decomposed position ranking."""
    graph = current_graph if isinstance(current_graph, dict) else {}
    mapping = execution_mapping if isinstance(execution_mapping, dict) else {}
    transition = transition_output if isinstance(transition_output, dict) else {}
    adjacency, model_nodes = _model_adjacency(mapping)
    root_selection, limits = _root_selection(mapping, adjacency, model_nodes)
    root_ids = set(root_selection["root_ids"])
    declared_constraints = _declared_constraints(mapping)
    runtime_constraints = _runtime_constraint_records(transition)

    ranking = []
    positions = graph.get("case_positions", graph.get("positions", []))
    for position in _dicts(positions):
        if str(position.get("position_kind") or "").upper() == "COVERAGE_CONDITION":
            continue
        position_id = _first_id(position, ("position_id", "id"))
        if not position_id:
            continue
        bound_nodes = _position_model_nodes(position_id, position, graph, mapping)
        reached_nodes, distance = _reachable(bound_nodes, adjacency)
        directly_linked_roots = set()
        for key in ("decision_root_id", "decision_root_ids", "decision_root_override"):
            directly_linked_roots.update(_strings(position.get(key)))
        directly_linked_roots &= root_ids
        model_reached_roots = reached_nodes & root_ids
        reached_roots = sorted(directly_linked_roots | model_reached_roots)
        minimum_hops = (
            0
            if directly_linked_roots
            else min((distance[root_id] for root_id in model_reached_roots), default=None)
        )
        support = _support_factor(_support_routes(position_id, position, graph))
        constraints = _constraint_factor(
            position_id,
            reached_nodes,
            graph,
            declared_constraints,
            runtime_constraints,
        )
        decision_status = str(
            position.get("decision_status")
            or position.get("decision_status_at_ic")
            or "PENDING"
        ).upper()
        epistemic_status = str(
            position.get("epistemic_status")
            or position.get("epistemic_status_at_ic")
            or "UNKNOWN"
        ).upper()
        actionable_reasons = []
        if decision_status in _GATE_STATUSES:
            actionable_reasons.append(f"decision_status={decision_status}")
        if epistemic_status in _UNSETTLED_EPISTEMIC_STATUSES:
            actionable_reasons.append(f"epistemic_status={epistemic_status}")
        if constraints["binding_or_failed_count"]:
            actionable_reasons.append("binding_or_failed_constraint")
        if support["fragile"] and reached_roots:
            actionable_reasons.append("at_most_one_independent_support_route")

        factors = {
            "decision_root_reachability": {
                "reachable": bool(reached_roots),
                "reachable_root_count": len(reached_roots),
                "reachable_root_ids": reached_roots,
                "directly_linked_root_ids": sorted(directly_linked_roots),
                "mapping_reached_root_ids": sorted(model_reached_roots),
                "minimum_hops_to_root": minimum_hops,
                "root_selection_method": root_selection["method"],
            },
            "economic_sensitivity_from_mapping": {
                "method": "STRUCTURAL_PROPAGATION_ONLY",
                "numeric_sensitivity_available": False,
                "bound_model_node_ids": sorted(bound_nodes),
                "reachable_model_node_count": len(reached_nodes),
                "reachable_model_node_ids": sorted(reached_nodes),
                "basis": (
                    "Count of mapped downstream model nodes; no derivative, elasticity or monetary delta is declared."
                ),
            },
            "independent_support_routes": support,
            "marginal_constraints": constraints,
        }
        ranking.append({
            "position_id": position_id,
            "id": position_id,
            "label": position.get("label") or position.get("metric") or position_id,
            "statement": position.get("statement") or "",
            "decision_status": decision_status,
            "epistemic_status": epistemic_status,
            "actionable": bool(actionable_reasons),
            "actionable_reasons": actionable_reasons,
            "factors": factors,
            "ordering_key": {
                "decision_root_reachable": bool(reached_roots),
                "reachable_root_count": len(reached_roots),
                "reachable_model_node_count": len(reached_nodes),
                "binding_or_failed_constraint_count": constraints["binding_or_failed_count"],
                "declared_constraint_count": constraints["declared_count"],
                "independent_support_route_count": support["independent_route_count"],
                "position_id": position_id,
            },
        })

    ranking.sort(key=lambda item: (
        not item["ordering_key"]["decision_root_reachable"],
        -item["ordering_key"]["reachable_root_count"],
        -item["ordering_key"]["reachable_model_node_count"],
        -item["ordering_key"]["binding_or_failed_constraint_count"],
        -item["ordering_key"]["declared_constraint_count"],
        item["ordering_key"]["independent_support_route_count"],
        item["position_id"],
    ))
    for rank, item in enumerate(ranking, start=1):
        item["rank"] = rank
        key = item["ordering_key"]
        item["explanation"] = (
            f"decision_root_reachable={str(key['decision_root_reachable']).lower()}; "
            f"reachable_roots={key['reachable_root_count']}; "
            f"mapped_downstream_nodes={key['reachable_model_node_count']}; "
            f"binding_or_failed_constraints={key['binding_or_failed_constraint_count']}; "
            f"declared_constraints={key['declared_constraint_count']}; "
            f"independent_support_routes={key['independent_support_route_count']}"
        )

    return {
        "schema_version": "decision-criticality/1.0",
        "policy": {
            "method": "DETERMINISTIC_LEXICOGRAPHIC",
            "aggregation": "NONE",
            "factors_exposed": True,
            "ordering": [
                "decision root reachable descending",
                "reachable decision root count descending",
                "reachable mapped model node count descending",
                "binding or failed marginal constraint count descending",
                "declared marginal constraint count descending",
                "independent support route count ascending",
                "position_id ascending",
            ],
            "root_selection": root_selection,
            "sensitivity_limit": (
                "Structural mapping propagation is reported because the mapping declares no numerical sensitivity."
            ),
        },
        "ranking": ranking,
        "coverage_limits": limits,
    }


def next_position_work(report: dict) -> dict | None:
    """Translate the highest actionable root-linked position into closure work."""
    candidates = [
        item
        for item in _dicts(report.get("ranking"))
        if item.get("actionable")
        and item.get("factors", {}).get("decision_root_reachability", {}).get("reachable")
    ]
    if not candidates:
        return None
    item = candidates[0]
    constraints = item["factors"]["marginal_constraints"]
    support = item["factors"]["independent_support_routes"]
    if constraints["binding_or_failed_count"]:
        closure = f"Resolve constraints on {item['label']}: {', '.join(constraints['binding_or_failed_ids'])}"
    elif constraints["declared_count"]:
        closure = f"Evaluate declared constraints on {item['label']}"
    elif support["fragile"]:
        closure = f"Add an independent support route for {item['label']}"
    else:
        closure = f"Resolve the unsettled position: {item['label']}"
    return {
        "id": f"NBW-{item['position_id']}",
        "question_id": None,
        "position_id": item["position_id"],
        "label": closure,
        "reason": f"Ranked first by the declared factor ordering: {item['explanation']}.",
        "owner": "Unassigned",
        "duration": "Not estimated",
        "unlocks": item["factors"]["decision_root_reachability"]["reachable_root_ids"],
        "ranking_basis": item["ordering_key"],
        "factors": item["factors"],
    }
