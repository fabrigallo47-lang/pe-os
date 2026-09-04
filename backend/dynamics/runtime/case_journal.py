#!/usr/bin/env python3
"""Canonical case-journal projection and deterministic change summaries.

The runtime ledger, institutional vault events and immutable graph archive are
durable for different reasons.  This module gives them one read contract.  It
contains no filesystem or HTTP code so the same rules can be reused by the API,
tests and future exporters without creating another source of truth.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


JOURNAL_SCHEMA_VERSION = "case-journal/1.0"
JOURNAL_EVENT_SCHEMA_VERSION = "case-journal-event/1.0"
CHANGE_RULES_VERSION = "journal-change-rules/1.1"


_COLLECTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("claims", ("claim_id", "stable_id", "id"), "CLAIM"),
    ("benchmark_validation_claims", ("claim_id", "stable_id", "id"), "CLAIM"),
    ("case_positions", ("position_id", "id"), "CASE_POSITION"),
    ("stated_positions", ("stated_position_id", "position_id", "id"), "STATED_POSITION"),
    ("model_nodes", ("model_node_id", "id"), "MODEL_NODE"),
    ("support_routes", ("support_route_id", "route_id", "id"), "SUPPORT_ROUTE"),
    ("position_dependencies", ("edge_id", "dependency_id", "id"), "POSITION_DEPENDENCY"),
    ("claim_position_edges", ("edge_id", "id"), "CLAIM_POSITION_EDGE"),
    ("position_model_bindings", ("binding_id", "id"), "POSITION_MODEL_BINDING"),
    ("questions", ("question_id", "id"), "QUESTION"),
    ("unknowns", ("unknown_id", "id"), "UNKNOWN"),
    ("conditions", ("condition_id", "id"), "CONDITION"),
    ("coverage_gaps", ("coverage_gap_id", "gap_id", "condition_id", "id"), "COVERAGE_GAP"),
    ("artifacts", ("artifact_id", "id"), "ARTIFACT"),
)

_STATUS_FIELDS = (
    "status",
    "status_at_ic",
    "decision_status",
    "decision_status_at_ic",
    "epistemic_status",
    "epistemic_status_at_ic",
    "freshness_status",
    "freshness_status_at_ic",
    "outcome_status",
    "outcome_status_at_ic",
    "model_binding_status",
    "coverage_state",
    "lifecycle",
    "strength",
    "state",
    "review_status",
    "status_at_opening",
)

# These fields describe serialization or observation mechanics, not the
# institutional meaning of a graph object.  They remain present in the raw
# before/after payload for audit, but cannot manufacture a semantic delta.
_NON_SEMANTIC_FIELDS = frozenset({
    "_meta",
    "created_at",
    "updated_at",
    "recorded_at",
    "known_at",
    "generated_at",
    "ingested_at",
    "computed_at",
    "last_seen_at",
    "last_modified_at",
    "version_id",
    "state_id",
    "graph_hash",
    "projection_hash",
})

# Order in these relationship fields is representational.  Reordering them
# must not look like a change in the investment case.
_UNORDERED_LIST_FIELDS = frozenset({
    "artifact_ids",
    "bears_on",
    "binding_ids",
    "claim_ids",
    "condition_ids",
    "depends_on",
    "evidence_ids",
    "labels",
    "model_node_ids",
    "object_ids",
    "question_ids",
    "related_ids",
    "source_ids",
    "support_route_ids",
    "supporting_claim_ids",
    "tags",
    "unknown_ids",
    "workstream_ids",
})

# Some relationship generators retain a human-readable edge_id that is not
# globally unique (for example, a shortened claim prefix).  Their endpoints
# are the durable semantic identity; relation changes remain UPDATED rather
# than becoming an artificial remove/add pair.
_COMPOUND_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "position_dependencies": ("from_position_id", "to_position_id"),
    "claim_position_edges": ("claim_id", "position_id"),
    "position_model_bindings": ("position_id", "model_node_id"),
}

_LIFECYCLE_OBJECTS = frozenset({"QUESTION", "UNKNOWN", "CONDITION", "COVERAGE_GAP"})

_GENERIC_STATUS_SCORE = {
    "FAILED": -4,
    "REJECTED": -4,
    "RETRACTED": -4,
    "BROKEN": -4,
    "BLOCKED": -3,
    "STALE": -2,
    "CONTESTED": -2,
    "WEAK": -2,
    "UNRESOLVED": -1,
    "AT_RISK": -1,
    "UNBOUND": -1,
    "OPEN": 0,
    "PENDING": 0,
    "UNKNOWN": 0,
    "UNEXAMINED": 0,
    "PARTIAL": 1,
    "ACTIVE": 1,
    "ADMITTED": 2,
    "ACCEPTED": 2,
    "BOUND": 2,
    "CURRENT": 2,
    "COVERED": 2,
    "VERIFIED": 3,
    "ESTABLISHED": 3,
    "STRONG": 3,
    "RESOLVED": 4,
    "CLOSED": 4,
    "PASS": 4,
    "COMPLETE": 4,
    "COMPLETED": 4,
    "SETTLED": 5,
}

_STATUS_FIELD_SCORES = {
    "decision_status": {
        "REJECTED": -3,
        "PENDING": 0,
        "ACCEPTED_WITH_CONDITIONS": 1,
        "ACCEPTED": 2,
    },
    "epistemic_status": {
        "RETRACTED": -4,
        "REJECTED": -4,
        "CONTESTED": -2,
        "OPEN": -1,
        "UNEXAMINED": 0,
        "UNKNOWN": 0,
        "ASSERTED": 1,
        "ADMITTED": 2,
        "ACCEPTED": 2,
        "OBSERVED": 3,
        "DERIVED": 3,
        "ATTESTED": 3,
        "VERIFIED": 4,
        "ESTABLISHED": 4,
    },
    "freshness_status": {"STALE": -1, "CURRENT": 1},
    "outcome_status": {
        "FALSIFIED": -3,
        "MATERIALIZED": -2,
        "NOT_TESTED": 0,
        "PARTIALLY_HELD": 1,
        "RECOVERED_AFTER_FAILURE": 1,
        "HELD": 2,
    },
    "model_binding_status": {
        "BROKEN": -3,
        "UNBOUND": -2,
        "PARTIAL": 0,
        "ACTIVE": 1,
        "BOUND": 2,
    },
    "coverage_state": {
        "GAP": -2,
        "UNCOVERED": -2,
        "PARTIAL": 0,
        "COVERED": 2,
    },
}

_OPEN_STATUSES = {
    "OPEN", "PENDING", "BLOCKED", "UNRESOLVED", "AT_RISK", "CONTESTED",
}
_CLOSED_STATUSES = {
    "RESOLVED", "CLOSED", "COMPLETE", "COMPLETED", "SETTLED", "VERIFIED",
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _token(value: Any, fallback: str = "INSTITUTIONAL_EVENT") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_")
    return text.upper() or fallback


def _instant(value: Any, *, end_of_day: bool = False) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw += "T23:59:59.999999Z" if end_of_day else "T00:00:00Z"
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO temporal value: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _strings(*values: Any) -> list[str]:
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        items = value if isinstance(value, (list, tuple, set)) else [value]
        for item in items:
            if isinstance(item, Mapping):
                item = item.get("id") or item.get("object_id") or item.get("workstream_id")
            text = str(item or "").strip()
            if text and text not in output:
                output.append(text)
    return output


def _journal_kind(event_type: str, raw_kind: Any) -> str:
    supplied = _token(raw_kind, "")
    if supplied:
        return supplied
    if event_type in {"CLAIM_ADMISSION", "EVIDENCE_ADMITTED", "SOURCE", "INGEST"}:
        return "EVIDENCE"
    if event_type in {"CASE_SETTLED", "SETTLEMENT"}:
        return "SETTLEMENT"
    if event_type in {"AUTHORITY", "IC_RECORD", "DECISION"}:
        return "DECISION"
    if event_type in {"NOTE", "ANNOTATION", "CLAIM_REVIEW"}:
        return "ANNOTATION"
    return event_type


def _phase(kind: str, event_type: str) -> str:
    value = kind or event_type
    if value in {"ORIGIN", "MEETING", "ACCESS", "LEGAL", "ENGAGEMENT"}:
        return "ORIGINATION"
    if value in {"EVIDENCE", "SOURCE", "INGEST", "CLAIM_ADMISSION", "QUESTION"}:
        return "DILIGENCE"
    if value in {"DECISION", "AUTHORITY", "IC_RECORD", "HUMAN_STOP"}:
        return "DECISION"
    if value in {"EXECUTION", "MISSION", "PROCESS"}:
        return "EXECUTION"
    if value in {"SETTLEMENT", "CASE_SETTLED", "CASE_VERSION"}:
        return "CASE_EVOLUTION"
    if value in {"ANNOTATION", "NOTE", "CLAIM_REVIEW"}:
        return "ANNOTATIONS"
    return "CASE_EVOLUTION"


def normalize_event(case_id: str, raw: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    """Normalize a ledger or vault event without changing its original payload."""

    original_id = str(raw.get("event_id") or raw.get("id") or "").strip()
    if not original_id:
        original_id = _canonical_hash(raw)
    event_type = _token(raw.get("event") or raw.get("type") or raw.get("kind"))
    kind = _journal_kind(event_type, raw.get("kind"))
    known_at = str(raw.get("known_at") or raw.get("timestamp") or raw.get("recorded_at") or "")
    if not known_at:
        raise ValueError(f"journal event {original_id!r} has no known_at")
    _instant(known_at)
    effective_raw = str(raw.get("effective_date") or known_at[:10])
    effective_at = _instant(effective_raw)
    effective_date = effective_at.date().isoformat() if effective_at else known_at[:10]
    recorded_at = str(raw.get("recorded_at") or raw.get("created_at") or known_at)
    _instant(recorded_at)

    mutations = raw.get("mutations") if isinstance(raw.get("mutations"), list) else []
    mutation_object_ids = [
        item.get("object_id")
        for item in mutations
        if isinstance(item, Mapping) and item.get("object_id")
    ]
    object_ids = _strings(
        raw.get("object_ids"),
        raw.get("settled_object_ids"),
        raw.get("settled-object-ids"),
        raw.get("object_id"),
        raw.get("claim_id"),
        raw.get("trigger_claim_ids"),
        mutation_object_ids,
    )
    workstream_ids = _strings(
        raw.get("workstream_ids"), raw.get("workstreams"), raw.get("workstream")
    )
    actor_id = str(
        raw.get("actor_id")
        or raw.get("actor")
        or raw.get("written_by")
        or raw.get("written-by")
        or "PANTA_SYSTEM"
    )
    actor_source = "DECLARED" if any(
        raw.get(field) for field in ("actor_id", "actor", "written_by", "written-by")
    ) else "INFERRED_SYSTEM"
    state_before = raw.get("source_state_id") or raw.get("prior_state_id")
    state_after = (
        raw.get("result_state_id")
        or raw.get("current_state_id")
        or raw.get("state_id")
    )
    source_event_id = raw.get("source_event_id")
    correlation_ids = _strings(
        source_event_id,
        raw.get("settles"),
        raw.get("run_id"),
        state_before,
        state_after,
    )
    label = str(
        raw.get("label")
        or raw.get("title")
        or event_type.replace("_", " ").title()
    )
    detail = str(
        raw.get("detail")
        or raw.get("source_passage")
        or raw.get("reason")
        or ""
    )
    journal_id = _canonical_hash(
        {"case_id": case_id, "source": source, "event_id": original_id}
    )
    return {
        "schema_version": JOURNAL_EVENT_SCHEMA_VERSION,
        "journal_id": journal_id,
        "event_id": original_id,
        "case_id": case_id,
        "event_type": event_type,
        "kind": kind,
        "phase": _phase(kind, event_type),
        "label": label,
        "detail": detail,
        "actor_id": actor_id,
        "actor_label": str(raw.get("actor_label") or actor_id),
        "actor_source": actor_source,
        "effective_date": effective_date,
        "known_at": known_at,
        "recorded_at": recorded_at,
        "object_ids": object_ids,
        "workstream_ids": workstream_ids,
        "source_ids": _strings(raw.get("source_ids"), raw.get("source_id")),
        "run_id": raw.get("run_id"),
        "state_before": state_before,
        "state_after": state_after,
        "correlation_ids": correlation_ids,
        "source": source,
        "integrity": {
            "ledger_sequence": raw.get("ledger_sequence"),
            "previous_ledger_hash": raw.get("previous_ledger_hash"),
            "ledger_hash": raw.get("ledger_hash"),
            "source_hash": _canonical_hash(raw),
        },
    }


def merge_events(
    case_id: str,
    *,
    runtime_events: Iterable[Mapping[str, Any]] = (),
    vault_events: Iterable[Mapping[str, Any]] = (),
    authority_events: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return one stable, correlation-preserving journal timeline."""

    normalized = [
        normalize_event(case_id, event, source=source)
        for source, records in (
            ("RUNTIME_LEDGER", runtime_events),
            ("VAULT_EVENT", vault_events),
            ("AUTHORITY_LEDGER", authority_events),
        )
        for event in records
    ]
    unique = {event["journal_id"]: event for event in normalized}
    return sorted(
        unique.values(),
        key=lambda event: (
            _instant(event["known_at"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            _instant(event["recorded_at"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            event["journal_id"],
        ),
    )


def _collection_value(graph: Mapping[str, Any], collection: str) -> Any:
    if collection == "case_positions":
        return graph.get("case_positions", graph.get("positions", []))
    return graph.get(collection, [])


def _record_id(
    record: Mapping[str, Any],
    id_fields: tuple[str, ...],
    *,
    collection: str,
) -> str:
    compound_fields = _COMPOUND_ID_FIELDS.get(collection, ())
    compound_values = [
        str(record.get(field) or "").strip() for field in compound_fields
    ]
    if compound_values and all(compound_values):
        return f"{collection}:" + "→".join(compound_values)
    return next(
        (
            str(record[field]).strip()
            for field in id_fields
            if str(record.get(field) or "").strip()
        ),
        "",
    )


def _index_records(
    graph: Mapping[str, Any],
    collection: str,
    id_fields: tuple[str, ...],
    *,
    snapshot_role: str,
) -> dict[str, dict[str, Any]]:
    """Index a graph collection without silently losing malformed objects."""

    value = _collection_value(graph, collection)
    if value is None:
        return {}
    if isinstance(value, Mapping):
        records = list(value.items())
    elif isinstance(value, (list, tuple)):
        records = [(None, item) for item in value]
    else:
        raise ValueError(
            f"graph identity error: {snapshot_role}.{collection} must be an array or object map"
        )

    indexed: dict[str, dict[str, Any]] = {}
    for position, (map_key, record) in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(
                f"graph identity error: {snapshot_role}.{collection}[{position}] must be an object"
            )
        explicit_id = _record_id(record, id_fields, collection=collection)
        map_id = str(map_key).strip() if map_key is not None else ""
        object_id = explicit_id or map_id
        if not object_id:
            expected = ", ".join(id_fields)
            raise ValueError(
                f"graph identity error: {snapshot_role}.{collection}[{position}] "
                f"has no stable id ({expected})"
            )
        if object_id in indexed:
            raise ValueError(
                f"graph identity error: duplicate id {object_id!r} in "
                f"{snapshot_role}.{collection}"
            )
        indexed[object_id] = copy.deepcopy(dict(record))
    return indexed


def _semantic_value(value: Any, *, field_name: str | None = None) -> Any:
    """Return the comparison form while preserving raw records for audit."""

    if isinstance(value, Mapping):
        return {
            str(key): _semantic_value(item, field_name=str(key))
            for key, item in value.items()
            if str(key) not in _NON_SEMANTIC_FIELDS
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_semantic_value(item) for item in value]
        if isinstance(value, (set, frozenset)) or field_name in _UNORDERED_LIST_FIELDS:
            items.sort(
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            )
        return items
    return value


def _semantic_record(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    semantic = _semantic_value(record)
    return semantic if isinstance(semantic, dict) else {}


def _status(record: Mapping[str, Any] | None) -> str:
    if not record:
        return ""
    for field in _STATUS_FIELDS:
        if record.get(field) is not None:
            return _token(record[field], "")
    return ""


def _status_dimension(field: str) -> str:
    return field.removesuffix("_at_ic")


def _status_score(object_type: str, field: str, status: str) -> int | None:
    dimension = _status_dimension(field)
    if dimension in _STATUS_FIELD_SCORES:
        return _STATUS_FIELD_SCORES[dimension].get(status)
    if object_type in _LIFECYCLE_OBJECTS:
        lifecycle_scores = {
            **_GENERIC_STATUS_SCORE,
            "FAILED": -4,
            "BLOCKED": -3,
            "AT_RISK": -2,
            "CONTESTED": -1,
            "UNRESOLVED": -1,
            "OPEN": 0,
            "PENDING": 0,
            "ACTIVE": 0,
            "RESOLVED": 3,
            "VERIFIED": 3,
            "CLOSED": 4,
            "COMPLETE": 4,
            "COMPLETED": 4,
            "SETTLED": 5,
        }
        return lifecycle_scores.get(status)
    return _GENERIC_STATUS_SCORE.get(status)


def _status_directions(
    object_type: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> tuple[list[int], list[str]]:
    """Evaluate every comparable status dimension, not just the first one."""

    directions: list[int] = []
    descriptions: list[str] = []
    for field in _STATUS_FIELDS:
        before_raw = (before or {}).get(field)
        after_raw = (after or {}).get(field)
        if before_raw is None or after_raw is None:
            continue
        before_status = _token(before_raw, "")
        after_status = _token(after_raw, "")
        if before_status == after_status:
            continue
        before_score = _status_score(object_type, field, before_status)
        after_score = _status_score(object_type, field, after_status)
        if before_score is None or after_score is None or before_score == after_score:
            continue
        direction = 1 if after_score > before_score else -1
        directions.append(direction)
        descriptions.append(f"{field} {before_status}→{after_status}")
    return directions, descriptions


def _workstream(record: Mapping[str, Any] | None) -> str:
    if not record:
        return "UNASSIGNED"
    bears_on = _strings(record.get("bears_on"))
    value = (
        record.get("workstream_id")
        or record.get("workstream")
        or record.get("question_id")
        or record.get("owner_area")
        or record.get("pillar")
        or record.get("sheet")
        or record.get("topic")
        or (bears_on[0] if bears_on else None)
        or record.get("target_position_id")
    )
    return str(value or "UNASSIGNED")


def _label(record: Mapping[str, Any] | None, object_id: str) -> str:
    if not record:
        return object_id
    return str(
        record.get("label")
        or record.get("title")
        or record.get("statement")
        or record.get("question")
        or record.get("proposition")
        or record.get("description")
        or record.get("name")
        or object_id
    )


def _trend(
    object_type: str,
    change_type: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> tuple[str, str | None, str]:
    before_status = _status(before)
    after_status = _status(after)
    if change_type == "ADDED":
        if object_type == "CLAIM_POSITION_EDGE":
            relation = _token((after or {}).get("relation_type"), "")
            if relation == "SUPPORTS":
                return "ADVANCED", None, "a new supporting relationship entered the case"
            if relation == "CONTRADICTS":
                return "REGRESSED", None, "a new contradictory relationship entered the case"
        if object_type in {"CLAIM", "SUPPORT_ROUTE", "ARTIFACT"}:
            return "ADVANCED", None, "new knowledge or support entered the case"
        if object_type in _LIFECYCLE_OBJECTS and after_status in _OPEN_STATUSES:
            return "REGRESSED", "OPENED", "a new unresolved item entered the case"
        if object_type in _LIFECYCLE_OBJECTS and after_status in _CLOSED_STATUSES:
            return "CHANGED", None, "an already-closed item entered the graph; no progress inferred"
        return "CHANGED", None, "a new case object was introduced without directional evidence"
    if change_type == "REMOVED":
        explicit = _token((before or {}).get("change_direction"), "")
        if explicit in {"ADVANCED", "IMPROVED", "POSITIVE"}:
            return "ADVANCED", None, "the removed object declares a positive change direction"
        if explicit in {"REGRESSED", "DETERIORATED", "NEGATIVE"}:
            return "REGRESSED", None, "the removed object declares a negative change direction"
        if object_type in _LIFECYCLE_OBJECTS:
            return (
                "CHANGED",
                None,
                "the item disappeared without a terminal transition; resolution is not inferred",
            )
        if object_type in {"CLAIM", "SUPPORT_ROUTE"}:
            return "REGRESSED", None, "knowledge or support left the active case"
        if object_type == "CLAIM_POSITION_EDGE":
            relation = _token((before or {}).get("relation_type"), "")
            if relation == "SUPPORTS":
                return "REGRESSED", None, "a supporting relationship left the case"
            if relation == "CONTRADICTS":
                return "ADVANCED", None, "a contradictory relationship left the case"
        return "CHANGED", None, "a case object was removed without directional evidence"

    explicit = _token((after or {}).get("change_direction"), "")
    explicit_direction = (
        1 if explicit in {"ADVANCED", "IMPROVED", "POSITIVE"}
        else -1 if explicit in {"REGRESSED", "DETERIORATED", "NEGATIVE"}
        else 0
    )
    status_directions, status_descriptions = _status_directions(
        object_type, before, after
    )
    observed_directions = set(status_directions)
    if explicit_direction and observed_directions and (
        -explicit_direction in observed_directions or len(observed_directions) > 1
    ):
        return (
            "CHANGED",
            None,
            "declared direction conflicts with status movement: "
            + ", ".join(status_descriptions),
        )
    if len(observed_directions) > 1:
        return (
            "CHANGED",
            None,
            "status dimensions moved in different directions: "
            + ", ".join(status_descriptions),
        )

    movement = None
    if before_status in _OPEN_STATUSES and after_status in _CLOSED_STATUSES:
        movement = "CLOSED"
    elif before_status in _CLOSED_STATUSES and after_status in _OPEN_STATUSES:
        movement = "OPENED"

    if explicit_direction:
        return (
            "ADVANCED" if explicit_direction > 0 else "REGRESSED",
            movement,
            "the object declares a positive change direction"
            if explicit_direction > 0
            else "the object declares a negative change direction",
        )
    if observed_directions:
        direction = next(iter(observed_directions))
        return (
            "ADVANCED" if direction > 0 else "REGRESSED",
            movement,
            "status improved: " + ", ".join(status_descriptions)
            if direction > 0
            else "status deteriorated: " + ", ".join(status_descriptions),
        )

    preference = _token(
        (after or {}).get("preferred_direction")
        or (before or {}).get("preferred_direction"),
        "",
    )
    before_value = (before or {}).get("value")
    after_value = (after or {}).get("value")
    if (
        preference in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}
        and isinstance(before_value, (int, float))
        and isinstance(after_value, (int, float))
        and before_value != after_value
    ):
        improved = after_value > before_value
        if preference == "LOWER_IS_BETTER":
            improved = not improved
        return (
            ("ADVANCED", None, f"value moved in the declared {preference.lower()} direction")
            if improved
            else ("REGRESSED", None, f"value moved against the declared {preference.lower()} direction")
        )
    return "CHANGED", None, "content changed without a declared positive or negative direction"


def compare_graphs(
    baseline: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare two immutable graph states by stable object identity."""

    if baseline is not None and not isinstance(baseline, Mapping):
        raise ValueError("graph identity error: baseline graph must be an object")
    if current is not None and not isinstance(current, Mapping):
        raise ValueError("graph identity error: current graph must be an object")
    baseline = baseline or {}
    current = current or {}
    changes: list[dict[str, Any]] = []
    for collection, id_fields, object_type in _COLLECTIONS:
        before_index = _index_records(
            baseline,
            collection,
            id_fields,
            snapshot_role="baseline",
        )
        after_index = _index_records(
            current,
            collection,
            id_fields,
            snapshot_role="current",
        )
        for object_id in sorted(before_index.keys() | after_index.keys()):
            before = before_index.get(object_id)
            after = after_index.get(object_id)
            semantic_before = _semantic_record(before)
            semantic_after = _semantic_record(after)
            before_hash = (
                _canonical_hash(semantic_before) if semantic_before is not None else None
            )
            after_hash = (
                _canonical_hash(semantic_after) if semantic_after is not None else None
            )
            if before is not None and after is not None and before_hash == after_hash:
                continue
            change_type = "ADDED" if before is None else "REMOVED" if after is None else "UPDATED"
            changed_fields = sorted(
                set((semantic_before or {}).keys()) | set((semantic_after or {}).keys())
            ) if change_type == "UPDATED" else []
            if change_type == "UPDATED":
                changed_fields = [
                    field for field in changed_fields
                    if (semantic_before or {}).get(field) != (semantic_after or {}).get(field)
                ]
            trend, movement, reason = _trend(object_type, change_type, before, after)
            active = after or before
            before_workstream = _workstream(before) if before is not None else None
            after_workstream = _workstream(after) if after is not None else None
            changes.append({
                "change_id": _canonical_hash({
                    "collection": collection,
                    "object_id": object_id,
                    "before": before_hash,
                    "after": after_hash,
                }),
                "object_id": object_id,
                "object_type": object_type,
                "collection": collection,
                "label": _label(active, object_id),
                "workstream_id": _workstream(active),
                "before_workstream_id": before_workstream,
                "after_workstream_id": after_workstream,
                "change_type": change_type,
                "trend": trend,
                "movement": movement,
                "reason": reason,
                "before_status": _status(before) or None,
                "after_status": _status(after) or None,
                "changed_fields": changed_fields,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "before": before,
                "after": after,
            })

    counts = Counter(change["trend"].lower() for change in changes)
    movement_counts = Counter(
        str(change["movement"]).lower() for change in changes if change["movement"]
    )
    workstreams: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for change in changes:
        workstreams[change["workstream_id"]].append(change)
    workstream_summaries = []
    for workstream_id, items in sorted(workstreams.items()):
        item_counts = Counter(item["trend"].lower() for item in items)
        workstream_summaries.append({
            "workstream_id": workstream_id,
            "change_count": len(items),
            "advanced": item_counts["advanced"],
            "regressed": item_counts["regressed"],
            "changed": item_counts["changed"],
            "net_direction": (
                "ADVANCED" if item_counts["advanced"] > item_counts["regressed"]
                else "REGRESSED" if item_counts["regressed"] > item_counts["advanced"]
                else "MIXED_OR_NEUTRAL"
            ),
            "change_ids": [item["change_id"] for item in items],
        })
    return {
        "rules_version": CHANGE_RULES_VERSION,
        "change_count": len(changes),
        "advanced": counts["advanced"],
        "regressed": counts["regressed"],
        "changed": counts["changed"],
        "opened": movement_counts["opened"],
        "closed": movement_counts["closed"],
        "workstreams": workstream_summaries,
        "changes": changes,
    }


def build_case_journal(
    case_id: str,
    *,
    runtime_events: Iterable[Mapping[str, Any]] = (),
    vault_events: Iterable[Mapping[str, Any]] = (),
    authority_events: Iterable[Mapping[str, Any]] = (),
    baseline_graph: Mapping[str, Any] | None = None,
    baseline_metadata: Mapping[str, Any] | None = None,
    current_graph: Mapping[str, Any] | None = None,
    current_metadata: Mapping[str, Any] | None = None,
    close_graph: Mapping[str, Any] | None = None,
    close_metadata: Mapping[str, Any] | None = None,
    since: str | None = None,
    until: str | None = None,
    as_of: str | None = None,
    workstream: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Build the API-ready timeline, state delta and optional post-close drift."""

    events = merge_events(
        case_id,
        runtime_events=runtime_events,
        vault_events=vault_events,
        authority_events=authority_events,
    )
    since_at = _instant(since) if since else None
    until_at = _instant(until, end_of_day=True) if until else None
    as_of_at = _instant(as_of, end_of_day=True) if as_of else None
    requested_kind = _token(kind, "") if kind else ""
    requested_workstream = str(workstream or "").strip()
    filtered_events = []
    for event in events:
        known_at = _instant(event["known_at"])
        if since_at and known_at and known_at < since_at:
            continue
        if until_at and known_at and known_at > until_at:
            continue
        if as_of_at and known_at and known_at > as_of_at:
            continue
        if requested_kind and requested_kind not in {event["kind"], event["event_type"]}:
            continue
        if requested_workstream and requested_workstream not in event["workstream_ids"]:
            continue
        filtered_events.append(event)

    delta = compare_graphs(baseline_graph, current_graph)
    if requested_workstream:
        delta["changes"] = [
            change for change in delta["changes"]
            if requested_workstream in {
                change["workstream_id"],
                change["before_workstream_id"],
                change["after_workstream_id"],
            }
        ]
        counts = Counter(change["trend"].lower() for change in delta["changes"])
        movements = Counter(
            str(change["movement"]).lower()
            for change in delta["changes"] if change["movement"]
        )
        delta.update(
            change_count=len(delta["changes"]),
            advanced=counts["advanced"],
            regressed=counts["regressed"],
            changed=counts["changed"],
            opened=movements["opened"],
            closed=movements["closed"],
            workstreams=[{
                "workstream_id": requested_workstream,
                "change_count": len(delta["changes"]),
                "advanced": counts["advanced"],
                "regressed": counts["regressed"],
                "changed": counts["changed"],
                "net_direction": (
                    "ADVANCED" if counts["advanced"] > counts["regressed"]
                    else "REGRESSED" if counts["regressed"] > counts["advanced"]
                    else "MIXED_OR_NEUTRAL"
                ),
                "change_ids": [change["change_id"] for change in delta["changes"]],
            }] if delta["changes"] else [],
        )

    phases: dict[str, list[str]] = defaultdict(list)
    for event in filtered_events:
        phases[event["phase"]].append(event["journal_id"])
    event_kinds = Counter(event["kind"] for event in filtered_events)

    if close_graph is not None:
        drift_delta = compare_graphs(close_graph, current_graph)
        drift = {
            "status": "AVAILABLE",
            "baseline_state_id": (close_metadata or {}).get("state_id"),
            "current_state_id": (current_metadata or {}).get("state_id"),
            **drift_delta,
        }
    else:
        drift = {
            "status": "UNAVAILABLE",
            "reason": "An explicit close_state_id is required before post-close drift can be measured.",
        }

    inferred_actors = sum(
        1 for event in filtered_events if event["actor_source"] == "INFERRED_SYSTEM"
    )
    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "case_id": case_id,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "temporal": {
            "effective_axis": "effective_date",
            "knowledge_axis": "known_at",
            "recording_axis": "recorded_at",
            "since": since,
            "until": until,
            "as_of": as_of,
        },
        "filters": {"workstream": workstream, "kind": kind},
        "baseline": copy.deepcopy(dict(baseline_metadata or {})),
        "current": copy.deepcopy(dict(current_metadata or {})),
        "event_count": len(filtered_events),
        "events": filtered_events,
        "phases": [
            {"phase": phase, "event_ids": ids, "event_count": len(ids)}
            for phase, ids in phases.items()
        ],
        "event_kinds": dict(sorted(event_kinds.items())),
        "summary": delta,
        "drift": drift,
        "integrity": {
            "sources": [
                "RUNTIME_LEDGER",
                "VAULT_EVENT",
                "AUTHORITY_LEDGER",
                "GRAPH_VERSION_ARCHIVE",
            ],
            "runtime_ledger_is_primary_for_admissions_and_settlements": True,
            "inferred_system_actor_count": inferred_actors,
            "warnings": (
                [f"{inferred_actors} event(s) predate explicit actor capture and are attributed to PANTA_SYSTEM."]
                if inferred_actors else []
            ),
        },
    }


__all__ = [
    "CHANGE_RULES_VERSION",
    "JOURNAL_EVENT_SCHEMA_VERSION",
    "JOURNAL_SCHEMA_VERSION",
    "build_case_journal",
    "compare_graphs",
    "merge_events",
    "normalize_event",
]
