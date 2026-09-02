"""Versioned benchmark registry and local dataset inventory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from evaluation.adapters import ADAPTERS


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = Path(__file__).resolve().parent / "registry" / "benchmarks.yaml"
DEFAULT_DATA_ROOT = ROOT / ".panta-eval" / "datasets"


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetEntry:
    raw: Mapping[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.raw["id"])

    @property
    def version(self) -> str:
        return str(self.raw["version"])

    @property
    def adapter(self) -> str:
        return str(self.raw["adapter"])

    @property
    def bundled(self) -> bool:
        return self.raw.get("acquisition", {}).get("type") == "bundled"

    def local_path(self, data_root: Path = DEFAULT_DATA_ROOT) -> Path:
        configured = self.raw.get("local_path")
        if configured:
            path = Path(str(configured))
            return path if path.is_absolute() else ROOT / path
        return data_root / self.dataset_id / self.version


class BenchmarkRegistry:
    def __init__(self, payload: Mapping[str, Any], source: Path = DEFAULT_REGISTRY):
        self.payload = dict(payload)
        self.source = source
        self._validate()

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY) -> "BenchmarkRegistry":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise RegistryError("Benchmark registry must be a YAML object")
        return cls(payload, Path(path))

    def _validate(self) -> None:
        if self.payload.get("schema") != "panta-eval.registry/1.0":
            raise RegistryError("Unsupported or missing registry schema")
        datasets = self.payload.get("datasets")
        if not isinstance(datasets, list):
            raise RegistryError("Registry datasets must be a list")
        seen: set[str] = set()
        required = {"id", "name", "version", "adapter", "formats", "tasks", "acquisition", "license"}
        for index, item in enumerate(datasets):
            if not isinstance(item, Mapping):
                raise RegistryError(f"datasets[{index}] must be an object")
            missing = required - set(item)
            if missing:
                raise RegistryError(f"datasets[{index}] missing: {', '.join(sorted(missing))}")
            dataset_id = str(item["id"])
            if dataset_id in seen:
                raise RegistryError(f"Duplicate dataset id: {dataset_id}")
            seen.add(dataset_id)
            if item["adapter"] not in ADAPTERS:
                raise RegistryError(f"Dataset {dataset_id} uses unknown adapter {item['adapter']}")

    def entries(self, *, enabled_only: bool = False) -> list[DatasetEntry]:
        items = self.payload["datasets"]
        if enabled_only:
            items = [item for item in items if item.get("enabled_by_default")]
        return [DatasetEntry(item) for item in items]

    def get(self, dataset_id: str) -> DatasetEntry:
        for entry in self.entries():
            if entry.dataset_id == dataset_id:
                return entry
        raise RegistryError(f"Unknown dataset: {dataset_id}")

    def digest(self) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DatasetManager:
    """Inventory datasets without silently downloading licensed corpora."""

    def __init__(self, registry: BenchmarkRegistry, data_root: Path = DEFAULT_DATA_ROOT):
        self.registry = registry
        self.data_root = Path(data_root)

    def status(self, dataset_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        selected = set(dataset_ids or [])
        rows = []
        for entry in self.registry.entries():
            if selected and entry.dataset_id not in selected:
                continue
            path = entry.local_path(self.data_root)
            rows.append({
                "id": entry.dataset_id,
                "version": entry.version,
                "adapter": entry.adapter,
                "path": str(path),
                "available": path.exists(),
                "bundled": entry.bundled,
                "acquisition": dict(entry.raw.get("acquisition", {})),
                "source_url": entry.raw.get("source_url"),
                "data_url": entry.raw.get("data_url"),
                "license": entry.raw.get("license"),
            })
        return rows

    def write_lock(self, path: Path) -> dict[str, Any]:
        rows = self.status()
        lock = {
            "schema": "panta-eval.dataset-lock/1.0",
            "registry_sha256": self.registry.digest(),
            "datasets": [
                {key: row[key] for key in ("id", "version", "path", "available")}
                for row in rows
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return lock
