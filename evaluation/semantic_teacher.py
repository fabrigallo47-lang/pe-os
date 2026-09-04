"""Optional GPT-5.6 Sol semantic-claim baseline and silver-label assistant.

The module implements the evaluator's one-case JSON stdin/stdout protocol.  It
only consumes the case metadata and source documents supplied by CommandSystem;
gold labels never reach the model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from evaluation.schema import validate_prediction


ROOT = Path(__file__).resolve().parents[1]
TEXT_FORMATS = {"md", "txt", "csv", "tsv", "json", "html", "xml"}


CLAIM_PROPERTIES: dict[str, Any] = {
    "claim_id": {"type": "string", "minLength": 1},
    "statement": {"type": "string", "minLength": 1},
    "source_id": {"type": "string", "minLength": 1},
    "input_id": {"type": "string", "minLength": 1},
    "locator_value": {"type": "string", "minLength": 1},
    "source_quote": {"type": "string"},
    "entity": {"type": "string", "minLength": 1},
    "metric": {"type": "string", "minLength": 1},
    "measurement": {"type": "string", "minLength": 1},
    "value": {"type": ["string", "number", "boolean", "null"]},
    "unit": {"type": ["string", "null"]},
    "bound": {"enum": ["EXACT", "AT_LEAST", "AT_MOST", "APPROXIMATE", "RANGE", "NONE"]},
    "period": {"type": ["string", "null"]},
    "period_canonical": {"type": "string", "minLength": 1},
    "scope": {"enum": ["consolidated", "standalone", "customer", "segment", "unspecified"]},
    "basis": {"enum": ["SellerView", "QoEView", "FirmView", "CovenantView", "ReportedView", "unspecified"]},
    "scenario": {"enum": ["base", "management", "seller", "upside", "downside", "unspecified"]},
    "epistemic_class": {"enum": ["asserted", "observed", "derived", "attested", "institutional_act"]},
    "claim_kind": {"enum": ["QUANTITATIVE", "DEFINITION", "CONDITION", "ATTRIBUTION", "NEGATIVE"]},
    "definition_id": {"type": ["string", "null"]},
    "direction": {"enum": ["supports", "contradicts", "context", None]},
    "known_at": {"type": ["string", "null"]},
    "effective_date": {"type": ["string", "null"]},
    "criticality": {"enum": ["decision_critical", "material", "contextual"]},
    "derivation": {
        "anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "expression": {"type": ["string", "null"]},
                    "operand_claim_ids": {
                        "type": "array", "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["expression", "operand_claim_ids"],
            },
        ]
    },
}

TEACHER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"enum": ["success", "abstained", "unsupported"]},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": CLAIM_PROPERTIES,
                "required": list(CLAIM_PROPERTIES),
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source_claim_id": {"type": "string", "minLength": 1},
                    "relation": {"type": "string", "minLength": 1},
                    "target_type": {"enum": ["claim", "question", "definition", "position"]},
                    "target_id": {"type": "string", "minLength": 1},
                },
                "required": ["source_claim_id", "relation", "target_type", "target_id"],
            },
        },
    },
    "required": ["status", "claims", "relations"],
}


INSTRUCTIONS = """You are a conservative financial semantic-claim annotator.
Extract every admissible claim from the supplied documents, but never invent a
claim from promotional language. A number is not a complete identity: preserve
entity, metric, measurement, period, perimeter/scope, economic basis, scenario,
bound and epistemic class. Keep reported, seller, QoE, firm and covenant EBITDA
as separate claims even when their metric names match. Produce row claims as well
as stated totals. Calculate only derivations explicitly requested by the source
or query, and list the exact operand claim IDs. Relations must use IDs emitted in
the same response. Respect any as-of boundary in the query and input known_at.

Use short extractor-local IDs; they need not match any hidden evaluator IDs.
source_quote must be verbatim. locator_value must be exactly the locator supplied
for the relevant Markdown section. Use the input known_at on claims from that
input. Return abstained with empty arrays only when no admissible claims exist.
"""


def _inside_root(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def _markdown_sections(filename: str, content: str) -> str:
    current = filename
    rendered: list[str] = []
    for line in content.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading and not line.startswith("# "):
            current = f"{filename}::{line.strip()}"
        rendered.append(f"[{current}] {line}")
    return "\n".join(rendered)


def _document_bundle(case: Mapping[str, Any]) -> str:
    documents: list[str] = []
    for item in case.get("inputs", []):
        path = (ROOT / str(item["path"])).resolve()
        if not _inside_root(path):
            raise ValueError(f"Input path escapes repository root: {item['path']}")
        if str(item.get("format", "")).casefold() not in TEXT_FORMATS:
            raise ValueError(
                f"{item.get('format')} is not normalized text; run physical extraction first"
            )
        content = path.read_text(encoding="utf-8")
        expected_hash = item.get("sha256")
        if expected_hash and hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"SHA-256 mismatch for {item['path']}")
        filename = path.name
        located = _markdown_sections(filename, content) if item.get("format") == "md" else content
        documents.append(
            "\n".join([
                f"INPUT_ID: {item['input_id']}",
                f"ROLE: {item.get('role', 'primary')}",
                f"KNOWN_AT: {(item.get('metadata') or {}).get('known_at')}",
                "CONTENT_WITH_CANONICAL_LOCATORS:",
                located,
            ])
        )
    return "\n\n--- NEXT INPUT ---\n\n".join(documents)


def _request_payload(case: Mapping[str, Any], bundle: str, draft: Mapping[str, Any] | None = None) -> str:
    parts = [
        f"TEST_ID: {case['test_id']}",
        f"QUERY: {case.get('query')}",
        "DOCUMENTS:",
        bundle,
    ]
    if draft is not None:
        parts.extend([
            "DRAFT_TO_AUDIT:",
            json.dumps(draft, ensure_ascii=False, sort_keys=True),
            "Audit the draft against every source line. Return a corrected, exhaustive result.",
        ])
    return "\n\n".join(parts)


def _call_model(case: Mapping[str, Any], bundle: str, draft: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Install the openai Python package to run the Sol baseline") from exc

    response = OpenAI().responses.create(
        model=os.getenv("PANTA_SEMANTIC_SOL_MODEL", "gpt-5.6-sol"),
        reasoning={"effort": os.getenv("PANTA_SEMANTIC_SOL_REASONING", "high")},
        instructions=INSTRUCTIONS,
        input=_request_payload(case, bundle, draft),
        text={
            "format": {
                "type": "json_schema",
                "name": "panta_semantic_claim_prediction",
                "strict": True,
                "schema": TEACHER_OUTPUT_SCHEMA,
            }
        },
        max_output_tokens=20000,
        store=False,
    )
    if not response.output_text:
        raise RuntimeError(f"Model returned no output text (status={response.status})")
    return json.loads(response.output_text)


def _prediction(case: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    optional_nullable = {
        "definition_id", "direction", "known_at", "effective_date", "derivation", "period",
    }
    for item in raw.get("claims", []):
        claim = dict(item)
        locator_value = claim.pop("locator_value")
        claim["locator"] = {"type": "generic", "value": locator_value}
        for name in optional_nullable:
            if claim.get(name) is None:
                claim.pop(name, None)
        claims.append(claim)
    prediction = {
        "schema_version": "panta-eval.prediction/1.0",
        "test_id": case["test_id"],
        "status": raw["status"],
        "claims": claims,
        "relations": list(raw.get("relations", [])),
        "metadata": {
            "generator": "openai-semantic-teacher",
            "model": os.getenv("PANTA_SEMANTIC_SOL_MODEL", "gpt-5.6-sol"),
            "passes": int(os.getenv("PANTA_SEMANTIC_SOL_PASSES", "1")),
        },
    }
    validate_prediction(prediction)
    return prediction


def main() -> int:
    try:
        case = json.load(sys.stdin)
        bundle = _document_bundle(case)
        raw = _call_model(case, bundle)
        passes = max(1, int(os.getenv("PANTA_SEMANTIC_SOL_PASSES", "1")))
        for _ in range(1, passes):
            raw = _call_model(case, bundle, raw)
        print(json.dumps(_prediction(case, raw), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"semantic teacher failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
