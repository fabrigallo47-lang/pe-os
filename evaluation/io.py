"""Deterministic JSON, JSONL and NDJSON I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read a JSON array/object or line-delimited JSON file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        records = []
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each record must be an object")
            records.append(value)
        return records

    value = json.loads(text)
    if isinstance(value, list):
        if not all(isinstance(item, dict) for item in value):
            raise ValueError(f"{path}: JSON array must contain objects")
        return value
    if isinstance(value, dict):
        if isinstance(value.get("records"), list):
            return list(value["records"])
        return [value]
    raise ValueError(f"{path}: expected a JSON object or array")


def iter_case_files(path: Path) -> Iterator[Path]:
    path = Path(path)
    if path.is_file():
        yield path
        return
    if not path.is_dir():
        raise FileNotFoundError(path)
    for suffix in ("*.json", "*.jsonl", "*.ndjson"):
        yield from sorted(path.rglob(suffix))


def read_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case_file in iter_case_files(path):
        cases.extend(read_records(case_file))
    return cases


def write_ndjson(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    path.write_text(payload, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
