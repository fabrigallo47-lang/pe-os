#!/usr/bin/env python3
"""
Extraction test harness — never writes to vault.

Drop any document into vault/test/inbox/ then run:
    .venv/bin/python3 tools/test_extract.py

Shows each extracted claim formatted exactly as it would appear in the vault,
plus a raw JSON dump for inspection.

Options:
    --file   extract a single specific file instead of scanning inbox
    --json   output raw JSON only (pipe-friendly)
    --deal   deal context hint fed to the model (default: "test")
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract import SYSTEM_PROMPT, llm_extract, parse_json

INBOX = ROOT / "vault" / "test" / "inbox"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EPISTEMIC_COLORS = {
    "asserted":  "⬜",   # seller/management claim — least verified
    "observed":  "🟦",   # directly measured
    "attested":  "🟩",   # third-party certified
    "derived":   "🟨",   # computed — requires derivation
}


def _format_claim(item: dict, idx: int) -> str:
    ep = item.get("epistemic", "?")
    badge = EPISTEMIC_COLORS.get(ep, "  ")
    lines = [
        f"── Claim {idx:02d} {badge} [{ep}] ────────────────────────────────",
        f"  subject   : {item.get('subject', '')}",
        f"  value     : {item.get('value', '')}",
        f"  period    : {item.get('period', '')}",
        f"  perimeter : {item.get('perimeter', '')}",
        f"  locator   : {item.get('locator', '')}",
        f"  bears-on  : {item.get('bears_on', [])}",
        f"  direction : {item.get('direction', '')}",
        f"  author    : {item.get('author', '')}",
    ]
    if item.get("derivation"):
        lines.append(f"  derivation: {item['derivation']}")
    if item.get("statement"):
        stmt = item["statement"]
        if len(stmt) > 120:
            stmt = stmt[:120] + "…"
        lines.append(f"  statement : {stmt}")
    return "\n".join(lines)


def _format_vault_frontmatter(item: dict, idx: int, source_file: str) -> str:
    """Render the claim exactly as it would look in vault/deals/.../claims/c-test-NNN.md"""
    ep      = item.get("epistemic", "asserted")
    subject = str(item.get("subject", "")).replace('"', "'")
    value   = str(item.get("value", "")).replace('"', "'")
    period  = str(item.get("period", "")).replace('"', "'")
    perim   = str(item.get("perimeter", "")).replace('"', "'")
    locator = str(item.get("locator", "")).replace('"', "'")
    author  = str(item.get("author", "")).replace('"', "'")
    direction = item.get("direction", "context")
    bears   = json.dumps(item.get("bears_on", []))
    deriv   = item.get("derivation")
    stmt    = (item.get("statement") or "").strip()

    lines = [
        "```yaml",
        "---",
        f'type: claim',
        f'id: c-test-{idx:03d}',
        f'epistemic: {ep}',
        f'subject: "{subject}"',
        f'value: "{value}"',
        f'period: "{period}"',
        f'perimeter: "{perim}"',
        f'bears-on: {bears}',
        f'direction: {direction}',
        f'source:',
        f'  artifact: "{source_file}"',
        f'  locator: "{locator}"',
        f'  author: "{author}"',
        f'derivation: {json.dumps(deriv)}',
        "---",
        "```",
    ]
    if stmt:
        lines.append(f"\n{stmt}")
    return "\n".join(lines)


def extract_file(path: Path, deal_context: str, json_only: bool) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    char_count = len(text)
    if char_count > 80_000:
        print(f"  [truncating {path.name}: {char_count:,} → 80,000 chars]", file=sys.stderr)
        text = text[:80_000]

    user_msg = f"DEAL CONTEXT:\n{deal_context}\n\nARTIFACT ({path.name}):\n{text}"

    if not json_only:
        print(f"\n{'='*64}")
        print(f"  Extracting: {path.name}  ({char_count:,} chars)")
        print(f"{'='*64}")

    raw = llm_extract(SYSTEM_PROMPT, user_msg)
    items = parse_json(raw)

    if not json_only:
        print(f"  → {len(items)} claims extracted\n")
        for i, item in enumerate(items, 1):
            print(_format_claim(item, i))
            print()
        print(f"\n{'─'*64}")
        print("  VAULT PREVIEW (first 5 claims as they'd appear in vault):")
        print(f"{'─'*64}\n")
        for i, item in enumerate(items[:5], 1):
            print(_format_vault_frontmatter(item, i, path.name))
            print()

    return items


def main() -> None:
    ap = argparse.ArgumentParser(description="Extraction test harness (never writes to vault)")
    ap.add_argument("--file", help="Extract a specific file (default: scan vault/test/inbox/)")
    ap.add_argument("--deal", default="test",
                    help="Deal name / context hint for the model")
    ap.add_argument("--json", action="store_true", dest="json_out",
                    help="Output raw JSON only")
    args = ap.parse_args()

    if not API_KEY:
        sys.exit("ANTHROPIC_API_KEY not set — export it first")

    deal_context = (
        f"Deal: {args.deal}. Extract all factual claims relevant to investment analysis. "
        "Apply epistemic typing carefully:\n"
        "  asserted  = seller or management claim, no external verification\n"
        "  observed  = directly measured / recorded by a third party\n"
        "  attested  = qualified third party formally certifies (QoE firm, IC decision, Firm underwriting)\n"
        "  derived   = you computed it from other stated values (include derivation)\n"
        "Include period and perimeter on every claim."
    )

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(INBOX.glob("*"))
        files = [f for f in files if f.is_file() and not f.name.startswith(".")]

    if not files:
        print(f"No files in {INBOX}")
        print(f"Drop a document there and re-run:")
        print(f"  cp /path/to/your/doc.md {INBOX}/")
        print(f"  .venv/bin/python3 tools/test_extract.py")
        return

    all_items: list[dict] = []
    for f in files:
        items = extract_file(f, deal_context, args.json_out)
        for item in items:
            item["_source_file"] = f.name
        all_items.extend(items)

    if args.json_out:
        print(json.dumps(all_items, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*64}")
        print(f"  TOTAL: {len(all_items)} claims from {len(files)} file(s)")
        print(f"  Run with --json to get raw JSON for inspection")
        print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
