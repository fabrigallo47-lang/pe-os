"""Load and validate the versioned PANTA evaluation contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMA_FILES = {
    "case": "evaluation_case.schema.json",
    "prediction": "system_prediction.schema.json",
    "result": "evaluation_result.schema.json",
    "evidence": "evidence_locator.schema.json",
}


class SchemaValidationError(ValueError):
    """Raised with stable, human-readable JSON paths for invalid records."""

    def __init__(self, schema_name: str, errors: list[str]):
        self.schema_name = schema_name
        self.errors = errors
        super().__init__(f"{schema_name} validation failed: " + "; ".join(errors))


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_FILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown evaluation schema: {name}") from exc
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _registry() -> Registry:
    registry = Registry()
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name), registry=_registry())


def _format_path(parts: Any) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def validate(name: str, value: Mapping[str, Any]) -> None:
    errors = sorted(validator(name).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        messages = [f"{_format_path(error.absolute_path)}: {error.message}" for error in errors]
        raise SchemaValidationError(name, messages)


def validate_case(value: Mapping[str, Any]) -> None:
    validate("case", value)


def validate_prediction(value: Mapping[str, Any]) -> None:
    validate("prediction", value)


def validate_result(value: Mapping[str, Any]) -> None:
    validate("result", value)
