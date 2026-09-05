#!/usr/bin/env python3
"""Say where a deal stands, in words, without moving anything.

G6. "What's the state of this deal?" should be answerable without a human
reconstructing it from files, and without the act of asking changing a single
byte.

This is a LENS, and the distinction is the whole design:

  * It never writes. Not the vault, not the index, not a cache. The test suite
    hashes every file under the deal before and after and asserts they are
    identical, because "read-only" is a property worth proving rather than
    intending.
  * It never derives `deal.state` itself. Invariant 10 says that state is
    resolved from events, exposure and blockers by the backbone rule; a second
    implementation living in a reporting tool would be a competing answer, and
    two answers is worse than none. The lens REPORTS the resolved value and
    says plainly when it is absent.
  * It never adjudicates. Open contradictions are counted and named, never
    ranked by who is probably right (invariant 8).
  * It confers no authority. It cannot admit, settle, resolve a question, or
    advance anything — the desks in vault/roles/ have the same property by
    design: "they never own data, only lens and triggers".

    python3 tools/deal_state_lens.py <deal-slug> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VAULT = ROOT / "vault"

# Question states that mean "still owed an answer". Anything else is either
# settled or explicitly parked by a human, and neither is an open front.
OPEN_QUESTION_STATES = frozenset({"open", "in-progress", "in_progress", "blocked"})


def _frontmatter(path: Path) -> dict[str, Any]:
    """Minimal YAML front-matter read: scalars and simple lists only.

    Deliberately not PyYAML-strict. The lens must never fail to describe a deal
    because one file has an exotic value; an unreadable field is reported as
    unknown, which is information, while a traceback is not.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    block, _, _ = rest.partition("\n---")
    out: dict[str, Any] = {}
    key = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Vault files write block-sequence items flush left, not indented:
        #     bears-on:
        #     - Q-03
        # Requiring indentation here silently dropped every binding and made
        # the lens report 817 of 836 keystone claims as bearing on nothing.
        if line.lstrip().startswith("- ") and key:
            out.setdefault(key, [])
            if isinstance(out[key], list):
                out[key].append(line.lstrip()[2:].strip().strip("\"'"))
            continue
        name, sep, value = line.partition(":")
        if not sep:
            continue
        key = name.strip()
        value = value.strip().strip("\"'")
        # `bears-on: []` is an EMPTY list written inline. Kept as the string
        # "[]" it reads as truthy, and a claim bearing on nothing would be
        # counted as bound — the opposite of what the field says.
        if value in {"[]", "{}", "null", "~"}:
            out[key] = []
        else:
            out[key] = value if value else []
    return out


def _count_md(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.md")) if directory.is_dir() else []


def observe(deal: str, vault: Path | None = None) -> dict[str, Any]:
    """Everything the lens can see. Pure read."""
    root = (vault or VAULT) / "deals" / deal
    if not root.is_dir():
        return {"deal": deal, "exists": False}

    deal_md = _frontmatter(root / "deal.md")

    questions = [_frontmatter(p) for p in _count_md(root / "questions")]
    q_states = Counter(str(q.get("state") or q.get("status") or "unknown").lower()
                       for q in questions)
    open_questions = [q for q in questions
                      if str(q.get("state") or q.get("status") or "").lower()
                      in OPEN_QUESTION_STATES]
    critical_open = [q for q in open_questions
                     if str(q.get("critical")).lower() in {"true", "yes", "1"}]

    claims = [_frontmatter(p) for p in _count_md(root / "claims")]
    epistemic = Counter(str(c.get("epistemic") or c.get("epistemic_class") or "unknown")
                        for c in claims)
    # A claim that bears on nothing is evidence nobody asked for: it is in the
    # vault but it answers no question, so it cannot move the deal.
    unbound = [c for c in claims if not c.get("bears-on")]

    events = [_frontmatter(p) for p in _count_md(root / "events")]
    event_kinds = Counter(str(e.get("kind") or "unknown") for e in events)
    latest = max((str(e.get("at") or "") for e in events), default="")

    decisions = _count_md(root / "decisions")

    return {
        "deal": deal,
        "exists": True,
        "state": deal_md.get("state") or None,
        "lead": deal_md.get("lead") or None,
        "opened": deal_md.get("opened") or None,
        "thesis": deal_md.get("thesis") or None,
        "questions": {
            "total": len(questions),
            "open": len(open_questions),
            "critical_open": [str(q.get("id") or "?") for q in critical_open],
            "by_state": dict(q_states),
        },
        "claims": {
            "total": len(claims),
            "by_epistemic": dict(epistemic),
            "unbound": len(unbound),
        },
        "events": {
            "total": len(events),
            "latest_at": latest or None,
            "by_kind": dict(event_kinds),
        },
        "decisions": len(decisions),
    }


def narrate(picture: dict[str, Any]) -> str:
    """The same facts as a paragraph a person can read in one pass."""
    if not picture.get("exists"):
        return f"{picture['deal']}: no such deal in the vault."

    lines = [f"{picture['deal']} — {picture.get('state') or 'state not resolved'}"]
    if picture.get("lead"):
        lines.append(f"  lead {picture['lead']}, opened {picture.get('opened') or 'unknown'}")
    if not picture.get("state"):
        # Invariant 10: derived, never set. Absence is reported, never filled in.
        lines.append("  deal.md carries no resolved state — the backbone rule has "
                     "not run, and this lens does not run it")

    q, c, e = picture["questions"], picture["claims"], picture["events"]
    lines.append(f"  questions   {q['open']} open of {q['total']}"
                 + (f" — critical: {', '.join(q['critical_open'])}"
                    if q["critical_open"] else ""))
    epistemic = ", ".join(f"{k} {v}" for k, v in sorted(c["by_epistemic"].items())
                          if k != "unknown")
    lines.append(f"  evidence    {c['total']} claims"
                 + (f" ({epistemic})" if epistemic else ""))
    if c["unbound"]:
        lines.append(f"              {c['unbound']} bear on no question — "
                     f"evidence nobody asked for")
    lines.append(f"  activity    {e['total']} events"
                 + (f", latest {e['latest_at']}" if e["latest_at"] else ""))
    lines.append(f"  decisions   {picture['decisions']} recorded")
    lines.append("  (lens only — nothing here was admitted, settled or written)")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Report where a deal stands. Writes nothing.")
    ap.add_argument("deal", help="deal slug, e.g. astrelia")
    ap.add_argument("--json", action="store_true", help="emit the raw observation")
    args = ap.parse_args(argv[1:])

    picture = observe(args.deal)
    print(json.dumps(picture, indent=2, ensure_ascii=False) if args.json
          else narrate(picture))
    return 0 if picture.get("exists") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
