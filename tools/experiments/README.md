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

## real_fixture_test.py

Everything above used one synthetic fragment, built specifically to force a
derivation by withholding the final total. This runs the same two
prototypes against three REAL fragments from
`sources/keystone-fixture/layer1-ingest/` -- actual Keystone deal documents,
not a test string -- to see whether the synthetic findings hold up:

  qoe_bridge   `keystone_qoe_report.md`         Reported EBITDA 10.2 + nine
                                                 QoE adjustments -> Normalized
                                                 EBITDA 11.9 (QoEView)
  firm_bridge  `keystone_firm_model_summary.md` Reported EBITDA 10.20 + four
                                                 Firm adjustments, two of
                                                 them negative reserves ->
                                                 Firm-underwritten EBITDA
                                                 11.40 (FirmView)
  cim_margin   `keystone_seller_cim.md`         seller-adjusted EBITDA 12.7 /
                                                 revenue 74.0 -> 17.2% margin
                                                 (SellerView), one hop

Run: `python3 -m tools.experiments.real_fixture_test` (needs
`ANTHROPIC_API_KEY`).

### What was found, running it -- this changes the picture from the
### synthetic test, not just confirms it

- **The unmodified baseline already handles real documents well.** All
  three fragments: correct final total, correct `basis` per source-type
  (ReportedView / QoEView / FirmView / SellerView), and -- this is the
  important one -- the nine "EBITDA Adjustment" claims in `qoe_bridge`,
  which all share the same `metric` and `basis`, are each given a distinct
  `measurement` matching their real table row ("Founder / executive
  compensation", "Transaction-readiness and professional fees", etc). Zero
  identity collisions in any of the nine runs (3 fragments x 3 modes).
  `measurement` is exactly the schema's own designed answer to this, and on
  these real documents it already works without any graph assistance.
- **This means the synthetic test's "naming collision" framing does not
  transfer as-is.** That test only checked `derived` claims for distinct
  names; on real documents almost nothing needs deriving, because real
  bridges STATE their own total ("normalized FY2025 EBITDA is $11.9m") --
  the model can correctly extract it as `attested`/`asserted` and copy it,
  never triggering the derived-naming problem at all. The real disambiguator
  in play here is `measurement` across same-metric-same-basis siblings, and
  it held up.
- **The document-graph extractor's genuine incremental value, where it
  showed up: independent arithmetic verification of a stated total**, not
  recovery of a missing one. On `firm_bridge` it produced an explicit
  6-input derivation ($10.20 + $1.70 − $0.20 − $0.15 − $0.10 − $0.05 =
  $11.40) proving the document's own printed total is internally
  consistent, where the baseline had just copied "$11.40m" as a stated
  fact without checking it against its own components. That is a real,
  distinct capability -- catching a document whose own math doesn't add up
  -- worth taking seriously given this session's own PAN-100 history of
  chart values that were confidently wrong.
- **But it did not do this consistently.** On `qoe_bridge` -- a clearer
  table, headed "Normalized EBITDA schedule", 9 line items instead of 5 --
  the graph extractor produced 0 dependency edges: every claim independent,
  no verification attempted, functionally identical to the baseline. Same
  mechanism, same kind of table, opposite behaviour. Not explained by
  anything found so far.
- **A real regression, not a synthetic-test artifact: the graph extractor
  got `basis` wrong on `qoe_bridge`** -- `FirmView` instead of the correct
  `QoEView` -- while the baseline and the assisted run, given the exact
  same fragment text, both got it right. The only difference is the longer
  `SYSTEM_PROMPT_GRAPH` (production `SYSTEM_PROMPT` plus the local_id/
  depends_on instructions). This is concrete evidence that appending
  instructions for the new capability can measurably degrade an unrelated,
  already-working part of the same prompt -- a real cost of this approach,
  not just a hypothetical one.
- Test harness caveat, not swept under the rug: all three fragments were
  sent with the same hardcoded `SOURCE: ... management presentation` line
  regardless of the fragment's real document type (QoE report, internal
  firm model, CIM) -- unlike production, which reads the real `doc_type`.
  The model still got `basis` right in 8 of 9 runs despite this, but the
  one miss above should be re-checked with the correct source line before
  concluding anything stronger about it.

### Status

Real documents change the conclusion, not just add color: on these three
fragments the CURRENT production extractor needs no help to get the totals
and the identities right, because real bridges state their own conclusion.
The one demonstrated value-add is arithmetic self-verification of a stated
total, which only fired on one of two structurally similar bridges, and
came with a real, measured accuracy cost on a field (`basis`) it had no
business touching. Before this goes anywhere near production: fix the
hardcoded SOURCE line and re-test, find a real fragment where the total is
genuinely NOT stated (rarer than expected -- none of these three qualified),
and treat the inconsistent edge-finding and the basis regression as open
problems, not noise.

### Two more real fragments -- this time it gets worse, not better

Two further fragments from `keystone_monitoring_junecompliance2027.md` (a
real held-back monitoring document, layer 2), richer and messier than the
first three:

  covenant_ebitda_dispute   two competing EBITDA bridges from the same
                            reported figure ($9.40m) -- lender-accepted
                            ($10.80m, controlling) vs management-proposed
                            ($11.60m, rejected) -- a genuine live dispute
                            between two parties, not just one basis.
  leverage_covenant_test    three concurrent covenant tests (total net
                            leverage, FCCR, minimum liquidity), each its
                            own actual/threshold/headroom, sharing one debt
                            table (three debt instruments -> gross funded
                            debt -> net debt -> a 4.70x leverage ratio
                            against covenant EBITDA).

- `covenant_ebitda_dispute` mostly held up: all three modes got the
  controlling total (10.8) and kept the two bridges apart with zero
  identity collisions. But the derived "how close to the 15% amendment cap"
  figure the source text alludes to ("within the amended 15% cap") got
  computed independently in each mode, correctly as 1.4/9.4 = 14.89% *in
  content* -- but landed under a DIFFERENT metric name each run: "Covenant
  Headroom" = 15 in (a), "Covenant Headroom" = 14.89 in (b), and the same
  14.89 value renamed to "Adjustment Supportability" in (c), with a
  DIFFERENT quantity (1.4, the raw dollar bridge) now sitting under
  "Covenant Headroom" instead. Three runs, three different names for
  overlapping concepts that are not in the source table at all -- exactly
  the instability risk flagged earlier, now reproduced on a real document
  for a genuinely novel (not literally stated) derived quantity.
- `leverage_covenant_test` is the sobering one. All three modes found the
  right final leverage figure (4.70x), but on the more complex structure
  (three separate covenant tests sharing one debt table) **all three
  produced real identity collisions** -- not a synthetic-test artifact:
  - (a) baseline: "Covenant Threshold" used for BOTH the 4.25x leverage cap
    and the 1.25x FCCR minimum, same basis, same non-distinguishing
    `measurement` ("total" both times) -- two different covenants collapsed
    into one identity. Same problem 3x over for "Covenant Headroom" across
    the leverage/FCCR/liquidity tests. 2 collision groups.
  - (b) document-graph extractor: fewer distinct concepts recovered
    overall, and a worse *semantic* mixup the collision checker cannot
    even catch -- "DDTL Availability" used once for the $5.955m DDTL debt
    tranche and again for $2.92m of *total liquidity*, two unrelated
    concepts that only escaped the checker because their `measurement`
    strings happened to differ. 1 flagged collision, but arguably a worse
    underlying confusion than what it flags.
  - (c) main extractor + document-graph context: **the worst of the
    three** -- 3 collision groups, more than the unassisted baseline. The
    graph context did not help here; it measurably hurt, opposite to what
    the two EBITDA-bridge fragments showed.
  - None of the three modes attempted the actual derivation chain (gross
    debt 53.0 − cash 2.2 = net debt 50.8, then 50.8 / covenant EBITDA 10.8
    = 4.70x) even though every input for it is present in the same table --
    consistent with every fragment tested so far: real Keystone documents
    state their conclusions, so `derived` essentially never fires on the
    final figure, whether or not the graph context is present.

This is the fifth and sixth real fragment tested (five real documents
total now, six fragments), and the pattern holds without exception: **no
fragment tested yet required the extractor to recover a genuinely unstated
final number** -- the one place graph assistance showed clear, repeatable
value (verifying a stated total's arithmetic, or computing a real but
unstated derived quantity like the 15% cap check) is also the one place
identity became unstable across runs. And on the structurally richer
fragment, the graph-context approach was measurably worse than doing
nothing at all. This is the strongest evidence yet against wiring this
into production as currently built -- the failure mode it was meant to
help with (missed derivation) barely occurs on real documents, while the
failure mode it does not help with (identity collision across concurrent,
structurally-similar concepts) got worse with it, not better.
