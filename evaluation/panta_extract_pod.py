#!/usr/bin/env python3
"""Extract every document the evaluation cases reference, on the GPU pod.

Stage 1 of the two-stage run, split out to keep the Anthropic API key off a
rented machine: this side reads documents and needs no credential, and the
answering stage runs locally against the JSON it writes.

Emits {test_id: {input_id: extracted_text}} so the local stage can be replayed
against the same extraction without paying for GPU time again -- which also
means a scoring change can be re-measured without re-reading the documents.

Run:  /venvs/granite/bin/python evaluation/panta_extract_pod.py \
          evaluation/fixtures/cases/panta_smoke.ndjson out.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

PADDLE_PYTHON = Path(os.environ.get("PE_OS_PADDLE_PYTHON", "/venvs/paddle/bin/python"))
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _paddle_convert(pdf: Path):
    """Route a PDF (or an image, PaddleOCR-VL accepts both) through the real
    engine, exactly as the test UI does. Shaped as Path -> convert_page,
    which doubles as the pdf_engine factory parse_pptx's PDF-fallback tier
    needs (it does not know the exported PDF's path until soffice creates
    it, so it cannot receive a pre-bound convert_page)."""
    out_json = pdf.with_suffix(".eval.paddle.json")
    proc = subprocess.run(
        [str(PADDLE_PYTHON), str(ROOT / "tools" / "paddle_engine.py"),
         str(pdf), str(out_json)],
        capture_output=True, timeout=1800,
    )
    if not out_json.exists():
        raise RuntimeError("paddle engine produced nothing: "
                           + proc.stderr.decode("utf-8", errors="replace")[-400:])
    payload = json.loads(out_json.read_text())
    if "error" in payload:
        raise RuntimeError(f"paddle engine failed: {payload['error']}")
    pages = payload.get("pages", {})

    def convert(image, page_num):
        page = pages.get(str(page_num)) or {}
        return page.get("markdown", ""), page.get("pictures", [])

    return convert


def extract(path: Path) -> str:
    """Everything the pipeline reads from one file, as text with locators.

    Images and PDFs share one convert_page (a bound per-page callable,
    since parse_pdf/parse_image already know the file they are reading).
    PPTX's PDF-fallback tier needs the factory form instead -- it creates
    its own PDF internally via soffice, so it cannot receive a callable
    pre-bound to a file it doesn't have yet -- and _paddle_convert is
    already exactly that shape.
    """
    from extract_v2 import parse_source

    suffix = path.suffix.lower()
    convert_page = _paddle_convert(path) if suffix in (".pdf", *IMAGE_SUFFIXES) else None
    pdf_engine = _paddle_convert if suffix == ".pptx" else None
    chunks = parse_source(path, convert_page=convert_page, pdf_engine=pdf_engine)
    return _render_chunks(chunks)


def _render_chunks(chunks) -> str:
    """Render chunks as locator-tagged text, headers and attachments included.

    Email headers and attachment filenames live on chunk.provenance, not
    chunk.body -- parse_email keeps them out of the body on purpose so
    re-chunking never splits a header across a word boundary. They still
    need to reach the answering stage, or "who is this from" has no source
    to cite even though the extractor read it.
    """
    parts = []
    for chunk in chunks:
        block = f"<<locator: {chunk.locator}>>\n{chunk.body}"
        prov = getattr(chunk, "provenance", None) or {}
        headers = prov.get("headers")
        if headers:
            block += "\n[headers] " + " | ".join(f"{k}={v}" for k, v in headers.items())
        names = prov.get("attachment_filenames")
        if names:
            block += "\n[attachments] " + ", ".join(names)
        parts.append(block)
    return "\n\n".join(parts)


def main() -> int:
    cases_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    cache: dict[str, str] = {}
    result: dict[str, dict[str, str]] = {}
    for line in cases_path.read_text().splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        per_input: dict[str, str] = {}
        for item in case.get("inputs", []):
            rel = item.get("path") or item.get("uri")
            input_id = item.get("input_id")
            if rel in cache:                      # the same PDF is used by 2 cases
                per_input[input_id] = cache[rel]
                continue
            started = time.perf_counter()
            try:
                text = extract(ROOT / rel)
                note = f"{time.perf_counter() - started:.1f}s, {len(text)} chars"
            except Exception as exc:
                text = f"(extraction failed: {type(exc).__name__}: {exc})"
                note = "FAILED"
            cache[rel] = text
            per_input[input_id] = text
            print(f"  {case['test_id']:34} {input_id:22} {rel.split('/')[-1]:34} {note}",
                  file=sys.stderr)
        result[case["test_id"]] = per_input
    out_path.write_text(json.dumps(result, indent=1))
    print(f"wrote {out_path} ({len(result)} cases)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
