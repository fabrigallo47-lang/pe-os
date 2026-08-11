#!/usr/bin/env python3
"""Batch extraction of remaining Keystone Layer-1 docs via direct Anthropic API.
Run: .venv/bin/python3 tools/batch_extract_keystone.py

Marks question_list and firm_initial_assessment as already done (partial claims exist),
then extracts all other keystone files sequentially.
"""
import json, os, pathlib, re, sys, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agents"))

import tools.indexer as indexer
import runtime as rt

VAULT = indexer.VAULT
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("PEOS_MODEL", "claude-sonnet-5")

if not API_KEY:
    sys.exit("ANTHROPIC_API_KEY not set")

EPISTEMIC = {"asserted", "derived", "observed", "attested"}

# Files already handled in prior sessions
ALREADY_DONE = {"keystone_question_list.md", "keystone_firm_initial_assessment.md"}


def llm_extract(system: str, user: str, max_tokens: int = 10000) -> str:
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


def parse_json(text: str):
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    m = fence or re.search(r"(\[[\s\S]*\])", text)
    if not m:
        raise ValueError(f"no JSON array found: {text[:300]}")
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(cleaned)


def next_claim_id(deal: str) -> str:
    cdir = VAULT / "deals" / deal / "claims"
    existing = sorted(cdir.glob("c-*.md"))
    if not existing:
        return f"c-{deal}-001"
    last = existing[-1].stem
    n = int(last.split("-")[-1]) + 1
    return f"c-{deal}-{n:03d}"


def write_claim(deal: str, item: dict, artifact_name: str) -> str:
    import tools.extract as _ext
    return _ext.write_claim(deal, item, artifact_name)


def extract_file(deal: str, artifact: pathlib.Path) -> list[str]:
    indexer.build()
    import sqlite3
    con = sqlite3.connect(indexer.DB)
    questions = "\n".join(
        f"- {f.stem}: {f.read_text(encoding='utf-8').split('# ',1)[1].splitlines()[0]}"
        for f in (VAULT / "deals" / deal / "questions").glob("*.md")
    )
    existing_subjects = sorted({
        json.loads(fm).get("subject")
        for fm, in con.execute(
            "SELECT frontmatter FROM nodes WHERE type='claim' AND deal=?", (deal,))
        if json.loads(fm).get("subject")
    })
    con.close()

    text = artifact.read_text(encoding="utf-8")
    # truncate to 100KB — data_room_extract is 149KB
    if len(text) > 100_000:
        print(f"  [truncating {artifact.name} from {len(text)} to 100000 chars]")
        text = text[:100_000]

    import tools.extract as _ext
    system = _ext.SYSTEM_PROMPT
    user = (
        f"DEAL QUESTIONS:\n{questions}\n\n"
        f"EXISTING SUBJECTS (reuse when same quantity): {existing_subjects}\n\n"
        f"ARTIFACT ({artifact.name}):\n{text}"
    )

    print(f"  Calling API for {artifact.name} ({len(text)} chars)...")
    raw = llm_extract(system, user)
    data = parse_json(raw)
    print(f"  Got {len(data)} items from model")

    written = []
    for item in data:
        cid = write_claim(deal, item, artifact.name)
        written.append(cid)
        print(f"    {cid}: {item.get('subject','?')} = {str(item.get('value','?'))[:50]}")
    return written


def main():
    deal = "keystone"
    state = rt._state()
    done = set(state.get("extracted", []))

    # Mark prior partial extractions as done
    for f in ALREADY_DONE:
        done.add(f)
    state["extracted"] = list(done)
    rt._save(state)
    print(f"Pre-marked as done: {sorted(done)}")

    inbox = VAULT / "inbox"
    targets = sorted([
        f for f in inbox.glob("*.md")
        if f.name not in done and rt.deal_for(f.name) == deal
    ])
    print(f"\nFiles to extract ({len(targets)}):")
    for t in targets:
        print(f"  {t.name} ({t.stat().st_size} bytes)")

    for artifact in targets:
        print(f"\n--- Extracting {artifact.name} ---")
        try:
            ids = extract_file(deal, artifact)
            rt.audit("extractor", "HVA_COMMERCIAL_01", "claims-extracted",
                     f"{artifact.name} → {len(ids)} claim(s)", ids)
            done.add(artifact.name)
            state["extracted"] = list(done)
            rt._save(state)
            print(f"  Done: {len(ids)} claims written")
        except Exception as exc:
            rt.audit("extractor", "HVA_COMMERCIAL_01", "error", f"{artifact.name}: {exc}", [])
            print(f"  ERROR: {exc}")

    print(f"\nAll done. Rebuilding index...")
    indexer.build()
    print("Index rebuilt. Run `make report` to see full state.")


if __name__ == "__main__":
    main()
