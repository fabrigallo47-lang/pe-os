#!/usr/bin/env python3
"""Reproducible, dependency-neutral benchmark harness for PAN-99.

The harness deliberately runs Docling and pdfplumber in subprocesses so the
repository environment stays untouched.  A successful Docling process is not
enough: released Docling CLIs can exit zero after a document-level conversion
failure, so this tool also requires a valid JSON artifact for every input.

Example (paths intentionally point outside the repository)::

    python tools/benchmark_pan99_docling.py \
      --docling /tmp/docling-venv/bin/docling \
      --pdfplumber-python /tmp/pdf-venv/bin/python \
      --cache-dir /tmp/docling-cache \
      --output-dir /tmp/pan99-output \
      report.pdf scanned-report.pdf
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any


def _directory_size(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    # Hugging Face snapshots are symlink views over ``blobs``.  Counting the
    # link targets twice materially overstates the downloaded model footprint.
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file() and not item.is_symlink()
    )


def _run(command: list[str], env: dict[str, str]) -> dict[str, Any]:
    """Run one process and sample its parent RSS without extra dependencies."""
    started = time.perf_counter()
    peak_rss_kib = 0
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        rss_sampling_available = True
        while process.poll() is None:
            if rss_sampling_available:
                try:
                    rss = subprocess.run(
                        ["ps", "-o", "rss=", "-p", str(process.pid)],
                        check=False,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    if rss.isdigit():
                        peak_rss_kib = max(peak_rss_kib, int(rss))
                except OSError:
                    # Sandboxed runners can prohibit process inspection.  The
                    # latency and output checks remain valid in that case.
                    rss_sampling_available = False
            time.sleep(0.05)
        log.seek(0)
        output = log.read()
    return {
        "returncode": process.returncode,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_parent_rss_mib": round(peak_rss_kib / 1024, 1) if rss_sampling_available else None,
        "log_tail": output[-2000:],
    }


def _docling_summary(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    tables = document.get("tables") or []
    return {
        "schema_name": document.get("schema_name"),
        "schema_version": document.get("version"),
        "pages": len(document.get("pages") or {}),
        "text_items": len(document.get("texts") or []),
        "tables": len(tables),
        "table_cells": sum(
            len(((table.get("data") or {}).get("table_cells") or []))
            for table in tables
        ),
        "pictures": len(document.get("pictures") or []),
        "items_with_page_bbox": sum(
            1
            for collection in ("texts", "tables", "pictures")
            for item in (document.get(collection) or [])
            if any(prov.get("page_no") is not None and prov.get("bbox") for prov in item.get("prov", []))
        ),
    }


_PDFPLUMBER_PROBE = r"""
import json, pdfplumber, sys
path = sys.argv[1]
with pdfplumber.open(path) as pdf:
    texts = [(page.extract_text() or '') for page in pdf.pages]
    tables = [table for page in pdf.pages for table in (page.extract_tables() or [])]
print(json.dumps({
    'pages': len(pdf.pages),
    'text_pages': sum(bool(text.strip()) for text in texts),
    'words': sum(len(text.split()) for text in texts),
    'tables': len(tables),
    'table_cells': sum(sum(len(row) for row in table) for table in tables),
}))
"""


def _baseline(python: Path, source: Path, env: dict[str, str]) -> dict[str, Any]:
    run = _run([str(python), "-c", _PDFPLUMBER_PROBE, str(source)], env)
    if run["returncode"] == 0:
        try:
            run["summary"] = json.loads(run["log_tail"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            run["summary"] = None
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--docling", type=Path, required=True)
    parser.add_argument("--pdfplumber-python", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, help="Write the machine-readable summary here")
    parser.add_argument("--offline", action="store_true", help="Forbid Hugging Face network access")
    parser.add_argument("--force-ocr", action="store_true", help="Replace PDF text with OCR output")
    parser.add_argument("--ocr-engine", help="Select a Docling OCR engine, for example rapidocr")
    parser.add_argument(
        "--enrich-chart-extraction",
        action="store_true",
        help="Run Docling's optional chart-to-table enrichment for PDF inputs",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if args.cache_dir:
        env["HF_HOME"] = str(args.cache_dir)
        env["DOCLING_CACHE_DIR"] = str(args.cache_dir / "docling")
    if args.offline:
        env["HF_HUB_OFFLINE"] = "1"

    result: dict[str, Any] = {
        "schema": "panta.pan99-docling-benchmark/1.0",
        "docling_executable": str(args.docling),
        "cache_bytes_before": _directory_size(args.cache_dir),
        "documents": [],
    }
    for index, source in enumerate(args.sources, 1):
        input_format = {".pdf": "pdf", ".docx": "docx"}.get(source.suffix.lower())
        if input_format is None:
            parser.error(f"unsupported benchmark source: {source} (expected PDF or DOCX)")
        output = args.output_dir / f"{index:02d}-{source.stem}"
        output.mkdir(parents=True, exist_ok=True)
        expected_json = output / f"{source.stem}.json"
        command = [
            str(args.docling), "convert", str(source), "--from", input_format, "--to", "json",
            "--image-export-mode", "placeholder", "--output", str(output),
            "--device", "cpu", "--num-threads", "4",
        ]
        if input_format == "pdf":
            command.extend(["--pdf-backend", "pypdfium2"])
        if args.force_ocr and input_format == "pdf":
            command.append("--force-ocr")
        if args.ocr_engine and input_format == "pdf":
            command.extend(["--ocr-engine", args.ocr_engine])
        if args.enrich_chart_extraction and input_format == "pdf":
            command.append("--enrich-chart-extraction")
        run = _run(command, env)
        run["artifact_exists"] = expected_json.exists()
        run["success"] = run["returncode"] == 0 and expected_json.exists()
        if run["success"]:
            try:
                run["summary"] = _docling_summary(expected_json)
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                run["success"] = False
                run["artifact_error"] = str(exc)
        entry: dict[str, Any] = {
            "source": str(source),
            "source_bytes": source.stat().st_size,
            "docling": run,
        }
        if args.pdfplumber_python and input_format == "pdf":
            entry["pdfplumber"] = _baseline(args.pdfplumber_python, source, env)
        result["documents"].append(entry)

    result["cache_bytes_after"] = _directory_size(args.cache_dir)
    result["cache_bytes_added"] = result["cache_bytes_after"] - result["cache_bytes_before"]
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if all(item["docling"]["success"] for item in result["documents"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
