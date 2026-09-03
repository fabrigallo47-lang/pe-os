---
written-by: Codex
issue: PAN-99
measured-at: 2026-09-02
status: recommendation
---

# PAN-99 — Docling physical-extraction spike

## Decision

**Adopt Docling for PDF only, behind an optional local worker; do not make it
the shared PDF+DOCX backbone.**

The measured PDF result is compelling where the current route is weak:
Docling recovered a 6×8 financial table exactly from both a searchable PDF and
its raster-only scan (48/48 cells in each case), while pdfplumber returned no
text or table from the scan.  It also emits page/bounding-box provenance for
every recovered PDF item.  The trade-off is operationally large: a clean
Python 3.12 environment grew by 1.28 GiB at install, the standard PDF models
and OCR assets added about 537 MiB on first use, a cold conversion took 43.97 s,
and the peak parent-process RSS was 2,555 MiB.

DOCX does not justify that cost as a shared route.  Docling preserved the test
table and exposed the comment text, but emitted zero pages and zero bounding
boxes; the comment was a detached text item rather than a link to the commented
run.  PANTA's existing deterministic OOXML route completed the same document
in 0.09 s and retained a paragraph-range locator.  PAN-103 can add native table,
comment-anchor, and tracked-change handling without placing a multi-GiB ML
runtime on every DOCX ingestion path.

Chart-to-table enrichment is not acceptable as the default route.  Its first
run was stopped after **more than 124 minutes** with no output artifact.  By
then it had downloaded a 7.46 GiB Granite Vision 4.1 4B model; total model cache
was 7.98 GiB.  Default Docling retained all six visible bar labels but produced
no structured series.  Chart data must therefore remain a separate optional
capability with fail-closed review/fallback behavior.

## Method and scope

Host: Apple arm64, macOS 26.5.1, Python 3.12.11, CPU execution, four threads.
Docling was pinned to the then-current PyPI release **2.124.0** and installed in
`/private/tmp`; neither the repository `.venv` nor production requirements were
changed.  The model cache and every generated artifact also lived outside the
repository.

The repository does not contain a Keystone CIM PDF.  To avoid inventing or
exposing a private artifact, the financial ground truth was generated from the
checked-in synthetic workbook `tools/fixtures/pan36_synthetic_model.xlsx` and
is explicitly synthetic:

1. Searchable one-page Keystone financial PDF: 18,995 bytes, one 6×8 table and
   one six-bar revenue chart.
2. Raster-only version of that page: 6,532,181 bytes, no PDF text layer.
3. Checked-in `PANTA_V20_Product_User_Guide.pdf`: five pages, 48,471 bytes.
4. A 37,694-byte DOCX probe containing the same table and one anchored reviewer
   comment was used only to decide whether DOCX belongs on the shared route.

The benchmark harness is `tools/benchmark_pan99_docling.py`.  It runs Docling
and pdfplumber in isolated subprocesses, records wall latency and output shape,
and treats a conversion as successful only when a parseable JSON artifact
exists.  This last check matters: an earlier release observed during setup
returned exit code zero after a document-level PDF conversion failure.

## Measurements

### Footprint and cold start

| Measurement | Result |
|---|---:|
| Empty venv | 12,640 KiB |
| Venv after `docling==2.124.0` | 1,354,760 KiB (1.292 GiB) |
| Installed footprint added | 1,342,120 KiB (1.280 GiB) |
| Install time, no pip cache | 45.52 s |
| Installed distributions | 102 |
| Standard HF model cache after first run | 530,008,922 bytes (505.5 MiB) |
| RapidOCR assets added inside venv on first run | 32,324 KiB (31.6 MiB) |
| First-run model/OCR acquisition | about 537 MiB |
| Venv + standard model cache after first run | 1,904,716 KiB (1.816 GiB) |
| First successful conversion, end to end | 43.967 s |
| Docling-reported conversion portion | 39.25 s |
| Peak parent-process RSS on cold run | 2,555.2 MiB |
| Optional chart model alone | 7,818,672 KiB (7.456 GiB) |
| Total cache after chart attempt | 8,369,192 KiB (7.981 GiB) |
| Chart attempt | >124 min, interrupted, no output artifact |

The standard first run downloaded the layout/table models into `HF_HOME` and
RapidOCR's PyTorch OCR weights into `site-packages/rapidocr/models`.  Production
must pre-seed and checksum both locations before switching to network-disabled
runtime; pre-seeding only the Hugging Face cache is insufficient.

RapidOCR readiness is version/backend-sensitive.  In the initial 2.67.0
preflight, explicitly selecting RapidOCR failed because `onnxruntime` was not
installed even though the `rapidocr` package itself was present.  Release
2.124.0 instead selected RapidOCR's PyTorch engine and succeeded after the
31.6 MiB first-use weight download.  A production image must pin and smoke-test
the exact OCR engine; importing `rapidocr` is not a sufficient readiness check.

### Warm per-document latency and output

Each row starts a fresh CLI process with the model cache already present.  The
parent RSS was measurable on the unsandboxed cold run; the warm subprocess
sampler was unavailable in the restricted runner and is deliberately reported
as unknown rather than estimated.

| Document | Docling wall | Internal conversion | Docling output | pdfplumber wall/output |
|---|---:|---:|---|---|
| Native financial PDF | 7.155 s | 3.45 s | 1 table, 48 cells; 22 text items; 1 picture | 0.166 s; 1 table/48 cells when `extract_tables()` is called |
| Raster financial PDF | 8.086 s | 4.56 s | 1 table, 48 cells; 22 OCR text items; 1 picture | 0.109 s; 0 text, 0 tables |
| Five-page product guide | 6.803 s | 3.23 s | 125 text items; 2 layout tables/62 cells | 0.222 s; 1,573 words, 0 tables |
| Synthetic financial DOCX | 4.094 s | 0.03 s | 1 table/48 cells; 4 text items; 0 page/bbox locators | PANTA OOXML route: 0.09 s, 1 chunk with paragraph-range locator |

The direct pdfplumber comparison is deliberately more generous than PANTA's
current `parse_pdf`: the library probe calls `extract_tables()`, while the
production parser currently calls only `extract_text()`.  Thus the native-PDF
row shows that a clean ruled table does not need ML in principle, not that the
current PANTA parser already preserves its structure.

### Quality checks

| Capability | Ground truth | Docling result | Current route |
|---|---:|---:|---:|
| Native table cell accuracy | 48 cells | 48/48 exact | Text-only in PANTA; pdfplumber can obtain 48/48 with new glue |
| Scanned table cell accuracy | 48 cells | 48/48 exact | 0/48; scan is rejected as OCR-required |
| Native chart visible labels | 6 values | 6/6 recovered as text | Labels may appear in page text only |
| Native chart structured series, default | 1 series | 0/1 | 0/1 |
| Chart enrichment | 1 series | No result after >124 min and 7.46 GiB model download | Not supported |
| PDF physical provenance | page + geometry | 24/24 logical items had page/bbox on financial pages | Page only; no item bbox |
| DOCX table structure | 6×8 | 6×8 exact | Values flattened into paragraph order |
| DOCX comment linkage | one comment anchored to a run | Comment text present, anchor absent | Comment absent |
| DOCX physical locator | paragraph/section address | no page/bbox/item source position | `filename::paragraphs:1-51` |

No tracked-change fidelity claim is made: the spike had no representative
tracked-change artifact, and accepting Docling for DOCX would still require a
separate redline benchmark.  This uncertainty strengthens the PDF-only choice.

## Docling framework vs TableFormer standalone

This is an **architectural comparison, not a direct standalone-TableFormer
benchmark**.  Both choices use TableFormer for table structure.  On the clean
native table, even pdfplumber reached 48/48 cells, so the spike does not show a
quality advantage attributable to the Docling framework there.  Docling's
measured advantage is orchestration around the model: PDF decoding, layout
objects, OCR selection, table reconstruction, page/bbox geometry, and one
versioned document schema.  A standalone TableFormer route should have a
smaller dependency/model surface, but PANTA would have to build and own the OCR,
page-rendering, geometry normalization, failure detection, and chart fallback
glue that Docling already coordinates.

For PDF-only ingestion that orchestration is worth an optional worker.  It is
not evidence for adding Docling to DOCX, and the Granite chart path overwhelms
the maintenance advantage.  The implementation decision should therefore be:

- Docling standard pipeline for tables/layout and scanned-page OCR.
- Deterministic/native extraction first for clean PDFs where sufficient.
- No Granite chart model in the default image; chart series remain a separate
  opt-in experiment or require the native spreadsheet/source chart data.

Docling's official documentation confirms that RapidOCR is a selectable local
engine and that TableFormer accurate/fast modes run locally; chart enrichment
is a separate bar/pie/line capability rather than part of default conversion:
[installation and OCR engines](https://docling-project.github.io/docling/getting_started/installation/),
[model catalog](https://docling-project.github.io/docling/usage/model_catalog/),
[chart extraction example](https://github.com/docling-project/docling/blob/main/docs/examples/chart_extraction.py),
and [CLI reference](https://github.com/docling-project/docling/blob/main/docs/reference/cli.md).

## Proposed PANTA mapping

### `Chunk`

Emit one chunk per Docling text/table logical item, not one page-sized blob:

- `body`: text as read; tables as a deterministic Markdown/CSV grid including
  empty cells, row/column spans, and headers.
- `locator`: `p{page_one_based}::bbox:{l},{t},{r},{b}::item:{self_ref}` after
  normalizing the bbox to top-left coordinates.  Never expose Docling's
  zero-based `page_no` directly.
- `page_or_slide_number`: `prov.page_no + 1`.
- `section_heading`: nearest preceding section header from document order.
- `chunk_id`: keep PANTA's current body hash for compatibility; store
  `self_ref` and geometry separately so repeated bodies remain reviewable.
- `provenance`: retain existing `source_id`, `source_version_id`, `case_id`,
  `original_filename`, and `locator`, and add `parser_capability`, Docling/core
  versions, PDF backend, OCR engine/mode, table engine/mode, `self_ref`, raw
  bbox, coordinate origin, and whether content was OCR-derived.

Tables and OCR fragments can then flow through the existing L2/L3 stages.  A
picture is not evidence of chart data: emit a chart-data chunk only when a
tabular series and its page/bbox exist; otherwise emit a capability failure or
review proposal, never invented values.

### `source_capabilities.py`

PAN-100 should add or refine these explicit capabilities:

| capability_id | support | success gate | failure action |
|---|---|---|---|
| `docling_pdf_layout` | `SUPPORTED_IF_READER_AVAILABLE` | JSON artifact, all emitted items have page/bbox | retry native parser or reject with install/cache action |
| `docling_pdf_tables` | `SUPPORTED_IF_READER_AVAILABLE` | non-empty rectangular cells with page/bbox | preserve page text and create human-review proposal |
| `scanned_pdf_ocr` | `SUPPORTED_IF_READER_AVAILABLE` | OCR text/table exists for every accepted image-only page | `REJECTED/OCR_REQUIRED`; never accept empty placeholder tables |
| `pdf_chart_data` | `UNSUPPORTED` by default | none in standard image | request source spreadsheet/native chart data or verified manual review |

The optional worker must fail closed on timeout, missing model checksums,
invalid/absent JSON, zero-cell placeholder tables, or logical items without PDF
page geometry.  `capability_failure()` should return the existing stable
`REJECTED` envelope with the relevant `capability_id` and a concrete action.
The current native PDF reader remains the low-latency fallback for searchable,
text-only documents.

## Reproduction

Create isolated environments outside the repository, pin versions, pre-seed a
temporary cache, and run the checked-in harness:

```bash
python3.12 -m venv /tmp/pan99-docling
/tmp/pan99-docling/bin/pip install --no-cache-dir 'docling==2.124.0'
python3.12 -m venv /tmp/pan99-pdfplumber
/tmp/pan99-pdfplumber/bin/pip install --no-cache-dir 'pdfplumber==0.11.7'

python tools/benchmark_pan99_docling.py \
  --docling /tmp/pan99-docling/bin/docling \
  --pdfplumber-python /tmp/pan99-pdfplumber/bin/python \
  --cache-dir /tmp/pan99-models \
  --output-dir /tmp/pan99-output \
  --result /tmp/pan99-result.json \
  report.pdf scanned-report.pdf report.docx
```

After the first successful run, add `--offline` and verify that the same inputs
still succeed.  `--enrich-chart-extraction` is available only for a deliberately
separate footprint experiment; it must not be run implicitly in production.
