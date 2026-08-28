"""Application boundary around the deterministic state-transition runtime.

The runtime consumes the *compiled Live Investment Case*, never ``graph.db``
or another raw extraction artifact.  This service owns filesystem loading and
atomic persistence so API and pipeline code do not reconstruct runtime output.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .runtime import apply_state_transition, build_runtime_state


class DynamicsBundleError(ValueError):
    """Raised when a runtime bundle is missing or internally inconsistent."""


REQUIRED_INPUTS = {
    "current_graph": "current_graph.json",
    "execution_mapping": "execution_mapping.json",
    "materiality_policy": "keystone_materiality_policy_v0.json",
    "authority_policy": "keystone_authority_matrix_v0.json",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DynamicsBundleError(f"missing dynamics input: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise DynamicsBundleError(
            f"invalid JSON in dynamics input {path.name}: {exc.msg}"
        ) from exc


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def load_bundle_inputs(bundle_dir: Path) -> dict[str, Any]:
    """Load one internally consistent compiler/runtime bundle."""

    bundle_dir = Path(bundle_dir)
    loaded = {
        key: _read_json(bundle_dir / filename)
        for key, filename in REQUIRED_INPUTS.items()
    }
    runtime_state_path = bundle_dir / "runtime_state.json"
    loaded["prior_state"] = (
        _read_json(runtime_state_path)
        if runtime_state_path.exists()
        else loaded["current_graph"]
    )
    return loaded


def load_event_batch(
    bundle_dir: Path,
    event_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve an event batch without inventing an event from UI prose.

    An API caller may submit ``event_batch`` or a complete ``event`` object.
    Otherwise the event must already exist as a JSON artifact in the compiled
    bundle and, when supplied, its id must match ``event_id`` exactly.
    """

    payload = payload or {}
    explicit_batch = payload.get("event_batch")
    if isinstance(explicit_batch, list):
        if not explicit_batch or not all(isinstance(item, Mapping) for item in explicit_batch):
            raise DynamicsBundleError("event_batch must contain one or more event objects")
        events = [dict(item) for item in explicit_batch]
    else:
        explicit_event = payload.get("event")
        if isinstance(explicit_event, Mapping):
            events = [dict(explicit_event)]
        else:
            events = []
            for path in sorted(Path(bundle_dir).glob("*event*.json")):
                candidate = _read_json(path)
                candidate_events = candidate if isinstance(candidate, list) else [candidate]
                for item in candidate_events:
                    if not isinstance(item, Mapping) or not item.get("event_id"):
                        continue
                    if event_id is None or str(item["event_id"]) == str(event_id):
                        events.append(dict(item))

    if not events:
        suffix = f" {event_id}" if event_id else ""
        raise DynamicsBundleError(f"no compiled event{suffix} found in the runtime bundle")
    if event_id is not None and any(str(item.get("event_id")) != str(event_id) for item in events):
        raise DynamicsBundleError("route event_id does not match the supplied event payload")
    return events


def _serializable_transition(result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_state = copy.deepcopy(dict(result["candidate_state"]))
    candidate_graph = copy.deepcopy(dict(candidate_state["current_graph"]))
    transition_output = copy.deepcopy(dict(result["transition_output"]))
    # The independent bundle contract expects these exact runtime products in
    # the flat output file.  They are copied, never recomputed here.
    transition_output["history_append"] = copy.deepcopy(result.get("history_append", []))
    transition_output["candidate_graph"] = candidate_graph
    return candidate_state, transition_output


def run_bundle_transition(
    bundle_dir: Path,
    event_batch: Sequence[Mapping[str, Any]],
    *,
    persist_outputs: bool = False,
) -> dict[str, Any]:
    """Execute the Candidate transition against the compiled bundle."""

    loaded = load_bundle_inputs(Path(bundle_dir))
    result = apply_state_transition(
        loaded["prior_state"],
        list(event_batch),
        loaded["execution_mapping"],
        loaded["materiality_policy"],
        loaded["authority_policy"],
    )
    candidate_state, transition_output = _serializable_transition(result)
    response = {
        **result,
        "candidate_state": candidate_state,
        "candidate_graph": candidate_state["current_graph"],
        "transition_output": transition_output,
    }
    if persist_outputs:
        bundle_dir = Path(bundle_dir)
        _atomic_write_json(bundle_dir / "candidate_graph.json", response["candidate_graph"])
        _atomic_write_json(bundle_dir / "candidate_state.json", candidate_state)
        _atomic_write_json(bundle_dir / "transition_output.json", transition_output)
    return response


def _absorbed_k_t(candidate_graph: Mapping[str, Any]) -> dict[str, Any]:
    """Close the cumulative-materiality bucket at the adopted Current."""

    return {
        str(node["model_node_id"]): copy.deepcopy(node.get("value"))
        for node in candidate_graph.get("model_nodes", [])
        if isinstance(node, Mapping) and node.get("model_node_id")
    }


def settle_candidate_state(
    bundle_dir: Path,
    candidate_state: Mapping[str, Any],
    history_append: Sequence[Mapping[str, Any]],
    *,
    current_state_id: str,
) -> dict[str, Any]:
    """Explicitly adopt a Candidate as Current and persist replay state.

    This function performs no authority decision.  The API must call it only
    after its human-review/authority checks have completed.
    """

    graph = copy.deepcopy(dict(candidate_state.get("current_graph", {})))
    if not graph:
        raise DynamicsBundleError("candidate_state.current_graph is required for settlement")
    history = copy.deepcopy(list(candidate_state.get("history", [])))
    history.extend(copy.deepcopy(list(history_append)))
    settled = build_runtime_state(
        graph,
        state_id=current_state_id,
        approved_snapshot=candidate_state.get("approved_snapshot", {}),
        history=history,
        k_t=_absorbed_k_t(graph),
    )
    bundle_dir = Path(bundle_dir)
    _atomic_write_json(bundle_dir / "current_graph.json", graph)
    _atomic_write_json(bundle_dir / "runtime_state.json", settled)
    _atomic_write_json(bundle_dir / "candidate_graph.json", {})
    (bundle_dir / "candidate_state.json").unlink(missing_ok=True)
    return settled
