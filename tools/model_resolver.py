#!/usr/bin/env python3
"""Resolve L2 workbook semantics as one auditable deal-wide constraint system.

The semantic layer proposes meanings for cells.  This module is the boundary
that decides which proposals can become bindings.  It never selects between
ambiguous cells merely because one proposal has a slightly higher confidence:
an unresolved choice is emitted as a ``coverage_limit`` and remains a Human
Stop.

The resolver enforces four conservative invariants:

* one model node per economic identity;
* declared and additive-formula unit coherence;
* compatibility with already extracted claims;
* a human-readable reason on every admitted binding.

It accepts both the current ``sheet_semantics`` envelope and direct R5-style
proposal dictionaries.  The small ``Binding``/``Concept`` API is intentionally
kept compatible with the earlier L3 prototype used by ``ingest_service``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


_QUARTER_END = re.compile(r"-(03-31|06-30|09-30|12-31)$")
_SUM_RE = re.compile(r"^=\s*(SUM|AVERAGE)\s*\(", re.IGNORECASE)
_CELL_ROW_COL_RE = re.compile(r"^(?P<sheet>[^!]+)!(?P<row>\d+):(?P<col>\d+)$")
_NON_SLUG = re.compile(r"[^A-Z0-9]+")

_UNIT_ALIASES = {
    "$mm": "USD_M",
    "$m": "USD_M",
    "usd m": "USD_M",
    "usd mm": "USD_M",
    "usd millions": "USD_M",
    "$bn": "USD_BN",
    "usd bn": "USD_BN",
    "$": "USD",
    "usd": "USD",
    "€mm": "EUR_M",
    "€m": "EUR_M",
    "eur m": "EUR_M",
    "eur mm": "EUR_M",
    "€": "EUR",
    "eur": "EUR",
    "%": "PERCENT",
    "pct": "PERCENT",
    "percent": "PERCENT",
    "percentage": "PERCENT",
    "x": "MULTIPLE",
    "multiple": "MULTIPLE",
    "days": "DAYS",
    "day": "DAYS",
    "count": "COUNT",
    "#": "COUNT",
}

_IDENTITY_FIELDS = (
    "concept_id",
    "entity",
    "period",
    "scope",
    "basis",
    "scenario",
    "section",
)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _stable_id(prefix: str, value: Any, length: int = 16) -> str:
    digest = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:length].upper()}"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dimension(value: Any) -> str:
    return " ".join(_clean(value).upper().split())


def norm_unit(unit: str) -> str:
    cleaned = " ".join(_clean(unit).lower().split())
    return _UNIT_ALIASES.get(cleaned, cleaned.upper())


def granularity_of(period: str) -> str:
    value = _clean(period)
    if not value:
        return ""
    if _QUARTER_END.search(value):
        return "quarter"
    if re.match(r"^Q[1-4](?:\s*FY)?\s*\d{2,4}", value, re.IGNORECASE):
        return "quarter"
    if re.match(r"^FY\s*\d{4}", value, re.IGNORECASE):
        return "fiscal_year"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return "point"
    return ""


@dataclass(frozen=True)
class Concept:
    concept_id: str
    label: str
    unit: str = ""
    granularity: str = ""
    form: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class Binding:
    # The first eight fields preserve the previous public constructor order.
    concept_id: str
    locator: str
    period: str = ""
    scenario: str = ""
    section: str = ""
    unit: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    entity: str = ""
    scope: str = ""
    basis: str = ""
    value: Any = None
    computational_form: str = ""
    proposed_model_node_id: str = ""
    reason_codes: list[str] = field(default_factory=list)
    explanation: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Binding":
        identity = raw.get("identity") if isinstance(raw.get("identity"), Mapping) else {}
        return cls(
            concept_id=_clean(
                raw.get("concept_id")
                or raw.get("economic_concept_id")
                or identity.get("concept_id")
            ),
            locator=_clean(
                raw.get("locator")
                or raw.get("cell")
                or raw.get("workbook_cell_ref")
                or raw.get("source_ref")
            ),
            period=_clean(
                raw.get("period_canonical")
                or raw.get("period")
                or raw.get("col_header")
                or identity.get("period")
            ),
            scenario=_clean(
                raw.get("scenario")
                or raw.get("record_key")
                or identity.get("scenario")
            ),
            section=_clean(raw.get("section") or identity.get("section")),
            unit=_clean(raw.get("unit") or raw.get("unit_canonical")),
            confidence=float(raw.get("confidence") or 0.0),
            evidence=sorted({_clean(item) for item in raw.get("evidence", []) if _clean(item)}),
            entity=_clean(raw.get("entity") or identity.get("entity")),
            scope=_clean(
                raw.get("scope")
                or raw.get("perimeter")
                or identity.get("scope")
                or identity.get("perimeter")
            ),
            basis=_clean(raw.get("basis") or identity.get("basis")),
            value=raw.get("value"),
            computational_form=_clean(
                raw.get("computational_form") or raw.get("form")
            ),
            proposed_model_node_id=_clean(
                raw.get("model_node_id") or raw.get("proposed_model_node_id")
            ),
        )

    @property
    def identity(self) -> dict[str, str]:
        return {
            "concept_id": _dimension(self.concept_id),
            "entity": _dimension(self.entity),
            "period": _dimension(self.period),
            "scope": _dimension(self.scope),
            "basis": _dimension(self.basis),
            "scenario": _dimension(self.scenario),
            "section": _dimension(self.section),
        }

    @property
    def identity_key(self) -> str:
        return _canonical(self.identity)


@dataclass
class Violation:
    code: str
    detail: str
    bindings: list[str]
    concept_id: str = ""
    relaxation: dict[str, Any] | None = None
    identity: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_coverage_limit(self) -> dict[str, Any]:
        reason_code = {
            "UNIQUE_BINDING": "AMBIGUOUS_IDENTITY",
            "UNIT_COHERENCE": "DECLARED_UNIT_CONFLICT",
            "FORMULA_UNIT_COHERENCE": "FORMULA_UNIT_CONFLICT",
        }.get(self.code, self.code)
        identity = self.identity or {"concept_id": self.concept_id}
        return {
            "coverage_limit_id": _stable_id(
                "COVERAGE", [reason_code, identity, sorted(self.bindings)]
            ),
            "reason_code": reason_code,
            "message": self.detail,
            "identity": identity,
            "candidate_locators": sorted(set(self.bindings)),
            "resolution": "HUMAN_STOP",
            "suggested_resolution": self.relaxation,
        }


@dataclass
class Resolution:
    admitted: list[Binding] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    halted: bool = False
    input_digest: str = ""

    @property
    def status(self) -> str:
        if self.halted:
            return "HALTED_OVERCONSTRAINED"
        return "RESOLVED" if not self.violations else "RESOLVED_WITH_WARNINGS"

    @property
    def coverage_limits(self) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for violation in self.violations:
            item = violation.as_coverage_limit()
            unique[item["coverage_limit_id"]] = item
        return [unique[key] for key in sorted(unique)]

    def as_payload(self) -> dict[str, Any]:
        bindings = [_resolved_binding_payload(item) for item in self.admitted]
        return {
            "schema_version": "model-binding-resolution/1.0",
            "status": self.status,
            "halted": self.halted,
            "input_digest": self.input_digest,
            "binding_count": len(bindings),
            "coverage_limit_count": len(self.coverage_limits),
            "bindings": bindings,
            "coverage_limits": self.coverage_limits,
        }


def _resolved_binding_payload(binding: Binding) -> dict[str, Any]:
    identity = binding.identity
    slug = _NON_SLUG.sub("-", binding.concept_id.upper()).strip("-") or "CONCEPT"
    identity_digest = hashlib.sha256(binding.identity_key.encode("utf-8")).hexdigest()
    model_node_id = f"MN-{slug[:36]}-{identity_digest[:10].upper()}"
    return {
        "binding_id": _stable_id("BINDING", [identity, binding.locator]),
        "model_node_id": model_node_id,
        "proposed_model_node_id": binding.proposed_model_node_id or None,
        "concept_id": binding.concept_id,
        "locator": binding.locator,
        "identity": identity,
        "unit": binding.unit or None,
        "confidence": binding.confidence,
        "value": binding.value,
        "reason_codes": list(binding.reason_codes),
        "explanation": binding.explanation,
        "evidence": sorted(set(binding.evidence)),
    }


def _coerce_concepts(
    concepts: Mapping[str, Concept | Mapping[str, Any]] | Sequence[Mapping[str, Any]],
) -> dict[str, Concept]:
    if isinstance(concepts, Mapping):
        items: Iterable[tuple[str, Concept | Mapping[str, Any]]] = concepts.items()
    else:
        items = ((str(item.get("concept_id") or ""), item) for item in concepts)
    result: dict[str, Concept] = {}
    for key, raw in items:
        if isinstance(raw, Concept):
            concept = raw
        else:
            concept_id = _clean(raw.get("concept_id") or key)
            if not concept_id:
                continue
            concept = Concept(
                concept_id=concept_id,
                label=_clean(raw.get("label") or raw.get("name") or concept_id),
                unit=_clean(raw.get("unit") or raw.get("unit_canonical")),
                granularity=_clean(raw.get("granularity") or raw.get("period_granularity")),
                form=_clean(raw.get("form") or raw.get("computational_form")),
                aliases=[_clean(item) for item in raw.get("aliases", []) if _clean(item)],
            )
        result[concept.concept_id] = concept
    return result


def _coerce_bindings(proposals: Iterable[Binding | Mapping[str, Any]]) -> list[Binding]:
    result = [
        item if isinstance(item, Binding) else Binding.from_mapping(item)
        for item in proposals
    ]
    return sorted(
        result,
        key=lambda item: (
            item.identity_key,
            _normalise_locator(item.locator),
            -item.confidence,
            _canonical(asdict(item)),
        ),
    )


def _cell(source: Mapping[str, Any], locator: str) -> Mapping[str, Any]:
    cells = source.get("cells") if isinstance(source.get("cells"), Mapping) else {}
    if locator in cells:
        return cells[locator]
    normal = _normalise_locator(locator)
    for key, value in cells.items():
        if _normalise_locator(str(key)) == normal and isinstance(value, Mapping):
            return value
    return {}


def _normalise_locator(locator: str) -> str:
    value = _clean(locator).replace("$", "").upper()
    if "::" in value:
        value = value.rsplit("::", 1)[1]
    elif ":" in value and "!" in value and value.split(":", 1)[0].endswith(
        (".XLSX", ".XLSM")
    ):
        value = value.split(":", 1)[1]
    match = _CELL_ROW_COL_RE.match(value)
    if match:
        value = (
            f"{match.group('sheet')}!"
            f"{_column_letter(int(match.group('col')))}{int(match.group('row'))}"
        )
    return value


def _column_letter(index: int) -> str:
    if index < 1:
        return ""
    chars: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.replace(",", "").strip())
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _cell_value(binding: Binding, cell: Mapping[str, Any]) -> float | None:
    direct = _numeric(binding.value)
    if direct is not None:
        return direct
    for field_name in ("evaluated_value", "cached_value", "value"):
        value = _numeric(cell.get(field_name))
        if value is not None:
            return value
    return None


def _values_match(left: float, right: float) -> bool:
    tolerance = max(1e-9, max(abs(left), abs(right), 1.0) * 1e-6)
    return abs(left - right) <= tolerance


def _claim_matches_identity(
    claim: Mapping[str, Any], binding: Binding, concept: Concept
) -> bool:
    declared_id = _clean(
        claim.get("concept_id")
        or claim.get("economic_concept_id")
        or claim.get("model_concept_id")
    )
    if declared_id and _dimension(declared_id) != _dimension(binding.concept_id):
        return False
    if not declared_id:
        claim_label = _dimension(
            claim.get("metric") or claim.get("concept") or claim.get("subject")
        )
        aliases = {_dimension(concept.label), *(_dimension(item) for item in concept.aliases)}
        if claim_label and claim_label not in aliases:
            return False
        if not claim_label:
            return False
    comparisons = (
        (claim.get("entity"), binding.entity),
        (claim.get("period_canonical") or claim.get("period"), binding.period),
        (claim.get("scope") or claim.get("perimeter"), binding.scope),
        (claim.get("basis"), binding.basis),
        (claim.get("scenario"), binding.scenario),
    )
    return all(
        not _clean(claim_value)
        or not _clean(binding_value)
        or _dimension(claim_value) == _dimension(binding_value)
        for claim_value, binding_value in comparisons
    )


def _claim_analysis(
    binding: Binding,
    concept: Concept,
    cell: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[Violation]]:
    matches = [item for item in claims if _claim_matches_identity(item, binding, concept)]
    if not matches:
        return [], []
    reasons = ["CLAIM_IDENTITY_MATCH"]
    violations: list[Violation] = []
    exact_locator = [
        item
        for item in matches
        if _clean(item.get("locator"))
        and _normalise_locator(str(item.get("locator")))
        == _normalise_locator(binding.locator)
    ]
    if exact_locator:
        reasons.append("CLAIM_LOCATOR_MATCH")

    relevant = exact_locator or matches
    binding_unit = norm_unit(binding.unit)
    claim_units = {
        norm_unit(_clean(item.get("unit") or item.get("unit_canonical")))
        for item in relevant
        if _clean(item.get("unit") or item.get("unit_canonical"))
    }
    if binding_unit and claim_units and claim_units != {binding_unit}:
        violations.append(
            Violation(
                "CLAIM_UNIT_CONFLICT",
                f"{binding.locator} usa {binding.unit!r}, ma i claim compatibili usano "
                + ", ".join(sorted(claim_units)),
                [binding.locator],
                binding.concept_id,
                identity=binding.identity,
                relaxation={
                    "kind": "review_claim_or_binding_unit",
                    "rationale": "claim e modello devono dichiarare unità compatibili",
                },
            )
        )
    elif binding_unit and claim_units:
        reasons.append("CLAIM_UNIT_MATCH")

    value = _cell_value(binding, cell)
    claim_values = [
        candidate
        for candidate in (_numeric(item.get("value")) for item in relevant)
        if candidate is not None
    ]
    if value is not None and claim_values:
        if any(not _values_match(value, candidate) for candidate in claim_values):
            violations.append(
                Violation(
                    "CLAIM_VALUE_CONFLICT",
                    f"{binding.locator} vale {value:g}, incompatibile con almeno un claim "
                    f"per {binding.concept_id}",
                    [binding.locator],
                    binding.concept_id,
                    identity=binding.identity,
                    relaxation={
                        "kind": "review_claim_or_model_value",
                        "rationale": "il resolver non decide quale fonte economica prevale",
                    },
                )
            )
        else:
            reasons.append("CLAIM_VALUE_MATCH")
    return reasons, violations


def _validate_candidate(
    binding: Binding,
    concept: Concept | None,
    source: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
) -> tuple[Binding | None, list[Violation]]:
    if concept is None:
        return None, [
            Violation(
                "UNKNOWN_CONCEPT",
                f"{binding.concept_id or '—'} non è un concetto economico dichiarato",
                [binding.locator],
                binding.concept_id,
                identity=binding.identity,
            )
        ]
    if not binding.locator:
        return None, [
            Violation(
                "MISSING_LOCATOR",
                f"La proposta per {binding.concept_id} non ha una cella sorgente",
                [],
                binding.concept_id,
                identity=binding.identity,
            )
        ]

    reasons = ["DECLARED_CONCEPT_MATCH", f"L2_CONFIDENCE_{binding.confidence:.3f}"]
    violations: list[Violation] = []
    cell = _cell(source, binding.locator)

    if concept.unit and binding.unit:
        if norm_unit(concept.unit) != norm_unit(binding.unit):
            violations.append(
                Violation(
                    "UNIT_COHERENCE",
                    f"{binding.locator} usa {binding.unit!r}, ma {concept.concept_id} "
                    f"dichiara {concept.unit!r}",
                    [binding.locator],
                    binding.concept_id,
                    identity=binding.identity,
                    relaxation={
                        "kind": "review_declared_unit",
                        "from": concept.unit,
                        "to": binding.unit,
                        "rationale": "l'unità deve essere corretta prima del binding",
                    },
                )
            )
        else:
            reasons.append("DECLARED_UNIT_MATCH")

    granularity = granularity_of(binding.period)
    if concept.granularity and granularity:
        if concept.granularity != granularity:
            violations.append(
                Violation(
                    "PERIOD_ALIGNMENT",
                    f"{binding.locator} è {granularity}, ma {concept.concept_id} "
                    f"richiede {concept.granularity}",
                    [binding.locator],
                    binding.concept_id,
                    identity=binding.identity,
                    relaxation={
                        "kind": "declare_period_transformation",
                        "from": granularity,
                        "to": concept.granularity,
                        "rationale": "aggregazione o disaggregazione devono essere esplicite",
                    },
                )
            )
        else:
            reasons.append("PERIOD_GRANULARITY_MATCH")

    cell_kind = _clean(cell.get("kind")).lower()
    formula = _clean(cell.get("value")) if cell_kind == "formula" else ""
    form = _clean(concept.form or binding.computational_form).lower()
    if form == "input" and formula:
        violations.append(
            Violation(
                "PRECEDENT_SHAPE",
                f"{concept.concept_id} è un input, ma {binding.locator} contiene una formula",
                [binding.locator],
                binding.concept_id,
                identity=binding.identity,
            )
        )
    elif form == "sum" and formula and not _SUM_RE.match(formula):
        violations.append(
            Violation(
                "PRECEDENT_SHAPE",
                f"{concept.concept_id} è una somma, ma {binding.locator} non usa SUM/AVERAGE",
                [binding.locator],
                binding.concept_id,
                identity=binding.identity,
            )
        )
    elif form and cell:
        reasons.append("FORMULA_SHAPE_MATCH")

    precedents = [_normalise_locator(str(item)) for item in cell.get("precedents", [])]
    if _normalise_locator(binding.locator) in precedents:
        violations.append(
            Violation(
                "NO_SELF_REFERENCE",
                f"{binding.locator} dipende da sé stessa",
                [binding.locator],
                binding.concept_id,
                identity=binding.identity,
            )
        )

    claim_reasons, claim_violations = _claim_analysis(
        binding, concept, cell, claims
    )
    reasons.extend(claim_reasons)
    violations.extend(claim_violations)
    if violations:
        return None, violations

    explanation_parts = [
        f"{binding.locator} è l'unica proposta ammissibile per {binding.concept_id}."
    ]
    if "DECLARED_UNIT_MATCH" in reasons:
        explanation_parts.append("L'unità coincide con il concetto dichiarato.")
    if "CLAIM_LOCATOR_MATCH" in reasons:
        explanation_parts.append("Un claim già estratto indica la stessa cella.")
    elif "CLAIM_IDENTITY_MATCH" in reasons:
        explanation_parts.append("I claim già estratti sono coerenti con l'identità.")
    return replace(
        binding,
        reason_codes=sorted(set(reasons)),
        explanation=" ".join(explanation_parts),
    ), []


def _deduplicate_same_locator(
    group: Sequence[Binding],
) -> tuple[list[Binding], list[Violation]]:
    by_locator: dict[str, list[Binding]] = defaultdict(list)
    for binding in group:
        by_locator[_normalise_locator(binding.locator)].append(binding)
    result: list[Binding] = []
    violations: list[Violation] = []
    for locator in sorted(by_locator):
        candidates = sorted(
            by_locator[locator],
            key=lambda item: (-item.confidence, _canonical(asdict(item))),
        )
        units = {norm_unit(item.unit) for item in candidates if item.unit}
        forms = {
            _dimension(item.computational_form)
            for item in candidates
            if item.computational_form
        }
        numeric_values = [
            value for value in (_numeric(item.value) for item in candidates)
            if value is not None
        ]
        values_conflict = bool(
            numeric_values
            and any(
                not _values_match(numeric_values[0], value)
                for value in numeric_values[1:]
            )
        )
        if len(units) > 1 or len(forms) > 1 or values_conflict:
            violations.append(
                Violation(
                    "PROPOSAL_DECLARATION_CONFLICT",
                    f"Le proposte R5 per {candidates[0].locator} dichiarano "
                    "unità, forma o valore incompatibili",
                    [candidates[0].locator],
                    candidates[0].concept_id,
                    identity=candidates[0].identity,
                    relaxation={
                        "kind": "review_semantic_proposals",
                        "rationale": "la stessa cella non può avere due dichiarazioni economiche",
                    },
                )
            )
            continue
        chosen = candidates[0]
        evidence = sorted({item for candidate in candidates for item in candidate.evidence})
        reason_set = {
            reason
            for candidate in candidates
            for reason in candidate.reason_codes
        }
        if len(candidates) > 1:
            reason_set.add("DUPLICATE_PROPOSALS_COLLAPSED")
        reasons = sorted(reason_set)
        unit = next((item.unit for item in candidates if item.unit), chosen.unit)
        form = next(
            (
                item.computational_form
                for item in candidates
                if item.computational_form
            ),
            chosen.computational_form,
        )
        value = next(
            (item.value for item in candidates if item.value is not None),
            chosen.value,
        )
        result.append(
            replace(
                chosen,
                unit=unit,
                computational_form=form,
                value=value,
                evidence=evidence,
                reason_codes=reasons,
            )
        )
    return result, violations


def _select_identity_group(
    group: Sequence[Binding],
) -> tuple[Binding | None, list[Violation]]:
    candidates, declaration_conflicts = _deduplicate_same_locator(group)
    if declaration_conflicts:
        return None, declaration_conflicts
    if len(candidates) == 1:
        chosen = candidates[0]
        reasons = sorted({*chosen.reason_codes, "UNIQUE_IDENTITY_CANDIDATE"})
        return replace(chosen, reason_codes=reasons), []

    claim_grounded = [
        item for item in candidates if "CLAIM_LOCATOR_MATCH" in item.reason_codes
    ]
    if len(claim_grounded) == 1:
        chosen = claim_grounded[0]
        reasons = sorted({*chosen.reason_codes, "CLAIM_DISAMBIGUATED_IDENTITY"})
        return replace(
            chosen,
            reason_codes=reasons,
            explanation=(
                chosen.explanation
                + " Il locator del claim disambigua le altre celle candidate."
            ).strip(),
        ), []

    ranked = sorted(
        candidates,
        key=lambda item: (-item.confidence, _normalise_locator(item.locator)),
    )
    margin = round(ranked[0].confidence - ranked[1].confidence, 6)
    identity = ranked[0].identity
    violation = Violation(
        "UNIQUE_BINDING",
        f"{ranked[0].concept_id} ha {len(candidates)} celle candidate per la stessa "
        "identità; il resolver non sceglie sulla sola confidenza",
        [item.locator for item in candidates],
        ranked[0].concept_id,
        identity=identity,
        relaxation={
            "kind": "human_select_source_cell",
            "candidate": ranked[0].locator,
            "margin": margin,
            "rationale": "serve evidenza di locator o una distinzione d'identità esplicita",
        },
    )
    return None, [violation]


def _is_additive_formula(formula: str) -> bool:
    text = _clean(formula).upper()
    if not text.startswith("="):
        return False
    if _SUM_RE.match(text):
        return True
    # A plain chain of references joined by + or - preserves the unit.  More
    # complex grammar is deliberately left to R7 rather than guessed here.
    if "*" in text or "/" in text or "^" in text:
        return False
    return "+" in text[1:] or "-" in text[1:]


def _formula_unit_violations(
    admitted: Sequence[Binding], source: Mapping[str, Any]
) -> tuple[list[Binding], list[Violation]]:
    by_locator = {
        _normalise_locator(item.locator): item for item in admitted
    }
    rejected: set[str] = set()
    violations: list[Violation] = []
    for output in sorted(admitted, key=lambda item: item.identity_key):
        cell = _cell(source, output.locator)
        formula = _clean(cell.get("value"))
        if not _is_additive_formula(formula):
            continue
        inputs = [
            by_locator.get(_normalise_locator(str(locator)))
            for locator in cell.get("precedents", [])
        ]
        inputs = [item for item in inputs if item is not None and item.unit]
        if not output.unit or not inputs:
            continue
        units = {norm_unit(output.unit), *(norm_unit(item.unit) for item in inputs)}
        if len(units) == 1:
            output.reason_codes = sorted(
                {*output.reason_codes, "ADDITIVE_FORMULA_UNIT_MATCH"}
            )
            output.explanation = (
                output.explanation
                + " L'unità è coerente lungo la formula additiva."
            ).strip()
            continue
        rejected.add(output.identity_key)
        scope = [output.locator, *(item.locator for item in inputs)]
        violations.append(
            Violation(
                "FORMULA_UNIT_COHERENCE",
                f"La formula additiva {output.locator} collega unità incompatibili: "
                + ", ".join(sorted(units)),
                scope,
                output.concept_id,
                identity=output.identity,
                relaxation={
                    "kind": "review_formula_units",
                    "rationale": "somma e sottrazione richiedono la stessa unità economica",
                },
            )
        )
    return [item for item in admitted if item.identity_key not in rejected], violations


def resolve(
    bindings: Iterable[Binding | Mapping[str, Any]],
    concepts: Mapping[str, Concept | Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    source: Mapping[str, Any] | None = None,
    claims: Sequence[Mapping[str, Any]] | None = None,
) -> Resolution:
    """Resolve all proposals together; never mutate input objects."""

    concept_map = _coerce_concepts(concepts)
    proposals = _coerce_bindings(bindings)
    source_graph: Mapping[str, Any] = source or {}
    claim_items = sorted(
        [item for item in (claims or []) if isinstance(item, Mapping)],
        key=_canonical,
    )
    digest_input = {
        "proposals": [asdict(item) for item in proposals],
        "concepts": [asdict(concept_map[key]) for key in sorted(concept_map)],
        "source": source_graph,
        "claims": claim_items,
    }

    valid: list[Binding] = []
    violations: list[Violation] = []
    for proposal in proposals:
        candidate, candidate_violations = _validate_candidate(
            proposal,
            concept_map.get(proposal.concept_id),
            source_graph,
            claim_items,
        )
        if candidate is not None:
            valid.append(candidate)
        violations.extend(candidate_violations)

    groups: dict[str, list[Binding]] = defaultdict(list)
    for candidate in valid:
        groups[candidate.identity_key].append(candidate)

    admitted: list[Binding] = []
    for identity_key in sorted(groups):
        chosen, identity_violations = _select_identity_group(groups[identity_key])
        if chosen is not None:
            admitted.append(chosen)
        violations.extend(identity_violations)

    admitted, formula_violations = _formula_unit_violations(admitted, source_graph)
    violations.extend(formula_violations)
    admitted.sort(key=lambda item: (item.identity_key, _normalise_locator(item.locator)))
    violations.sort(
        key=lambda item: (
            item.code,
            _canonical(item.identity or {}),
            tuple(sorted(item.bindings)),
            item.detail,
        )
    )

    admitted_identities = {item.identity_key for item in admitted}
    unresolved_identities = {
        _canonical(item.identity)
        for item in violations
        if item.identity is not None
    }
    halted = bool(unresolved_identities - admitted_identities)
    return Resolution(
        admitted=admitted,
        violations=violations,
        halted=halted,
        input_digest="sha256:"
        + hashlib.sha256(_canonical(digest_input).encode("utf-8")).hexdigest(),
    )


def _embedded_concepts(proposals: Sequence[Mapping[str, Any]]) -> dict[str, Concept]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for proposal in sorted(proposals, key=_canonical):
        concept_id = _clean(
            proposal.get("concept_id") or proposal.get("economic_concept_id")
        )
        if concept_id:
            grouped[concept_id].append(proposal)

    concepts: dict[str, Concept] = {}
    for concept_id in sorted(grouped):
        group = grouped[concept_id]
        units = sorted(
            {
                _clean(
                    proposal.get("declared_unit")
                    or proposal.get("unit_canonical")
                    or proposal.get("unit")
                )
                for proposal in group
                if _clean(
                    proposal.get("declared_unit")
                    or proposal.get("unit_canonical")
                    or proposal.get("unit")
                )
            }
        )
        forms = sorted(
            {
                _clean(
                    proposal.get("declared_form")
                    or proposal.get("computational_form")
                )
                for proposal in group
                if _clean(
                    proposal.get("declared_form")
                    or proposal.get("computational_form")
                )
            }
        )
        labels = sorted(
            {
                _clean(
                    proposal.get("concept_label")
                    or proposal.get("concept")
                    or proposal.get("label")
                )
                for proposal in group
                if _clean(
                    proposal.get("concept_label")
                    or proposal.get("concept")
                    or proposal.get("label")
                )
            }
        )
        aliases = sorted(
            {
                _clean(alias)
                for proposal in group
                for alias in proposal.get("concept_aliases", [])
                if _clean(alias)
            }
        )
        concepts[concept_id] = Concept(
            concept_id=concept_id,
            label=labels[0] if labels else concept_id,
            # A conflicting embedded declaration is not resolved by input
            # order.  It remains unconstrained until R5 or a Human Stop supplies
            # one canonical declaration.
            unit=units[0] if len(units) == 1 else "",
            granularity="",
            form=forms[0] if len(forms) == 1 else "",
            aliases=aliases,
        )
    return concepts


def resolve_model(
    proposals: Sequence[Mapping[str, Any]],
    source_graph: Mapping[str, Any],
    concepts: Mapping[str, Concept | Mapping[str, Any]]
    | Sequence[Mapping[str, Any]]
    | None = None,
    claims: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """High-level JSON contract consumed by R5/R7 and command-line users."""

    declared = concepts if concepts is not None else _embedded_concepts(proposals)
    return resolve(proposals, declared, source_graph, claims).as_payload()


def _proposal_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        direct = [item for item in payload if isinstance(item, Mapping)]
        if all("proposals" in item for item in direct):
            return [
                {**proposal, "scenario": proposal.get("scenario") or sheet.get("sheet", "")}
                for sheet in direct
                for proposal in sheet.get("proposals", [])
                if isinstance(proposal, Mapping)
            ]
        return direct
    if not isinstance(payload, Mapping):
        return []
    for key in ("proposals", "bindings", "candidates"):
        if isinstance(payload.get(key), list):
            return [item for item in payload[key] if isinstance(item, Mapping)]
    return []


def proposals_from_semantics(
    payload: Any,
    concepts: Mapping[str, Concept | Mapping[str, Any]],
    floor: float = 0.6,
) -> list[Binding]:
    """Map the current sheet-semantics envelope to declared concept IDs."""

    concept_map = _coerce_concepts(concepts)
    aliases: dict[str, str] = {}
    for concept in concept_map.values():
        for alias in (concept.label, *concept.aliases):
            aliases[_dimension(alias)] = concept.concept_id

    sheets = payload if isinstance(payload, list) else payload.get("sheets", [])
    result: list[Binding] = []
    for sheet in sheets:
        if not isinstance(sheet, Mapping):
            continue
        for raw in sheet.get("proposals", []):
            if not isinstance(raw, Mapping) or float(raw.get("confidence") or 0) < floor:
                continue
            record_key = _clean(raw.get("record_key"))
            label = _clean(raw.get("col_header") if record_key else raw.get("row_label"))
            concept_id = aliases.get(_dimension(label))
            if not concept_id:
                continue
            result.append(
                Binding.from_mapping(
                    {
                        **raw,
                        "concept_id": concept_id,
                        "period": "" if record_key else raw.get("col_header"),
                        "scenario": record_key or sheet.get("sheet"),
                    }
                )
            )
    return _coerce_bindings(result)


def bindings_from_semantics(
    path: Path,
    concepts: Mapping[str, Concept | Mapping[str, Any]],
    floor: float = 0.6,
) -> list[Binding]:
    return proposals_from_semantics(
        json.loads(path.read_text(encoding="utf-8")), concepts, floor
    )


def load_concepts(path: Path) -> dict[str, Concept]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("concepts", raw) if isinstance(raw, Mapping) else raw
    return _coerce_concepts(items)


def _load_json(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve workbook semantic proposals as a global constraint system"
    )
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--concepts", type=Path)
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    proposals_payload = _load_json(args.proposals, [])
    proposals = _proposal_items(proposals_payload)
    source = _load_json(args.source, {})
    claims_payload = _load_json(args.claims, [])
    claims = (
        claims_payload.get("claims", [])
        if isinstance(claims_payload, Mapping)
        else claims_payload
    )
    concepts = load_concepts(args.concepts) if args.concepts else None
    result = resolve_model(proposals, source, concepts, claims)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"{result['status']}: {result['binding_count']} binding, "
        f"{result['coverage_limit_count']} coverage limit → {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
