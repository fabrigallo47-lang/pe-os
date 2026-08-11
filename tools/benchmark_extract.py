#!/usr/bin/env python3
"""
Blind claim extraction benchmark — runs extractor on layer_1_ingested docs only.

Outputs to a temp JSON file (never writes to vault). The benchmark_runner then
scores this output against claims_live.csv.

Leakage guard: never reads layer_3_validation_DO_NOT_INGEST, claims_validation_only.csv,
or canonical/PANTA_Keystone_Canonical_Investment_Case_v1.1.json.

Usage:
    .venv/bin/python3 tools/benchmark_extract.py \
        --cic /path/to/PANTA_CIC_v1.1 \
        --out /tmp/benchmark_claims.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract import SYSTEM_PROMPT, llm_extract, parse_json

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("PEOS_MODEL", "claude-sonnet-5")

FORBIDDEN = {"layer_3_validation_DO_NOT_INGEST", "claims_validation_only.csv",
             "PANTA_Keystone_Canonical_Investment_Case_v1.1.json"}

# Source mapping: file name pattern → canonical source_id
SOURCE_MAP = {
    "seller_cim": "SRC-CIM",
    "data_room": "SRC-DR",
    "firm_initial_assessment": "SRC-IA",
    "ic_memo": "SRC-IC",
    "model_working": "SRC-MODEL",
    "model_summary": "SRC-MODEL-SUM",
    "qoe_report": "SRC-QOE",
    "question_list": "SRC-QL",
}


def _source_id(fname: str) -> str:
    for pat, sid in SOURCE_MAP.items():
        if pat in fname.lower():
            return sid
    return "SRC-UNKNOWN"


def _extract_one(artifact: pathlib.Path, deal_context: str) -> list[dict]:
    text = artifact.read_text(encoding="utf-8")
    if len(text) > 100_000:
        print(f"  [truncating {artifact.name}: {len(text)} → 100000 chars]")
        text = text[:100_000]

    user = (
        f"DEAL CONTEXT:\n{deal_context}\n\n"
        f"ARTIFACT ({artifact.name}):\n{text}"
    )
    print(f"  Extracting {artifact.name} ({len(text):,} chars)...", end=" ", flush=True)
    raw = llm_extract(SYSTEM_PROMPT, user)
    items = parse_json(raw)
    print(f"{len(items)} claims")

    src_id = _source_id(artifact.name)
    for item in items:
        item["source_id"] = src_id
        item["source_file"] = artifact.name
    return items


def main():
    parser = argparse.ArgumentParser(description="Benchmark claim extractor")
    parser.add_argument("--cic", required=True, help="Path to PANTA_CIC_v1.1 package root")
    parser.add_argument("--out", default="/tmp/benchmark_claims.json",
                        help="Output JSON path (default: /tmp/benchmark_claims.json)")
    parser.add_argument("--files", nargs="+", help="Specific filenames to extract (default: all L1)")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("ANTHROPIC_API_KEY not set")

    cic_dir = pathlib.Path(args.cic)
    l1_dir = cic_dir / "source_materials" / "layer_1_ingested"
    if not l1_dir.exists():
        sys.exit(f"Layer 1 directory not found: {l1_dir}")

    # Leakage guard
    for name in FORBIDDEN:
        for p in cic_dir.rglob(name):
            pass  # just checking, never reading

    # Collect markdown docs (skip xlsx — model parser handles that)
    docs = sorted(f for f in l1_dir.glob("*.md"))
    if args.files:
        docs = [f for f in docs if f.name in args.files]

    print(f"Layer-1 documents to extract ({len(docs)}):")
    for d in docs:
        print(f"  {d.name} ({d.stat().st_size:,} bytes)")
    print()

    deal_context = (
        "Deal: Project Keystone — PE firm evaluating acquisition of Alderstone, "
        "a regional provider of outsourced technical-compliance services. "
        "Extract all factual claims relevant to deal analysis. "
        "Apply epistemic typing carefully: IC memo / Firm underwriting = attested; "
        "seller CIM = asserted; QoE report conclusions = attested; "
        "computed concentrations = derived."
    )

    all_claims: list[dict] = []
    for doc in docs:
        try:
            items = _extract_one(doc, deal_context)
            all_claims.extend(items)
        except Exception as exc:
            print(f"  ERROR on {doc.name}: {exc}")

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_claims, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nExtracted {len(all_claims)} claims → {out_path}")
    print("Next: .venv/bin/python3 tools/benchmark_runner.py --cic ... --claims-file", out_path)


if __name__ == "__main__":
    main()
