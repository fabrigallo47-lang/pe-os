# Semantic claim extraction evaluation

This suite tests whether an extractor understands a claim, not merely whether it
copied a number. The same EBITDA value attached to the wrong period, perimeter or
economic basis is scored as a semantic error.

## What is executable now

The smoke dataset contains three raw-document cases:

1. a Keystone packet with 16 claims, five distinct EBITDA bases, customer rows,
   an explicitly requested concentration derivation and graph edges;
2. a marketing-only document where the correct output is no claims;
3. an as-of case where a later document must not leak into the answer.

Gold labels live separately in `fixtures/semantic_cases`. The fixture sources are
hash locked. Perfect predictions in `fixtures/semantic_predictions/perfect.json`
use different claim IDs from gold, proving that the scorer does not match on
hidden identifiers.

Run the contract and degradation tests:

```bash
make semantic-claim-eval-validate
make semantic-claim-eval-oracle
make semantic-claim-eval-test
```

The oracle is only a test of the evaluator. It is not evidence that the PANTA
extractor works. Evaluate a real one-case stdin/stdout adapter with:

```bash
make semantic-claim-eval SYSTEM_COMMAND='.venv/bin/python path/to/predict.py'
```

The evaluator removes gold, metrics and thresholds before invoking the adapter.

## Metrics and their meaning

| Metric | Failure it detects |
|---|---|
| `semantic_claim_precision` | invented or promotional claims |
| `semantic_claim_recall` | omitted claims |
| `semantic_claim_f1` | balanced claim-boundary detection |
| `semantic_exact_match` | any wrong identity, value, class or citation |
| `semantic_critical_exact_match` | exactness on decision-critical claims |
| `semantic_*_accuracy` | which dimension failed: entity, metric, measurement, period, scope, basis, scenario, value or epistemic class |
| `semantic_grounding_accuracy` | wrong input or source locator |
| `semantic_relation_f1` | missing or invented graph edges |
| `semantic_derivation_accuracy` | wrong or missing derivation operands |
| `semantic_abstention_accuracy` | marketing language converted into facts |
| `semantic_no_temporal_leakage` | use of evidence not knowable at the requested as-of time |

Detection and understanding are deliberately separate. A claim with the correct
source passage but a wrong basis can retain detection credit while failing basis
accuracy and exact match. For exhaustive gold, extra claims reduce precision; for
subset gold, unannotated extras are treated as unknown rather than false.

## Who performs the understanding work

Analysts should not draw the graph manually. The scalable annotation loop is:

1. a strong model proposes atomic claims and relations from normalized documents;
2. deterministic checks verify hashes, exact quotes, arithmetic, required fields,
   unique IDs, valid relation endpoints and time boundaries;
3. a second pass audits omissions and semantic collisions;
4. a human reviews compact claim cards only for model disagreement,
   decision-critical claims and a random quality-control sample;
5. approved labels are frozen before the system under test is run.

The repository includes an optional GPT-5.6 Sol adapter for steps 1 and 3. It uses
the Responses API with Structured Outputs and receives no gold labels:

```bash
.venv/bin/pip install -r evaluation/requirements-semantic.txt
OPENAI_API_KEY=... make semantic-claim-eval-sol
OPENAI_API_KEY=... make semantic-claim-eval-sol PASSES=2
```

The first command is a one-pass independent baseline. `PASSES=2` asks the same
model to audit its draft. API calls incur usage costs. The adapter accepts
normalized textual inputs; binary PDF, Word, slide, spreadsheet and email files
must first pass through the already-tested physical extraction layer.

Model-generated annotations are **silver**, not unquestionable gold. A headline
accuracy number for general text comprehension does not establish correctness on
PANTA's ontology, basis distinctions, abstention rules or temporal policy. Also,
using the same model to create labels and to score itself would be circular.

## Growing the dataset

Add examples by failure mode, not by random document count. Keep a mix of:

- simple atomic claims;
- same metric with different basis, period, scope or scenario;
- tables that require entity resolution and aggregation;
- contradictions and revisions across documents;
- derived claims with explicit operands;
- promotional or ambiguous passages requiring abstention;
- documents after an as-of boundary;
- real redacted documents representing production distributions.

Maintain three splits: development, frozen regression and a hidden holdout. Do
not tune prompts or thresholds on the holdout. Report every dimension above plus
results by document family and failure-mode tag; a single average conceals the
errors that matter most in investment decisions.
