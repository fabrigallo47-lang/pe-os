#!/usr/bin/env python3
"""
extract_v2.py — E3 extraction pipeline for PANTA.

Architecture:
  L1  Document parser    → deterministic chunks with stable locators
  L2  LLM annotator      → one call per chunk, tool_use schema-constrained
  L3  Claim validator    → deterministic normalization + stable_id
  L4  Graph assembler    → deterministic dedup + conflict detection

Claim schema aligned to PANTA_Keystone_Canonical_Investment_Case_v1.1.json
(CAP-003). Does NOT touch extract.py.

Manifest modes prevent temporal leakage between knowledge snapshots:
  K-PRE   CIM, DR, IA, QL, QoE  — state of knowledge before IC memo
  K-IC    K-PRE + IC memo        — as-of IC gate (2026-03-10)
  K-LIVE  K-IC + board packs     — post-close, event-by-event

Usage:
  python3 tools/extract_v2.py --manifest K-IC --deal keystone --dry-run

  export ANTHROPIC_API_KEY=sk-...  # or OPENROUTER_API_KEY with PEOS_LLM_PROVIDER=openrouter
  python3 tools/extract_v2.py --manifest K-PRE --deal keystone \\
      --output pipeline_out/e3/k_pre

  python3 tools/extract_v2.py --source vault/inbox/keystone_ic_memo.md \\
      --deal keystone --output pipeline_out/e3/single

  python3 tools/extract_v2.py --manifest K-IC --deal keystone \\
      --compare pipeline_out/keystone_full_story/graph.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.llm_provider import (  # noqa: E402
    anthropic_client_kwargs,
    configured_api_key,
    configured_model,
    missing_key_message,
    openrouter_extra_body,
)

VAULT_INBOX = ROOT / "vault" / "inbox"
MODEL = configured_model("claude-haiku-4-5-20251001")

# ─────────────────────────────────────────────────────────────────────────────
# Source registry — maps vault/inbox filenames to canonical SRC-xxx IDs.
# Aligned with the sources dict in the benchmark CIC v1.1.
# known_at = when the Firm first received this document.
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_REGISTRY: dict[str, dict] = {
    # filename (without extension or with) → canonical source record
    "keystone_seller_cim": {
        "source_id": "SRC-CIM",
        "name": "Project Keystone CIM",
        "party": "Alderstone management and Hawthorne Capital Markets",
        "doc_type": "CIM",
        "effective_date": "2025-10-27",
        "known_at": "2025-10-27",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone_data_room_extract": {
        "source_id": "SRC-DR",
        "name": "Keystone data room extract",
        "party": "Alderstone management / VDR export",
        "doc_type": "Data Room",
        "effective_date": "2025-11-15",
        "known_at": "2025-11-15",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone_firm_initial_assessment": {
        "source_id": "SRC-IA",
        "name": "Firm initial assessment",
        "party": "The Firm investment team",
        "doc_type": "Internal",
        "effective_date": "2025-12-01",
        "known_at": "2025-12-01",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone_question_list": {
        "source_id": "SRC-QL",
        "name": "Keystone question list",
        "party": "The Firm diligence team",
        "doc_type": "Internal",
        "effective_date": "2026-01-10",
        "known_at": "2026-01-10",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone_qoe_report": {
        "source_id": "SRC-QOE",
        "name": "Quality of Earnings report",
        "party": "Independent financial diligence provider",
        "doc_type": "QoE Report",
        "effective_date": "2026-02-20",
        "known_at": "2026-02-20",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone_firm_model_summary": {
        "source_id": "SRC-MODEL-SUM",
        "name": "Firm model summary",
        "party": "The Firm investment team",
        "doc_type": "LBO Model",
        "effective_date": "2026-03-05",
        "known_at": "2026-03-05",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone-model-part1": {
        "source_id": "SRC-MODEL",
        "name": "Keystone LBO model (part 1)",
        "party": "The Firm investment team",
        "doc_type": "LBO Model",
        "effective_date": "2026-03-05",
        "known_at": "2026-03-05",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone-model-part2": {
        "source_id": "SRC-MODEL",
        "name": "Keystone LBO model (part 2)",
        "party": "The Firm investment team",
        "doc_type": "LBO Model",
        "effective_date": "2026-03-05",
        "known_at": "2026-03-05",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone-model-part3": {
        "source_id": "SRC-MODEL",
        "name": "Keystone LBO model (part 3)",
        "party": "The Firm investment team",
        "doc_type": "LBO Model",
        "effective_date": "2026-03-05",
        "known_at": "2026-03-05",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone-model-part4": {
        "source_id": "SRC-MODEL",
        "name": "Keystone LBO model (part 4)",
        "party": "The Firm investment team",
        "doc_type": "LBO Model",
        "effective_date": "2026-03-05",
        "known_at": "2026-03-05",
        "manifest": ["K-PRE", "K-IC", "K-LIVE"],
    },
    "keystone_ic_memo": {
        "source_id": "SRC-IC",
        "name": "IC memo 2026-03-10",
        "party": "The Firm investment team / Investment Committee",
        "doc_type": "IC Memo",
        "effective_date": "2026-03-10",
        "known_at": "2026-03-10",
        "manifest": ["K-IC", "K-LIVE"],  # not in K-PRE
    },
    "keystone_monitoring_boardpack1_dec2026": {
        "source_id": "SRC-BP1",
        "name": "Board pack Dec 2026",
        "party": "Alderstone management / board package",
        "doc_type": "Board Pack",
        "effective_date": "2026-12-31",
        "known_at": "2026-12-31",
        "manifest": ["K-LIVE"],
    },
    "keystone_monitoring_boardpack2_mar2027": {
        "source_id": "SRC-BP2",
        "name": "Board pack Mar 2027",
        "party": "Alderstone management / board package",
        "doc_type": "Board Pack",
        "effective_date": "2027-03-31",
        "known_at": "2027-03-31",
        "manifest": ["K-LIVE"],
    },
    "keystone_monitoring_junecompliance2027": {
        "source_id": "SRC-JUN27",
        "name": "June 2027 compliance certificate",
        "party": "Alderstone management / board package",
        "doc_type": "Board Pack",
        "effective_date": "2027-06-30",
        "known_at": "2027-06-30",
        "manifest": ["K-LIVE"],
    },
    "keystone_monitoring_augustamendment2027": {
        "source_id": "SRC-AUG27",
        "name": "August 2027 amendment",
        "party": "Alderstone management / board package",
        "doc_type": "Amendment",
        "effective_date": "2027-08-15",
        "known_at": "2027-08-15",
        "manifest": ["K-LIVE"],
    },
    "keystone_monitoring_recovery_exit2031": {
        "source_id": "SRC-EXIT31",
        "name": "Exit 2031 package",
        "party": "Alderstone management / board package",
        "doc_type": "Board Pack",
        "effective_date": "2031-06-01",
        "known_at": "2031-06-01",
        "manifest": ["K-LIVE"],
    },
}

# Sources per manifest — derived from registry
MANIFEST_SOURCES: dict[str, list[str]] = {
    "K-PRE": [k for k, v in SOURCE_REGISTRY.items() if "K-PRE" in v["manifest"]],
    "K-IC": [k for k, v in SOURCE_REGISTRY.items() if "K-IC" in v["manifest"]],
    "K-LIVE": [k for k, v in SOURCE_REGISTRY.items() if "K-LIVE" in v["manifest"]],
    "ALL": list(SOURCE_REGISTRY.keys()),
}

def _source_record(path: Path) -> dict:
    """Return the source registry record for this file, or a synthetic fallback."""
    stem = path.stem
    # Try exact match first, then strip suffixes like _part1, _extract
    record = SOURCE_REGISTRY.get(stem)
    if not record:
        for key in SOURCE_REGISTRY:
            if stem.startswith(key) or key.startswith(stem):
                record = SOURCE_REGISTRY[key]
                break
    if not record:
        record = {
            "source_id": f"SRC-{stem.upper()[:12]}",
            "name": stem,
            "party": "unknown",
            "doc_type": "Other",
            "effective_date": "",
            "known_at": "",
            "manifest": ["ALL"],
        }
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Schema definitions (bounded enums)
# ─────────────────────────────────────────────────────────────────────────────

METRIC_ENUM: list[str] = [
    "Revenue", "Recurring Revenue", "Revenue Growth",
    "Gross Profit", "Gross Margin",
    "EBITDA", "EBITDA Margin", "EBITDA Add-back", "EBITDA Adjustment",
    "EBIT", "Net Income", "Free Cash Flow", "Operating Cash Flow",
    "Capex", "Working Capital", "DSO", "DPO", "Inventory Days",
    "Earnings Quality Risk", "Revenue Quality", "Adjustment Supportability",
    "Customer Concentration", "Customer Count", "Active Billing Accounts",
    "Customer Retention", "Contract Terms", "Market Position", "Market Size",
    "Enterprise Value", "Equity Value", "Entry Multiple", "Exit Multiple", "Exit EV",
    "Net Debt", "Gross Debt", "Leverage", "Interest Coverage",
    "Sponsor Equity", "Seller Rollover", "First-Lien Debt",
    "Revolver Capacity", "DDTL Availability", "Covenant EBITDA",
    "Covenant Threshold", "Covenant Headroom",
    "MOIC", "IRR", "Exit Horizon", "Supported Price",
    "Net Working Capital", "Net Working Capital Target", "Net Working Capital Adjustment",
    "Headcount", "Team Tenure", "Acquisition Count",
    "Systems Integration Risk", "Integration Risk", "Operational Risk",
    "Key Person Risk", "Regulatory Risk", "Competition Risk",
    "IC Conditions", "IC Vote", "Decision Coherence",
    "Customer Contract Terms",
]
_seen: set[str] = set()
METRIC_ENUM = [m for m in METRIC_ENUM if not (m in _seen or _seen.add(m))]  # type: ignore

UNIT_ENUM: list[str | None] = [
    None, "", "$m", "£m", "€m", "$m/year", "$m/quarter",
    "%", "x", "bps", "days", "headcount", "turns", "$", "£", "€",
]

PERIOD_MAP: dict[str, str] = {
    "FY2025A": "2025-12-31", "FY2025": "2025-12-31",
    "FY2026E": "2026-12-31", "FY2026": "2026-12-31",
    "FY2027E": "2027-12-31", "FY2027": "2027-12-31",
    "FY2028E": "2028-12-31", "FY2028": "2028-12-31",
    "FY2029E": "2029-12-31", "FY2029": "2029-12-31",
    "FY2030E": "2030-12-31", "FY2030": "2030-12-31",
    "FY2031E": "2031-12-31", "FY2031": "2031-12-31",
    "OPENING": "2026-03-31",
    "LTM": "LTM",
    "Q1 2026": "2026-06-30", "Q2 2026": "2026-09-30",
    "Q3 2026": "2026-12-31", "Q4 2026": "2027-03-31",
    "Q1 2027": "2027-06-30", "Q2 2027": "2027-09-30",
}
# Period is now free-text — no enum constraint.
# PERIOD_MAP is kept for period_iso normalization only (not for constraining the field).

EPISTEMIC_CLASS_ENUM = ["asserted", "observed", "derived", "attested"]
DIRECTION_ENUM = ["supports", "contradicts", "context"]
TOPIC_ENUM = [
    "Financial Performance", "Earnings Quality", "Customer Risk",
    "Team & Management", "Market Position", "Capital Structure",
    "Valuation & Returns", "Operational", "Legal & Compliance", "Other",
]

# Known definition IDs — if LLM flags a claim as definition-linked, map to DEF-xxx.
# These align with the definitions[] array in the canonical benchmark.
DEFINITION_ENUM: list[str | None] = [
    None,
    "DEF-FIRM-EBITDA", "DEF-QOE-EBITDA", "DEF-COV-EBITDA",
    "DEF-SELLER-EBITDA", "DEF-NWC", "DEF-NWC-TARGET",
    "DEF-RECURRING-REVENUE", "DEF-CONCENTRATION",
    "DEF-MOIC", "DEF-IRR", "DEF-EV",
]

# ─────────────────────────────────────────────────────────────────────────────
# Tool schema (tool_use — enforced at LLM decoding level)
# ─────────────────────────────────────────────────────────────────────────────

CLAIM_TOOL = {
    "name": "emit_claims",
    "description": (
        "Emit 0-4 financial claims from this document fragment. "
        "Extract only what is explicitly stated. Empty list if no financial claims. "
        "epistemic_class: asserted=seller/mgmt claim, observed=third-party real-time, "
        "attested=formally certified (QoE conclusion, IC decision), derived=YOU computed it."
    ),
    "input_schema": {
        "type": "object",
        "required": ["claims"],
        "properties": {
            "claims": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "required": [
                        "metric", "value", "unit", "period", "perimeter",
                        "epistemic_class", "direction", "topic",
                        "statement", "locator_hint",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": METRIC_ENUM,
                        },
                        "value": {
                            "type": ["number", "string", "null"],
                        },
                        "unit": {
                            "type": ["string", "null"],
                            "enum": UNIT_ENUM,
                        },
                        "period": {
                            "type": ["string", "null"],
                            "description": (
                                "The time period or vintage this claim refers to, in the document's own language. "
                                "Use the richest description available. Examples: "
                                "'FY2025A', 'FY2025A / FY2025E seller presentation', 'As of 2025-10-27', "
                                "'LTM Sep-25', '2020 to 2025-10-27', 'FY2026E–FY2030E forecast'. "
                                "Null only if the claim is genuinely timeless."
                            ),
                        },
                        "perimeter": {
                            "type": ["string", "null"],
                            "description": (
                                "The precise economic scope — entity + metric definition + any adjustments. "
                                "Write the full descriptive string, not a shorthand. Examples: "
                                "'Alderstone consolidated revenue', "
                                "'Alderstone consolidated EBITDA under seller adjustment perimeter', "
                                "'Alderstone consolidated EBITDA under independent QoE adjustment perimeter', "
                                "'Alderstone consolidated EBITDA under Firm valuation, leverage and returns perimeter', "
                                "'Alderstone customer revenue measured by individual billing account', "
                                "'Alderstone accounts-receivable ledger'. "
                                "Null only if scope is truly unspecified."
                            ),
                        },
                        "epistemic_class": {
                            "type": "string",
                            "enum": EPISTEMIC_CLASS_ENUM,
                            "description": (
                                "asserted=seller/management; observed=third-party real-time; "
                                "attested=QoE conclusion or IC decision; derived=computed by you"
                            ),
                        },
                        "direction": {
                            "type": "string",
                            "enum": DIRECTION_ENUM,
                            "description": "supports=positive thesis signal; contradicts=negative signal; context=neutral",
                        },
                        "topic": {
                            "type": "string",
                            "enum": TOPIC_ENUM,
                        },
                        "definition_id": {
                            "type": ["string", "null"],
                            "enum": DEFINITION_ENUM,
                            "description": "If claim uses a specific defined term, reference its DEF-xxx ID.",
                        },
                        "statement": {
                            "type": "string",
                            "maxLength": 280,
                            "description": "One complete sentence stating the claim with full numeric and contextual detail.",
                        },
                        "locator_hint": {
                            "type": "string",
                            "maxLength": 120,
                            "description": "Section heading, table name, slide, or line reference where this appears.",
                        },
                        "derivation": {
                            "type": ["string", "null"],
                            "description": "Required when epistemic_class=derived. State the computation.",
                        },
                        "author": {
                            "type": ["string", "null"],
                            "description": "Party making the claim (e.g. management, QoE provider, IC).",
                        },
                    },
                },
            }
        },
    },
}

SYSTEM_PROMPT = textwrap.dedent("""
    You are a financial claim extractor for a private equity firm (PANTA system).
    Extract only claims explicitly stated in the fragment. Never infer or interpolate.
    Return an empty list when the fragment contains no financial claims.

    EPISTEMIC CLASS — apply strictly by document source and claim type:
    - attested: ANY claim from the IC memo, QoE report conclusion, firm underwriting, or
      formal buyer analysis. This includes the firm's EBITDA view, QoE findings,
      covenant analysis, and any value the buyer's team formally concluded.
      When in doubt for IC memo or QoE document fragments → use attested.
    - asserted: seller or management stated claims with no third-party verification.
      CIM numbers, management presentations, seller-deck projections → asserted.
    - observed: a third-party measured or witnessed something directly in real time
      (e.g. QoE workpaper data room observation, call transcript quote, site visit).
    - derived: YOU computed this claim from two or more stated values — requires derivation field.
      Only use when you performed arithmetic (ratio, sum, subtraction).

    Source → class mapping (use this every time):
      IC memo         → attested  (the firm's own formal conclusion)
      QoE report      → attested  (third-party certifies)
      Initial assessment → attested  (firm's own preliminary underwriting)
      Data room docs  → observed  (raw third-party data)
      Seller CIM / IM → asserted  (seller's marketing claims)
      Management presentation → asserted
      Computed by you → derived

    Identity rule — write the FULL perimeter and FULL period, not a shorthand:
    - period: use the document's own language including context, e.g.
        'FY2025A / FY2025E seller presentation'  not just 'FY2025A'
        'As of 2025-10-27'  not just '2025-10-27'
        'FY2026E–FY2030E forecast'  not just 'FY2026E'
    - perimeter: write the complete scope string, e.g.
        'Alderstone consolidated EBITDA under seller adjustment perimeter'
        'Alderstone consolidated EBITDA under independent QoE adjustment perimeter'
        'Alderstone customer revenue measured by individual billing account'
      NOT just 'Alderstone consolidated' or 'Alderstone standalone'.

    Do not collapse different definitions:
    - Firm EBITDA ≠ QoE EBITDA ≠ Covenant EBITDA ≠ Seller EBITDA
    - account-level concentration ≠ parent-level concentration
    - FY2025A ≠ LTM ≠ FY2026E

    No source statement may be invented. If the fragment is ambiguous, omit the claim.
""").strip()


# ─────────────────────────────────────────────────────────────────────────────
# L1 — Document parser (deterministic)
# ─────────────────────────────────────────────────────────────────────────────

CHUNK_WORDS = 250


@dataclass
class Chunk:
    chunk_id: str
    locator: str
    body: str
    source_path: str
    source_type: str
    source_record: dict
    word_count: int


def _chunk_hash(body: str) -> str:
    return "ch-" + hashlib.sha256(body.encode()).hexdigest()[:12]


def _split_words(text: str, max_words: int, locator_prefix: str,
                 source_path: str, source_type: str, source_record: dict) -> list[Chunk]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_words):
        body = " ".join(words[i: i + max_words])
        locator = f"{locator_prefix}:w{i}-{i + len(body.split())}"
        chunks.append(Chunk(
            chunk_id=_chunk_hash(body),
            locator=locator,
            body=body,
            source_path=source_path,
            source_type=source_type,
            source_record=source_record,
            word_count=len(body.split()),
        ))
    return chunks


def parse_markdown(path: Path, max_words: int = CHUNK_WORDS) -> list[Chunk]:
    src = _source_record(path)
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?=^#{2,3} )", text, flags=re.MULTILINE)
    chunks: list[Chunk] = []
    for part in parts:
        if not part.strip():
            continue
        header_match = re.match(r"^(#{2,3} .+)", part)
        section_label = header_match.group(1)[:50].strip() if header_match else "section"
        words = part.split()
        if len(words) <= max_words:
            body = part.strip()
            chunks.append(Chunk(
                chunk_id=_chunk_hash(body),
                locator=f"{path.name}::{section_label}",
                body=body,
                source_path=str(path),
                source_type="markdown",
                source_record=src,
                word_count=len(words),
            ))
        else:
            sub = _split_words(part, max_words, f"{path.name}::{section_label}",
                               str(path), "markdown", src)
            chunks.extend(sub)
    return chunks


def parse_pdf(path: Path, max_words: int = CHUNK_WORDS) -> list[Chunk]:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber required: pip install pdfplumber")
    src = _source_record(path)
    chunks: list[Chunk] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            words = text.split()
            if len(words) <= max_words:
                body = text.strip()
                chunks.append(Chunk(
                    chunk_id=_chunk_hash(body),
                    locator=f"p{page_num}",
                    body=body,
                    source_path=str(path),
                    source_type="pdf",
                    source_record=src,
                    word_count=len(words),
                ))
            else:
                sub = _split_words(text, max_words, f"p{page_num}",
                                   str(path), "pdf", src)
                chunks.extend(sub)
    return chunks


def parse_xlsx(path: Path, max_words: int = CHUNK_WORDS) -> list[Chunk]:
    """Create reproducible, cell-addressable chunks from an Excel workbook.

    A workbook is not prose: formulas and their cached outputs carry different
    meanings.  The chunk body keeps both, while the locator names the exact
    sheet and cell range so a reviewer can verify any extracted claim.
    """
    try:
        import openpyxl
    except ImportError:
        sys.exit("openpyxl required for Excel extraction: .venv/bin/pip install openpyxl")
    try:
        formulas = openpyxl.load_workbook(path, data_only=False, read_only=True)
        values = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        sys.exit(f"Cannot read workbook {path.name}: {exc}")
    src = _source_record(path)
    chunks: list[Chunk] = []
    for sheet_name in formulas.sheetnames:
        ws, value_ws = formulas[sheet_name], values[sheet_name]
        pending: list[str] = []
        start_row = end_row = None
        def flush() -> None:
            nonlocal pending, start_row, end_row
            if not pending or start_row is None or end_row is None:
                return
            body = f"Workbook: {path.name}\nSheet: {sheet_name}\n" + "\n".join(pending)
            chunks.append(Chunk(
                chunk_id=_chunk_hash(body),
                locator=f"{path.name}::{sheet_name}!{start_row}:{end_row}",
                body=body, source_path=str(path), source_type="xlsx",
                source_record=src, word_count=len(body.split()),
            ))
            pending, start_row, end_row = [], None, None
        for row_number, (row, cached_row) in enumerate(zip(ws.iter_rows(), value_ws.iter_rows()), start=1):
            cells: list[str] = []
            for cell, cached_cell in zip(row, cached_row):
                raw = cell.value
                if raw is None:
                    continue
                if isinstance(raw, str) and raw.startswith("="):
                    cells.append(f"{cell.coordinate}=FORMULA({raw}); cached={cached_cell.value!r}")
                else:
                    cells.append(f"{cell.coordinate}={raw}")
            if not cells:
                continue
            line = " | ".join(cells)
            projected = len((" ".join(pending + [line])).split())
            if pending and projected > max_words:
                flush()
            if start_row is None:
                start_row = row_number
            end_row = row_number
            pending.append(line)
        flush()
    return chunks


def parse_source(path: Path, max_words: int = CHUNK_WORDS) -> list[Chunk]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path, max_words)
    elif suffix in (".md", ".txt", ".html"):
        return parse_markdown(path, max_words)
    elif suffix in (".xlsx", ".xlsm"):
        return parse_xlsx(path, max_words)
    else:
        sys.exit(f"Unsupported source type: {suffix}. Use .pdf, .md, .txt, .xlsx, or .xlsm")


def load_manifest(manifest: str, deal: str) -> list[Path]:
    """Return ordered list of source files for the given manifest."""
    keys = MANIFEST_SOURCES.get(manifest, [])
    paths = []
    for key in keys:
        # Try stem match in vault/inbox
        for ext in (".md", ".txt", ".pdf", ".xlsx", ".xlsm"):
            candidate = VAULT_INBOX / f"{key}{ext}"
            if candidate.exists():
                paths.append(candidate)
                break
    return paths


# ─────────────────────────────────────────────────────────────────────────────
# L2 — LLM annotator (schema-constrained via tool_use)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RawClaim:
    metric: str
    value: Any
    unit: str | None
    period: str | None
    perimeter: str | None
    epistemic_class: str
    direction: str
    topic: str
    definition_id: str | None
    statement: str
    locator: str
    source_id: str
    source_path: str
    known_at: str
    derivation: str | None = None
    author: str | None = None


def annotate_chunk(chunk: Chunk, client, deal: str,
                   rate_limit_delay: float = 0.25) -> list[RawClaim]:
    src = chunk.source_record
    prompt = (
        f"DEAL: {deal}\n"
        f"SOURCE: {src['source_id']} ({src['name']}) — {src['doc_type']}\n"
        f"KNOWN AT: {src['known_at']}\n"
        f"FRAGMENT LOCATOR: {chunk.locator}\n\n"
        f"{chunk.body}"
    )
    try:
        request = {
            "model": MODEL,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "tools": [CLAIM_TOOL],
            "tool_choice": {"type": "tool", "name": "emit_claims"},
            "messages": [{"role": "user", "content": prompt}],
        }
        extra_body = openrouter_extra_body()
        if extra_body:
            request["extra_body"] = extra_body
        resp = client.messages.create(**request)
        time.sleep(rate_limit_delay)
    except Exception as e:
        print(f"  [L2 ERROR] {chunk.chunk_id}: {e}", file=sys.stderr)
        return []

    raw_claims: list[RawClaim] = []
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_claims":
            for c in block.input.get("claims", []):
                hint = (c.get("locator_hint") or "").strip()
                # The model sometimes echoes the fragment locator it was given
                # instead of naming a position inside it, which produced
                # "file.md::## Heading:file.md::## Heading". Only append a hint
                # that adds something.
                if hint and hint not in chunk.locator and chunk.locator not in hint:
                    locator = f"{chunk.locator}:{hint}"
                else:
                    locator = chunk.locator
                raw_claims.append(RawClaim(
                    metric=c["metric"],
                    value=c.get("value"),
                    unit=c.get("unit"),
                    period=c.get("period"),
                    perimeter=c.get("perimeter"),
                    epistemic_class=c.get("epistemic_class", "asserted"),
                    direction=c.get("direction", "context"),
                    topic=c.get("topic", "Other"),
                    definition_id=c.get("definition_id"),
                    statement=c.get("statement", ""),
                    locator=locator,
                    source_id=src["source_id"],
                    source_path=chunk.source_path,
                    known_at=src["known_at"],
                    derivation=c.get("derivation"),
                    author=c.get("author"),
                ))
    return raw_claims


# ─────────────────────────────────────────────────────────────────────────────
# L3 — Validator / normalizer (deterministic)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _normalize_period(raw: str | None) -> str:
    if not raw:
        return "unknown"
    if raw.upper().strip() in PERIOD_MAP:
        return PERIOD_MAP[raw.upper().strip()]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    return f"RAW:{raw}"


def _stable_id(metric: str, value: Any, period_iso: str, perimeter: str) -> str:
    key = f"{metric}|{value}|{period_iso}|{perimeter}"
    return "ks-" + hashlib.sha256(key.encode()).hexdigest()[:12]


@dataclass
class CanonicalClaim:
    # --- CAP-003 required fields (aligned to benchmark v1.1) ---
    claim_id: str           # ks-sha256 stable content-addressed ID
    statement: str
    source_id: str          # SRC-CIM, SRC-QOE, etc.
    locator: str
    epistemic_class: str    # asserted / observed / derived / attested
    value: float | None
    value_raw: Any
    unit: str | None
    definition_id: str | None
    period: str             # raw period label from source
    period_iso: str         # normalized ISO date or "LTM"
    perimeter: str
    ground_truth_flag: bool  # True only for benchmark validation claims
    validation_only: bool    # True only for quarantined benchmark claims
    notes: str | None
    # --- compiler metadata (NOT in frozen CIC schema) ---
    metric: str             # from METRIC_ENUM — for dedup and reporting
    source_path: str
    known_at: str
    direction: str
    topic: str
    derivation: str | None
    author: str | None
    validation_errors: list[str] = field(default_factory=list)


def validate(raw: RawClaim) -> CanonicalClaim:
    errors: list[str] = []
    if raw.metric not in METRIC_ENUM:
        errors.append(f"unknown metric: '{raw.metric}'")
    value = _parse_float(raw.value)
    period_iso = _normalize_period(raw.period)
    # RAW: prefix means period didn't match PERIOD_MAP — store as-is, no longer reject.
    # period_iso carries the raw label for non-standard periods.
    perimeter = raw.perimeter or "unknown"
    ec = raw.epistemic_class if raw.epistemic_class in EPISTEMIC_CLASS_ENUM else "asserted"
    if raw.epistemic_class not in EPISTEMIC_CLASS_ENUM:
        errors.append(f"invalid epistemic_class: '{raw.epistemic_class}'")
    if ec == "derived" and not raw.derivation:
        errors.append("derived claim missing derivation field")
    claim_id = _stable_id(raw.metric, value, period_iso, perimeter)
    return CanonicalClaim(
        claim_id=claim_id,
        statement=raw.statement,
        source_id=raw.source_id,
        locator=raw.locator,
        epistemic_class=ec,
        value=value,
        value_raw=raw.value,
        unit=raw.unit,
        definition_id=raw.definition_id,
        period=raw.period or "",
        period_iso=period_iso,
        perimeter=perimeter,
        ground_truth_flag=False,
        validation_only=False,
        notes=None,
        metric=raw.metric,
        source_path=raw.source_path,
        known_at=raw.known_at,
        direction=raw.direction,
        topic=raw.topic,
        derivation=raw.derivation,
        author=raw.author,
        validation_errors=errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# L4 — Graph assembler (deterministic)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SubGraph:
    claims: list[CanonicalClaim]
    conflicts: list[dict]
    rejected: list[dict]
    admitted_count: int
    rejected_count: int
    conflict_count: int


def assemble(claims: list[CanonicalClaim]) -> SubGraph:
    admitted: dict[str, CanonicalClaim] = {}
    conflicts: list[dict] = []
    rejected: list[dict] = []
    for c in claims:
        if c.validation_errors:
            rejected.append({
                "claim_id": c.claim_id,
                "metric": c.metric,
                "errors": c.validation_errors,
                "statement": c.statement[:80],
            })
            continue
        sid = c.claim_id
        if sid in admitted:
            existing = admitted[sid]
            if existing.value != c.value:
                conflicts.append({
                    "claim_id": sid,
                    "metric": c.metric,
                    "source_a": existing.source_id,
                    "value_a": existing.value,
                    "source_b": c.source_id,
                    "value_b": c.value,
                    "note": "Same stable_id, different values — check perimeter or period.",
                })
        else:
            admitted[sid] = c
    return SubGraph(
        claims=list(admitted.values()),
        conflicts=conflicts,
        rejected=rejected,
        admitted_count=len(admitted),
        rejected_count=len(rejected),
        conflict_count=len(conflicts),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output — E3 manifest format + graph.json for comparison
# ─────────────────────────────────────────────────────────────────────────────

def _to_e3_manifest(graph: SubGraph, deal: str, manifest: str,
                    sources_used: list[dict]) -> dict:
    """
    Produce an E3 extraction manifest.
    Claims are in CAP-003 format: only the frozen fields, no compiler metadata.
    Compiler metadata lives in the adjacent extraction_metadata section.
    """
    claims_output = []
    for c in graph.claims:
        claims_output.append({
            "claim_id": c.claim_id,
            "statement": c.statement,
            "source_id": c.source_id,
            "locator": c.locator,
            "epistemic_class": c.epistemic_class,
            "value": str(c.value) if c.value is not None else c.value_raw,
            "unit": c.unit,
            "definition_id": c.definition_id,
            "period": c.period,
            "perimeter": c.perimeter,
            "ground_truth_flag": c.ground_truth_flag,
            "validation_only": c.validation_only,
            "notes": c.notes,
        })
    return {
        "schema_version": "e3-1.0",
        "manifest_id": manifest,
        "deal": deal,
        "extractor": "extract_v2",
        "sources_included": [s["source_id"] for s in sources_used],
        "claims": claims_output,
        "conflicts": graph.conflicts,
        "extraction_metadata": {
            "admitted_count": graph.admitted_count,
            "rejected_count": graph.rejected_count,
            "conflict_count": graph.conflict_count,
            "rejected": graph.rejected,
            "compiler_fields_per_claim": [
                {
                    "claim_id": c.claim_id,
                    "metric": c.metric,
                    "known_at": c.known_at,
                    "direction": c.direction,
                    "topic": c.topic,
                    "derivation": c.derivation,
                    "author": c.author,
                }
                for c in graph.claims
            ],
        },
    }


def _compare_graphs(new_claims: list[dict], old_path: Path) -> dict:
    with open(old_path) as f:
        old_graph = json.load(f)
    old_nodes = {n["id"]: n for n in old_graph.get("nodes", [])
                 if n.get("type") == "claim"}
    new_by_metric_period = {}
    for c in new_claims:
        key = (c.get("metric", c.get("claim_id", "")), c.get("period", ""), c.get("perimeter", ""))
        new_by_metric_period[key] = c
    old_by_key = {}
    for n in old_nodes.values():
        key = (n.get("metric", ""), n.get("as_of", ""), n.get("perimeter", ""))
        old_by_key[key] = n
    only_new = [c for k, c in new_by_metric_period.items() if k not in old_by_key]
    only_old = [n for k, n in old_by_key.items() if k not in new_by_metric_period]
    changes = []
    for k in new_by_metric_period:
        if k in old_by_key:
            nv = str(new_by_metric_period[k].get("value", ""))
            ov = str(old_by_key[k].get("value", ""))
            if nv != ov:
                changes.append({"metric": k[0], "period": k[1],
                                 "old_value": ov, "new_value": nv})
    return {
        "new_total": len(new_claims),
        "old_total": len(old_nodes),
        "only_in_new": len(only_new),
        "only_in_old": len(only_old),
        "value_changes": len(changes),
        "samples_only_new": [
            {"metric": c.get("metric", c.get("claim_id", "")),
             "value": c.get("value"), "statement": c.get("statement", "")[:80]}
            for c in only_new[:5]
        ],
        "samples_only_old": [
            {"metric": n.get("metric", ""), "value": n.get("value"),
             "statement": n.get("statement", "")[:80]}
            for n in only_old[:5]
        ],
        "value_change_samples": changes[:5],
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _w(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    size = path.stat().st_size
    sha = _sha256_file(path)
    print(f"  {path.name:<45} {size//1024:4d}KB  sha256:{sha[:16]}...")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="extract_v2 / E3 pipeline")
    src_group = ap.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--manifest", choices=["K-PRE", "K-IC", "K-LIVE", "ALL"],
                           help="Run over all sources in manifest (no temporal leakage)")
    src_group.add_argument("--source", help="Single source file (.pdf, .md, .txt, .xlsx, .xlsm)")
    ap.add_argument("--deal", required=True, help="Deal slug (e.g. keystone)")
    ap.add_argument("--output", default="pipeline_out/e3",
                    help="Output directory (default: pipeline_out/e3)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show chunks without calling LLM")
    ap.add_argument("--compare", default=None,
                    help="Path to existing graph.json to compare against")
    ap.add_argument("--workers", type=int, default=3,
                    help="Parallel LLM workers (default: 3)")
    ap.add_argument("--chunk-words", type=int, default=CHUNK_WORDS,
                    help=f"Words per chunk (default: {CHUNK_WORDS})")
    args = ap.parse_args()

    # ── Collect source paths ──────────────────────────────────────────────
    if args.manifest:
        source_paths = load_manifest(args.manifest, args.deal)
        manifest_label = args.manifest
        if not source_paths:
            print(f"ERROR: No sources found for manifest {args.manifest} in {VAULT_INBOX}",
                  file=sys.stderr)
            print(f"  Expected stems: {MANIFEST_SOURCES[args.manifest]}")
            return 1
        print(f"\n[Manifest {args.manifest}] {len(source_paths)} sources:")
        for p in source_paths:
            rec = _source_record(p)
            print(f"  {rec['source_id']:<16} {p.name}  (known_at: {rec['known_at']})")
    else:
        source_path = Path(args.source)
        if not source_path.exists():
            source_path = ROOT / args.source
        if not source_path.exists():
            print(f"ERROR: source not found: {args.source}", file=sys.stderr)
            return 1
        source_paths = [source_path]
        manifest_label = "SINGLE"

    out_dir = ROOT / args.output / manifest_label
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── L1: Parse all sources ─────────────────────────────────────────────
    print(f"\n[L1] Parsing {len(source_paths)} source(s)...")
    all_chunks: list[Chunk] = []
    for sp in source_paths:
        chunks = parse_source(sp, args.chunk_words)
        print(f"  {sp.name:<50} {len(chunks):3d} chunks")
        all_chunks.extend(chunks)
    print(f"  Total: {len(all_chunks)} chunks  "
          f"(avg {sum(c.word_count for c in all_chunks)//max(len(all_chunks),1)} w/chunk)")

    chunks_debug = [
        {"chunk_id": c.chunk_id, "locator": c.locator,
         "source_id": c.source_record["source_id"],
         "word_count": c.word_count, "preview": c.body[:100].replace("\n", " ") + "..."}
        for c in all_chunks
    ]
    _w(out_dir / "chunks_debug.json", chunks_debug)

    if args.dry_run:
        print(f"\n[DRY-RUN] Chunks written to {out_dir}/chunks_debug.json")
        _print_chunk_summary(all_chunks)
        return 0

    # ── L2: Annotate ──────────────────────────────────────────────────────
    api_key = configured_api_key()
    if not api_key:
        print(f"ERROR: {missing_key_message()}.", file=sys.stderr)
        print("  Or use --dry-run to inspect chunks.")
        return 1
    try:
        import anthropic
        client = anthropic.Anthropic(**anthropic_client_kwargs(api_key))
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 1

    # Raw claims cache: if a previous run completed L2, reuse without re-calling the API.
    raw_cache_path = out_dir / "raw_claims_cache.json"
    if raw_cache_path.exists():
        print(f"\n[L2] Cache found — loading raw claims from {raw_cache_path.name} (skipping API calls)")
        cached = json.loads(raw_cache_path.read_text())
        all_raw = [RawClaim(**c) for c in cached]
        print(f"  Loaded {len(all_raw)} raw claims from cache")
    else:
        print(f"\n[L2] Annotating {len(all_chunks)} chunks "
              f"(workers={args.workers}, model={MODEL})...")
        all_raw = []
        processed = 0

        def _process(chunk: Chunk) -> tuple[Chunk, list[RawClaim]]:
            return chunk, annotate_chunk(chunk, client, args.deal)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_process, c): c for c in all_chunks}
            for fut in as_completed(futures):
                chunk, raw_claims = fut.result()
                all_raw.extend(raw_claims)
                processed += 1
                if raw_claims:
                    print(f"  [{processed:03d}/{len(all_chunks):03d}] "
                          f"{chunk.locator[:55]:<55} → {len(raw_claims)} claim(s)")

        # Persist raw claims immediately so L3/L4 failures don't require re-running the API
        from dataclasses import asdict
        raw_cache_path.write_text(
            json.dumps([asdict(r) for r in all_raw], indent=2, default=str),
            encoding="utf-8"
        )
        print(f"  Raw claims cached → {raw_cache_path.name}")

    print(f"  Total raw: {len(all_raw)}")

    # ── L3: Validate ──────────────────────────────────────────────────────
    print("\n[L3] Validating...")
    canonicals = [validate(r) for r in all_raw]
    invalid = [c for c in canonicals if c.validation_errors]
    if invalid:
        print(f"  Rejected: {len(invalid)}")
        for c in invalid[:5]:
            print(f"    x {c.metric}: {c.validation_errors}")

    # ── L4: Assemble ──────────────────────────────────────────────────────
    print("\n[L4] Assembling...")
    graph = assemble(canonicals)
    print(f"  Admitted: {graph.admitted_count}  "
          f"Rejected: {graph.rejected_count}  "
          f"Conflicts: {graph.conflict_count}")
    if graph.conflicts:
        for conf in graph.conflicts:
            print(f"    conflict: {conf['metric']} {conf['value_a']} vs {conf['value_b']}")

    # ── Output ────────────────────────────────────────────────────────────
    print(f"\n[Output] Writing to {out_dir}/...")
    sources_used = [_source_record(p) for p in source_paths]
    e3 = _to_e3_manifest(graph, args.deal, manifest_label, sources_used)
    _w(out_dir / "e3_claims.json", e3)
    _w(out_dir / "rejected_claims.json", graph.rejected)
    _w(out_dir / "conflict_report.json", graph.conflicts)

    # Metric distribution
    metric_counts: dict[str, int] = {}
    for c in graph.claims:
        metric_counts[c.metric] = metric_counts.get(c.metric, 0) + 1

    report_lines = [
        f"E3 Extraction Report — {manifest_label}",
        "=" * 50,
        f"  Deal        : {args.deal}",
        f"  Manifest    : {manifest_label}",
        f"  Sources     : {len(source_paths)}",
        f"  Chunks      : {len(all_chunks)}",
        f"  Raw claims  : {len(all_raw)}",
        f"  Admitted    : {graph.admitted_count}",
        f"  Rejected    : {graph.rejected_count}",
        f"  Conflicts   : {graph.conflict_count}",
        "",
        "Admitted by metric:",
    ]
    for metric, count in sorted(metric_counts.items(), key=lambda x: -x[1]):
        report_lines.append(f"  {count:3d}  {metric}")
    if graph.conflicts:
        report_lines += ["", "Conflicts:"]
        for conf in graph.conflicts:
            report_lines.append(
                f"  {conf['metric']}: {conf['value_a']} ({conf['source_a']}) "
                f"vs {conf['value_b']} ({conf['source_b']})"
            )
    report_text = "\n".join(report_lines) + "\n"
    (out_dir / "extraction_report.txt").write_text(report_text, encoding="utf-8")

    # Hash manifest for version pinning
    e3_path = out_dir / "e3_claims.json"
    manifest_record = {
        "manifest_id": manifest_label,
        "deal": args.deal,
        "sources": [s["source_id"] for s in sources_used],
        "admitted_count": graph.admitted_count,
        "e3_claims_sha256": _sha256_file(e3_path),
    }
    _w(out_dir / "manifest_hash.json", manifest_record)

    print()
    print(report_text)

    # ── Compare ───────────────────────────────────────────────────────────
    if args.compare:
        compare_path = Path(args.compare)
        if not compare_path.exists():
            compare_path = ROOT / args.compare
        if compare_path.exists():
            print(f"[Compare] vs {compare_path.name}...")
            diff = _compare_graphs(e3["claims"], compare_path)
            _w(out_dir / "comparison.json", diff)
            print(f"  New: {diff['new_total']}  Old: {diff['old_total']}  "
                  f"Only-new: {diff['only_in_new']}  Only-old: {diff['only_in_old']}  "
                  f"Changed: {diff['value_changes']}")

    return 0


def _print_chunk_summary(chunks: list[Chunk]) -> None:
    print(f"\n  Chunk summary ({len(chunks)} total):")
    for c in chunks[:12]:
        preview = c.body[:55].replace("\n", " ")
        print(f"    {c.source_record['source_id']:<14} {c.locator:<50} "
              f"{c.word_count:3d}w  \"{preview}...\"")
    if len(chunks) > 12:
        print(f"    ... and {len(chunks) - 12} more")


if __name__ == "__main__":
    sys.exit(main())
