"""Load canonical domain archetype packs used for extraction routing."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
PACK_PATHS = {
    "buyout": ROOT / "vault" / "policy" / "archetypes" / "semantic_handoff_v0_2"
    / "02_buyout_archetype_pack_v0_2.yaml",
}


@lru_cache(maxsize=None)
def load_pack(archetype_id: str = "buyout") -> dict[str, Any]:
    """Return the named archetype pack, parsed once per process."""
    try:
        path = PACK_PATHS[archetype_id]
    except KeyError as exc:
        raise ValueError(f"Unknown archetype pack: {archetype_id!r}") from exc

    if not path.is_file():
        raise FileNotFoundError(f"Archetype pack file is missing: {path}")

    with path.open(encoding="utf-8") as stream:
        pack = yaml.safe_load(stream)
    if not isinstance(pack, dict):
        raise ValueError(f"Archetype pack must be a YAML mapping: {path}")
    if not isinstance(pack.get("workstreams"), dict):
        raise ValueError(f"Archetype pack has no workstreams mapping: {path}")
    return pack


def workstream_ids(pack: dict[str, Any]) -> list[str]:
    """Return the canonical workstream IDs in stable order."""
    workstreams = pack.get("workstreams")
    if not isinstance(workstreams, dict):
        raise ValueError("Archetype pack has no workstreams mapping")
    return sorted(workstreams)


def question_families(pack: dict[str, Any], workstream_id: str) -> list[dict[str, Any]]:
    """Return a workstream's question-family records without inventing defaults."""
    workstreams = pack.get("workstreams")
    if not isinstance(workstreams, dict) or workstream_id not in workstreams:
        raise KeyError(f"Unknown workstream: {workstream_id}")
    families = workstreams[workstream_id].get("question_families")
    if not isinstance(families, list):
        raise ValueError(f"Workstream {workstream_id} has no question_families list")
    return families
