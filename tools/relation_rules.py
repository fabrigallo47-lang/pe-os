#!/usr/bin/env python3
"""Deterministic relation orchestration for the PANTA runtime graph.

The five runtime relations do not share one inference rule.  This module owns
their producer registry and the provenance envelope attached to every emitted
edge.  Rules may either materialize a deterministic edge or create a proposal;
proposals are never traversable and require a later human decision.

The current deterministic producers are:

* complete metric identity + incompatible values -> ``CONTRADICTS``;
* explicit claim inputs -> ``DERIVES_FROM``;
* compiled formula precedents -> ``DRIVES``;
* admitted claim/position binding -> ``SUPPORTS`` (or ``CONTRADICTS`` when the
  binding gate rejects the claim).

``CONDITIONS`` is registered here but its producer is intentionally deferred to
PAN-69, where its propagation semantics are verified before it is connected.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.object_identity import (  # noqa: E402
    claims_from_e3,
    is_resolvable,
    metric_identity,
    values_conflict,
)


SCHEMA_VERSION = "panta.relation-orchestration/1.0"
RULE_VERSION = "pan68-1.0"
RUNTIME_RELATIONS = frozenset(
    {"SUPPORTS", "CONTRADICTS", "DERIVES_FROM", "DRIVES", "CONDITIONS"}
)

RULES: dict[str, dict[str, str]] = {
    "IDENTITY_VALUE_CONFLICT": {
        "relation_type": "CONTRADICTS",
        "mode": "DETERMINISTIC",
        "basis": "complete metric identity plus bound-aware incompatible values",
    },
    "EXPLICIT_DERIVATION_INPUT": {
        "relation_type": "DERIVES_FROM",
        "mode": "DETERMINISTIC",
        "basis": "source claim identifier explicitly declared by the derived claim",
    },
    "FORMULA_PRECEDENT_DRIVES": {
        "relation_type": "DRIVES",
        "mode": "DETERMINISTIC",
        "basis": "compiled formula input is a declared precedent of the output node",
    },
    "CLAIM_POSITION_BINDING_SUPPORTS": {
        "relation_type": "SUPPORTS",
        "mode": "DETERMINISTIC",
        "basis": "claim passed the deterministic position binding gate",
    },
    "CLAIM_POSITION_BINDING_REJECTS": {
        "relation_type": "CONTRADICTS",
        "mode": "DETERMINISTIC",
        "basis": "claim failed the deterministic position binding gate",
    },
    "DECLARED_POSITION_CONDITION": {
        "relation_type": "CONDITIONS",
        "mode": "DETERMINISTIC",
        "basis": "typed prerequisite explicitly declared by a governed position",
    },
    "PROSE_DERIVATION_CANDIDATE": {
        "relation_type": "DERIVES_FROM",
        "mode": "PROPOSAL",
        "basis": "free-text derivation mentions a candidate source metric",
    },
    "NARRATIVE_SUPPORT_CANDIDATE": {
        "relation_type": "SUPPORTS",
        "mode": "PROPOSAL",
        "basis": "quantitative and narrative claims share subject and underwriting area",
    },
}


def relation_rule(rule_id: str, *, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the immutable provenance envelope for one registered rule."""
    if rule_id not in RULES:
        raise KeyError(f"unknown relation rule: {rule_id}")
    rule = {"rule_id": rule_id, "rule_version": RULE_VERSION, **RULES[rule_id]}
    if evidence:
        rule["evidence"] = copy.deepcopy(dict(evidence))
    return rule


def annotate_edge(
    edge: Mapping[str, Any],
    rule_id: str,
    *,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy an edge and attach the rule that produced it."""
    output = copy.deepcopy(dict(edge))
    expected = RULES[rule_id]["relation_type"]
    actual = output.get("rel") or output.get("relation_type")
    if actual and actual != expected:
        raise ValueError(f"rule {rule_id} produces {expected}, not {actual}")
    if "rel" not in output and "relation_type" not in output:
        output["relation_type"] = expected
    output["relation_rule"] = relation_rule(rule_id, evidence=evidence)
    return output


def _claim_id(claim: Mapping[str, Any], fallback: str) -> str:
    return str(
        claim.get("claim_id")
        or claim.get("stable_id")
        or claim.get("id")
        or fallback
    )


def _source_identity(claim: Mapping[str, Any]) -> tuple[str, str]:
    source = claim.get("source")
    source_record = source if isinstance(source, Mapping) else {}
    source_id = (
        claim.get("source_id")
        or claim.get("source_doc")
        or source_record.get("source_id")
        or source_record.get("artifact")
        or (source if isinstance(source, str) else "")
    )
    source_version = (
        claim.get("source_version_id")
        or claim.get("source_version")
        or source_record.get("source_version_id")
        or source_record.get("source_version")
        or ""
    )
    return str(source_id), str(source_version)


def _explicit_inputs(claim: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("derivation_claim_ids", "input_claim_ids", "precedent_claim_ids"):
        raw = claim.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            values.extend(raw)
    derivation = claim.get("derivation")
    if isinstance(derivation, Mapping):
        for key in ("claim_ids", "inputs", "precedents"):
            raw = derivation.get(key)
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
                values.extend(raw)
    return sorted({str(value) for value in values if str(value).strip()})


def _subject(claim: Mapping[str, Any]) -> str:
    return str(claim.get("subject") or claim.get("entity") or "").strip().lower()


def _metric(claim: Mapping[str, Any]) -> str:
    return str(claim.get("metric") or claim.get("subject") or "").strip().lower()


def _has_value(claim: Mapping[str, Any]) -> bool:
    value = claim.get("value")
    return value is not None and str(value).strip() != ""


def _overlaps(left: str, right: str) -> bool:
    return bool(left and right and (left == right or left in right or right in left))


def _edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(edge.get("source") or edge.get("from_model_node_id") or ""),
        str(edge.get("target") or edge.get("to_model_node_id") or ""),
        str(edge.get("rel") or edge.get("relation_type") or ""),
    )


def _proposal(
    source: str,
    target: str,
    rule_id: str,
    *,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "relation_type": RULES[rule_id]["relation_type"],
        "proposal_status": "PENDING_HUMAN_REVIEW",
        "llm_authority": "PROPOSE_ONLY",
        "adjudication": "HUMAN_REQUIRED",
        "canonical": False,
        "relation_rule": relation_rule(rule_id, evidence=evidence),
    }


def audit_relation_outputs(
    edges: Iterable[Mapping[str, Any]],
    proposals: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Measure deterministic coverage without counting proposals as graph arcs."""
    selected = [
        dict(edge)
        for edge in edges
        if str(edge.get("rel") or edge.get("relation_type") or "") in RUNTIME_RELATIONS
    ]
    proposed = [dict(item) for item in proposals]
    deterministic = 0
    unclassified = 0
    by_relation: dict[str, Counter[str]] = defaultdict(Counter)
    for edge in selected:
        relation = str(edge.get("rel") or edge.get("relation_type"))
        mode = str(edge.get("relation_rule", {}).get("mode") or "UNCLASSIFIED")
        by_relation[relation][mode.lower()] += 1
        if mode == "DETERMINISTIC":
            deterministic += 1
        else:
            unclassified += 1
    for item in proposed:
        relation = str(item.get("relation_type") or item.get("rel") or "")
        by_relation[relation]["proposals"] += 1

    total_edges = len(selected)
    all_outputs = total_edges + len(proposed)
    return {
        "schema_version": SCHEMA_VERSION,
        "materialized_edge_count": total_edges,
        "deterministic_edge_count": deterministic,
        "unclassified_edge_count": unclassified,
        "proposal_count": len(proposed),
        "deterministic_edge_pct": (
            round(100.0 * deterministic / total_edges, 2) if total_edges else 0.0
        ),
        "deterministic_output_pct": (
            round(100.0 * deterministic / all_outputs, 2) if all_outputs else 0.0
        ),
        "by_relation": {
            relation: dict(sorted(counts.items()))
            for relation, counts in sorted(by_relation.items())
        },
    }


def orchestrate_claim_relations(
    claims: Sequence[Mapping[str, Any]],
    claim_ids: Sequence[str | None] | None = None,
    *,
    area_resolver: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Return deterministic claim edges and non-canonical ambiguous proposals."""
    items = [dict(claim) for claim in claims]
    ids = [
        str(claim_ids[index]) if claim_ids and claim_ids[index] else _claim_id(claim, f"claim:{index:04d}")
        for index, claim in enumerate(items)
    ]
    known_ids = set(ids)
    edges: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []

    groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, claim in enumerate(items):
        if is_resolvable(claim):
            groups[metric_identity(claim)].append(index)
    for identity, members in sorted(groups.items()):
        for offset, left_index in enumerate(members):
            for right_index in members[offset + 1:]:
                left, right = items[left_index], items[right_index]
                if _source_identity(left) == _source_identity(right):
                    continue
                conflict, reason = values_conflict(left, right)
                if not conflict:
                    continue
                left_id, right_id = ids[left_index], ids[right_index]
                left_direction = str(left.get("direction") or "")
                right_direction = str(right.get("direction") or "")
                if left_direction == "contradicts" and right_direction == "supports":
                    source, target = right_id, left_id
                elif right_direction == "contradicts" and left_direction == "supports":
                    source, target = left_id, right_id
                else:
                    source, target = sorted((left_id, right_id))
                edges.append(annotate_edge(
                    {"source": source, "target": target, "rel": "CONTRADICTS", "canonical": True},
                    "IDENTITY_VALUE_CONFLICT",
                    evidence={"identity": list(identity), "reason": reason},
                ))

    for index, claim in enumerate(items):
        current_id = ids[index]
        explicit = [value for value in _explicit_inputs(claim) if value in known_ids and value != current_id]
        for source_id in explicit:
            edges.append(annotate_edge(
                {"source": current_id, "target": source_id, "rel": "DERIVES_FROM", "canonical": True},
                "EXPLICIT_DERIVATION_INPUT",
                evidence={"declared_input_claim_id": source_id},
            ))

        derivation = claim.get("derivation")
        if explicit or not isinstance(derivation, str) or len(derivation.strip()) < 5:
            continue
        derivation_lower = derivation.lower()
        for candidate_index, candidate in enumerate(items):
            if candidate_index == index:
                continue
            candidate_metric = _metric(candidate)
            if len(candidate_metric) < 5 or candidate_metric not in derivation_lower:
                continue
            proposals.append(_proposal(
                current_id,
                ids[candidate_index],
                "PROSE_DERIVATION_CANDIDATE",
                evidence={"matched_metric": candidate_metric},
            ))

    if area_resolver is not None:
        for narrative_index, narrative in enumerate(items):
            if _has_value(narrative):
                continue
            narrative_subject = _subject(narrative)
            narrative_area = area_resolver(str(narrative.get("topic") or narrative.get("metric") or ""))
            if not narrative_subject or narrative_area == "Other":
                continue
            for evidence_index, evidence_claim in enumerate(items):
                if narrative_index == evidence_index or not _has_value(evidence_claim):
                    continue
                evidence_subject = _subject(evidence_claim)
                evidence_area = area_resolver(str(evidence_claim.get("topic") or evidence_claim.get("metric") or ""))
                if _overlaps(narrative_subject, evidence_subject) and narrative_area == evidence_area:
                    proposals.append(_proposal(
                        ids[evidence_index],
                        ids[narrative_index],
                        "NARRATIVE_SUPPORT_CANDIDATE",
                        evidence={"area": narrative_area, "subject": narrative_subject},
                    ))

    edges_by_key = {_edge_key(edge): edge for edge in edges}
    proposals_by_key = {_edge_key(item): item for item in proposals if _edge_key(item) not in edges_by_key}
    ordered_edges = [edges_by_key[key] for key in sorted(edges_by_key)]
    ordered_proposals = [proposals_by_key[key] for key in sorted(proposals_by_key)]
    return {
        "schema_version": SCHEMA_VERSION,
        "edges": ordered_edges,
        "proposals": ordered_proposals,
        "audit": audit_relation_outputs(ordered_edges, ordered_proposals),
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit deterministic PANTA relation production")
    parser.add_argument("--claims", type=Path, required=True, help="E3 e3_claims.json")
    parser.add_argument("--execution-mapping", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = json.loads(args.claims.read_text(encoding="utf-8"))
    claims = claims_from_e3(payload)
    result = orchestrate_claim_relations(claims)
    execution_edges: list[dict[str, Any]] = []
    if args.execution_mapping:
        mapping = json.loads(args.execution_mapping.read_text(encoding="utf-8"))
        for raw in mapping.get("directed_model_edges", []):
            edge = dict(raw)
            edge.setdefault("relation_type", "DRIVES")
            if not edge.get("relation_rule"):
                edge = annotate_edge(
                    edge,
                    "FORMULA_PRECEDENT_DRIVES",
                    evidence={"formula_or_function_ref": edge.get("formula_or_function_ref")},
                )
            execution_edges.append(edge)

    all_edges = [*result["edges"], *execution_edges]
    report = {
        "schema_version": SCHEMA_VERSION,
        "claims_file": str(args.claims),
        "execution_mapping": str(args.execution_mapping) if args.execution_mapping else None,
        "audit": audit_relation_outputs(all_edges, result["proposals"]),
        "rules": RULES,
        "deterministic_edge_sample": all_edges[:20],
        "proposal_sample": result["proposals"][:20],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    audit = report["audit"]
    print(
        f"{audit['deterministic_edge_count']}/{audit['materialized_edge_count']} "
        f"materialized relation edges deterministic ({audit['deterministic_edge_pct']:.2f}%); "
        f"{audit['proposal_count']} ambiguous proposals"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
