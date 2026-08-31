#!/usr/bin/env python3
"""PANTA State Transition Engine runtime.

This module consumes a conforming Live Investment Case graph, not a raw
extraction database.  The implemented runtime blocks cover:

* deterministic event normalization and simultaneous-batch merge;
* immutable Candidate overlay construction;
* semantic applicability checks;
* conservative graph closure and deterministic SCC ordering;
* three-valued support-route evaluation with OR between routes;
* invalidation of circular support as independent evidence;
* deterministic Decimal formula recomputation;
* contradiction, materiality and governance routing;
* cumulative materiality and first-class rule switching;
* numerical SCC and inverse-solver outcomes;
* incremental/global conformance comparison;
* append-only event records and deterministic replay hashes;
* Candidate / Current / Approved separation in the transition output.

Every executable stage is driven by versioned mapping or policy input. Missing
deal-specific mapping remains an explicit coverage limit instead of being guessed.
"""

from __future__ import annotations

import ast
import copy
import fnmatch
import hashlib
import heapq
import json
import re
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


ENGINE_VERSION = "0.4.0-conformance"
OUTPUT_SCHEMA_VERSION = "transition-output-1.0"
RUNTIME_STATE_VERSION = "runtime-state-1.0"

CANONICAL_RELATIONS = frozenset(
    {"SUPPORTS", "CONTRADICTS", "DERIVES_FROM", "DRIVES", "CONDITIONS"}
)
MUTATION_OPERATIONS = frozenset(
    {"ADD", "OBSERVE", "CORRECT", "SUPERSEDE", "RETRACT"}
)
MUTATION_OBJECT_TYPES = frozenset(
    {"CLAIM", "POSITION", "MODEL_NODE", "SUPPORT_ROUTE", "ARTIFACT"}
)

# Fields only a recorded human decision may write. The engine can compute how
# well supported a position is (epistemic_status); whether the firm has decided
# is not a computation and must never be reached by inference.
HUMAN_ONLY_FIELDS = frozenset({"decision_status"})

# Event types that carry a human decision. An event outside this set may compute
# anything it likes, but it cannot move a position's decision status.
HUMAN_DECISION_EVENTS = frozenset(
    {"IC_DECISION", "AUTHORITY_DECISION", "PROFESSIONAL_ADOPTION", "HUMAN_DECISION"}
)


def _is_recorded_human_decision(event: Mapping[str, Any]) -> bool:
    """True when this event is a decision a named person made and signed.

    Both halves are required. An event typed as a decision but carrying no actor
    is a decision nobody made, which is exactly the shape an automated write
    would take if it tried to pass itself off as one.
    """
    if str(event.get("event", "")).upper() not in HUMAN_DECISION_EVENTS:
        return False
    return bool(event.get("actor_id") or event.get("decided_by"))


class StateInputError(ValueError):
    """Raised when the Current Live Investment Case is structurally invalid."""


class EventInputError(ValueError):
    """Raised when an event envelope is structurally invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decimal_or_original(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    try:
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        if isinstance(value, str):
            return Decimal(value.strip())
    except (InvalidOperation, ValueError):
        pass
    return value


def _equivalent(left: Any, right: Any) -> bool:
    normalized_left = _decimal_or_original(left)
    normalized_right = _decimal_or_original(right)
    if isinstance(normalized_left, Decimal) and isinstance(normalized_right, Decimal):
        return normalized_left == normalized_right
    if isinstance(normalized_left, Decimal) or isinstance(normalized_right, Decimal):
        return False
    return _canonical_json(normalized_left) == _canonical_json(normalized_right)


def _normalize_unit(unit: Any) -> Any:
    if not isinstance(unit, str):
        return unit
    aliases = {
        "$m": "$mm",
        "$mn": "$mm",
        "usd_m": "$mm",
        "decimal ratio": "decimal_ratio",
    }
    lowered = unit.strip().lower()
    return aliases.get(lowered, unit.strip())


def _validate_iso(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise EventInputError(f"{field} must be a non-empty ISO string")
    try:
        if field == "effective_date":
            date.fromisoformat(value)
        else:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventInputError(f"invalid {field}: {value!r}") from exc


def _event_batch_key(event: Mapping[str, Any]) -> tuple[str, str]:
    if event.get("batch_id"):
        return ("BATCH", str(event["batch_id"]))
    return ("KNOWN_AT", str(event["known_at"]))


def _mutation_sort_key(mutation: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(mutation.get("object_type", "")),
        str(mutation.get("object_id", "")),
        str(mutation.get("field", "__lifecycle__")),
        str(mutation.get("operation", "")),
        _canonical_json(mutation.get("to")),
    )


def normalize_event_batch(event_batch: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and canonically order a sequence of event envelopes."""

    if not isinstance(event_batch, Sequence) or isinstance(event_batch, (str, bytes)):
        raise EventInputError("event_batch must be an array of event objects")

    required = (
        "event_id",
        "event",
        "effective_date",
        "known_at",
        "source_ids",
        "trigger_claim_ids",
        "mutations",
    )
    normalized: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    batch_known_at: dict[tuple[str, str], str] = {}

    for event_index, raw_event in enumerate(event_batch):
        if not isinstance(raw_event, Mapping):
            raise EventInputError(f"event_batch[{event_index}] must be an object")
        missing = [field for field in required if field not in raw_event]
        if missing:
            raise EventInputError(
                f"event_batch[{event_index}] missing required fields: {', '.join(missing)}"
            )
        event_id = raw_event["event_id"]
        if not isinstance(event_id, str) or not event_id:
            raise EventInputError("event_id must be a non-empty string")
        if event_id in event_ids:
            raise EventInputError(f"duplicate event_id in input: {event_id}")
        event_ids.add(event_id)
        if not isinstance(raw_event["event"], str) or not raw_event["event"]:
            raise EventInputError(f"event {event_id} has an empty event label")
        _validate_iso(raw_event["effective_date"], "effective_date")
        _validate_iso(raw_event["known_at"], "known_at")

        for field in ("source_ids", "trigger_claim_ids", "mutations"):
            if not isinstance(raw_event[field], list):
                raise EventInputError(f"event {event_id}: {field} must be an array")

        event = copy.deepcopy(dict(raw_event))
        event["source_ids"] = sorted(set(str(item) for item in event["source_ids"]))
        event["trigger_claim_ids"] = sorted(
            set(str(item) for item in event["trigger_claim_ids"])
        )

        normalized_mutations: list[dict[str, Any]] = []
        for mutation_index, raw_mutation in enumerate(event["mutations"]):
            if not isinstance(raw_mutation, Mapping):
                raise EventInputError(
                    f"event {event_id}: mutations[{mutation_index}] must be an object"
                )
            missing_mutation = [
                field
                for field in ("operation", "object_type", "object_id")
                if field not in raw_mutation
            ]
            if missing_mutation:
                raise EventInputError(
                    f"event {event_id}: mutations[{mutation_index}] missing "
                    + ", ".join(missing_mutation)
                )
            mutation = copy.deepcopy(dict(raw_mutation))
            if mutation["operation"] not in MUTATION_OPERATIONS:
                raise EventInputError(
                    f"event {event_id}: unsupported operation {mutation['operation']!r}"
                )
            if mutation["object_type"] not in MUTATION_OBJECT_TYPES:
                raise EventInputError(
                    f"event {event_id}: unsupported object_type {mutation['object_type']!r}"
                )
            if not isinstance(mutation["object_id"], str) or not mutation["object_id"]:
                raise EventInputError(
                    f"event {event_id}: mutation object_id must be a non-empty string"
                )
            if "unit" in mutation:
                mutation["unit"] = _normalize_unit(mutation["unit"])
            normalized_mutations.append(mutation)
        event["mutations"] = sorted(normalized_mutations, key=_mutation_sort_key)

        batch_key = _event_batch_key(event)
        previous_known_at = batch_known_at.get(batch_key)
        if previous_known_at is not None and previous_known_at != event["known_at"]:
            raise EventInputError(
                f"explicit batch {batch_key[1]!r} contains different known_at values"
            )
        batch_known_at[batch_key] = event["known_at"]
        normalized.append(event)

    normalized.sort(
        key=lambda event: (
            event["known_at"],
            _event_batch_key(event),
            event["event_id"],
        )
    )
    return normalized


def _graph_state_id(graph: Mapping[str, Any]) -> str:
    as_of = graph.get("canonical_as_of", "unknown")
    return f"STATE-{graph.get('case_id', 'CASE')}-{as_of}"


def _initial_k_t(graph: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(node["model_node_id"]): copy.deepcopy(node.get("value"))
        for node in graph.get("model_nodes", [])
        if isinstance(node, Mapping) and node.get("model_node_id")
    }


def build_runtime_state(
    current_graph: Mapping[str, Any],
    *,
    state_id: str | None = None,
    approved_snapshot: Mapping[str, Any] | None = None,
    history: Sequence[Mapping[str, Any]] | None = None,
    k_t: Mapping[str, Any] | None = None,
    runtime_flags: Mapping[str, Mapping[str, Any]] | None = None,
    pending_settlement: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a conforming Canonical Case graph in the runtime state envelope."""

    _validate_case_graph(current_graph)
    state = {
        "schema_version": RUNTIME_STATE_VERSION,
        "state_id": state_id or _graph_state_id(current_graph),
        "case_id": current_graph["case_id"],
        "current_graph": copy.deepcopy(dict(current_graph)),
        "approved_snapshot": copy.deepcopy(
            dict(approved_snapshot or current_graph.get("decision_snapshot", {}))
        ),
        "history": copy.deepcopy(list(history or [])),
        "K_t": copy.deepcopy(dict(k_t or _initial_k_t(current_graph))),
    }
    # Lifecycle flags are part of replay state only when there is something to
    # preserve.  Omitting the empty map keeps historical replay hashes stable.
    if runtime_flags:
        state["runtime_flags"] = copy.deepcopy(dict(runtime_flags))
    if pending_settlement:
        state["pending_settlement"] = copy.deepcopy(dict(pending_settlement))
    return state


def _coerce_runtime_state(prior_state: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(prior_state, Mapping):
        raise StateInputError("prior_state must be an object")
    if "current_graph" in prior_state:
        required = {"state_id", "case_id", "current_graph", "approved_snapshot", "history", "K_t"}
        missing = sorted(required - set(prior_state))
        if missing:
            raise StateInputError("runtime state missing: " + ", ".join(missing))
        _validate_case_graph(prior_state["current_graph"])
        return copy.deepcopy(dict(prior_state))
    return build_runtime_state(prior_state)


def _validate_unique_objects(
    items: Any, id_field: str, collection_name: str
) -> dict[str, MutableMapping[str, Any]]:
    if not isinstance(items, list):
        raise StateInputError(f"{collection_name} must be an array")
    result: dict[str, MutableMapping[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, MutableMapping):
            raise StateInputError(f"{collection_name}[{index}] must be an object")
        object_id = item.get(id_field)
        if not isinstance(object_id, str) or not object_id:
            raise StateInputError(f"{collection_name}[{index}].{id_field} is required")
        if object_id in result:
            raise StateInputError(f"duplicate {collection_name} id: {object_id}")
        result[object_id] = item
    return result


def _validate_case_graph(graph: Mapping[str, Any]) -> None:
    if not isinstance(graph, Mapping):
        raise StateInputError("current_graph must be an object")
    if not isinstance(graph.get("case_id"), str) or not graph.get("case_id"):
        raise StateInputError("current_graph.case_id is required")
    for collection, id_field in (
        ("claims", "claim_id"),
        ("case_positions", "position_id"),
        ("model_nodes", "model_node_id"),
        ("support_routes", "route_id"),
    ):
        _validate_unique_objects(graph.get(collection, []), id_field, collection)


def _object_registry(graph: MutableMapping[str, Any]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    specs = (
        ("claims", "claim_id", "CLAIM"),
        ("case_positions", "position_id", "POSITION"),
        ("model_nodes", "model_node_id", "MODEL_NODE"),
        ("support_routes", "route_id", "SUPPORT_ROUTE"),
        ("artifacts", "artifact_id", "ARTIFACT"),
    )
    for collection, id_field, object_type in specs:
        items = graph.get(collection, [])
        if items is None:
            continue
        if not isinstance(items, list):
            raise StateInputError(f"{collection} must be an array")
        for item in items:
            if not isinstance(item, MutableMapping):
                raise StateInputError(f"{collection} items must be objects")
            object_id = item.get(id_field)
            if not object_id:
                continue
            if object_id in registry:
                raise StateInputError(f"object id reused across collections: {object_id}")
            registry[object_id] = {
                "object_type": object_type,
                "collection": collection,
                "id_field": id_field,
                "object": item,
            }
    return registry


def _add_adjacency_edge(
    adjacency: dict[str, list[tuple[str, str, str]]],
    registry: Mapping[str, Any],
    source: Any,
    target: Any,
    relation: str,
    edge_id: str,
) -> None:
    if source in registry and target in registry:
        adjacency[str(source)].append((str(target), relation, edge_id))


def _build_execution_adjacency(
    graph: MutableMapping[str, Any], execution_mapping: Mapping[str, Any]
) -> dict[str, list[tuple[str, str, str]]]:
    registry = _object_registry(graph)
    adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for edge in graph.get("claim_position_edges", []):
        relation = edge.get("relation_type")
        if relation in {"SUPPORTS", "CONTRADICTS"}:
            _add_adjacency_edge(
                adjacency,
                registry,
                edge.get("claim_id"),
                edge.get("position_id"),
                str(relation),
                str(edge.get("edge_id", "CLAIM_POSITION_EDGE")),
            )

    for edge in graph.get("position_dependencies", []):
        relation = edge.get("relation_type")
        if relation in CANONICAL_RELATIONS:
            _add_adjacency_edge(
                adjacency,
                registry,
                edge.get("from_position_id"),
                edge.get("to_position_id"),
                str(relation),
                str(edge.get("edge_id", "POSITION_DEPENDENCY")),
            )

    for route in graph.get("support_routes", []):
        route_id = route.get("route_id")
        target = route.get("target_position_id")
        for member_id in sorted(
            set(route.get("member_claim_ids", []))
            | set(route.get("member_position_ids", []))
        ):
            _add_adjacency_edge(
                adjacency,
                registry,
                member_id,
                route_id,
                "SUPPORT_ROUTE_MEMBER",
                f"{route_id}:MEMBER:{member_id}",
            )
        _add_adjacency_edge(
            adjacency,
            registry,
            route_id,
            target,
            "ROUTE_FOR_POSITION",
            f"{route_id}:TARGET:{target}",
        )

    for formula in execution_mapping.get("formulas", []):
        formula_id = str(formula.get("formula_id", "FORMULA"))
        output_id = formula.get("output_id")
        for input_id in formula.get("input_ids", []):
            _add_adjacency_edge(
                adjacency,
                registry,
                input_id,
                output_id,
                "FORMULA_INPUT",
                f"{formula_id}:{input_id}:{output_id}",
            )

    for edge in execution_mapping.get("directed_model_edges", []):
        relation = str(edge.get("relation_type") or "MODEL_DEPENDENCY")
        _add_adjacency_edge(
            adjacency,
            registry,
            edge.get("from_model_node_id"),
            edge.get("to_model_node_id"),
            relation,
            str(edge.get("edge_id", "MODEL_DEPENDENCY")),
        )

    for binding in execution_mapping.get("position_model_directions", []):
        position_id = binding.get("position_id")
        model_node_id = binding.get("model_node_id")
        direction = binding.get("direction")
        binding_id = str(binding.get("binding_id", "POSITION_MODEL_BINDING"))
        if direction == "POSITION_DRIVES_MODEL":
            source, target = position_id, model_node_id
        elif direction in {"MODEL_DERIVES_POSITION", "MODEL_VALIDATES_POSITION"}:
            source, target = model_node_id, position_id
        else:
            continue
        _add_adjacency_edge(
            adjacency,
            registry,
            source,
            target,
            str(direction),
            binding_id,
        )

    for rule_switch in execution_mapping.get("rule_switches", []):
        rule_switch_id = str(rule_switch.get("rule_switch_id", "RULE_SWITCH"))
        for selector_id in rule_switch.get("selector_input_ids", []):
            for dependent_id in rule_switch.get("dependent_ids", []):
                _add_adjacency_edge(
                    adjacency,
                    registry,
                    selector_id,
                    dependent_id,
                    "RULE_SWITCH_SELECTOR",
                    f"{rule_switch_id}:{selector_id}:{dependent_id}",
                )

    for config in execution_mapping.get("cyclic_component_solver_configs", []):
        component_id = str(config.get("component_id", "NUMERICAL-SCC"))
        for activation_id in config.get("activation_input_ids", []):
            for member_id in config.get("member_ids", []):
                _add_adjacency_edge(
                    adjacency,
                    registry,
                    activation_id,
                    member_id,
                    "SOLVER_ACTIVATION",
                    f"{component_id}:{activation_id}:{member_id}",
                )

    for config in execution_mapping.get("inverse_solver_configs", []):
        solver_id = str(config.get("solver_id", "INVERSE-SOLVER"))
        objective = config.get("objective", {})
        decision_ids = [str(item) for item in config.get("decision_variable_ids", [])]
        variable_id = objective.get("variable_id") or (decision_ids[0] if decision_ids else None)
        for activation_id in config.get("activation_input_ids", []):
            _add_adjacency_edge(
                adjacency,
                registry,
                activation_id,
                variable_id,
                "INVERSE_SOLVER_ACTIVATION",
                f"{solver_id}:{activation_id}:{variable_id}",
            )
        for dependent_id in config.get("dependent_ids", []):
            _add_adjacency_edge(
                adjacency,
                registry,
                variable_id,
                dependent_id,
                "INVERSE_SOLVER_DEPENDENT",
                f"{solver_id}:{variable_id}:{dependent_id}",
            )

    for source in adjacency:
        adjacency[source] = sorted(
            set(adjacency[source]), key=lambda item: (item[0], item[1], item[2])
        )
    return adjacency


def compute_affected_set(
    current_graph: Mapping[str, Any],
    trigger_ids: Iterable[str],
    execution_mapping: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the complete forward least fixed point from admitted triggers."""

    graph = copy.deepcopy(dict(current_graph))
    _validate_case_graph(graph)
    registry = _object_registry(graph)
    mapping = execution_mapping or {}
    adjacency = _build_execution_adjacency(graph, mapping)
    seeds = sorted(set(str(item) for item in trigger_ids))
    missing = [object_id for object_id in seeds if object_id not in registry]
    if missing:
        raise EventInputError("unknown trigger object ids: " + ", ".join(missing))

    visited = set(seeds)
    reached_via: dict[str, set[str]] = defaultdict(set)
    queue: deque[str] = deque(seeds)
    while queue:
        source = queue.popleft()
        for target, relation, edge_id in adjacency.get(source, []):
            reached_via[target].add(f"{edge_id}:{relation}")
            if target not in visited:
                visited.add(target)
                queue.append(target)

    affected_set = []
    for object_id in sorted(
        visited,
        key=lambda item: (registry[item]["object_type"], item),
    ):
        affected_set.append(
            {
                "object_type": registry[object_id]["object_type"],
                "object_id": object_id,
                "seed": object_id in seeds,
                "reached_via": sorted(reached_via.get(object_id, set())),
            }
        )
    return {
        "affected_set": affected_set,
        "visited_ids": sorted(visited),
        "adjacency": adjacency,
        "registry": registry,
    }


def _strongly_connected_components(
    member_ids: Iterable[str],
    adjacency: Mapping[str, Sequence[tuple[str, str, str]]],
) -> list[list[str]]:
    allowed = set(member_ids)
    next_index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node_id: str) -> None:
        nonlocal next_index
        indexes[node_id] = next_index
        lowlinks[node_id] = next_index
        next_index += 1
        stack.append(node_id)
        on_stack.add(node_id)

        for target, _relation, _edge_id in adjacency.get(node_id, []):
            if target not in allowed:
                continue
            if target not in indexes:
                visit(target)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target])
            elif target in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indexes[target])

        if lowlinks[node_id] == indexes[node_id]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node_id:
                    break
            components.append(sorted(component))

    for node_id in sorted(allowed):
        if node_id not in indexes:
            visit(node_id)
    return components


def _ordered_components(
    affected_ids: Iterable[str],
    adjacency: Mapping[str, Sequence[tuple[str, str, str]]],
    registry: Mapping[str, Any],
    settled_ids: set[str],
    blocked_ids: set[str],
) -> list[dict[str, Any]]:
    affected = sorted(set(affected_ids))
    components = _strongly_connected_components(affected, adjacency)
    component_by_member = {
        member: component_index
        for component_index, members in enumerate(components)
        for member in members
    }
    successors: dict[int, set[int]] = defaultdict(set)
    indegree = {index: 0 for index in range(len(components))}
    internal_relations: dict[int, set[str]] = defaultdict(set)
    self_loops: set[int] = set()

    for source in affected:
        for target, relation, _edge_id in adjacency.get(source, []):
            if target not in component_by_member:
                continue
            source_component = component_by_member[source]
            target_component = component_by_member[target]
            if source_component == target_component:
                internal_relations[source_component].add(relation)
                if source == target:
                    self_loops.add(source_component)
            elif target_component not in successors[source_component]:
                successors[source_component].add(target_component)
                indegree[target_component] += 1

    ready = sorted(
        (index for index, degree in indegree.items() if degree == 0),
        key=lambda index: components[index],
    )
    ordered_indexes: list[int] = []
    while ready:
        current = ready.pop(0)
        ordered_indexes.append(current)
        for successor in sorted(successors.get(current, set()), key=lambda i: components[i]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
                ready.sort(key=lambda index: components[index])

    ordered: list[dict[str, Any]] = []
    for order, component_index in enumerate(ordered_indexes):
        members = components[component_index]
        cyclic = len(members) > 1 or component_index in self_loops
        relations = internal_relations.get(component_index, set())
        member_types = {registry[member]["object_type"] for member in members}
        if cyclic and relations and relations <= {"SUPPORTS", "SUPPORT_ROUTE_MEMBER", "ROUTE_FOR_POSITION"}:
            component_type = "CIRCULAR_SUPPORT_SCC"
            if set(members) <= blocked_ids:
                result = "BLOCKED"
            elif set(members) <= settled_ids:
                result = "SETTLED"
            else:
                result = "PROVISIONAL"
            reason_codes = ["CIRCULAR_SUPPORT_NOT_INDEPENDENT"]
        elif cyclic and member_types == {"MODEL_NODE"}:
            component_type = "NUMERICAL_SCC"
            result = "PROVISIONAL"
            reason_codes = ["SOLVER_STAGE_PENDING"]
        elif cyclic:
            component_type = "QUALITATIVE_SCC"
            result = "PROVISIONAL"
            reason_codes = ["COMPONENT_EVALUATION_PENDING"]
        elif set(members) & blocked_ids:
            component_type = "ACYCLIC"
            result = "BLOCKED"
            reason_codes = ["UPSTREAM_INPUT_BLOCKED"]
        elif set(members) <= settled_ids:
            component_type = "ACYCLIC"
            result = "SETTLED"
            reason_codes = []
        else:
            component_type = "ACYCLIC"
            result = "PROVISIONAL"
            reason_codes = ["CORE_EVALUATION_PENDING"]
        ordered.append(
            {
                "order": order,
                "component_id": "component:"
                + hashlib.sha256("|".join(members).encode("utf-8")).hexdigest()[:12],
                "component_type": component_type,
                "member_ids": members,
                "result": result,
                "reason_codes": reason_codes,
            }
        )
    return ordered


def _history_event_ids(history: Sequence[Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    for record in history:
        if not isinstance(record, Mapping):
            continue
        if isinstance(record.get("event_id"), str):
            result.add(record["event_id"])
        for event_id in record.get("event_ids", []):
            if isinstance(event_id, str):
                result.add(event_id)
        event = record.get("event")
        if isinstance(event, Mapping) and isinstance(event.get("event_id"), str):
            result.add(event["event_id"])
    return result


def _object_semantics(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "definition_id": item.get("definition_id", item.get("definition")),
        "period": item.get("period"),
        "perimeter": item.get("perimeter"),
        "unit": _normalize_unit(item.get("unit")),
    }


def _semantic_reason_codes(
    mutation: Mapping[str, Any], item: Mapping[str, Any]
) -> list[str]:
    item_semantics = _object_semantics(item)
    reason_codes: list[str] = []

    candidate_target_definition = mutation.get("candidate_target_definition_id")
    mutation_definition = mutation.get("definition_id")
    if (
        candidate_target_definition is not None
        and mutation_definition is not None
        and candidate_target_definition != mutation_definition
    ):
        reason_codes.append("NON_APPLICABLE_DEFINITION")
    elif (
        mutation_definition is not None
        and item_semantics["definition_id"] is not None
        and mutation_definition != item_semantics["definition_id"]
    ):
        reason_codes.append("NON_APPLICABLE_DEFINITION")

    for field, reason_code in (
        ("period", "NON_APPLICABLE_PERIOD"),
        ("perimeter", "NON_APPLICABLE_PERIMETER"),
    ):
        proposed = mutation.get(field)
        current = item_semantics[field]
        if proposed is not None and current is not None and proposed != current:
            reason_codes.append(reason_code)

    proposed_unit = _normalize_unit(mutation.get("unit"))
    current_unit = item_semantics["unit"]
    if proposed_unit is not None and current_unit is not None and proposed_unit != current_unit:
        reason_codes.append("NON_APPLICABLE_UNIT")
    return sorted(set(reason_codes))


def _normalize_mapping_coverage_limits(
    execution_mapping: Mapping[str, Any]
) -> list[dict[str, Any]]:
    limits: list[dict[str, Any]] = []
    for index, limit in enumerate(execution_mapping.get("coverage_limits", [])):
        if not isinstance(limit, Mapping):
            continue
        limits.append(
            {
                "limit_id": str(limit.get("limit_id", f"MAPPING-LIMIT-{index:03d}")),
                "reason_code": str(limit.get("reason_code", "MISSING_EXECUTABLE_MAPPING")),
                "scope_ids": sorted(set(str(item) for item in limit.get("scope_ids", []))),
                "effect": str(limit.get("effect", limit.get("reason", "Execution coverage is incomplete."))),
            }
        )
    return limits


def _policy_id(policy: Mapping[str, Any], fallback: str) -> str:
    policy_id = policy.get("policy_id") if isinstance(policy, Mapping) else None
    version = policy.get("version") if isinstance(policy, Mapping) else None
    if policy_id and version:
        return f"{policy_id}@{version}"
    return str(policy_id or fallback)


_MATERIALITY_RANK = {
    "M0_LOCAL": 0,
    "M1_PROFESSIONAL_REVIEW": 1,
    "M2_GATE_AUTHORITY": 2,
    "M3_HARD_BLOCKER": 3,
}


def _selector_matches(
    delta: Mapping[str, Any],
    registry: Mapping[str, Any],
    selectors: Mapping[str, Any],
) -> bool:
    object_id = str(delta["object_id"])
    entry = registry.get(object_id)
    item = entry["object"] if entry else {}
    object_type = delta.get("object_type")

    exact_selectors_present = False
    exact_match = False
    for selector_key, expected_type in (
        ("model_node_ids", "MODEL_NODE"),
        ("position_ids", "POSITION"),
    ):
        values = selectors.get(selector_key, [])
        if values:
            exact_selectors_present = True
            if object_type == expected_type and object_id in values:
                exact_match = True
    definition_ids = selectors.get("definition_ids", [])
    if definition_ids:
        exact_selectors_present = True
        if item.get("definition_id", item.get("definition")) in definition_ids:
            exact_match = True

    pattern_selectors_present = False
    pattern_match = False
    for pattern in selectors.get("model_node_id_patterns", []):
        pattern_selectors_present = True
        if object_type == "MODEL_NODE" and fnmatch.fnmatchcase(object_id, str(pattern)):
            pattern_match = True
    metric_name = str(item.get("metric", item.get("name", object_id)))
    for pattern in selectors.get("metric_name_patterns", []):
        pattern_selectors_present = True
        if fnmatch.fnmatchcase(metric_name.upper(), str(pattern).upper()):
            pattern_match = True

    if not exact_selectors_present and not pattern_selectors_present:
        return False
    return exact_match or pattern_match


def _numeric_threshold_triggered(
    old_value: Any, new_value: Any, test: Mapping[str, Any]
) -> tuple[bool, str | None]:
    try:
        old_decimal = Decimal(str(old_value))
        new_decimal = Decimal(str(new_value))
        threshold = Decimal(str(test["value"]))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False, None
    basis = test.get("basis")
    if basis == "ABSOLUTE_CHANGE":
        observed = abs(new_decimal - old_decimal)
    elif basis == "RELATIVE_CHANGE_TO_LAST_CURRENT":
        if old_decimal == 0:
            return False, None
        observed = abs(new_decimal - old_decimal) / abs(old_decimal)
    else:
        return False, None
    operator = test.get("operator")
    triggered = observed >= threshold if operator == "gte" else observed > threshold
    return triggered, _decimal_output(observed)


def _immediate_propagation_tolerance(
    object_id: str, execution_mapping: Mapping[str, Any]
) -> Decimal | None:
    for item in execution_mapping.get("model_nodes", []):
        if item.get("model_node_id") != object_id:
            continue
        raw_tolerance = item.get("immediate_propagation_tolerance")
        if raw_tolerance is None:
            return None
        try:
            return Decimal(str(raw_tolerance))
        except InvalidOperation:
            return None
    return None


def _condition_matches_decimal(condition: str, value: Decimal) -> tuple[bool, str | None]:
    match = re.search(
        r"(<=|>=|==|!=|<|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$", condition.strip()
    )
    if not match:
        return False, None
    operator, raw_threshold = match.groups()
    threshold = Decimal(raw_threshold)
    result = {
        "<=": value <= threshold,
        ">=": value >= threshold,
        "==": value == threshold,
        "!=": value != threshold,
        "<": value < threshold,
        ">": value > threshold,
    }[operator]
    return result, _decimal_output(threshold)


def _evaluate_rule_switches(
    admitted_mutations: Sequence[Mapping[str, Any]],
    execution_mapping: Mapping[str, Any],
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mutations_by_id = {
        str(mutation["object_id"]): mutation
        for mutation in admitted_mutations
        if mutation.get("field") == "value"
    }
    results: list[dict[str, Any]] = []
    coverage_limits: list[dict[str, Any]] = []
    blocked_ids: set[str] = set()

    for rule_switch in sorted(
        execution_mapping.get("rule_switches", []),
        key=lambda item: str(item.get("rule_switch_id", "")),
    ):
        selector_ids = [str(item) for item in rule_switch.get("selector_input_ids", [])]
        changed_selectors = [item for item in selector_ids if item in mutations_by_id]
        if not changed_selectors:
            continue
        rule_switch_id = str(rule_switch.get("rule_switch_id", "RULE_SWITCH"))
        source_ref = rule_switch.get("source_ref")
        dependent_ids = sorted(set(str(item) for item in rule_switch.get("dependent_ids", [])))
        if not source_ref:
            coverage_limits.append(
                {
                    "limit_id": f"RULE-SOURCE-{rule_switch_id}",
                    "reason_code": "MISSING_RULE_PROVENANCE",
                    "scope_ids": changed_selectors + dependent_ids,
                    "effect": "The governed calculation is blocked until rule provenance is supplied.",
                }
            )
            blocked_ids.update(dependent_ids)
            continue

        selector_id = changed_selectors[0]
        mutation = mutations_by_id[selector_id]
        try:
            old_value = Decimal(str(mutation["from"]))
            new_value = Decimal(str(mutation["to"]))
        except (InvalidOperation, KeyError, TypeError):
            coverage_limits.append(
                {
                    "limit_id": f"RULE-SELECTOR-{rule_switch_id}",
                    "reason_code": "NON_NUMERIC_RULE_SELECTOR",
                    "scope_ids": [selector_id] + dependent_ids,
                    "effect": "The rule selector cannot be evaluated numerically.",
                }
            )
            blocked_ids.update(dependent_ids)
            continue

        def active_branch(value: Decimal) -> tuple[str | None, str | None, str | None]:
            for branch in rule_switch.get("branches", []):
                condition = str(branch.get("condition", ""))
                matches, threshold = _condition_matches_decimal(condition, value)
                if matches:
                    return (
                        str(branch.get("branch_id", branch.get("rule_id"))),
                        condition,
                        threshold,
                    )
            return None, None, None

        if rule_switch.get("condition_evaluation_type") == "GENERAL_EXPRESSION":
            operand_bindings = rule_switch.get("operand_bindings", {})

            def expression_branch(
                use_new_values: bool,
            ) -> tuple[str | None, str | None, str | None]:
                if not registry or not isinstance(operand_bindings, Mapping):
                    raise ValueError("general rule switch has no runtime registry")
                variables: dict[str, Decimal] = {}
                for variable, raw_object_id in operand_bindings.items():
                    object_id = str(raw_object_id)
                    mutation = mutations_by_id.get(object_id)
                    if mutation is not None:
                        raw_value = mutation["to" if use_new_values else "from"]
                    else:
                        entry = registry.get(object_id)
                        if entry is None:
                            raise ValueError(f"missing rule-switch operand {object_id}")
                        raw_value = entry["object"].get("value")
                    variables[str(variable)] = Decimal(str(raw_value))
                for branch in rule_switch.get("branches", []):
                    condition = str(branch.get("condition", ""))
                    if bool(_safe_decimal_expression(condition, variables)):
                        return (
                            str(branch.get("branch_id", branch.get("rule_id"))),
                            condition,
                            None,
                        )
                return None, None, None

            try:
                old_branch, old_condition, old_threshold = expression_branch(False)
                new_branch, new_condition, new_threshold = expression_branch(True)
            except (ArithmeticError, InvalidOperation, KeyError, TypeError, ValueError) as exc:
                coverage_limits.append(
                    {
                        "limit_id": f"RULE-EXPRESSION-{rule_switch_id}",
                        "reason_code": "RULE_SWITCH_EXPRESSION_EVALUATION_FAILED",
                        "scope_ids": changed_selectors + dependent_ids,
                        "effect": (
                            "The complete IF selector expression could not be evaluated: "
                            f"{exc}"
                        ),
                    }
                )
                blocked_ids.update(dependent_ids)
                continue
        else:
            old_branch, old_condition, old_threshold = active_branch(old_value)
            new_branch, new_condition, new_threshold = active_branch(new_value)
        if old_branch is None or new_branch is None:
            coverage_limits.append(
                {
                    "limit_id": f"RULE-BRANCH-{rule_switch_id}",
                    "reason_code": "NO_RULE_BRANCH_MATCH",
                    "scope_ids": [selector_id] + dependent_ids,
                    "effect": "No declared branch covers the selector value.",
                }
            )
            blocked_ids.update(dependent_ids)
            continue
        if old_branch != new_branch:
            results.append(
                {
                    "object_id": selector_id,
                    "rule_id": rule_switch_id,
                    "from": old_branch,
                    "to": new_branch,
                    "reason_code": "RULE_SWITCH_MATERIAL_BY_DEFINITION",
                    "selector_old_value": _decimal_output(old_value),
                    "selector_new_value": _decimal_output(new_value),
                    "selector_condition_from": old_condition,
                    "selector_condition_to": new_condition,
                    "selector_threshold": new_threshold or old_threshold,
                    "source_ref": str(source_ref),
                    "numeric_delta": rule_switch.get(
                        "numeric_delta_at_switch_detection"
                    ),
                    "dependent_ids": dependent_ids,
                    "dependent_financing_component_requeued": bool(dependent_ids),
                    "minimum_materiality_class": str(
                        rule_switch.get("minimum_materiality_class", "M1_PROFESSIONAL_REVIEW")
                    ),
                }
            )

    return {
        "results": results,
        "coverage_limits": coverage_limits,
        "blocked_ids": blocked_ids,
    }


def _classify_materiality(
    candidate_deltas: Sequence[Mapping[str, Any]],
    admitted_mutations: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Any],
    contradictions: Sequence[Mapping[str, Any]],
    materiality_policy: Mapping[str, Any],
    k_t: Mapping[str, Any],
    rule_switches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []

    for rule in materiality_policy.get("economic_thresholds", []):
        selectors = rule.get("selectors", {})
        for delta in candidate_deltas:
            if delta.get("field") != "value" or not _selector_matches(delta, registry, selectors):
                continue
            triggered_tests = []
            comparison_value = k_t.get(str(delta["object_id"]), delta.get("from"))
            for test in rule.get("tests", []):
                triggered, observed = _numeric_threshold_triggered(
                    comparison_value, delta.get("to"), test
                )
                if triggered:
                    triggered_tests.append(
                        {
                            "basis": test.get("basis"),
                            "operator": test.get("operator"),
                            "threshold": test.get("value"),
                            "observed": observed,
                        }
                    )
            if triggered_tests:
                cumulative = not _equivalent(comparison_value, delta.get("from"))
                hits.append(
                    {
                        "rule_id": str(rule["rule_id"]),
                        "object_id": str(delta["object_id"]),
                        "materiality_class": str(rule["minimum_class_when_triggered"]),
                        "tests": triggered_tests,
                        "comparison_basis": (
                            "LAST_ABSORBED_CURRENT_K_T" if cumulative else "CURRENT_INPUT"
                        ),
                        "reason_code": (
                            "CUMULATIVE_THRESHOLD_CROSSED"
                            if cumulative
                            else "ECONOMIC_THRESHOLD_CROSSED"
                        ),
                    }
                )

    for switch in rule_switches:
        hits.append(
            {
                "rule_id": str(switch["rule_id"]),
                "object_id": str(switch["object_id"]),
                "materiality_class": str(switch["minimum_materiality_class"]),
                "reason_code": "RULE_SWITCH_MATERIAL_BY_DEFINITION",
            }
        )

    if contradictions:
        epistemic_rule = next(
            (
                rule
                for rule in materiality_policy.get("epistemic_rules", [])
                if rule.get("condition") == "APPLICABLE_MATERIAL_CONTRADICTION"
            ),
            {},
        )
        hits.append(
            {
                "rule_id": str(epistemic_rule.get("rule_id", "MAT-EPI-004")),
                "object_id": str(contradictions[0]["position_id"]),
                "materiality_class": str(
                    epistemic_rule.get("minimum_class", "M1_PROFESSIONAL_REVIEW")
                ),
                "reason_code": "APPLICABLE_MATERIAL_CONTRADICTION",
            }
        )

    policy_conditions = {
        str(rule.get("condition")): rule
        for rule in materiality_policy.get("gate_and_blocker_rules", [])
    }
    for mutation in admitted_mutations:
        policy_type = mutation.get("policy_type")
        condition = {
            "NON_WAIVABLE_AXIOM": "NON_WAIVABLE_AXIOM",
            "WAIVABLE_HARD_POLICY_BLOCKER": "WAIVABLE_HARD_POLICY_BLOCKER",
        }.get(policy_type)
        rule = policy_conditions.get(condition) if condition else None
        if rule:
            hits.append(
                {
                    "rule_id": str(rule["rule_id"]),
                    "object_id": str(mutation["object_id"]),
                    "materiality_class": str(rule["minimum_class"]),
                    "reason_code": condition,
                }
            )

    classes = [str(hit["materiality_class"]) for hit in hits]
    overall_class = max(classes, key=lambda item: _MATERIALITY_RANK[item]) if classes else "M0_LOCAL"
    return {
        "overall_class": overall_class,
        "triggered_rule_ids": sorted({str(hit["rule_id"]) for hit in hits}),
        "assessments": sorted(hits, key=lambda item: (item["rule_id"], item["object_id"])),
        "comparison_after_full_affected_set": True,
        "severity_aggregation": "MAX",
    }


def _authority_rule(
    authority_policy: Mapping[str, Any], rule_id: str
) -> Mapping[str, Any] | None:
    return next(
        (rule for rule in authority_policy.get("rules", []) if rule.get("rule_id") == rule_id),
        None,
    )


def _govern_transition(
    normalized_events: Sequence[Mapping[str, Any]],
    candidate_deltas: Sequence[Mapping[str, Any]],
    materiality: Mapping[str, Any],
    authority_policy: Mapping[str, Any],
    contradictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    materiality_class = str(materiality["overall_class"])
    human_stops: list[dict[str, Any]] = []
    current_deltas: list[dict[str, Any]] = []
    action_results: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    blocked_components: list[dict[str, Any]] = []
    governance = {
        "current_treatment": "NO_CHANGE",
        "gate_status": "OPEN",
        "waiver_allowed": None,
        "approved_treatment": "UNCHANGED",
    }

    for event in normalized_events:
        action = event.get("governance_action")
        if not isinstance(action, Mapping):
            continue
        rule_id = str(action.get("policy_rule_id", ""))
        rule = _authority_rule(authority_policy, rule_id)
        adoption = rule.get("current_adoption", {}) if rule else {}
        actor_id = action.get("actor_id")
        preparer_id = action.get("prepared_by_actor_id")
        independence_required = bool(
            adoption.get("independence_required")
            or adoption.get("adopter_actor_must_differ_from_preparer_actor")
        )
        if (
            action.get("action") == "ADOPT_INTO_CURRENT"
            and independence_required
            and actor_id == preparer_id
        ):
            required_role = str(
                adoption.get("required_role", "PROFESSIONAL_REVIEWER")
            )
            result = {
                "change_set_id": str(action.get("change_set_id", "UNSPECIFIED")),
                "action": "ADOPT_INTO_CURRENT",
                "result": "REJECTED",
                "reason_code": "SELF_ADOPTION_FORBIDDEN",
                "actor_id": actor_id,
                "required_actor_distinct_from": preparer_id,
                "candidate_change_set_preserved": True,
                "policy_rule_id": rule_id,
            }
            action_results.append(result)
            audit_records.append(
                {
                    "record_type": "GOVERNANCE_ACTION_REJECTED",
                    "event_id": event["event_id"],
                    **result,
                }
            )
            human_stops.append(
                {
                    "stop_id": f"STOP-SELF-ADOPTION-{action.get('change_set_id', event['event_id'])}",
                    "object_or_component_id": str(
                        action.get("change_set_id", event["event_id"])
                    ),
                    "reason_code": "SELF_ADOPTION_FORBIDDEN",
                    "requested_action": "Assign an eligible independent reviewer.",
                    "required_role": required_role,
                    "required_actor_distinct_from": str(preparer_id),
                    "policy_rule_id": rule_id,
                    "downstream_scope": [],
                }
            )
            governance["current_treatment"] = "REJECTED_PENDING_INDEPENDENT_REVIEW"

    if materiality_class == "M0_LOCAL" and candidate_deltas:
        m0_guards_pass = not contradictions and all(
            delta.get("object_type") not in {"POSITION", "ARTIFACT"}
            for delta in candidate_deltas
        )
        if m0_guards_pass:
            governance["current_treatment"] = "AUTOMATIC_RECONCILIATION"
            current_deltas = [
                {**copy.deepcopy(dict(delta)), "status": "APPLIED"}
                for delta in candidate_deltas
            ]
        else:
            materiality_class = "M1_PROFESSIONAL_REVIEW"
            materiality["overall_class"] = materiality_class
            materiality.setdefault("assessments", []).append(
                {
                    "rule_id": "M0-AUTO-RECONCILIATION-GUARDS",
                    "object_id": "candidate-change-set",
                    "materiality_class": materiality_class,
                    "reason_code": "M0_AUTO_RECONCILIATION_GUARDS_FAILED",
                }
            )

    if materiality_class == "M1_PROFESSIONAL_REVIEW" and candidate_deltas:
        if contradictions:
            rule_id = "AUTH-020"
            role = "QUALIFIED_PROFESSIONAL_REVIEWER"
            reason_code = "APPLICABLE_MATERIAL_CONTRADICTION"
        elif "MAT-ECON-001" in materiality.get("triggered_rule_ids", []):
            rule_id = "AUTH-030"
            role = "FINANCIAL_OR_WORKSTREAM_REVIEWER"
            reason_code = "DECISION_REQUIRES_HUMAN"
        else:
            rule_id = "AUTH-010"
            role = "WORKSTREAM_REVIEWER"
            reason_code = "DECISION_REQUIRES_HUMAN"
        governance["current_treatment"] = "PROFESSIONAL_REVIEW_REQUIRED"
        human_stops.append(
            {
                "stop_id": "STOP-CURRENT-REVIEW",
                "object_or_component_id": "candidate-change-set",
                "reason_code": reason_code,
                "requested_action": "Review and adopt or reject the Candidate treatment.",
                "required_role": role,
                "policy_rule_id": rule_id,
                "downstream_scope": sorted(
                    {str(delta["object_id"]) for delta in candidate_deltas}
                ),
            }
        )
    elif materiality_class == "M2_GATE_AUTHORITY":
        governance.update(
            {
                "current_treatment": "PROFESSIONAL_REVIEW_REQUIRED",
                "approved_treatment": "AUTHORITY_PENDING",
            }
        )
        human_stops.extend(
            [
                {
                    "stop_id": "STOP-CURRENT-REVIEW",
                    "object_or_component_id": "candidate-change-set",
                    "reason_code": "DECISION_REQUIRES_HUMAN",
                    "requested_action": "Review the Candidate analysis for Current.",
                    "required_role": "PROFESSIONAL_REVIEWER",
                    "policy_rule_id": "AUTH-040",
                    "downstream_scope": sorted(
                        {str(delta["object_id"]) for delta in candidate_deltas}
                    ),
                },
                {
                    "stop_id": "STOP-APPROVED-AUTHORITY",
                    "object_or_component_id": "approved-snapshot",
                    "reason_code": "APPROVED_FROZEN",
                    "requested_action": "Obtain the applicable authority act before creating a new Approved version.",
                    "required_role": "AUTHORITY_HOLDER",
                    "policy_rule_id": "AUTH-040",
                    "downstream_scope": sorted(
                        {str(delta["object_id"]) for delta in candidate_deltas}
                    ),
                },
            ]
        )
    elif materiality_class == "M3_HARD_BLOCKER":
        non_waivable = any(
            item.get("reason_code") == "NON_WAIVABLE_AXIOM"
            for item in materiality.get("assessments", [])
        )
        governance.update(
            {
                "current_treatment": "REGISTER_FACT_ONLY",
                "gate_status": "BLOCKED",
                "waiver_allowed": not non_waivable,
                "approved_treatment": "UNCHANGED",
            }
        )
        member_ids = sorted({str(delta["object_id"]) for delta in candidate_deltas})
        blocked_components.append(
            {
                "component_id": "component:hard-blocker",
                "member_ids": member_ids,
                "reason_code": "NON_WAIVABLE_AXIOM" if non_waivable else "HARD_POLICY_BLOCKER",
                "dependent_ids": [],
                "missing_assumption_or_condition": None if non_waivable else "Explicit waiver",
            }
        )
        human_stops.append(
            {
                "stop_id": "STOP-HARD-BLOCKER",
                "object_or_component_id": "component:hard-blocker",
                "reason_code": "NON_WAIVABLE_AXIOM" if non_waivable else "HARD_POLICY_BLOCKER",
                "requested_action": (
                    "Stop: the failed axiom is non-waivable."
                    if non_waivable
                    else "Obtain an allowed explicit waiver."
                ),
                "required_role": "PROFESSIONAL_REVIEWER",
                "policy_rule_id": "AUTH-050",
                "downstream_scope": member_ids,
            }
        )

    return {
        "materiality_class": materiality_class,
        "current_deltas": current_deltas,
        "approved_deltas": [],
        "human_stops": human_stops,
        "blocked_components": blocked_components,
        "governance": governance,
        "governance_action_results": action_results,
        "audit_records": audit_records,
    }


def _truth_and(states: Sequence[str]) -> str:
    if any(state == "FALSE" for state in states):
        return "FALSE"
    if states and all(state == "TRUE" for state in states):
        return "TRUE"
    return "UNKNOWN"


def _truth_or(states: Sequence[str]) -> str:
    if any(state == "TRUE" for state in states):
        return "TRUE"
    if states and all(state == "FALSE" for state in states):
        return "FALSE"
    return "UNKNOWN"


def _member_usability(
    object_id: str,
    registry: Mapping[str, Any],
    runtime_flags: Mapping[str, Mapping[str, Any]],
) -> str:
    entry = registry.get(object_id)
    if entry is None:
        return "UNKNOWN"
    item = entry["object"]
    if runtime_flags.get(object_id, {}).get("lifecycle") == "RETRACTED":
        return "FALSE"
    if item.get("validation_only") is True:
        return "FALSE"
    if item.get("usable") is False:
        return "FALSE"
    if item.get("usable") is True:
        return "TRUE"
    if entry["object_type"] == "CLAIM":
        return "TRUE"
    if entry["object_type"] == "POSITION":
        decision_status = item.get("decision_status", item.get("decision_status_at_ic"))
        freshness_status = item.get(
            "freshness_status", item.get("freshness_status_at_ic", "CURRENT")
        )
        if freshness_status == "STALE":
            return "FALSE"
        if decision_status in {"ACCEPTED", "ACCEPTED_WITH_CONDITIONS"}:
            return "TRUE"
        if decision_status in {"REJECTED"}:
            return "FALSE"
        if decision_status is None:
            # Synthetic support fixtures omit institutional axes deliberately.
            return "TRUE"
        return "UNKNOWN"
    if entry["object_type"] == "MODEL_NODE":
        return "TRUE" if item.get("value") is not None else "UNKNOWN"
    return "UNKNOWN"


def _support_circular_route_ids(graph: Mapping[str, Any]) -> set[str]:
    positions = {
        str(position["position_id"])
        for position in graph.get("case_positions", [])
        if isinstance(position, Mapping) and position.get("position_id")
    }
    adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for edge in graph.get("position_dependencies", []):
        if edge.get("relation_type") == "SUPPORTS":
            source = edge.get("from_position_id")
            target = edge.get("to_position_id")
            if source in positions and target in positions:
                adjacency[source].append((target, "SUPPORTS", str(edge.get("edge_id", ""))))
    for route in graph.get("support_routes", []):
        target = route.get("target_position_id")
        for member in route.get("member_position_ids", []):
            if member in positions and target in positions:
                adjacency[member].append((target, "SUPPORTS", str(route.get("route_id", ""))))

    components = _strongly_connected_components(positions, adjacency)
    component_by_position = {
        member: component_index
        for component_index, members in enumerate(components)
        for member in members
    }
    circular: set[str] = set()
    for route in graph.get("support_routes", []):
        target = route.get("target_position_id")
        target_component = component_by_position.get(target)
        if target_component is None:
            continue
        for member in route.get("member_position_ids", []):
            if component_by_position.get(member) == target_component:
                component = components[target_component]
                if len(component) > 1 or member == target:
                    circular.add(str(route["route_id"]))
                    break
    return circular


def _safe_decimal_expression(expression: str, variables: Mapping[str, Decimal]) -> Decimal:
    tree = ast.parse(expression, mode="eval")

    def evaluate(node: ast.AST) -> Decimal | bool:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"unbound formula variable: {node.id}")
            return variables[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left**right
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            left = evaluate(node.left)
            right = evaluate(node.comparators[0])
            operator = node.ops[0]
            if isinstance(operator, ast.Eq):
                return left == right
            if isinstance(operator, ast.NotEq):
                return left != right
            if isinstance(operator, ast.Lt):
                return left < right
            if isinstance(operator, ast.LtE):
                return left <= right
            if isinstance(operator, ast.Gt):
                return left > right
            if isinstance(operator, ast.GtE):
                return left >= right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function_name = node.func.id.upper()
            if function_name == "IF" and len(node.args) == 3:
                condition = evaluate(node.args[0])
                return evaluate(node.args[1]) if bool(condition) else evaluate(node.args[2])
            arguments = [evaluate(argument) for argument in node.args]
            if function_name == "MIN" and arguments:
                return min(arguments)
            if function_name == "MAX" and arguments:
                return max(arguments)
            if function_name == "SUM":
                return sum(arguments, Decimal("0"))
            if function_name == "ABS" and len(arguments) == 1:
                return abs(arguments[0])
        raise ValueError(f"unsupported formula syntax: {ast.dump(node)}")

    result = evaluate(tree)
    if isinstance(result, bool):
        return Decimal("1") if result else Decimal("0")
    return result


def _decimal_output(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _plain_decimal_output(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _formula_input_value(
    registry: Mapping[str, Any], object_id: str
) -> tuple[Any | None, str | None]:
    entry = registry.get(object_id)
    if entry is None:
        return None, "MISSING_FORMULA_INPUT"
    return entry["object"].get("value"), None


def _build_dated_cash_flow_vector(
    formula: Mapping[str, Any], registry: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    spec = formula.get("dated_cash_flow_spec")
    if not isinstance(spec, Mapping):
        return None, "MISSING_DATED_CASH_FLOW_SPEC"
    invested_id = str(spec.get("total_invested_input_id", ""))
    proceeds_id = str(spec.get("exit_proceeds_input_id", ""))
    invested_raw, invested_error = _formula_input_value(registry, invested_id)
    proceeds_raw, proceeds_error = _formula_input_value(registry, proceeds_id)
    if invested_error or proceeds_error:
        return None, invested_error or proceeds_error
    try:
        total_invested = Decimal(str(invested_raw))
        exit_proceeds = Decimal(str(proceeds_raw))
    except (InvalidOperation, TypeError, ValueError):
        return None, "NON_NUMERIC_FORMULA_INPUT"
    if not total_invested.is_finite() or not exit_proceeds.is_finite():
        return None, "NON_NUMERIC_FORMULA_INPUT"

    opening_date = spec.get("opening_date")
    exit_date = spec.get("exit_date")
    try:
        parsed_opening_date = date.fromisoformat(str(opening_date))
        parsed_exit_date = date.fromisoformat(str(exit_date))
    except ValueError:
        return None, "INVALID_CASH_FLOW_DATE"
    if parsed_exit_date <= parsed_opening_date:
        return None, "INVALID_CASH_FLOW_DATE_ORDER"

    interim: list[tuple[date, Decimal]] = []
    for raw_flow in spec.get("interim_investments", []):
        if not isinstance(raw_flow, Mapping):
            return None, "INVALID_INTERIM_CASH_FLOW"
        try:
            flow_date = date.fromisoformat(str(raw_flow.get("date")))
            amount = Decimal(str(raw_flow.get("amount")))
        except (InvalidOperation, TypeError, ValueError):
            return None, "INVALID_INTERIM_CASH_FLOW"
        if (
            not amount.is_finite()
            or amount < 0
            or not (parsed_opening_date < flow_date < parsed_exit_date)
        ):
            return None, "INVALID_INTERIM_CASH_FLOW"
        interim.append((flow_date, amount))

    interim_total = sum((amount for _flow_date, amount in interim), Decimal("0"))
    opening_investment = total_invested - interim_total
    if opening_investment <= 0 or exit_proceeds <= 0:
        return None, "INVALID_CASH_FLOW_SIGN_PATTERN"

    combined: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    combined[parsed_opening_date] -= opening_investment
    for flow_date, amount in interim:
        combined[flow_date] -= amount
    combined[parsed_exit_date] += exit_proceeds
    return (
        {
            "value_type": "DATED_CASH_FLOW_VECTOR",
            "day_count_basis": "ACT_365",
            "cash_flows": [
                {
                    "date": flow_date.isoformat(),
                    "amount": _decimal_output(amount),
                }
                for flow_date, amount in sorted(combined.items())
            ],
        },
        None,
    )


def _xirr_npv(rate: Decimal, cash_flows: Sequence[tuple[date, Decimal]]) -> Decimal:
    if rate <= Decimal("-1"):
        raise ValueError("XIRR rate must be greater than -1")
    base_date = cash_flows[0][0]
    with localcontext() as context:
        context.prec = 50
        base = Decimal("1") + rate
        total = Decimal("0")
        for flow_date, amount in cash_flows:
            year_fraction = Decimal((flow_date - base_date).days) / Decimal("365")
            discount_factor = context.power(base, year_fraction)
            total += amount / discount_factor
        return +total


def _solve_xirr(
    vector: Any, config: Mapping[str, Any] | None = None
) -> tuple[str | None, str | None]:
    if not isinstance(vector, Mapping) or vector.get("value_type") != "DATED_CASH_FLOW_VECTOR":
        return None, "INVALID_DATED_CASH_FLOW_VECTOR"
    config = config if isinstance(config, Mapping) else {}
    vector_basis = str(vector.get("day_count_basis", ""))
    configured_basis = str(config.get("day_count_basis", "ACT_365"))
    if vector_basis != "ACT_365" or configured_basis != "ACT_365":
        return None, "UNSUPPORTED_XIRR_DAY_COUNT_BASIS"
    raw_flows = vector.get("cash_flows")
    if not isinstance(raw_flows, list) or len(raw_flows) < 2:
        return None, "INSUFFICIENT_XIRR_CASH_FLOWS"

    combined: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    try:
        for raw_flow in raw_flows:
            if not isinstance(raw_flow, Mapping):
                return None, "INVALID_DATED_CASH_FLOW_VECTOR"
            flow_date = date.fromisoformat(str(raw_flow.get("date")))
            amount = Decimal(str(raw_flow.get("amount")))
            if not amount.is_finite():
                return None, "INVALID_DATED_CASH_FLOW_VECTOR"
            combined[flow_date] += amount
    except (InvalidOperation, TypeError, ValueError):
        return None, "INVALID_DATED_CASH_FLOW_VECTOR"

    cash_flows = sorted(
        (flow_date, amount) for flow_date, amount in combined.items() if amount != 0
    )
    if len(cash_flows) < 2 or cash_flows[-1][0] == cash_flows[0][0]:
        return None, "INSUFFICIENT_XIRR_CASH_FLOWS"
    signs = [1 if amount > 0 else -1 for _flow_date, amount in cash_flows]
    if 1 not in signs or -1 not in signs:
        return None, "INVALID_CASH_FLOW_SIGN_PATTERN"
    sign_changes = sum(
        left != right for left, right in zip(signs, signs[1:])
    )
    if sign_changes != 1:
        return None, "AMBIGUOUS_XIRR_MULTIPLE_SIGN_CHANGES"

    try:
        tolerance = Decimal(str(config.get("tolerance", "1e-24")))
        residual_tolerance = Decimal(
            str(config.get("residual_tolerance", "1e-28"))
        )
        max_iterations = int(config.get("max_iterations", 256))
    except (InvalidOperation, TypeError, ValueError):
        return None, "INVALID_XIRR_SOLVER_CONFIG"
    if (
        not tolerance.is_finite()
        or not residual_tolerance.is_finite()
        or tolerance <= 0
        or residual_tolerance <= 0
        or max_iterations <= 0
        or config.get("root_selection", "UNIQUE_SIGN_CHANGE_ONLY")
        != "UNIQUE_SIGN_CHANGE_ONLY"
    ):
        return None, "INVALID_XIRR_SOLVER_CONFIG"

    lower = Decimal("-0.999999999999")
    upper = Decimal("1")
    try:
        lower_value = _xirr_npv(lower, cash_flows)
        upper_value = _xirr_npv(upper, cash_flows)
        expansion_count = 0
        while lower_value * upper_value > 0 and expansion_count < 32:
            upper = upper * Decimal("2") + Decimal("1")
            upper_value = _xirr_npv(upper, cash_flows)
            expansion_count += 1
    except (ArithmeticError, InvalidOperation, ValueError):
        return None, "XIRR_EVALUATION_FAILED"
    if lower_value == 0:
        return _decimal_output(lower), None
    if upper_value == 0:
        return _decimal_output(upper), None
    if lower_value * upper_value > 0:
        return None, "XIRR_NO_SOLUTION"

    for _iteration in range(max_iterations):
        midpoint = (lower + upper) / Decimal("2")
        try:
            midpoint_value = _xirr_npv(midpoint, cash_flows)
        except (ArithmeticError, InvalidOperation, ValueError):
            return None, "XIRR_EVALUATION_FAILED"
        if abs(midpoint_value) <= residual_tolerance or abs(upper - lower) <= tolerance:
            return _decimal_output(midpoint), None
        if lower_value * midpoint_value <= 0:
            upper = midpoint
            upper_value = midpoint_value
        else:
            lower = midpoint
            lower_value = midpoint_value
    return None, "XIRR_NON_CONVERGENT"


def _execute_formula(
    formula: Mapping[str, Any], registry: Mapping[str, Any]
) -> tuple[Any | None, str | None]:
    evaluation_type = str(formula.get("evaluation_type", ""))
    if evaluation_type == "BUILD_DATED_CASH_FLOW_VECTOR":
        return _build_dated_cash_flow_vector(formula, registry)
    if evaluation_type == "XIRR":
        input_ids = [str(item) for item in formula.get("input_ids", [])]
        if len(input_ids) != 1:
            return None, "INVALID_XIRR_INPUT_BINDING"
        vector, error = _formula_input_value(registry, input_ids[0])
        if error:
            return None, error
        return _solve_xirr(vector, formula.get("xirr_config"))

    expression = formula.get("expression_or_function_ref")
    if not isinstance(expression, str) or not expression:
        return None, "MISSING_FORMULA_EXPRESSION"
    variables: dict[str, Decimal] = {}
    for name, raw_value in formula.get("fixture_parameters", {}).items():
        try:
            variables[str(name)] = Decimal(str(raw_value))
        except InvalidOperation:
            return None, "NON_NUMERIC_FORMULA_PARAMETER"

    expression_tree = ast.parse(expression, mode="eval")
    called_names = {
        node.func.id
        for node in ast.walk(expression_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    names = sorted(
        {
            node.id
            for node in ast.walk(expression_tree)
            if isinstance(node, ast.Name) and node.id not in called_names
        }
    )
    unresolved_names = [name for name in names if name not in variables]
    input_ids = list(formula.get("input_ids", []))
    operand_bindings = formula.get("operand_bindings", {})
    if operand_bindings:
        resolved_pairs = sorted(
            (str(name), str(object_id)) for name, object_id in operand_bindings.items()
        )
    elif len(unresolved_names) == len(input_ids):
        resolved_pairs = list(zip(unresolved_names, input_ids))
    else:
        return None, "AMBIGUOUS_FORMULA_OPERAND_BINDING"

    for name, object_id in resolved_pairs:
        entry = registry.get(object_id)
        if entry is None:
            return None, "MISSING_FORMULA_INPUT"
        raw_value = entry["object"].get("value")
        try:
            variables[name] = Decimal(str(raw_value))
        except (InvalidOperation, ValueError):
            return None, "NON_NUMERIC_FORMULA_INPUT"
    try:
        return _decimal_output(_safe_decimal_expression(expression, variables)), None
    except (ArithmeticError, ValueError):
        return None, "FORMULA_EVALUATION_FAILED"


def _solve_linear_component(config: Mapping[str, Any]) -> dict[str, Any]:
    member_ids = [str(item) for item in config.get("member_ids", [])]
    equations = [str(item) for item in config.get("equations", [])]
    component_id = str(config.get("component_id", "NUMERICAL-SCC"))
    if len(equations) != len(member_ids) or not member_ids:
        return {
            "component_id": component_id,
            "member_ids": member_ids,
            "outcome": "MISSING_BOUNDARY_CONDITION",
            "values": {},
            "iterations": 0,
            "residual": None,
        }

    zero = {name: Decimal("0") for name in member_ids}
    matrix: list[list[Decimal]] = []
    vector: list[Decimal] = []
    try:
        for equation in equations:
            lhs, rhs = (part.strip() for part in equation.split("=", 1))
            if lhs not in zero:
                raise ValueError("equation lhs is not a component member")
            constant = _safe_decimal_expression(rhs, zero)
            rhs_coefficients = []
            for variable in member_ids:
                basis = dict(zero)
                basis[variable] = Decimal("1")
                rhs_coefficients.append(
                    _safe_decimal_expression(rhs, basis) - constant
                )
            row = [
                (Decimal("1") if variable == lhs else Decimal("0"))
                - rhs_coefficient
                for variable, rhs_coefficient in zip(member_ids, rhs_coefficients)
            ]
            matrix.append(row)
            vector.append(constant)
    except (ArithmeticError, ValueError):
        return {
            "component_id": component_id,
            "member_ids": member_ids,
            "outcome": "MISSING_BOUNDARY_CONDITION",
            "values": {},
            "iterations": 0,
            "residual": None,
        }

    try:
        tolerance = Decimal(str(config.get("absolute_residual_tolerance", "1e-9")))
    except InvalidOperation:
        tolerance = Decimal("1e-9")
    augmented = [row[:] + [rhs] for row, rhs in zip(matrix, vector)]
    pivot_columns: list[int] = []
    pivot_row = 0
    for column in range(len(member_ids)):
        selected = next(
            (
                row_index
                for row_index in range(pivot_row, len(augmented))
                if abs(augmented[row_index][column]) > tolerance
            ),
            None,
        )
        if selected is None:
            continue
        augmented[pivot_row], augmented[selected] = (
            augmented[selected],
            augmented[pivot_row],
        )
        pivot = augmented[pivot_row][column]
        augmented[pivot_row] = [value / pivot for value in augmented[pivot_row]]
        for row_index in range(len(augmented)):
            if row_index == pivot_row:
                continue
            factor = augmented[row_index][column]
            if abs(factor) <= tolerance:
                continue
            augmented[row_index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    augmented[row_index], augmented[pivot_row]
                )
            ]
        pivot_columns.append(column)
        pivot_row += 1
        if pivot_row == len(augmented):
            break

    inconsistent = any(
        all(abs(value) <= tolerance for value in row[:-1])
        and abs(row[-1]) > tolerance
        for row in augmented
    )
    if inconsistent:
        outcome = "NO_ADMISSIBLE_SOLUTION"
        values: dict[str, Decimal] = {}
    elif len(pivot_columns) < len(member_ids):
        outcome = "MULTIPLE_SOLUTIONS"
        values = {}
    else:
        outcome = "UNIQUE_SOLUTION"
        solution = [Decimal("0") for _ in member_ids]
        for row_index, column in enumerate(pivot_columns):
            solution[column] = augmented[row_index][-1]
        values = dict(zip(member_ids, solution))
        for variable, bounds in config.get("admissible_bounds", {}).items():
            if variable not in values or not isinstance(bounds, Sequence) or len(bounds) != 2:
                continue
            lower, upper = Decimal(str(bounds[0])), Decimal(str(bounds[1]))
            if values[variable] < lower - tolerance or values[variable] > upper + tolerance:
                outcome = "NO_ADMISSIBLE_SOLUTION"
                values = {}
                break

    residual: Decimal | None = None
    if values:
        residual = max(
            abs(
                values[equation.split("=", 1)[0].strip()]
                - _safe_decimal_expression(equation.split("=", 1)[1].strip(), values)
            )
            for equation in equations
        )
    return {
        "component_id": component_id,
        "member_ids": member_ids,
        "outcome": outcome,
        "values": {key: _plain_decimal_output(value) for key, value in values.items()},
        "iterations": 1,
        "residual": _plain_decimal_output(residual) if residual is not None else None,
    }


def _evaluate_numeric_components(
    candidate_graph: MutableMapping[str, Any],
    execution_mapping: Mapping[str, Any],
    affected_ids: set[str],
) -> dict[str, Any]:
    registry = _object_registry(candidate_graph)
    results: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    settled_ids: set[str] = set()
    blocked_ids: set[str] = set()
    human_stops: list[dict[str, Any]] = []
    blocked_components: list[dict[str, Any]] = []
    invariant_checks: list[dict[str, Any]] = []

    for config in sorted(
        execution_mapping.get("cyclic_component_solver_configs", []),
        key=lambda item: str(item.get("component_id", "")),
    ):
        member_ids = {str(item) for item in config.get("member_ids", [])}
        activation_ids = {str(item) for item in config.get("activation_input_ids", [])}
        if not (member_ids | activation_ids) & affected_ids:
            continue
        result = _solve_linear_component(config)
        results.append(result)
        if result["outcome"] == "UNIQUE_SOLUTION":
            for object_id, value in sorted(result["values"].items()):
                entry = registry.get(object_id)
                if entry is None:
                    continue
                old_value = copy.deepcopy(entry["object"].get("value"))
                entry["object"]["value"] = value
                updates.append(
                    {
                        "object_type": "MODEL_NODE",
                        "object_id": object_id,
                        "field": "value",
                        "from": old_value,
                        "to": value,
                        "unit": entry["object"].get("unit"),
                        "formula_id": str(config.get("component_id")),
                        "solver_outcome": "UNIQUE_SOLUTION",
                    }
                )
            settled_ids.update(member_ids)
            for control_id in config.get("invariant_control_ids", []):
                invariant_checks.append(
                    {
                        "invariant_id": str(control_id),
                        "status": "PASS",
                        "details": "The numerical component has a unique admissible solution.",
                    }
                )
        else:
            blocked_ids.update(member_ids)
            reason_code = str(result["outcome"])
            blocked_components.append(
                {
                    "component_id": str(result["component_id"]),
                    "member_ids": sorted(member_ids),
                    "reason_code": reason_code,
                    "dependent_ids": sorted(
                        set(str(item) for item in config.get("dependent_ids", []))
                    ),
                    "missing_assumption_or_condition": (
                        "Add an independent constraint or boundary condition."
                        if reason_code == "MULTIPLE_SOLUTIONS"
                        else "Resolve inconsistent equations or constraints."
                    ),
                }
            )
            human_stops.append(
                {
                    "stop_id": f"STOP-NUMERIC-{result['component_id']}",
                    "object_or_component_id": str(result["component_id"]),
                    "reason_code": reason_code,
                    "requested_action": blocked_components[-1][
                        "missing_assumption_or_condition"
                    ],
                    "required_role": "PREPARER",
                    "policy_rule_id": "KERNEL-NUMERICAL-SCC",
                    "downstream_scope": sorted(member_ids),
                }
            )
    return {
        "results": results,
        "updates": updates,
        "settled_ids": settled_ids,
        "blocked_ids": blocked_ids,
        "human_stops": human_stops,
        "blocked_components": blocked_components,
        "invariant_checks": invariant_checks,
    }


def _inverse_variables(
    price: Decimal, branch: Mapping[str, Any], variable_symbol: str
) -> dict[str, Decimal]:
    variables: dict[str, Decimal] = {
        variable_symbol: price,
        "SUPPORTED_PRICE": price,
    }
    for key, value in branch.items():
        if key in {"branch_id", "entry_equity_formula"}:
            continue
        try:
            variables[str(key)] = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            continue
    fixed_debt = variables.get("fixed_debt", variables.get("entry_debt", Decimal("0")))
    exit_proceeds = variables.get(
        "exit_equity_proceeds", Decimal(str(branch.get("exit_equity_proceeds", "0")))
    )
    variables["fixed_debt"] = fixed_debt
    variables["entry_debt"] = fixed_debt
    variables["exit_equity_proceeds"] = exit_proceeds
    entry_expression = str(
        branch.get("entry_equity_formula", f"{variable_symbol} - fixed_debt")
    ).replace("^", "**")
    variables["entry_equity"] = _safe_decimal_expression(entry_expression, variables)
    return variables


def _constraint_result(
    constraint: Mapping[str, Any], variables: Mapping[str, Decimal]
) -> tuple[bool, Decimal, Decimal]:
    expression = str(
        constraint.get("expression_or_function_ref", constraint.get("expression", ""))
    ).replace("^", "**")
    actual = _safe_decimal_expression(expression, variables)
    required = Decimal(str(constraint["value"]))
    operator = str(constraint.get("operator", "gte"))
    satisfied = {
        "gte": actual >= required,
        "gt": actual > required,
        "lte": actual <= required,
        "lt": actual < required,
        "eq": actual == required,
    }.get(operator, False)
    slack = actual - required if operator in {"gte", "gt", "eq"} else required - actual
    return satisfied, actual, slack


def _solve_inverse_branch(
    config: Mapping[str, Any], branch: Mapping[str, Any]
) -> dict[str, Any]:
    objective = config.get("objective", {})
    variable_id = str(
        objective.get("variable_id", config.get("decision_variable_ids", [""])[0])
    )
    variable_symbol = str(objective.get("variable_symbol", "SUPPORTED_PRICE"))
    raw_bounds = objective.get("bounds") or config.get("admissible_bounds", {}).get(variable_id)
    if not isinstance(raw_bounds, Sequence) or len(raw_bounds) != 2:
        return {"outcome": "MISSING_BOUNDARY_CONDITION", "branch_id": branch.get("branch_id")}
    lower, upper = Decimal(str(raw_bounds[0])), Decimal(str(raw_bounds[1]))
    tolerance = Decimal(str(config.get("price_tolerance", config.get("absolute_residual_tolerance", "1e-9"))))
    constraint_tolerance = Decimal(str(config.get("constraint_tolerance", "1e-9")))
    constraints = list(config.get("constraints", []))

    def evaluate(price: Decimal) -> tuple[bool, dict[str, Decimal], list[dict[str, Any]]]:
        try:
            variables = _inverse_variables(price, branch, variable_symbol)
            evaluations = []
            for constraint in constraints:
                satisfied, actual, slack = _constraint_result(constraint, variables)
                evaluations.append(
                    {
                        "constraint_id": str(constraint["constraint_id"]),
                        "source_ref": str(constraint.get("source_ref", "")),
                        "satisfied": satisfied,
                        "actual": actual,
                        "slack": slack,
                    }
                )
            return all(item["satisfied"] for item in evaluations), variables, evaluations
        except (ArithmeticError, InvalidOperation, KeyError, ValueError):
            return False, {}, []

    feasible_low: Decimal | None = None
    feasible_low_data: tuple[dict[str, Decimal], list[dict[str, Any]]] | None = None
    scan_steps = 1000
    for index in range(scan_steps + 1):
        candidate = lower + (upper - lower) * Decimal(index) / Decimal(scan_steps)
        if index == 0:
            candidate += tolerance
        feasible, variables, evaluations = evaluate(candidate)
        if feasible:
            feasible_low = candidate
            feasible_low_data = (variables, evaluations)
            break
    if feasible_low is None or feasible_low_data is None:
        return {
            "outcome": "NO_ADMISSIBLE_SOLUTION",
            "branch_id": str(branch.get("branch_id", "DEFAULT")),
        }

    upper_feasible, upper_variables, upper_evaluations = evaluate(upper)
    if upper_feasible:
        optimum = upper
        variables = upper_variables
        evaluations = upper_evaluations
        iterations = 0
    else:
        feasible_bound = feasible_low
        infeasible_bound = upper
        iterations = 0
        maximum_iterations = int(config.get("maximum_iterations", 200))
        while iterations < maximum_iterations and infeasible_bound - feasible_bound > tolerance:
            midpoint = (feasible_bound + infeasible_bound) / Decimal("2")
            feasible, _variables, _evaluations = evaluate(midpoint)
            if feasible:
                feasible_bound = midpoint
            else:
                infeasible_bound = midpoint
            iterations += 1
        optimum = feasible_bound.quantize(tolerance)
        feasible, variables, evaluations = evaluate(optimum)
        if not feasible:
            optimum -= tolerance
            feasible, variables, evaluations = evaluate(optimum)
        if not feasible:
            return {
                "outcome": "NON_CONVERGENT",
                "branch_id": str(branch.get("branch_id", "DEFAULT")),
            }

    binding_constraints = [
        {
            "constraint_id": item["constraint_id"],
            "source_ref": item["source_ref"],
            "slack": _plain_decimal_output(item["slack"]),
        }
        for item in evaluations
        if abs(item["slack"]) <= constraint_tolerance
    ]
    return {
        "outcome": "UNIQUE_OPTIMUM",
        "branch_id": str(branch.get("branch_id", "DEFAULT")),
        "decision_value": _plain_decimal_output(optimum),
        "variables": {
            key: _plain_decimal_output(value)
            for key, value in variables.items()
        },
        "binding_constraints": binding_constraints,
        "iterations": iterations,
    }


def _evaluate_inverse_solvers(
    candidate_graph: MutableMapping[str, Any],
    execution_mapping: Mapping[str, Any],
    affected_ids: set[str],
) -> dict[str, Any]:
    registry = _object_registry(candidate_graph)
    results: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    settled_ids: set[str] = set()
    blocked_ids: set[str] = set()
    blocked_components: list[dict[str, Any]] = []
    human_stops: list[dict[str, Any]] = []

    for config in sorted(
        execution_mapping.get("inverse_solver_configs", []),
        key=lambda item: str(item.get("solver_id", "")),
    ):
        objective = config.get("objective", {})
        variable_id = str(
            objective.get("variable_id", config.get("decision_variable_ids", [""])[0])
        )
        activation_ids = {str(item) for item in config.get("activation_input_ids", [])}
        if variable_id not in affected_ids and not (activation_ids & affected_ids):
            continue
        solver_id = str(config.get("solver_id", "INVERSE-SOLVER"))
        branches = list(config.get("financing_branches", config.get("branches", [])))
        if not branches:
            branches = [{"branch_id": "DEFAULT"}]
        branch_results = [_solve_inverse_branch(config, branch) for branch in branches]
        feasible = [item for item in branch_results if item.get("outcome") == "UNIQUE_OPTIMUM"]

        if not feasible:
            outcome = "NO_ADMISSIBLE_SOLUTION"
            result = {
                "solver_id": solver_id,
                "object_id": variable_id,
                "solver_outcome": outcome,
                "selected_solution": None,
                "branch_results": branch_results,
            }
        else:
            sense = str(objective.get("sense", "MAXIMIZE"))
            optimum_value = (
                max(Decimal(item["decision_value"]) for item in feasible)
                if sense == "MAXIMIZE"
                else min(Decimal(item["decision_value"]) for item in feasible)
            )
            tolerance = Decimal(str(config.get("price_tolerance", config.get("absolute_residual_tolerance", "1e-9"))))
            optimal = [
                item
                for item in feasible
                if abs(Decimal(item["decision_value"]) - optimum_value) <= tolerance
            ]
            precedence = config.get("branch_precedence")
            selected = None
            if len(optimal) == 1:
                selected = optimal[0]
            elif precedence:
                by_branch = {item["branch_id"]: item for item in optimal}
                selected = next(
                    (by_branch[item] for item in precedence if item in by_branch), None
                )
            if selected is None:
                outcome = "MULTIPLE_OPTIMAL_SOLUTIONS"
                result = {
                    "solver_id": solver_id,
                    "object_id": variable_id,
                    "solver_outcome": outcome,
                    "selected_solution": None,
                    "supported_price_candidates": [item["decision_value"] for item in optimal],
                    "solution_branch_ids": [item["branch_id"] for item in optimal],
                    "branch_results": branch_results,
                }
            else:
                outcome = "UNIQUE_OPTIMUM"
                result = {
                    "solver_id": solver_id,
                    "object_id": variable_id,
                    "solver_outcome": outcome,
                    "selected_solution": selected,
                    "decision_value": selected["decision_value"],
                    "binding_constraints": selected["binding_constraints"],
                    "branch_results": branch_results,
                }

        results.append(result)
        if result["solver_outcome"] == "UNIQUE_OPTIMUM":
            entry = registry.get(variable_id)
            if entry is not None:
                old_value = copy.deepcopy(entry["object"].get("value"))
                entry["object"]["value"] = result["decision_value"]
                updates.append(
                    {
                        "object_type": "MODEL_NODE",
                        "object_id": variable_id,
                        "field": "value",
                        "from": old_value,
                        "to": result["decision_value"],
                        "unit": entry["object"].get("unit"),
                        "formula_id": solver_id,
                        "solver_outcome": "UNIQUE_OPTIMUM",
                        "binding_constraints": result["binding_constraints"],
                    }
                )
            settled_ids.add(variable_id)
        else:
            blocked_ids.add(variable_id)
            reason_code = str(result["solver_outcome"])
            blocked_components.append(
                {
                    "component_id": solver_id,
                    "member_ids": [variable_id],
                    "reason_code": reason_code,
                    "dependent_ids": sorted(
                        set(str(item) for item in config.get("dependent_ids", []))
                    ),
                    "missing_assumption_or_condition": (
                        "Declare deterministic branch precedence."
                        if reason_code == "MULTIPLE_OPTIMAL_SOLUTIONS"
                        else "Relax or reconcile the declared constraints and bounds."
                    ),
                }
            )
            human_stops.append(
                {
                    "stop_id": f"STOP-INVERSE-{solver_id}",
                    "object_or_component_id": solver_id,
                    "reason_code": reason_code,
                    "requested_action": blocked_components[-1]["missing_assumption_or_condition"],
                    "required_role": "PROFESSIONAL_REVIEWER",
                    "policy_rule_id": "KERNEL-INVERSE-SOLVE",
                    "downstream_scope": [variable_id]
                    + blocked_components[-1]["dependent_ids"],
                }
            )
    return {
        "results": results,
        "updates": updates,
        "settled_ids": settled_ids,
        "blocked_ids": blocked_ids,
        "blocked_components": blocked_components,
        "human_stops": human_stops,
    }


def _topologically_order_formulas(
    formulas: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return a deterministic dependency order for scalar formula evaluation.

    The execution mapping may contain thousands of formulas whose identifiers
    are unrelated to calculation order.  Formula outputs therefore have to be
    ordered from their mapped inputs, not lexicographically.  Any residual
    cycle is kept deterministic here and remains subject to the dedicated SCC
    solver stage; no fixed point is selected by this helper.
    """

    formula_by_output = {
        str(formula.get("output_id")): formula
        for formula in formulas
        if formula.get("output_id")
    }
    formula_id_by_output = {
        output_id: str(formula.get("formula_id", output_id))
        for output_id, formula in formula_by_output.items()
    }
    dependents: dict[str, set[str]] = defaultdict(set)
    indegree = {output_id: 0 for output_id in formula_by_output}
    for output_id, formula in formula_by_output.items():
        for input_id in set(str(item) for item in formula.get("input_ids", [])):
            if input_id not in formula_by_output or input_id == output_id:
                continue
            if output_id not in dependents[input_id]:
                dependents[input_id].add(output_id)
                indegree[output_id] += 1

    ready = [
        (formula_id_by_output[output_id], output_id)
        for output_id, degree in indegree.items()
        if degree == 0
    ]
    heapq.heapify(ready)
    ordered_outputs: list[str] = []
    while ready:
        _formula_id, output_id = heapq.heappop(ready)
        ordered_outputs.append(output_id)
        for dependent_id in sorted(
            dependents.get(output_id, ()),
            key=lambda item: (formula_id_by_output[item], item),
        ):
            indegree[dependent_id] -= 1
            if indegree[dependent_id] == 0:
                heapq.heappush(
                    ready, (formula_id_by_output[dependent_id], dependent_id)
                )

    residual_outputs = sorted(
        set(formula_by_output) - set(ordered_outputs),
        key=lambda item: (formula_id_by_output[item], item),
    )
    return [formula_by_output[item] for item in ordered_outputs + residual_outputs]


def _evaluate_routes_and_formulas(
    candidate_graph: MutableMapping[str, Any],
    execution_mapping: Mapping[str, Any],
    runtime_flags: Mapping[str, Mapping[str, Any]],
    affected_ids: set[str],
    *,
    evaluate_all_routes: bool,
    evaluate_all_formulas: bool,
) -> dict[str, Any]:
    registry = _object_registry(candidate_graph)
    routes_by_id = {
        str(route["route_id"]): route
        for route in candidate_graph.get("support_routes", [])
        if isinstance(route, Mapping) and route.get("route_id")
    }
    formulas_by_route = {
        str(formula["route_id"]): formula
        for formula in execution_mapping.get("formulas", [])
        if isinstance(formula, Mapping) and formula.get("route_id")
    }
    circular_route_ids = _support_circular_route_ids(candidate_graph)
    affected_targets = {
        object_id
        for object_id in affected_ids
        if object_id in registry and registry[object_id]["object_type"] == "POSITION"
    }
    for route_id in affected_ids:
        route = routes_by_id.get(route_id)
        if route:
            affected_targets.add(str(route["target_position_id"]))
    selected_route_ids = {
        route_id
        for route_id, route in routes_by_id.items()
        if evaluate_all_routes or route.get("target_position_id") in affected_targets
    }

    route_results: list[dict[str, Any]] = []
    formula_updates: list[dict[str, Any]] = []
    coverage_limits: list[dict[str, Any]] = []
    invariant_checks: list[dict[str, Any]] = []
    settled_ids: set[str] = set()
    blocked_ids: set[str] = set()

    for route_id in sorted(selected_route_ids):
        route = routes_by_id[route_id]
        target_id = str(route["target_position_id"])
        logic = str(route.get("logic", ""))
        member_ids = sorted(
            set(route.get("member_claim_ids", []))
            | set(route.get("member_position_ids", []))
        )
        counter_ids = sorted(set(route.get("counter_claim_ids", [])))
        member_states = {
            member_id: _member_usability(member_id, registry, runtime_flags)
            for member_id in member_ids
        }
        counter_states = {
            member_id: _member_usability(member_id, registry, runtime_flags)
            for member_id in counter_ids
        }
        result: dict[str, Any] = {
            "route_id": route_id,
            "target_position_id": target_id,
            "logic": logic,
            "member_states": member_states,
            "invalid": False,
            "reason_codes": [],
        }
        if route_id in circular_route_ids:
            result.update(
                {
                    "state": "UNKNOWN",
                    "support_satisfied": "UNKNOWN",
                    "invalid": True,
                    "reason_codes": ["CIRCULAR_SUPPORT"],
                }
            )
            blocked_ids.add(route_id)
            route_results.append(result)
            continue

        support_state = _truth_and(list(member_states.values()))
        if logic == "FORMULA":
            formula = formulas_by_route.get(route_id)
            if support_state == "TRUE" and formula is not None:
                candidate_value, error = _execute_formula(formula, registry)
                output_id = str(formula.get("output_id", ""))
                output_entry = registry.get(output_id)
                if error is None and output_entry is not None:
                    old_value = copy.deepcopy(output_entry["object"].get("value"))
                    if not _equivalent(old_value, candidate_value):
                        output_entry["object"]["value"] = candidate_value
                    result.update(
                        {
                            "state": "TRUE",
                            "support_satisfied": "TRUE",
                            "candidate_value": candidate_value,
                            "unit": output_entry["object"].get("unit"),
                            "formula_id": formula.get("formula_id"),
                        }
                    )
                    settled_ids.add(output_id)
                    formula_updates.append(
                        {
                            "object_type": "MODEL_NODE",
                            "object_id": output_id,
                            "field": "value",
                            "from": old_value,
                            "to": candidate_value,
                            "unit": output_entry["object"].get("unit"),
                            "formula_id": formula.get("formula_id"),
                        }
                    )
                    for control_id in formula.get("control_ids", []):
                        invariant_checks.append(
                            {
                                "invariant_id": str(control_id),
                                "status": "PASS",
                                "details": "Declared formula evaluated with usable inputs.",
                            }
                        )
                else:
                    reason_code = error or "MISSING_FORMULA_OUTPUT"
                    result.update(
                        {
                            "state": "UNKNOWN",
                            "support_satisfied": "UNKNOWN",
                            "reason_codes": [reason_code],
                        }
                    )
                    coverage_limits.append(
                        {
                            "limit_id": f"FORMULA-{route_id}",
                            "reason_code": reason_code,
                            "scope_ids": [route_id, output_id],
                            "effect": "The formula route could not produce a Candidate value.",
                        }
                    )
            elif support_state == "FALSE":
                result.update({"state": "FALSE", "support_satisfied": "FALSE"})
            else:
                reason_code = "MISSING_FORMULA_MAPPING" if formula is None else "FORMULA_INPUT_UNKNOWN"
                result.update(
                    {
                        "state": "UNKNOWN",
                        "support_satisfied": "UNKNOWN",
                        "reason_codes": [reason_code],
                    }
                )
                if formula is None:
                    coverage_limits.append(
                        {
                            "limit_id": f"FORMULA-{route_id}",
                            "reason_code": reason_code,
                            "scope_ids": [route_id, target_id],
                            "effect": "A FORMULA support route has no executable formula mapping.",
                        }
                    )
        elif logic == "AND_WITH_COUNTEREVIDENCE":
            counter_state = _truth_or(list(counter_states.values()))
            result.update(
                {
                    "state": support_state,
                    "support_satisfied": support_state,
                    "counterevidence_present": counter_state,
                    "counter_member_states": counter_states,
                }
            )
        elif logic in {"AND", "INDEPENDENT"}:
            result.update({"state": support_state, "support_satisfied": support_state})
        else:
            result.update(
                {
                    "state": "UNKNOWN",
                    "support_satisfied": "UNKNOWN",
                    "reason_codes": ["UNKNOWN_ROUTE_LOGIC"],
                }
            )
            coverage_limits.append(
                {
                    "limit_id": f"ROUTE-{route_id}",
                    "reason_code": "UNKNOWN_ROUTE_LOGIC",
                    "scope_ids": [route_id, target_id],
                    "effect": "The route logic is not executable.",
                }
            )
        settled_ids.add(route_id)
        route_results.append(result)

    standalone_formulas = [
        item
        for item in execution_mapping.get("formulas", [])
        if isinstance(item, Mapping) and not item.get("route_id")
    ]
    selected_formulas = [
        formula
        for formula in standalone_formulas
        if evaluate_all_formulas
        or str(formula.get("output_id", "")) in affected_ids
        or bool(
            {str(item) for item in formula.get("input_ids", [])} & affected_ids
        )
    ]
    for formula in _topologically_order_formulas(selected_formulas):
        input_ids = {str(item) for item in formula.get("input_ids", [])}
        output_id = str(formula.get("output_id", ""))
        candidate_value, error = _execute_formula(formula, registry)
        output_entry = registry.get(output_id)
        if error is None and output_entry is not None:
            old_value = copy.deepcopy(output_entry["object"].get("value"))
            if not _equivalent(old_value, candidate_value):
                output_entry["object"]["value"] = candidate_value
            formula_updates.append(
                {
                    "object_type": "MODEL_NODE",
                    "object_id": output_id,
                    "field": "value",
                    "from": old_value,
                    "to": candidate_value,
                    "unit": output_entry["object"].get("unit"),
                    "formula_id": formula.get("formula_id"),
                }
            )
            settled_ids.add(output_id)
        else:
            reason_code = error or "MISSING_FORMULA_OUTPUT"
            coverage_limits.append(
                {
                    "limit_id": f"FORMULA-{formula.get('formula_id', output_id)}",
                    "reason_code": reason_code,
                    "scope_ids": sorted(input_ids | {output_id}),
                    "effect": "The standalone formula could not produce a Candidate value.",
                }
            )

    combination_results = []
    targets = sorted({result["target_position_id"] for result in route_results})
    for target_id in targets:
        target_routes = [
            result for result in route_results if result["target_position_id"] == target_id
        ]
        valid_states = [result["state"] for result in target_routes if not result["invalid"]]
        combined_state = _truth_or(valid_states)
        combination_results.append(
            {
                "position_id": target_id,
                "state": combined_state,
                "valid_route_ids": sorted(
                    result["route_id"] for result in target_routes if not result["invalid"]
                ),
                "invalid_route_ids": sorted(
                    result["route_id"] for result in target_routes if result["invalid"]
                ),
            }
        )
        if combined_state in {"TRUE", "FALSE"}:
            settled_ids.add(target_id)

    return {
        "route_results": route_results,
        "combination_results": combination_results,
        "formula_updates": formula_updates,
        "coverage_limits": coverage_limits,
        "invariant_checks": invariant_checks,
        "settled_ids": settled_ids,
        "blocked_ids": blocked_ids,
        "invalid_route_ids": sorted(circular_route_ids & selected_route_ids),
    }


def apply_state_transition(
    prior_state: Mapping[str, Any],
    event_batch: Sequence[Mapping[str, Any]],
    execution_mapping: Mapping[str, Any],
    materiality_policy: Mapping[str, Any],
    authority_policy: Mapping[str, Any],
    *,
    execution_mode: str = "INCREMENTAL_SCC",
) -> dict[str, Any]:
    """Build an immutable Candidate and deterministic core transition output.

    ``prior_state`` may be either a bare Canonical Case graph or the runtime
    envelope returned by :func:`build_runtime_state`.
    """

    if execution_mode not in {"INCREMENTAL_SCC", "GLOBAL_RECOMPUTE"}:
        raise EventInputError(f"unsupported execution_mode: {execution_mode}")
    state = _coerce_runtime_state(prior_state)
    current_graph = state["current_graph"]
    candidate_graph = copy.deepcopy(current_graph)
    registry = _object_registry(candidate_graph)
    normalized_events = normalize_event_batch(event_batch)
    previous_event_ids = _history_event_ids(state["history"])

    admitted_mutations: list[dict[str, Any]] = []
    equivalent_mutations: list[dict[str, Any]] = []
    non_applicable_mutations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    rejected_mutations: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    epistemic_candidate_deltas: list[dict[str, Any]] = []
    sub_tolerance_mutations: list[dict[str, Any]] = []
    runtime_flags: dict[str, dict[str, Any]] = copy.deepcopy(
        dict(state.get("runtime_flags", {}))
    )
    history_append: list[dict[str, Any]] = []
    trigger_ids: set[str] = set()
    conflict_seed_ids: set[str] = set()
    evaluation_request = False

    grouped_events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in normalized_events:
        grouped_events[_event_batch_key(event)].append(event)
    ordered_groups = sorted(
        grouped_events.items(),
        key=lambda item: (item[1][0]["known_at"], item[0], item[1][0]["event_id"]),
    )

    for batch_key, events in ordered_groups:
        active_events = [event for event in events if event["event_id"] not in previous_event_ids]
        replayed_events = [event for event in events if event["event_id"] in previous_event_ids]
        for event in replayed_events:
            equivalent_mutations.append(
                {
                    "object_type": "CLAIM",
                    "object_id": event["event_id"],
                    "field": "event_id",
                    "from": event["event_id"],
                    "to": event["event_id"],
                    "reason_code": "EQUIVALENT_EVENT",
                }
            )
        if not active_events:
            continue

        for event in active_events:
            if not event["mutations"]:
                evaluation_request = True
                for trigger_id in event["trigger_claim_ids"]:
                    if trigger_id in registry:
                        trigger_ids.add(trigger_id)

        mutations_by_key: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for event in active_events:
            for mutation in event["mutations"]:
                field = str(mutation.get("field", "__lifecycle__"))
                mutations_by_key[(mutation["object_id"], field)].append((event, mutation))

        for (object_id, field), event_mutations in sorted(mutations_by_key.items()):
            target_values = {
                _canonical_json(mutation.get("to"))
                for _event, mutation in event_mutations
            }
            operations = {mutation["operation"] for _event, mutation in event_mutations}
            if len(target_values) > 1 or len(operations) > 1:
                conflicts.append(
                    {
                        "object_id": object_id,
                        "field": field,
                        "event_ids": sorted(event["event_id"] for event, _mutation in event_mutations),
                        "reason_code": "BATCH_VALUE_CONFLICT",
                    }
                )
                if object_id in registry:
                    conflict_seed_ids.add(object_id)
                continue

            event, mutation = sorted(
                event_mutations, key=lambda pair: pair[0]["event_id"]
            )[0]
            entry = registry.get(object_id)
            if entry is None:
                if mutation["operation"] == "ADD" and mutation["object_type"] == "CLAIM":
                    relation_type = mutation.get("relation_type")
                    target_position_id = mutation.get("target_position_id")
                    target_entry = registry.get(str(target_position_id))
                    if relation_type in {"SUPPORTS", "CONTRADICTS"}:
                        if target_entry is None or target_entry["object_type"] != "POSITION":
                            rejected_mutations.append(
                                {
                                    "object_type": "CLAIM",
                                    "object_id": object_id,
                                    "field": field,
                                    "reason_code": "UNKNOWN_TARGET_POSITION_ID",
                                }
                            )
                            continue
                        semantic_reasons = _semantic_reason_codes(
                            mutation, target_entry["object"]
                        )
                        if semantic_reasons:
                            non_applicable_mutations.append(
                                {
                                    "object_type": "CLAIM",
                                    "object_id": object_id,
                                    "field": field,
                                    "from": None,
                                    "to": "ACTIVE",
                                    "reason_codes": semantic_reasons,
                                }
                            )
                            continue

                    new_claim = {
                        "claim_id": object_id,
                        "statement": str(mutation.get("statement", event["event"])),
                        "source_id": str(event["source_ids"][0]) if event["source_ids"] else "UNSPECIFIED",
                        "locator": str(mutation.get("locator", f"event:{event['event_id']}")),
                        "epistemic_class": str(mutation.get("epistemic_class", "observed")),
                        "period": str(mutation.get("period", "UNSPECIFIED")),
                        "perimeter": str(mutation.get("perimeter", "UNSPECIFIED")),
                        "ground_truth_flag": bool(mutation.get("ground_truth_flag", False)),
                        "validation_only": False,
                    }
                    for optional_field in ("definition_id", "unit", "value"):
                        if mutation.get(optional_field) is not None:
                            new_claim[optional_field] = copy.deepcopy(mutation[optional_field])
                    candidate_graph.setdefault("claims", []).append(new_claim)
                    registry[object_id] = {
                        "object_type": "CLAIM",
                        "collection": "claims",
                        "id_field": "claim_id",
                        "object": new_claim,
                    }
                    admitted = {
                        "event_id": event["event_id"],
                        "operation": "ADD",
                        "object_type": "CLAIM",
                        "object_id": object_id,
                        "field": "__lifecycle__",
                        "from": None,
                        "to": "ACTIVE",
                        "unit": mutation.get("unit"),
                        "materiality_fixture": mutation.get("materiality_fixture"),
                        "relation_type": relation_type,
                        "target_position_id": target_position_id,
                        "value": copy.deepcopy(mutation.get("value")),
                    }
                    admitted_mutations.append(admitted)
                    trigger_ids.add(object_id)

                    if relation_type in {"SUPPORTS", "CONTRADICTS"}:
                        edge_id = "EVENT-EDGE:" + hashlib.sha256(
                            f"{event['event_id']}|{object_id}|{relation_type}|{target_position_id}".encode("utf-8")
                        ).hexdigest()[:12]
                        candidate_graph.setdefault("claim_position_edges", []).append(
                            {
                                "edge_id": edge_id,
                                "claim_id": object_id,
                                "position_id": target_position_id,
                                "relation_type": relation_type,
                            }
                        )
                    if relation_type == "CONTRADICTS" and mutation.get("materiality_fixture") == "MATERIAL":
                        target_item = target_entry["object"]
                        old_epistemic = target_item.get(
                            "epistemic_status", target_item.get("epistemic_status_at_ic")
                        )
                        target_item["epistemic_status"] = "CONTESTED"
                        contradictions.append(
                            {
                                "claim_id": object_id,
                                "position_id": str(target_position_id),
                                "applicable": True,
                                "material": True,
                            }
                        )
                        if old_epistemic != "CONTESTED":
                            epistemic_candidate_deltas.append(
                                {
                                    "object_type": "POSITION",
                                    "object_id": str(target_position_id),
                                    "field": "epistemic_status",
                                    "from": old_epistemic,
                                    "to": "CONTESTED",
                                    "status": "PROPOSED",
                                    "reason_code": "APPLICABLE_MATERIAL_CONTRADICTION",
                                }
                            )
                    continue
                rejected_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "reason_code": "UNKNOWN_OBJECT_ID",
                    }
                )
                continue
            if entry["object_type"] != mutation["object_type"]:
                rejected_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "reason_code": "OBJECT_TYPE_MISMATCH",
                    }
                )
                continue
            if field.endswith("_at_ic"):
                rejected_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "reason_code": "IMMUTABLE_HISTORICAL_FIELD",
                    }
                )
                conflict_seed_ids.add(object_id)
                continue
            if field in HUMAN_ONLY_FIELDS and not _is_recorded_human_decision(event):
                # The system may compute how well supported a position is; whether
                # the firm has decided is not a computation. The _at_ic guard above
                # already freezes decision_status_at_ic, but the unsuffixed field is
                # what _truth_status reads first and what the router writes, so
                # without this a transition could move a position to ACCEPTED with
                # no human ever having decided — the one thing the case model must
                # never do.
                rejected_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "reason_code": "DECISION_STATUS_HUMAN_ONLY",
                    }
                )
                conflict_seed_ids.add(object_id)
                continue

            item = entry["object"]
            semantic_reasons = _semantic_reason_codes(mutation, item)
            if semantic_reasons:
                non_applicable_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "from": copy.deepcopy(item.get(field)),
                        "to": copy.deepcopy(mutation.get("to")),
                        "reason_codes": semantic_reasons,
                    }
                )
                continue

            operation = mutation["operation"]
            current_value = (
                runtime_flags.get(object_id, {}).get("lifecycle", "ACTIVE")
                if field == "__lifecycle__"
                else item.get(field)
            )
            proposed_value = "RETRACTED" if operation == "RETRACT" else mutation.get("to")
            if _equivalent(current_value, proposed_value):
                equivalent_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "from": copy.deepcopy(current_value),
                        "to": copy.deepcopy(proposed_value),
                        "reason_code": "EQUIVALENT_EVENT",
                    }
                )
                continue
            if "from" in mutation and not _equivalent(current_value, mutation.get("from")):
                rejected_mutations.append(
                    {
                        "object_type": mutation["object_type"],
                        "object_id": object_id,
                        "field": field,
                        "from": copy.deepcopy(current_value),
                        "to": copy.deepcopy(proposed_value),
                        "reason_code": "PRIOR_VALUE_MISMATCH",
                    }
                )
                conflict_seed_ids.add(object_id)
                continue

            admitted = {
                "event_id": event["event_id"],
                "operation": operation,
                "object_type": mutation["object_type"],
                "object_id": object_id,
                "field": field,
                "from": copy.deepcopy(current_value),
                "to": copy.deepcopy(proposed_value),
                "unit": mutation.get("unit", item.get("unit")),
            }
            for metadata_field in (
                "policy_type",
                "materiality_fixture",
                "relation_type",
                "target_position_id",
            ):
                if mutation.get(metadata_field) is not None:
                    admitted[metadata_field] = copy.deepcopy(mutation[metadata_field])
            admitted_mutations.append(admitted)
            if operation == "RETRACT":
                runtime_flags.setdefault(object_id, {})["lifecycle"] = "RETRACTED"
                trigger_ids.add(object_id)
            elif operation == "ADD":
                rejected_mutations.append(
                    {
                        **admitted,
                        "reason_code": "DUPLICATE_OBJECT_ID",
                    }
                )
                admitted_mutations.pop()
            else:
                item[field] = copy.deepcopy(proposed_value)
                tolerance = _immediate_propagation_tolerance(
                    object_id, execution_mapping
                )
                below_tolerance = False
                if tolerance is not None and field == "value":
                    try:
                        below_tolerance = (
                            abs(Decimal(str(proposed_value)) - Decimal(str(current_value)))
                            < tolerance
                        )
                    except (InvalidOperation, TypeError, ValueError):
                        below_tolerance = False
                if below_tolerance:
                    sub_tolerance_mutations.append(
                        {
                            "event_id": event["event_id"],
                            "object_id": object_id,
                            "from": copy.deepcopy(current_value),
                            "to": copy.deepcopy(proposed_value),
                            "tolerance": _decimal_output(tolerance),
                            "reason_code": "BELOW_PROPAGATION_TOLERANCE_RECORDED",
                        }
                    )
                else:
                    trigger_ids.add(object_id)

        history_append.append(
            {
                "record_type": "EVENT_BATCH_PROCESSED",
                "batch_key": list(batch_key),
                "event_ids": sorted(event["event_id"] for event in active_events),
                "known_at": active_events[0]["known_at"],
                "effective_dates": sorted(
                    set(event["effective_date"] for event in active_events)
                ),
                "events": copy.deepcopy(active_events),
            }
        )

    preliminary_deltas = [
        {
            "object_type": mutation["object_type"],
            "object_id": mutation["object_id"],
            "field": mutation["field"],
            "from": mutation["from"],
            "to": mutation["to"],
            "status": "PROPOSED",
            "reason_code": "DIRECT_EVENT_MUTATION",
        }
        for mutation in admitted_mutations
    ] + copy.deepcopy(epistemic_candidate_deltas)
    rule_switch_evaluation = _evaluate_rule_switches(
        admitted_mutations, execution_mapping, registry
    )
    preliminary_materiality = _classify_materiality(
        preliminary_deltas,
        admitted_mutations,
        registry,
        contradictions,
        materiality_policy,
        state["K_t"],
        rule_switch_evaluation["results"],
    )
    cumulative_trigger_ids = {
        str(assessment["object_id"])
        for assessment in preliminary_materiality["assessments"]
        if assessment.get("reason_code") == "CUMULATIVE_THRESHOLD_CROSSED"
        and assessment.get("object_id") in registry
    }
    trigger_ids.update(cumulative_trigger_ids)

    if evaluation_request:
        trigger_ids.update(
            str(route["route_id"])
            for route in candidate_graph.get("support_routes", [])
            if isinstance(route, Mapping) and route.get("route_id")
        )

    impact_seed_ids = trigger_ids | conflict_seed_ids
    if impact_seed_ids:
        impact = compute_affected_set(candidate_graph, impact_seed_ids, execution_mapping)
    else:
        impact = {
            "affected_set": [],
            "visited_ids": [],
            "adjacency": _build_execution_adjacency(candidate_graph, execution_mapping),
            "registry": registry,
        }
    affected_ids = set(impact["visited_ids"])

    evaluation = _evaluate_routes_and_formulas(
        candidate_graph,
        execution_mapping,
        runtime_flags,
        affected_ids,
        evaluate_all_routes=evaluation_request or execution_mode == "GLOBAL_RECOMPUTE",
        evaluate_all_formulas=execution_mode == "GLOBAL_RECOMPUTE",
    )
    solver_scope = (
        set(impact["registry"])
        if execution_mode == "GLOBAL_RECOMPUTE"
        else affected_ids
    )
    numerical_evaluation = _evaluate_numeric_components(
        candidate_graph, execution_mapping, solver_scope
    )
    inverse_evaluation = _evaluate_inverse_solvers(
        candidate_graph, execution_mapping, solver_scope
    )

    blocked_ids: set[str] = set(conflict_seed_ids)
    for conflict_seed in conflict_seed_ids:
        queue = deque([conflict_seed])
        while queue:
            source = queue.popleft()
            for target, _relation, _edge_id in impact["adjacency"].get(source, []):
                if target in affected_ids and target not in blocked_ids:
                    blocked_ids.add(target)
                    queue.append(target)
    blocked_ids.update(evaluation["blocked_ids"])
    blocked_ids.update(rule_switch_evaluation["blocked_ids"])
    blocked_ids.update(numerical_evaluation["blocked_ids"])
    blocked_ids.update(inverse_evaluation["blocked_ids"])
    settled_ids = (
        set(trigger_ids)
        | set(evaluation["settled_ids"])
        | set(numerical_evaluation["settled_ids"])
        | set(inverse_evaluation["settled_ids"])
    )

    ordered_transitions = _ordered_components(
        affected_ids,
        impact["adjacency"],
        impact["registry"],
        settled_ids,
        blocked_ids,
    )
    for solver_result in numerical_evaluation["results"]:
        solver_members = set(solver_result["member_ids"])
        for component in ordered_transitions:
            if set(component["member_ids"]) != solver_members:
                continue
            component.update(
                {
                    "component_id": solver_result["component_id"],
                    "component_type": "NUMERICAL_SCC",
                    "result": (
                        "SETTLED"
                        if solver_result["outcome"] == "UNIQUE_SOLUTION"
                        else "BLOCKED"
                    ),
                    "iterations": solver_result["iterations"],
                    "residual": solver_result["residual"],
                    "reason_codes": (
                        []
                        if solver_result["outcome"] == "UNIQUE_SOLUTION"
                        else [solver_result["outcome"]]
                    ),
                }
            )
            break
    for solver_result in inverse_evaluation["results"]:
        for component in ordered_transitions:
            if solver_result["object_id"] not in component["member_ids"]:
                continue
            component.update(
                {
                    "component_id": solver_result["solver_id"],
                    "result": (
                        "SETTLED"
                        if solver_result["solver_outcome"] == "UNIQUE_OPTIMUM"
                        else "BLOCKED"
                    ),
                    "reason_codes": (
                        []
                        if solver_result["solver_outcome"] == "UNIQUE_OPTIMUM"
                        else [solver_result["solver_outcome"]]
                    ),
                }
            )
            break

    candidate_deltas = [
        {
            "object_type": mutation["object_type"],
            "object_id": mutation["object_id"],
            "field": mutation["field"],
            "from": mutation["from"],
            "to": mutation["to"],
            "status": "PROPOSED",
            "reason_code": "DIRECT_EVENT_MUTATION",
        }
        for mutation in admitted_mutations
    ]
    candidate_deltas.extend(
        {
            "object_type": update["object_type"],
            "object_id": update["object_id"],
            "field": update["field"],
            "from": update["from"],
            "to": update["to"],
            "status": "PROPOSED",
            "reason_code": "FORMULA_RECOMPUTATION",
        }
        for update in evaluation["formula_updates"]
        if not _equivalent(update["from"], update["to"])
    )
    candidate_deltas.extend(
        {
            "object_type": update["object_type"],
            "object_id": update["object_id"],
            "field": update["field"],
            "from": update["from"],
            "to": update["to"],
            "status": "PROPOSED",
            "reason_code": "INVERSE_SOLVER_RECOMPUTATION",
        }
        for update in inverse_evaluation["updates"]
        if not _equivalent(update["from"], update["to"])
    )
    candidate_deltas.extend(
        {
            "object_type": update["object_type"],
            "object_id": update["object_id"],
            "field": update["field"],
            "from": update["from"],
            "to": update["to"],
            "status": "PROPOSED",
            "reason_code": "NUMERICAL_SCC_RECOMPUTATION",
        }
        for update in numerical_evaluation["updates"]
        if not _equivalent(update["from"], update["to"])
    )
    candidate_deltas.extend(copy.deepcopy(epistemic_candidate_deltas))
    candidate_deltas.sort(
        key=lambda item: (item["object_type"], item["object_id"], item["field"])
    )

    materiality_assessment = _classify_materiality(
        candidate_deltas,
        admitted_mutations,
        impact["registry"],
        contradictions,
        materiality_policy,
        state["K_t"],
        rule_switch_evaluation["results"],
    )
    governance_plan = _govern_transition(
        normalized_events,
        candidate_deltas,
        materiality_assessment,
        authority_policy,
        contradictions,
    )

    recomputed_values = []
    for mutation in admitted_mutations:
        if mutation["field"] == "value":
            recomputed_values.append(
                {
                    "object_id": mutation["object_id"],
                    "old_value": mutation["from"],
                    "candidate_value": mutation["to"],
                    "unit": mutation.get("unit"),
                    "provisional": True,
                    "formula_or_solver_ref": None,
                    "materiality_class": materiality_assessment["overall_class"],
                }
            )
        elif mutation["operation"] == "ADD" and mutation.get("value") is not None:
            recomputed_values.append(
                {
                    "object_id": mutation["object_id"],
                    "old_value": None,
                    "candidate_value": mutation["value"],
                    "unit": mutation.get("unit"),
                    "provisional": True,
                    "formula_or_solver_ref": None,
                    "materiality_class": materiality_assessment["overall_class"],
                }
            )
    for update in evaluation["formula_updates"]:
        if not _equivalent(update["from"], update["to"]):
            recomputed_values.append(
                {
                    "object_id": update["object_id"],
                    "old_value": update["from"],
                    "candidate_value": update["to"],
                    "unit": update.get("unit"),
                    "provisional": True,
                    "formula_or_solver_ref": update.get("formula_id"),
                    "materiality_class": materiality_assessment["overall_class"],
                }
            )
    for update in numerical_evaluation["updates"]:
        if not _equivalent(update["from"], update["to"]):
            recomputed_values.append(
                {
                    "object_id": update["object_id"],
                    "old_value": update["from"],
                    "candidate_value": update["to"],
                    "unit": update.get("unit"),
                    "provisional": False,
                    "formula_or_solver_ref": update.get("formula_id"),
                    "materiality_class": materiality_assessment["overall_class"],
                }
            )
    for update in inverse_evaluation["updates"]:
        if not _equivalent(update["from"], update["to"]):
            recomputed_values.append(
                {
                    "object_id": update["object_id"],
                    "old_value": update["from"],
                    "candidate_value": update["to"],
                    "unit": update.get("unit"),
                    "provisional": False,
                    "formula_or_solver_ref": update.get("formula_id"),
                    "materiality_class": materiality_assessment["overall_class"],
                    "solver_outcome": update["solver_outcome"],
                    "binding_constraints": update["binding_constraints"],
                }
            )
    recomputed_values.sort(key=lambda item: item["object_id"])

    directly_changed_ids = {mutation["object_id"] for mutation in admitted_mutations} | {
        update["object_id"] for update in evaluation["formula_updates"]
    } | {update["object_id"] for update in numerical_evaluation["updates"]}
    directly_changed_ids.update(
        update["object_id"] for update in inverse_evaluation["updates"]
    )
    unchanged_objects = []
    for affected in impact["affected_set"]:
        if affected["object_id"] not in directly_changed_ids:
            if affected["object_id"] in blocked_ids:
                reason_code = "UPSTREAM_INPUT_BLOCKED"
                reason = "The object cannot settle because an upstream input is blocked."
            elif affected["object_id"] in settled_ids:
                reason_code = "EVALUATED_NO_STATE_CHANGE"
                reason = "The object was evaluated and its stored state did not change."
            else:
                reason_code = "REACHED_PENDING_EVALUATION"
                reason = (
                    "Reached by the conservative closure; no executable evaluator is "
                    "currently mapped for this object."
                )
            unchanged_objects.append(
                {
                    "object_type": affected["object_type"],
                    "object_id": affected["object_id"],
                    "reason_code": reason_code,
                    "reason": reason,
                }
            )
    for mutation in equivalent_mutations:
        object_id = mutation["object_id"]
        object_type = mutation["object_type"]
        if object_id not in impact["registry"] and object_type == "CLAIM":
            object_type = "COMPONENT"
        unchanged_objects.append(
            {
                "object_type": object_type,
                "object_id": object_id,
                "reason_code": mutation["reason_code"],
                "reason": "The event is already represented by the supplied state.",
            }
        )
    for mutation in non_applicable_mutations:
        unchanged_objects.append(
            {
                "object_type": mutation["object_type"],
                "object_id": mutation["object_id"],
                "reason_code": mutation["reason_codes"][0],
                "reason": "Definition, period, perimeter or unit is not applicable.",
            }
        )
    for combination in evaluation["combination_results"]:
        target_id = combination["position_id"]
        if combination["state"] == "TRUE" and any(
            result["state"] == "FALSE"
            for result in evaluation["route_results"]
            if result["target_position_id"] == target_id
        ):
            unchanged_objects.append(
                {
                    "object_type": "POSITION",
                    "object_id": target_id,
                    "reason_code": "ROUTE_SURVIVES_ALTERNATIVE",
                    "reason": "At least one sufficient independent route remains true.",
                }
            )
    unchanged_objects.sort(key=lambda item: (item["object_type"], item["object_id"], item["reason_code"]))

    human_stops = []
    blocked_components = []
    if conflicts:
        scope = sorted(f"{item['object_id']}.{item['field']}" for item in conflicts)
        human_stops.append(
            {
                "stop_id": "STOP-BATCH-CONFLICT",
                "object_or_component_id": "batch:" + hashlib.sha256(
                    "|".join(scope).encode("utf-8")
                ).hexdigest()[:12],
                "reason_code": "BATCH_VALUE_CONFLICT",
                "requested_action": "Resolve simultaneous incompatible values; no winner was selected.",
                "required_role": "PREPARER",
                "policy_rule_id": "KERNEL-BATCH-MERGE",
                "downstream_scope": sorted(blocked_ids),
            }
        )
    for mutation in rejected_mutations:
        human_stops.append(
            {
                "stop_id": "STOP-" + hashlib.sha256(
                    _canonical_json(mutation).encode("utf-8")
                ).hexdigest()[:12],
                "object_or_component_id": mutation["object_id"],
                "reason_code": mutation["reason_code"],
                "requested_action": "Correct or admit the mutation before replay.",
                "required_role": "PREPARER",
                "policy_rule_id": "KERNEL-INPUT-ADMISSION",
                "downstream_scope": sorted(blocked_ids),
            }
        )
    for combination in evaluation["combination_results"]:
        if combination["state"] == "UNKNOWN" and combination["invalid_route_ids"]:
            human_stops.append(
                {
                    "stop_id": "STOP-CIRCULAR-SUPPORT-" + combination["position_id"],
                    "object_or_component_id": combination["position_id"],
                    "reason_code": "CIRCULAR_SUPPORT",
                    "requested_action": "Provide a grounded non-circular support route.",
                    "required_role": "PROFESSIONAL_REVIEWER",
                    "policy_rule_id": "KERNEL-CIRCULAR-SUPPORT",
                    "downstream_scope": [combination["position_id"]],
                }
            )
    if conflict_seed_ids:
        blocked_components.append(
            {
                "component_id": "component:blocked-input",
                "member_ids": sorted(conflict_seed_ids),
                "reason_code": (
                    "BATCH_VALUE_CONFLICT" if conflicts else "UPSTREAM_INPUT_BLOCKED"
                ),
                "dependent_ids": sorted(blocked_ids - conflict_seed_ids),
                "missing_assumption_or_condition": "One admitted value per object field.",
            }
        )
    for route_id in evaluation["invalid_route_ids"]:
        blocked_components.append(
            {
                "component_id": f"component:circular:{route_id}",
                "member_ids": [route_id],
                "reason_code": "CIRCULAR_SUPPORT",
                "dependent_ids": [],
                "missing_assumption_or_condition": "A grounded non-circular support route.",
            }
        )
    for object_id in sorted(rule_switch_evaluation["blocked_ids"]):
        blocked_components.append(
            {
                "component_id": f"component:rule-switch:{object_id}",
                "member_ids": [object_id],
                "reason_code": "MISSING_RULE_PROVENANCE",
                "dependent_ids": [],
                "missing_assumption_or_condition": "A versioned rule source reference.",
            }
        )
    human_stops.extend(governance_plan["human_stops"])
    human_stops.extend(numerical_evaluation["human_stops"])
    human_stops.extend(inverse_evaluation["human_stops"])
    blocked_components.extend(governance_plan["blocked_components"])
    blocked_components.extend(numerical_evaluation["blocked_components"])
    blocked_components.extend(inverse_evaluation["blocked_components"])
    accumulation_audit_records = [
        {
            "record_type": "SUB_TOLERANCE_MOVEMENT_RECORDED",
            **copy.deepcopy(item),
        }
        for item in sub_tolerance_mutations
    ]
    history_append.extend(copy.deepcopy(accumulation_audit_records))
    history_append.extend(copy.deepcopy(governance_plan["audit_records"]))
    human_stops.sort(key=lambda item: item["stop_id"])
    blocked_components.sort(key=lambda item: item["component_id"])

    coverage_limits = _normalize_mapping_coverage_limits(execution_mapping)
    coverage_limits.extend(evaluation["coverage_limits"])
    coverage_limits.extend(rule_switch_evaluation["coverage_limits"])
    pending_scope = sorted(affected_ids - settled_ids - blocked_ids)
    if pending_scope:
        coverage_limits.append(
            {
                "limit_id": "CORE-001",
                "reason_code": "EVALUATION_STAGE_NOT_IMPLEMENTED",
                "scope_ids": pending_scope,
                "effect": (
                    "The engine computed the review perimeter but has no executable "
                    "evaluator for this remaining scope."
                ),
            }
        )
    coverage_limits.sort(key=lambda item: item["limit_id"])

    graph_hash = _sha256(current_graph)
    mapping_hash = _sha256(execution_mapping)
    solver_hash = _sha256(
        {
            "cyclic_component_solver_configs": execution_mapping.get(
                "cyclic_component_solver_configs", []
            ),
            "inverse_solver_configs": execution_mapping.get("inverse_solver_configs", []),
        }
    )
    normalized_execution_inputs = {
        "prior_state_hash": _sha256(state),
        "canonical_graph_hash": graph_hash,
        "materiality_policy_hash": _sha256(materiality_policy),
        "authority_policy_hash": _sha256(authority_policy),
        "execution_mapping_hash": mapping_hash,
        "solver_config_hash": solver_hash,
        "normalized_event_batch": normalized_events,
        "execution_mode": execution_mode,
    }
    replay_hash = _sha256(normalized_execution_inputs)

    settled_component_ids = [
        item["component_id"]
        for item in ordered_transitions
        if item["result"] == "SETTLED"
    ]
    unsettled_component_ids = [
        item["component_id"]
        for item in ordered_transitions
        if item["result"] != "SETTLED"
    ]
    candidate_status = (
        "NONE"
        if not affected_ids and (conflicts or rejected_mutations)
        else "PARTIAL"
        if unsettled_component_ids or blocked_components
        else "FULL"
    )
    if governance_plan["governance"]["gate_status"] == "BLOCKED":
        current_status = "BLOCKED"
    elif blocked_components:
        current_status = "PARTIAL" if settled_component_ids else "BLOCKED"
    elif governance_plan["governance"]["current_treatment"] == "AUTOMATIC_RECONCILIATION":
        current_status = "RECONCILED"
    elif governance_plan["human_stops"] or candidate_deltas:
        current_status = "REVIEW_PENDING"
    else:
        current_status = "RECONCILED"
    approved_status = (
        "AUTHORITY_PENDING"
        if governance_plan["governance"]["approved_treatment"] == "AUTHORITY_PENDING"
        else "UNCHANGED"
    )

    transition_output = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "execution_mode": execution_mode,
        "run_id": "run:" + replay_hash[7:19],
        "case_id": state["case_id"],
        "prior_state_id": state["state_id"],
        "policy_refs": {
            "materiality_policy_id": _policy_id(
                materiality_policy, "UNBOUND-MATERIALITY-POLICY"
            ),
            "authority_policy_id": _policy_id(
                authority_policy, "UNBOUND-AUTHORITY-POLICY"
            ),
            "canonical_graph_hash": graph_hash,
            "execution_mapping_hash": mapping_hash,
            "solver_config_hash": solver_hash,
        },
        "affected_set": impact["affected_set"],
        "ordered_transitions": ordered_transitions,
        "rule_switches": rule_switch_evaluation["results"],
        "recomputed_values": recomputed_values,
        "unchanged_objects": unchanged_objects,
        "human_stops": human_stops,
        "blocked_components": blocked_components,
        "coverage_limits": coverage_limits,
        "invariant_checks": [
            {
                "invariant_id": "CURRENT_INPUT_IMMUTABLE",
                "status": "PASS",
                "details": "All mutations were applied to a Candidate copy.",
            },
            {
                "invariant_id": "APPROVED_NOT_REWRITTEN",
                "status": "PASS",
                "details": "Approved snapshot is byte-equivalent to the prior state.",
            },
            {
                "invariant_id": "HISTORY_APPEND_ONLY",
                "status": "PASS",
                "details": "Prior history was not modified; new records are returned separately.",
            },
            {
                "invariant_id": "FULL_EVALUATION_COVERAGE",
                "status": "UNKNOWN" if pending_scope else "PASS",
                "details": (
                    "Some affected objects have no executable evaluator in this mapping."
                    if pending_scope
                    else "No downstream evaluation remained in this run."
                ),
            },
        ]
        + evaluation["invariant_checks"]
        + numerical_evaluation["invariant_checks"],
        "candidate_current_approved_delta": {
            "candidate": candidate_deltas,
            "current": governance_plan["current_deltas"],
            "approved": governance_plan["approved_deltas"],
        },
        "partial_settlement_status": {
            "candidate": candidate_status,
            "current": current_status,
            "approved": approved_status,
            "settled_component_ids": settled_component_ids,
            "unsettled_component_ids": unsettled_component_ids,
        },
        "replay_hash": replay_hash,
        "route_results": evaluation["route_results"],
        "support_combination_results": evaluation["combination_results"],
        "invalid_route_ids": evaluation["invalid_route_ids"],
        "numerical_solver_invocations": len(numerical_evaluation["results"]),
        "numerical_solver_results": numerical_evaluation["results"],
        "inverse_solver_invocations": len(inverse_evaluation["results"]),
        "inverse_solver_results": inverse_evaluation["results"],
        "global_block": False,
        "materiality_assessment": materiality_assessment,
        "governance": governance_plan["governance"],
        "governance_action_results": governance_plan["governance_action_results"],
        "audit_records": accumulation_audit_records + governance_plan["audit_records"],
        "accumulation": {
            "comparison_basis": "LAST_ABSORBED_CURRENT_K_T",
            "K_t": copy.deepcopy(state["K_t"]),
            "sub_tolerance_recorded": bool(sub_tolerance_mutations),
            "sub_tolerance_movements": copy.deepcopy(sub_tolerance_mutations),
            "cumulative_trigger_ids": sorted(cumulative_trigger_ids),
        },
    }
    transition_output["semantic_result_hash"] = _sha256(transition_output)

    candidate_state = {
        "schema_version": RUNTIME_STATE_VERSION,
        "state_id": "CANDIDATE:" + replay_hash[7:19],
        "case_id": state["case_id"],
        "current_graph": candidate_graph,
        "approved_snapshot": copy.deepcopy(state["approved_snapshot"]),
        "history": copy.deepcopy(state["history"]),
        "K_t": copy.deepcopy(state["K_t"]),
        "runtime_flags": runtime_flags,
        "pending_history_append": history_append,
        "candidate_graph_hash": _sha256(candidate_graph),
    }
    if state.get("pending_settlement"):
        candidate_state["pending_settlement"] = copy.deepcopy(
            state["pending_settlement"]
        )
    return {
        "candidate_state": candidate_state,
        "transition_output": transition_output,
        "normalized_event_batch": normalized_events,
        "history_append": history_append,
    }


def compare_incremental_global(
    prior_state: Mapping[str, Any],
    event_batch: Sequence[Mapping[str, Any]],
    execution_mapping: Mapping[str, Any],
    materiality_policy: Mapping[str, Any],
    authority_policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the incremental engine and its global oracle, then compare projection.

    The global run evaluates every mapped executable component, while comparison
    is deliberately restricted to the incremental affected set as required by
    the conformance contract.
    """

    incremental = apply_state_transition(
        prior_state,
        event_batch,
        execution_mapping,
        materiality_policy,
        authority_policy,
        execution_mode="INCREMENTAL_SCC",
    )
    global_run = apply_state_transition(
        prior_state,
        event_batch,
        execution_mapping,
        materiality_policy,
        authority_policy,
        execution_mode="GLOBAL_RECOMPUTE",
    )
    incremental_output = incremental["transition_output"]
    global_output = global_run["transition_output"]
    affected_ids = {
        str(item["object_id"]) for item in incremental_output["affected_set"]
    }

    def affected_deltas(output: Mapping[str, Any]) -> list[dict[str, Any]]:
        return sorted(
            (
                copy.deepcopy(item)
                for item in output["candidate_current_approved_delta"]["candidate"]
                if item["object_id"] in affected_ids
            ),
            key=lambda item: (item["object_type"], item["object_id"], item["field"]),
        )

    def affected_routes(output: Mapping[str, Any]) -> list[dict[str, Any]]:
        return sorted(
            (
                copy.deepcopy(item)
                for item in output.get("route_results", [])
                if item["route_id"] in affected_ids
                or item["target_position_id"] in affected_ids
            ),
            key=lambda item: item["route_id"],
        )

    current_graph = _coerce_runtime_state(prior_state)["current_graph"]
    current_registry = _object_registry(copy.deepcopy(current_graph))
    global_registry = _object_registry(global_run["candidate_state"]["current_graph"])
    unaffected_ids = set(current_registry) - affected_ids
    unaffected_equal = all(
        _canonical_json(current_registry[object_id]["object"])
        == _canonical_json(global_registry[object_id]["object"])
        for object_id in unaffected_ids
    )
    comparisons = {
        "candidate_values_equal": affected_deltas(incremental_output)
        == affected_deltas(global_output),
        "route_states_equal": affected_routes(incremental_output)
        == affected_routes(global_output),
        "canonical_axis_deltas_equal": [
            item
            for item in affected_deltas(incremental_output)
            if item["object_type"] == "POSITION"
        ]
        == [
            item
            for item in affected_deltas(global_output)
            if item["object_type"] == "POSITION"
        ],
        "materiality_classes_equal": incremental_output["materiality_assessment"]
        == global_output["materiality_assessment"],
        "human_stops_equal": incremental_output["human_stops"]
        == global_output["human_stops"],
        "blocked_components_equal": incremental_output["blocked_components"]
        == global_output["blocked_components"],
        "invariant_results_equal": incremental_output["invariant_checks"]
        == global_output["invariant_checks"],
        "unaffected_objects_byte_equivalent_after_normalization": unaffected_equal,
        "coverage_limits_equal": incremental_output["coverage_limits"]
        == global_output["coverage_limits"],
    }
    return {
        "equivalent": all(comparisons.values()),
        "comparisons": comparisons,
        "affected_ids": sorted(affected_ids),
        "incremental": incremental,
        "global": global_run,
    }
