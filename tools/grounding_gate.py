#!/usr/bin/env python3
"""
Grounding gate — routes unverifiable extracted claims to human review.

Why
---
The extractor is an LLM and will occasionally attach a claim to the wrong
economic scope. The observed failure on Keystone is *intra-chunk attribution
bleed*: the IC memo's "Concern block" lists

    1. Riverton remains sufficiently durable that ...
    2. The Firm prices the transaction on $11.4m, ...

and the extractor emitted "the Firm prices the **Riverton** transaction" with
perimeter "Riverton Group". Riverton is the largest *customer*, not the target.
The claim was classed `attested` — the highest authority tier — so a downstream
engine would have enforced a false economic scope with full confidence.

A token-presence check cannot catch this: "Riverton" *is* in the chunk. What
catches it is knowing that Riverton is a counterparty and can never be the
perimeter of a firm-level financial position. That knowledge is declared per
deal in deal_profile.json, not inferred.

What this does NOT do
---------------------
It does not decide which claim is right — agents do not adjudicate. It emits a
review queue saying what could not be verified and why, for a human to ground.

Checks
------
  G1 PERIMETER_IS_COUNTERPARTY  perimeter names a declared counterparty
  G2 PERIMETER_OFF_VOCABULARY   perimeter outside the deal's declared vocabulary
  G3 PERIMETER_MISSING          perimeter absent/'unknown' on a valued claim
  G4 VALUE_NOT_IN_SOURCE        numeric value does not appear in the cited source
  G4b DERIVATION_MISSING        epistemic_class=derived with no inspectable derivation
  G5 ENTITY_NOT_IN_SOURCE       statement names an entity absent from the source

Usage
-----
  python3 tools/grounding_gate.py --claims <claims.json> [--deal keystone]
                                  [--out review_queue.json] [--fail-on blocking]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deal_profile import load_profile, DealProfile

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"
INBOX = VAULT / "inbox"

# G1 and G4 are blocking: a wrong perimeter or an unsourced number corrupts the
# economic meaning of the graph. The rest are advisory — they mark thin
# extraction, not false extraction.
BLOCKING = {"PERIMETER_IS_COUNTERPARTY", "VALUE_NOT_IN_SOURCE", "DERIVATION_MISSING"}


# ── source resolution ────────────────────────────────────────────────────────

def _source_file(locator: str) -> Path | None:
    """locator looks like 'keystone_ic_memo.md::## Heading:hint'."""
    if not locator:
        return None
    fname = locator.split("::", 1)[0].strip()
    if not fname:
        return None
    p = INBOX / fname
    return p if p.exists() else None


_source_cache: dict[str, str] = {}


def _source_text(locator: str) -> str:
    p = _source_file(locator)
    if p is None:
        return ""
    key = str(p)
    if key not in _source_cache:
        _source_cache[key] = p.read_text(encoding="utf-8", errors="replace")
    return _source_cache[key]


_WORD_NUMBERS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen", 20: "twenty",
}


def _number_in_text(value, text: str) -> bool:
    """Does this numeric value appear in the source, allowing formatting variance?"""
    if value in (None, ""):
        return True  # nothing numeric to ground
    try:
        v = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return True  # non-numeric claim value — not this check's business
    # Compare numerically against every number in the source rather than by
    # string. This tolerates the two notations that are correct but do not
    # match textually: accounting negatives — "$(0.20)m" for -0.2 — and values
    # the claim rounded, e.g. 30.7 quoted from a source that says 30.72.
    target = abs(v)
    # Sources write small counts as words ("approximately eight years"), which
    # ground the claim just as well as a digit would.
    if target == int(target) and int(target) in _WORD_NUMBERS:
        if re.search(rf"\b{_WORD_NUMBERS[int(target)]}\b", text, re.I):
            return True
    for tok in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text):
        try:
            n = float(tok.replace(",", ""))
        except ValueError:
            continue
        if n == target:
            return True
        # accept the claim as grounded if it is the source figure rounded to
        # the precision the claim itself carries
        decimals = len(str(target).split(".")[1]) if "." in str(target) else 0
        if round(n, decimals) == target:
            return True
    return False


# ── checks ───────────────────────────────────────────────────────────────────

def check_claim(claim: dict, profile: DealProfile) -> list[dict]:
    findings: list[dict] = []
    perim = (claim.get("perimeter") or "").strip()
    stmt = claim.get("statement") or ""
    locator = claim.get("locator") or ""
    value = claim.get("value")

    def add(code, detail):
        findings.append({
            "code": code,
            "blocking": code in BLOCKING,
            "claim_id": claim.get("claim_id", ""),
            "statement": stmt[:160],
            "perimeter": perim,
            "locator": locator,
            "detail": detail,
        })

    # G1 — perimeter names a counterparty
    for name, role in profile.counterparty_entities.items():
        if name.lower() in perim.lower():
            add("PERIMETER_IS_COUNTERPARTY",
                f"perimeter names {name!r}, which is a {role}. A counterparty is "
                f"not an economic perimeter for this deal.")
            break

    # G2 — perimeter outside declared vocabulary
    if perim and perim.lower() != "unknown" and profile.perimeter_vocabulary:
        if not any(perim.lower() == v.lower() for v in profile.perimeter_vocabulary):
            add("PERIMETER_OFF_VOCABULARY",
                f"{perim!r} is not in the declared perimeter vocabulary "
                f"({len(profile.perimeter_vocabulary)} entries).")

    # G3 — missing perimeter on a claim that carries a value
    if (not perim or perim.lower() == "unknown") and value not in (None, ""):
        add("PERIMETER_MISSING",
            "valued claim has no economic perimeter — scope is undetermined.")

    # G4 / G5 — grounding against the cited source
    text = _source_text(locator)
    is_derived = (claim.get("epistemic_class") or "").strip().lower() == "derived"
    if is_derived:
        # A derived value is computed, so it correctly does not appear verbatim in
        # the source. Invariant 3 requires an inspectable derivation instead.
        if not (claim.get("derivation") or "").strip():
            add("DERIVATION_MISSING",
                "epistemic_class=derived without an inspectable derivation.")
    elif text:
        if not _number_in_text(value, text):
            add("VALUE_NOT_IN_SOURCE",
                f"value {value!r} does not appear in {_source_file(locator).name}.")
        # entity mentioned in the statement but absent from the cited document
        for name in profile.counterparty_entities:
            if name.lower() in stmt.lower() and name.lower() not in text.lower():
                add("ENTITY_NOT_IN_SOURCE",
                    f"statement names {name!r}, absent from the cited source.")
                break
    elif locator:
        add("ENTITY_NOT_IN_SOURCE", f"cited source not found for locator {locator!r}.")

    return findings


def run(claims_path: Path, deal: str) -> dict:
    raw = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = raw.get("claims", raw) if isinstance(raw, dict) else raw
    profile = load_profile(deal)

    # CAP-003 keeps the claim record to frozen fields; compiler metadata
    # (derivation, author, metric) lives alongside it. Join it back on claim_id
    # so the derivation check reads the field where it actually lives.
    if isinstance(raw, dict):
        sidecar = {
            m.get("claim_id"): m
            for m in raw.get("extraction_metadata", {})
                        .get("compiler_fields_per_claim", [])
            if m.get("claim_id")
        }
        if sidecar:
            claims = [
                {**c, **{k: v for k, v in sidecar.get(c.get("claim_id"), {}).items()
                         if k not in c or not c.get(k)}}
                for c in claims
            ]

    all_findings: list[dict] = []
    for c in claims:
        all_findings.extend(check_claim(c, profile))

    by_code: dict[str, int] = {}
    for f in all_findings:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
    blocking = [f for f in all_findings if f["blocking"]]
    flagged_ids = {f["claim_id"] for f in all_findings}

    return {
        "deal": deal,
        "claims_file": str(claims_path),
        "profile_loaded": profile.loaded,
        "claims_total": len(claims),
        "claims_flagged": len(flagged_ids),
        "claims_clean": len(claims) - len(flagged_ids),
        "findings_total": len(all_findings),
        "blocking_total": len(blocking),
        "by_code": by_code,
        "review_queue": all_findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Grounding gate for extracted claims")
    ap.add_argument("--claims", type=Path, required=True)
    ap.add_argument("--deal", default="keystone")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--fail-on", choices=["none", "blocking", "any"], default="none",
                    help="exit non-zero when findings of this severity exist")
    a = ap.parse_args()

    rep = run(a.claims, a.deal)

    print("=" * 62)
    print("GROUNDING GATE —", a.deal)
    print("=" * 62)
    print(f"  claims             : {rep['claims_total']}")
    print(f"  clean              : {rep['claims_clean']}")
    print(f"  flagged for review : {rep['claims_flagged']}")
    print(f"  blocking findings  : {rep['blocking_total']}")
    print()
    for code, n in sorted(rep["by_code"].items(), key=lambda kv: -kv[1]):
        mark = "BLOCK" if code in BLOCKING else "review"
        print(f"    [{mark:6}] {code:<28} {n}")

    if rep["blocking_total"]:
        print()
        print("  Blocking findings (human grounding required):")
        for f in rep["review_queue"]:
            if not f["blocking"]:
                continue
            print(f"    · {f['claim_id']}  {f['code']}")
            print(f"        {f['statement']}")
            print(f"        {f['detail']}")

    if a.out:
        a.out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"\n  review queue → {a.out}")

    if a.fail_on == "blocking" and rep["blocking_total"]:
        return 1
    if a.fail_on == "any" and rep["findings_total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
