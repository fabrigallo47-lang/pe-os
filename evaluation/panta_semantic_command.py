#!/usr/bin/env python3
"""One-case stdin/stdout adapter wiring PANTA's real semantic pipeline into
evaluation/cli.py's --system-command protocol (evaluation/runner.py::CommandSystem).

Calls tools.extract_v2_physical.parse_source -> annotate_chunk -> validate ->
assemble exactly as tools/extraction_test_ui.py's step 2 and the production
CLI do. No UI-only approximation, no re-implemented scoring logic here.

Three real, structural gaps this surfaces rather than hides -- read scores
in light of these, they are findings about production, not adapter bugs:

  1. source_id is one value per physical INPUT FILE (production's source-
     registry model: one chunk -> one source_record -> one source_id for
     every claim drawn from it). A fixture that packs several distinct
     sources into one physical document (e.g. "Reported accounts" and
     "Independent QoE" as sections of the same .md file) will score below
     100% on semantic_grounding_accuracy for that reason alone.
  2. derivation is a free-text expression in production ("state the
     computation"); operand_claim_ids is populated ONLY when the operand is
     another claim in the SAME annotate_chunk tool call (via
     derivation_operand_indices, resolved by derive_relations() after
     validate() assigns real claim_ids). An operand from a different chunk,
     or a plain number in the fragment that was never extracted as its own
     claim, still leaves operand_claim_ids empty.
  3. DERIVED_FROM edges ARE produced (see derive_relations(), same-batch
     operands only). BEARS_ON (claim->question) and the vault's
     SUPERSEDES/CONTRADICTS/CONFIRMS revision-tracking are NOT -- those
     require, respectively, tools/binding_proposer.py's real vault question
     index and the .claude/skills/contradictions agentic workflow, neither
     of which this eval fixture has an equivalent of. relations only ever
     contains DERIVED_FROM edges.
  4. annotate_chunk's prompt is deal-name + source metadata + chunk body
     only; it never sees a case's `query` field (the per-case task text
     the optional OpenAI baseline in semantic_teacher.py DOES read). This
     is intentional fidelity, not an oversight -- production's chunk
     annotation has no per-document task-instruction channel.

Run manually:
  echo '{...case json...}' | .venv/bin/python evaluation/panta_semantic_command.py

Run through the evaluator:
  make semantic-claim-eval SYSTEM_COMMAND='.venv/bin/python evaluation/panta_semantic_command.py'
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import (  # noqa: E402
    MODEL, annotate_chunk, assemble, derive_relations, parse_source,
    resolve_operand_claim_ids, validate,
)
from tools.llm_provider import anthropic_client_kwargs, configured_api_key  # noqa: E402


def _inside_root(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def _source_id_for(input_id: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in input_id.upper())
    return f"SRC-{slug[:24]}".strip("-")


def _client() -> Any:
    import anthropic

    api_key = configured_api_key()
    if not api_key:
        raise RuntimeError("no Anthropic API key configured (ANTHROPIC_API_KEY)")
    return anthropic.Anthropic(**anthropic_client_kwargs(api_key))


def _load_chunks(case: Mapping[str, Any]) -> tuple[list, dict[str, str]]:
    """Returns (chunks, source_path -> input_id). Raises on any load failure --
    a case with an unreadable input has no honest prediction to offer."""
    chunks: list = []
    path_to_input: dict[str, str] = {}
    for item in case.get("inputs", []):
        path = (ROOT / str(item["path"])).resolve()
        if not _inside_root(path):
            raise ValueError(f"input path escapes repository root: {item['path']}")
        expected_hash = item.get("sha256")
        if expected_hash and hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"sha256 mismatch for {item['path']}")
        metadata = item.get("metadata") or {}
        source_record = {
            "source_id": _source_id_for(item["input_id"]),
            "name": path.name,
            "party": "unknown",
            "doc_type": item.get("format", "Other"),
            "effective_date": metadata.get("effective_date") or "",
            "known_at": metadata.get("known_at") or "",
            "manifest": ["ALL"],
        }
        file_chunks = parse_source(path, source_record=source_record)
        for chunk in file_chunks:
            path_to_input[chunk.source_path] = item["input_id"]
        chunks.extend(file_chunks)
    return chunks, path_to_input


def _claim_to_prediction(claim: Any, input_id: str,
                         operand_ids: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "claim_id": claim.claim_id,
        "statement": claim.statement,
        "source_id": claim.source_id,
        "input_id": input_id,
        "locator": {"type": "generic", "value": claim.locator},
        "entity": claim.entity,
        "metric": claim.metric,
        "measurement": claim.measurement,
        "value": claim.value if claim.value is not None else claim.value_raw,
        "unit": claim.unit,
        "bound": claim.bound,
        "period_canonical": claim.period_canonical,
        "scope": claim.scope,
        "basis": claim.basis,
        "scenario": claim.scenario,
        "epistemic_class": claim.epistemic_class,
        "claim_kind": claim.claim_kind,
    }
    if claim.definition_id:
        out["definition_id"] = claim.definition_id
    # `direction` (supports/contradicts/context) is PANTA-internal thesis
    # signal, not part of a claim's semantic identity or its factual content.
    # This benchmark's gold never sets it, but semantic_exact_match compares
    # it anyway -- so emitting a value where the reference states none failed
    # 83% of gold claims on that field alone, masking every other field being
    # right. Not emitting it is the honest read: gold makes no claim about
    # direction, so there is nothing here to agree or disagree with.
    # Production still populates it; this is an adapter-level omission.
    if claim.known_at:
        out["known_at"] = claim.known_at
    if claim.period:
        out["period"] = claim.period
    if claim.derivation:
        # A derived value has to name what it was computed FROM, or nobody
        # downstream can re-check it (dictionary section 11.3: the formula output
        # "porta input IDs"). Operands the model referenced positionally are
        # resolved to real claim_ids by resolve_operand_claim_ids(); an operand
        # that was a bare number in the text, or lived in another chunk, stays
        # unlisted rather than being invented.
        out["derivation"] = {
            "expression": claim.derivation,
            "operand_claim_ids": list(operand_ids or []),
        }
    return out


def main() -> int:
    case = json.load(sys.stdin)
    chunks, path_to_input = _load_chunks(case)
    client = _client()
    raw_claims = []
    chunk_errors = []
    for chunk in chunks:
        try:
            raw_claims.extend(annotate_chunk(chunk, client, deal=case["test_id"], raise_errors=True))
        except Exception as exc:  # noqa: BLE001 -- one bad chunk must not void the rest
            chunk_errors.append(f"{chunk.chunk_id}: {type(exc).__name__}: {exc}")

    canonicals = [validate(r) for r in raw_claims]
    graph = assemble(canonicals)
    operand_ids = resolve_operand_claim_ids(graph.claims)
    claims = [
        _claim_to_prediction(c, path_to_input.get(c.source_path, "unknown-input"),
                             operand_ids.get(c.claim_id))
        for c in graph.claims
    ]
    # The per-claim eval schema has additionalProperties:false, so a real
    # PAN-125 derivation-disagreement flag (the model's own stated arithmetic
    # not matching its own stated value) has nowhere to live on the claim
    # object itself. Surface it in metadata instead of silently dropping
    # it -- the UI shows the same flag with a ⚑; a prediction that hides it
    # would look more trustworthy than the pipeline actually claims to be.
    derivation_warnings = [
        {"claim_id": c.claim_id, "errors": c.nonblocking_validation_errors}
        for c in graph.claims
        if c.nonblocking_validation_errors
    ]
    prediction = {
        "schema_version": "panta-eval.prediction/1.0",
        "test_id": case["test_id"],
        "status": "success" if claims else "abstained",
        "claims": claims,
        "relations": derive_relations(graph.claims),
        "metadata": {
            "generator": "panta-extract-v2-physical",
            "model": MODEL,
            "chunk_count": len(chunks),
            "rejected_count": graph.rejected_count,
            "chunk_errors": chunk_errors,
            "derivation_warnings": derivation_warnings,
        },
    }
    print(json.dumps(prediction, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 -- CommandSystem reads stderr + nonzero exit as the error prediction
        print(f"panta semantic command failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
