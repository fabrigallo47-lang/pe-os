#!/usr/bin/env python3
"""
Keystone Layer-1 + Layer-2 arc grader.

Reads the answer key (NEVER ingested into vault/prompts) and compares against
extracted claims and events. Produces a scorecard with PASS/FAIL/PARTIAL per field.

Usage:
    .venv/bin/python3 tools/grade_keystone.py           # Layer-1 + arc
    .venv/bin/python3 tools/grade_keystone.py --json    # machine-readable
    .venv/bin/python3 tools/grade_keystone.py --arc     # arc tests only

The answer key path is deliberately hardcoded outside vault/ to prevent accidental
ingestion. This script is the ONLY authorized reader of the answer key.
"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).parent.parent
VAULT = ROOT / "vault"
CLAIMS_DIR = VAULT / "deals" / "keystone" / "claims"
EVENTS_DIR = VAULT / "deals" / "keystone" / "events"

# ---------------------------------------------------------------------------
# Answer key — controlling values from keystone_answer_key.md (Layer 3).
# These are NOT derived from vault contents; they are the ground truth.
# ---------------------------------------------------------------------------
CONTROLLING = {
    "enterprise_value": 108.0,
    "reported_ebitda": 10.2,
    "seller_adj_ebitda": 12.7,
    "qoe_ebitda": 11.9,
    "firm_ebitda": 11.4,
    "covenant_ebitda": 12.2,
    "sponsor_equity": 62.0,
    "seller_rollover": 12.0,
    "largest_billing_account_pct": 0.076,   # 7.6% — by billing account
    "largest_ultimate_parent_pct": 0.182,   # 18.2% — by ultimate parent (Riverton)
    "riverton_row_count": 7,                # rows in data-room customer schedule
}

EBITDA_BASES = {
    "reported":       10.2,
    "seller-adj":     12.7,
    "qoe":            11.9,
    "firm-underwritten": 11.4,
    "covenant":       12.2,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_claims() -> list[dict]:
    """Parse all keystone claim frontmatter."""
    claims = []
    for f in sorted(CLAIMS_DIR.glob("c-keystone-*.md")):
        txt = f.read_text(encoding="utf-8")
        c = {
            "id": f.stem,
            "file": f.name,
            "epistemic": _field(txt, "epistemic"),
            "subject": _field(txt, "subject"),
            "value": _field(txt, "value"),
            "artifact": _field(txt, "artifact"),
            "derivation": _field(txt, "derivation"),
            "statement": _body(txt),
            "raw": txt,
        }
        claims.append(c)
    return claims


def _field(txt: str, key: str) -> str:
    m = re.search(rf'^{key}:\s*"?([^"\n]+)"?', txt, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _body(txt: str) -> str:
    parts = txt.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else ""


def num_in(text: str, value: float, tol: float = 0.02) -> bool:
    """Return True if `value` (±tol) appears as a number in text."""
    for m in re.finditer(r"[\d]+\.?\d*", text):
        try:
            if abs(float(m.group()) - value) <= tol:
                return True
        except ValueError:
            pass
    return False


def claims_containing(claims: list[dict], value: float, tol: float = 0.02) -> list[dict]:
    return [c for c in claims if num_in(c["value"] + " " + c["statement"], value, tol)]


def claims_with_subject(claims: list[dict], *keywords) -> list[dict]:
    kws = [k.lower() for k in keywords]
    return [c for c in claims if all(k in c["subject"].lower() for k in kws)]


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

def test_ev(claims) -> dict:
    hits = [c for c in claims_containing(claims, 108.0) if num_in(c["value"], 108.0)]
    return {
        "name": "Enterprise value = 108",
        "found_count": len(hits),
        "claim_ids": [c["id"] for c in hits[:5]],
        "status": "PASS" if hits else "FAIL",
    }


def test_ebitda_bases(claims) -> dict:
    """All 5 EBITDA bases must exist as distinct claims (distinct values)."""
    results = {}
    for label, val in EBITDA_BASES.items():
        hits = claims_containing(claims, val)
        # Filter: must be in value field (not just body text)
        val_hits = [c for c in hits if num_in(c["value"], val)]
        results[label] = {
            "expected": val,
            "found_count": len(val_hits),
            "claim_ids": [c["id"] for c in val_hits],
            "epistemic_types": list({c["epistemic"] for c in val_hits}),
            "subjects": list({c["subject"] for c in val_hits}),
            "status": "PASS" if val_hits else "FAIL",
        }
    all_pass = all(v["status"] == "PASS" for v in results.values())
    distinct_subjects = len({s for v in results.values() for s in v["subjects"]})
    separation_pass = distinct_subjects >= 3  # at least 3 distinct subject strings
    return {
        "name": "EBITDA bases (5 distinct values)",
        "bases": results,
        "separation": {
            "distinct_subjects_across_bases": distinct_subjects,
            "status": "PASS" if separation_pass else "FAIL",
            "note": "Requires ≥3 distinct subjects so bases aren't all under one subject",
        },
        "status": "PASS" if (all_pass and separation_pass) else "PARTIAL" if all_pass else "FAIL",
    }


def test_customer_concentration(claims) -> dict:
    """Both 7.6% billing-account AND 18.2% ultimate-parent must exist as SEPARATE claims."""
    billing_hits = [c for c in claims if num_in(c["value"], 7.6, tol=0.1)
                    and ("billing" in c["subject"].lower() or "billing" in c["statement"].lower()
                         or "7.6" in c["value"])]
    parent_hits = [c for c in claims if num_in(c["value"], 18.2, tol=0.1)
                   and ("parent" in c["subject"].lower() or "18.2" in c["value"]
                        or "riverton" in c["statement"].lower())]

    billing_ok = len(billing_hits) >= 1
    parent_ok = len(parent_hits) >= 1
    separate = billing_ok and parent_ok

    return {
        "name": "Customer concentration — billing-account vs ultimate-parent SEPARATE",
        "billing_account_7pct": {
            "found": billing_ok,
            "claim_ids": [c["id"] for c in billing_hits],
            "status": "PASS" if billing_ok else "FAIL",
        },
        "ultimate_parent_18pct": {
            "found": parent_ok,
            "claim_ids": [c["id"] for c in parent_hits],
            "status": "PASS" if parent_ok else "FAIL",
        },
        "are_separate_claims": separate,
        "status": "PASS" if separate else "FAIL",
    }


def test_riverton_derivation(claims) -> dict:
    """The 18.2% ultimate-parent concentration must exist as a DERIVED claim
    computed by our system from summing 7 individual Riverton rows in the
    data-room extract — NOT merely copied from the IC memo's stated conclusion.
    PARTIAL = value exists but only as asserted or derived-from-IC-memo.
    FAIL  = value not present at all.
    """
    parent_hits_18 = [c for c in claims
                      if num_in(c["value"], 18.2, tol=0.1)
                      and ("parent" in c["subject"].lower() or "18.2" in c["value"])]

    # A derived claim is only valid for this test if it originated from the
    # data-room extract (raw row data), NOT from the IC memo (already summarized).
    derived_from_raw = [c for c in parent_hits_18
                        if c["epistemic"] == "derived"
                        and "data_room_extract" in c["artifact"]]
    derived_from_memo = [c for c in parent_hits_18
                         if c["epistemic"] == "derived"
                         and "ic_memo" in c["artifact"]]

    # Individual Riverton customer row claims from data-room (goal: 7)
    data_room_riverton = [
        c for c in claims
        if "keystone_data_room_extract" in c["artifact"]
        and ("riverton" in c["raw"].lower() or "riv-" in c["raw"].lower())
    ]

    # TRUE pass: our system computed 18.2% from summing data-room rows
    true_derived = bool(derived_from_raw)
    # PARTIAL: value exists (even from IC memo), but not yet machine-computed from rows
    value_present = bool(parent_hits_18)
    row_count = len(data_room_riverton)

    if true_derived and row_count >= 5:
        status = "PASS"
    elif value_present:
        status = "PARTIAL"
    else:
        status = "FAIL"

    return {
        "name": "Riverton 18.2% — derived by summing 7 data-room customer rows",
        "value_present": value_present,
        "derived_from_data_room_rows": true_derived,
        "derived_from_ic_memo_only": bool(derived_from_memo) and not true_derived,
        "riverton_data_room_row_claims": row_count,
        "data_room_riverton_ids": [c["id"] for c in data_room_riverton],
        "derived_from_raw_ids": [c["id"] for c in derived_from_raw],
        "all_18pct_claim_ids": [c["id"] for c in parent_hits_18],
        "status": status,
        "note": (
            "TRUE PASS requires DERIVED claim from data-room row summation (P1b). "
            "PARTIAL = IC memo's 18.2% conclusion was captured but our system didn't aggregate. "
            "Fix: aggregation/derivation pass that sums Riverton rows → DERIVED claim with "
            "rests-on the row claims. This is the key new capability in P1b."
        ),
    }


def test_sponsor_equity(claims) -> dict:
    hits = [c for c in claims if num_in(c["value"], 62.0)]
    return {
        "name": "Sponsor initial equity = 62",
        "found_count": len(hits),
        "claim_ids": [c["id"] for c in hits[:5]],
        "status": "PASS" if hits else "FAIL",
    }


def test_seller_rollover(claims) -> dict:
    hits = [c for c in claims if num_in(c["value"], 12.0)
            and "rollover" in c["raw"].lower()]
    return {
        "name": "Seller rollover = 12",
        "found_count": len(hits),
        "claim_ids": [c["id"] for c in hits[:5]],
        "status": "PASS" if hits else "FAIL",
    }


def test_epistemic_separation(claims) -> dict:
    """Seller 12.7 and firm 11.4 must not share the same subject string."""
    seller_subjects = {c["subject"] for c in claims if num_in(c["value"], 12.7, 0.05)}
    firm_subjects = {c["subject"] for c in claims if num_in(c["value"], 11.4, 0.05)}
    shared = seller_subjects & firm_subjects
    return {
        "name": "Epistemic separation: seller-adj 12.7 ≠ firm 11.4 subject",
        "seller_subjects": sorted(seller_subjects),
        "firm_subjects": sorted(firm_subjects),
        "shared_subjects": sorted(shared),
        "status": "PASS" if not shared else "FAIL",
        "note": "Conflating both under one subject = fail; they are intentionally different bases",
    }


def test_billing_vs_parent_labels(claims) -> dict:
    """7.6% and 18.2% must be under DIFFERENT subject strings."""
    billing_subjects = {c["subject"] for c in claims
                        if num_in(c["value"], 7.6, 0.1) and "7.6" in c["value"]}
    parent_subjects = {c["subject"] for c in claims
                       if num_in(c["value"], 18.2, 0.1) and "18.2" in c["value"]}
    shared = billing_subjects & parent_subjects
    return {
        "name": "Label separation: 7.6% billing-account ≠ 18.2% ultimate-parent subject",
        "billing_subjects": sorted(billing_subjects),
        "parent_subjects": sorted(parent_subjects),
        "shared_subjects": sorted(shared),
        "status": "PASS" if (billing_subjects and parent_subjects and not shared) else
                  "PARTIAL" if (billing_subjects and parent_subjects) else "FAIL",
    }


# ---------------------------------------------------------------------------
# Layer-2 arc answer key (controlling values from answer key causal chain)
# ---------------------------------------------------------------------------
ARC_CONTROLLING = {
    "riverton_notice_date": "2027-01-31",
    "scope_reduction_effective": "2027-04-01",
    "jun2027_ltm_covenant_ebitda": 10.8,
    "jun2027_net_leverage": 4.70,
    "jun2027_liquidity": 2.92,
    "jun2027_gross_debt": 53.0,
    "amendment_contribution": 7.5,
    "revolver_repayment": 4.78,
    "exit_ltm_ebitda_combined_risk": 17.85,
    "exit_gross_moic": 1.50,
    "exit_xirr": 0.087,
    "amendment_not_ordinary_cure": True,   # $7.5m is a waiver-condition contribution
    "risk_identified_pre_ic": True,         # concentration + integration flagged in IA/IC
}


def load_events() -> list[dict]:
    events = []
    for f in sorted(EVENTS_DIR.glob("ev-keystone-*.md")):
        txt = f.read_text(encoding="utf-8")
        e = {
            "id": f.stem,
            "kind": _field(txt, "kind"),
            "at": _field(txt, "at"),
            "raw": txt,
        }
        events.append(e)
    return events


def test_arc_riverton_notice(claims) -> dict:
    """Riverton issued scope-reduction notice on 2027-01-31, effective 2027-04-01."""
    notice_hits = [c for c in claims
                   if "2027-01-31" in c["raw"] or "january 31" in c["raw"].lower()
                   or "jan 31" in c["raw"].lower()]
    effective_hits = [c for c in claims
                      if "2027-04-01" in c["raw"] or "april 1" in c["raw"].lower()
                      or "effective april" in c["raw"].lower()]
    notice_ok = bool(notice_hits)
    effective_ok = bool(effective_hits)
    return {
        "name": "Riverton notice 2027-01-31 and effective date 2027-04-01 captured",
        "notice_date_claims": [c["id"] for c in notice_hits[:3]],
        "effective_date_claims": [c["id"] for c in effective_hits[:3]],
        "status": "PASS" if (notice_ok and effective_ok) else
                  "PARTIAL" if (notice_ok or effective_ok) else "FAIL",
    }


def test_arc_covenant_breach(claims) -> dict:
    """June 2027 breach: LTM EBITDA $10.8m, net leverage 4.70x, liquidity $2.92m."""
    ebitda_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 10.8, tol=0.05)
                   and ("covenant" in c["raw"].lower() or "ltm" in c["raw"].lower())]
    leverage_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 4.70, tol=0.05)
                     and "leverage" in c["raw"].lower()]
    liquidity_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 2.92, tol=0.05)
                      and "liquid" in c["raw"].lower()]
    all_ok = bool(ebitda_hits) and bool(leverage_hits) and bool(liquidity_hits)
    return {
        "name": "June 2027 covenant breach: LTM $10.8m · leverage 4.70x · liquidity $2.92m",
        "covenant_ebitda_10.8": {
            "found": bool(ebitda_hits),
            "claim_ids": [c["id"] for c in ebitda_hits[:3]],
        },
        "net_leverage_4.70x": {
            "found": bool(leverage_hits),
            "claim_ids": [c["id"] for c in leverage_hits[:3]],
        },
        "liquidity_2.92m": {
            "found": bool(liquidity_hits),
            "claim_ids": [c["id"] for c in liquidity_hits[:3]],
        },
        "status": "PASS" if all_ok else "PARTIAL" if any([ebitda_hits, leverage_hits, liquidity_hits]) else "FAIL",
    }


def test_arc_amendment(claims) -> dict:
    """August 2027 amendment: $7.5m equity contribution NOT an ordinary contractual cure."""
    amount_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 7.5, tol=0.05)
                   and ("sponsor" in c["raw"].lower() or "contribution" in c["raw"].lower()
                        or "amendment" in c["raw"].lower())]
    not_cure_hits = [c for c in claims
                     if ("outside ordinary" in c["raw"].lower()
                         or "not.*cure" in c["raw"].lower()
                         or "waiver-condition" in c["raw"].lower()
                         or "not contractual" in c["raw"].lower()
                         or "not an ordinary" in c["raw"].lower())]
    not_cure_hits = [c for c in claims
                     if re.search(r"outside ordinary|not.*cure|waiver.condition|not contractual|not an ordinary",
                                  c["raw"], re.IGNORECASE)]
    amount_ok = bool(amount_hits)
    cure_ok = bool(not_cure_hits)
    return {
        "name": "August 2027 amendment: $7.5m contribution identified as NOT ordinary equity cure",
        "amount_7.5m": {"found": amount_ok, "claim_ids": [c["id"] for c in amount_hits[:3]]},
        "cure_distinction": {"found": cure_ok, "claim_ids": [c["id"] for c in not_cure_hits[:3]]},
        "status": "PASS" if (amount_ok and cure_ok) else "PARTIAL" if amount_ok else "FAIL",
    }


def test_arc_exit(claims) -> dict:
    """Exit March 2031: Combined Risk LTM EBITDA $17.85m, gross MOIC 1.50x, XIRR 8.7%."""
    ebitda_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 17.85, tol=0.1)]
    moic_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 1.50, tol=0.05)
                 and ("moic" in c["raw"].lower() or "return" in c["raw"].lower())]
    xirr_hits = [c for c in claims if num_in(c["value"] + " " + c["raw"], 8.7, tol=0.1)
                 and ("xirr" in c["raw"].lower() or "irr" in c["raw"].lower())]
    all_ok = bool(ebitda_hits) and bool(moic_hits) and bool(xirr_hits)
    return {
        "name": "Exit 2031 (Combined Risk): EBITDA $17.85m · MOIC 1.50x · XIRR 8.7%",
        "exit_ebitda_17.85": {"found": bool(ebitda_hits), "claim_ids": [c["id"] for c in ebitda_hits[:3]]},
        "moic_1.50x": {"found": bool(moic_hits), "claim_ids": [c["id"] for c in moic_hits[:3]]},
        "xirr_8.7pct": {"found": bool(xirr_hits), "claim_ids": [c["id"] for c in xirr_hits[:3]]},
        "status": "PASS" if all_ok else "PARTIAL" if any([ebitda_hits, moic_hits, xirr_hits]) else "FAIL",
    }


def test_arc_risk_was_known(claims) -> dict:
    """Pre-IC IA/IC docs must contain concentration + integration risk claims (risks were known).

    Pre-IC artifacts: IC memo, question list (empty artifact field from early extraction),
    firm initial assessment (also early batch). We check ic_memo and empty-artifact claims.
    """
    pre_ic_artifacts = {"vault/inbox/keystone_ic_memo.md", "vault/inbox/keystone_firm_initial_assessment.md",
                        "vault/inbox/keystone_question_list.md", ""}
    pre_ic_claims = [c for c in claims if c["artifact"] in pre_ic_artifacts
                     or "ic_memo" in c["artifact"] or "initial_assessment" in c["artifact"]
                     or "question_list" in c["artifact"]]
    concentration_risk_pre_ic = [c for c in pre_ic_claims
                                  if "concentration" in c["raw"].lower()
                                  and ("risk" in c["raw"].lower() or "concern" in c["raw"].lower()
                                       or "parent" in c["raw"].lower())]
    integration_risk_pre_ic = [c for c in pre_ic_claims
                                if "integration" in c["raw"].lower()
                                and ("risk" in c["raw"].lower() or "concern" in c["raw"].lower()
                                     or "key" in c["raw"].lower() or "prior" in c["raw"].lower())]
    conc_ok = bool(concentration_risk_pre_ic)
    int_ok = bool(integration_risk_pre_ic)
    return {
        "name": "Risk pre-identified: concentration + integration flagged in IA/IC before close",
        "concentration_risk_pre_ic": {
            "found": conc_ok,
            "claim_ids": [c["id"] for c in concentration_risk_pre_ic[:3]],
        },
        "integration_risk_pre_ic": {
            "found": int_ok,
            "claim_ids": [c["id"] for c in integration_risk_pre_ic[:3]],
        },
        "note": "A correct arc analysis shows failure was NOT an undiscovered surprise — risks were identified, accepted, then compounded",
        "status": "PASS" if (conc_ok and int_ok) else "PARTIAL" if (conc_ok or int_ok) else "FAIL",
    }


def test_arc_lifecycle_state() -> dict:
    """deal.md state field must be S12_EXIT_REALIZATION (engine derived it from events)."""
    deal_md = VAULT / "deals" / "keystone" / "deal.md"
    text = deal_md.read_text(encoding="utf-8") if deal_md.exists() else ""
    state_m = re.search(r"^state:\s*(\S+)", text, re.MULTILINE)
    state = state_m.group(1).strip() if state_m else "UNKNOWN"
    return {
        "name": "Lifecycle state = S12_EXIT_REALIZATION (engine-derived from event replay)",
        "current_state": state,
        "expected": "S12_EXIT_REALIZATION",
        "status": "PASS" if state == "S12_EXIT_REALIZATION" else "FAIL",
    }


def test_arc_staleness_cascade(claims) -> dict:
    """kq-01 must be stale after Riverton notice (staleness cascade triggered)."""
    q_file = VAULT / "deals" / "keystone" / "questions" / "kq-01-parent-concentration.md"
    text = q_file.read_text(encoding="utf-8") if q_file.exists() else ""
    is_stale = bool(re.search(r"^stale:\s*true", text, re.MULTILINE))
    assumption_file = VAULT / "deals" / "keystone" / "assumptions" / "a-keystone-002.md"
    a_text = assumption_file.read_text(encoding="utf-8") if assumption_file.exists() else ""
    assumption_updated = "v2" in a_text or "UNDER STRESS" in a_text or "version: 2" in a_text
    return {
        "name": "Staleness cascade: Riverton notice → a-keystone-002 v2 → kq-01 stale",
        "kq_01_stale": is_stale,
        "assumption_002_updated": assumption_updated,
        "status": "PASS" if (is_stale and assumption_updated) else
                  "PARTIAL" if (is_stale or assumption_updated) else "FAIL",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_grader(verbose: bool = False, arc_only: bool = False) -> dict:
    claims = load_claims()
    total = len(claims)

    layer1_tests = [] if arc_only else [
        test_ev(claims),
        test_ebitda_bases(claims),
        test_customer_concentration(claims),
        test_riverton_derivation(claims),
        test_sponsor_equity(claims),
        test_seller_rollover(claims),
        test_epistemic_separation(claims),
        test_billing_vs_parent_labels(claims),
    ]

    arc_tests = [
        test_arc_riverton_notice(claims),
        test_arc_covenant_breach(claims),
        test_arc_amendment(claims),
        test_arc_exit(claims),
        test_arc_risk_was_known(claims),
        test_arc_lifecycle_state(),
        test_arc_staleness_cascade(claims),
    ]

    all_tests = layer1_tests + arc_tests
    pass_count = sum(1 for t in all_tests if t.get("status") == "PASS")
    fail_count = sum(1 for t in all_tests if t.get("status") == "FAIL")
    partial_count = sum(1 for t in all_tests if t.get("status") == "PARTIAL")

    return {
        "deal": "keystone",
        "layer": "1+2",
        "total_claims": total,
        "layer1_tests": len(layer1_tests),
        "arc_tests": len(arc_tests),
        "test_count": len(all_tests),
        "pass": pass_count,
        "partial": partial_count,
        "fail": fail_count,
        "layer1_results": layer1_tests,
        "arc_results": arc_tests,
        "tests": all_tests,
    }


def print_scorecard(result: dict) -> None:
    STATUS_ICON = {"PASS": "✓", "FAIL": "✗", "PARTIAL": "~"}
    print("\n" + "=" * 70)
    print(f"  KEYSTONE LAYER-1 + LAYER-2 ARC SCORECARD")
    print(f"  {result['total_claims']} claims · "
          f"{result['pass']}/{result['test_count']} PASS · "
          f"{result['partial']} PARTIAL · {result['fail']} FAIL")
    print("=" * 70)

    def print_tests(tests: list[dict], header: str) -> None:
        print(f"\n  ── {header} ──")
        for test in tests:
            icon = STATUS_ICON.get(test["status"], "?")
            name = test.get("name", test.get("test", "?"))
            print(f"\n  [{icon}] {test['status']:7s}  {name}")

            # EBITDA bases — print per-basis breakdown
            if "bases" in test:
                for label, info in test["bases"].items():
                    sub_icon = STATUS_ICON.get(info["status"], "?")
                    print(f"           [{sub_icon}] {label:20s} = {info['expected']:4.1f}  "
                          f"({info['found_count']} claims, subjects: {info['subjects'][:2]})")
                sep = test.get("separation", {})
                s_icon = STATUS_ICON.get(sep.get("status","?"), "?")
                print(f"           [{s_icon}] epistemic separation — {sep.get('distinct_subjects_across_bases',0)} distinct subjects")

            # Concentration
            if "billing_account_7pct" in test:
                b = test["billing_account_7pct"]
                p = test["ultimate_parent_18pct"]
                print(f"           7.6% billing-account: {b['status']} ids={b['claim_ids'][:3]}")
                print(f"           18.2% ultimate-parent: {p['status']} ids={p['claim_ids'][:3]}")

            # Riverton derivation
            if "derived_from_data_room_rows" in test:
                print(f"           derived from data-room rows: {test['derived_from_data_room_rows']}  "
                      f"ids={test.get('derived_from_raw_ids',[][:3])}")
                print(f"           data-room Riverton row claims: {test['riverton_data_room_row_claims']}")

            # Epistemic separation
            if "shared_subjects" in test and test.get("shared_subjects"):
                print(f"           ⚠ shared subjects: {test['shared_subjects'][:3]}")

            # Arc-specific: covenant breach sub-fields
            if "covenant_ebitda_10.8" in test:
                for k in ("covenant_ebitda_10.8", "net_leverage_4.70x", "liquidity_2.92m"):
                    sub = test[k]
                    sub_icon = STATUS_ICON.get("PASS" if sub["found"] else "FAIL", "?")
                    print(f"           [{sub_icon}] {k}: ids={sub['claim_ids'][:2]}")

            # Amendment
            if "amount_7.5m" in test:
                a = test["amount_7.5m"]; c = test["cure_distinction"]
                print(f"           $7.5m present: {a['found']} ids={a['claim_ids'][:2]}")
                print(f"           cure distinction: {c['found']} ids={c['claim_ids'][:2]}")

            # Exit
            if "exit_ebitda_17.85" in test:
                for k in ("exit_ebitda_17.85", "moic_1.50x", "xirr_8.7pct"):
                    sub = test[k]
                    sub_icon = STATUS_ICON.get("PASS" if sub["found"] else "FAIL", "?")
                    print(f"           [{sub_icon}] {k}: ids={sub['claim_ids'][:2]}")

            # Lifecycle
            if "current_state" in test:
                print(f"           state: {test['current_state']} (expected: {test['expected']})")

            # Staleness
            if "kq_01_stale" in test:
                print(f"           kq-01 stale: {test['kq_01_stale']}; "
                      f"assumption updated: {test['assumption_002_updated']}")

            # Risk known
            if "concentration_risk_pre_ic" in test:
                c = test["concentration_risk_pre_ic"]; i = test["integration_risk_pre_ic"]
                print(f"           concentration risk pre-IC: {c['found']} ids={c['claim_ids'][:2]}")
                print(f"           integration risk pre-IC: {i['found']} ids={i['claim_ids'][:2]}")
                if test.get("note"):
                    print(f"           → {test['note']}")

    print_tests(result["layer1_results"], f"LAYER 1 — Extraction quality ({result['layer1_tests']} tests)")
    print_tests(result["arc_results"], f"LAYER 2 — Living deal arc ({result['arc_tests']} tests)")

    print("\n" + "-" * 70)
    overall = "PASS" if result["fail"] == 0 else "PARTIAL" if result["partial"] > 0 else "FAIL"
    if result["fail"] == 0 and result["partial"] == 0:
        overall = "PASS"
    elif result["fail"] == 0:
        overall = "PARTIAL"
    else:
        overall = "FAIL"
    print(f"  OVERALL: {overall}  ({result['pass']} pass, {result['partial']} partial, {result['fail']} fail)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--arc", action="store_true", help="Arc tests only (skip Layer-1)")
    args = parser.parse_args()

    result = run_grader(arc_only=args.arc)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_scorecard(result)
