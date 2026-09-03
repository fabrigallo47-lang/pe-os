#!/usr/bin/env python3
"""Prototype: GraphIC-style example retrieval for derived-claim extraction.

GraphIC (arXiv:2410.02203) retrieves in-context examples for multi-step
reasoning by comparing "thought graphs" -- directed, node-attributed graphs
of the reasoning steps and their dependencies -- instead of flat text
embeddings, on the claim that text similarity carries irrelevant semantic
noise and misses reasoning STRUCTURE.

The closest thing our claim extractor has to "multi-step reasoning" is a
`derived` claim: annotate_chunk() is explicitly allowed to compute a value
from two or more stated ones (EBITDA = Revenue - Costs, a margin ratio, a
two-hop adjusted-EBITDA bridge), and that is exactly where a bad or missing
in-context example would hurt most. This module is a standalone experiment,
NOT wired into annotate_chunk() -- it exists to show whether retrieving a
worked example by dependency-graph shape picks a more useful example, and
changes the extraction, versus (a) no example at all (today's production
behaviour) or (b) an example picked by flat text overlap.

Run: python3 -m tools.experiments.graphic_examples
Needs ANTHROPIC_API_KEY (reads .env at repo root if present) to run the
live before/after extraction; retrieval-only comparison works without it.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.minigraph import DiGraph  # noqa: E402


# ---------------------------------------------------------------------------
# Thought graphs: nodes are claims (stated or derived), edges are "feeds into"
# dependency arrows. Each bank example authors its own `depends_on` per claim
# rather than parsing the free-text `derivation` string -- reliable for a
# hand-built bank; a production version would need the real parse.
# ---------------------------------------------------------------------------

def build_thought_graph(claims: list[dict[str, Any]]) -> DiGraph:
    g = DiGraph()
    for claim in claims:
        role = "derived" if claim["epistemic_class"] == "derived" else "stated"
        g.add_node(claim["metric"], role=role, topic=claim.get("topic", "OTHER"))
    for claim in claims:
        for dep in claim.get("depends_on", []):
            g.add_edge(dep, claim["metric"])
    return g


EXAMPLE_BANK: list[dict[str, Any]] = [
    {
        "id": "simple_subtraction",
        "chunk_text": (
            "FY2024A revenue was EUR 40.0m. Total operating costs for the "
            "period were EUR 28.0m."
        ),
        "claims": [
            {"metric": "Revenue", "value": 40.0, "topic": "REVENUE",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "Operating costs", "value": 28.0, "topic": "COSTS",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "EBITDA", "value": 12.0, "topic": "EBITDA",
             "epistemic_class": "derived", "depends_on": ["Revenue", "Operating costs"],
             "derivation": "Revenue (40.0) - Operating costs (28.0) = 12.0"},
        ],
    },
    {
        "id": "ratio_margin",
        "chunk_text": (
            "The business generated EUR 15.0m of EBITDA on EUR 60.0m of "
            "revenue in FY2024A."
        ),
        "claims": [
            {"metric": "EBITDA", "value": 15.0, "topic": "EBITDA",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "Revenue", "value": 60.0, "topic": "REVENUE",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "EBITDA margin", "value": 25.0, "topic": "MARGIN",
             "epistemic_class": "derived", "depends_on": ["EBITDA", "Revenue"],
             "derivation": "EBITDA (15.0) / Revenue (60.0) = 25.0%"},
        ],
    },
    {
        "id": "two_hop_bridge",
        "chunk_text": (
            "FY2024A revenue was EUR 50.0m. Cost of goods sold was EUR "
            "22.0m and operating expenses were EUR 13.0m. Management "
            "add back EUR 3.0m of one-off restructuring costs excluded "
            "from the adjusted view."
        ),
        "claims": [
            {"metric": "Revenue", "value": 50.0, "topic": "REVENUE",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "COGS", "value": 22.0, "topic": "COSTS",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "Operating expenses", "value": 13.0, "topic": "COSTS",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "One-off addback", "value": 3.0, "topic": "ADJUSTMENTS",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "EBITDA", "value": 15.0, "topic": "EBITDA",
             "epistemic_class": "derived",
             "depends_on": ["Revenue", "COGS", "Operating expenses"],
             "derivation": "Revenue (50.0) - COGS (22.0) - Opex (13.0) = 15.0"},
            {"metric": "Adjusted EBITDA", "value": 18.0, "topic": "EBITDA",
             "epistemic_class": "derived",
             "depends_on": ["EBITDA", "One-off addback"],
             "derivation": "EBITDA (15.0) + one-off addback (3.0) = 18.0"},
        ],
    },
    {
        "id": "no_derivation",
        "chunk_text": (
            "The company reported 4,200 active customers as of 30 June "
            "2025. Monthly churn was 1.8% over the same period."
        ),
        "claims": [
            {"metric": "Active customers", "value": 4200, "topic": "OTHER",
             "epistemic_class": "asserted", "depends_on": []},
            {"metric": "Monthly churn", "value": 1.8, "topic": "OTHER",
             "epistemic_class": "asserted", "depends_on": []},
        ],
    },
]

for _example in EXAMPLE_BANK:
    _example["thought_graph"] = build_thought_graph(_example["claims"])


# ---------------------------------------------------------------------------
# Query-side: approximate a new chunk's reasoning shape without a full
# extraction pass. Deliberately a coarse heuristic (numeric anchors + nearby
# arithmetic connector words), not NLP -- in a real system this first pass
# would likely be a cheap, separate LLM call; the heuristic is enough to
# show the retrieval mechanism working end to end.
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"\b(?:(?:EUR|USD|GBP)\s*[\d,]+(?:\.\d+)?\s*(?:%|m|bn|k)?"
    r"|[\d,]+(?:\.\d+)?\s*(?:%|m|bn|k))\b",
    re.IGNORECASE,
)
_SUBTRACT_CUE_RE = re.compile(
    r"\b(cost|costs|expense|expenses|cogs|opex|less|minus|net of)\b", re.IGNORECASE)
_ADDBACK_CUE_RE = re.compile(
    r"\b(add(?:ed)? back|adjusted for|adjusted view|plus)\b", re.IGNORECASE)
_RATIO_CUE_RE = re.compile(r"\b(margin|ratio|divided by|per|over|%)\b", re.IGNORECASE)


def build_query_thought_graph(chunk_text: str) -> DiGraph:
    """Heuristic: one 'stated' node per numeric anchor, classified by the
    cue words in a short window around it -- both before ("less EUR 3.0m")
    and after ("EUR 3.0m that are added back"), since English puts a cue
    on either side depending on phrasing -- into an AGGREGATE first hop
    (e.g. three costs feeding one EBITDA, not a linear chain of pairs) plus
    a second hop for anything an addback/adjustment cue attaches to.

    This still cannot recover the real computation (that stays the
    extractor's job), and an earlier version of it -- one edge per adjacent
    anchor pair, a before-only cue window, and a number regex that matched
    bare years out of "FY2024A" as spurious anchors -- silently under-
    detected exactly the "deeper reasoning structure" GraphIC's own
    argument is about. Those were found empirically, running this exact
    module against the TEST_CHUNK below, not by design review -- see
    tools/experiments/README.md.
    """
    g = DiGraph()
    anchors = list(_NUMBER_RE.finditer(chunk_text))
    if not anchors:
        return g

    base_ids: list[str] = []
    subtract_ids: list[str] = []
    addback_ids: list[str] = []
    ratio = False
    for i, m in enumerate(anchors):
        nid = f"v{i}"
        g.add_node(nid, role="stated", topic="OTHER")
        # Directional, bounded by the neighbouring anchors so one anchor's
        # own clause ("Direct costs ... came to EUR 38.0m") cannot bleed
        # into the anchor before it. Cost-type cues precede the number
        # they describe ("costs ... were $Y"); addback-type cues trail it
        # ("$Y ... added back") -- so each side only checks the cue it
        # naturally carries in this domain's phrasing.
        before = chunk_text[(anchors[i - 1].end() if i > 0 else max(0, m.start() - 60)):m.start()]
        after = chunk_text[m.end():(anchors[i + 1].start() if i + 1 < len(anchors)
                                     else min(len(chunk_text), m.end() + 60))]
        if _ADDBACK_CUE_RE.search(after):
            addback_ids.append(nid)
        elif _SUBTRACT_CUE_RE.search(before):
            subtract_ids.append(nid)
        else:
            base_ids.append(nid)
        if _RATIO_CUE_RE.search(before) or _RATIO_CUE_RE.search(after):
            ratio = True

    if ratio and len(anchors) >= 2 and not subtract_ids and not addback_ids:
        g.add_node("d1", role="derived", topic="OTHER")
        for nid in (base_ids or [f"v{i}" for i in range(min(2, len(anchors)))]):
            g.add_edge(nid, "d1")
        return g

    hop1 = None
    if subtract_ids and base_ids:
        hop1 = "d1"
        g.add_node(hop1, role="derived", topic="OTHER")
        for nid in base_ids + subtract_ids:
            g.add_edge(nid, hop1)

    if addback_ids and hop1 is not None:
        hop2 = "d2"
        g.add_node(hop2, role="derived", topic="OTHER")
        g.add_edge(hop1, hop2)
        for nid in addback_ids:
            g.add_edge(nid, hop2)
    return g


# ---------------------------------------------------------------------------
# Similarity metrics
# ---------------------------------------------------------------------------

def _wl_labels(g: DiGraph, iterations: int = 1) -> Counter:
    """1-step Weisfeiler-Leman-style label refinement: each node's label
    becomes its own role folded with the sorted roles of its in- and
    out-neighbours, so two graphs with the same DEPENDENCY SHAPE (e.g. two
    stated values feeding one derived value) land on the same refined
    labels even when the node names differ -- structure, not vocabulary."""
    labels = {n: g.nodes[n]["role"] for n in g.nodes()}
    for _ in range(iterations):
        new_labels = {}
        for n in g.nodes():
            neighbours = sorted(
                labels[m] for m in list(g.predecessors(n)) + list(g.successors(n))
            )
            new_labels[n] = labels[n] + "|" + ",".join(neighbours)
        labels = new_labels
    return Counter(labels.values())


def graph_similarity(g1: DiGraph, g2: DiGraph) -> float:
    """Sorensen-Dice overlap of the two graphs' WL-refined label multisets.
    Bounded [0, 1]; 1.0 only when the refined-label histograms match exactly."""
    c1, c2 = _wl_labels(g1), _wl_labels(g2)
    total = sum(c1.values()) + sum(c2.values())
    if total == 0:
        return 0.0
    overlap = sum(min(c1[k], c2[k]) for k in set(c1) | set(c2))
    return 2 * overlap / total


def text_similarity(a: str, b: str) -> float:
    """Naive baseline standing in for a flat embedding similarity: word-set
    Jaccard. This is exactly the kind of comparison GraphIC argues loses
    reasoning structure -- kept here only as a contrast, not a real baseline."""
    wa = set(re.findall(r"[a-z]+", a.lower()))
    wb = set(re.findall(r"[a-z]+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def retrieve(query_graph: DiGraph, query_text: str,
             bank: list[dict[str, Any]] = EXAMPLE_BANK) -> dict[str, list[tuple[str, float]]]:
    by_graph = sorted(
        ((ex["id"], graph_similarity(query_graph, ex["thought_graph"])) for ex in bank),
        key=lambda pair: -pair[1],
    )
    by_text = sorted(
        ((ex["id"], text_similarity(query_text, ex["chunk_text"])) for ex in bank),
        key=lambda pair: -pair[1],
    )
    return {"graph": by_graph, "text": by_text}


# ---------------------------------------------------------------------------
# Live extraction comparison (needs an API key)
# ---------------------------------------------------------------------------

def render_fewshot(example: dict[str, Any]) -> str:
    claims_for_prompt = [
        {k: v for k, v in c.items() if k not in ("depends_on",)}
        for c in example["claims"]
    ]
    return (
        f"WORKED EXAMPLE -- a fragment shaped like the one below, and the "
        f"claims correctly extracted from it:\n\n"
        f"FRAGMENT:\n{example['chunk_text']}\n\n"
        f"CORRECT CLAIMS:\n{json.dumps(claims_for_prompt, indent=2)}\n"
    )


def run_extraction(chunk_text: str, fewshot_example: dict[str, Any] | None,
                    client, model: str, claim_tool: dict, system_prompt: str) -> list[dict]:
    user_content = ""
    if fewshot_example is not None:
        user_content += render_fewshot(fewshot_example) + "\n---\n\n"
    user_content += (
        "DEAL: prototype\nSOURCE: test-fragment (test) — management presentation\n"
        "KNOWN AT: 2026-09-03\nFRAGMENT LOCATOR: test::fragment\n\n"
        f"{chunk_text}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system_prompt,
        tools=[claim_tool],
        tool_choice={"type": "tool", "name": "emit_claims"},
        messages=[{"role": "user", "content": user_content}],
        extra_body={"temperature": 0},
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_claims":
            return block.input.get("claims", [])
    return []


TEST_CHUNK = (
    "FY2024A revenue for the division was EUR 90.0m. Direct costs of "
    "production came to EUR 38.0m, and other operating expenses were "
    "EUR 19.0m for the period. Management separately identify EUR 4.0m "
    "of non-recurring legal costs in FY2024A that are added back for "
    "the adjusted view of profitability."
)
# Ground truth for the automatic check below: EBITDA = 90 - 38 - 19 = 33.0;
# Adjusted EBITDA = 33.0 + 4.0 = 37.0 -- a two-hop chain not stated anywhere
# in the fragment, deliberately shaped like the bank's two_hop_bridge example
# but with different numbers and wording so retrieval cannot just reuse text.
EXPECTED_ADJUSTED_EBITDA = 37.0


def _found_correct_adjusted_ebitda(claims: list[dict]) -> bool:
    """Grade on the derived VALUE, not the metric name -- the model may
    (and, observed empirically, does) reuse "EBITDA" for both the first-
    and second-hop derived claim rather than switching to "Adjusted
    EBITDA", which is itself worth flagging (a real identity-collision
    risk under CLAUDE.md's claim-identity rules) but is a separate,
    already-known naming problem, not evidence the arithmetic was wrong."""
    for c in claims:
        if c.get("epistemic_class") != "derived":
            continue
        try:
            if abs(float(c.get("value")) - EXPECTED_ADJUSTED_EBITDA) < 0.05:
                return True
        except (TypeError, ValueError):
            continue
    return False


def main() -> int:
    query_graph = build_query_thought_graph(TEST_CHUNK)
    ranking = retrieve(query_graph, TEST_CHUNK)

    print("=" * 70)
    print("QUERY CHUNK")
    print("=" * 70)
    print(TEST_CHUNK)
    print(f"\nQuery thought graph: {len(list(query_graph.nodes()))} nodes, "
          f"{len(list(query_graph.edges()))} edges")

    print("\n" + "=" * 70)
    print("RETRIEVAL: graph-structure similarity vs flat text similarity")
    print("=" * 70)
    print(f"{'rank':<5}{'by graph shape':<28}{'by text overlap':<28}")
    for i in range(len(EXAMPLE_BANK)):
        g_id, g_score = ranking["graph"][i]
        t_id, t_score = ranking["text"][i]
        print(f"{i + 1:<5}{g_id + f' ({g_score:.2f})':<28}{t_id + f' ({t_score:.2f})':<28}")

    graph_top = ranking["graph"][0][0]
    text_top = ranking["text"][0][0]
    if graph_top != text_top:
        print(f"\nThe two methods disagree: graph-shape retrieval picks "
              f"'{graph_top}' (matches the query's two-hop dependency "
              f"structure), text overlap picks '{text_top}' (shares more "
              f"vocabulary but not the same reasoning shape).")
    else:
        print(f"\nBoth methods agree on '{graph_top}' for this query.")

    from tools.extract_v2_physical import CLAIM_TOOL, SYSTEM_PROMPT, MODEL
    from tools.llm_provider import anthropic_client_kwargs, configured_api_key

    api_key = configured_api_key()
    if not api_key:
        print("\n(no ANTHROPIC_API_KEY configured -- skipping the live "
              "extraction comparison; retrieval ranking above still stands)")
        return 0

    import anthropic
    client = anthropic.Anthropic(**anthropic_client_kwargs(api_key))

    best_example = next(ex for ex in EXAMPLE_BANK if ex["id"] == graph_top)

    print("\n" + "=" * 70)
    print("LIVE EXTRACTION: baseline (no example) vs GraphIC-retrieved example")
    print("=" * 70)

    baseline_claims = run_extraction(TEST_CHUNK, None, client, MODEL, CLAIM_TOOL, SYSTEM_PROMPT)
    graphic_claims = run_extraction(TEST_CHUNK, best_example, client, MODEL, CLAIM_TOOL, SYSTEM_PROMPT)

    for label, claims in (("baseline (zero-shot, today's production prompt)", baseline_claims),
                          (f"graphic-augmented (retrieved example: {best_example['id']})", graphic_claims)):
        print(f"\n--- {label} ---")
        for c in claims:
            print(f"  {c.get('metric'):<22} {c.get('value')!s:<10} "
                  f"epistemic={c.get('epistemic_class')} "
                  f"derivation={c.get('derivation')}")
        found = _found_correct_adjusted_ebitda(claims)
        print(f"  correct Adjusted EBITDA ({EXPECTED_ADJUSTED_EBITDA}) found: {found}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
