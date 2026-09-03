#!/usr/bin/env python3
"""Convert a PDF to per-page markdown with the classic Docling pipeline
(layout model + TableFormer), for A/B comparison against Granite-Docling.

Runs as a SUBPROCESS in its own virtualenv, on purpose. `pip install
docling` resolves transformers down to 5.8.1, and the Granite-Docling path
in extract_v2 is verified on 5.16.1 -- installing both in one environment
would silently change the model we already trust to test the one we don't.
Two venvs, each at its working versions, talking over JSON on stdout.

Invoked by tools/extraction_test_ui.py; not part of the extraction
pipeline. Writes to a FILE, not stdout:

    {"pages": {"1": {"markdown": "...", "pictures": ["bar_chart"]}},
     "warnings": ["Orphan pdf_cell 39 recovered ..."], ...}

stdout is unusable as a channel here: TableFormer's MatchingPostProcessor
prints "Orphan pdf_cell N recovered to col=M by nearest-column fallback"
straight to stdout, which corrupts any JSON sharing it. Those lines are
kept as `warnings` rather than dropped -- they are the model telling you
its cell-to-column matching was uncertain, which is exactly the kind of
thing a table-extraction comparison should surface.

Run:  ~/venvs/pe-os-docling/bin/python tools/docling_engine.py <pdf> <out.json>
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path


def _accelerator_device():
    """Build AcceleratorOptions for PE_OS_DOCLING_DEVICE (auto|cuda|cpu|mps).

    Returns None when this docling build exposes no accelerator options, so
    an older/newer layout degrades to the library default instead of
    crashing the whole engine over a config knob.
    """
    import os
    name = os.environ.get("PE_OS_DOCLING_DEVICE", "auto").strip().lower()
    try:                                    # docling >= 2.26 moved these out
        from docling.datamodel.accelerator_options import (
            AcceleratorDevice, AcceleratorOptions)
    except ImportError:
        try:
            from docling.datamodel.pipeline_options import (
                AcceleratorDevice, AcceleratorOptions)
        except ImportError:
            return None
    try:
        return AcceleratorOptions(device=AcceleratorDevice(name))
    except ValueError:
        return AcceleratorOptions(device=AcceleratorDevice.AUTO)


def convert(pdf: Path) -> dict:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # do_picture_classification defaults to False, which makes a chart
    # vanish from the output entirely. The Granite path declares one as
    # IMAGE_NOT_EXTRACTED naming its type, so leaving this off would not
    # make docling look cleaner -- it would make it silently lossy, and
    # would compare "declares a chart" against "drops a chart" while
    # appearing to compare two table extractors.
    options = PdfPipelineOptions()
    options.do_picture_classification = True

    # Accelerator is set explicitly rather than left on AUTO. AUTO does find
    # CUDA, but silently: if the GPU wheel is missing on a GPU box this path
    # falls back to CPU and the only symptom is that it is slow, which is
    # indistinguishable from the thing we deployed a GPU to fix. Naming the
    # device makes that failure loud, and puts it in the report.
    device = _accelerator_device()
    if device is not None:
        options.accelerator_options = device

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    result = converter.convert(str(pdf))
    doc = result.document

    # Page count is needed up front so a page that yields nothing still
    # reports as an empty page rather than silently vanishing from the
    # comparison.
    try:
        total = len(doc.pages)
    except Exception:
        total = 0

    # Picture classifications are grouped by page so the caller can render
    # the same IMAGE_NOT_EXTRACTED markers the Granite path emits.
    pictures: dict[int, list[str]] = {}
    for pic in getattr(doc, "pictures", []) or []:
        try:
            page_no = pic.prov[0].page_no
        except Exception:
            continue
        # meta.classification is an object holding ranked `.predictions`,
        # not an iterable of labels -- iterating it directly yields nothing
        # and silently reports every page as picture-free.
        classification = getattr(getattr(pic, "meta", None), "classification", None)
        predictions = list(getattr(classification, "predictions", []) or [])
        if not predictions:
            pictures.setdefault(page_no, []).append("unclassified")
            continue
        # Only the top prediction is reported: the classifier ranks all 26
        # classes every time, so the tail is noise at ~1e-7 confidence.
        # The confidence rides along because "pie_chart (0.62)" and
        # "pie_chart (0.9998)" mean different things to a human deciding
        # whether to open the page.
        best = max(predictions, key=lambda p: getattr(p, "confidence", 0.0))
        pictures.setdefault(page_no, []).append(
            f"{best.class_name} ({getattr(best, 'confidence', 0.0):.2f})"
        )

    pages: dict[str, dict] = {}
    for page_no in range(1, total + 1):
        try:
            markdown = doc.export_to_markdown(page_no=page_no)
        except TypeError:
            # Older/newer docling_core without per-page export: fall back to
            # the whole document on page 1 rather than inventing a split.
            markdown = doc.export_to_markdown() if page_no == 1 else ""
        except Exception as exc:
            markdown = ""
            pages[str(page_no)] = {"markdown": "", "pictures": [],
                                   "error": f"{type(exc).__name__}: {exc}"}
            continue
        pages[str(page_no)] = {
            "markdown": markdown,
            "pictures": pictures.get(page_no, []),
        }
    return {"pages": pages, "page_count": total,
            "device": str(getattr(getattr(options, "accelerator_options", None),
                                  "device", "default"))}


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: docling_engine.py <pdf> <out.json>", file=sys.stderr)
        return 2
    out_path = Path(sys.argv[2])

    # Everything the libraries print goes to stderr from here on, so no
    # amount of third-party chatter can corrupt the result.
    captured = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, captured
    try:
        payload = convert(Path(sys.argv[1]))
        code = 0
    except Exception as exc:
        import traceback
        payload = {"error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()}
        code = 1
    finally:
        sys.stdout = real_stdout

    noise = captured.getvalue()
    payload["warnings"] = [
        line for line in noise.splitlines() if "WARNING" in line or "ERROR" in line
    ]
    sys.stderr.write(noise)
    out_path.write_text(json.dumps(payload))
    return code


if __name__ == "__main__":
    sys.exit(main())
