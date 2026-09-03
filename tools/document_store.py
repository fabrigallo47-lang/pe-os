#!/usr/bin/env python3
"""The documents themselves, indexed as they are, so extraction has context.

How this differs from tools/rag_index.py
----------------------------------------
``rag_index`` indexes *claims that have already been extracted*, and ranks them
against declared coverage gaps. It works on the output of understanding.

This works on the input. A source goes in whole, is chunked exactly as the
extractor chunks it, and stays retrievable as text — so when a later fragment is
read, what the deal has already said is available to read it *with*.

Both are retrieval; they answer different questions. "Which existing claim might
fill this gap?" is rag_index. "What does this deal call things?" is here.

What retrieval is for, and the line it must not cross
-----------------------------------------------------
Context supplies **vocabulary, not answers**: how this deal names its entities,
which definitions it has used, what its period conventions are. That makes a
later fragment readable in the deal's own terms.

It must not supply values already believed. An extractor shown "EBITDA was 11.4"
while reading a fragment about EBITDA can anchor on it and report the number it
was primed with rather than the one in front of it — silently converting a fresh
source into an echo. The corpus would then agree with itself for a reason that is
not evidence.

``retrieve`` therefore returns passages, and ``vocabulary_context`` returns only
the naming layer. The wiring into extraction should use the second.

Storage
-------
    pipeline_out/knowledge/<case_id>/documents.json

Append-only in effect: re-indexing the same source version replaces its own
chunks and leaves every other document untouched. Chunking reuses the
extractor's own L1 so a retrieved passage is the same unit the extractor sees;
tokenisation and cosine reuse rag_index so the two indexes cannot drift into
disagreeing about what a word is.

    python3 tools/document_store.py add <file> --case keystone
    python3 tools/document_store.py query "EBITDA definition" --case keystone
    python3 tools/document_store.py stats --case keystone
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# One tokeniser and one similarity for both indexes. Two implementations would
# eventually disagree about what counts as a token, and a retrieval bug of that
# shape is nearly impossible to see.
from tools.rag_index import _digest, _idf, cosine_similarity, tokenize  # noqa: E402

KNOWLEDGE_ROOT = ROOT / "pipeline_out" / "knowledge"
SCHEMA_VERSION = "panta.document-store/1.0"


def _store_path(case_id: str) -> Path:
    return KNOWLEDGE_ROOT / case_id / "documents.json"


def load_store(case_id: str) -> dict[str, Any]:
    path = _store_path(case_id)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "case_id": case_id, "documents": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(case_id: str, store: dict[str, Any]) -> Path:
    path = _store_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    store["index_digest"] = _digest(store.get("documents", []))
    path.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def add_document(case_id: str, source: Path) -> dict[str, Any]:
    """Chunk a source with the extractor's own L1 and keep the text.

    A source version is identified by the hash of its bytes, so re-adding an
    unchanged file is a no-op and an edited one replaces its own chunks without
    disturbing anything else.
    """
    from tools.extract_v2_physical import CHUNK_WORDS, parse_source

    raw = source.read_bytes()
    version = _digest(raw.decode("utf-8", "replace")[:2_000_000])
    store = load_store(case_id)

    existing = next((d for d in store["documents"] if d["source_version"] == version), None)
    if existing:
        return {"added": False, "reason": "questa versione del documento è già indicizzata",
                "source_version": version, "chunks": len(existing["chunks"])}

    chunks = parse_source(source, max_words=CHUNK_WORDS)
    document = {
        "source_id": source.stem,
        "filename": source.name,
        "source_version": version,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "chunks": [
            {
                "chunk_id": f"{version[:12]}-{index:04d}",
                "locator": chunk.locator,
                "heading": chunk.section_heading or "",
                "text": chunk.body,
                "tokens": tokenize(f"{chunk.section_heading or ''} {chunk.body}"),
            }
            for index, chunk in enumerate(chunks)
        ],
    }
    # Replace any earlier version of the same logical source: a document has one
    # current text, and keeping several would let retrieval return a passage the
    # deal has since revised.
    store["documents"] = [d for d in store["documents"]
                          if d["source_id"] != document["source_id"]] + [document]
    path = _save(case_id, store)
    return {"added": True, "source_version": version,
            "chunks": len(document["chunks"]), "path": str(path)}


def _all_chunks(store: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**chunk, "source_id": doc["source_id"], "filename": doc["filename"]}
            for doc in store.get("documents", []) for chunk in doc["chunks"]]


def retrieve(case_id: str, query: str, *, top_k: int = 4,
             min_score: float = 0.05) -> list[dict[str, Any]]:
    """Passages most similar to a query, best first.

    Returns text. Whatever consumes it decides what may be shown to a model —
    see ``vocabulary_context`` for the restricted form extraction should use.
    """
    chunks = _all_chunks(load_store(case_id))
    if not chunks:
        return []
    idf = _idf([c["tokens"] for c in chunks])
    query_tokens = tokenize(query)
    scored = [
        {"score": round(cosine_similarity(query_tokens, c["tokens"], idf), 6),
         "source_id": c["source_id"], "locator": c["locator"],
         "heading": c["heading"], "text": c["text"]}
        for c in chunks
    ]
    hits = [s for s in scored if s["score"] >= min_score]
    # Locator breaks score ties so the same query returns the same order twice.
    hits.sort(key=lambda s: (-s["score"], s["locator"]))
    return hits[:top_k]


def vocabulary_context(case_id: str, query: str, *, top_k: int = 4) -> dict[str, Any]:
    """The naming layer only: what this deal calls things.

    Deliberately not the passages. An extractor primed with "EBITDA was 11.4"
    while reading a fragment about EBITDA can report the number it was shown
    instead of the number in front of it, turning an independent source into an
    echo of the corpus. Entity names and defined terms carry no such risk: they
    make a fragment readable in the deal's own language without suggesting what
    it should say.

    Read from the claims the deal has already produced, not from its prose. A
    first attempt regexed capitalised phrases out of retrieved passages and
    returned "Diligence Question List This" and "Firm should" as entities — the
    vocabulary is already structured in entity / basis / period_canonical, and
    re-deriving it from text was strictly worse than reading it.

    The passages still decide *which* claims are relevant; they just no longer
    supply the vocabulary themselves.
    """
    hits = retrieve(case_id, query, top_k=top_k)

    entities: set[str] = set()
    definitions: set[str] = set()
    periods: set[str] = set()

    for path in sorted((ROOT / "pipeline_out").rglob("e3_claims.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sidecar = payload.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
        by_id = {str(item.get("claim_id")): item for item in sidecar}
        for claim in payload.get("claims", []):
            extra = by_id.get(str(claim.get("claim_id")), {})
            if extra.get("entity") and extra["entity"] != "unspecified":
                entities.add(str(extra["entity"]))
            if extra.get("basis") and extra["basis"] != "unspecified":
                definitions.add(str(extra["basis"]))
            if extra.get("period_canonical") and extra["period_canonical"] != "none":
                periods.add(str(extra["period_canonical"]))

    return {
        "entities": sorted(entities)[:20],
        "definitions": sorted(definitions)[:20],
        "periods": sorted(periods)[:12],
        "drawn_from": [{"source_id": h["source_id"], "locator": h["locator"]} for h in hits],
        "note": ("vocabolario letto dai claim strutturati, non dalla prosa; "
                 "vuoto finché una fonte non è stata estratta"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Document knowledge store")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="index a document as it is")
    add.add_argument("file", type=Path)
    add.add_argument("--case", required=True)

    query = sub.add_parser("query", help="retrieve passages")
    query.add_argument("text")
    query.add_argument("--case", required=True)
    query.add_argument("--top-k", type=int, default=4)
    query.add_argument("--vocabulary", action="store_true",
                       help="return only the naming layer, as extraction should use it")

    stats = sub.add_parser("stats")
    stats.add_argument("--case", required=True)

    args = parser.parse_args()

    if args.command == "add":
        if not args.file.exists():
            print(f"non trovato: {args.file}", file=sys.stderr)
            return 1
        result = add_document(args.case, args.file)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    if args.command == "query":
        if args.vocabulary:
            print(json.dumps(vocabulary_context(args.case, args.text, top_k=args.top_k),
                             ensure_ascii=False, indent=1))
            return 0
        for hit in retrieve(args.case, args.text, top_k=args.top_k):
            print(f"[{hit['score']:.3f}] {hit['source_id']} · {hit['locator']}")
            print(f"        {hit['text'][:200].strip()}\n")
        return 0

    store = load_store(args.case)
    chunks = _all_chunks(store)
    print(f"documenti : {len(store.get('documents', []))}")
    print(f"frammenti : {len(chunks)}")
    for doc in store.get("documents", []):
        print(f"  {doc['filename']:44} {len(doc['chunks']):4} frammenti  {doc['source_version'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
