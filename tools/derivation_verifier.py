#!/usr/bin/env python3
"""Verify a `derived` claim's arithmetic by executing it, never by trusting it.

The pattern this follows is established, not improvised: Logic-LM and
Faithful Chain-of-Thought (translate to a formal program, execute with a
separate deterministic engine, never let the model's own arithmetic stand
unchecked) and FinQA specifically for financial text (an executable
numerical program over extracted values, checked against the stated
answer). PANTA's `derivation` field is already the right SHAPE for this --
free text describing an arithmetic chain -- it is just never executed.

Run against the real Keystone claims (pipeline_out/e3/K-PRE/e3_claims.json,
9 derived claims): finds three claims whose stored `value` does not match
their own derivation text's arithmetic, sitting unflagged in the pipeline's
output today. Not synthetic examples -- this file's own first real run
found them.

This module only reports. It never corrects a claim -- per the same
principle CHARACTERISATION filtering already established in extract_v2_
physical.py: a deterministic filter's job is to make a defect visible with
a reason, not to silently repair it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.model_evaluator import UnsupportedExpression, evaluate_expression  # noqa: E402

# Unicode operator variants a derivation string may use, normalized to ASCII
# before parsing -- "−" (U+2212) is not "-" (U+002D) to Python's tokenizer.
_OPERATOR_NORMALIZE = {"−": "-", "×": "*", "÷": "/", ",": ""}
_CURRENCY_RE = re.compile(r"[$€£]")
# A number directly followed by a unit word: "$0.7m", "463 / 9 = 51.4 days".
# Stripped only when adjacent -- never removes a bare word elsewhere in the
# sentence, so "8 employees" strips to "8" but a stray "employees" alone is
# left for the arithmetic-chain regex to correctly fail to match.
_UNIT_SUFFIX_RE = re.compile(
    r"(?<=[\d)])\s*(?:m|mm|million|thousand|k|days?|years?|employees?|%)\b",
    re.IGNORECASE,
)
# The longest run of digits/operators/parens/dots/spaces containing at least
# one operator -- deliberately greedy, so prose on either side (which always
# contains a letter) breaks the match rather than being swallowed into it.
_ARITHMETIC_CHAIN_RE = re.compile(r"[()\d.\s+\-*/]*[+\-*/][()\d.\s+\-*/]*")
_FIRST_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _normalize(text: str) -> str:
    for old, new in _OPERATOR_NORMALIZE.items():
        text = text.replace(old, new)
    text = _CURRENCY_RE.sub("", text)
    text = _UNIT_SUFFIX_RE.sub("", text)
    return text


def _longest_arithmetic_chain(text: str) -> str | None:
    """The longest pure-numeric expression in `text`, or None.

    Deliberately conservative: "customer relationships $2.8m + non-compete
    $0.2m" has an operator but also letters inside the chain, so no regex
    match spans it whole -- correctly refused rather than mis-parsed into
    "2.8 + 0.2" while silently dropping what the addends actually were.
    """
    best = None
    for match in _ARITHMETIC_CHAIN_RE.finditer(text):
        # Trim dangling operators the regex's greedy match can pick up at a
        # boundary with prose -- "customer relationships $2.8m + non-compete"
        # matches "2.8 +" before this trim, a fragment with no right-hand
        # side that would only fail two calls later, inside evaluate_expression.
        candidate = match.group().strip().strip("+-*/ \t")
        if not candidate or not any(op in candidate for op in "+-*/"):
            continue
        if best is None or len(candidate) > len(best):
            best = candidate
    return best


def parse_derivation(derivation: str) -> dict[str, Any]:
    """Split a derivation string into (expression, stated result), or say why not.

    A derivation may state its result more than once ("... = 10.73 years"
    after already resolving an earlier "="), in which case the LAST "="
    is the one whose left side is the actual computation and whose right
    side is the number a reader is meant to take away.
    """
    if not derivation or not derivation.strip():
        return {"parsed": False, "reason": "empty derivation"}

    text = _normalize(derivation)
    if "=" not in text:
        return {"parsed": False, "reason": "no '=' in derivation -- nothing to check against"}

    left, _, right = text.rpartition("=")
    result_match = _FIRST_NUMBER_RE.search(right)
    if not result_match:
        return {"parsed": False, "reason": "no numeric result after the final '='"}
    stated_result = float(result_match.group())

    expression = _longest_arithmetic_chain(left)
    if expression is None:
        return {
            "parsed": False,
            "reason": "no pure-numeric arithmetic chain found before '=' "
                      "(the computation is described in prose, not numbers, "
                      "or mixes labels into the chain)",
            "stated_result": stated_result,
        }
    return {"parsed": True, "expression": expression, "stated_result": stated_result}


def verify_derivation(derivation: str, claimed_value: Any) -> dict[str, Any]:
    """Execute a derivation's own arithmetic and compare it two ways:
    against what the derivation TEXT itself claims as its result, and
    against the VALUE the claim actually carries. These can disagree with
    each other independently of whether the arithmetic is right -- and did,
    on real data (a claim's stored value matching neither its own
    derivation's stated result nor the executed computation).
    """
    parsed = parse_derivation(derivation)
    if not parsed["parsed"]:
        return {"status": "unparseable", **parsed}

    try:
        computed = evaluate_expression(parsed["expression"], {})
    except UnsupportedExpression as exc:
        return {"status": "unparseable", "parsed": True,
                "expression": parsed["expression"], "reason": str(exc)}

    tolerance = max(abs(computed) * 0.005, 0.01)  # 0.5% or 0.01, whichever wider
    text_self_consistent = abs(computed - parsed["stated_result"]) <= tolerance

    try:
        claimed_float = float(str(claimed_value).strip())
    except (TypeError, ValueError):
        return {
            "status": "text_inconsistent" if not text_self_consistent else "value_not_numeric",
            "expression": parsed["expression"], "computed": computed,
            "stated_result": parsed["stated_result"],
            "text_self_consistent": text_self_consistent,
            "claimed_value": claimed_value,
        }

    value_matches_computed = abs(computed - claimed_float) <= tolerance
    if text_self_consistent and value_matches_computed:
        status = "verified"
    elif not text_self_consistent and value_matches_computed:
        status = "value_ok_text_wrong"      # derivation prose miscalculates its own stated result
    elif text_self_consistent and not value_matches_computed:
        status = "value_disagrees_with_text"  # stored value does not match what the derivation itself concluded
    else:
        status = "computed_disagrees_with_both"

    return {
        "status": status, "expression": parsed["expression"], "computed": computed,
        "stated_result": parsed["stated_result"], "claimed_value": claimed_float,
        "text_self_consistent": text_self_consistent,
        "value_matches_computed": value_matches_computed,
    }


def verify_claims(claims_payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields_by_id = {
        f["claim_id"]: f
        for f in claims_payload.get("extraction_metadata", {}).get("compiler_fields_per_claim", [])
    }
    results = []
    for claim in claims_payload.get("claims", []):
        if claim.get("epistemic_class") != "derived":
            continue
        fields = fields_by_id.get(claim.get("claim_id"), {})
        derivation = fields.get("derivation")
        result = verify_derivation(derivation or "", claim.get("value"))
        results.append({
            "claim_id": claim.get("claim_id"), "metric": fields.get("metric"),
            "statement": claim.get("statement"), "derivation": derivation,
            **result,
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("claims_path", type=Path)
    parser.add_argument("--flagged-only", action="store_true",
                        help="only print claims whose status is not 'verified'")
    args = parser.parse_args()

    payload = json.loads(args.claims_path.read_text())
    results = verify_claims(payload)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(f"{len(results)} derived claims checked")
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}  {status}")
    print()
    for r in results:
        if args.flagged_only and r["status"] == "verified":
            continue
        print(f"[{r['status']}] {r['claim_id']} — {r['metric']}")
        print(f"  derivation: {r['derivation']}")
        print(f"  claimed value: {r.get('claimed_value')!r}")
        if r.get("expression"):
            print(f"  parsed expression: {r['expression']!r} -> computed = {r.get('computed')}")
        if r.get("reason"):
            print(f"  reason: {r['reason']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
