# PANTA multimodal document evaluation

This package evaluates two different capabilities without conflating them:

1. **Information extraction**: text, fields, tables, layout, images, charts,
   attachments and their source locations.
2. **Document understanding**: question answering, comparisons, summaries,
   cross-document reasoning, grounding and correct abstention.

For semantic claim extraction specifically, see
[`SEMANTIC_CLAIM_EVAL.md`](SEMANTIC_CLAIM_EVAL.md). It adds claim identity,
economic basis, provenance, derivations, graph edges, abstention and temporal
leakage tests over raw synthetic documents.

Every benchmark is converted to one versioned case contract. The original gold
labels stay intact under canonical fields or `gold.native`; the evaluator then
applies comparable metrics where that comparison is meaningful. Dataset-specific
leaderboard scoring can be supplied as `native:<metric>` rather than approximated.

## What is included

The repository contains an executable, non-sensitive smoke dataset rather than
only test code. Its nine gold cases cover:

| Source | Extraction/understanding covered | Visual or mixed evidence |
|---|---|---|
| PDF | text, table, reading order, grounding | embedded image and chart |
| Word (`.docx`) | semantic QA and abstention | embedded image |
| PowerPoint (`.pptx`) | visual QA and chart values | native chart |
| Excel (`.xlsx`) | typed fields, semantic facts and cell grounding | formula plus native chart |
| Outlook-compatible email (`.eml`) | headers, bodies and attachments | PDF and PNG attachments |
| Image (`.png`) | OCR, field extraction and visual QA | text plus chart |
| Email + PDF | cross-document mixed QA | attachment evidence from both inputs |

The fixtures live in `evaluation/fixtures/documents`, the gold cases in
`evaluation/fixtures/cases`, and an oracle prediction file used to verify the
evaluation contract in `evaluation/fixtures/predictions/perfect.ndjson`.

The benchmark registry additionally covers modern and legacy containers through
adapters for OfficeComprehensionBench, OmniDocBench, DocILE, DocVQA, SlideVQA,
SpreadsheetBench, SpreadsheetBench 2, Apache Tika fixtures, QAConv and EmailSum. This includes
`.doc`, `.docx`, `.ppt`, `.pptx`, `.xls`, `.xlsx`, `.xlsm`, `.msg`, `.pst`,
`.eml`, `.mbox`, PDF and common raster/vector image formats. Public corpora are not copied into
this repository: several require license acceptance, credentials, or retain
private test labels.

## Quick start

From the repository root:

```bash
make document-eval-validate
make document-eval
make document-information-eval  # only structure-independent information gates
```

The validation command checks schemas, unique IDs, fixture existence and every
declared SHA-256 digest. The run command gates on all nine smoke cases and writes
JSON, NDJSON and Markdown reports below `.panta-eval/runs/`.

Equivalent direct commands are:

```bash
.venv/bin/python -m evaluation.cli validate \
  --cases evaluation/fixtures/cases \
  --predictions evaluation/fixtures/predictions/perfect.ndjson \
  --require-files

.venv/bin/python -m evaluation.cli run \
  --cases evaluation/fixtures/cases \
  --predictions evaluation/fixtures/predictions/perfect.ndjson
```

Filter a run by any repeatable dimension:

```bash
.venv/bin/python -m evaluation.cli run \
  --cases evaluation/fixtures/cases \
  --predictions evaluation/fixtures/predictions/perfect.ndjson \
  --family image --task visual_qa --tag chart
```

## Running a real extraction system

Use `--system-command` to evaluate any executable that accepts one JSON case on
standard input and emits one prediction object on standard output:

```bash
.venv/bin/python -m evaluation.cli run \
  --cases evaluation/fixtures/cases \
  --system-command '.venv/bin/python path/to/predict.py'
```

The evaluator deliberately removes `gold`, expected evidence, metrics and
acceptance thresholds before invoking the command. The process receives only the
identity, benchmark metadata, task, inputs, query and tags. It must return:

```json
{
  "schema_version": "panta-eval.prediction/1.0",
  "test_id": "panta-smoke.docx.qa-001",
  "status": "success",
  "answer": "Maria Rossi",
  "evidence": [
    {
      "input_id": "word-review",
      "locator": {"type": "word", "section": "Investment decision"}
    }
  ]
}
```

One process is invoked per case. Non-zero exits, invalid JSON and timeouts become
explicit error predictions rather than terminating the whole run.

## The common schema

The schema is a technical contract, not a replacement for each dataset's meaning.
It fixes the names and types needed to combine results:

- `benchmark`: dataset ID, version, original sample ID and optional native track;
- `inputs`: one or more files/URIs, family, format, role, parent attachment and hash;
- `task` and `query`: the capability being tested and its instruction;
- `gold`: answers, assertions, fields or semantic facts, canonical content, layout
  elements, media, expected status and untouched dataset-specific annotations;
- `evidence`: typed locators for pages, slides, spreadsheet ranges, Word sections,
  email parts, attachments, messages and image regions;
- `metrics` and `acceptance`: scoring functions, required outputs and pass threshold;
- `diagnostic_metrics`: additional measurements shown in reports but excluded from
  the gate score.

The strict JSON Schemas are in `evaluation/schemas`. Unknown top-level properties
fail validation, while `gold.native` and prediction metadata intentionally remain
extensible for upstream evaluator details.

### Evaluation profiles

Use `evaluation_profile: "information_graph"` when downstream processing only
needs the information that will become graph facts. In this profile, gold may use
explicit `facts` or existing `fields`; fields are projected to facts automatically,
so old gold data can migrate incrementally. A fact can carry `fact_id`,
`concept_id`, `subject`, `predicate`, `aliases`, `value`, `unit`, `qualifiers`,
`input_id` and `locator`.

The matcher aligns facts one-to-one by canonical concept/alias or compatible source
locator. Labels are normalized for case, whitespace, punctuation and separators,
so `revenue_eur_m` matches `Revenue (EUR m)`. Values and semantic qualifiers are
then scored independently; the locator measures grounding and is not part of the
required output shape. Equal values with unrelated concepts do not match.

Set `gold.coverage` explicitly:

- `subset`: the gold lists only required facts. Additional extracted facts are
  unlabelled and therefore do not reduce precision;
- `exhaustive`: the gold is complete, so unmatched predictions count as false
  positives.

The other declared profiles are `schema_strict`, `layout_fidelity` and `full`.
Profiles describe evaluation intent; each case's `metrics` remains the explicit,
reproducible scoring contract. For an information-only gate, use for example:

```json
{
  "evaluation_profile": "information_graph",
  "gold": {"coverage": "subset", "fields": []},
  "metrics": [
    "information_recall",
    "fact_value_accuracy",
    "fact_grounding_accuracy",
    "status_accuracy"
  ],
  "diagnostic_metrics": ["field_precision", "field_recall", "field_f1"]
}
```

This contract is container-independent: the same fact metrics work for PDF, Word,
PowerPoint, spreadsheets, email, standalone images, embedded images and mixed
multi-document cases. Layout, media and schema metrics can still be added as gates
when a use case actually depends on them.

The bundled information-only smoke selection currently exercises PDF, spreadsheet,
email and image extraction, including altered labels and additional valid facts.
The PDF information case also requires facts read from an embedded image, while
remaining independent of field order and document layout.
Run it with `make document-information-eval`; the complete smoke command still
covers PDF, Word, PowerPoint and mixed-document understanding as separate tracks.

## Metrics

Built-in deterministic metrics are:

- answer exact match, token F1, ANLS and ROUGE-1/2/L;
- nested structured-value accuracy with locale-aware numeric comparison;
- weighted assertion recall;
- strict field precision, recall and F1;
- structure-independent information recall, fact precision/F1, value accuracy,
  qualifier accuracy and fact grounding accuracy;
- evidence grounding F1 with locator matching and bounding-box IoU;
- normalized content similarity;
- document-element and media F1;
- success, abstention, unsupported and error status accuracy.

The per-case score is the mean of available requested `metrics`; diagnostic metrics
are reported but never enter that mean. Aggregate means honor the optional case
weight. A case passes only
when the expected status matches, every required metric is available, latency is
within any declared limit, and the score reaches its threshold. Reports aggregate
by benchmark, task, source family and metric; mixed cases appear in each relevant
family group.

## Adding public benchmark data

First inspect availability and licensing notes:

```bash
.venv/bin/python -m evaluation.cli datasets --verbose
.venv/bin/python -m evaluation.cli adapters
```

Acquire a dataset under `.panta-eval/datasets/<dataset>/<version>` according to
its upstream terms, then normalize its annotations. For example:

```bash
.venv/bin/python -m evaluation.cli adapt \
  --adapter docvqa \
  --source .panta-eval/datasets/docvqa/2026/val.json \
  --dataset-root .panta-eval/datasets/docvqa/2026 \
  --split validation --version 2026 \
  --output .panta-eval/cases/docvqa-validation.ndjson
```

Adapters accept JSON/NDJSON exports. For Parquet-hosted collections such as OCB
and DocVQA 2026, export the dataset rows to JSON with the official Hugging Face
`datasets` library first; for DocVQA, save each embedded page image and put its
path in `page_paths` (or use `--option images_dir=...` with the documented
`<doc_id>/page-NNN.png` layout). OCB's companion repository already generates
the supported query NDJSON directly.

Do not merge restricted binary corpora into Git. Combining benchmark results means
combining their canonical case records and reports; it does not change upstream
licenses or make private gold labels public.

## Adding a gold case

1. Put redistributable, non-sensitive source material under a versioned fixture or
   keep licensed material in `.panta-eval/datasets`.
2. Add a globally unique `test_id`, upstream `original_id`, exact format and input
   role, plus SHA-256 for stable local fixtures.
3. Store expected facts separately in `gold`; use `coverage: "subset"` when the
   annotations are intentionally incomplete, and never insert hidden answers into
   the source metadata presented to the system.
4. Add the narrowest reliable evidence locator and select task-appropriate metrics.
5. Validate, run the oracle contract check, then test a deliberately degraded
   prediction so the case is known to fail for the intended reason.

## Package map

| Path | Responsibility |
|---|---|
| `schemas/` | versioned case, locator, prediction and result contracts |
| `adapters/` | public benchmark normalization |
| `metrics.py` | deterministic comparable metrics |
| `evaluator.py` | one-case scoring and gates |
| `runner.py` | filtering, saved predictions and isolated command execution |
| `registry.py` + `registry/benchmarks.yaml` | versions, acquisition and license inventory |
| `report.py` | stable JSON summaries and Markdown output |
| `tests/` | schema, metric, adapter, no-leakage, registry and fixture tests |
