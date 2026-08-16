#!/usr/bin/env python3
"""
General-purpose batch extractor — works for any deal.

Usage:
    .venv/bin/python3 tools/extract.py                    # all unextracted inbox files
    .venv/bin/python3 tools/extract.py --deal keystone    # only keystone files
    .venv/bin/python3 tools/extract.py --file keystone_seller_cim.md  # single file
    .venv/bin/python3 tools/extract.py --reset keystone   # clear extracted state for a deal

Files in vault/inbox/ are routed to deals by name prefix (e.g. "keystone_*.md" → deal "keystone").
The runtime's deal_for() function handles routing; see agents/runtime.py.

Each file is extracted once (state persisted in vault/audit/runtime-state.json → "extracted" list).
Re-run safely — already-extracted files are skipped.
"""
import argparse, json, os, pathlib, re, sqlite3, sys
from datetime import datetime

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents"))

import tools.indexer as indexer
import runtime as rt

VAULT = indexer.VAULT
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("PEOS_MODEL", "claude-sonnet-5")

EPISTEMIC = {"asserted", "derived", "observed", "attested"}

SYSTEM_PROMPT = """\
You are the PE OS extractor agent for a private equity firm.

Extract every discrete factual claim from the artifact that would be useful for deal analysis.

EPISTEMIC TYPING RULES (critical — most claims from formal documents are 'attested'):
- asserted:  the SELLER or MANAGEMENT makes a claim without external verification
             (seller CIM narrative, management business description, seller forecast)
- observed:  direct measurement or recorded interaction by a third party in real time
             (QoE firm walks through a workpaper result, meeting notes, call transcript)
- attested:  a qualified THIRD PARTY formally certifies, underwrites, or decides
             Examples: QoE firm certifies EBITDA; the Firm underwrites a metric;
             IC formally approves; legal counsel confirms; an auditor states.
             Use 'attested' for the Firm's underwriting memo, IC memo, QoE conclusions.
- derived:   YOU (the extractor) computed this from other stated values;
             requires a derivation field explaining the computation.

COMMON MISTAKES TO AVOID:
- IC memo claims → attested (IC is formally deciding / underwriting)
- QoE firm conclusions → attested (third-party certification)
- Firm's initial assessment / underwriting → attested
- Seller CIM narrative → asserted
- Data room raw data → observed or asserted (depending on whether measured or claimed)
- Derived concentrations (e.g. Riverton 18.2% from 7 rows) → derived with derivation

SUBJECT NAMING RULES (critical — these prevent false contradictions):
- Use a DIFFERENT subject for each distinct EBITDA definition:
    "reported EBITDA", "seller-adjusted EBITDA", "QoE-normalized EBITDA",
    "firm-underwritten EBITDA", "covenant EBITDA" — never conflate under "EBITDA"
- Use a DIFFERENT subject for billing-account vs ultimate-parent concentration:
    "largest billing-account customer concentration" vs "largest ultimate-parent customer concentration"
- Reuse an EXISTING subject string when the same quantity (same definition, same basis) is meant
- Create a NEW subject when a different definition, basis, party, or time period applies

PERIOD AND PERIMETER (required on every claim):
- period: the time reference for the claim (e.g. "FY2025A", "As of 2025-10-27",
          "FY2026E-FY2030E", "Closing / 2026-03-31"). Use the document's own date language.
- perimeter: the economic scope — WHAT entity and definition this claim covers
          (e.g. "Alderstone consolidated revenue", "Alderstone EBITDA under QoE adjustment perimeter",
          "Alderstone customer revenue measured by individual billing account").
          Perimeter is the most important dimension — it disambiguates claims with the same value.

WHAT TO EXTRACT:
- All numeric values with their definition/basis (EBITDA, revenue, multiples, concentrations, dates)
- Key factual claims about the business (customers, products, team, markets)
- Risk factors stated by any party
- Assumptions, adjustments, and their rationale

Return ONLY a JSON array. Each element:
{
  "subject": "basis-specific subject string",
  "value": "the extracted value as a string (empty string for qualitative claims)",
  "epistemic": "asserted|derived|observed|attested",
  "period": "time reference for this claim",
  "perimeter": "economic scope / definition boundary for this claim",
  "bears_on": ["list of question ids by meaning — empty list if none"],
  "direction": "supports|contradicts|context",
  "locator": "precise section, slide, row or line reference in the artifact",
  "author": "document author or party making the claim",
  "statement": "one complete sentence stating the claim with full context",
  "derivation": "string explaining the computation if epistemic=derived, else null"
}
"""


def llm_extract(system: str, user: str, max_tokens: int = 10000) -> str:
    import urllib.request, urllib.error
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        blocks = json.loads(resp.read())["content"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if not text:
            raise ValueError(f"no text block: {str(blocks)[:200]}")
        return text


def _extract_top_level_objects(s: str) -> list[str]:
    """Quote-aware extractor: yields each top-level {...} span from a JSON array string."""
    objects: list[str] = []
    n = len(s)
    i = 0
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        start = i
        depth = 0
        in_str = False
        escaped = False
        j = i
        while j < n:
            c = s[j]
            if escaped:
                escaped = False
            elif c == "\\" and in_str:
                escaped = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        objects.append(s[start : j + 1])
                        i = j
                        break
            j += 1
        i += 1
    return objects


def _repair_json_array(raw: str) -> list:
    """Quote-aware repair for model-generated JSON arrays."""
    import sys as _sys

    # Pass 1: trailing commas
    s = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Pass 2+: quote-aware object extraction — handles unterminated strings,
    # unescaped quotes, truncated output, and braces embedded in string values.
    spans = _extract_top_level_objects(s)
    items: list = []
    skipped = 0
    for span in spans:
        try:
            items.append(json.loads(span))
        except json.JSONDecodeError:
            skipped += 1

    if not items:
        raise ValueError(f"could not parse any JSON objects; first 300 chars: {raw[:300]}")

    note = f"skipped {skipped} malformed" if skipped else "array not properly closed"
    print(f"  [parse_json] recovered {len(items)} items ({note})", file=_sys.stderr)
    return items


def parse_json(text: str) -> list:
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    m = fence or re.search(r"(\[[\s\S]*\])", text)
    if m:
        raw = m.group(1)
    else:
        # Truncated output: model was cut off before the closing ]
        start = text.find("[")
        if start < 0:
            raise ValueError(f"no JSON array found: {text[:300]}")
        raw = text[start:]  # pass to repair; truncation handler closes it
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _repair_json_array(raw)


def next_claim_id(deal: str) -> str:
    cdir = VAULT / "deals" / deal / "claims"
    existing = sorted(cdir.glob("c-*.md")) if cdir.exists() else []
    if not existing:
        return f"c-{deal}-001"
    n = int(existing[-1].stem.split("-")[-1]) + 1
    return f"c-{deal}-{n:03d}"


def write_claim(deal: str, item: dict, artifact_name: str) -> str:
    cid = next_claim_id(deal)
    ep = item.get("epistemic", "asserted")
    if ep not in EPISTEMIC:
        ep = "asserted"
    if ep == "derived" and not item.get("derivation"):
        ep = "asserted"
    bears_on = [b for b in (item.get("bears_on") or []) if b]
    bears_on_yaml = "\n".join(f"  - {b}" for b in bears_on) or "  []"
    deriv_line = (f'derivation: "{item.get("derivation","").replace(chr(34), chr(39))}"\n'
                  if ep == "derived" else "")
    subject = str(item.get("subject", "?")).replace('"', "'")
    value = str(item.get("value", "?")).replace('"', "'")
    statement = str(item.get("statement", "")).replace('"', "'")
    period = str(item.get("period", "")).replace('"', "'")
    perimeter = str(item.get("perimeter", "")).replace('"', "'")
    content = f"""---
type: claim
id: {cid}
epistemic: {ep}
subject: "{subject}"
value: "{value}"
period: "{period}"
perimeter: "{perimeter}"
direction: {item.get('direction', 'context')}
bears-on:
{bears_on_yaml}
locator: "{item.get('locator', '')}"
author: "{item.get('author', '')}"
artifact: "vault/inbox/{artifact_name}"
{deriv_line}written-by: extractor
---

# {subject}

{statement}
"""
    cdir = VAULT / "deals" / deal / "claims"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / f"{cid}.md").write_text(content, encoding="utf-8")
    return cid


def extract_file(deal: str, artifact: pathlib.Path) -> list[str]:
    """Extract claims from one artifact. Rebuilds index first to get current subjects."""
    indexer.build()
    con = sqlite3.connect(indexer.DB)
    q_rows = list((VAULT / "deals" / deal / "questions").glob("*.md")) if \
        (VAULT / "deals" / deal / "questions").exists() else []
    questions = "\n".join(
        f"- {f.stem}: {f.read_text(encoding='utf-8').split('# ',1)[1].splitlines()[0]}"
        for f in sorted(q_rows)
    ) or "(no questions defined yet for this deal)"
    existing_subjects = sorted({
        json.loads(fm).get("subject")
        for fm, in con.execute(
            "SELECT frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,))
        if json.loads(fm).get("subject")
    })
    con.close()

    text = artifact.read_text(encoding="utf-8")
    if len(text) > 100_000:
        print(f"  [truncating {artifact.name}: {len(text)} → 100000 chars]")
        text = text[:100_000]

    user = (
        f"DEAL: {deal}\n"
        f"DEAL QUESTIONS:\n{questions}\n\n"
        f"EXISTING SUBJECTS (reuse when same quantity/basis): {existing_subjects}\n\n"
        f"ARTIFACT ({artifact.name}):\n{text}"
    )

    print(f"  Calling API for {artifact.name} ({len(text):,} chars)...")
    raw = llm_extract(SYSTEM_PROMPT, user)
    data = parse_json(raw)
    print(f"  Got {len(data)} items from model")

    written = []
    for item in data:
        cid = write_claim(deal, item, artifact.name)
        written.append(cid)
        print(f"    {cid}: {str(item.get('subject','?'))[:45]} = {str(item.get('value','?'))[:50]}")
    return written


def should_run_derivations(artifact: pathlib.Path) -> bool:
    """Return True if this artifact likely contains a customer concentration table."""
    text_head = artifact.read_text(encoding="utf-8")[:5_000].lower()
    return "ultimate parent" in text_head and "% revenue" in text_head


def run_derivations(deal: str, artifact: pathlib.Path):
    """Run the concentration derivation pass for this artifact."""
    import importlib, importlib.util
    spec = importlib.util.spec_from_file_location(
        "derive_concentrations",
        ROOT / "tools" / "derive_concentrations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print(f"  Running derivation pass for {artifact.name}...")
    written = mod.derive_for_artifact(deal, artifact)
    print(f"  Derivation pass wrote {len(written)} claims: {written}")


def get_targets(deal_filter: str | None, file_filter: str | None,
                skip_done: bool = True) -> list[tuple[str, pathlib.Path]]:
    state = rt._state()
    done = set(state.get("extracted", []))
    inbox = VAULT / "inbox"
    targets = []
    for f in sorted(inbox.glob("*.md")):
        if file_filter and f.name != file_filter:
            continue
        if skip_done and f.name in done:
            continue
        deal = rt.deal_for(f.name)
        if not deal:
            continue
        if deal_filter and deal != deal_filter:
            continue
        targets.append((deal, f))
    return targets


def mark_done(filename: str):
    state = rt._state()
    done = set(state.get("extracted", []))
    done.add(filename)
    state["extracted"] = sorted(done)
    rt._save(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deal", help="Only process files for this deal slug")
    parser.add_argument("--file", help="Process exactly this filename from vault/inbox/")
    parser.add_argument("--reset", metavar="DEAL",
                        help="Clear extracted state for a deal (re-extracts everything)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files that would be extracted without doing it")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("ANTHROPIC_API_KEY not set — export it before running")

    # Reset mode
    if args.reset:
        state = rt._state()
        deal_slug = args.reset
        deal_inbox = [f.name for f in (VAULT / "inbox").glob("*.md")
                      if rt.deal_for(f.name) == deal_slug]
        done = set(state.get("extracted", [])) - set(deal_inbox)
        state["extracted"] = sorted(done)
        rt._save(state)
        print(f"Reset: cleared {len(deal_inbox)} files for deal '{deal_slug}' from extracted state")
        return

    targets = get_targets(args.deal, args.file)

    if not targets:
        print("No unextracted files found (all done or no matching deal).")
        return

    print(f"Files to extract ({len(targets)}):")
    for deal, f in targets:
        print(f"  [{deal}] {f.name} ({f.stat().st_size:,} bytes)")

    if args.dry_run:
        return

    for deal, artifact in targets:
        print(f"\n--- [{deal}] {artifact.name} ---")
        try:
            ids = extract_file(deal, artifact)
            rt.audit("extractor", "HVA_COMMERCIAL_01", "claims-extracted",
                     f"{artifact.name} → {len(ids)} claim(s)", ids)
            mark_done(artifact.name)
            print(f"  Done: {len(ids)} claims written")

            # Auto-run derivations if this looks like a customer schedule file
            if should_run_derivations(artifact):
                try:
                    run_derivations(deal, artifact)
                except Exception as exc:
                    print(f"  Derivation pass error (non-fatal): {exc}")

        except Exception as exc:
            rt.audit("extractor", "HVA_COMMERCIAL_01", "error", f"{artifact.name}: {exc}", [])
            print(f"  ERROR: {exc}")

    print(f"\nAll done. Rebuilding index...")
    indexer.build()
    print("Index rebuilt. Run `make report` or `make grade-keystone` to verify.")


if __name__ == "__main__":
    main()
