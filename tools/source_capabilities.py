"""Versioned, machine-readable source parsing capability contract.

The matrix is intentionally honest about two different states: formats that
PANTA can parse deterministically, and formats that require a local optional
reader.  A filename is never treated as evidence that extraction succeeded;
the parser still has to produce addressable content or return an actionable
capability response.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any


CAPABILITY_SCHEMA = "panta.source-capabilities/1.0"

_PROVENANCE = [
    "source_id",
    "source_version_id",
    "case_id",
    "original_filename",
    "locator",
]
_PERIOD_SEMANTICS = {
    "effective_date": "declared source date only; never inferred from upload time",
    "known_at": "when the Firm could know the source; not the claim period",
    "content_period": "preserve source labels for L2; L1 never invents a period",
}


def _capability(
    capability_id: str,
    formats: list[str],
    support: str,
    parser: str | None,
    locator: str,
    *,
    dependency: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "formats": formats,
        "support": support,
        "parser": parser,
        "dependency": dependency,
        "provenance_fields": list(_PROVENANCE),
        "locator_semantics": locator,
        "period_semantics": dict(_PERIOD_SEMANTICS),
        "action_if_unavailable": action,
    }


_CAPABILITIES: tuple[dict[str, Any], ...] = (
    _capability(
        "native_pdf", [".pdf"], "SUPPORTED_IF_READER_AVAILABLE", "parse_pdf",
        "one-based PDF page, with word offsets when split",
        dependency="pdfplumber (local optional reader)",
        action="Install the approved PDF reader or export the document as UTF-8 text.",
    ),
    _capability(
        "scanned_pdf_ocr", [".pdf"], "UNSUPPORTED", None,
        "OCR output must retain one-based source page numbers",
        action="Run OCR outside PANTA, verify the page mapping, then upload a searchable PDF or UTF-8 text export.",
    ),
    _capability(
        "native_image", [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"],
        "SUPPORTED_IF_READER_AVAILABLE", "parse_image",
        "single image, page 1; a caller-supplied vision_fallback is a separate, "
        "explicitly injected capability, not part of this contract",
        dependency="a local PDF-page model (Granite-Docling or an injected convert_page)",
        action="Install the PDF model stack (see deploy/README.md) or supply convert_page.",
    ),
    _capability(
        "docx", [".docx"], "SUPPORTED", "parse_docx",
        "document paragraph range in XML document order",
    ),
    _capability(
        "pptx", [".pptx"], "SUPPORTED", "parse_pptx",
        "one-based slide number, with word offsets when split",
    ),
    _capability(
        "openxml_workbook", [".xlsx", ".xlsm"], "SUPPORTED_IF_READER_AVAILABLE", "parse_xlsx",
        "workbook filename, sheet name, and exact row range; formula graph remains cell-addressable",
        dependency="openpyxl (existing approved workbook reader)",
        action="Install the repository requirements; do not convert formulas to displayed values.",
    ),
    _capability(
        "csv", [".csv"], "SUPPORTED", "parse_csv",
        "one-based CSV row range including the header row",
    ),
    _capability(
        "markup_or_text", [".md", ".markdown", ".txt", ".html", ".htm"], "SUPPORTED", "parse_text",
        "heading/line/word range in the original artifact",
    ),
    _capability(
        "transcript_export", [".srt", ".vtt", ".txt"], "SUPPORTED", "parse_transcript",
        "cue number and source timecode; plain-text transcripts use line ranges",
    ),
    _capability(
        "email_export", [".eml", ".mbox"], "SUPPORTED", "parse_email",
        "one-based message number and body word range; attachments are not silently parsed",
    ),
    _capability(
        "legacy_excel", [".xls"], "UNSUPPORTED", None,
        "none",
        action="Open the workbook in Excel and save it as .xlsx without replacing formulas with values.",
    ),
    _capability(
        "outlook_msg", [".msg"], "UNSUPPORTED", None,
        "none",
        action="Export the message as RFC 822 .eml, preserving headers and the plain-text body.",
    ),
)

# Public read contract.  Call ``capability_manifest`` when a defensive copy is
# required for serialization.
SOURCE_CAPABILITY_MATRIX = _CAPABILITIES


def capability_manifest() -> dict[str, Any]:
    """Return a copy so callers cannot mutate the process-wide contract."""
    return {
        "schema": CAPABILITY_SCHEMA,
        "invariants": {
            "no_fake_extraction": True,
            "source_envelope_required_for_live_intake": True,
            "unknown_period_is_preserved_as_unknown": True,
        },
        "capabilities": copy.deepcopy(list(_CAPABILITIES)),
    }


def resolve_source_capability(
    path: Path,
    declared_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve routing metadata without claiming that parsing has succeeded."""
    suffix = path.suffix.lower()
    declared = declared_metadata or {}
    document_type = str(declared.get("document_type") or "").lower()
    parser_route = str(declared.get("parser_route") or "").lower()

    if suffix == ".txt" and ("transcript" in document_type or "transcript" in parser_route):
        capability_id = "transcript_export"
    else:
        capability_id = next(
            (
                item["capability_id"]
                for item in _CAPABILITIES
                if suffix in item["formats"] and item["capability_id"] != "scanned_pdf_ocr"
            ),
            "unsupported_source",
        )
    if capability_id == "unsupported_source":
        return {
            "capability_id": capability_id,
            "formats": [suffix or "<no extension>"],
            "support": "UNSUPPORTED",
            "parser": None,
            "dependency": None,
            "provenance_fields": list(_PROVENANCE),
            "locator_semantics": "none",
            "period_semantics": dict(_PERIOD_SEMANTICS),
            "action_if_unavailable": (
                "Export to searchable PDF, DOCX, PPTX, XLSX/XLSM, CSV, Markdown/TXT/HTML, "
                "SRT/VTT, or RFC 822 EML/MBOX."
            ),
        }
    return copy.deepcopy(next(item for item in _CAPABILITIES if item["capability_id"] == capability_id))


def capability_failure(
    path: Path,
    code: str,
    *,
    capability_id: str | None = None,
    action: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build the stable error body exposed by parser failures."""
    resolved = resolve_source_capability(path)
    if capability_id:
        match = next(
            (item for item in _CAPABILITIES if item["capability_id"] == capability_id),
            None,
        )
        if match:
            resolved = copy.deepcopy(match)
    return {
        "schema": CAPABILITY_SCHEMA,
        "status": "REJECTED",
        "code": code,
        "filename": path.name,
        "capability_id": resolved["capability_id"],
        "detail": detail,
        "action": action or resolved.get("action_if_unavailable"),
        "accepted_formats": sorted({ext for item in _CAPABILITIES for ext in item["formats"] if item["support"] != "UNSUPPORTED"}),
    }
