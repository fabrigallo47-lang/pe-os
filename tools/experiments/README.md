# experiments/

Standalone prototypes, not wired into production (`tools/extract_v2_physical.py`
or any Claude Code skill). Nothing here runs unless invoked directly.

## graphic_examples.py

Tests whether GraphIC's idea (arXiv:2410.02203 -- retrieve in-context examples
by comparing "thought graphs" of reasoning structure, not flat text
similarity) helps our claim extractor's `derived` claims: the one place it is
explicitly allowed to compute a value from two or more stated ones rather
than just transcribe what the source says.

Run: `python3 -m tools.experiments.graphic_examples` (needs `ANTHROPIC_API_KEY`
for the live extraction half; retrieval-only comparison runs without it).

### What it does

1. A small hand-built bank of four worked examples, each a (fragment, correct
   claims) pair, with a "thought graph" built from the claims' own authored
   `depends_on` edges -- not parsed from text, since that would need the
   extractor itself.
2. A heuristic `build_query_thought_graph()` approximates a NEW fragment's
   dependency shape from numeric anchors + nearby cue words (cost-type cues
   precede their number, addback-type cues trail it) -- a stand-in for what a
   real system would get from a cheap upstream LLM call, not NLP-complete.
3. Retrieves the best-matching bank example two ways: graph-structure
   similarity (Weisfeiler-Leman label overlap on the thought graphs) vs a
   naive text-overlap baseline (word-set Jaccard, standing in for what a flat
   embedding similarity would do).
4. Runs the real extraction (same `CLAIM_TOOL`/`SYSTEM_PROMPT`/model as
   production) twice on a held-out two-hop fragment (an EBITDA bridge with an
   addback, not in the bank): once zero-shot (today's production prompt,
   unchanged), once with the retrieved example injected as a worked few-shot.

### What was found, running it

- The first version of the query-graph heuristic was too coarse to be worth
  much: it only linked *adjacent* number pairs, so it couldn't represent one
  value depending on *three* others (an aggregate) or a genuine second hop.
  It also picked up the bare year in "FY2024A" as a spurious numeric anchor,
  and only looked *before* each number for cue words, missing a trailing cue
  like "EUR 4.0m ... that are added back". All three were found by running
  the module against `TEST_CHUNK`, not by reviewing the code -- worth keeping
  in mind before trusting any single test case's result at face value here.
- Once fixed, graph-structure similarity and text-overlap happened to agree
  on the same top example for this one test case (`two_hop_bridge`, score
  1.00 by graph shape vs 0.39 by text overlap) -- so this run does not by
  itself demonstrate the two methods diverging in which example they'd pick,
  only that the graph method is far more confident when the shape actually
  matches. An earlier, broken version of the heuristic *did* diverge (picked
  `simple_subtraction` on text-adjacent grounds), which is closer to the
  scenario GraphIC's argument is actually about -- worth another test
  fragment designed so the two methods disagree once the heuristic is
  trusted more.
- The live comparison is the real finding: zero-shot production prompt
  extracted the four stated values but derived nothing -- 0 derived claims,
  the EBITDA bridge entirely missed. With the retrieved two-hop example
  injected as a few-shot, the model correctly derived both hops (EBITDA =
  90 - 38 - 19 = 33.0, then 33.0 + 4.0 = 37.0) with a correct derivation
  string for each.
- Caveat, not swept under the rug: the model labelled *both* derived claims
  "EBITDA" rather than distinguishing "Adjusted EBITDA" for the second hop.
  Under CLAUDE.md's claim-identity rules this is a real collision risk (two
  different values under the same metric/period/perimeter reads as a
  contradiction, not two components) -- a naming-precision gap the few-shot
  example didn't fix, separate from whether the arithmetic itself was right.

### Status

Prototype only. Retrieval mechanism and similarity metric are demonstrated
working end to end against one real extraction call; not evaluated against a
real chunk sample, not wired into `annotate_chunk()`, and the query-graph
heuristic is a stand-in that would need real validation (or replacing with a
cheap LLM sketch) before this could be trusted on real documents.

## document_logic_extractor.py

A different, narrower application of the same paper: instead of retrieving
an external worked example, extract the CURRENT document's own dependency
graph -- which stated values feed which derived ones -- using the exact same
categories, enums and fields the production claim extractor already emits
(`CLAIM_TOOL` copied verbatim: same `METRIC_ENUM`, `TOPIC_ENUM`,
`epistemic_class`, everything), plus two additional fields (`local_id`,
`depends_on`) that make the same relationship the `derivation` free-text
field already states, structured instead of prose.

The question: can that structure, extracted once and rendered as a short
text summary, then be handed to the MAIN per-claim extractor --
`annotate_chunk`'s actual `CLAIM_TOOL`/`SYSTEM_PROMPT`, completely
unmodified -- as extra context, and change what it produces?

Run: `python3 -m tools.experiments.document_logic_extractor` (needs
`ANTHROPIC_API_KEY`; reuses `TEST_CHUNK` from `graphic_examples.py`).

### What was found, running it

- Yes, on the arithmetic: the unmodified main extractor, alone, still finds
  the same thing `graphic_examples.py` found -- 0 derived claims, the whole
  EBITDA bridge missed. Handed the document-graph summary as context (no
  schema change, no few-shot claims, just a plain-text description of what
  depends on what), it correctly derives through to the right final value
  (37.0). The scaffold alone was enough, without ever showing it a worked
  example's actual claims.
- No, on naming: the derived claims still collide on the metric name
  "EBITDA" for two different values at two different derivation depths --
  the exact gap `graphic_examples.py` flagged. This run went further and
  explicitly instructed against it (`SYSTEM_PROMPT_GRAPH` names this exact
  failure mode) on the document-graph extractor itself, and it STILL
  produced two claims both named "EBITDA" (33.0 and 37.0) in its own
  output -- so the instruction didn't even hold on the prompt written
  for it, let alone propagate through to the main extractor via the text
  summary. This looks like it needs a schema/validation-side fix (e.g.
  detecting two derived claims at different `depends_on` depths sharing a
  metric name), not another prompt sentence.
- A structural quirk worth flagging: rather than recognizing "EBITDA
  depends on 3 stated values at once" (an aggregate), the document-graph
  extractor folded it into two sequential pairwise steps through an
  invented intermediate concept it called "Gross Profit" -- not present or
  implied in the source text, and a poor label for what is actually
  revenue minus COGS. The arithmetic stayed correct throughout (52 - 19 =
  33, matching the aggregate), but the graph SHAPE it discovers is not
  guaranteed to match the most natural reading of the document, only *a*
  mathematically consistent one.

### Status

Prototype only, same caveats as `graphic_examples.py`: one test fragment,
not wired into `annotate_chunk()`. The positive finding (context from a
document's own extracted structure fixes a missed derivation, without a
worked example) is worth a real trial on actual deal fragments; the naming
collision is now confirmed to reproduce across two different prompting
strategies and should probably be chased as a schema/validation change
instead of a third prompt attempt.
