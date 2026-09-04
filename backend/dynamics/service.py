"""Application boundary around the deterministic state-transition runtime.

The runtime consumes the *compiled Live Investment Case*, never ``graph.db``
or another raw extraction artifact.  This service owns filesystem loading and
atomic persistence so API and pipeline code do not reconstruct runtime output.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import os
import tempfile
import threading
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

_SETTLEMENT_LOCK = threading.RLock()


def _settlement_serialized(function):
    """Serialize in-process compare-and-swap checks with their file commit."""

    @functools.wraps(function)
    def locked(*args: Any, **kwargs: Any) -> Any:
        with _SETTLEMENT_LOCK:
            return function(*args, **kwargs)

    return locked


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


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


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


@_settlement_serialized
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


@_settlement_serialized
def settle_candidate_state(
    bundle_dir: Path,
    candidate_state: Mapping[str, Any],
    history_append: Sequence[Mapping[str, Any]],
    *,
    current_state_id: str,
    settlement_graph: Mapping[str, Any] | None = None,
    expected_prior_state_id: str | None = None,
    expected_prior_graph_hash: str | None = None,
    expected_candidate_state_id: str | None = None,
    expected_candidate_state_hash: str | None = None,
    expected_candidate_graph_hash: str | None = None,
    settlement_runtime_flags: Mapping[str, Mapping[str, Any]] | None = None,
    pending_settlement: Mapping[str, Any] | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Explicitly adopt a Candidate as Current and persist replay state.

    This function performs no authority decision.  The API must call it only
    after its human-review/authority checks have completed.
    """

    bundle_dir = Path(bundle_dir)
    journal_path = bundle_dir / "settlement_journal.json"
    if journal_path.exists():
        journal = _read_json(journal_path)
        if str(journal.get("current_state_id") or "") != str(current_state_id):
            raise DynamicsBundleError(
                "another interrupted settlement owns the runtime bundle"
            )
        expected_pairs = (
            ("prior_state_id", expected_prior_state_id),
            ("prior_graph_hash", expected_prior_graph_hash),
            ("candidate_state_id", expected_candidate_state_id),
            ("candidate_state_hash", expected_candidate_state_hash),
            ("candidate_graph_hash", expected_candidate_graph_hash),
        )
        if any(
            expected is not None and str(journal.get(field)) != str(expected)
            for field, expected in expected_pairs
        ):
            raise DynamicsBundleError(
                "interrupted settlement journal does not match this prepared run"
            )
        target_graph = journal.get("target_graph")
        target_state = journal.get("target_runtime_state")
        if not isinstance(target_graph, Mapping) or not isinstance(target_state, Mapping):
            raise DynamicsBundleError("interrupted settlement journal is incomplete")
        current_before_recovery = _read_json(bundle_dir / "current_graph.json")
        runtime_before_recovery = (
            _read_json(bundle_dir / "runtime_state.json")
            if (bundle_dir / "runtime_state.json").exists()
            else {}
        )
        allowed_graph_hashes = {
            str(journal.get("prior_graph_hash") or ""),
            _canonical_hash(target_graph),
        }
        if _canonical_hash(current_before_recovery) not in allowed_graph_hashes:
            raise DynamicsBundleError(
                "interrupted settlement cannot recover over an unrelated Current graph"
            )
        runtime_id = str(runtime_before_recovery.get("state_id") or "")
        if runtime_id and runtime_id not in {
            str(journal.get("prior_state_id") or ""),
            str(current_state_id),
        }:
            raise DynamicsBundleError(
                "interrupted settlement cannot recover over an unrelated runtime state"
            )
        candidate_graph_path = bundle_dir / "candidate_graph.json"
        candidate_state_path = bundle_dir / "candidate_state.json"
        if not candidate_graph_path.exists():
            raise DynamicsBundleError(
                "interrupted settlement Candidate graph has disappeared"
            )
        persisted_candidate_graph = _read_json(candidate_graph_path)
        candidate_graph_safe = _canonical_hash(persisted_candidate_graph) in {
            str(journal.get("candidate_graph_hash") or ""),
            _canonical_hash({}),
        }
        candidate_state_safe = not candidate_state_path.exists()
        if candidate_state_path.exists():
            candidate_state_safe = (
                _canonical_hash(_read_json(candidate_state_path))
                == str(journal.get("candidate_state_hash") or "")
            )
        if not candidate_graph_safe or not candidate_state_safe:
            raise DynamicsBundleError(
                "interrupted settlement Candidate artifacts were modified"
            )

        try:
            _atomic_write_json(bundle_dir / "current_graph.json", target_graph)
            _atomic_write_json(bundle_dir / "runtime_state.json", target_state)
            _atomic_write_json(candidate_graph_path, {})
            candidate_state_path.unlink(missing_ok=True)
            _atomic_write_json(bundle_dir / "transition_output.json", {})
            ledger_event = journal.get("ledger_event")
            if isinstance(ledger_event, Mapping):
                _append_settlement_event_to_ledger(target_graph, ledger_event)
            else:
                # Backward-compatible recovery for a journal created before the
                # durable outbox event became part of settlement-journal/1.1.
                _append_settlement_to_ledger(
                    target_graph,
                    target_state,
                    history_append,
                    actor_id=actor_id,
                )
            journal_path.unlink(missing_ok=True)
        except OSError as exc:
            raise DynamicsBundleError(
                "settlement recovery was interrupted; retry the same request"
            ) from exc
        return copy.deepcopy(dict(target_state))

    persisted_graph = _read_json(bundle_dir / "current_graph.json")
    runtime_state_path = bundle_dir / "runtime_state.json"
    persisted_state = (
        _read_json(runtime_state_path)
        if runtime_state_path.exists()
        else build_runtime_state(persisted_graph)
    )
    runtime_graph = persisted_state.get("current_graph")
    if not isinstance(runtime_graph, Mapping):
        raise DynamicsBundleError("runtime_state.current_graph is required for settlement")
    if _canonical_hash(runtime_graph) != _canonical_hash(persisted_graph):
        raise DynamicsBundleError(
            "runtime_state and current_graph disagree; settlement refused"
        )
    if (
        expected_prior_state_id is not None
        and str(persisted_state.get("state_id")) != str(expected_prior_state_id)
    ):
        raise DynamicsBundleError(
            "stale Candidate: Current state no longer matches prior_state_id"
        )
    if (
        expected_prior_graph_hash is not None
        and _canonical_hash(persisted_graph) != str(expected_prior_graph_hash)
    ):
        raise DynamicsBundleError(
            "stale Candidate: Current graph no longer matches the Candidate base"
        )

    if expected_candidate_state_id is not None:
        supplied_candidate_id = str(candidate_state.get("state_id") or "")
        if supplied_candidate_id != str(expected_candidate_state_id):
            raise DynamicsBundleError("Candidate state_id does not match the prepared run")
        persisted_candidate_path = bundle_dir / "candidate_state.json"
        if not persisted_candidate_path.exists():
            raise DynamicsBundleError("persisted Candidate state is missing")
        persisted_candidate = _read_json(persisted_candidate_path)
        if str(persisted_candidate.get("state_id") or "") != supplied_candidate_id:
            raise DynamicsBundleError("persisted Candidate does not match the prepared run")

    if expected_candidate_state_hash is not None:
        if _canonical_hash(candidate_state) != str(expected_candidate_state_hash):
            raise DynamicsBundleError("Candidate state envelope does not match the prepared run")
        persisted_candidate_path = bundle_dir / "candidate_state.json"
        if not persisted_candidate_path.exists():
            raise DynamicsBundleError("persisted Candidate state is missing")
        persisted_candidate = _read_json(persisted_candidate_path)
        if _canonical_hash(persisted_candidate) != str(expected_candidate_state_hash):
            raise DynamicsBundleError("persisted Candidate state envelope was modified")

    candidate_graph = candidate_state.get("current_graph", {})
    if expected_candidate_graph_hash is not None:
        if _canonical_hash(candidate_graph) != str(expected_candidate_graph_hash):
            raise DynamicsBundleError("Candidate graph hash does not match the prepared run")
        persisted_candidate_graph_path = bundle_dir / "candidate_graph.json"
        if not persisted_candidate_graph_path.exists():
            raise DynamicsBundleError("persisted Candidate graph is missing")
        persisted_candidate_graph = _read_json(persisted_candidate_graph_path)
        if _canonical_hash(persisted_candidate_graph) != str(expected_candidate_graph_hash):
            raise DynamicsBundleError("persisted Candidate graph is internally inconsistent")

    if str(candidate_state.get("case_id") or "") != str(persisted_state.get("case_id") or ""):
        raise DynamicsBundleError("Candidate case_id does not match the persisted Current")
    for immutable_field in ("approved_snapshot", "history", "K_t"):
        if candidate_state.get(immutable_field) != persisted_state.get(immutable_field):
            raise DynamicsBundleError(
                f"Candidate {immutable_field} diverges from its persisted Current base"
            )

    graph_source = settlement_graph if settlement_graph is not None else candidate_graph
    graph = copy.deepcopy(dict(graph_source))
    if not graph:
        raise DynamicsBundleError("candidate_state.current_graph is required for settlement")
    if graph.get("case_id") != persisted_state.get("case_id"):
        raise DynamicsBundleError("Candidate case_id does not match the persisted Current")
    history = copy.deepcopy(list(candidate_state.get("history", [])))
    history.extend(copy.deepcopy(list(history_append)))
    settled = build_runtime_state(
        graph,
        state_id=current_state_id,
        approved_snapshot=candidate_state.get("approved_snapshot", {}),
        history=history,
        k_t=_absorbed_k_t(graph),
        runtime_flags=(
            settlement_runtime_flags
            if settlement_runtime_flags is not None
            else candidate_state.get("runtime_flags", {})
        ),
        pending_settlement=(
            pending_settlement
            if pending_settlement is not None
            else candidate_state.get("pending_settlement")
        ),
    )
    ledger_event = _settlement_ledger_event(
        graph,
        settled,
        history_append,
        actor_id=actor_id,
    )
    journal = {
        "schema_version": "settlement-journal/1.1",
        "status": "SETTLING",
        "current_state_id": current_state_id,
        "prior_state_id": persisted_state.get("state_id"),
        "prior_graph_hash": _canonical_hash(persisted_graph),
        "candidate_state_id": candidate_state.get("state_id"),
        "candidate_state_hash": _canonical_hash(candidate_state),
        "candidate_graph_hash": _canonical_hash(candidate_graph),
        "target_graph": graph,
        "target_runtime_state": settled,
        # Durable outbox payload. The recovery marker is removed only after
        # this event is present in the canonical case ledger.
        "ledger_event": ledger_event,
    }
    try:
        _atomic_write_json(journal_path, journal)
    except OSError as exc:
        raise DynamicsBundleError(
            "settlement journal could not be created; Current is unchanged"
        ) from exc
    try:
        _atomic_write_json(bundle_dir / "current_graph.json", graph)
        _atomic_write_json(bundle_dir / "runtime_state.json", settled)
        _atomic_write_json(bundle_dir / "candidate_graph.json", {})
        (bundle_dir / "candidate_state.json").unlink(missing_ok=True)
        _atomic_write_json(bundle_dir / "transition_output.json", {})
        _append_settlement_event_to_ledger(graph, ledger_event)
        journal_path.unlink(missing_ok=True)
    except OSError as exc:
        raise DynamicsBundleError(
            "settlement commit was interrupted; retry the same idempotent request"
        ) from exc
    return settled


def _settlement_ledger_event(
    graph: Mapping[str, Any],
    settled: Mapping[str, Any],
    history_append: Sequence[Mapping[str, Any]],
    *,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Build the immutable event placed in the settlement outbox."""

    case_id = str(graph.get("case_id") or settled.get("case_id") or "")
    if not case_id:
        raise DynamicsBundleError(
            "Current is settled but has no case_id, so the audit row cannot be written"
        )

    from datetime import datetime, timezone

    state_id = str(settled.get("state_id") or "")
    graph_hash = _canonical_hash(graph)
    return {
        # Derived from what was settled, so re-appending the same settlement is a
        # no-op and a retried request cannot double-count it. Hashed here rather
        # than through ledger_store.compute_event_id, whose parameters name an
        # extraction — passing a settlement through them would make the field
        # names lie about what produced the id.
        "event_id": _canonical_hash(
            {"kind": "CASE_SETTLED", "case_id": case_id,
             "state_id": state_id, "graph_hash": graph_hash}
        ),
        "event": "CASE_SETTLED",
        "effective_date": str(graph.get("canonical_as_of") or "")[:10] or "1970-01-01",
        "known_at": datetime.now(timezone.utc).isoformat(),
        "actor_id": str(actor_id or "PANTA_SYSTEM"),
        "source_ids": [],
        "trigger_claim_ids": [],
        "mutations": [],
        "state_id": state_id,
        "graph_hash": graph_hash,
        "history_append": copy.deepcopy(list(history_append)),
    }


def _append_settlement_event_to_ledger(
    graph: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    """Append an outbox event and surface a precise post-commit failure."""

    from .runtime import ledger_store

    case_id = str(graph.get("case_id") or "")
    state_id = str(event.get("state_id") or "UNKNOWN")
    if not case_id:
        raise DynamicsBundleError(
            "Current is settled but has no case_id, so the audit row cannot be written"
        )
    try:
        ledger_store.append_event(case_id, event)
    except Exception as exc:                       # noqa: BLE001 — surfaced verbatim below
        # Current is already settled and correct. Say exactly that, so nobody reads
        # this as a settlement failure and re-runs one that already happened.
        raise DynamicsBundleError(
            f"Current is settled ({state_id}) but its ledger row failed to append: {exc}. "
            "Do not re-settle; re-appending is idempotent."
        ) from exc


def _append_settlement_to_ledger(
    graph: Mapping[str, Any],
    settled: Mapping[str, Any],
    history_append: Sequence[Mapping[str, Any]],
    *,
    actor_id: str | None = None,
) -> None:
    """Backward-compatible helper used by legacy settlement recovery."""

    event = _settlement_ledger_event(
        graph,
        settled,
        history_append,
        actor_id=actor_id,
    )
    _append_settlement_event_to_ledger(graph, event)
