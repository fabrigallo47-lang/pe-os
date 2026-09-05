"""Load deal source metadata without inferring facts absent from the ledger."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


# doc_type is not a validated enum -- it is interpolated straight into the
# prompt (`SOURCE: ... - {doc_type}`), where the model reads it against the
# "Source -> class mapping" block. So each label here is chosen to match a
# phrase that block already names; a label it does not name teaches nothing.
# `Other` is the honest non-answer, and anything absent from this table lands
# there AND is reported by unmapped_source_types() rather than nudged onto a
# neighbour.
DOC_TYPE_BY_SOURCE_TYPE: dict[str, str] = {
    "amendment": "Amendment",
    "board_pack": "Board Pack",
    "cim": "Seller CIM",
    "seller_cim": "Seller CIM",
    "data_room": "Data Room",
    "ic_memo": "IC Memo",
    "investment_memo": "IC Memo",
    "internal": "Internal",
    "internal_research": "Internal",
    "internal_event_note": "Internal",
    "internal_collaboration_thread": "Internal",
    "institutional_notes": "Internal",
    "lbo_model": "LBO Model",
    "qoe_report": "QoE Report",
    # "Meeting notes / call transcript / DDQ -> observed" is a rule the prompt
    # already states; before this it never fired, because every transcript in a
    # non-Keystone deal reached the model labelled Other.
    "call_transcript": "Call Transcript",
    "ic_call_transcript": "Call Transcript",
    "expert_call_transcript": "Call Transcript",
    "expert_call_notes_and_transcript": "Call Transcript",
    "reference_call_transcript": "Call Transcript",
    # A summary is somebody's rendering of a call, not the call. Keeping it
    # distinct from a transcript preserves that difference for the reader.
    "call_summary": "Meeting Notes",
    # The mapping block names no email rule. "Email" is still the true label,
    # and a true label the block ignores beats a false one it acts on.
    "email": "Email",
    "email_thread": "Email",
}


def _basename(value: object) -> str:
    """Treat both POSIX and Windows separators as catalog path separators."""
    return str(value or "").replace("\\", "/").rsplit("/", 1)[-1].strip()


def _clean_row(row: object) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    cleaned = {
        str(key).strip(): value.strip() if isinstance(value, str) else value
        for key, value in row.items()
        if key is not None
    }
    filename = _basename(cleaned.get("filename"))
    source_id = cleaned.get("source_id")
    if not filename or not isinstance(source_id, str) or not source_id:
        return None
    cleaned["filename"] = filename
    return cleaned


def load_source_catalog(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a CSV or equivalent JSON-list ledger, keyed by source basename.

    Intake metadata is optional, so an absent, unreadable, or malformed catalog
    behaves like an empty one instead of preventing source extraction.
    """
    catalog_path = Path(path)
    try:
        if catalog_path.suffix.lower() == ".json":
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else []
        else:
            with catalog_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError):
        return {}

    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        cleaned = _clean_row(row)
        if cleaned is not None:
            catalog[cleaned["filename"]] = cleaned
    return catalog


def source_record_from_catalog(
    path: str | Path, catalog: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Return declared source metadata for ``path`` without filling factual gaps."""
    row = catalog.get(Path(path).name)
    if not isinstance(row, dict):
        return None
    source_id = row.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        return None
    source_type = str(row.get("source_type") or "").strip()
    return {
        "source_id": source_id,
        "name": str(row.get("title") or ""),
        "party": "unknown",
        "doc_type": DOC_TYPE_BY_SOURCE_TYPE.get(source_type, "Other"),
        "effective_date": str(row.get("effective_at") or ""),
        "known_at": str(row.get("known_at") or ""),
        "manifest": ["ALL"],
    }


def unmapped_source_types(catalog: dict[str, dict[str, Any]]) -> set[str]:
    """Expose vocabulary gaps so callers can resolve them rather than guess."""
    return {
        source_type
        for row in catalog.values()
        if isinstance(row, dict)
        if (source_type := str(row.get("source_type") or "").strip())
        and source_type not in DOC_TYPE_BY_SOURCE_TYPE
    }
