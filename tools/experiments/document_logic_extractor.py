#!/usr/bin/env python3
"""Prototype: extract a document's OWN derivation structure, same schema.

graphic_examples.py tested retrieving a graph-shaped EXAMPLE from an
external bank as a few-shot demonstration. This is a different, narrower
idea from the same paper (GraphIC, arXiv:2410.02203): instead of borrowing
someone else's worked example, extract the CURRENT document's own
dependency graph -- which stated values feed which derived ones -- in one
pass, using the exact same categories, enums and fields the production
claim extractor already emits (METRIC_ENUM, TOPIC_ENUM, epistemic_class,
etc. -- nothing new there), plus two additional fields (`local_id`,
`depends_on`) that make the SAME relationship the `derivation` free-text
field already states, structured and machine-readable instead of prose.

The question this tests: can that structural map, extracted once, then be
handed to the MAIN per-claim extractor (annotate_chunk's unmodified
CLAIM_TOOL / SYSTEM_PROMPT, completely unchanged) as extra context and
improve what it produces -- not just whether it derives the right VALUE
(graphic_examples.py already showed a worked example fixes that), but
whether it also assigns each derived claim a DISTINCT identity, which that
prototype's own writeup flagged as a real gap: the model reused the metric
name "EBITDA" for two different derived values.

Run: python3 -m tools.experiments.document_logic_extractor
Needs ANTHROPIC_API_KEY (reads .env at repo root if present).
"""
from __future__ import annotations

import copy
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.minigraph import DiGraph  # noqa: E402
from tools.extract_v2_physical import CLAIM_TOOL, SYSTEM_PROMPT, MODEL  # noqa: E402
from tools.llm_provider import anthropic_client_kwargs, configured_api_key  # noqa: E402
from tools.experiments.graphic_examples import (  # noqa: E402
    TEST_CHUNK, EXPECTED_ADJUSTED_EBITDA, _found_correct_adjusted_ebitda,
)


# ---------------------------------------------------------------------------
# The graph-extraction tool: CLAIM_TOOL verbatim (same categories, same
# metrics, same everything it already extracts) plus local_id/depends_on so
# the document's own derivation edges come back structured, not just as the
# `derivation` free-text sentence.
# ---------------------------------------------------------------------------

def _build_graph_tool() -> dict[str, Any]:
    tool = copy.deepcopy(CLAIM_TOOL)
    tool["name"] = "emit_claim_graph"
    tool["description"] = (
        CLAIM_TOOL["description"] + " Additionally, give each claim a "
        "local_id and a depends_on list, making this same emission's own "
        "derivation structure explicit and machine-readable."
    )
    items = tool["input_schema"]["properties"]["claims"]["items"]
    items["properties"]["local_id"] = {
        "type": "string",
        "minLength": 1,
        "description": (
            "A short id unique within THIS emission (c1, c2, ...). Exists "
            "only so depends_on can reference this claim -- never persisted "
            "as the claim's real identity."
        ),
    }
    items["properties"]["depends_on"] = {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "local_id of every OTHER claim in this SAME emission whose "
            "value this claim was computed from. Empty for anything not "
            "derived from other claims in this fragment. Every id here "
            "MUST also appear as some claim's own local_id in this same "
            "batch -- never an external or invented reference."
        ),
    }
    items["required"] = items["required"] + ["local_id", "depends_on"]
    return tool


GRAPH_TOOL = _build_graph_tool()

SYSTEM_PROMPT_GRAPH = SYSTEM_PROMPT + "\n\n" + textwrap.dedent("""
    ADDITIONALLY: every claim needs a `local_id` (c1, c2, ...) and a
    `depends_on` list -- the local_ids of any OTHER claims in this SAME
    emission whose values this claim was computed from. This is the same
    fact the `derivation` field already states in prose; depends_on makes
    it structured. A claim with epistemic_class != derived should have an
    empty depends_on. Never reference a local_id you did not also emit in
    this same batch. If a derived claim depends on more than one earlier
    derived claim, or the SAME metric appears at two different derivation
    depths (e.g. an EBITDA before adjustments and a second EBITDA after
    them), give each a name that distinguishes them -- "EBITDA" reused
    unchanged for two different values at two different depths is a
    naming collision, not two claims.
""")


def extract_document_graph(chunk_text: str, client) -> tuple[list[dict], DiGraph]:
    user_content = (
        "DEAL: prototype\nSOURCE: test-fragment (test) — management presentation\n"
        "KNOWN AT: 2026-09-03\nFRAGMENT LOCATOR: test::fragment\n\n"
        f"{chunk_text}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT_GRAPH,
        tools=[GRAPH_TOOL],
        tool_choice={"type": "tool", "name": "emit_claim_graph"},
        messages=[{"role": "user", "content": user_content}],
        extra_body={"temperature": 0},
    )
    claims: list[dict] = []
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_claim_graph":
            claims = block.input.get("claims", [])

    g = DiGraph()
    ids = {c.get("local_id") for c in claims}
    for c in claims:
        g.add_node(c["local_id"], metric=c.get("metric"), value=c.get("value"),
                   epistemic_class=c.get("epistemic_class"))
    for c in claims:
        for dep in c.get("depends_on") or []:
            if dep in ids:  # drop anything hallucinated outside this batch
                g.add_edge(dep, c["local_id"])
    return claims, g


def render_graph_summary(claims: list[dict]) -> str:
    """Compact text rendering of the extracted structure, meant to be
    handed to a DIFFERENT extraction call as grounding context -- not the
    claims themselves (that would just be a second copy of the same
    extraction), only the dependency shape."""
    by_id = {c["local_id"]: c for c in claims}
    lines = ["This document's own derivation structure (extracted separately, "
             "for reference -- re-derive and re-verify values yourself, do "
             "not just copy them):"]
    for c in claims:
        deps = [by_id[d]["metric"] for d in (c.get("depends_on") or []) if d in by_id]
        if deps:
            lines.append(f"  - {c['metric']} is derived from: {', '.join(deps)}")
        else:
            lines.append(f"  - {c['metric']} is a stated value, not derived")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Does handing that structure to the MAIN extractor (unmodified CLAIM_TOOL
# and SYSTEM_PROMPT -- the one annotate_chunk() actually uses) change what
# it produces?
# ---------------------------------------------------------------------------

def run_main_extractor(chunk_text: str, client, extra_context: str | None = None) -> list[dict]:
    user_content = ""
    if extra_context:
        user_content += extra_context + "\n\n---\n\n"
    user_content += (
        "DEAL: prototype\nSOURCE: test-fragment (test) — management presentation\n"
        "KNOWN AT: 2026-09-03\nFRAGMENT LOCATOR: test::fragment\n\n"
        f"{chunk_text}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,          # unmodified production prompt
        tools=[CLAIM_TOOL],            # unmodified production schema
        tool_choice={"type": "tool", "name": "emit_claims"},
        messages=[{"role": "user", "content": user_content}],
        extra_body={"temperature": 0},
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_claims":
            return block.input.get("claims", [])
    return []


def _has_distinct_derived_names(claims: list[dict]) -> bool:
    derived_names = [c.get("metric") for c in claims if c.get("epistemic_class") == "derived"]
    return len(derived_names) >= 2 and len(set(derived_names)) == len(derived_names)


def main() -> int:
    api_key = configured_api_key()
    if not api_key:
        print("ANTHROPIC_API_KEY not configured -- nothing to run.")
        return 1

    import anthropic
    client = anthropic.Anthropic(**anthropic_client_kwargs(api_key))

    print("=" * 70)
    print("STEP 1 -- extract the document's own derivation graph")
    print("=" * 70)
    print(TEST_CHUNK)
    graph_claims, g = extract_document_graph(TEST_CHUNK, client)
    for c in graph_claims:
        deps = ", ".join(c.get("depends_on") or []) or "-"
        print(f"  [{c['local_id']}] {c.get('metric'):<22} {c.get('value')!s:<10} "
              f"epistemic={c.get('epistemic_class'):<10} depends_on=[{deps}]")
    print(f"\nGraph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    summary = render_graph_summary(graph_claims)
    print("\nRendered summary (this is what gets handed to the main extractor):")
    print(summary)

    print("\n" + "=" * 70)
    print("STEP 2 -- does the MAIN extractor (unchanged schema/prompt) do "
          "better with that structure as context?")
    print("=" * 70)

    baseline = run_main_extractor(TEST_CHUNK, client, extra_context=None)
    assisted = run_main_extractor(TEST_CHUNK, client, extra_context=summary)

    for label, claims in (("baseline (main extractor alone)", baseline),
                          ("main extractor + document-graph context", assisted)):
        print(f"\n--- {label} ---")
        for c in claims:
            print(f"  {c.get('metric'):<24} {c.get('value')!s:<10} "
                  f"epistemic={c.get('epistemic_class'):<10} "
                  f"derivation={c.get('derivation')}")
        correct_value = _found_correct_adjusted_ebitda(claims)
        distinct_names = _has_distinct_derived_names(claims)
        print(f"  correct Adjusted EBITDA value ({EXPECTED_ADJUSTED_EBITDA}) found: {correct_value}")
        print(f"  derived claims have distinct metric names: {distinct_names}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
