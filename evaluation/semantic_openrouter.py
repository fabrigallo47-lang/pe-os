#!/usr/bin/env python3
"""Run the semantic-claim contract with GLM 5.2 through OpenRouter.

The module implements the evaluator's one-case JSON stdin/stdout protocol. It
shares the semantic schema and source-bundling rules with the independent Sol
baseline, but uses OpenRouter Chat Completions with strict structured output.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Mapping

from evaluation.schema import validate_prediction
from evaluation.semantic_teacher import (
    INSTRUCTIONS,
    TEACHER_OUTPUT_SCHEMA,
    _document_bundle,
    _prediction,
    _request_payload,
)
from tools.llm_provider import (
    DEFAULT_OPENROUTER_EXTRACTION_MODEL,
    openrouter_provider_preferences,
)


def configured_model() -> str:
    return os.environ.get(
        "PANTA_SEMANTIC_OPENROUTER_MODEL",
        DEFAULT_OPENROUTER_EXTRACTION_MODEL,
    ).strip()


def completion_request(
    case: Mapping[str, Any],
    bundle: str,
    draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "model": configured_model(),
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": _request_payload(case, bundle, draft)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "panta_semantic_claim_prediction",
                "strict": True,
                "schema": TEACHER_OUTPUT_SCHEMA,
            },
        },
        "max_tokens": 20000,
        "temperature": 0,
        "extra_body": {
            "provider": openrouter_provider_preferences(),
            "reasoning": {
                "effort": os.environ.get(
                    "PANTA_SEMANTIC_OPENROUTER_REASONING", "high"
                )
            },
        },
    }


def _call_model(
    case: Mapping[str, Any],
    bundle: str,
    draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Install evaluation/requirements-semantic.txt to run GLM 5.2"
        ) from exc

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    response = client.chat.completions.create(**completion_request(case, bundle, draft))
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter returned no structured message content")
    return json.loads(content)


def _openrouter_prediction(
    case: Mapping[str, Any], raw: Mapping[str, Any], passes: int
) -> dict[str, Any]:
    prediction = _prediction(case, raw)
    prediction["metadata"] = {
        "generator": "openrouter-semantic-extractor",
        "model": configured_model(),
        "passes": passes,
    }
    validate_prediction(prediction)
    return prediction


def main() -> int:
    try:
        case = json.load(sys.stdin)
        bundle = _document_bundle(case)
        passes = max(
            1, int(os.environ.get("PANTA_SEMANTIC_OPENROUTER_PASSES", "1"))
        )
        raw = _call_model(case, bundle)
        for _ in range(1, passes):
            raw = _call_model(case, bundle, raw)
        print(json.dumps(_openrouter_prediction(case, raw, passes), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"OpenRouter semantic extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
