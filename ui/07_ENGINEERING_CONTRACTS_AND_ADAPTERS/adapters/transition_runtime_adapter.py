#!/usr/bin/env python3
"""Pure PANTA frozen-engine-output → frontend transition projection mapping.

The frozen Transition Engine v1.1 contract contains 18 required top-level
fields. PANTA's integration boundary adds ``source_event_id`` so the frontend
projection can bind the deterministic result back to its admitted event. The
adapter therefore validates and maps a 19-field integration envelope without
inventing economics, materiality, authority or settlement state.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Callable, Mapping

FROZEN_REQUIRED_FIELDS = (
    "schema_version",
    "engine_version",
    "run_id",
    "case_id",
    "prior_state_id",
    "policy_refs",
    "affected_set",
    "ordered_transitions",
    "rule_switches",
    "recomputed_values",
    "unchanged_objects",
    "human_stops",
    "blocked_components",
    "coverage_limits",
    "invariant_checks",
    "candidate_current_approved_delta",
    "partial_settlement_status",
    "replay_hash",
)
INTEGRATION_REQUIRED_FIELDS = FROZEN_REQUIRED_FIELDS + ("source_event_id",)


class TransitionMappingError(ValueError):
    """Raised when the engine output cannot be mapped without invention."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TransitionMappingError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TransitionMappingError(f"{name} must be an array")
    return value


def _normalise_affected(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        item = _require_mapping(raw, f"affected_set[{index}]")
        object_id = item.get("object_id") or item.get("target_ref") or item.get("model_node_id") or item.get("id")
        if not object_id:
            raise TransitionMappingError(f"affected_set[{index}] lacks object_id")
        order = item["order"] if item.get("order") is not None else index
        result.append(
            {
                **copy.deepcopy(dict(item)),
                "order": int(order),
                "object_id": str(object_id),
                "label": str(item.get("label") or item.get("name") or object_id),
                "disposition": str(item.get("disposition") or item.get("behavior") or item.get("transition_type") or "RECOMPUTES"),
                "before": item.get("before", item.get("old_value", item.get("old"))),
                "after": item.get("after", item.get("new_value", item.get("new"))),
                "explanation": str(item.get("explanation") or item.get("reason") or item.get("detail") or ""),
                "source_trace": item.get("source_trace") or item.get("source_ref"),
            }
        )
    return sorted(result, key=lambda item: (item["order"], item["object_id"]))


_NON_ATTESTABLE_STOP_REASONS = {
    "BATCH_VALUE_CONFLICT",
    "CIRCULAR_SUPPORT",
    "MISSING_RULE_PROVENANCE",
    "NON_WAIVABLE_AXIOM",
    "UPSTREAM_INPUT_BLOCKED",
}


def _normalise_human_stops(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        item = _require_mapping(raw, f"human_stops[{index}]")
        stop_id = str(item.get("stop_id") or "")
        object_id = str(
            item.get("object_id")
            or item.get("object_or_component_id")
            or item.get("component_id")
            or ""
        )
        if not stop_id or not object_id:
            raise TransitionMappingError(
                f"human_stops[{index}] lacks stop_id or object/component identity"
            )
        required_role = str(item.get("required_role") or "UNSPECIFIED_REVIEWER")
        reason_code = str(item.get("reason_code") or "HUMAN_REVIEW_REQUIRED")
        requested_action = str(
            item.get("requested_action")
            or item.get("reason")
            or reason_code
        )
        reason = str(item.get("reason") or requested_action or reason_code)
        attestable = item.get("attestable")
        if not isinstance(attestable, bool):
            attestable = (
                required_role != "PREPARER"
                and reason_code not in _NON_ATTESTABLE_STOP_REASONS
            )
        if item.get("resolution_kind"):
            resolution_kind = str(item["resolution_kind"])
        elif reason_code == "NON_WAIVABLE_AXIOM":
            resolution_kind = "NON_WAIVABLE_BLOCK"
        elif not attestable:
            resolution_kind = "INPUT_OR_MODEL_CORRECTION"
        else:
            resolution_kind = "AUTHORITY_ATTESTATION"
        result.append(
            {
                **copy.deepcopy(dict(item)),
                "stop_id": stop_id,
                "object_id": object_id,
                "reason_code": reason_code,
                "requested_action": requested_action,
                "reason": reason,
                "required_role": required_role,
                # These compatibility fallbacks make the application contract
                # renderable; the server remains authoritative for permission.
                "required_authority_level": str(
                    item.get("required_authority_level") or required_role
                ),
                "authority_verb": str(
                    item.get("authority_verb") or "RESOLVE_HUMAN_STOP"
                ),
                "status": str(item.get("status") or "OPEN"),
                "downstream_scope": list(item.get("downstream_scope") or []),
                "resolution_kind": resolution_kind,
                "attestable": attestable,
            }
        )
    return result


def _normalise_blocked_components(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        item = _require_mapping(raw, f"blocked_components[{index}]")
        component_id = str(item.get("component_id") or "")
        if not component_id:
            raise TransitionMappingError(
                f"blocked_components[{index}] lacks component_id"
            )
        reason_code = str(item.get("reason_code") or "BLOCKED")
        resolution = item.get("resolvable_by")
        if resolution is None:
            resolution = item.get("missing_assumption_or_condition")
        result.append(
            {
                **copy.deepcopy(dict(item)),
                "component_id": component_id,
                "member_ids": list(item.get("member_ids") or []),
                "reason_code": reason_code,
                "reason": str(item.get("reason") or resolution or reason_code),
                "downstream_scope": list(
                    item.get("downstream_scope")
                    or item.get("dependent_ids")
                    or []
                ),
                "resolvable_by": None if resolution is None else str(resolution),
                "status": str(item.get("status") or "BLOCKED"),
            }
        )
    return result


def _normalise_change_sets(
    raw: Mapping[str, Any],
    candidate_deltas: list[Mapping[str, Any]],
    human_stops: list[Mapping[str, Any]],
    blocked_components: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    supplied = raw.get("change_sets") or raw.get("artifact_change_sets") or []
    if supplied:
        supplied = _require_list(supplied, "change_sets")
        result: list[dict[str, Any]] = []
        for index, value in enumerate(supplied):
            item = _require_mapping(value, f"change_sets[{index}]")
            change_set_id = str(
                item.get("change_set_id")
                or item.get("artifact_id")
                or item.get("change_id")
                or item.get("id")
                or ""
            )
            if not change_set_id:
                raise TransitionMappingError(f"change_sets[{index}] lacks an id")
            changes = copy.deepcopy(list(item.get("changes") or []))
            result.append(
                {
                    **copy.deepcopy(dict(item)),
                    "change_set_id": change_set_id,
                    "artifact_id": change_set_id,
                    "title": str(item.get("title") or item.get("label") or change_set_id),
                    "status": str(item.get("status") or "PREPARED"),
                    "changes": changes,
                    "object_ids": list(item.get("object_ids") or []),
                    "component_ids": list(item.get("component_ids") or []),
                    "blocking_stop_ids": list(item.get("blocking_stop_ids") or []),
                    "blocked_component_ids": list(
                        item.get("blocked_component_ids") or []
                    ),
                }
            )
        return result

    ordered = raw.get("ordered_transitions") or []
    result = []
    for delta in candidate_deltas:
        object_id = str(delta.get("object_id") or "")
        if not object_id:
            continue
        component_ids = [
            str(item.get("component_id"))
            for item in ordered
            if object_id in (item.get("member_ids") or []) and item.get("component_id")
        ]
        blocked_ids = [
            str(item["component_id"])
            for item in blocked_components
            if object_id in (item.get("member_ids") or [])
            or object_id in (item.get("downstream_scope") or [])
        ]
        stop_ids = [
            str(item["stop_id"])
            for item in human_stops
            if object_id in (item.get("downstream_scope") or [])
            or object_id == item.get("object_id")
        ]
        before = delta.get("before", delta.get("from", delta.get("old_value")))
        after = delta.get("after", delta.get("to", delta.get("new_value")))
        result.append(
            {
                "change_set_id": object_id,
                # Compatibility alias retained until the existing Action Frontier
                # is renamed from artifact-specific terminology.
                "artifact_id": object_id,
                "title": f"{str(delta.get('object_type') or 'OBJECT')} {object_id}",
                "status": "BLOCKED" if blocked_ids else "PREPARED",
                "object_ids": [object_id],
                "component_ids": component_ids,
                "blocking_stop_ids": stop_ids,
                "blocked_component_ids": blocked_ids,
                "changes": [
                    {
                        "change_id": str(delta.get("change_id") or object_id),
                        "object_id": object_id,
                        "field": delta.get("field"),
                        "label": str(delta.get("label") or delta.get("field") or object_id),
                        "before": copy.deepcopy(before),
                        "after": copy.deepcopy(after),
                        "reason_code": delta.get("reason_code"),
                    }
                ],
            }
        )
    return result


def map_engine_output(engine_output: Mapping[str, Any]) -> dict[str, Any]:
    """Map one frozen engine result into the browser transition projection.

    This is a pure function: it does not read fixtures, mutate the input, call a
    server, calculate economics, resolve authority, or settle state.
    """
    raw = _require_mapping(engine_output, "engine_output")
    missing = [field for field in INTEGRATION_REQUIRED_FIELDS if field not in raw]
    if missing:
        raise TransitionMappingError("Missing frozen/integration field(s): " + ", ".join(missing))

    for field in (
        "affected_set",
        "ordered_transitions",
        "rule_switches",
        "recomputed_values",
        "unchanged_objects",
        "human_stops",
        "blocked_components",
        "coverage_limits",
        "invariant_checks",
    ):
        _require_list(raw[field], field)
    delta = _require_mapping(raw["candidate_current_approved_delta"], "candidate_current_approved_delta")
    candidate_value = delta.get("candidate")
    if isinstance(candidate_value, Mapping):
        candidate_metadata: Mapping[str, Any] = candidate_value
        candidate_deltas: list[Mapping[str, Any]] = []
    elif isinstance(candidate_value, list):
        candidate_metadata = {}
        candidate_deltas = [
            _require_mapping(item, f"candidate_current_approved_delta.candidate[{index}]")
            for index, item in enumerate(candidate_value)
        ]
    else:
        raise TransitionMappingError(
            "candidate_current_approved_delta.candidate must be an object or array"
        )
    partial = _require_mapping(raw["partial_settlement_status"], "partial_settlement_status")

    output = copy.deepcopy(dict(raw))
    output["affected_set"] = _normalise_affected(raw["affected_set"])
    candidate_state_id = str(
        raw.get("candidate_state_id") or candidate_metadata.get("state_id") or ""
    )
    if candidate_state_id:
        output["candidate_state_id"] = candidate_state_id
    else:
        output.pop("candidate_state_id", None)
    output["as_of_state_id"] = str(raw.get("as_of_state_id") or raw["prior_state_id"])
    output["status"] = str(
        raw.get("status")
        or partial.get("candidate")
        or candidate_metadata.get("status")
        or "UNKNOWN"
    )
    human_stops = _normalise_human_stops(raw["human_stops"])
    blocked_components = _normalise_blocked_components(raw["blocked_components"])
    change_sets = _normalise_change_sets(
        raw, candidate_deltas, human_stops, blocked_components
    )
    output["human_stops"] = human_stops
    output["blocked_components"] = blocked_components
    output["change_sets"] = change_sets
    output["artifact_change_sets"] = copy.deepcopy(change_sets)
    output["invariant_checks"] = [
        {
            **copy.deepcopy(dict(item)),
            "check_id": str(item.get("check_id") or item.get("invariant_id") or ""),
        }
        for item in raw["invariant_checks"]
    ]
    output["policy_result"] = copy.deepcopy(raw.get("policy_result") or {})
    output["mapping_contract"] = {
        "name": "frozen-engine-output-to-frontend-transition",
        "version": "20.0.0",
        "frozen_required_field_count": len(FROZEN_REQUIRED_FIELDS),
        "integration_required_field_count": len(INTEGRATION_REQUIRED_FIELDS),
        "source_event_id": raw["source_event_id"],
        "pure_function": True,
    }
    return output


def run_transition(engine_or_output: Mapping[str, Any] | Callable[..., Mapping[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Invoke a supplied engine callable or map an already-produced output."""
    output = engine_or_output(*args, **kwargs) if callable(engine_or_output) else engine_or_output
    return map_engine_output(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Frozen engine output JSON")
    parser.add_argument("output", type=Path, help="Frontend transition projection JSON")
    args = parser.parse_args()
    mapped = map_engine_output(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(mapped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
