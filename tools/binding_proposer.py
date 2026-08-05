#!/usr/bin/env python3
"""Binding proposer — zero LLM.

Connects unbound claims to the questions they support, with a confidence score.
Confidence-scored proposals; ambiguous cases go to human review queue.

Output categories:
  high_confidence (>=0.70): auto-propose for human confirmation
  needs_review (0.35-0.70): put in queue, require human judgment
  unresolvable (<0.35): cannot map — flag in coverage report

Usage:
    python3 tools/binding_proposer.py keystone
    python3 tools/binding_proposer.py keystone --min-confidence 0.5 --write
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# metric-category → question keyword signals
METRIC_TO_QUESTION_SIGNALS: dict[str, list[str]] = {
    "ebitda": ["ebitda", "quality", "adjustment", "bridge", "earnings", "margin", "profitability"],
    "revenue": ["revenue", "durability", "concentration", "customer", "growth", "backlog"],
    "debt": ["debt", "leverage", "covenant", "classification", "lien", "credit"],
    "equity": ["equity", "ownership", "sponsor", "return", "cure"],
    "irr": ["return", "irr", "moic", "exit", "value creation"],
    "leverage": ["leverage", "covenant", "debt", "net leverage"],
    "customer-concentration": ["concentration", "customer", "parent", "counterparty"],
    "working-capital": ["working capital", "nwc", "wip", "receivable", "payable", "dso"],
    "headcount": ["employee", "headcount", "key person", "management", "team"],
    "cash": ["cash", "liquidity", "free cash flow", "fcf"],
}


@dataclass
class BindingProposal:
    claim_id: str
    claim_subject: str
    question_id: str
    question_title: str
    confidence: float
    reasons: list[str]
    category: str   # "high_confidence" | "needs_review" | "unresolvable"


def _words(s: str) -> set[str]:
    return set(re.findall(r'\w+', s.lower()))


def _score_binding(claim: dict, question: dict) -> tuple[float, list[str]]:
    """Score how well a claim binds to a question."""
    reasons: list[str] = []
    score = 0.0

    c_subj = (claim.get("subject") or "").lower()
    c_mc = claim.get("metric_category") or claim.get("metric-category") or ""
    c_value = (claim.get("value") or "").lower()

    q_title = (question.get("title") or "").lower()
    q_bearing = (question.get("bearing") or "").lower()
    q_id = (question.get("id") or "").lower()

    q_text = f"{q_title} {q_bearing} {q_id}"

    # Direct word overlap between claim subject and question title/bearing
    c_words = _words(c_subj)
    q_words = _words(q_text)
    overlap = len(c_words & q_words) / max(len(c_words | q_words), 1)
    if overlap > 0:
        score += overlap * 0.60
        if overlap > 0.30:
            reasons.append(f"subject overlap {overlap:.0%}: {c_words & q_words}")

    # metric-category signals match question
    if c_mc and c_mc in METRIC_TO_QUESTION_SIGNALS:
        signals = METRIC_TO_QUESTION_SIGNALS[c_mc]
        signal_hits = [s for s in signals if s in q_text]
        if signal_hits:
            score = min(1.0, score + 0.25)
            reasons.append(f"metric '{c_mc}' → signals: {signal_hits[:3]}")

    # metric-category directly in question ID (e.g. kq-01-ebitda-quality)
    if c_mc and c_mc.replace("-", "").replace(" ", "") in q_id.replace("-", "").replace(" ", ""):
        score = min(1.0, score + 0.15)
        reasons.append(f"metric '{c_mc}' in question ID")

    # Value mentions a number that appears in question bearing
    nums_in_value = re.findall(r'\d+\.?\d*', c_value)
    nums_in_q = re.findall(r'\d+\.?\d*', q_bearing)
    if nums_in_value and nums_in_q and set(nums_in_value) & set(nums_in_q):
        score = min(1.0, score + 0.10)
        reasons.append(f"numeric match in value/question")

    return round(score, 3), reasons


def propose_bindings(con: sqlite3.Connection, deal: str) -> list[BindingProposal]:
    """Find best question bindings for all unbound claims in a deal."""
    # Load unbound claims
    claim_rows = con.execute(
        "SELECT n.id, n.subject, n.frontmatter, n.metric_category "
        "FROM nodes n "
        "WHERE n.type='claim' AND n.deal=? "
        "AND NOT EXISTS (SELECT 1 FROM edges e WHERE e.src=n.id AND e.rel='bears-on')",
        (deal,),
    ).fetchall()

    # Load open questions
    question_rows = con.execute(
        "SELECT id, title, frontmatter FROM nodes "
        "WHERE type='question' AND deal=? AND state IN ('open','reducing')",
        (deal,),
    ).fetchall()

    questions: list[dict] = []
    for qid, qtitle, fm_raw in question_rows:
        fm = json.loads(fm_raw or "{}")
        questions.append({
            "id": qid, "title": qtitle or qid,
            "bearing": fm.get("bearing", ""),
        })

    proposals: list[BindingProposal] = []
    for cid, subj, fm_raw, mc in claim_rows:
        fm = json.loads(fm_raw or "{}")
        claim = {
            "id": cid, "subject": subj or fm.get("subject", ""),
            "value": fm.get("value", ""),
            "metric_category": mc or fm.get("metric-category"),
        }

        best_score = 0.0
        best_q = None
        best_reasons: list[str] = []
        for q in questions:
            sc, reasons = _score_binding(claim, q)
            if sc > best_score:
                best_score, best_q, best_reasons = sc, q, reasons

        if best_q is None or best_score < 0.10:
            proposals.append(BindingProposal(
                claim_id=cid, claim_subject=claim["subject"],
                question_id="", question_title="",
                confidence=0.0, reasons=["no matching question found"],
                category="unresolvable",
            ))
            continue

        cat = ("high_confidence" if best_score >= 0.70
               else "needs_review" if best_score >= 0.35
               else "unresolvable")
        proposals.append(BindingProposal(
            claim_id=cid, claim_subject=claim["subject"],
            question_id=best_q["id"], question_title=best_q["title"],
            confidence=best_score, reasons=best_reasons,
            category=cat,
        ))

    proposals.sort(key=lambda p: -p.confidence)
    return proposals


def print_report(proposals: list[BindingProposal]) -> None:
    high = [p for p in proposals if p.category == "high_confidence"]
    review = [p for p in proposals if p.category == "needs_review"]
    unres = [p for p in proposals if p.category == "unresolvable"]

    print(f"\nBinding Proposals — {len(proposals)} unbound claims")
    print(f"  ✓ High confidence (≥0.70): {len(high)}")
    print(f"  ? Needs review (0.35–0.70): {len(review)}")
    print(f"  ✗ Unresolvable (<0.35): {len(unres)}")

    for section, items, badge in [
        ("HIGH CONFIDENCE", high, "✓"),
        ("NEEDS REVIEW", review, "?"),
        ("UNRESOLVABLE", unres[:10], "✗"),
    ]:
        if not items:
            continue
        print(f"\n── {section} ──")
        for p in items[:15]:
            print(f"{badge} [{p.confidence:.2f}] {p.claim_id}")
            print(f"     subject: {p.claim_subject[:80]}")
            if p.question_id:
                print(f"     → {p.question_id}: {p.question_title}")
            for r in p.reasons[:2]:
                print(f"     reason: {r}")


def main() -> None:
    import argparse, os
    sys.path.insert(0, str(ROOT / "tools"))
    import indexer

    p = argparse.ArgumentParser()
    p.add_argument("deal")
    p.add_argument("--min-confidence", type=float, default=0.35)
    p.add_argument("--write", action="store_true",
                   help="Write high-confidence proposals as bears-on into claim files")
    args = p.parse_args()

    if not indexer.DB.exists():
        sys.exit("No index — run `make index` first")

    con = sqlite3.connect(indexer.DB)
    proposals = propose_bindings(con, args.deal)
    print_report(proposals)

    if args.write:
        import datetime as _dt
        VAULT = Path(os.environ["PEOS_VAULT"]) if os.environ.get("PEOS_VAULT") else ROOT / "vault"
        today = _dt.date.today().isoformat()
        written = 0
        for p_item in proposals:
            if p_item.category != "high_confidence":
                continue
            fpath = VAULT / "deals" / args.deal / "claims" / f"{p_item.claim_id}.md"
            if not fpath.exists():
                continue
            text = fpath.read_text(encoding="utf-8")
            if p_item.question_id in text:
                continue  # already bound
            # Insert bears-on
            bears_line = f'bears-on: ["[[{p_item.question_id}]]"]'
            text = re.sub(r"bears-on:\s*\[\]", bears_line, text)
            text = re.sub(r"last-seen:\s*\S+", f"last-seen: {today}", text)
            fpath.write_text(text, encoding="utf-8")
            written += 1
        print(f"\nWrote {written} high-confidence bindings to vault.")
        indexer.build()

    con.close()


if __name__ == "__main__":
    main()
