"""
The extract_v2 pipeline (L1-L4) behind the app's /api/extract route.

The previous flow sent the whole document to the model in one call and parsed
free-form JSON back. This runs the same four layers the local pipeline does:

  L1  deterministic chunking on markdown headings, 250 words per chunk
  L2  one schema-constrained tool_use call per chunk
  L3  deterministic validation, period normalisation, stable ids
  L4  deterministic assembly, dedup and conflict detection

Only L2 involves the model, so locators, identity and dedup stay reproducible.

The UI expects flat claims with keys like `epistemic` and `locator`, while
extract_v2 emits CAP-003 records with `epistemic_class` and `locator_hint` and
parks compiler metadata alongside. e3_to_claims() joins the two back together,
so the existing front end keeps working against the new extractor.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _extract_v2 import (           # noqa: E402  (vendored copy)
    parse_source, annotate_chunk, validate, assemble, _to_e3_manifest,
    _source_record, CHUNK_WORDS,
)

# One document is tens of chunks, not hundreds, and each L2 call is small.
# Keep concurrency modest so a burst never trips the provider's rate limit.
MAX_WORKERS = 8
# A hard ceiling so a pathological upload cannot fan out into hundreds of calls
# inside a single request.
MAX_CHUNKS = 120


def e3_to_claims(e3: dict) -> list[dict]:
    """CAP-003 manifest -> the flat claim shape the UI and graph builder read."""
    sidecar = {
        m.get("claim_id"): m
        for m in e3.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
        if m.get("claim_id")
    }
    out = []
    for c in e3.get("claims", []):
        meta = sidecar.get(c.get("claim_id"), {})
        perimeter = c.get("perimeter") or ""
        out.append({
            "subject":    perimeter.split(",")[0].strip() or "unknown",
            "metric":     meta.get("metric", ""),
            "value":      c.get("value"),
            "unit":       c.get("unit", ""),
            "as_of":      c.get("period") or "",
            "period":     c.get("period") or "",
            "perimeter":  perimeter,
            "topic":      meta.get("topic", ""),
            "source_doc": c.get("source_id", ""),
            "epistemic":  c.get("epistemic_class", "asserted"),
            "direction":  meta.get("direction", "context"),
            "bears_on":   [],
            "locator":    c.get("locator", ""),
            "author":     meta.get("author"),
            "statement":  c.get("statement", ""),
            "derivation": meta.get("derivation"),
            "claim_id":   c.get("claim_id"),
        })
    return out


def run_extraction(text: str, filename: str, deal: str, api_key: str,
                   chunk_words: int = CHUNK_WORDS,
                   source_path: "Path | None" = None) -> dict:
    """
    Run L1-L4 over one document. Returns claims + diagnostics.

    An upload arrives as text and is written to a temp file, because L1 chunks
    from disk. A caller that already has the file — the local ingest does —
    passes source_path instead: a PDF is not its own text, and re-encoding one
    through a string produces a file parse_source cannot open.
    """
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic SDK not installed in this deployment"}

    client = anthropic.Anthropic(api_key=api_key)

    # L1 needs a file on disk: reuse parse_source verbatim rather than
    # reimplementing the chunker, so segmentation matches the local pipeline
    # exactly — including the locators the claims are grounded on.
    suffix = Path(filename).suffix or ".md"
    stem = Path(filename).stem or "upload"
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        if source_path is not None:
            src = Path(source_path)
        else:
            src = Path(td) / f"{stem}{suffix}"
            src.write_text(text, encoding="utf-8")
        chunks = parse_source(src, max_words=chunk_words)
        record = _source_record(src)

        truncated = len(chunks) > MAX_CHUNKS
        if truncated:
            chunks = chunks[:MAX_CHUNKS]

        raw: list = []
        failures: list[str] = []
        if chunks:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {
                    pool.submit(annotate_chunk, ch, client, deal): ch
                    for ch in chunks
                }
                for fut in as_completed(futures):
                    try:
                        raw.extend(fut.result())
                    except Exception as exc:
                        # A single chunk failing must not lose the rest of the
                        # document. But failures have to be counted: when every
                        # chunk fails — a bad key, a rate limit — the result is
                        # zero claims, which is indistinguishable from a document
                        # that says nothing unless the count says otherwise.
                        failures.append(f"{futures[fut].chunk_id}: {exc}"[:200])
                        continue

    # validate() never raises and never returns None: it records problems on
    # validation_errors and assemble() decides what is admitted.
    canonical = [validate(r) for r in raw]
    invalid = [c for c in canonical if c.validation_errors]
    graph = assemble(canonical)
    e3 = _to_e3_manifest(graph, deal, "UPLOAD", [record])
    claims = e3_to_claims(e3)

    return {
        "claims": claims,
        "e3": e3,
        "elapsed": round(time.time() - t0, 2),
        "pipeline": {
            "extractor": "extract_v2",
            "chunks": len(chunks),
            "chunk_words": chunk_words,
            "raw_claims": len(raw),
            "chunks_failed": len(failures),
            "chunk_errors": failures[:5],
            "admitted": len(claims),
            "invalid": len(invalid),
            "rejected": getattr(graph, "rejected_count", 0),
            "conflicts": getattr(graph, "conflict_count", 0),
            "truncated": truncated,
            "max_chunks": MAX_CHUNKS if truncated else None,
        },
    }
