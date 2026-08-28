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
    candidate = _require_mapping(delta.get("candidate"), "candidate_current_approved_delta.candidate")
    partial = _require_mapping(raw["partial_settlement_status"], "partial_settlement_status")

    output = copy.deepcopy(dict(raw))
    output["affected_set"] = _normalise_affected(raw["affected_set"])
    output["candidate_state_id"] = str(raw.get("candidate_state_id") or candidate.get("state_id") or "")
    if not output["candidate_state_id"]:
        raise TransitionMappingError("candidate_state_id cannot be derived from candidate_current_approved_delta")
    output["as_of_state_id"] = str(raw.get("as_of_state_id") or raw["prior_state_id"])
    output["status"] = str(raw.get("status") or partial.get("candidate") or candidate.get("status") or "UNKNOWN")
    output["artifact_change_sets"] = copy.deepcopy(raw.get("artifact_change_sets") or [])
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
