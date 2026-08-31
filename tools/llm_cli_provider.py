#!/usr/bin/env python3
"""Route extractor model calls through the Claude Code CLI instead of the API.

Why
---
Re-running a full manifest is ~1000 model calls. Billing those to the Anthropic
API burns credit on work that is a test, while the CLI already carries a
subscription. This makes the swap a one-line change at the call site instead of a
rewrite of the extractor.

What it is
----------
A shim exposing the one method ``tools/extract_v2.py`` actually uses —
``client.messages.create(**request)`` — and returning an object shaped like the
Anthropic SDK's response, so ``resp.content[i].type / .name / .input`` keeps
working untouched.

The honest limitation
---------------------
The API path forces the schema: ``tool_choice={"type":"tool","name":"emit_claims"}``
makes malformed output impossible. The CLI has no equivalent, so here the schema
is *instructed* rather than *enforced* — it is rendered into the prompt and the
reply is parsed back. The model can therefore drop a field or invent an enum
value in a way the API path structurally cannot.

That matters for what this may be used for. Comparing two extractor versions, or
re-checking a pipeline after a refactor: fine. Producing a number that will be
quoted as a benchmark result, or compared against one produced via the API:
not fine, because a difference could be the transport rather than the change
under test. Anything scored and reported should say which path produced it.

Malformed replies are dropped with a warning rather than repaired, so a
degradation shows up as lower yield instead of quietly wrong claims.

Usage
-----
    from tools.llm_cli_provider import CliClient
    client = CliClient(model="haiku")
    resp = client.messages.create(model=..., system=..., tools=[...], messages=[...])
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

# The CLI loads its own system prompt, project instructions and tool definitions
# on every invocation — tens of thousands of cached tokens that have nothing to do
# with extraction. These strip what can be stripped.
_LEAN_FLAGS = (
    "--strict-mcp-config",
    "--no-session-persistence",
    "--disallowed-tools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task",
)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


@dataclass
class _Block:
    """Mimics an Anthropic tool_use content block."""

    type: str
    name: str
    input: dict[str, Any]


@dataclass
class _Response:
    content: list[_Block] = field(default_factory=list)


class CliError(RuntimeError):
    pass


def _extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a reply that may be wrapped in prose.

    Tried in order: a fenced block, the whole reply, then the widest brace span.
    The last is a fallback for replies that open with a sentence the instruction
    asked the model not to write.
    """
    fenced = _FENCE.search(text)
    for candidate in (fenced.group(1) if fenced else None, text.strip()):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise CliError("no JSON object in reply")


def _render_prompt(system: str, tool: dict[str, Any], user: str) -> str:
    """Fold system prompt, tool schema and user content into one CLI prompt.

    The schema is included verbatim. Restating the constraints in prose instead
    would be a second, drifting copy of a contract that already exists in
    machine-readable form.
    """
    schema = json.dumps(tool.get("input_schema", {}), ensure_ascii=False, indent=1)
    return (
        f"{system}\n\n"
        f"---\n"
        f"Return ONLY a JSON object conforming to this schema. No prose, no "
        f"explanation, no code fence. Every required field must be present, and "
        f"every field with an `enum` must use one of its listed values exactly.\n\n"
        f"SCHEMA:\n{schema}\n\n"
        f"---\n{user}"
    )


class _Messages:
    def __init__(self, client: "CliClient"):
        self._client = client

    def create(self, **request: Any) -> _Response:
        tools = request.get("tools") or []
        if not tools:
            raise CliError("CliClient supports only tool-shaped requests")
        tool = tools[0]

        system = request.get("system") or ""
        user = "\n\n".join(
            block if isinstance(block, str) else str(block.get("content", ""))
            for block in request.get("messages", [])
        )

        prompt = _render_prompt(system, tool, user)
        model = self._client.model or request.get("model") or "haiku"

        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", model, *_LEAN_FLAGS],
            input=prompt, capture_output=True, text=True,
            timeout=self._client.timeout,
        )
        if proc.returncode != 0:
            raise CliError(f"claude exited {proc.returncode}: {proc.stderr[:200]}")

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise CliError(f"CLI envelope not JSON: {proc.stdout[:200]}") from exc

        if envelope.get("is_error"):
            raise CliError(f"CLI reported error: {str(envelope.get('result'))[:200]}")

        self._client.calls += 1
        self._client.cost_usd += float(envelope.get("total_cost_usd") or 0.0)

        try:
            payload = _extract_json_object(str(envelope.get("result", "")))
        except CliError as exc:
            # Dropped, not repaired: a malformed reply must reduce yield, never
            # become a half-parsed claim that looks extracted.
            print(f"  [CLI PARSE] {exc}", file=sys.stderr)
            self._client.dropped += 1
            return _Response(content=[])

        return _Response(content=[
            _Block(type="tool_use", name=tool.get("name", "emit_claims"), input=payload)
        ])


class CliClient:
    """Drop-in for the Anthropic client, backed by the Claude Code CLI."""

    def __init__(self, model: str | None = None, timeout: float = 180.0):
        self.model = model
        self.timeout = timeout
        self.calls = 0
        self.dropped = 0
        self.cost_usd = 0.0
        self.messages = _Messages(self)

    def stats(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "dropped": self.dropped,
            "drop_rate": round(self.dropped / self.calls, 4) if self.calls else 0.0,
            "reported_cost_usd": round(self.cost_usd, 4),
        }


def selftest() -> int:
    """Prove the shim returns the shape extract_v2 expects, on one small call."""
    client = CliClient(model="haiku")
    tool = {
        "name": "emit_claims",
        "input_schema": {
            "type": "object",
            "required": ["claims"],
            "properties": {"claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["metric", "value"],
                    "properties": {
                        "metric": {"type": "string", "enum": ["EBITDA", "Revenue"]},
                        "value": {"type": ["number", "null"]},
                    },
                },
            }},
        },
    }
    resp = client.messages.create(
        model="haiku",
        system="Extract financial claims from the fragment.",
        tools=[tool],
        messages=[{"role": "user", "content": "FY2025 EBITDA was 11.4m and revenue was 45.0m."}],
    )
    if not resp.content:
        print("FAIL — empty response"); return 1
    block = resp.content[0]
    print(f"type={block.type} name={block.name}")
    print(f"claims={json.dumps(block.input.get('claims'), ensure_ascii=False)}")
    print(f"stats={client.stats()}")
    ok = block.type == "tool_use" and isinstance(block.input.get("claims"), list)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
