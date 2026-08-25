#!/usr/bin/env python3
"""
V7 Compiler — keystone workbook mapping → execution_graph_v7.json

Reads formula constants and data from keystone_model.py (the workbook
mapping layer) and emits the V7 execution format that Anto's runtime
consumes.

Does NOT modify Current or Approved. Produces a raw V7 extraction that
must be admitted through the admission process.

Usage:
    .venv/bin/python3 tools/compiler_v7.py
    .venv/bin/python3 tools/compiler_v7.py --out /tmp/v7_test.json
    .venv/bin/python3 tools/compiler_v7.py --validate  # also runs test_v7.py

Two-layer architecture
----------------------
  Layer 1 (LBO Grammar): reusable buyout concept schema — which node
    types CAN exist in a leveraged buyout (Revenue, EBITDA, Leverage, etc.)
  Layer 2 (Workbook mapping): Keystone-specific formulas with real cell
    references, actual data vectors, and deal-specific identity

This compiler merges both layers into the V7 execution format. The
grammar provides the structural skeleton; the workbook mapping provides
the computably-grounded values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.keystone_model import (
    DealInputs,
    PERIODS,
    SB_REVENUE, SB_EBITDA, SB_DSO, SB_WIP, SB_PREPAIDS, SB_AP,
    SB_ACCRUALS, SB_DEFERRED, SB_CAPEX, SB_SEASONALITY, SB_SOFR,
    SB_PPA, SB_CASH_FLOOR, SB_COV_LIMIT, SB_GROSS_MARGIN,
    MIP_VESTING,
)

OUT_PATH = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"

# Canonical "as of" date for this extraction
AS_OF_KNOWN_AT = "2026-08-24T00:00:00Z"

# Workbook source reference prefix
WB = "keystone_lbo_model_working.xlsx"


# ── Helper ────────────────────────────────────────────────────────────────────

def _hash_content(obj: dict | list) -> str:
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── Model nodes ───────────────────────────────────────────────────────────────

def _build_model_nodes(inp: DealInputs) -> dict:
    """
    Full model node inventory.

    Node spec fields:
      id              : stable MN-* identifier
      label           : human label
      computational_form: INPUT | DERIVED | SCC_MEMBER | CONTROL | SOLVER_OUTPUT
      unit            : MM_USD | RATIO | DAYS | PERCENT | BOOL | DATED_CASH_FLOW_VECTOR
      period          : ISO date, range, or OPENING | QUARTERLY_20 | EXIT | ANNUAL
      perimeter       : Alderstone | Alderstone_standalone | deal_level
      epistemic_class : asserted | observed | derived | attested
      formula_id      : ref to formulas[] (absent for pure INPUT nodes)
      value_current   : current underwriting value (scalar or tag)
      effective_date  : ISO date or range
      known_at        : ISO-8601 timestamp when the fact was acquired (or COVERAGE_LIMIT)
      coverage_limits : list of explicit gaps in coverage
      workbook_ref    : cell reference in the workbook
      directed_deps   : list of MN-* this node depends on (NOT the effect set)
    """
    nodes: dict = {}

    # ── Static deal inputs (from Inputs sheet) ─────────────────────────────

    nodes["MN-EV"] = {
        "id": "MN-EV",
        "label": "Enterprise Value (entry)",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "Alderstone",
        "epistemic_class": "attested",
        "value_current": inp.enterprise_value,
        "workbook_ref": f"{WB}:Inputs!B3",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-SELLER-NET-DEBT-AND-DEBT-LIKE-IT"] = {
        "id": "MN-SELLER-NET-DEBT-AND-DEBT-LIKE-IT",
        "label": "Seller Net Debt + Debt-Like Items",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "Alderstone",
        "epistemic_class": "attested",
        "value_current": inp.seller_net_debt,
        "workbook_ref": f"{WB}:Inputs!B4",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-ROLLOVER"] = {
        "id": "MN-ROLLOVER",
        "label": "Seller Rollover Equity",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "attested",
        "value_current": inp.seller_rollover,
        "workbook_ref": f"{WB}:Inputs!B7",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-SPONSOR-EQUITY"] = {
        "id": "MN-SPONSOR-EQUITY",
        "label": "Sponsor Equity Invested",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "attested",
        "value_current": inp.sponsor_equity,
        "workbook_ref": f"{WB}:Inputs!B8 / S&U_Opening!E21",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": ["MN-EV", "MN-DEBT", "MN-ROLLOVER",
                          "MN-CHECK-SOURCES-USES"],
        "formula_id": "F-SOURCES-USES-EQUITY",
        "coverage_limits": [],
    }

    nodes["MN-DEBT"] = {
        "id": "MN-DEBT",
        "label": "Opening Term Loan Balance",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "attested",
        "value_current": inp.term_loan_opening,
        "workbook_ref": f"{WB}:Inputs!B9",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-OPENING-CASH"] = {
        "id": "MN-OPENING-CASH",
        "label": "Opening Cash Balance",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "Alderstone",
        "epistemic_class": "attested",
        "value_current": inp.opening_cash,
        "workbook_ref": f"{WB}:Inputs!B10",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-FIRM-EBITDA"] = {
        "id": "MN-FIRM-EBITDA",
        "label": "Firm Underwriting EBITDA (opening, annual)",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "2025-12-31",
        "effective_date": "2025-12-31",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "attested",
        "value_current": inp.firm_ebitda_opening,
        "workbook_ref": f"{WB}:Inputs!B11",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,   # INPUT seeded by CP-EBITDA-FIRM
        "coverage_limits": [],
        "note": "Valuation + internal leverage metric; DIFFERENT from MN-COV-EBITDA",
    }

    nodes["MN-COV-EBITDA"] = {
        "id": "MN-COV-EBITDA",
        "label": "Covenant EBITDA (opening, credit agreement definition)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": "2025-12-31",
        "effective_date": "2025-12-31",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "attested",
        "value_current": inp.covenant_ebitda_opening,
        "workbook_ref": f"{WB}:Inputs!B12",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": ["MN-FIRM-EBITDA", "MN-INTEGRATION-COST-ADJ",
                          "MN-RELATED-PARTY-RENT-NORM"],
        "formula_id": "F-COV-EBITDA-OPENING",
        "coverage_limits": [],
        "note": "Credit-agreement only; includes addbacks not in MN-FIRM-EBITDA",
    }

    nodes["MN-NWC"] = {
        "id": "MN-NWC",
        "label": "Net Working Capital Target",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "Alderstone",
        "epistemic_class": "attested",
        "value_current": inp.nwc_target,
        "workbook_ref": f"{WB}:Inputs!B14",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-INTEGRATION-COST-ADJ"] = {
        "id": "MN-INTEGRATION-COST-ADJ",
        "label": "Integration Cost Add-back (EBITDA normalization)",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "2025-12-31",
        "effective_date": "2025-12-31",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "attested",
        "value_current": 0.0,
        "workbook_ref": f"{WB}:Scenario_Drivers!C8:V8 (one-time charges)",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-RELATED-PARTY-RENT-NORM"] = {
        "id": "MN-RELATED-PARTY-RENT-NORM",
        "label": "Related Party Rent Normalization",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": "2025-12-31",
        "effective_date": "2025-12-31",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "attested",
        "value_current": 0.0,
        "workbook_ref": f"{WB}:Scenario_Drivers!C9:V9 (covenant addbacks)",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-CONCENTRATION"] = {
        "id": "MN-CONCENTRATION",
        "label": "Customer / Geographic Concentration",
        "computational_form": "INPUT",
        "unit": "RATIO",
        "period": "2025-12-31",
        "effective_date": "2025-12-31",
        "perimeter": "Alderstone",
        "epistemic_class": "attested",
        "value_current": None,
        "workbook_ref": None,
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [
            "COVERAGE_LIMIT: concentration metrics not modelled in workbook; "
            "qualitative risk factor only"
        ],
    }

    # ── Per-quarter computed nodes ─────────────────────────────────────────

    nodes["MN-REVENUE"] = {
        "id": "MN-REVENUE",
        "label": "Quarterly Revenue (Standalone Base, 20 periods)",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "asserted",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "vector_values": list(zip(PERIODS, SB_REVENUE)),
        "workbook_ref": f"{WB}:Scenario_Drivers!C5:V5",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,   # INPUT seeded by CP-REVENUE
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-FIRM-EBITDA"] = {
        "id": "MN-QUARTERLY-FIRM-EBITDA",
        "label": "Quarterly Firm EBITDA (Standalone Base, 20 periods)",
        "computational_form": "INPUT",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "asserted",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "vector_values": list(zip(PERIODS, SB_EBITDA)),
        "workbook_ref": f"{WB}:Scenario_Drivers!C7:V7",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": ["MN-REVENUE"],
        "formula_id": "F-QUARTERLY-FIRM-EBITDA",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-COV-EBITDA"] = {
        "id": "MN-QUARTERLY-COV-EBITDA",
        "label": "Quarterly Covenant EBITDA (Standalone Base, 20 periods)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C14:V14",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": ["MN-QUARTERLY-FIRM-EBITDA",
                          "MN-INTEGRATION-COST-ADJ",
                          "MN-RELATED-PARTY-RENT-NORM"],
        "formula_id": "F-QUARTERLY-COV-EBITDA",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-INTEREST"] = {
        "id": "MN-QUARTERLY-INTEREST",
        "label": "Quarterly Cash Interest Expense (SCC member)",
        "computational_form": "SCC_MEMBER",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C22:V22",
        "known_at": None,
        "directed_deps": ["MN-DEBT", "MN-QUARTERLY-REVOLVER",
                          "MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-DDTL"],
        "formula_id": "F-INTEREST-EXPENSE",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-CFO"] = {
        "id": "MN-QUARTERLY-CFO",
        "label": "Quarterly Cash Flow from Operations (SCC member)",
        "computational_form": "SCC_MEMBER",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C52:V52",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-FIRM-EBITDA", "MN-NWC",
                          "MN-QUARTERLY-INTEREST", "MN-REVENUE"],
        "formula_id": "F-CFO",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-REVOLVER"] = {
        "id": "MN-QUARTERLY-REVOLVER",
        "label": "Quarterly Revolver Balance (SCC member)",
        "computational_form": "SCC_MEMBER",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C78:V78",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-CFO", "MN-OPENING-CASH"],
        "formula_id": "F-REVOLVER-DRAW-REPAY",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-TERM-LOAN"] = {
        "id": "MN-QUARTERLY-TERM-LOAN",
        "label": "Quarterly Term Loan Balance (end-of-period)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C76:V76",
        "known_at": None,
        "directed_deps": ["MN-DEBT", "MN-QUARTERLY-CFO"],
        "formula_id": "F-TERM-LOAN-AMORT",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-DDTL"] = {
        "id": "MN-QUARTERLY-DDTL",
        "label": "Quarterly DDTL Balance",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C77:V77",
        "known_at": None,
        "directed_deps": ["MN-DEBT"],
        "formula_id": "F-DDTL-BALANCE",
        "coverage_limits": [],
    }

    nodes["MN-QUARTERLY-CASH"] = {
        "id": "MN-QUARTERLY-CASH",
        "label": "Quarterly Ending Cash Balance",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base!C67:V67",
        "known_at": None,
        "directed_deps": ["MN-OPENING-CASH", "MN-QUARTERLY-CFO",
                          "MN-QUARTERLY-REVOLVER"],
        "formula_id": "F-ENDING-CASH",
        "coverage_limits": [],
    }

    nodes["MN-NET-LEVERAGE"] = {
        "id": "MN-NET-LEVERAGE",
        "label": "Net Leverage (covenant definition, LTM)",
        "computational_form": "DERIVED",
        "unit": "RATIO",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": "DATED_CASH_FLOW_VECTOR",
        "workbook_ref": f"{WB}:SB_Base (covenant leverage rows)",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-DDTL",
                          "MN-QUARTERLY-REVOLVER", "MN-QUARTERLY-CASH",
                          "MN-QUARTERLY-COV-EBITDA"],
        "formula_id": "F-NET-LEVERAGE",
        "coverage_limits": [],
    }

    nodes["MN-DEBT-CAPACITY"] = {
        "id": "MN-DEBT-CAPACITY",
        "label": "Debt Capacity (max debt from covenant + financing grid)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": "OPENING",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Inputs (leverage and covenant terms)",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": ["MN-NET-LEVERAGE", "MN-COV-EBITDA"],
        "formula_id": "F-DEBT-CAPACITY",
        "coverage_limits": [
            "COVERAGE_LIMIT: financing grid step-down rule (>15% single-parent "
            "exposure) not available in current policy file; treatment is conservative "
            "hold until policy_owner confirms step-down threshold"
        ],
    }

    # ── Exit / returns nodes ────────────────────────────────────────────────

    nodes["MN-EXIT-EV"] = {
        "id": "MN-EXIT-EV",
        "label": "Exit Enterprise Value (LTM EBITDA × exit multiple)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!E4",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-FIRM-EBITDA", "MN-BASE-EXIT-MULT"],
        "formula_id": "F-EXIT-EV",
        "coverage_limits": [],
    }

    nodes["MN-EXIT-NET-DEBT"] = {
        "id": "MN-EXIT-NET-DEBT",
        "label": "Exit Net Debt (term + ddtl + revolver − cash at exit)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!F4",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-DDTL",
                          "MN-QUARTERLY-REVOLVER", "MN-QUARTERLY-CASH"],
        "formula_id": "F-EXIT-NET-DEBT",
        "coverage_limits": [],
    }

    nodes["MN-EXIT-EQUITY"] = {
        "id": "MN-EXIT-EQUITY",
        "label": "Exit Equity Value (exit_ev − exit_net_debt)",
        "computational_form": "DERIVED",
        "unit": "MM_USD",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!G4",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EV", "MN-EXIT-NET-DEBT"],
        "formula_id": "F-EXIT-EQUITY",
        "coverage_limits": [],
    }

    # ── Scenario return nodes (existing IDs preserved) ─────────────────────

    nodes["MN-BASE-EXIT-MULT"] = {
        "id": "MN-BASE-EXIT-MULT",
        "label": "Standalone Base Exit Multiple",
        "computational_form": "INPUT",
        "unit": "RATIO",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "asserted",
        "value_current": 9.0,
        "workbook_ref": f"{WB}:Inputs!B46",
        "known_at": "2026-03-10T00:00:00Z",
        "directed_deps": [],
        "formula_id": None,
        "coverage_limits": [],
    }

    nodes["MN-BASE-MOIC"] = {
        "id": "MN-BASE-MOIC",
        "label": "Standalone Base Gross MOIC",
        "computational_form": "DERIVED",
        "unit": "RATIO",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!K4",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-MOIC",
        "coverage_limits": [],
    }

    nodes["MN-BASE-IRR"] = {
        "id": "MN-BASE-IRR",
        "label": "Standalone Base Gross XIRR (ACT/365)",
        "computational_form": "DERIVED",
        "unit": "PERCENT",
        "period": "2026-03-10/2031-03-31",
        "effective_date": "2026-03-10/2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!L4",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-XIRR",
        "coverage_limits": [],
    }

    nodes["MN-DOWN-MOIC"] = {
        "id": "MN-DOWN-MOIC",
        "label": "Standalone Downside Gross MOIC",
        "computational_form": "DERIVED",
        "unit": "RATIO",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!K5",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-MOIC",
        "coverage_limits": [],
    }

    nodes["MN-DOWN-IRR"] = {
        "id": "MN-DOWN-IRR",
        "label": "Standalone Downside Gross XIRR",
        "computational_form": "DERIVED",
        "unit": "PERCENT",
        "period": "2026-03-10/2031-03-31",
        "effective_date": "2026-03-10/2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!L5",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-XIRR",
        "coverage_limits": [],
    }

    nodes["MN-ACQ-MOIC"] = {
        "id": "MN-ACQ-MOIC",
        "label": "Acquisition Base Gross MOIC",
        "computational_form": "DERIVED",
        "unit": "RATIO",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!K7",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-MOIC",
        "coverage_limits": [],
    }

    nodes["MN-ACQ-IRR"] = {
        "id": "MN-ACQ-IRR",
        "label": "Acquisition Base Gross XIRR",
        "computational_form": "DERIVED",
        "unit": "PERCENT",
        "period": "2026-03-10/2031-03-31",
        "effective_date": "2026-03-10/2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!L7",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-XIRR",
        "coverage_limits": [],
    }

    nodes["MN-COMBINED-RISK-MOIC"] = {
        "id": "MN-COMBINED-RISK-MOIC",
        "label": "Combined Risk Gross MOIC",
        "computational_form": "DERIVED",
        "unit": "RATIO",
        "period": "2031-03-31",
        "effective_date": "2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!K8",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-MOIC",
        "coverage_limits": [],
    }

    nodes["MN-COMBINED-RISK-IRR"] = {
        "id": "MN-COMBINED-RISK-IRR",
        "label": "Combined Risk Gross XIRR",
        "computational_form": "DERIVED",
        "unit": "PERCENT",
        "period": "2026-03-10/2031-03-31",
        "effective_date": "2026-03-10/2031-03-31",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns!L8",
        "known_at": None,
        "directed_deps": ["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        "formula_id": "F-GROSS-XIRR",
        "coverage_limits": [],
    }

    nodes["MN-SUPPORTED-PRICE"] = {
        "id": "MN-SUPPORTED-PRICE",
        "label": "Supported Entry Price (max EV s.t. IRR ≥ 14% & MOIC ≥ 2.0×)",
        "computational_form": "SOLVER_OUTPUT",
        "unit": "MM_USD",
        "period": "2026-03-10",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Ownership_Returns (goal-seek on EV)",
        "known_at": None,
        "directed_deps": ["MN-BASE-MOIC", "MN-BASE-IRR"],
        "formula_id": "F-SUPPORTED-PRICE-SOLVER",
        "coverage_limits": [],
    }

    # ── Check / control nodes ──────────────────────────────────────────────

    nodes["MN-CHECK-SOURCES-USES"] = {
        "id": "MN-CHECK-SOURCES-USES",
        "label": "Sources & Uses Balance Check (closing)",
        "computational_form": "CONTROL",
        "unit": "BOOL",
        "period": "2026-03-10",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:S&U_Opening (balance check)",
        "known_at": None,
        "directed_deps": ["MN-EV", "MN-DEBT", "MN-ROLLOVER",
                          "MN-SPONSOR-EQUITY"],
        "formula_id": "F-CHECK-SOURCES-USES",
        "coverage_limits": [],
    }

    nodes["MN-CHECK-OPENING-BS"] = {
        "id": "MN-CHECK-OPENING-BS",
        "label": "Opening Balance Sheet Check",
        "computational_form": "CONTROL",
        "unit": "BOOL",
        "period": "2026-03-10",
        "effective_date": "2026-03-10",
        "perimeter": "deal_level",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:S&U_Opening!BS_check",
        "known_at": None,
        "directed_deps": ["MN-DEBT", "MN-OPENING-CASH",
                          "MN-SPONSOR-EQUITY", "MN-ROLLOVER"],
        "formula_id": "F-CHECK-OPENING-BS",
        "coverage_limits": [],
    }

    nodes["MN-CHECK-SB-BASE-BS"] = {
        "id": "MN-CHECK-SB-BASE-BS",
        "label": "Standalone Base Quarterly Balance Sheet Check",
        "computational_form": "CONTROL",
        "unit": "BOOL",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:SB_Base (BS check rows)",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN",
                          "MN-QUARTERLY-REVOLVER"],
        "formula_id": "F-CHECK-QUARTERLY-BS",
        "coverage_limits": [],
    }

    nodes["MN-CHECK-SB-DOWN-BS"] = {
        "id": "MN-CHECK-SB-DOWN-BS",
        "label": "Standalone Downside Quarterly Balance Sheet Check",
        "computational_form": "CONTROL",
        "unit": "BOOL",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:SB_Down (BS check rows)",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN",
                          "MN-QUARTERLY-REVOLVER"],
        "formula_id": "F-CHECK-QUARTERLY-BS",
        "coverage_limits": [],
    }

    nodes["MN-CHECK-ACQ-BASE-BS"] = {
        "id": "MN-CHECK-ACQ-BASE-BS",
        "label": "Acquisition Base Quarterly Balance Sheet Check",
        "computational_form": "CONTROL",
        "unit": "BOOL",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Acq_Base (BS check rows)",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN",
                          "MN-QUARTERLY-REVOLVER"],
        "formula_id": "F-CHECK-QUARTERLY-BS",
        "coverage_limits": [],
    }

    nodes["MN-CHECK-COMBINED-BS"] = {
        "id": "MN-CHECK-COMBINED-BS",
        "label": "Combined Risk Quarterly Balance Sheet Check",
        "computational_form": "CONTROL",
        "unit": "BOOL",
        "period": f"{PERIODS[0]}/{PERIODS[-1]}",
        "effective_date": f"{PERIODS[0]}/{PERIODS[-1]}",
        "perimeter": "Alderstone_standalone",
        "epistemic_class": "derived",
        "value_current": None,
        "workbook_ref": f"{WB}:Combined_Risk (BS check rows)",
        "known_at": None,
        "directed_deps": ["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN",
                          "MN-QUARTERLY-REVOLVER"],
        "formula_id": "F-CHECK-QUARTERLY-BS",
        "coverage_limits": [],
    }

    # ── Scenario driver leaf nodes (scenario inputs) ────────────────────────
    # Listed for edge completeness; not fully expanded here

    for nid, label, val, cell in [
        ("MN-BASE-GROWTH",          "Standalone Base Revenue Growth",     None, "Scenario_Drivers (row 5 YoY)"),
        ("MN-BASE-EBITDA-MARGIN",   "Standalone Base EBITDA Margin",      None, "Scenario_Drivers!C7 / C5"),
        ("MN-BASE-DSO",             "Standalone Base DSO",                SB_DSO[0], "Scenario_Drivers!C10:V10"),
        ("MN-BASE-WIP",             "Standalone Base WIP / Revenue",      SB_WIP[0], "Scenario_Drivers!C11:V11"),
        ("MN-BASE-CAPEX",           "Standalone Base CapEx / Revenue",    SB_CAPEX[0], "Scenario_Drivers!C16:V16"),
        ("MN-BASE-EXIT-MULT",       None, None, None),  # defined above
        ("MN-DOWN-GROWTH",          "Standalone Downside Revenue Growth",  None, "Scenario_Drivers (down row)"),
        ("MN-DOWN-EBITDA-MARGIN",   "Standalone Downside EBITDA Margin",  None, "Scenario_Drivers (down row)"),
        ("MN-DOWN-DSO",             "Standalone Downside DSO",            None, "Scenario_Drivers (down row)"),
        ("MN-DOWN-WIP",             "Standalone Downside WIP",            None, "Scenario_Drivers (down row)"),
        ("MN-DOWN-CAPEX",           "Standalone Downside CapEx",          None, "Scenario_Drivers (down row)"),
        ("MN-STANDALONE-DOWNSIDE-EXIT-MULTIPLE", "Standalone Downside Exit Multiple", 7.5, "Inputs!B47"),
        ("MN-STANDALONE-UPSIDE-PLATFORM-GROWTH","Standalone Upside Platform Growth",None,"Scenario_Drivers (up row)"),
        ("MN-STANDALONE-UPSIDE-FIRM-EBITDA-MARGIN","Standalone Upside EBITDA Margin",None,"Scenario_Drivers (up row)"),
        ("MN-STANDALONE-UPSIDE-DSO", "Standalone Upside DSO", None, "Scenario_Drivers (up row)"),
        ("MN-STANDALONE-UPSIDE-WIP-REVENUE","Standalone Upside WIP",None,"Scenario_Drivers (up row)"),
        ("MN-STANDALONE-UPSIDE-CAPEX-REVENUE","Standalone Upside CapEx",None,"Scenario_Drivers (up row)"),
        ("MN-STANDALONE-UPSIDE-EXIT-MULTIPLE","Standalone Upside Exit Multiple",10.0,"Inputs!B48"),
        ("MN-ACQUISITION-BASE-PLATFORM-GROWTH","Acq Base Platform Growth",None,"Scenario_Drivers (acq row)"),
        ("MN-ACQUISITION-BASE-FIRM-EBITDA-MARGIN","Acq Base EBITDA Margin",None,"Scenario_Drivers (acq row)"),
        ("MN-ACQUISITION-BASE-DSO","Acq Base DSO",None,"Scenario_Drivers (acq row)"),
        ("MN-ACQUISITION-BASE-WIP-REVENUE","Acq Base WIP",None,"Scenario_Drivers (acq row)"),
        ("MN-ACQUISITION-BASE-CAPEX-REVENUE","Acq Base CapEx",None,"Scenario_Drivers (acq row)"),
        ("MN-ACQUISITION-BASE-EXIT-MULTIPLE","Acq Base Exit Multiple",9.5,"Inputs!B49"),
        ("MN-COMBINED-RISK-GROWTH","Combined Risk Growth",None,"Scenario_Drivers (combined row)"),
        ("MN-COMBINED-RISK-EBITDA-MARGIN","Combined Risk EBITDA Margin",None,"Scenario_Drivers (combined row)"),
        ("MN-COMBINED-RISK-DSO","Combined Risk DSO",None,"Scenario_Drivers (combined row)"),
        ("MN-COMBINED-RISK-WIP","Combined Risk WIP",None,"Scenario_Drivers (combined row)"),
        ("MN-COMBINED-RISK-CAPEX-REVENUE","Combined Risk CapEx",None,"Scenario_Drivers (combined row)"),
        ("MN-COMBINED-RISK-EXIT-MULT","Combined Risk Exit Multiple",8.0,"Inputs!B50"),
        ("MN-COMBINED-RISK-INTEGRATION-SPEND","Combined Risk Integration Spend",None,"Scenario_Drivers (combined row)"),
        ("MN-SELLER-EBITDA","Seller Stated EBITDA",None,"CIM / management accounts"),
        ("MN-QOE-EBITDA","QoE Adjusted EBITDA",None,"QoE report"),
    ]:
        if nid in nodes:
            continue  # already defined above
        nodes[nid] = {
            "id": nid,
            "label": label or nid,
            "computational_form": "INPUT",
            "unit": "MM_USD" if "EBITDA" in nid or "MULTIPLE" in nid.upper() or "GROWTH" in nid else "RATIO",
            "period": "2025-12-31",
            "effective_date": "2025-12-31",
            "perimeter": "Alderstone_standalone",
            "epistemic_class": "asserted",
            "value_current": val,
            "workbook_ref": f"{WB}:{cell}" if cell else None,
            "known_at": "2026-03-10T00:00:00Z",
            "directed_deps": [],
            "formula_id": None,
            "coverage_limits": [] if val is not None else [
                "COVERAGE_LIMIT: value not yet bound from workbook; "
                f"scenario node {nid} requires workbook extraction pass"
            ],
        }

    return nodes


# ── Directed edges ────────────────────────────────────────────────────────────

def _build_directed_edges() -> list[dict]:
    """
    Financial chain edges with runtime contract.

    Contract:
      edge_id                 : stable E-* identifier
      from_model_node_id      : source node (produces value)
      to_model_node_id        : target node (consumes value)
      formula_or_function_ref : formula_id or function name
      control_ids             : gates that block this edge on FAIL
      scenario                : which scenario this edge is active in (None = all)
    """
    edges = []

    def _e(eid, src, tgt, formula, controls=None, scenario=None):
        edges.append({
            "edge_id": eid,
            "from_model_node_id": src,
            "to_model_node_id": tgt,
            "formula_or_function_ref": formula,
            "control_ids": controls or [],
            "scenario": scenario,
        })

    # ── Operating model chain ─────────────────────────────────────────────
    _e("E-EBITDA-QUARTERLY",  "MN-FIRM-EBITDA",           "MN-QUARTERLY-FIRM-EBITDA", "F-QUARTERLY-FIRM-EBITDA")
    # MN-FIRM-EBITDA and MN-REVENUE are INPUT nodes seeded by their Case
    # Positions rather than computed from a workbook cell, so they carry no
    # formula edge. Revenue never produced opening EBITDA in any case.
    _e("E-EBITDA-COV-EBITDA", "MN-QUARTERLY-FIRM-EBITDA", "MN-QUARTERLY-COV-EBITDA",  "F-QUARTERLY-COV-EBITDA")
    _e("E-EBITDA-LEVERAGE",   "MN-FIRM-EBITDA",           "MN-NET-LEVERAGE",          "F-NET-LEVERAGE")
    _e("E-QEBITDA-LEVERAGE",  "MN-QUARTERLY-COV-EBITDA",  "MN-NET-LEVERAGE",          "F-NET-LEVERAGE")

    # Debt schedule
    _e("E-DEBT-TERM",         "MN-DEBT",                  "MN-QUARTERLY-TERM-LOAN",   "F-TERM-LOAN-AMORT")
    _e("E-DEBT-DDTL",         "MN-DEBT",                  "MN-QUARTERLY-DDTL",        "F-DDTL-BALANCE")

    # SCC: Interest ↔ CFO ↔ Revolver
    _e("E-SCC-INT-REV",       "MN-QUARTERLY-INTEREST",    "MN-QUARTERLY-REVOLVER",    "F-REVOLVER-DRAW-REPAY")
    _e("E-SCC-REV-INT",       "MN-QUARTERLY-REVOLVER",    "MN-QUARTERLY-INTEREST",    "F-INTEREST-EXPENSE")
    _e("E-SCC-CFO-REV",       "MN-QUARTERLY-CFO",         "MN-QUARTERLY-REVOLVER",    "F-REVOLVER-DRAW-REPAY")
    _e("E-SCC-INT-CFO",       "MN-QUARTERLY-INTEREST",    "MN-QUARTERLY-CFO",         "F-CFO")
    _e("E-EBITDA-CFO",        "MN-QUARTERLY-FIRM-EBITDA", "MN-QUARTERLY-CFO",         "F-CFO")
    _e("E-NWC-CFO",           "MN-NWC",                   "MN-QUARTERLY-CFO",         "F-CFO")
    _e("E-REV-CFO",           "MN-REVENUE",               "MN-QUARTERLY-CFO",         "F-CFO")

    # Cash balance
    _e("E-CFO-CASH",          "MN-QUARTERLY-CFO",         "MN-QUARTERLY-CASH",        "F-ENDING-CASH")
    _e("E-REV-CASH",          "MN-QUARTERLY-REVOLVER",    "MN-QUARTERLY-CASH",        "F-ENDING-CASH")
    _e("E-OPENING-CASH",      "MN-OPENING-CASH",          "MN-QUARTERLY-CASH",        "F-ENDING-CASH")

    # Leverage → debt capacity → S&U → sponsor equity
    _e("E-LEV-DEBTCAP",       "MN-NET-LEVERAGE",          "MN-DEBT-CAPACITY",         "F-DEBT-CAPACITY")
    _e("E-DEBTCAP-SU",        "MN-DEBT-CAPACITY",         "MN-CHECK-SOURCES-USES",    "F-CHECK-SOURCES-USES")
    _e("E-SU-EQUITY",         "MN-CHECK-SOURCES-USES",    "MN-SPONSOR-EQUITY",        "F-SOURCES-USES-EQUITY",
       controls=["CTRL-SOURCES-USES-BALANCE"])

    # Exit
    _e("E-EBITDA-EXITV",      "MN-QUARTERLY-FIRM-EBITDA", "MN-EXIT-EV",               "F-EXIT-EV")
    _e("E-FIRM-EBITDA-EXITV", "MN-FIRM-EBITDA",           "MN-EXIT-EV",               "F-EXIT-EV")
    _e("E-MULT-EXITV",        "MN-BASE-EXIT-MULT",        "MN-EXIT-EV",               "F-EXIT-EV")
    _e("E-EXITV-NETDEBT",     "MN-EXIT-EV",               "MN-EXIT-NET-DEBT",         "F-EXIT-NET-DEBT")
    _e("E-CASH-NETDEBT",      "MN-QUARTERLY-CASH",        "MN-EXIT-NET-DEBT",         "F-EXIT-NET-DEBT")
    _e("E-TERM-NETDEBT",      "MN-QUARTERLY-TERM-LOAN",   "MN-EXIT-NET-DEBT",         "F-EXIT-NET-DEBT")
    _e("E-EXITV-EQUITY",      "MN-EXIT-EV",               "MN-EXIT-EQUITY",           "F-EXIT-EQUITY")
    _e("E-NETDEBT-EQUITY",    "MN-EXIT-NET-DEBT",         "MN-EXIT-EQUITY",           "F-EXIT-EQUITY")

    # Returns
    _e("E-EQUITY-MOIC",       "MN-EXIT-EQUITY",           "MN-BASE-MOIC",             "F-GROSS-MOIC")
    _e("E-EQUITY-IRR",        "MN-EXIT-EQUITY",           "MN-BASE-IRR",              "F-GROSS-XIRR")
    _e("E-EQUITY-DOWN-MOIC",  "MN-EXIT-EQUITY",           "MN-DOWN-MOIC",             "F-GROSS-MOIC")
    _e("E-EQUITY-DOWN-IRR",   "MN-EXIT-EQUITY",           "MN-DOWN-IRR",              "F-GROSS-XIRR")
    _e("E-EQUITY-ACQ-MOIC",   "MN-EXIT-EQUITY",           "MN-ACQ-MOIC",              "F-GROSS-MOIC")
    _e("E-EQUITY-ACQ-IRR",    "MN-EXIT-EQUITY",           "MN-ACQ-IRR",               "F-GROSS-XIRR")
    _e("E-EQUITY-COMB-MOIC",  "MN-EXIT-EQUITY",           "MN-COMBINED-RISK-MOIC",    "F-GROSS-MOIC")
    _e("E-EQUITY-COMB-IRR",   "MN-EXIT-EQUITY",           "MN-COMBINED-RISK-IRR",     "F-GROSS-XIRR")

    # Supported Price (inverse solve)
    _e("E-MOIC-SUPPRICE",     "MN-BASE-MOIC",             "MN-SUPPORTED-PRICE",       "F-SUPPORTED-PRICE-SOLVER")
    _e("E-IRR-SUPPRICE",      "MN-BASE-IRR",              "MN-SUPPORTED-PRICE",       "F-SUPPORTED-PRICE-SOLVER")

    return edges


# ── Formulas ──────────────────────────────────────────────────────────────────

def _build_formulas(inp: DealInputs) -> list[dict]:
    """
    Computably-grounded formula objects.

    Each formula has:
      formula_id                  : stable F-* identifier
      description                 : one-line
      input_ids                   : list of MN-* node IDs consumed
      output_id                   : MN-* node ID produced
      expression_or_function_ref  : Python expression or function name
      evaluation_type             : WORKBOOK_READ | ARITHMETIC | PYTHON_FUNCTION |
                                    DATED_VECTOR_ARITHMETIC | SCC_MEMBER | SOLVER
      workbook_cell_ref           : source cell(s) in the workbook
      unit                        : unit of the output
      period                      : applicable period(s)
      perimeter                   : applicable perimeter
      scenario                    : applicable scenario (None = all)
      source_ref                  : code location
      variable_binding            : {var_name: node_id} for arithmetic formulas
      tolerances                  : {abs: ..., rel: ...} where applicable
    """
    F = []

    def _f(**kw):
        F.append(kw)

    # Revenue (direct workbook read)

    # Opening Firm EBITDA (direct workbook read)

    # Quarterly Firm EBITDA (workbook read — scenario drivers)
    _f(
        formula_id="F-QUARTERLY-FIRM-EBITDA",
        description="Quarterly firm EBITDA from Scenario_Drivers!C7:V7",
        # Quarterly firm EBITDA is the annual figure spread across four
        # quarters — exactly what bridge_v7 already computes. Stating it as an
        # executable expression lets a correction to the annual node propagate,
        # instead of re-reading a frozen workbook range.
        input_ids=["MN-FIRM-EBITDA"],
        output_id="MN-QUARTERLY-FIRM-EBITDA",
        expression_or_function_ref="firm_ebitda / 4",
        operand_bindings={"firm_ebitda": "MN-FIRM-EBITDA"},
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Scenario_Drivers!C7:V7",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="Alderstone_standalone",
        scenario="standalone_base",
        source_ref="keystone_model.py:SB_EBITDA",
        variable_binding={},
        tolerances={},
    )

    # Opening Covenant EBITDA
    _f(
        formula_id="F-COV-EBITDA-OPENING",
        description="Opening covenant EBITDA = firm_ebitda + rent_norm + integration_addback",
        input_ids=["MN-FIRM-EBITDA", "MN-RELATED-PARTY-RENT-NORM",
                   "MN-INTEGRATION-COST-ADJ"],
        output_id="MN-COV-EBITDA",
        expression_or_function_ref=(
            "firm_ebitda + related_party_rent_norm + integration_cost_adj"
        ),
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Inputs!B12",
        unit="MM_USD",
        period="2025-12-31",
        perimeter="Alderstone_standalone",
        scenario=None,
        source_ref="keystone_model.py:DealInputs.covenant_ebitda_opening",
        variable_binding={
            "firm_ebitda":           "MN-FIRM-EBITDA",
            "related_party_rent_norm":"MN-RELATED-PARTY-RENT-NORM",
            "integration_cost_adj":  "MN-INTEGRATION-COST-ADJ",
        },
        tolerances={"abs": 0.001},
    )

    # Quarterly Covenant EBITDA
    _f(
        formula_id="F-QUARTERLY-COV-EBITDA",
        description=(
            "covenant_ebitda[q] = firm_ebitda[q] - one_time_charges[q] + covenant_addbacks[q]"
            " (SB_Base!C14)"
        ),
        input_ids=["MN-QUARTERLY-FIRM-EBITDA", "MN-INTEGRATION-COST-ADJ",
                   "MN-RELATED-PARTY-RENT-NORM"],
        output_id="MN-QUARTERLY-COV-EBITDA",
        expression_or_function_ref=(
            "firm_ebitda_q - one_time_charges_q + covenant_addbacks_q"
        ),
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base!C14:V14",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="Alderstone_standalone",
        scenario=None,
        source_ref="keystone_model.py:_run_quarter():L623-624",
        variable_binding={
            "firm_ebitda_q":      "MN-QUARTERLY-FIRM-EBITDA",
            "one_time_charges_q": "MN-INTEGRATION-COST-ADJ",
            "covenant_addbacks_q":"MN-RELATED-PARTY-RENT-NORM",
        },
        tolerances={"abs": 0.001},
    )

    # Interest expense (SCC member)
    _f(
        formula_id="F-INTEREST-EXPENSE",
        description=(
            "Quarterly cash interest — term/DDTL avg-balance × (SOFR + spread)/4 "
            "+ revolver_beg × (SOFR + spread)/4 + unused fees. SB_Base!C22/D22."
        ),
        input_ids=["MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-DDTL",
                   "MN-QUARTERLY-REVOLVER", "MN-DEBT"],
        output_id="MN-QUARTERLY-INTEREST",
        expression_or_function_ref="_interest_expense",
        evaluation_type="PYTHON_FUNCTION",
        workbook_cell_ref=f"{WB}:SB_Base!C22:V22",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_interest_expense():L396-451",
        variable_binding={
            "term_beg":     "MN-QUARTERLY-TERM-LOAN[prior]",
            "rev_beg":      "MN-QUARTERLY-REVOLVER[prior]",
            "ddtl_beg":     "MN-QUARTERLY-DDTL[prior]",
            "sofr":         "Scenario_Drivers!C33:V33",
            "cash_beg":     "MN-QUARTERLY-CASH[prior]",
            "term_spread":  "Inputs!B23",
            "revolver_spread": "Inputs!B24",
            "ddtl_spread":  "Inputs!B25",
            "sofr_floor":   "Inputs!B26",
        },
        tolerances={"abs": 1e-6},
        note=(
            "Cyclic dependency: rev_beg is the beginning-of-period revolver "
            "balance. Converged within SCC-CASHFLOW-INTEREST-REVOLVER."
        ),
    )

    # CFO
    _f(
        formula_id="F-CFO",
        description=(
            "Cash flow from operations = net_income + D&A + fee_amort "
            "+ deferred_tax_adj − delta_nwc. SB_Base!C52."
        ),
        input_ids=["MN-QUARTERLY-FIRM-EBITDA", "MN-QUARTERLY-INTEREST",
                   "MN-NWC", "MN-REVENUE"],
        output_id="MN-QUARTERLY-CFO",
        expression_or_function_ref=(
            "net_income + total_da + fee_amort + deferred_tax_adj - delta_nwc"
        ),
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base!C52:V52",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_run_quarter():L683-686",
        variable_binding={
            "net_income":      "F-NET-INCOME",
            "total_da":        "F-TOTAL-DA",
            "fee_amort":       "Inputs!B31 / 24",
            "deferred_tax_adj":"F-DEFERRED-TAX-ADJ",
            "delta_nwc":       "F-NWC-BALANCE",
        },
        tolerances={"abs": 1e-6},
        note="Cyclic via interest. Resolved within SCC-CASHFLOW-INTEREST-REVOLVER.",
    )

    # Revolver draw/repay (SCC member — rule switch)
    _f(
        formula_id="F-REVOLVER-DRAW-REPAY",
        description=(
            "Revolver draw/repay — IF-chain: forced_target, repay_all, "
            "cash_shortfall, cash_surplus. SB_Base!C59/D59, C60/D60."
        ),
        input_ids=["MN-QUARTERLY-CFO", "MN-QUARTERLY-CASH",
                   "MN-QUARTERLY-DDTL"],
        output_id="MN-QUARTERLY-REVOLVER",
        expression_or_function_ref="_revolver_draw_repay",
        evaluation_type="PYTHON_FUNCTION",
        workbook_cell_ref=f"{WB}:SB_Base!C59:V59,C60:V60",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_revolver_draw_repay():L454-500",
        variable_binding={
            "prior_cash":    "MN-QUARTERLY-CASH[prior]",
            "prior_rev":     "MN-QUARTERLY-REVOLVER[prior]",
            "cfo":           "MN-QUARTERLY-CFO",
            "cfi":           "-total_capex",
            "cff_ex_rev":    "sponsor_contrib + term_amort + ddtl_amort",
            "cash_floor":    "Scenario_Drivers!C29:V29",
            "forced_target": "Scenario_Drivers!C30:V30",
            "repay_all":     "Scenario_Drivers!C31:V31",
        },
        tolerances={"abs": 1e-4},
    )

    # Term loan amortization
    _f(
        formula_id="F-TERM-LOAN-AMORT",
        description=(
            "end_term = max(0, max(0, beg_term - scheduled_amort) + ecf_sweep). "
            "SB_Base!C76."
        ),
        input_ids=["MN-DEBT", "MN-QUARTERLY-CFO"],
        output_id="MN-QUARTERLY-TERM-LOAN",
        expression_or_function_ref=(
            "max(0, max(0, beg_term - min(term_amort_q, beg_term)) + ecf_sweep)"
        ),
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base!C76:V76",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_run_quarter():L755",
        variable_binding={
            "beg_term":     "MN-QUARTERLY-TERM-LOAN[prior]",
            "term_amort_q": "min(inp.quarterly_term_amort, beg_term)",
            "ecf_sweep":    "F-ECF-SWEEP",
        },
        tolerances={"abs": 1e-6},
    )

    # DDTL balance
    _f(
        formula_id="F-DDTL-BALANCE",
        description="end_ddtl = max(0, beg_ddtl + draw_q + amort_q). SB_Base!C77.",
        input_ids=["MN-DEBT"],
        output_id="MN-QUARTERLY-DDTL",
        expression_or_function_ref="max(0, beg_ddtl + ddtl_draw_q + ddtl_amort_q)",
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base!C77:V77",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_run_quarter():L653",
        variable_binding={
            "beg_ddtl":     "MN-QUARTERLY-DDTL[prior]",
            "ddtl_draw_q":  "Scenario_Drivers!C25:V25",
            "ddtl_amort_q": "min(0.015, beg_ddtl) if beg_ddtl > 0 else 0",
        },
        tolerances={"abs": 1e-6},
    )

    # Ending cash
    _f(
        formula_id="F-ENDING-CASH",
        description="end_cash = beg_cash + cfo + cfi + cff. SB_Base!C67.",
        input_ids=["MN-OPENING-CASH", "MN-QUARTERLY-CFO", "MN-QUARTERLY-REVOLVER"],
        output_id="MN-QUARTERLY-CASH",
        expression_or_function_ref="beg_cash + cfo + cfi + cff",
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base!C67:V67",
        unit="MM_USD",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_run_quarter():L764",
        variable_binding={
            "beg_cash": "MN-QUARTERLY-CASH[prior]",
            "cfo":      "MN-QUARTERLY-CFO",
            "cfi":      "-total_capex",
            "cff":      "sponsor_contrib + ddtl_draw + term_amort + ddtl_amort + rev_draw + rev_repay + ecf_sweep",
        },
        tolerances={"abs": 1e-6},
    )

    # Net leverage (covenant)
    _f(
        formula_id="F-NET-LEVERAGE",
        description=(
            "net_leverage = (term + ddtl + revolver - min(cash, netting_cap)) "
            "/ ltm_covenant_ebitda. Covenant definition."
        ),
        input_ids=["MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-DDTL",
                   "MN-QUARTERLY-REVOLVER", "MN-QUARTERLY-CASH",
                   "MN-QUARTERLY-COV-EBITDA", "MN-FIRM-EBITDA"],
        output_id="MN-NET-LEVERAGE",
        expression_or_function_ref=(
            "(term + ddtl + revolver - min(cash, eligible_cash_netting)) "
            "/ ltm_4q_covenant_ebitda"
        ),
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base (covenant leverage rows)",
        unit="RATIO",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_run_quarter():L768-770",
        variable_binding={
            "term":                   "MN-QUARTERLY-TERM-LOAN",
            "ddtl":                   "MN-QUARTERLY-DDTL",
            "revolver":               "MN-QUARTERLY-REVOLVER",
            "cash":                   "MN-QUARTERLY-CASH",
            "eligible_cash_netting":  "Inputs!B19",
            "ltm_4q_covenant_ebitda": "sum(MN-QUARTERLY-COV-EBITDA[-3:q])",
        },
        tolerances={"abs": 1e-6},
    )

    # Debt capacity
    _f(
        formula_id="F-DEBT-CAPACITY",
        description=(
            "Max opening debt = covenant_ebitda × max_leverage_multiple. "
            "Max leverage from credit agreement; financing grid step-down "
            "rule (>15% single-parent) is a coverage limit."
        ),
        input_ids=["MN-COV-EBITDA", "MN-NET-LEVERAGE"],
        output_id="MN-DEBT-CAPACITY",
        expression_or_function_ref="covenant_ebitda * max_leverage_at_close",
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Inputs (leverage covenant terms)",
        unit="MM_USD",
        period="2026-03-10",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:DealInputs (term loan + covenant terms)",
        variable_binding={
            "covenant_ebitda":        "MN-COV-EBITDA",
            "max_leverage_at_close":  "SB_COV_LIMIT[0]",
        },
        tolerances={"abs": 0.1},
        note=(
            "COVERAGE_LIMIT: financing grid step-down rule (>15% single-parent "
            "exposure) not modelled; requires policy_owner confirmation"
        ),
    )

    # S&U balance → sponsor equity
    _f(
        formula_id="F-SOURCES-USES-EQUITY",
        description=(
            "sponsor_equity = EV - term_loan - seller_rollover - "
            "opening_cash + financing_fees + buyer_tx_expenses"
        ),
        input_ids=["MN-EV", "MN-DEBT", "MN-ROLLOVER", "MN-OPENING-CASH"],
        output_id="MN-SPONSOR-EQUITY",
        expression_or_function_ref=(
            "ev - term_loan - seller_rollover + financing_fees + buyer_tx_expenses"
        ),
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:S&U_Opening!E21",
        unit="MM_USD",
        period="2026-03-10",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:DealInputs.sponsor_equity",
        variable_binding={
            "ev":              "MN-EV",
            "term_loan":       "MN-DEBT",
            "seller_rollover": "MN-ROLLOVER",
            "financing_fees":  "Inputs!B31",
            "buyer_tx_expenses":"Inputs!B32",
        },
        tolerances={"abs": 0.001},
    )

    # Exit EV
    _f(
        formula_id="F-EXIT-EV",
        description="exit_ev = ltm_4q_ebitda × exit_multiple. OR!E4.",
        input_ids=["MN-QUARTERLY-FIRM-EBITDA", "MN-BASE-EXIT-MULT"],
        output_id="MN-EXIT-EV",
        expression_or_function_ref="ltm_4q_firm_ebitda * exit_multiple",
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Ownership_Returns!E4",
        unit="MM_USD",
        period="2031-03-31",
        perimeter="Alderstone_standalone",
        scenario="standalone_base",
        source_ref="keystone_model.py:_compute_returns():L875",
        variable_binding={
            "ltm_4q_firm_ebitda": "sum(MN-QUARTERLY-FIRM-EBITDA[-4:])",
            "exit_multiple":      "MN-BASE-EXIT-MULT",
        },
        tolerances={"abs": 0.01},
    )

    # Exit net debt
    _f(
        formula_id="F-EXIT-NET-DEBT",
        description=(
            "exit_net_debt = term_loan_exit + ddtl_exit + revolver_exit - cash_exit. "
            "OR!F4."
        ),
        input_ids=["MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-DDTL",
                   "MN-QUARTERLY-REVOLVER", "MN-QUARTERLY-CASH"],
        output_id="MN-EXIT-NET-DEBT",
        expression_or_function_ref=(
            "term_exit + ddtl_exit + revolver_exit - cash_exit"
        ),
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Ownership_Returns!F4",
        unit="MM_USD",
        period="2031-03-31",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_compute_returns():L876",
        variable_binding={
            "term_exit":     "MN-QUARTERLY-TERM-LOAN[period=2031-03-31]",
            "ddtl_exit":     "MN-QUARTERLY-DDTL[period=2031-03-31]",
            "revolver_exit": "MN-QUARTERLY-REVOLVER[period=2031-03-31]",
            "cash_exit":     "MN-QUARTERLY-CASH[period=2031-03-31]",
        },
        tolerances={"abs": 0.01},
    )

    # Exit equity
    _f(
        formula_id="F-EXIT-EQUITY",
        description="exit_equity = exit_ev - exit_net_debt. OR!G4.",
        input_ids=["MN-EXIT-EV", "MN-EXIT-NET-DEBT"],
        output_id="MN-EXIT-EQUITY",
        expression_or_function_ref="exit_ev - exit_net_debt",
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Ownership_Returns!G4",
        unit="MM_USD",
        period="2031-03-31",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:_compute_returns():L877",
        variable_binding={
            "exit_ev":      "MN-EXIT-EV",
            "exit_net_debt":"MN-EXIT-NET-DEBT",
        },
        tolerances={"abs": 0.01},
    )

    # Gross MOIC
    _f(
        formula_id="F-GROSS-MOIC",
        description=(
            "gross_moic = (exit_equity × (1 - mip_pct) × sponsor_ownership_pct) "
            "/ sponsor_invested. OR!K4."
        ),
        input_ids=["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        output_id="MN-BASE-MOIC",
        expression_or_function_ref=(
            "(exit_equity * (1 - mip_vested) * sponsor_pre_mip_pct) / sponsor_invested"
        ),
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:Ownership_Returns!K4",
        unit="RATIO",
        period="2031-03-31",
        perimeter="deal_level",
        scenario="standalone_base",
        source_ref="keystone_model.py:_compute_returns():L884-887",
        variable_binding={
            "exit_equity":        "MN-EXIT-EQUITY",
            "mip_vested":         f"{MIP_VESTING['standalone_base']}",
            "sponsor_pre_mip_pct":f"{DealInputs().mip_base_pct:.6f}",
            "sponsor_invested":   "MN-SPONSOR-EQUITY",
        },
        tolerances={"abs": 0.001},
    )

    # Gross XIRR (ACT/365)
    _f(
        formula_id="F-GROSS-XIRR",
        description=(
            "gross_xirr = XIRR([-sponsor_invested, 0..., +sponsor_proceeds], "
            "[entry_date, ..., exit_date]). Newton-Raphson, ACT/365. OR!L4."
        ),
        input_ids=["MN-EXIT-EQUITY", "MN-SPONSOR-EQUITY"],
        output_id="MN-BASE-IRR",
        expression_or_function_ref="_xirr",
        evaluation_type="PYTHON_FUNCTION",
        workbook_cell_ref=f"{WB}:Ownership_Returns!L4",
        unit="PERCENT",
        period="2026-03-10/2031-03-31",
        perimeter="deal_level",
        scenario="standalone_base",
        source_ref="keystone_model.py:_xirr():L826-856",
        variable_binding={
            "cashflows":   "[-sponsor_invested, 0 × (n-1), +sponsor_proceeds]",
            "dates_iso":   "[entry_date] + [PERIODS] + [exit_date]",
            "day_count":   "ACT/365",
        },
        tolerances={"abs": 1e-8, "max_iterations": 100},
    )

    # Supported Price solver formula stub (actual solve is in inverse_solver_config)
    _f(
        formula_id="F-SUPPORTED-PRICE-SOLVER",
        description=(
            "Finds max entry EV s.t. IRR ≥ 14% and MOIC ≥ 2.0×. "
            "Implemented as bisection over run_lbo(). "
            "Binding constraint reported in output."
        ),
        input_ids=["MN-BASE-MOIC", "MN-BASE-IRR", "MN-EV"],
        output_id="MN-SUPPORTED-PRICE",
        expression_or_function_ref="INV-SUPPORTED-PRICE",
        evaluation_type="SOLVER",
        workbook_cell_ref=f"{WB}:Ownership_Returns (goal-seek on EV)",
        unit="MM_USD",
        period="2026-03-10",
        perimeter="deal_level",
        scenario="standalone_base",
        source_ref="keystone_model.py:run_lbo() + _compute_returns()",
        variable_binding={},
        tolerances={"abs": 0.01},
    )

    # Check formulas
    _f(
        formula_id="F-CHECK-SOURCES-USES",
        description="Sources = Uses check at closing",
        input_ids=["MN-EV", "MN-DEBT", "MN-ROLLOVER", "MN-SPONSOR-EQUITY",
                   "MN-OPENING-CASH"],
        output_id="MN-CHECK-SOURCES-USES",
        # Written as a single evaluable expression: the previous form carried a
        # pseudo-code "where" clause, which is not parseable Python and made the
        # whole bundle unrunnable once control nodes entered the Current graph.
        expression_or_function_ref=(
            "abs((ev + opening_cash) - (debt + rollover + sponsor_equity)) < 0.001"
        ),
        operand_bindings={
            "ev": "MN-EV",
            "opening_cash": "MN-OPENING-CASH",
            "debt": "MN-DEBT",
            "rollover": "MN-ROLLOVER",
            "sponsor_equity": "MN-SPONSOR-EQUITY",
        },
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:S&U_Opening (balance check)",
        unit="BOOL",
        period="2026-03-10",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:DealInputs (S&U identity)",
        variable_binding={
            "ev":              "MN-EV",
            "term_loan":       "MN-DEBT",
            "rollover":        "MN-ROLLOVER",
            "sponsor_equity":  "MN-SPONSOR-EQUITY",
            "financing_fees":  "Inputs!B31",
            "buyer_tx_expenses":"Inputs!B32",
        },
        tolerances={"abs": 0.001},
    )

    _f(
        formula_id="F-CHECK-OPENING-BS",
        description="Opening balance sheet assets = liabilities + equity",
        input_ids=["MN-DEBT", "MN-OPENING-CASH", "MN-SPONSOR-EQUITY", "MN-ROLLOVER"],
        output_id="MN-CHECK-OPENING-BS",
        expression_or_function_ref=(
            "abs(total_assets - (total_liabilities + total_equity)) < 0.001"
        ),
        evaluation_type="ARITHMETIC",
        workbook_cell_ref=f"{WB}:S&U_Opening!BS_check",
        unit="BOOL",
        period="2026-03-10",
        perimeter="deal_level",
        scenario=None,
        source_ref="keystone_model.py:DealInputs.opening_equity_book",
        variable_binding={
            "total_assets":     "goodwill + fixed_assets + cash + nwc",
            "total_liabilities":"term_loan + ddtl",
            "total_equity":     "sponsor_equity + rollover",
        },
        tolerances={"abs": 0.001},
    )

    _f(
        formula_id="F-CHECK-QUARTERLY-BS",
        description="Per-quarter balance sheet check: assets = liabilities + equity",
        input_ids=["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN",
                   "MN-QUARTERLY-REVOLVER"],
        output_id="MN-CHECK-SB-BASE-BS",
        expression_or_function_ref="abs(assets - liabilities - equity) < 0.001",
        evaluation_type="DATED_VECTOR_ARITHMETIC",
        workbook_cell_ref=f"{WB}:SB_Base (BS check rows)",
        unit="BOOL",
        period=f"{PERIODS[0]}/{PERIODS[-1]}",
        perimeter="Alderstone_standalone",
        scenario=None,
        source_ref="keystone_model.py:LBOResult.bs_check_passes",
        variable_binding={
            "assets":      "cash + ar + wip + prepaids + fixed_assets + goodwill",
            "liabilities": "term_loan + ddtl + revolver + ap + accruals + deferred_rev",
            "equity":      "opening_equity + cumulative_net_income",
        },
        tolerances={"abs": 0.001},
    )

    return F


# ── Rule switches ─────────────────────────────────────────────────────────────

def _build_rule_switches() -> list[dict]:
    return [
        {
            "rule_switch_id": "RS-REVOLVER-DRAW",
            "description": (
                "Determines revolver draw/repay each quarter based on cash position "
                "relative to floor and optional forced target. SB_Base!C59/D59, C60/D60."
            ),
            "selector_input_ids": [
                "MN-QUARTERLY-CFO", "MN-QUARTERLY-CASH",
                "Scenario_Drivers!C29:V29",  # cash_floor
                "Scenario_Drivers!C30:V30",  # forced_target (-1 = auto)
                "Scenario_Drivers!C31:V31",  # repay_all flag
            ],
            "branches": [
                {
                    "branch_id": "RS-REV-FORCED",
                    "condition": "forced_revolver_target >= 0",
                    "output_expression": (
                        "draw = max(0, forced_target - prior_rev); "
                        "repay = -max(0, prior_rev - forced_target)"
                    ),
                },
                {
                    "branch_id": "RS-REV-REPAY-ALL",
                    "condition": "repay_all == 1",
                    "output_expression": "draw = 0; repay = -prior_rev",
                    "priority": 2,
                },
                {
                    "branch_id": "RS-REV-AUTO-SURPLUS",
                    "condition": "pre_cash >= cash_floor AND repay_all == 0 AND forced_target < 0",
                    "output_expression": (
                        "draw = 0; "
                        "repay = -min(prior_rev, pre_cash - cash_floor)"
                    ),
                },
                {
                    "branch_id": "RS-REV-AUTO-DRAW",
                    "condition": "pre_cash < cash_floor AND forced_target < 0",
                    "output_expression": (
                        "draw = min(cash_floor - pre_cash, "
                        "revolver_commitment - prior_rev); "
                        "repay = 0"
                    ),
                },
            ],
            "dependent_ids": ["MN-QUARTERLY-REVOLVER", "MN-QUARTERLY-CASH"],
            "source_ref": "keystone_model.py:_revolver_draw_repay():L454-500",
            "workbook_ref": f"{WB}:SB_Base!C59:V59 / C60:V60",
            "no_branch_behavior": "RAISE_UNDEFINED",
            "multi_branch_behavior": (
                "RS-REV-FORCED takes priority; then RS-REV-REPAY-ALL; "
                "then RS-REV-AUTO-SURPLUS / RS-REV-AUTO-DRAW are mutually exclusive"
            ),
        },
        {
            "rule_switch_id": "RS-ECF-SWEEP",
            "description": (
                "Annual excess cash flow sweep — fires Dec-31 quarters only. "
                "Rate determined by net leverage tier. SB_Base!E63/I63/M63/Q63/U63."
            ),
            "selector_input_ids": [
                "MN-NET-LEVERAGE",
                "MN-QUARTERLY-CASH",
                "Scenario_Drivers!C29:V29",  # cash_floor
            ],
            "branches": [
                {
                    "branch_id": "RS-ECF-NOT-DEC",
                    "condition": "quarter_month NOT IN {Dec}",
                    "output_expression": "ecf_sweep = 0",
                },
                {
                    "branch_id": "RS-ECF-HIGH-LEV",
                    "condition": "quarter_month IN {Dec} AND net_leverage > 3.0",
                    "output_expression": (
                        "ecf_sweep = -min(remaining_term, free_cash) * 0.50"
                    ),
                },
                {
                    "branch_id": "RS-ECF-MID-LEV",
                    "condition": "quarter_month IN {Dec} AND 2.5 < net_leverage <= 3.0",
                    "output_expression": (
                        "ecf_sweep = -min(remaining_term, free_cash) * 0.25"
                    ),
                },
                {
                    "branch_id": "RS-ECF-LOW-LEV",
                    "condition": "quarter_month IN {Dec} AND net_leverage <= 2.5",
                    "output_expression": "ecf_sweep = 0",
                },
            ],
            "dependent_ids": ["MN-QUARTERLY-TERM-LOAN", "MN-QUARTERLY-CASH"],
            "source_ref": "keystone_model.py:_ecf_sweep():L503-555",
            "workbook_ref": f"{WB}:SB_Base!E63,I63,M63,Q63,U63",
            "no_branch_behavior": "RAISE_UNDEFINED",
            "multi_branch_behavior": "RAISE_AMBIGUOUS (branches are mutually exclusive by construction)",
        },
        {
            "rule_switch_id": "RS-163J-TAX",
            "description": (
                "163(j) interest deduction cap — limits deductible interest to "
                "30% of reported EBITDA; excess carries forward. SB_Base!C116."
            ),
            "selector_input_ids": [
                "MN-QUARTERLY-INTEREST",
                "MN-QUARTERLY-FIRM-EBITDA",
            ],
            "branches": [
                {
                    "branch_id": "RS-TAX-NO-CAP",
                    "condition": "abs(cash_interest) <= 0.30 * rep_ebitda",
                    "output_expression": (
                        "deductible_interest = abs(cash_interest); "
                        "carryforward = 0"
                    ),
                },
                {
                    "branch_id": "RS-TAX-CAPPED",
                    "condition": "abs(cash_interest) + prior_carryforward > 0.30 * rep_ebitda",
                    "output_expression": (
                        "deductible_interest = 0.30 * rep_ebitda; "
                        "carryforward = abs(cash_interest) + prior_carryforward - "
                        "0.30 * rep_ebitda"
                    ),
                },
            ],
            "dependent_ids": ["MN-QUARTERLY-CFO"],
            "source_ref": "keystone_model.py:_taxable_income():L558-583",
            "workbook_ref": f"{WB}:SB_Base!C116:V116 / Inputs!B16",
            "no_branch_behavior": "RAISE_UNDEFINED",
            "multi_branch_behavior": "RAISE_AMBIGUOUS",
        },
        {
            "rule_switch_id": "RS-FINANCING-GRID",
            "description": (
                "Financing grid: selects applicable leverage / pricing tier "
                "based on deal characteristics. Step-down rule for >15% "
                "single-parent exposure is a coverage limit."
            ),
            "selector_input_ids": ["MN-CONCENTRATION", "MN-NET-LEVERAGE"],
            "branches": [
                {
                    "branch_id": "RS-FG-STANDARD",
                    "condition": "single_parent_exposure <= 0.15",
                    "output_expression": "financing_terms = standard_grid",
                    "priority": 1,
                    "exclusive": True,
                },
                {
                    "branch_id": "RS-FG-STEP-DOWN-PLACEHOLDER",
                    "condition": "single_parent_exposure > 0.15",
                    "output_expression": "COVERAGE_LIMIT: step-down terms not policy-specified; block MN-DEBT-CAPACITY until policy_owner confirms",
                    "priority": 2,
                    "exclusive": True,
                    "fixture_only": True,
                    "coverage_limit_id": "KS-V7-CL-001",
                },
            ],
            "dependent_ids": ["MN-DEBT-CAPACITY"],
            "source_ref": f"{WB}:Financing_Grid (step-down rule)",
            "no_branch_behavior": "EMIT_COVERAGE_LIMIT",
            "multi_branch_behavior": "RAISE_AMBIGUOUS",
            "coverage_limits": [
                {
                    "limit_id": "KS-V7-CL-001",
                    "reason_code": "MISSING_POLICY_SPECIFICATION",
                    "scope_ids": ["MN-DEBT-CAPACITY", "RS-FG-STEP-DOWN-PLACEHOLDER"],
                    "effect": "Step-down branch is a fixture placeholder. Policy owner must confirm the exact step-down rule before RS-FG-STEP-DOWN-PLACEHOLDER can be evaluated.",
                }
            ],
        },
    ]


# ── SCC config ────────────────────────────────────────────────────────────────

def _build_scc_configs() -> list[dict]:
    return [
        {
            "component_id": "SCC-CASHFLOW-INTEREST-REVOLVER",
            "description": (
                "Cash Flow ↔ Interest ↔ Revolver cyclic dependency. "
                "Cash interest drives CFO; CFO + prior cash determines revolver need; "
                "revolver balance drives interest. Resolved per-quarter by "
                "fixed-point iteration."
            ),
            "member_ids": [
                "MN-QUARTERLY-CFO",
                "MN-QUARTERLY-INTEREST",
                "MN-QUARTERLY-REVOLVER",
            ],
            "equations": [
                {
                    "eq_id": "EQ-INTEREST",
                    "description": "Cash interest = f(term_avg, revolver_beg, ddtl_avg, sofr, spreads)",
                    "formula_ref": "F-INTEREST-EXPENSE",
                    "inputs": ["MN-QUARTERLY-TERM-LOAN[prior]",
                               "MN-QUARTERLY-REVOLVER[iteration]",
                               "MN-QUARTERLY-DDTL[prior]"],
                    "output": "MN-QUARTERLY-INTEREST",
                },
                {
                    "eq_id": "EQ-CFO",
                    "description": "CFO = net_income + D&A + fee_amort + deferred_tax - delta_NWC",
                    "formula_ref": "F-CFO",
                    "inputs": ["MN-QUARTERLY-FIRM-EBITDA",
                               "MN-QUARTERLY-INTEREST[iteration]",
                               "MN-NWC", "MN-REVENUE"],
                    "output": "MN-QUARTERLY-CFO",
                },
                {
                    "eq_id": "EQ-REVOLVER",
                    "description": "Revolver draw/repay = f(CFO, prior_cash, cash_floor, rule_switch)",
                    "formula_ref": "F-REVOLVER-DRAW-REPAY",
                    "rule_switch_ref": "RS-REVOLVER-DRAW",
                    "inputs": ["MN-QUARTERLY-CFO[iteration]",
                               "MN-QUARTERLY-CASH[prior]"],
                    "output": "MN-QUARTERLY-REVOLVER",
                },
            ],
            "component_type": "NUMERICAL_SCC",
            "method": "FIXED_POINT_ITERATION",
            "initialization": {
                "MN-QUARTERLY-REVOLVER": "prior_period_revolver_balance",
                "MN-QUARTERLY-INTEREST": 0.0,
            },
            "admissible_bounds": {
                "MN-QUARTERLY-REVOLVER": {"lower": 0.0, "upper": 7.5, "unit": "$mm"},
                "MN-QUARTERLY-INTEREST": {"lower": -50.0, "upper": 0.0, "unit": "$mm"},
            },
            "absolute_residual_tolerance": "1e-4",
            "relative_residual_tolerance": "1e-8",
            "maximum_iterations": 150,
            "convergence_condition": (
                "max(|revolver[k+1] - revolver[k]|) < absolute_residual_tolerance"
            ),
            "uniqueness_condition": (
                "Interest is monotonically increasing in revolver balance "
                "(higher revolver → more interest → lower CFO → more revolver need). "
                "Fixed point exists and is unique given bounded revolver commitment."
            ),
            "invariant_control_ids": ["MN-CHECK-SB-BASE-BS"],
            "no_solution_behavior": (
                "EMIT_PARTIAL_SETTLEMENT: report convergence_delta and "
                "last-iteration values; flag node as UNRESOLVED"
            ),
            "multiple_solution_behavior": "NOT_POSSIBLE (see uniqueness_condition)",
            "source_ref": "keystone_model.py:_run_quarter():L658-707",
        }
    ]


# ── Inverse solver ────────────────────────────────────────────────────────────

def _build_inverse_solvers() -> list[dict]:
    return [
        {
            "solver_id": "INV-SUPPORTED-PRICE",
            "description": (
                "Find the maximum entry enterprise value (EV) such that the sponsor "
                "achieves at least 14% gross IRR AND at least 2.0× gross MOIC "
                "in the Standalone Base scenario. Reports binding constraint."
            ),
            "decision_variable_ids": ["MN-EV"],
            "objective": {
                "sense": "MAXIMIZE",
                "variable_id": "MN-EV",
                "unit": "MM_USD",
            },
            "constraints": [
                {
                    "constraint_id": "IRR_FLOOR",
                    "expression_or_function_ref": "MN-BASE-IRR >= 0.14",
                    "unit": "decimal_rate",
                    "display_equivalent": "14% gross IRR floor",
                    "source_ref": "fund_lens_keystone: minimum gross IRR 14%; IC mandate",
                },
                {
                    "constraint_id": "MOIC_FLOOR",
                    "expression_or_function_ref": "MN-BASE-MOIC >= 2.0",
                    "unit": "x",
                    "display_equivalent": "2.0× gross MOIC floor",
                    "source_ref": "fund_lens_keystone: minimum gross MOIC 2.0×; IC mandate",
                },
                {
                    "constraint_id": "FINANCING_FEASIBLE",
                    "expression_or_function_ref": "MN-DEBT-CAPACITY >= MN-DEBT",
                    "unit": "MM_USD",
                    "source_ref": "credit agreement leverage covenant at close",
                },
            ],
            "initialization": {"MN-EV": 108.0},
            "admissible_bounds": {
                "lower": {"value": 0.0, "unit": "MM_USD"},
                "upper": {"value": 300.0, "unit": "MM_USD",
                          "note": "3× current underwritten EV 108"},
            },
            "absolute_residual_tolerance": "0.01",
            "relative_residual_tolerance": "1e-6",
            "maximum_iterations": 50,
            "method": "bisection over run_lbo(ev_override=MN-EV)",
            "uniqueness_condition": (
                "IRR and MOIC are strictly decreasing in EV; "
                "feasible set is a closed interval [0, max_ev]; solution unique at max_ev"
            ),
            "invariant_control_ids": ["CTRL-SOURCES-USES-BALANCE"],
            "financing_branch_ids": ["RS-REVOLVER-DRAW", "RS-ECF-SWEEP"],
            "binding_constraint_output": True,
            "no_solution_behavior": (
                "EMIT_INFEASIBLE: report which constraint(s) are binding at EV=0 "
                "and at EV=upper_bound; do not select a value arbitrarily"
            ),
            "multiple_solution_behavior": (
                "NOT_POSSIBLE: both IRR and MOIC are strictly decreasing in EV; "
                "solution is unique at max_ev"
            ),
            "source_ref": "keystone_model.py:run_lbo() + _compute_returns()",
        }
    ]


# ── Model controls ────────────────────────────────────────────────────────────

def _build_model_controls(inp: DealInputs) -> list[dict]:
    return [
        {
            "control_id": "CTRL-SOURCES-USES-BALANCE",
            "description": "Sources must equal Uses at closing (S&U identity).",
            "pass_condition_type": "tolerance_check",
            "expression": (
                "abs((term_loan + rollover + sponsor_equity) - "
                "(ev + financing_fees + buyer_tx_expenses)) < 0.001"
            ),
            "input_ids": ["MN-EV", "MN-DEBT", "MN-ROLLOVER",
                          "MN-SPONSOR-EQUITY", "MN-OPENING-CASH"],
            "tolerance": 0.001,
            "unit": "MM_USD",
            "period": "2026-03-10",
            "perimeter": "deal_level",
            "source_ref": f"{WB}:S&U_Opening (balance check)",
            "pass_condition": "sources_total == uses_total within 1k tolerance",
            "fail_outcome": "FAIL",
            "pass_outcome": "PASS",
            "unknown_condition": "any input_id unresolved",
            "blocks_on_fail": ["MN-SPONSOR-EQUITY", "MN-SUPPORTED-PRICE"],
        },
        {
            "control_id": "CTRL-OPENING-BS",
            "description": "Opening balance sheet assets = liabilities + equity.",
            "pass_condition_type": "tolerance_check",
            "expression": (
                "abs(total_assets - (total_liabilities + total_equity)) < 0.001"
            ),
            "input_ids": ["MN-DEBT", "MN-OPENING-CASH",
                          "MN-SPONSOR-EQUITY", "MN-ROLLOVER"],
            "tolerance": 0.001,
            "unit": "MM_USD",
            "period": "2026-03-10",
            "perimeter": "deal_level",
            "source_ref": f"{WB}:S&U_Opening!BS_check",
            "pass_condition": "assets == liabilities + equity within 1k tolerance",
            "fail_outcome": "FAIL",
            "pass_outcome": "PASS",
            "unknown_condition": "any input_id unresolved",
            "blocks_on_fail": ["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN"],
        },
        {
            "control_id": "CTRL-QUARTERLY-BS",
            "description": "Per-quarter balance sheet: assets = liabilities + equity.",
            "pass_condition_type": "tolerance_check",
            "expression": "abs(assets_q - liabilities_q - equity_q) < 0.001",
            "input_ids": ["MN-QUARTERLY-CASH", "MN-QUARTERLY-TERM-LOAN",
                          "MN-QUARTERLY-REVOLVER"],
            "tolerance": 0.001,
            "unit": "MM_USD",
            "period": f"{PERIODS[0]}/{PERIODS[-1]}",
            "perimeter": "Alderstone_standalone",
            "source_ref": f"{WB}:SB_Base (BS check rows)",
            "pass_condition": "balance sheet balances each quarter",
            "fail_outcome": "FAIL",
            "pass_outcome": "PASS",
            "unknown_condition": "any input_id unresolved in that period",
            "blocks_on_fail": ["MN-NET-LEVERAGE", "MN-EXIT-NET-DEBT"],
        },
        {
            "control_id": "CTRL-REVOLVER-COHERENCE",
            "description": (
                "Revolver balance must remain within [0, commitment] "
                f"(commitment = {inp.revolver_commitment} MM)."
            ),
            "pass_condition_type": "expression",
            "expression": (
                f"0 <= revolver_q <= {inp.revolver_commitment} for all q"
            ),
            "input_ids": ["MN-QUARTERLY-REVOLVER"],
            "tolerance": 0.001,
            "unit": "MM_USD",
            "period": f"{PERIODS[0]}/{PERIODS[-1]}",
            "perimeter": "deal_level",
            "source_ref": f"{WB}:Inputs!B20 (revolver_commitment = 7.5)",
            "pass_condition": "0 ≤ revolver ≤ 7.5 every quarter",
            "fail_outcome": "FAIL",
            "pass_outcome": "PASS",
            "unknown_condition": "MN-QUARTERLY-REVOLVER unresolved",
            "blocks_on_fail": ["MN-QUARTERLY-INTEREST", "MN-QUARTERLY-CFO"],
        },
        {
            "control_id": "CTRL-DEBT-INTEREST-COHERENCE",
            "description": "Interest expense sign must be negative (cash outflow).",
            "pass_condition_type": "expression",
            "expression": "cash_interest_q <= 0 for all q",
            "input_ids": ["MN-QUARTERLY-INTEREST"],
            "tolerance": 0.0,
            "unit": "MM_USD",
            "period": f"{PERIODS[0]}/{PERIODS[-1]}",
            "perimeter": "deal_level",
            "source_ref": "keystone_model.py:_interest_expense():L450",
            "pass_condition": "cash_interest is always ≤ 0",
            "fail_outcome": "FAIL",
            "pass_outcome": "PASS",
            "unknown_condition": "MN-QUARTERLY-INTEREST unresolved",
            "blocks_on_fail": ["MN-QUARTERLY-CFO"],
        },
        {
            "control_id": "CTRL-COVENANT-COMPLIANCE",
            "description": (
                "Net leverage must remain at or below covenant limit each quarter. "
                "Breach does NOT block the computation — it flags FAIL for IC review."
            ),
            "pass_condition_type": "expression",
            "expression": "net_leverage_q <= covenant_limit_q for all q",
            "input_ids": ["MN-NET-LEVERAGE"],
            "tolerance": 0.001,
            "unit": "RATIO",
            "period": f"{PERIODS[0]}/{PERIODS[-1]}",
            "perimeter": "deal_level",
            "source_ref": f"{WB}:Scenario_Drivers!C32:V32",
            "pass_condition": "net leverage ≤ covenant limit every quarter",
            "fail_outcome": "FAIL",
            "pass_outcome": "PASS",
            "unknown_condition": "MN-NET-LEVERAGE unresolved",
            "blocks_on_fail": [],
            "note": (
                "Covenant breach is advisory for monitoring; does not block "
                "Supported Price or MOIC computation"
            ),
        },
    ]


# ── Admission manifest ────────────────────────────────────────────────────────

def _build_admission_manifest(
    nodes: dict, formulas: list, edges: list, compiled_at: str, source_hash: str
) -> dict:
    content_hash = _hash_content({
        "model_nodes": nodes,
        "formulas":    formulas,
        "directed_model_edges": edges,
    })
    return {
        "manifest_id": f"KS-V7-{compiled_at[:10].replace('-', '')}",
        "extraction_hash": content_hash,
        "compiled_at": compiled_at,
        "compiler_source_hash": source_hash,
        "deal": "Project Keystone / Alderstone",
        "compiler": "tools/compiler_v7.py",
        "workbook_mapping_ref": "tools/keystone_model.py",
        "ontology_version": "v1.1",
        "admitted_claims": (
            "see vault/deals/keystone/claims/ — "
            "claim IDs must be re-bound after this extraction via the admission process"
        ),
        "cutoff_as_of_known_at": AS_OF_KNOWN_AT,
        "mapping_bundle_version": "v7",
        "policy_bundle_ref": "vault/policy/policy-table.md",
        "authority_matrix_ref": "EXTERNAL — must be provided by policy_owner",
        "materiality_policy_ref": "EXTERNAL — must be provided by policy_owner",
        "coverage_limits": [
            {
                "limit_id": "CL-FINANCING-GRID",
                "description": (
                    "Financing grid step-down rule (>15% single-parent exposure) "
                    "not available in current policy file. "
                    "RS-FINANCING-GRID branch RS-FG-STANDARD is the only declared branch. "
                    "MN-DEBT-CAPACITY is conservative until policy_owner confirms."
                ),
                "affected_nodes": ["MN-DEBT-CAPACITY", "RS-FINANCING-GRID"],
                "resolution": "policy_owner to provide financing_grid_v1.json",
            },
            {
                "limit_id": "CL-MATERIALITY-POLICY",
                "description": (
                    "keystone_materiality_policy_v0.json referenced in prior extractions "
                    "does not exist. Materiality thresholds are not applied in this V7."
                ),
                "affected_nodes": ["RS-ECF-SWEEP", "MN-SUPPORTED-PRICE"],
                "resolution": "policy_owner to provide keystone_materiality_policy_v1.json",
            },
            {
                "limit_id": "CL-SCENARIO-DRIVERS",
                "description": (
                    "Scenario drivers other than Standalone Base "
                    "(Downside, Upside, Acq Base, Combined Risk) "
                    "are declared as node stubs only. Workbook extraction pass needed "
                    "to bind their values."
                ),
                "affected_nodes": [
                    "MN-DOWN-MOIC", "MN-DOWN-IRR",
                    "MN-ACQ-MOIC", "MN-ACQ-IRR",
                    "MN-COMBINED-RISK-MOIC", "MN-COMBINED-RISK-IRR",
                ],
                "resolution": "run benchmark_extract.py --scenario all on the workbook",
            },
            {
                "limit_id": "CL-CONCENTRATION",
                "description": (
                    "MN-CONCENTRATION has no quantitative workbook binding. "
                    "RS-FINANCING-GRID cannot fully evaluate the step-down rule."
                ),
                "affected_nodes": ["MN-CONCENTRATION", "RS-FINANCING-GRID"],
                "resolution": "bind concentration metrics from QoE report or CIM",
            },
        ],
        "identity_migration_map": {
            "note": (
                "Stable MN-* IDs are used throughout this V7. "
                "Prior claim IDs (claim:000 style) from earlier extractions "
                "must NOT be used — they are not stable across extractions. "
                "Use MN-* IDs as the operative identity layer."
            ),
            "from_version": "V6",
            "stable_id_anchors": [
                "MN-EV", "MN-FIRM-EBITDA", "MN-COV-EBITDA",
                "MN-SPONSOR-EQUITY", "MN-DEBT", "MN-BASE-MOIC", "MN-BASE-IRR",
            ],
        },
    }


# ── LBO Grammar scaffold (diagnostic only) ───────────────────────────────────

def _build_grammar_scaffold() -> dict:
    return {
        "note": (
            "Diagnostic scaffold only — not executed by the runtime. "
            "All executable content is in the top-level collections above."
        ),
        "grammar_version": "lbo_grammar_v1",
        "canonical_chain": [
            "Revenue → EBITDA → Leverage → Debt_Capacity",
            "→ Sources_Uses → Sponsor_Equity",
            "→ Cash_Flow ↔ Interest/Revolver (SCC)",
            "→ Exit_EV / Exit_Net_Debt / Exit_Equity",
            "→ MOIC / XIRR → Supported_Price",
        ],
        "scc_members": ["CFO", "Interest", "Revolver"],
        "inverse_solve_node": "Supported_Price",
        "control_nodes": ["S&U_Balance", "Opening_BS", "Quarterly_BS",
                          "Covenant_Compliance", "Revolver_Coherence"],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def compile_v7(out_path: pathlib.Path = OUT_PATH) -> dict:
    """
    Compile the V7 execution graph and write to out_path.
    Returns the graph dict.
    """
    inp = DealInputs()
    compiled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Compute source hash over compiler + workbook mapping
    compiler_src   = pathlib.Path(__file__).read_bytes()
    workbook_src   = (ROOT / "tools" / "keystone_model.py").read_bytes()
    source_hash    = hashlib.sha256(compiler_src + workbook_src).hexdigest()

    nodes    = _build_model_nodes(inp)
    formulas = _build_formulas(inp)
    edges    = _build_directed_edges()

    graph = {
        "format_version": "v7",
        "schema_version": "1.0",
        "deal": {
            "name": "Project Keystone",
            "company": "Alderstone",
            "slug": "keystone",
        },
        "compiler": {
            "source": "tools/compiler_v7.py",
            "source_hash": source_hash[:16],
            "compiled_at": compiled_at,
            "workbook_mapping_ref": "tools/keystone_model.py",
        },
        "model_nodes":                     nodes,
        "directed_model_edges":            edges,
        "formulas":                        formulas,
        "rule_switches":                   _build_rule_switches(),
        "cyclic_component_solver_configs": _build_scc_configs(),
        "inverse_solver_configs":          _build_inverse_solvers(),
        "model_controls":                  _build_model_controls(inp),
        "admission_manifest":              _build_admission_manifest(
                                               nodes, formulas, edges,
                                               compiled_at, source_hash,
                                           ),
        "lbo_grammar_scaffold":            _build_grammar_scaffold(),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False))
    return graph


def main() -> None:
    ap = argparse.ArgumentParser(
        description="V7 Compiler: keystone_model.py → execution_graph_v7.json"
    )
    ap.add_argument("--out", default=str(OUT_PATH),
                    help=f"Output path (default: {OUT_PATH})")
    ap.add_argument("--validate", action="store_true",
                    help="Run test_v7.py after compilation")
    args = ap.parse_args()

    out = pathlib.Path(args.out).expanduser().resolve()
    print(f"\n=== V7 Compiler ===")
    print(f"  workbook mapping : tools/keystone_model.py")
    print(f"  output           : {out}\n")

    graph = compile_v7(out)

    n_nodes   = len(graph["model_nodes"])
    n_edges   = len(graph["directed_model_edges"])
    n_forms   = len(graph["formulas"])
    n_rules   = len(graph["rule_switches"])
    n_sccs    = len(graph["cyclic_component_solver_configs"])
    n_solvers = len(graph["inverse_solver_configs"])
    n_ctrls   = len(graph["model_controls"])

    print(f"  model_nodes               : {n_nodes}")
    print(f"  directed_model_edges      : {n_edges}")
    print(f"  formulas                  : {n_forms}")
    print(f"  rule_switches             : {n_rules}")
    print(f"  cyclic_solver_configs     : {n_sccs}")
    print(f"  inverse_solver_configs    : {n_solvers}")
    print(f"  model_controls            : {n_ctrls}")
    print(f"\n  extraction_hash : {graph['admission_manifest']['extraction_hash'][:32]}…")
    print(f"\nDone → {out}\n")

    if args.validate:
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "test_v7.py")],
            cwd=str(ROOT),
        )
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
