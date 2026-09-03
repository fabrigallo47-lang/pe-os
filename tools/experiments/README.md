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
