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


def canonical_question_spine(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Project the pack's question families into a stable question spine.

    A question-family id is already the pack's durable semantic identifier, so
    the registry must use it directly rather than minting title-derived ids.
    The governing question remains explicit routing context on every family;
    it is not turned into a deal fact or a synthesized position.
    """
    metadata = pack.get("metadata")
    if not isinstance(metadata, dict) or not str(metadata.get("version") or "").strip():
        raise ValueError("Archetype pack has no metadata.version")

    strategy = pack.get("strategy_definition")
    if not isinstance(strategy, dict) or not str(strategy.get("strategy") or "").strip():
        raise ValueError("Archetype pack has no strategy_definition.strategy")

    archetype_id = str(strategy["strategy"]).strip().lower()
    pack_version = str(metadata["version"]).strip()
    spine: list[dict[str, Any]] = []
    seen: set[str] = set()
    for workstream_id in workstream_ids(pack):
        workstream = pack["workstreams"][workstream_id]
        governing_question = str(workstream.get("governing_question") or "").strip()
        if not governing_question:
            raise ValueError(f"Workstream {workstream_id} has no governing_question")
        for family in question_families(pack, workstream_id):
            question_id = str(family.get("id") or "").strip()
            title = str(family.get("question") or "").strip()
            if not question_id or not title:
                raise ValueError(
                    f"Workstream {workstream_id} has a question family without id or question"
                )
            if question_id in seen:
                raise ValueError(f"Duplicate archetype question-family id: {question_id}")
            seen.add(question_id)
            spine.append({
                "id": question_id,
                "title": title,
                "workstream": workstream_id,
                "governing_question": governing_question,
                "archetype_id": archetype_id,
                "archetype_pack_version": pack_version,
                "question_family_id": question_id,
                "question_version": 1,
            })
    return spine


# ── Reconciling the vocabularies that already exist ───────────────────────────
# Three names for the same field were in use before the pack arrived:
#
#   archetype pack   FINANCIAL_QOE, LEGAL_REGULATORY, ...        (9, canonical)
#   Fund Lens        commercial, financial, operations, ...      (7, lowercase)
#   V20 router       underwriting, deal-emergent                 (2, placeholders)
#
# So a claim tagged FINANCIAL_QOE and a question tagged "financial" did not join,
# and a question with no workstream defaulted to "underwriting", which matches
# nothing at all. Normalizing on read rather than rewriting the Fund Lens keeps
# configuration owned by whoever wrote it while giving the system one vocabulary
# to reason in.
UNASSIGNED_WORKSTREAM = "OTHER"

_WORKSTREAM_ALIASES: dict[str, str] = {
    "commercial": "COMMERCIAL_AND_MARKET",
    "market": "COMMERCIAL_AND_MARKET",
    "financial": "FINANCIAL_QOE",
    "finance": "FINANCIAL_QOE",
    "qoe": "FINANCIAL_QOE",
    "operations": "OPERATIONS_TECHNOLOGY_AND_EXECUTION",
    "operational": "OPERATIONS_TECHNOLOGY_AND_EXECUTION",
    "technology": "OPERATIONS_TECHNOLOGY_AND_EXECUTION",
    # The Fund Lens splits people from governance; the pack does not. Both fold
    # into one canonical workstream — a real narrowing, recorded here rather than
    # hidden, because it means two lens questions can no longer be told apart by
    # workstream alone.
    "people": "MANAGEMENT_SPONSOR_AND_GOVERNANCE",
    "management": "MANAGEMENT_SPONSOR_AND_GOVERNANCE",
    "governance": "MANAGEMENT_SPONSOR_AND_GOVERNANCE",
    "sponsor": "MANAGEMENT_SPONSOR_AND_GOVERNANCE",
    "legal": "LEGAL_REGULATORY",
    "regulatory": "LEGAL_REGULATORY",
    "tax": "TAX_AND_STRUCTURING",
    "structuring": "TAX_AND_STRUCTURING",
    "financing": "FINANCING_AND_LIQUIDITY",
    "liquidity": "FINANCING_AND_LIQUIDITY",
    "debt": "FINANCING_AND_LIQUIDITY",
    "model": "MODEL_VALUATION_AND_RETURNS",
    "valuation": "MODEL_VALUATION_AND_RETURNS",
    "returns": "MODEL_VALUATION_AND_RETURNS",
    "value_creation": "VALUE_CREATION_AND_OWNERSHIP_READINESS",
    "ownership": "VALUE_CREATION_AND_OWNERSHIP_READINESS",
    # Router placeholders. These never named a workstream — they meant "nobody
    # assigned one" — so they resolve to OTHER rather than to a guessed area.
    "underwriting": UNASSIGNED_WORKSTREAM,
    "deal-emergent": UNASSIGNED_WORKSTREAM,
    "deal_emergent": UNASSIGNED_WORKSTREAM,
}


def normalize_workstream(value: Any, pack: dict[str, Any] | None = None) -> str:
    """Map any surface form to a canonical workstream id, or OTHER.

    Returns OTHER rather than raising: an unrecognised workstream is a claim or
    question that still exists and must stay visible. Silently dropping it, or
    guessing an area for it, both lose more than an honest "unplaced" does.
    """
    text = str(value or "").strip()
    if not text:
        return UNASSIGNED_WORKSTREAM

    canonical = set(workstream_ids(pack or load_pack()))
    if text in canonical:
        return text
    upper = text.upper().replace(" ", "_").replace("-", "_")
    if upper in canonical:
        return upper

    alias = _WORKSTREAM_ALIASES.get(text.lower())
    if alias and (alias in canonical or alias == UNASSIGNED_WORKSTREAM):
        return alias
    return UNASSIGNED_WORKSTREAM
