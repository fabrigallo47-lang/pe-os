#!/usr/bin/env python3
"""Append-only event ledger for durable PANTA runtime history.

Current and candidate runtime files are useful projections, but they cannot
answer what the system knew at an earlier point in time after they have been
replaced.  This module keeps the submitted event envelopes as the durable
record.  It deliberately does not interpret transition-engine policy: replay
only provides a transparent, deterministic materialization of mutations.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


# Anchored to the repository, not the working directory. A relative path here
# silently forks the ledger: the API serving from the repo root and a script run
# from backend/dynamics would each append to their own file, and an append-only
# audit record that quietly splits in two is worse than one that fails loudly.
# Tests override this attribute to redirect into a temp tree.
PIPELINE_OUT = Path(__file__).resolve().parents[3] / "pipeline_out"


ADMISSION_MODES = frozenset(
    {"AUTO_POLICY", "HUMAN_CONFIRMED", "AUTHORITY_RECORDED"}
)


def _canonical_json(value: Any) -> str:
    """Match the transition engine's canonical representation for stable hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _case_path(case_id: str) -> Path:
    if not isinstance(case_id, str) or not case_id or Path(case_id).name != case_id:
        raise ValueError("case_id must be a non-empty path component")
    return PIPELINE_OUT / "cases" / case_id / "ledger.jsonl"


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    # The event schema permits ISO datetimes without an offset. Treat those as
    # UTC so a valid historical record cannot make an as-of query incomparable.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _read_all(case_id: str) -> list[dict[str, Any]]:
    ledger_path = _case_path(case_id)
    if not ledger_path.exists():
        return []

    events: list[dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON in ledger for case {case_id!r}, line {line_number}"
                ) from exc
            if not isinstance(event, dict):
                raise ValueError(
                    f"ledger event for case {case_id!r}, line {line_number} must be an object"
                )
            events.append(event)
    _validate_ledger_chain(case_id, events)
    return events


def _ledger_hash(event: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "ledger_hash"}
    return _sha256(payload)


def _previous_hash(event: Mapping[str, Any]) -> str:
    """Return the chain identity of a protected or pre-chain legacy row."""

    value = event.get("ledger_hash")
    return str(value) if value else _sha256(event)


def _validate_ledger_chain(case_id: str, events: list[dict[str, Any]]) -> None:
    """Fail closed when any hash-chained row was altered or reordered.

    Rows written before ``journal-ledger/1.0`` remain readable.  The first new
    row anchors itself to the canonical hash of the last legacy row, after
    which every row must carry a continuous sequence and hash.
    """

    protected_started = False
    prior_hash: str | None = None
    for index, event in enumerate(events, start=1):
        ledger_hash = event.get("ledger_hash")
        if ledger_hash is None:
            if protected_started:
                raise ValueError(
                    f"ledger chain for case {case_id!r} contains an unprotected row after protected history"
                )
            prior_hash = _previous_hash(event)
            continue
        protected_started = True
        if event.get("ledger_sequence") != index:
            raise ValueError(
                f"ledger chain for case {case_id!r} has an invalid sequence at row {index}"
            )
        if event.get("previous_ledger_hash") != prior_hash:
            raise ValueError(
                f"ledger chain for case {case_id!r} is discontinuous at row {index}"
            )
        if ledger_hash != _ledger_hash(event):
            raise ValueError(
                f"ledger chain for case {case_id!r} failed integrity at row {index}"
            )
        prior_hash = str(ledger_hash)


def compute_event_id(source_version_id: Any, extractor_version: Any, manifest_hash: Any) -> str:
    """Return the stable event-level idempotency key for one extraction result."""

    return _sha256(
        {
            "source_version_id": source_version_id,
            "extractor_version": extractor_version,
            "manifest_hash": manifest_hash,
        }
    )


def validate_admission_mode(value: Any) -> str:
    """Validate and return one canonical institutional admission mode.

    There is intentionally no fallback here.  Inferring ``AUTO_POLICY`` from a
    missing field, or a human mode merely from the presence of an actor, would
    make the ledger assert an admission path that it cannot prove.
    """

    if not isinstance(value, str) or value not in ADMISSION_MODES:
        allowed = ", ".join(sorted(ADMISSION_MODES))
        raise ValueError(f"admission_mode must be one of: {allowed}")
    return value


def append_event(case_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
    """Append one event unless its event id is already present in this case ledger."""

    if not isinstance(event, Mapping):
        raise ValueError("event must be a mapping")
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event.event_id must be a non-empty string")

    admission_mode = event.get("admission_mode")
    if event.get("event") == "CLAIM_ADMISSION" and admission_mode is None:
        raise ValueError("CLAIM_ADMISSION event.admission_mode is required")
    if admission_mode is not None:
        validate_admission_mode(admission_mode)

    ledger_path = _case_path(case_id)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ledger_path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        # The duplicate check and append form one inter-process critical
        # section. Without the advisory file lock, two workers can both observe
        # absence and append the same event id.
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        existing_events = _read_all(case_id)
        if any(existing.get("event_id") == event_id for existing in existing_events):
            return {
                "appended": False,
                "event_id": event_id,
                "reason": "event_id already present",
            }

        # The kernel's third temporal field. effective_at is when the fact held,
        # known_at when the institution learned it, recorded_at when the ledger
        # actually took it. Server-owned chain fields make later editing or
        # reordering detectable and cannot be spoofed by a caller.
        stored = {
            key: value
            for key, value in dict(event).items()
            if key not in {
                "recorded_at",
                "ledger_sequence",
                "previous_ledger_hash",
                "ledger_hash",
            }
        }
        stored["recorded_at"] = datetime.now(timezone.utc).isoformat()
        stored["ledger_sequence"] = len(existing_events) + 1
        stored["previous_ledger_hash"] = (
            _previous_hash(existing_events[-1]) if existing_events else None
        )
        stored["ledger_hash"] = _ledger_hash(stored)

        # Serialize while holding the lock but before changing the file: a
        # failure to encode never leaves a partial row.
        line = (_canonical_json(stored) + "\n").encode("utf-8")
        written = 0
        while written < len(line):
            count = os.write(descriptor, line[written:])
            if count <= 0:
                raise OSError("ledger append wrote an incomplete event line")
            written += count
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return {"appended": True, "event_id": event_id, "reason": None}


def read_ledger(case_id: str, as_of: str | None = None) -> list[dict[str, Any]]:
    """Return events in append order, optionally bounded by when they became known."""

    events = _read_all(case_id)
    if as_of is None:
        return events
    cutoff = _parse_datetime(as_of, "as_of")
    return [
        event
        for event in events
        if _parse_datetime(event.get("known_at"), "event.known_at") <= cutoff
    ]


def replay(case_id: str, as_of: str | None = None) -> dict[str, Any]:
    """Materialize ledger mutations in append order without engine-level adjudication."""

    events = read_ledger(case_id, as_of)
    objects: dict[str, dict[str, dict[str, Any]]] = {}
    for event in events:
        for mutation in event.get("mutations", []):
            if not isinstance(mutation, Mapping):
                raise ValueError(f"event {event.get('event_id')!r} has a non-object mutation")
            object_type = mutation.get("object_type")
            object_id = mutation.get("object_id")
            if not isinstance(object_type, str) or not isinstance(object_id, str):
                raise ValueError(
                    f"event {event.get('event_id')!r} mutation needs object_type and object_id"
                )

            object_state = objects.setdefault(object_type, {}).setdefault(object_id, {})
            for key, value in mutation.items():
                if key not in {"operation", "object_type", "object_id", "field", "from", "to"}:
                    object_state[key] = copy.deepcopy(value)
            field = mutation.get("field")
            if isinstance(field, str) and field:
                object_state[field] = copy.deepcopy(mutation.get("to"))
            elif "to" in mutation:
                object_state["value"] = copy.deepcopy(mutation["to"])
            elif mutation.get("operation") == "RETRACT":
                object_state["lifecycle"] = "RETRACTED"

    result = {
        "case_id": case_id,
        "as_of": as_of,
        "event_count": len(events),
        "objects": objects,
        "last_event_id": events[-1].get("event_id") if events else None,
    }
    result["replay_hash"] = _sha256(result)
    return result
