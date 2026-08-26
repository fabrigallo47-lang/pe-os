"""Anto-side adapter template: PANTA engine output -> V17 transition projection."""
from __future__ import annotations

from typing import Any, Mapping


class TransitionContractError(ValueError):
    pass


def to_frontend_transition(output: Mapping[str, Any]) -> dict[str, Any]:
    """Map the frozen engine output without inferring business dispositions."""
    affected = output.get("affected_set")
    if not isinstance(affected, list):
        raise TransitionContractError("affected_set[] is required")
    return {
        "schema_version": "frontend-transition-projection/1.0",
        "run_id": output.get("run_id"),
        "case_id": output.get("case_id"),
        "prior_state_id": output.get("prior_state_id"),
        "candidate_state_id": output.get("candidate_state_id"),
        "status": output.get("partial_settlement_status", "UNKNOWN"),
        "affected_set": affected,
        "recomputed_values": output.get("recomputed_values", []),
        "unchanged_objects": output.get("unchanged_objects", []),
        "human_stops": output.get("human_stops", []),
        "blocked_components": output.get("blocked_components", []),
        "coverage_limits": output.get("coverage_limits", []),
        "artifact_change_sets": output.get("artifact_change_sets", []),
        "policy_result": output.get("policy_result"),
        "replay_hash": output.get("replay_hash"),
    }
