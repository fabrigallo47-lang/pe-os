"""Versioned source metadata shared by live intake and extractors.

The envelope deliberately records unknown fields as ``None``.  It is evidence
about a document, not an inference engine: missing issuer or effective date
must never be silently replaced with Keystone defaults.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tools.source_capabilities import CAPABILITY_SCHEMA, resolve_source_capability


SCHEMA = "panta.source-envelope/1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _clean(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def build_source_envelope(
    path: Path,
    case_id: str,
    uploaded_at: str,
    *,
    original_filename: str | None = None,
    declared_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable, case-scoped source identity from durable file bytes."""
    declared = declared_metadata or {}
    version_id = sha256_file(path)
    digest = version_id.removeprefix("sha256:")
    media_type = _clean(declared.get("media_type")) or path.suffix.lower().removeprefix(".") or "unknown"
    capability = resolve_source_capability(path, declared)
    return {
        "schema": SCHEMA,
        "source_id": _clean(declared.get("source_id")) or f"SRC-{digest[:16].upper()}",
        "source_version_id": version_id,
        "case_id": str(case_id),
        "original_filename": _clean(original_filename) or path.name,
        "stored_filename": path.name,
        "media_type": media_type,
        "document_type": _clean(declared.get("document_type")) or "unknown",
        "issuer": _clean(declared.get("issuer")),
        "author": _clean(declared.get("author")),
        "effective_date": _clean(declared.get("effective_date")),
        "known_at": _clean(declared.get("known_at")) or uploaded_at,
        "uploaded_at": uploaded_at,
        "provenance": _clean(declared.get("provenance")) or "user_upload",
        "parser_route": _clean(declared.get("parser_route")) or "extract_v2",
        "parser_capability": capability["capability_id"],
        "capability_contract": CAPABILITY_SCHEMA,
        "locator_semantics": capability["locator_semantics"],
        "period_semantics": capability["period_semantics"],
        "declared_metadata": {
            key: value for key, value in declared.items()
            if key not in {"source_id", "media_type", "document_type", "issuer", "author", "effective_date", "known_at", "provenance", "parser_route"}
        },
    }


def extractor_source_record(envelope: dict[str, Any]) -> dict[str, Any]:
    """Adapt the envelope to the established E3 source record contract."""
    return {
        "source_id": envelope["source_id"],
        "name": envelope.get("original_filename") or envelope["source_id"],
        "party": envelope.get("issuer") or "unknown",
        "doc_type": envelope.get("document_type") or "unknown",
        "effective_date": envelope.get("effective_date") or "",
        "known_at": envelope.get("known_at") or "",
        "manifest": ["SINGLE"],
        "source_envelope": envelope,
    }
