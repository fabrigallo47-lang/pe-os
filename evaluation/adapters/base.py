"""Shared adapter primitives for heterogeneous public benchmarks."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping


CASE_VERSION = "panta-eval.case/1.0"

EXTENSION_FORMAT = {
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "docx",
    ".docm": "docm",
    ".rtf": "rtf",
    ".ppt": "ppt",
    ".pptx": "pptx",
    ".pptm": "pptm",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".xlsm": "xlsm",
    ".csv": "csv",
    ".tsv": "tsv",
    ".msg": "msg",
    ".pst": "pst",
    ".ost": "ost",
    ".eml": "eml",
    ".mbox": "mbox",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".bmp": "bmp",
    ".webp": "webp",
    ".gif": "gif",
    ".svg": "svg",
    ".emf": "emf",
    ".wmf": "wmf",
    ".heic": "heic",
    ".heif": "heic",
    ".jp2": "jp2",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "md",
    ".json": "json",
}

FORMAT_FAMILY = {
    "pdf": "document", "pdf_page": "document", "doc": "document",
    "docx": "document", "docm": "document", "rtf": "document",
    "ppt": "presentation", "pptx": "presentation", "pptm": "presentation",
    "slide_images": "presentation", "xls": "spreadsheet", "xlsx": "spreadsheet",
    "xlsm": "spreadsheet", "csv": "spreadsheet", "tsv": "spreadsheet",
    "msg": "email", "pst": "email", "ost": "email", "eml": "email",
    "mbox": "email", "email_thread": "email", "png": "image", "jpeg": "image",
    "tiff": "image", "bmp": "image", "webp": "image", "gif": "image",
    "svg": "image", "emf": "image", "wmf": "image", "heic": "image",
    "jp2": "image", "bundle": "multimodal",
}


class AdapterError(ValueError):
    pass


def safe_id(value: Any) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(value).strip()).strip("-.")
    return candidate or "unknown"


def infer_format(value: str | Path, fallback: str = "other") -> str:
    return EXTENSION_FORMAT.get(Path(str(value)).suffix.lower(), fallback)


def infer_family(format_name: str) -> str:
    return FORMAT_FAMILY.get(format_name, "other")


def resolved_path(value: str | Path, root: Path | None) -> str:
    path = Path(str(value))
    if root is not None and not path.is_absolute():
        path = root / path
    return str(path)


def make_input(
    input_id: str,
    value: str | Path,
    *,
    root: Path | None = None,
    format_name: str | None = None,
    family: str | None = None,
    role: str = "primary",
    parent_input_id: str | None = None,
    selector: Mapping[str, Any] | None = None,
    uri: bool = False,
) -> dict[str, Any]:
    fmt = format_name or infer_format(value)
    item: dict[str, Any] = {
        "input_id": input_id,
        "family": family or infer_family(fmt),
        "format": fmt,
        "role": role,
    }
    item["uri" if uri else "path"] = str(value) if uri else resolved_path(value, root)
    if parent_input_id:
        item["parent_input_id"] = parent_input_id
    if selector:
        item["selector"] = dict(selector)
    return item


def make_case(
    *,
    test_id: str,
    benchmark_id: str,
    benchmark_version: str,
    original_id: str,
    split: str,
    task: str,
    inputs: list[dict[str, Any]],
    gold: dict[str, Any],
    metrics: list[str],
    diagnostic_metrics: list[str] | None = None,
    evaluation_profile: str | None = None,
    query: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    track: str | None = None,
    source_uri: str | None = None,
    tags: list[str] | None = None,
    license_name: str | None = None,
) -> dict[str, Any]:
    benchmark = {
        "id": benchmark_id,
        "version": benchmark_version,
        "original_id": str(original_id),
    }
    if track:
        benchmark["track"] = track
    if source_uri:
        benchmark["source_uri"] = source_uri
    case: dict[str, Any] = {
        "schema_version": CASE_VERSION,
        "test_id": safe_id(test_id),
        "benchmark": benchmark,
        "split": split,
        "task": task,
        "inputs": inputs,
        "query": query,
        "gold": gold,
        "evidence": evidence or [],
        "metrics": metrics,
        "tags": sorted(set(tags or [])),
    }
    if diagnostic_metrics:
        case["diagnostic_metrics"] = diagnostic_metrics
    if evaluation_profile:
        case["evaluation_profile"] = evaluation_profile
    if license_name:
        case["license"] = license_name
    return case


class BenchmarkAdapter(ABC):
    adapter_id: str

    @abstractmethod
    def adapt(
        self,
        source: Path,
        *,
        dataset_root: Path | None = None,
        split: str = "validation",
        version: str = "unknown",
        options: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
