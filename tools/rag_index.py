#!/usr/bin/env python3
"""Deterministic RAG proposals for explicitly declared coverage gaps.

This module deliberately stops before admission.  It indexes claims that an
ingestion pipeline has already extracted and, when a new source arrives,
ranks its claims against *existing, explicitly declared* gaps.  A match is an
auditable proposal, never a mutation of the gap or an admitted claim.

The implementation is local and reproducible: tokenisation, TF-IDF and cosine
similarity use the standard library.  PyYAML is used only when a YAML input is
provided.  Claim identity is delegated to ``tools.object_identity`` so that a
missing entity, metric or period is never guessed from similarity.

CLI examples::

    python3 tools/rag_index.py index \
        --input pipeline_out/live/keystone/claims.json \
        --out pipeline_out/rag/keystone_index.json

    python3 tools/rag_index.py propose \
        --index pipeline_out/rag/keystone_index.json \
        --source new_source_extraction.json \
        --gaps current_graph.json \
        --out pipeline_out/rag/review_proposals.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.object_identity import is_resolvable, metric_identity


INDEX_SCHEMA_VERSION = "panta.rag-index.v1"
PROPOSAL_SCHEMA_VERSION = "panta.rag-gap-proposals.v1"

# Structural words do not say what evidence is about.  The list is deliberately
# small and bilingual because the current corpus contains both Italian and
# English notes.  Domain terms (customer, diligence, covenant, etc.) remain.
_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "by", "da",
        "de", "dei", "del", "della", "di", "e", "for", "from", "gli",
        "i", "il", "in", "is", "it", "la", "le", "lo", "no", "non",
        "of", "on", "or", "per", "the", "to", "un", "una", "with",
    }
)
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_CLOSED_GAP_STATES = frozenset(
    {"ADMITTED", "CLOSED", "FILLED", "RESOLVED", "RETIRED", "SUPERSEDED"}
)
_IDENTITY_FIELDS = (
    "entity", "metric", "period", "scope", "basis", "measurement", "scenario",
    "unit", "currency",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _digest(value: Any) -> str:
    raw = _canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_as_text(item) for item in value)
    if isinstance(value, Mapping):
        return " ".join(_as_text(value[key]) for key in sorted(value))
    return str(value).strip()


def tokenize(text: str) -> list[str]:
    """Return deterministic unigrams and adjacent bigrams.

    Bigrams retain useful phrases such as ``customer contract`` without a
    language model.  They are emitted only from meaningful adjacent tokens.
    """
    unigrams = [
        token.casefold()
        for token in _TOKEN_RE.findall(text)
        if len(token) > 1 and token.casefold() not in _STOP_WORDS
    ]
    bigrams = [f"{left}::{right}" for left, right in zip(unigrams, unigrams[1:])]
    return unigrams + bigrams


def _idf(token_rows: Sequence[Sequence[str]]) -> dict[str, float]:
    count = max(1, len(token_rows))
    document_frequency: Counter[str] = Counter()
    for tokens in token_rows:
        document_frequency.update(set(tokens))
    return {
        token: math.log((1.0 + count) / (1.0 + frequency)) + 1.0
        for token, frequency in sorted(document_frequency.items())
    }


def _tfidf(tokens: Sequence[str], idf: Mapping[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    if not counts:
        return {}
    maximum = max(counts.values())
    return {
        token: (0.5 + 0.5 * frequency / maximum) * idf.get(token, 1.0)
        for token, frequency in sorted(counts.items())
    }


def cosine_similarity(
    left_tokens: Sequence[str],
    right_tokens: Sequence[str],
    idf: Mapping[str, float],
) -> float:
    """Sparse cosine similarity with stable floating-point rounding."""
    left = _tfidf(left_tokens, idf)
    right = _tfidf(right_tokens, idf)
    if not left or not right:
        return 0.0
    dot = sum(weight * right.get(token, 0.0) for token, weight in left.items())
    left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
    right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return round(dot / (left_norm * right_norm), 8)


def _source_value(claim: Mapping[str, Any], fallback: str = "") -> str:
    source = claim.get("source")
    if isinstance(source, Mapping):
        source = source.get("source_id") or source.get("artifact") or source.get("name")
    return _as_text(
        claim.get("source_id")
        or claim.get("source_doc")
        or source
        or fallback
    )


def _locator_value(claim: Mapping[str, Any], fallback: str = "") -> str:
    source = claim.get("source")
    source_locator = source.get("locator") if isinstance(source, Mapping) else ""
    return _as_text(claim.get("locator") or source_locator or fallback)


def _claim_text(claim: Mapping[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _as_text(claim.get("statement")),
            _as_text(claim.get("metric")),
            _as_text(claim.get("subject")),
            _as_text(claim.get("topic")),
            _as_text(claim.get("perimeter")),
            _as_text(claim.get("keywords")),
        )
        if part
    )


def _prepared_claim(
    raw_claim: Mapping[str, Any],
    *,
    source_fallback: str = "",
    locator_fallback: str = "",
) -> dict[str, Any]:
    claim = copy.deepcopy(dict(raw_claim))
    # Some extraction versions call the same temporal field ``as_of``.  This is
    # a field alias, not an inferred period: its exact value still goes through
    # object_identity.normalize_period via is_resolvable().
    if not claim.get("period") and claim.get("as_of"):
        claim["period"] = claim["as_of"]
    source_id = _source_value(claim, source_fallback)
    locator = _locator_value(claim, locator_fallback)
    text = _claim_text(claim)
    identity = metric_identity(claim)
    explicit_id = _as_text(claim.get("claim_id") or claim.get("stable_id") or claim.get("id"))
    claim_id = explicit_id or "claim:" + hashlib.sha256(
        _canonical_json(
            {
                "identity": identity,
                "source_id": source_id,
                "locator": locator,
                "statement": claim.get("statement"),
                "value": claim.get("value"),
            }
        ).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "claim_id": claim_id,
        "source_id": source_id,
        "source_version": _as_text(claim.get("source_version")),
        "locator": locator,
        "statement": _as_text(claim.get("statement")),
        "metric": _as_text(claim.get("metric")),
        "period": _as_text(claim.get("period")),
        "perimeter": _as_text(claim.get("perimeter")),
        "value": claim.get("value"),
        "unit": _as_text(claim.get("unit")),
        "text": text,
        "tokens": tokenize(text),
        "metric_identity": list(identity),
        "resolvable": is_resolvable(claim),
    }


def _looks_like_claim(value: Mapping[str, Any]) -> bool:
    return bool(
        (value.get("statement") or value.get("metric") or value.get("subject"))
        and not value.get("gap_id")
    )


def _claim_records(payload: Any) -> list[tuple[Mapping[str, Any], str, str]]:
    """Extract claims from common ingestion payloads without traversing arbitrary data."""
    if isinstance(payload, list):
        return [
            (item, "", "")
            for item in payload
            if isinstance(item, Mapping) and _looks_like_claim(item)
        ]
    if not isinstance(payload, Mapping):
        return []

    source = _source_value(payload)
    locator = _locator_value(payload)
    if isinstance(payload.get("claims"), list):
        return [
            (item, source, locator)
            for item in payload["claims"]
            if isinstance(item, Mapping) and _looks_like_claim(item)
        ]
    if isinstance(payload.get("documents"), list):
        rows: list[tuple[Mapping[str, Any], str, str]] = []
        for document in payload["documents"]:
            if not isinstance(document, Mapping):
                continue
            rows.extend(_claim_records(document))
        return rows
    if _looks_like_claim(payload):
        return [(payload, source, locator)]
    return []


def build_index(ingested_documents: Iterable[Any]) -> dict[str, Any]:
    """Build an immutable, content-addressed index from ingestion outputs.

    Duplicate claim/source/locator tuples collapse deterministically.  Claims
    with incomplete identity remain visible in the index statistics, but the
    proposal stage will never match them.
    """
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    input_claims = 0
    for payload in ingested_documents:
        for raw_claim, source, locator in _claim_records(payload):
            input_claims += 1
            prepared = _prepared_claim(
                raw_claim,
                source_fallback=source,
                locator_fallback=locator,
            )
            key = (
                prepared["claim_id"],
                prepared["source_id"],
                prepared["locator"],
            )
            by_key[key] = prepared

    claims = [by_key[key] for key in sorted(by_key)]
    idf = _idf([claim["tokens"] for claim in claims])
    body = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "claims": claims,
        "idf": {token: round(weight, 10) for token, weight in idf.items()},
        "statistics": {
            "input_claims": input_claims,
            "indexed_claims": len(claims),
            "resolvable_claims": sum(bool(claim["resolvable"]) for claim in claims),
            "unresolvable_claims": sum(not claim["resolvable"] for claim in claims),
        },
    }
    return {**body, "index_digest": _digest(body)}


def _gap_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = payload.get("coverage_gaps")
        if rows is None:
            rows = payload.get("coverage_limits")
        if rows is None:
            rows = payload.get("gaps")
        if rows is None and payload.get("gap_id"):
            rows = [payload]
    else:
        rows = None
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        gap = copy.deepcopy(dict(row))
        gap_id = _as_text(gap.get("gap_id") or gap.get("limit_id") or gap.get("coverage_limit_id"))
        if not gap_id:
            raise ValueError("every declared gap must have gap_id (or limit_id)")
        gap["gap_id"] = gap_id
        result.append(gap)
    return sorted(result, key=lambda item: item["gap_id"])


def _gap_is_active(gap: Mapping[str, Any]) -> bool:
    state = _as_text(
        gap.get("status")
        or gap.get("state")
        or gap.get("resolution_status")
    ).upper()
    return state not in _CLOSED_GAP_STATES


def _gap_text(gap: Mapping[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _as_text(gap.get("area")),
            _as_text(gap.get("statement") or gap.get("description")),
            _as_text(gap.get("effect")),
            _as_text(gap.get("reason_code")),
            _as_text(gap.get("keywords")),
        )
        if part
    )


def _declared_gap_identity(gap: Mapping[str, Any]) -> dict[str, str]:
    """Normalize only structured identity dimensions explicitly declared by the gap."""
    declared = gap.get("expected_identity") or gap.get("target_identity")
    if declared is None:
        declared = {field: gap.get(field) for field in _IDENTITY_FIELDS if gap.get(field)}
    if not isinstance(declared, Mapping) or not any(declared.get(field) for field in _IDENTITY_FIELDS):
        return {}
    identity_claim = {field: declared.get(field) for field in _IDENTITY_FIELDS}
    # Perimeter decomposition is allowed only when the declaration explicitly
    # supplied it as structured target data.
    if declared.get("perimeter"):
        identity_claim["perimeter"] = declared["perimeter"]
    normalized = metric_identity(identity_claim)
    return {
        field: normalized[index]
        for index, field in enumerate(_IDENTITY_FIELDS)
        if declared.get(field) and normalized[index]
    }


def _identity_factor(
    gap_identity: Mapping[str, str],
    claim_identity: Sequence[str],
) -> tuple[bool, float, list[str], list[str]]:
    if not gap_identity:
        return True, 0.0, [], []
    matched: list[str] = []
    mismatched: list[str] = []
    candidate = dict(zip(_IDENTITY_FIELDS, claim_identity))
    for field, expected in gap_identity.items():
        if candidate.get(field) == expected:
            matched.append(field)
        else:
            mismatched.append(field)
    score = len(matched) / len(gap_identity)
    return not mismatched, round(score, 8), matched, mismatched


def _gap_state(gap: Mapping[str, Any]) -> str:
    return _as_text(
        gap.get("status")
        or gap.get("state")
        or gap.get("resolution_status")
        or "DECLARED"
    )


def _candidate_summary(claim: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": claim["claim_id"],
        "statement": claim["statement"],
        "metric": claim["metric"],
        "period": claim["period"],
        "perimeter": claim["perimeter"],
        "value": claim["value"],
        "unit": claim["unit"],
        "metric_identity": claim["metric_identity"],
    }


def propose_gap_candidates(
    index: Mapping[str, Any],
    new_source: Any,
    declared_gaps: Any,
    *,
    top_k: int = 3,
    min_score: float = 0.12,
) -> dict[str, Any]:
    """Rank new-source claims for declared gaps without mutating either input.

    The returned payload is deliberately not consumable as an admission event:
    every proposal is ``PROPOSED`` / ``HUMAN_REVIEW`` / ``PENDING`` and carries
    ``auto_admitted: false``.  A separate human-governed admission workflow must
    make the actual state change.
    """
    if index.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise ValueError(f"unsupported index schema: {index.get('schema_version')!r}")
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    if not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be between 0 and 1")

    gaps = _gap_records(declared_gaps)
    original_gaps = copy.deepcopy(gaps)
    incoming = [
        _prepared_claim(raw, source_fallback=source, locator_fallback=locator)
        for raw, source, locator in _claim_records(new_source)
    ]
    incoming.sort(key=lambda item: (item["claim_id"], item["source_id"], item["locator"]))

    existing_keys = {
        (claim.get("claim_id"), claim.get("source_id"), claim.get("locator"))
        for claim in index.get("claims", [])
        if isinstance(claim, Mapping)
    }
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_incoming: set[tuple[str, str, str]] = set()
    for claim in incoming:
        key = (claim["claim_id"], claim["source_id"], claim["locator"])
        if key in seen_incoming or key in existing_keys:
            code = "ALREADY_INDEXED"
            reason = "Il claim è già presente nell’indice derivato."
        elif not claim["resolvable"]:
            code = "UNRESOLVABLE_IDENTITY"
            reason = "Entity, metric e period non sono tutti risolvibili; nessun accoppiamento è consentito."
        elif not claim["source_id"] or not claim["locator"]:
            code = "MISSING_PROVENANCE"
            reason = "Source e locator sono obbligatori per una proposta auditabile."
        else:
            eligible.append(claim)
            seen_incoming.add(key)
            continue
        excluded.append(
            {
                "claim_id": claim["claim_id"],
                "source_id": claim["source_id"],
                "locator": claim["locator"],
                "reason_code": code,
                "reason": reason,
            }
        )
        seen_incoming.add(key)

    gap_tokens = {gap["gap_id"]: tokenize(_gap_text(gap)) for gap in gaps}
    corpus_tokens = [
        list(claim.get("tokens", []))
        for claim in index.get("claims", [])
        if isinstance(claim, Mapping)
    ] + [claim["tokens"] for claim in eligible] + list(gap_tokens.values())
    idf = _idf(corpus_tokens)

    proposals: list[dict[str, Any]] = []
    proposal_count_by_gap: Counter[str] = Counter()
    for gap in gaps:
        if not _gap_is_active(gap):
            continue
        gap_identity = _declared_gap_identity(gap)
        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for claim in eligible:
            compatible, identity_score, matched, mismatched = _identity_factor(
                gap_identity, claim["metric_identity"]
            )
            if not compatible:
                continue
            lexical = cosine_similarity(gap_tokens[gap["gap_id"]], claim["tokens"], idf)
            shared_terms = sorted(
                set(gap_tokens[gap["gap_id"]]).intersection(claim["tokens"])
            )
            if not shared_terms:
                continue
            score = lexical if not gap_identity else 0.75 * lexical + 0.25 * identity_score
            score = round(score, 8)
            if score < min_score:
                continue
            stable_rank = "|".join((claim["claim_id"], claim["source_id"], claim["locator"]))
            factors = {
                "lexical_cosine": lexical,
                "identity_match": identity_score,
                "identity_dimensions_matched": matched,
                "identity_dimensions_mismatched": mismatched,
                "shared_terms": shared_terms[:12],
            }
            proposal_key = {
                "gap_id": gap["gap_id"],
                "claim_id": claim["claim_id"],
                "source_id": claim["source_id"],
                "locator": claim["locator"],
            }
            reason_parts = [
                "Claim risolvibile e pertinente alla lacuna esplicitamente dichiarata",
                "termini condivisi: " + ", ".join(shared_terms[:6]),
            ]
            if gap_identity:
                reason_parts.append("identità dichiarata compatibile: " + ", ".join(matched))
            reason_parts.append("nessuna ammissione automatica")
            proposal = {
                "proposal_id": "rag-proposal:" + hashlib.sha256(
                    _canonical_json(proposal_key).encode("utf-8")
                ).hexdigest()[:16],
                "gap_id": gap["gap_id"],
                "candidate_claim": _candidate_summary(claim),
                "source": {
                    "source_id": claim["source_id"],
                    "source_version": claim["source_version"],
                    "locator": claim["locator"],
                },
                "score": score,
                "score_factors": factors,
                "status": "PROPOSED",
                "review_status": "HUMAN_REVIEW",
                "admission_status": "PENDING",
                "auto_admitted": False,
                "reason": "; ".join(reason_parts) + ".",
            }
            ranked.append((score, stable_rank, proposal))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        for _, _, proposal in ranked[:top_k]:
            proposals.append(proposal)
            proposal_count_by_gap[gap["gap_id"]] += 1

    proposals.sort(key=lambda item: (item["gap_id"], -item["score"], item["proposal_id"]))
    gap_snapshots = [
        {
            "gap_id": gap["gap_id"],
            "active_for_proposals": _gap_is_active(gap),
            "state_before": _gap_state(gap),
            "state_after": _gap_state(gap),
            "unchanged": True,
            "proposal_count": proposal_count_by_gap[gap["gap_id"]],
        }
        for gap in gaps
    ]
    gap_digest = _digest(original_gaps)
    source_descriptor = {
        "source_ids": sorted({claim["source_id"] for claim in incoming if claim["source_id"]}),
        "claim_count": len(incoming),
        "source_digest": _digest(incoming),
    }
    body = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "index_digest": index.get("index_digest"),
        "new_source": source_descriptor,
        # The declarations are carried forward byte-for-byte at the object
        # level.  Consumers do not need to reconstruct persistent gap state
        # from a proposal or infer that a proposed match closed anything.
        "declared_gaps": original_gaps,
        "declared_gap_digest_before": gap_digest,
        "declared_gap_digest_after": gap_digest,
        "gap_snapshots": gap_snapshots,
        "proposals": proposals,
        "excluded_candidates": sorted(
            excluded,
            key=lambda item: (item["reason_code"], item["claim_id"], item["source_id"]),
        ),
        "governance": {
            "auto_admission": False,
            "required_next_step": "HUMAN_REVIEW",
            "gap_mutation_performed": False,
        },
        "statistics": {
            "declared_gaps": len(gaps),
            "active_declared_gaps": sum(_gap_is_active(gap) for gap in gaps),
            "incoming_claims": len(incoming),
            "eligible_claims": len(eligible),
            "excluded_claims": len(excluded),
            "proposals": len(proposals),
        },
    }
    return {**body, "proposal_batch_digest": _digest(body)}


def _load_yaml(text: str) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on local installation
        raise RuntimeError("PyYAML is required to read YAML inputs") from exc
    return yaml.safe_load(text)


def load_payload(path: Path) -> Any:
    """Load JSON/YAML, a frontmatter claim note, or a live-store directory."""
    if path.is_dir():
        claims_file = path / "claims.json"
        if not claims_file.exists():
            raise ValueError(f"directory has no claims.json: {path}")
        return load_payload(claims_file)
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        return _load_yaml(text)
    if suffix == ".md" and text.startswith("---"):
        end = text.find("\n---", 3)
        if end < 0:
            raise ValueError(f"unterminated YAML frontmatter: {path}")
        frontmatter = _load_yaml(text[3:end]) or {}
        if not isinstance(frontmatter, Mapping):
            raise ValueError(f"frontmatter must be an object: {path}")
        body = text[end + 4 :].strip()
        claim = dict(frontmatter)
        claim.setdefault("statement", body)
        return claim
    raise ValueError(f"unsupported input format: {path}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index ingested claims and propose human-reviewed matches to declared gaps"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    index_parser = subcommands.add_parser("index", help="build a deterministic derived index")
    index_parser.add_argument("--input", type=Path, action="append", required=True)
    index_parser.add_argument("--out", type=Path, required=True)

    propose_parser = subcommands.add_parser(
        "propose", help="rank claims from a new source against declared gaps"
    )
    propose_parser.add_argument("--index", type=Path, required=True)
    propose_parser.add_argument("--source", type=Path, required=True)
    propose_parser.add_argument("--gaps", type=Path, required=True)
    propose_parser.add_argument("--out", type=Path, required=True)
    propose_parser.add_argument("--top-k", type=int, default=3)
    propose_parser.add_argument("--min-score", type=float, default=0.12)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "index":
        result = build_index(load_payload(path) for path in args.input)
        _write_json(args.out, result)
        print(
            f"indexed {result['statistics']['indexed_claims']} claims "
            f"({result['statistics']['resolvable_claims']} resolvable) -> {args.out}"
        )
        return 0

    index = load_payload(args.index)
    result = propose_gap_candidates(
        index,
        load_payload(args.source),
        load_payload(args.gaps),
        top_k=args.top_k,
        min_score=args.min_score,
    )
    _write_json(args.out, result)
    print(
        f"proposed {result['statistics']['proposals']} candidates for "
        f"{result['statistics']['active_declared_gaps']} active declared gaps -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
