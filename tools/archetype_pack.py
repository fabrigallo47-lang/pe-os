"""Load canonical domain archetype packs used for extraction routing."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
_ARCHETYPE_DIR = ROOT / "vault" / "policy" / "archetypes"
PACK_PATHS = {
    "buyout": _ARCHETYPE_DIR / "semantic_handoff_v0_2" / "02_buyout_archetype_pack_v0_2.yaml",
    "venture": _ARCHETYPE_DIR / "venture_growth_v1_1" / "01_venture_archetype_pack_v1_1.yaml",
    "growth": _ARCHETYPE_DIR / "venture_growth_v1_1" / "02_growth_archetype_pack_v1_1.yaml",
}
DEFAULT_ARCHETYPE = "buyout"


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


# ── Canonical concept registry (dictionary section 4) ────────────────────────
# The pack ships 40 concept seeds, each declaring the identity fields a claim
# of that concept MUST carry. Nothing read them before this: the pack was
# loaded only for workstreams and the question spine.
#
# Coverage is deliberately partial and visible rather than padded. Section 4.1
# specifies the registry record as
#     concept_id · label · family · kind · required_identity[] · aliases[]
# and the pack ships every field except `aliases[]`, which lives in the
# companion `01_canonical_concepts_registry.csv` (142 seeds across the three
# archetypes). Without it only a direct label match resolves -- 11 of the 69
# METRIC_ENUM labels. The remaining 58 are NOT hand-mapped here on purpose:
# 4.1 says "il codice non deve mantenere una seconda lista piatta divergente",
# and a hand-written bridge is exactly that second list, guaranteed to drift
# from the registry it is imitating. Ship the CSV and this resolves properly.

def canonical_concepts(pack: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The pack's canonical concept seeds, or [] when the pack declares none."""
    concepts = (pack or load_pack()).get("canonical_concepts")
    return concepts if isinstance(concepts, list) else []


def _concept_key(text: Any) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def concept_for_metric(metric: Any, pack: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve a metric label to its canonical concept, or None.

    None is a real answer, not a failure to try harder: section 4.2 says an
    unmatched-but-material concept becomes a candidate/unbound residue and is
    never forced onto the nearest-looking neighbour.
    """
    key = _concept_key(metric)
    if not key:
        return None
    for concept in canonical_concepts(pack):
        if _concept_key(concept.get("label")) == key or _concept_key(concept.get("id")) == key:
            return concept
    return None


# Pack identity vocabulary -> extraction-schema attribute. Only clearly
# equivalent names are mapped; nothing is invented to raise coverage.
_IDENTITY_FIELD_MAP: dict[str, str] = {
    "entity": "entity",
    "period": "period",
    "scenario": "scenario",
    "perimeter": "perimeter",
    "basis": "basis",
    "scope": "scope",
    "unit": "unit",
    "currency": "unit",        # currency is carried as the unit token
    "measure": "measurement",  # same axis, different name
}

_IDENTITY_EMPTY = {"", "unspecified", "unknown", "none", "not available"}


def _identity_value(claim: Any, attribute: str) -> str:
    value = getattr(claim, attribute, None)
    if attribute == "period" and not value:
        value = getattr(claim, "period_canonical", None)
    return str(value or "").strip().lower()


def missing_required_identity(claim: Any, pack: dict[str, Any] | None = None) -> list[str]:
    """Identity fields the claim's concept declares mandatory, that the schema
    CAN carry, and that this claim left empty.

    Deterministic completeness, not a judgement about whether a value is
    right: `basis` left "unspecified" on a concept whose required_identity
    names basis is incomplete by the pack's own declaration rather than by a
    rule someone wrote here. Returns [] for an unresolved concept -- 4.2 is
    explicit that an unmatched concept becomes residue and is never forced
    onto a neighbour, and a concept we cannot name cannot tell us what it
    requires either.

    Fields the schema has no home for are NOT reported here; they are not the
    claim's fault. See unrepresentable_required_identity().
    """
    concept = concept_for_metric(getattr(claim, "metric", None), pack)
    if not concept:
        return []
    missing: list[str] = []
    for field_name in concept.get("required_identity") or []:
        attribute = _IDENTITY_FIELD_MAP.get(field_name)
        if attribute and _identity_value(claim, attribute) in _IDENTITY_EMPTY:
            missing.append(field_name)
    return missing


def unrepresentable_required_identity(
    claim_or_metric: Any, pack: dict[str, Any] | None = None,
) -> list[str]:
    """Identity fields the concept requires that this schema cannot express.

    The pack declares 63 distinct required_identity names across its concepts
    (numerator_definition, covenant_basis, cash_flow_dates, valuation_date,
    ...) and the extraction schema has a field for 7 of them. That gap is not
    an extraction failure and must never be reported as one -- it measures how
    much more identity the archetype packs assume than the flat claim object
    currently carries, which is the concrete case for the section 3 axis
    migration. Surfacing it keeps the gap countable instead of anecdotal.
    """
    metric = getattr(claim_or_metric, "metric", claim_or_metric)
    concept = concept_for_metric(metric, pack)
    if not concept:
        return []
    return [
        field_name for field_name in concept.get("required_identity") or []
        if field_name not in _IDENTITY_FIELD_MAP
    ]


# ── Archetype-selected extraction vocabulary ─────────────────────────────────
# A concept only belongs in the `metric` slot if it actually carries a value.
# Section 3.3 maps `kind` to object type, and most of an archetype is NOT a
# metric: 9 of venture's 49 concepts are `kind: metric`, the rest are
# case_reading, qualitative_topic, condition, risk, assumption... Flattening
# those into the metric enum would put "Current product state" (a
# categorical_observation) in the same slot as "Revenue" and let two different
# object types collide on one identity. They stay out until the object model
# can hold them -- honestly unresolvable beats wrongly resolved.
_VALUE_BEARING_KINDS = frozenset({
    "metric", "metric_set", "metric_or_definition", "metric_or_reading",
    "metric_or_condition", "metric_or_assumption", "metric_or_model_output",
    "model_output", "model_output_set", "derived_analytic",
})


def value_bearing_concepts(archetype_id: str) -> list[dict[str, Any]]:
    """Concepts of this archetype that can legitimately carry a value."""
    return [
        c for c in canonical_concepts(load_pack(archetype_id))
        if str(c.get("kind") or "") in _VALUE_BEARING_KINDS
    ]


def extraction_vocabulary(archetype_id: str, baseline: list[str]) -> list[str]:
    """The metric labels extraction may use for this archetype.

    `baseline` (METRIC_ENUM) is always kept: it is the buyout vocabulary and
    the frozen contract the benchmark scores against, so widening must never
    remove or rename anything already in it.

    For buyout the baseline is returned UNCHANGED. The buyout pack's own
    labels ("Reported revenue", "Reported EBITDA") are deliberately not merged:
    METRIC_ENUM already covers that archetype, and adding near-synonyms would
    fragment one identity across two spellings -- the same failure mode the
    dictionary's 4.1 warns about from the other direction.

    For venture and growth the baseline carries no vocabulary at all, which is
    why a venture corpus extracts almost entirely as "Other". There, the
    pack's value-bearing concept labels are appended.
    """
    if archetype_id == DEFAULT_ARCHETYPE:
        return list(baseline)
    seen = {label.casefold() for label in baseline}
    widened = list(baseline)
    for concept in value_bearing_concepts(archetype_id):
        label = str(concept.get("label") or "").strip()
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            widened.append(label)
    return widened


# ── Evidence state (dictionary section 9) ────────────────────────────────────
# Evidence in private markets is substantially a POSITION ON A LADDER, not a
# number: "paid pilot" and "production deployment" are different states of the
# same relationship, and the difference is the finding. Section 9 types these
# per archetype and says so directly -- "queste sono categorie/progressioni di
# evidenza, non universal numeric scores".
#
# Forced through metric+value+unit a state becomes a null-valued claim or free
# text, and stops being ORDERABLE, which is the one operation a ladder exists
# for. This axis exists so that ordering survives extraction.
_BUYOUT_STATE_FILE = _ARCHETYPE_DIR / "evidence_states_v0_1.yaml"


@lru_cache(maxsize=8)
def evidence_state_axes(archetype_id: str) -> dict[str, list[str]]:
    """{axis name: states, ordered low->high} for this archetype.

    venture and growth read the pack's own proof_ladder. buyout has none by
    design (9.4 forbids collapsing it into a single ladder) and reads the
    transcribed axes file instead.
    """
    if archetype_id == DEFAULT_ARCHETYPE:
        if not _BUYOUT_STATE_FILE.is_file():
            return {}
        with _BUYOUT_STATE_FILE.open(encoding="utf-8") as stream:
            document = yaml.safe_load(stream) or {}
        return {
            name: list(spec.get("states") or [])
            for name, spec in (document.get("axes") or {}).items()
        }
    ladder = load_pack(archetype_id).get("proof_ladder") or {}
    return {
        name: list(states)
        for name, states in ladder.items()
        if isinstance(states, list) and states
    }


def evidence_state_vocabulary(archetype_id: str) -> list[str]:
    """Every state this archetype can express, de-duplicated, order preserved."""
    seen: set[str] = set()
    vocabulary: list[str] = []
    for states in evidence_state_axes(archetype_id).values():
        for state in states:
            if state not in seen:
                seen.add(state)
                vocabulary.append(state)
    return vocabulary


def evidence_state_rank(archetype_id: str, state: Any) -> list[tuple[str, int, int]]:
    """Where a state sits: [(axis, index, axis length), ...].

    Returns every axis the state belongs to rather than picking one, because
    for buyout some states genuinely sit on two axes -- "contracted" is both a
    commercial_commitment_state and a recognition_state. Choosing silently
    would invent precision the source never had; an ambiguous answer is the
    honest one and the caller can disambiguate with the claim's own metric.

    Empty list means the state is unknown to this archetype, which is a real
    answer too: states are not portable across archetypes.
    """
    needle = str(state or "").strip().casefold()
    if not needle:
        return []
    found: list[tuple[str, int, int]] = []
    for axis, states in evidence_state_axes(archetype_id).items():
        for index, candidate in enumerate(states):
            if candidate.casefold() == needle:
                found.append((axis, index, len(states)))
    return found
