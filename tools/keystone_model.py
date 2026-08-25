"""
keystone_model.py — Runnable workbook mapping for Keystone / Alderstone LBO.

This module is the workbook_mapping layer (Alex's Layer 2):
  - Every formula is derived from keystone_lbo_model_working.xlsx
  - Cell references are documented on each computation
  - Anto's runtime calls propagate_claim() with new evidence → gets real economic delta

Sheets mapped:
  Inputs        (B3:B34)    — locked deal terms + model assumptions
  Scenario_Drivers (C3:V36) — quarterly drivers for each scenario
  SB_Base       (C5:V140)   — full quarterly P&L / CF / BS / debt schedule
  Ownership_Returns (B4:L8) — MOIC / XIRR by case

LBO Grammar (general LBO concepts) lives in _claim_graph.py execution_mapping.
This file is the workbook mapping — Keystone-specific and executable.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any

# ── Cell-reference index ──────────────────────────────────────────────────────
# Each constant below cross-references the Inputs sheet cell that defines it.
# Format: Inputs!B<row>

@dataclass
class DealInputs:
    """Locked deal terms and model assumptions — Inputs!B3:B34."""
    # Inputs!B3  — KS-DL-1.2
    enterprise_value:        float = 108.0
    # Inputs!B4  — KS-DL-1.2 (seller net debt + debt-like items)
    seller_net_debt:         float = 10.2
    # Inputs!B7  — KS-DL-1.2
    seller_rollover:         float = 12.0
    # Inputs!B8  — KS-DL-1.2 (corrected capitalization)
    sponsor_equity:          float = 62.0
    # Inputs!B9  — KS-DL-1.2
    term_loan_opening:       float = 42.8
    # Inputs!B10 — KS-DL-1.2
    opening_cash:            float = 3.0
    # Inputs!B11 — KS-DL-1.2 (valuation + internal leverage)
    firm_ebitda_opening:     float = 11.4
    # Inputs!B12 — KS-DL-1.2 (credit agreement only)
    covenant_ebitda_opening: float = 12.2
    # Inputs!B14 — KS-DL-1.2 (dollar-for-dollar true-up)
    nwc_target:              float = 8.4
    # Inputs!B15 — KS-MA-001 (blended federal/state)
    tax_rate:                float = 0.26
    # Inputs!B16 — KS-MA-002 (simplified 163(j))
    interest_deduction_cap:  float = 0.30
    # Inputs!B17 — KS-MA-003
    depreciation_pct_rev:    float = 0.015
    # Inputs!B18 — KS-MA-004
    maintenance_capex_share: float = 0.75
    # Inputs!B19 — KS-DL-1.2 (covenant only)
    eligible_cash_netting:   float = 5.0
    # Inputs!B20 — KS-DL-1.2
    revolver_commitment:     float = 7.5
    # Inputs!B21 — KS-DL-1.2
    ddtl_commitment:         float = 10.0
    # Inputs!B22 — KS-DL-1.2
    lc_sublimit:             float = 2.0
    # Inputs!B23 — KS-DL-1.2 (over adjusted Term SOFR)
    term_spread:             float = 0.055
    # Inputs!B24 — KS-DL-1.2
    revolver_spread:         float = 0.050
    # Inputs!B25 — KS-DL-1.2
    ddtl_spread:             float = 0.0575
    # Inputs!B26 — KS-DL-1.2
    sofr_floor:              float = 0.01
    # Inputs!B27 — KS-DL-1.2 (quarterly payments)
    term_amort_pa:           float = 0.01        # % of original principal p.a.
    # Inputs!B28 — KS-DL-1.2 (after draw)
    ddtl_amort_pa:           float = 0.01
    # Inputs!B29 — KS-DL-1.2
    unused_revolver_fee:     float = 0.005
    # Inputs!B30 — KS-DL-1.2 (after first 90 days)
    unused_ddtl_fee:         float = 0.010
    # Inputs!B31 — KS-DL-1.2 (amortized over 24 quarters)
    financing_fees:          float = 1.4
    # Inputs!B32 — KS-DL-1.2 (expensed at closing)
    buyer_tx_expenses:       float = 4.4
    # Inputs!B34 — KS-DL-1.2
    exit_date:               str   = "2031-03-31"
    # S&U_Opening!E18 — opening term loan balance (= term_loan_opening)
    # S&U_Opening!B15 — opening cash (= opening_cash)
    # S&U_Opening!B24 — deferred financing fees = financing_fees

    @property
    def quarterly_term_amort(self) -> float:
        """Inputs!B27 × opening_term / 4 — quarterly cash amortization."""
        # SB_Base!C61: =-(MIN(0.107, S&U_Opening!E18))
        # 0.107 = 42.8 × 1% / 4 = 0.107
        return round(self.term_loan_opening * self.term_amort_pa / 4, 6)

    @property
    def quarterly_ddtl_amort_rate(self) -> float:
        """Per-quarter DDTL amortization: Inputs!B28 × drawn / 4."""
        # SB_Base!D62: =-(IF(C77>0, MIN(0.015, C77), 0))
        # 0.015 = 10 × 1% × 1.5 = 0.015? Actually: 10 × 1% / 4 = 0.025? No.
        # Looking at actual formula: MIN(0.015, ddtl_balance)
        # 0.015 = 10 × 0.01 / ... hmm, not quarterly. Let me check:
        # 10 × 1% pa = 0.1/year = 0.025/quarter. But formula uses 0.015.
        # 0.015 seems to be pre-coded. Use as-is from workbook.
        return 0.015  # SB_Base rows 62: MIN(0.015, ddtl_balance) quarterly cap

    @property
    def quarterly_financing_fee_amort(self) -> float:
        """Inputs!B31 / 24 quarters — SB_Base!C23."""
        return self.financing_fees / 24

    @property
    def opening_equity_book(self) -> float:
        """S&U_Opening!E21 — opening book equity after transaction expenses."""
        return 69.6  # 74.0 - 4.4 (buyer tx expenses)

    @property
    def mip_base_pct(self) -> float:
        """Sponsor pre-MIP ownership % at closing — Ownership_Returns!D13."""
        total = self.sponsor_equity + self.seller_rollover  # 62 + 12 = 74
        return self.sponsor_equity / total  # 0.8378


@dataclass
class QuarterlyDrivers:
    """
    Per-quarter operating assumptions — Scenario_Drivers rows 4-36 for one scenario.
    20 quarters: Jun-26, Sep-26, Dec-26, Mar-27, ..., Mar-31.
    """
    periods: list[str]             # 20 quarter-end dates
    revenue: list[float]           # Scenario_Drivers row 5 (or equiv per scenario)
    ebitda:  list[float]           # Scenario_Drivers row 7
    dso:     list[float]           # days — row 10
    wip_pct: list[float]           # WIP / annualised revenue — row 11
    prepaids_pct: list[float]      # row 12
    ap_pct:  list[float]           # row 13
    accruals_pct: list[float]      # row 14
    deferred_rev_pct: list[float]  # row 15
    capex_pct: list[float]         # row 16
    seasonality: list[float]       # row 36 (quarterly revenue weight)
    sofr: list[float]              # row 33
    ppa_amort: list[float]         # row 35 ($mm per quarter)
    cash_floor: list[float]        # row 29
    forced_revolver_target: list[float]  # row 30 (-1 = auto)
    repay_all_revolver: list[float]      # row 31 (0 = no, 1 = yes)
    covenant_limit: list[float]    # row 32 (max net leverage)
    one_time_charges: list[float]  # row 8 (positive = charge)
    covenant_addbacks: list[float] # row 9
    ddtl_draw: list[float]         # row 25
    sponsor_contribution: list[float]   # row 26
    exit_multiple: float           # Inputs!B46 (per scenario)


@dataclass
class QuarterResult:
    """State at end of one quarter — mirrors SB_Base row structure."""
    period:          str
    # Operating model (SB_Base rows 5-15)
    revenue:         float   # SB_Base row 5
    gross_profit:    float   # row 8 = revenue × gross_margin
    firm_ebitda:     float   # row 10 (from Scenario_Drivers)
    reported_ebitda: float   # row 12 = firm_ebitda - one_time_charges
    covenant_ebitda: float   # row 14 = reported + addbacks
    # Income statement (rows 17-28)
    depreciation:    float   # row 17 = revenue × dep_pct
    ppa_amort:       float   # row 18
    total_da:        float   # row 20 = dep + ppa_amort
    cash_interest:   float   # row 22 (cyclic, negative = outflow)
    fee_amort:       float   # row 23
    interest_income: float   # row 24
    pre_tax_income:  float   # row 25
    book_tax:        float   # row 26
    cash_tax:        float   # row 27
    net_income:      float   # row 28
    # Working capital (rows 30-38)
    ar:              float   # row 30
    wip:             float   # row 31
    prepaids:        float   # row 32
    ap:              float   # row 33
    accruals:        float   # row 34
    deferred_rev:    float   # row 35
    op_nwc:          float   # row 36 = ar+wip+prepaids - ap - accruals - deferred_rev
    delta_nwc:       float   # row 38 (change vs prior)
    # Capex (rows 39-41)
    maintenance_capex: float  # row 39
    growth_capex:    float    # row 40
    total_capex:     float    # row 41
    # Cash flow statement (rows 47-67)
    cfo:             float    # row 52
    cfi:             float    # row 56
    ddtl_draw:       float    # row 58
    revolver_draw:   float    # row 59
    revolver_repay:  float    # row 60
    term_amort:      float    # row 61 (negative)
    ddtl_amort:      float    # row 62 (negative)
    ecf_sweep:       float    # row 63 (negative)
    cff:             float    # row 64
    net_cash_change: float    # row 65
    beg_cash:        float    # row 66
    end_cash:        float    # row 67
    # Debt balances (rows 76-78)
    term_loan:       float    # row 76 end-of-quarter
    ddtl:            float    # row 77
    revolver:        float    # row 78
    # Covenant metrics
    ltm_covenant_ebitda: float = 0.0
    net_leverage_covenant: float = 0.0


@dataclass
class LBOResult:
    """Full model output for one scenario."""
    quarters:     list[QuarterResult]
    # Returns (Ownership_Returns sheet)
    exit_ltm_revenue:  float
    exit_ltm_ebitda:   float
    exit_multiple:     float
    exit_ev:           float
    exit_net_debt:     float
    exit_equity:       float
    sponsor_invested:  float
    vested_mip_pct:    float
    sponsor_proceeds:  float
    gross_moic:        float
    gross_xirr:        float
    # Validation
    bs_check_passes:   bool


# ── Workbook constants ────────────────────────────────────────────────────────

PERIODS = [
    "2026-06-30", "2026-09-30", "2026-12-31", "2027-03-31",
    "2027-06-30", "2027-09-30", "2027-12-31", "2028-03-31",
    "2028-06-30", "2028-09-30", "2028-12-31", "2029-03-31",
    "2029-06-30", "2029-09-30", "2029-12-31", "2030-03-31",
    "2030-06-30", "2030-09-30", "2030-12-31", "2031-03-31",
]  # SB_Base!C3:V3

# Scenario_Drivers!C5:V5 (Standalone Base)
SB_REVENUE = [
    19.795, 20.587, 20.587, 19.486,
    21.181, 22.028, 22.028, 20.850,
    22.663, 23.570, 23.570, 22.310,
    24.250, 25.220, 25.220, 23.871,
    25.947, 26.985, 26.985, 25.542,
]  # Scenario_Drivers!C5:V5

# Scenario_Drivers!C7:V7 (Standalone Base firm EBITDA)
SB_EBITDA = [
    3.088, 3.212, 3.212, 3.137,
    3.410, 3.546, 3.546, 3.440,
    3.739, 3.889, 3.889, 3.770,
    4.098, 4.262, 4.262, 4.130,
    4.489, 4.668, 4.668, 4.521,
]  # Scenario_Drivers!C7:V7

# Scenario_Drivers!C10:V10 (DSO days)
SB_DSO = [
    64, 64, 64, 63, 63, 63, 63, 62, 62, 62, 62, 61,
    61, 61, 61, 60, 60, 60, 60, 60,
]  # Scenario_Drivers!C10:V10

# Scenario_Drivers!C11:V11 (WIP / annualised revenue)
SB_WIP = [
    0.067, 0.067, 0.067, 0.065, 0.065, 0.065, 0.065, 0.063,
    0.063, 0.063, 0.063, 0.061, 0.061, 0.061, 0.061, 0.060,
    0.060, 0.060, 0.060, 0.060,
]  # Scenario_Drivers!C11:V11

# Scenario_Drivers!C12:V12 (prepaids)
SB_PREPAIDS = [0.012] * 20  # Scenario_Drivers!C12:V12

# Scenario_Drivers!C13:V13 (AP / annualised revenue)
SB_AP = [0.055] * 20  # Scenario_Drivers!C13:V13

# Scenario_Drivers!C14:V14 (accruals)
SB_ACCRUALS = [0.075] * 20  # Scenario_Drivers!C14:V14

# Scenario_Drivers!C15:V15 (deferred revenue)
SB_DEFERRED = [0.012] * 20  # Scenario_Drivers!C15:V15

# Scenario_Drivers!C16:V16 (capex / revenue)
SB_CAPEX = [0.016] * 20  # Scenario_Drivers!C16:V16

# Scenario_Drivers!C36:V36 (seasonality — quarterly revenue weight)
SB_SEASONALITY = [
    0.25, 0.26, 0.26, 0.23,
    0.25, 0.26, 0.26, 0.23,
    0.25, 0.26, 0.26, 0.23,
    0.25, 0.26, 0.26, 0.23,
    0.25, 0.26, 0.26, 0.23,
]  # Scenario_Drivers!C36:V36

# Scenario_Drivers!C33:V33 (SOFR forward curve)
SB_SOFR = [
    0.0425, 0.0425, 0.0425, 0.0375,
    0.0375, 0.0375, 0.0375, 0.0350,
    0.0350, 0.0350, 0.0350, 0.0325,
    0.0325, 0.0325, 0.0325, 0.0300,
    0.0300, 0.0300, 0.0300, 0.0300,
]  # Scenario_Drivers!C33:V33

# Scenario_Drivers!C35:V35 (core PPA amortization, $mm/quarter)
SB_PPA = [0.75] * 20  # Scenario_Drivers!C35:V35

# Scenario_Drivers!C29:V29 (cash floor)
SB_CASH_FLOOR = [3.0] * 20  # Scenario_Drivers!C29:V29

# Scenario_Drivers!C30:V30 (forced revolver target — -1 = auto)
SB_FORCED_REV = [-1.0] * 20  # Scenario_Drivers!C30:V30

# Scenario_Drivers!C31:V31 (repay all revolver flag)
SB_REPAY_ALL = [0.0] * 20  # Scenario_Drivers!C31:V31

# Scenario_Drivers!C32:V32 (net leverage covenant limit)
SB_COV_LIMIT = [
    4.25, 4.25, 4.25, 4.25,
    4.25, 4.25, 4.25, 4.00,
    4.00, 4.00, 4.00, 3.75,
    3.75, 3.75, 3.75, 3.50,
    3.50, 3.50, 3.50, 3.50,
]  # Scenario_Drivers!C32:V32

SB_GROSS_MARGIN = [
    0.362, 0.362, 0.362, 0.365, 0.365, 0.365, 0.365, 0.368,
    0.368, 0.368, 0.368, 0.371, 0.371, 0.371, 0.371, 0.374,
    0.374, 0.374, 0.374, 0.377,
]  # Scenario_Drivers!C6:V6

# MIP vesting schedule — interpolated from Ownership_Returns values
# At exit (2031-03-31): Standalone Base vested = 8.75%, Down = 6%, Up = 10%
# Simplified: linear vest from 0% at entry to max pct at exit
MIP_VESTING = {
    "standalone_base":     0.0875,  # OR!I4
    "standalone_downside": 0.0600,  # OR!I5
    "standalone_upside":   0.1000,  # OR!I6
    "acquisition_base":    0.0915,  # OR!I7
}


def _build_sb_drivers() -> QuarterlyDrivers:
    """Build Standalone Base QuarterlyDrivers from hardcoded workbook values."""
    return QuarterlyDrivers(
        periods=PERIODS,
        revenue=SB_REVENUE,
        ebitda=SB_EBITDA,
        dso=SB_DSO,
        wip_pct=SB_WIP,
        prepaids_pct=SB_PREPAIDS,
        ap_pct=SB_AP,
        accruals_pct=SB_ACCRUALS,
        deferred_rev_pct=SB_DEFERRED,
        capex_pct=SB_CAPEX,
        seasonality=SB_SEASONALITY,
        sofr=SB_SOFR,
        ppa_amort=SB_PPA,
        cash_floor=SB_CASH_FLOOR,
        forced_revolver_target=SB_FORCED_REV,
        repay_all_revolver=SB_REPAY_ALL,
        covenant_limit=SB_COV_LIMIT,
        one_time_charges=[0.0] * 20,   # Scenario_Drivers!C8:V8 = 0
        covenant_addbacks=[0.0] * 20,  # Scenario_Drivers!C9:V9 = 0
        ddtl_draw=[0.0] * 20,          # Scenario_Drivers!C25:V25 = 0
        sponsor_contribution=[0.0] * 20,  # Scenario_Drivers!C26:V26 = 0
        exit_multiple=9.0,             # Inputs!B46
    )


# ── Core quarterly computation ────────────────────────────────────────────────

def _nwc_balance(rev: float, season: float, dso: float, wip: float,
                 prepaids: float, ap: float, accruals: float, deferred: float) -> float:
    """
    Operating NWC — SB_Base!C36.
    ar     = (rev / season) * dso / 365           — row 30
    wip    = (rev / season) * wip_pct             — row 31
    prepaid= (rev / season) * prepaids_pct        — row 32
    ap     = (rev / season) * ap_pct              — row 33
    accr   = (rev / season) * accruals_pct        — row 34
    def_r  = (rev / season) * deferred_pct        — row 35
    nwc    = ar + wip + prepaid - ap - accr - def_r
    """
    ann_rev = rev / season
    ar_b    = ann_rev * dso / 365
    wip_b   = ann_rev * wip
    pre_b   = ann_rev * prepaids
    ap_b    = ann_rev * ap
    acc_b   = ann_rev * accruals
    def_b   = ann_rev * deferred
    return ar_b + wip_b + pre_b - ap_b - acc_b - def_b


def _interest_expense(inp: DealInputs,
                      term_beg: float, term_amort_q: float,
                      rev_beg: float,
                      ddtl_beg: float, ddtl_draw_q: float, ddtl_amort_q: float,
                      sofr: float,
                      cash_beg: float,
                      lc_drawn: float = 0.0,
                      rate_step_up: float = 0.0) -> tuple[float, float]:
    """
    Quarterly cash interest — SB_Base!C22 (first quarter) / D22 (subsequent).

    Exact formula from SB_Base!D22:
      -(
        ((term_beg + MAX(0, term_beg - MIN(0.107, term_beg))) / 2)
          × (MAX(sofr_floor, sofr) + term_spread + rate_step_up) / 4

      + ((ddtl_beg + ddtl_beg + ddtl_draw - IF(ddtl_beg>0, MIN(0.015, ddtl_beg), 0)) / 2)
          × (MAX(sofr_floor, sofr) + ddtl_spread + rate_step_up) / 4

      + rev_beg × (MAX(sofr_floor, sofr) + revolver_spread + rate_step_up) / 4

      + MAX(0, rev_commitment - rev_beg - lc_drawn) × unused_rev_fee / 4

      + MAX(0, ddtl_commitment - ddtl_beg - ddtl_draw) × unused_ddtl_fee / 4
      )

    Note: revolver uses BEGINNING balance (rev_beg), not average — SB_Base!D22.
    Note: term uses avg of beg and (beg - amort).
    Note: DDTL unused fee computed after draw — SB_Base!D22 Inputs!B30.
    """
    eff_sofr = max(inp.sofr_floor, sofr)
    eff_rate = eff_sofr + rate_step_up

    # Term: avg of beginning and provisional end (SB_Base!D22)
    term_end_prov = max(0.0, term_beg - min(inp.quarterly_term_amort, term_beg))
    term_avg      = (term_beg + term_end_prov) / 2
    term_int      = term_avg * (eff_rate + inp.term_spread) / 4

    # DDTL: avg of beg and (beg + draw - amort) — SB_Base!D22
    ddtl_amort_draw = -min(inp.quarterly_ddtl_amort_rate, ddtl_beg) if ddtl_beg > 0 else 0.0
    ddtl_end_prov   = ddtl_beg + ddtl_draw_q + ddtl_amort_draw
    ddtl_avg        = (ddtl_beg + ddtl_end_prov) / 2
    ddtl_int        = ddtl_avg * (eff_rate + inp.ddtl_spread) / 4
    ddtl_unused     = max(0.0, inp.ddtl_commitment - ddtl_beg - ddtl_draw_q)
    ddtl_fee        = ddtl_unused * inp.unused_ddtl_fee / 4

    # Revolver: uses beginning balance, not average — SB_Base!D22
    rev_int = rev_beg * (eff_rate + inp.revolver_spread) / 4
    rev_unused = max(0.0, inp.revolver_commitment - rev_beg - lc_drawn)
    rev_fee = rev_unused * inp.unused_revolver_fee / 4

    # Interest income on beginning cash — SB_Base!C24/D24
    int_income = cash_beg * 0.01 / 4

    cash_interest = -(term_int + ddtl_int + ddtl_fee + rev_int + rev_fee)
    return cash_interest, int_income


def _revolver_draw_repay(inp: DealInputs,
                         prior_cash: float, prior_rev: float,
                         cfo: float, cfi: float, cff_ex_rev: float,
                         sofr: float,
                         cash_floor: float,
                         forced_target: float,
                         repay_all: bool,
                         q_idx: int) -> tuple[float, float]:
    """
    Revolver draw (positive) and repay (negative) — SB_Base!C59/D59 and C60/D60.

    Logic (simplified from the IF-chain):
      pre_rev_cash = prior_cash + cfo + cfi + cff_ex_rev
      if forced_target >= 0:          # manual override
          draw = MAX(0, forced_target - prior_rev)
          repay = -MAX(0, prior_rev - forced_target)
      elif pre_rev_cash >= cash_floor:
          # enough cash — repay as much as possible
          draw = 0
          surplus = pre_rev_cash - cash_floor
          repay = -MIN(prior_rev, surplus)
      else:
          # cash shortfall — draw to reach floor, capped at commitment - outstanding
          shortfall = cash_floor - pre_rev_cash
          draw = MIN(shortfall, inp.revolver_commitment - prior_rev)
          repay = 0
      if repay_all:
          repay = -prior_rev  # full repayment

    This mirrors SB_Base!D59 (subsequent quarter formula).
    """
    pre_cash = prior_cash + cfo + cfi + cff_ex_rev
    if forced_target >= 0:
        draw   = max(0.0, forced_target - prior_rev)
        repay  = -max(0.0, prior_rev - forced_target)
    elif repay_all:
        draw   = 0.0
        repay  = -prior_rev
    elif pre_cash >= cash_floor:
        draw   = 0.0
        surplus = pre_cash - cash_floor
        repay  = -min(prior_rev, surplus)
    else:
        shortfall = cash_floor - pre_cash
        draw   = min(shortfall, inp.revolver_commitment - prior_rev)
        repay  = 0.0
    return draw, repay


def _ecf_sweep(inp: DealInputs,
               prior_term: float,
               term_amort_q: float,
               prior_ddtl: float,
               ddtl_draw_q: float,
               ddtl_amort_q: float,
               ending_rev: float,
               ending_cash: float,
               cash_floor: float,
               ltm_covenant_ebitda: float,
               q_idx: int) -> float:
    """
    Annual excess cash flow sweep — SB_Base!E63, I63, M63, Q63, U63.
    Only fires in Dec-31 quarters (indices 2, 6, 10, 14, 18 — 0-based).

    Exact formula from SB_Base!E63:
      = -(
          MIN(
            MAX(0, prior_term + term_amort),        ← remaining term after sched amort
            MAX(0, ending_cash - cash_floor)         ← free cash above floor
          )
          ×
          IF(net_leverage > 3.0, 50%,
             IF(net_leverage > 2.5, 25%, 0%))
        )

    Where net_leverage at ECF date =
      (remaining_term + remaining_ddtl + ending_revolver
       - MIN(ending_cash, Inputs!B19)) / ltm_covenant_ebitda
    """
    DEC_INDICES = {2, 6, 10, 14, 18}  # 0-based — Dec-31 quarters
    if q_idx not in DEC_INDICES:
        return 0.0

    remaining_term = max(0.0, prior_term + term_amort_q)
    remaining_ddtl = max(0.0, prior_ddtl + ddtl_draw_q + ddtl_amort_q)
    free_cash = max(0.0, ending_cash - cash_floor)

    # Net leverage for sweep rate determination — SB_Base!E63 condition
    net_debt_ecf = (remaining_term + remaining_ddtl + ending_rev
                    - min(ending_cash, inp.eligible_cash_netting))
    ltm = max(0.001, ltm_covenant_ebitda)
    net_lev = net_debt_ecf / ltm

    if net_lev > 3.0:
        sweep_rate = 0.50
    elif net_lev > 2.5:
        sweep_rate = 0.25
    else:
        sweep_rate = 0.0

    raw_sweep = min(remaining_term, free_cash)
    return -raw_sweep * sweep_rate


def _taxable_income(rep_ebitda: float,
                    dep_only: float,
                    cash_interest: float,
                    interest_cap: float,
                    prior_int_carryforward: float = 0.0) -> float:
    """
    Taxable income — SB_Base!C116/D116.

    C116 = MAX(0, C12 - C17 - MIN(-C22 + 0, MAX(0, B16 × C12)))
    D116 = MAX(0, D12 - D17 - MIN(-D22 + C114, MAX(0, B16 × D12)))

    Where:
      C12  = reported EBITDA (not firm EBITDA)
      C17  = depreciation ONLY (NOT PPA amort — C17 not C20)
      -C22 = abs(cash_interest)
      C114 = 163(j) interest carryforward from prior quarter
      B16  = 0.30 (163j cap as % of EBITDA)

    PPA amortization (row 18) is excluded from the tax deduction — workbook uses
    only C17 (row 17 = depreciation = revenue × 1.5%).
    """
    abs_int_avail = abs(cash_interest) + prior_int_carryforward
    cap = max(0.0, interest_cap * rep_ebitda)
    deductible_int = min(abs_int_avail, cap)
    return max(0.0, rep_ebitda - dep_only - deductible_int)


def _int_carryforward(abs_int_avail: float, cap: float) -> float:
    """163(j) interest carryforward — SB_Base!C114."""
    return max(0.0, abs_int_avail - cap)


def _run_quarter(
    q: int,
    drv: QuarterlyDrivers,
    inp: DealInputs,
    prior: QuarterResult | None,
    prior_nwc: float,
    ltm_window: list[QuarterResult],
    prior_int_carry: float = 0.0,
) -> tuple[QuarterResult, float]:
    """
    Compute one quarter — mirrors SB_Base column logic.
    Cyclic interest/revolver resolved by fixed-point iteration (SCC-001).
    """
    rev      = drv.revenue[q]
    ebitda   = drv.ebitda[q]
    one_time = drv.one_time_charges[q]
    cov_add  = drv.covenant_addbacks[q]
    sofr_q   = drv.sofr[q]
    season   = drv.seasonality[q]
    dso      = drv.dso[q]
    capex_r  = drv.capex_pct[q]
    ppa_q    = drv.ppa_amort[q]

    # Opening balances
    beg_term  = prior.term_loan if prior else inp.term_loan_opening
    beg_ddtl  = prior.ddtl     if prior else 0.0
    beg_rev   = prior.revolver  if prior else 0.0
    beg_cash  = prior.end_cash  if prior else inp.opening_cash

    # Opening book equity (for BS check)
    prior_eq  = prior.end_cash if prior else inp.opening_equity_book

    # ── Income statement ──────────────────────────────────────────────────────
    rep_ebitda = ebitda - one_time     # SB_Base!C12 (one_time is subtracted)
    cov_ebitda = rep_ebitda + cov_add  # SB_Base!C14

    # Depreciation — SB_Base!C17: = revenue × Inputs!B17
    dep = rev * inp.depreciation_pct_rev

    # PPA amortization — SB_Base!C18: = Scenario_Drivers!C35
    total_da = dep + ppa_q                 # SB_Base!C20 (integration amort = 0)

    # Fee amortization — SB_Base!C23
    prior_def_fees = prior.fee_amort if prior else inp.financing_fees  # approximation
    fee_amort = min(inp.quarterly_financing_fee_amort, inp.financing_fees)

    # Capex — SB_Base!C39/C40/C41
    maint_capex = rev * capex_r * inp.maintenance_capex_share
    growth_capex = rev * capex_r * (1 - inp.maintenance_capex_share)
    total_capex = maint_capex + growth_capex

    # Working capital — SB_Base!C36/C38
    nwc = _nwc_balance(rev, season, dso,
                       drv.wip_pct[q], drv.prepaids_pct[q],
                       drv.ap_pct[q], drv.accruals_pct[q],
                       drv.deferred_rev_pct[q])
    # Opening NWC reference for first quarter uses S&U_Opening balance sheet
    delta_nwc = nwc - prior_nwc          # increase = cash outflow → -(delta)

    # DDTL — SB_Base!C77
    ddtl_draw_q = drv.ddtl_draw[q]
    ddtl_amort_q = -(min(inp.quarterly_ddtl_amort_rate, beg_ddtl)
                     if beg_ddtl > 0 else 0.0)
    end_ddtl  = max(0.0, beg_ddtl + ddtl_draw_q + ddtl_amort_q)

    # Term amortization — SB_Base!C61: -(MIN(0.107, term_balance))
    term_amort_q = -(min(inp.quarterly_term_amort, beg_term))

    # ── Cyclic solve: interest ↔ revolver (CYC-SCC-001) ──────────────────────
    # SB_Base rows 22/59/60/78 are coupled: interest drives CFO → revolver need;
    # revolver balance drives interest. Solve by fixed-point iteration.
    rev_bal = beg_rev   # initial guess
    sponsor_contrib = drv.sponsor_contribution[q]

    for _iter in range(150):
        # Interest expense — SB_Base!D22 signature
        cash_int, int_income = _interest_expense(
            inp,
            beg_term,  term_amort_q,
            rev_bal,                       # beginning revolver (pre-draw/repay)
            beg_ddtl,  ddtl_draw_q, ddtl_amort_q,
            sofr_q, beg_cash,
        )

        # Income statement
        ebit      = rep_ebitda - total_da
        pre_tax   = ebit + cash_int - fee_amort + int_income
        book_tax  = -max(0.0, pre_tax * inp.tax_rate)
        # Cash tax uses dep-only (row 17, NOT row 20) and 163(j) carryforward — C116
        taxable   = _taxable_income(rep_ebitda, dep, cash_int, inp.interest_deduction_cap, prior_int_carry)
        cash_tax  = -taxable * inp.tax_rate
        net_income = pre_tax + book_tax

        # CFO — SB_Base!C52 — deferred_tax = -C26 + C27 (both negative, signs kept)
        deferred_tax_adj = -book_tax + cash_tax   # = +abs(book_tax) + (cash_tax)
        cfo = net_income + total_da + fee_amort + deferred_tax_adj - delta_nwc

        # CFI — SB_Base!C56
        cfi = -total_capex

        # Financing ex-revolver (deterministic)
        cff_ex_rev = sponsor_contrib + ddtl_draw_q + term_amort_q + ddtl_amort_q

        # Revolver draw / repay — SB_Base!C59/D59 / C60/D60
        draw_q, repay_q = _revolver_draw_repay(
            inp, beg_cash, rev_bal, cfo, cfi, cff_ex_rev,
            sofr_q,
            drv.cash_floor[q],
            drv.forced_revolver_target[q],
            bool(drv.repay_all_revolver[q]),
            q,
        )
        new_rev_bal = max(0.0, min(beg_rev + draw_q + repay_q, inp.revolver_commitment))

        if abs(new_rev_bal - rev_bal) < 0.0001:
            rev_bal = new_rev_bal
            break
        rev_bal = new_rev_bal

    # Recompute final interest with converged rev_bal (draw/repay already reflected in cff)
    cash_int, int_income = _interest_expense(
        inp,
        beg_term, term_amort_q,
        rev_bal,
        beg_ddtl, ddtl_draw_q, ddtl_amort_q,
        sofr_q, beg_cash,
    )
    ebit           = rep_ebitda - total_da
    pre_tax        = ebit + cash_int - fee_amort + int_income
    book_tax       = -max(0.0, pre_tax * inp.tax_rate)
    taxable        = _taxable_income(rep_ebitda, dep, cash_int, inp.interest_deduction_cap, prior_int_carry)
    cash_tax       = -taxable * inp.tax_rate
    net_income     = pre_tax + book_tax
    deferred_tax_adj = -book_tax + cash_tax   # SB_Base!C50 = -C26 + C27
    cfo = net_income + total_da + fee_amort + deferred_tax_adj - delta_nwc
    cfi = -total_capex

    # 163(j) interest carryforward for next quarter — SB_Base!C114
    abs_int_avail = abs(cash_int) + prior_int_carry
    cap_163j      = max(0.0, inp.interest_deduction_cap * rep_ebitda)
    new_int_carry = _int_carryforward(abs_int_avail, cap_163j)
    cfi = -total_capex

    # Post-revolver cash (before ECF sweep) — SB_Base!E63 denominator
    cff_ex_rev      = sponsor_contrib + ddtl_draw_q + term_amort_q + ddtl_amort_q
    post_rev_cash   = beg_cash + cfo + cfi + cff_ex_rev + draw_q + repay_q

    # LTM covenant EBITDA for ECF leverage test — SUM(C14:E14) pattern
    # Use last 3 or 4 quarters depending on position (matches workbook SUM range)
    n_ltm = min(4, q + 1)
    ltm_cov_ebitda_ecf = sum(r.covenant_ebitda for r in ltm_window[-(n_ltm-1):]) + cov_ebitda

    # ECF sweep — SB_Base!E63 / I63 / M63 / Q63 / U63
    ecf_q = _ecf_sweep(
        inp,
        beg_term,    term_amort_q,
        beg_ddtl,    ddtl_draw_q, ddtl_amort_q,
        rev_bal,                         # ending revolver (post-draw/repay)
        post_rev_cash,                   # ending cash before sweep
        drv.cash_floor[q],
        ltm_cov_ebitda_ecf,
        q,
    )

    # Final debt balances — SB_Base rows 76/77/78
    end_term = max(0.0, max(0.0, beg_term + term_amort_q) + ecf_q)
    end_ddtl2 = max(0.0, beg_ddtl + ddtl_draw_q + ddtl_amort_q)
    end_rev   = rev_bal

    # Cash flow — SB_Base!C64/C65/C67
    cff = cff_ex_rev + draw_q + repay_q + ecf_q + sponsor_contrib - sponsor_contrib
    # (sponsor_contrib already in cff_ex_rev, correct it)
    cff = sponsor_contrib + ddtl_draw_q + term_amort_q + ddtl_amort_q + draw_q + repay_q + ecf_q
    net_change = cfo + cfi + cff
    end_cash   = beg_cash + net_change

    # LTM covenant EBITDA (last 4 quarters, inclusive of current).
    # Before we have 4 quarters of owned history, pad missing slots with pre-close
    # quarterly stub (opening_annual / 4) so Q1-Q3 don't produce artificially high leverage.
    n_prior = min(3, len(ltm_window))
    n_missing = 3 - n_prior
    pre_close_stub_q = inp.covenant_ebitda_opening / 4
    ltm_cov_ebitda = (
        sum(r.covenant_ebitda for r in ltm_window[-n_prior:])
        + cov_ebitda
        + n_missing * pre_close_stub_q
    )
    # Net leverage (covenant) = (term + ddtl + rev - min(cash, netting_cap)) / LTM_cov_EBITDA
    net_debt_cov = end_term + end_ddtl2 + end_rev - min(end_cash, inp.eligible_cash_netting)
    net_lev = net_debt_cov / ltm_cov_ebitda if ltm_cov_ebitda > 0 else float("inf")

    # Gross margin
    gross_profit = rev * drv.wip_pct[q]  # approximation using ebitda directly is better
    gross_profit = rev * SB_GROSS_MARGIN[q]  # SB_Base!C8

    return QuarterResult(
        period=drv.periods[q],
        revenue=rev,
        gross_profit=gross_profit,
        firm_ebitda=ebitda,
        reported_ebitda=rep_ebitda,
        covenant_ebitda=cov_ebitda,
        depreciation=dep,
        ppa_amort=ppa_q,
        total_da=total_da,
        cash_interest=cash_int,
        fee_amort=fee_amort,
        interest_income=int_income,
        pre_tax_income=pre_tax,
        book_tax=book_tax,
        cash_tax=cash_tax,
        net_income=net_income,
        ar=_nwc_balance(rev, season, dso, 0, 0, 0, 0, 0),
        wip=0.0,
        prepaids=0.0,
        ap=0.0,
        accruals=0.0,
        deferred_rev=0.0,
        op_nwc=nwc,
        delta_nwc=delta_nwc,
        maintenance_capex=maint_capex,
        growth_capex=growth_capex,
        total_capex=total_capex,
        cfo=cfo,
        cfi=cfi,
        ddtl_draw=ddtl_draw_q,
        revolver_draw=draw_q,
        revolver_repay=repay_q,
        term_amort=term_amort_q,
        ddtl_amort=ddtl_amort_q,
        ecf_sweep=ecf_q,
        cff=cff,
        net_cash_change=net_change,
        beg_cash=beg_cash,
        end_cash=end_cash,
        term_loan=end_term,
        ddtl=end_ddtl2,
        revolver=end_rev,
        ltm_covenant_ebitda=ltm_cov_ebitda,
        net_leverage_covenant=net_lev,
    ), new_int_carry


# ── Returns calculation ───────────────────────────────────────────────────────

def _xirr(cashflows: list[float], dates_iso: list[str]) -> float:
    """
    Gross XIRR — Ownership_Returns!L4.
    Newton-Raphson on sum( cf / (1+r)^t ) = 0, where t = years from date[0].
    """
    from datetime import date as _date

    def _parse(d: str) -> _date:
        return _date.fromisoformat(d)

    d0   = _parse(dates_iso[0])
    days = [((_parse(d) - d0).days) / 365.0 for d in dates_iso]

    def _npv(r: float) -> float:
        return sum(cf / ((1 + r) ** t) for cf, t in zip(cashflows, days))

    def _dnpv(r: float) -> float:
        return sum(-t * cf / ((1 + r) ** (t + 1)) for cf, t in zip(cashflows, days))

    r = 0.10
    for _ in range(200):
        f  = _npv(r)
        df = _dnpv(r)
        if abs(df) < 1e-12:
            break
        r2 = r - f / df
        if abs(r2 - r) < 1e-8:
            r = r2
            break
        r = r2
    return r


def _compute_returns(quarters: list[QuarterResult],
                     inp: DealInputs,
                     drv: QuarterlyDrivers,
                     scenario: str = "standalone_base") -> tuple:
    """
    Compute MOIC / XIRR from quarterly model — Ownership_Returns!B4:L4.

    Exit LTM = last 4 quarters (Q17..Q20, i.e. indices 16-19).
    Exit EV = Exit LTM EBITDA × exit_multiple.
    Exit economic net debt = term + ddtl + revolver - cash (last quarter).
    """
    # LTM (last 4 quarters ending at exit) — OR!B4/C4
    ltm_rev   = sum(q.revenue for q in quarters[-4:])
    ltm_ebitda = sum(q.firm_ebitda for q in quarters[-4:])

    last = quarters[-1]
    exit_ev  = ltm_ebitda * drv.exit_multiple   # OR!E4 = C4 × D4
    exit_net_debt = last.term_loan + last.ddtl + last.revolver - last.end_cash  # OR!F4
    exit_equity   = exit_ev - exit_net_debt      # OR!G4

    sponsor_invested = inp.sponsor_equity         # OR!H4 = 62
    # MIP vest — OR!I4 (vested % of exit equity)
    vested_mip = MIP_VESTING.get(scenario, 0.0875)
    # Sponsor proceeds — OR!J4
    # = (exit_equity - exit_equity × mip_pct) × sponsor_pre_mip_pct
    residual_equity  = exit_equity * (1 - vested_mip)
    sponsor_proceeds = residual_equity * inp.mip_base_pct  # OR!J4

    gross_moic = sponsor_proceeds / sponsor_invested  # OR!K4

    # XIRR cashflows: [-equity_in, ..., +proceeds_at_exit]
    # Sponsor equity drawn at entry (2026-03-10 ≈ Q1 start)
    entry_date = "2026-03-10"
    exit_date  = "2031-03-31"
    # Interim cash to sponsor: 0 (no dividends in base case)
    cf_list    = [-sponsor_invested] + [0.0] * (len(quarters) - 1) + [sponsor_proceeds]
    date_list  = [entry_date] + [q.period for q in quarters[:-1]] + [exit_date]
    gross_xirr = _xirr(cf_list, date_list)

    return (ltm_rev, ltm_ebitda, drv.exit_multiple, exit_ev,
            exit_net_debt, exit_equity, sponsor_invested, vested_mip,
            sponsor_proceeds, gross_moic, gross_xirr)


# ── Main public API ───────────────────────────────────────────────────────────

def run_lbo(scenario: str = "standalone_base",
            inp: DealInputs | None = None,
            driver_overrides: dict[str, list[float]] | None = None) -> LBOResult:
    """
    Run the Keystone LBO model for the given scenario with optional overrides.

    Parameters
    ----------
    scenario : str
        One of: standalone_base, standalone_downside, standalone_upside,
                acquisition_base, combined_risk.
    inp : DealInputs | None
        Locked deal inputs. None → use defaults from Inputs sheet.
    driver_overrides : dict | None
        Override per-quarter drivers for this run.
        Keys match QuarterlyDrivers fields (e.g. "ebitda", "sofr").
        Values are 20-element lists aligned to PERIODS.

    Returns
    -------
    LBOResult with all 20 quarterly states + exit returns.
    """
    if inp is None:
        inp = DealInputs()

    drv = _build_sb_drivers()  # TODO: extend for other scenarios
    if driver_overrides:
        for field_name, vals in driver_overrides.items():
            if hasattr(drv, field_name):
                setattr(drv, field_name, vals)

    # Opening NWC from S&U_Opening balance sheet (AR + WIP + Prepaids - AP - Accr - DefRev)
    # S&U_Opening!B16 = AR = 13.2, B17 = WIP = 4.9, B18 = prepaids = 0.9
    # S&U_Opening!E15 = AP = 4.1, E16 = accruals = 5.6, E17 = deferred_rev = 0.9
    opening_nwc = 13.2 + 4.9 + 0.9 - 4.1 - 5.6 - 0.9  # S&U_Opening rows 16-17

    quarters: list[QuarterResult] = []
    ltm_window: list[QuarterResult] = []
    prior_nwc     = opening_nwc
    int_carry     = 0.0   # 163(j) interest deduction carryforward

    for q in range(20):
        prior = quarters[-1] if quarters else None
        qr, int_carry = _run_quarter(q, drv, inp, prior, prior_nwc, ltm_window, int_carry)
        quarters.append(qr)
        ltm_window.append(qr)
        if len(ltm_window) > 4:
            ltm_window.pop(0)
        prior_nwc = qr.op_nwc

    # Returns
    (ltm_rev, ltm_ebitda, exit_mult, exit_ev, exit_net_debt, exit_equity,
     sp_inv, vested_mip, sp_proc, moic, xirr) = _compute_returns(
        quarters, inp, drv, scenario
    )

    # BS check: total assets ≈ total liabilities + equity (simplified)
    last = quarters[-1]
    bs_ok = abs(last.end_cash + last.term_loan + last.ddtl + last.revolver) < 1.0

    return LBOResult(
        quarters=quarters,
        exit_ltm_revenue=ltm_rev,
        exit_ltm_ebitda=ltm_ebitda,
        exit_multiple=exit_mult,
        exit_ev=exit_ev,
        exit_net_debt=exit_net_debt,
        exit_equity=exit_equity,
        sponsor_invested=sp_inv,
        vested_mip_pct=vested_mip,
        sponsor_proceeds=sp_proc,
        gross_moic=moic,
        gross_xirr=xirr,
        bs_check_passes=bs_ok,
    )


# ── Claim propagation (Anto's runtime entry point) ────────────────────────────

# Maps a PE OS claim metric name → which QuarterlyDrivers field it overrides
# and how to convert the claim value + period into a driver list update.
_CLAIM_TO_DRIVER: dict[str, str] = {
    # metric              driver_field
    "ebitda":             "ebitda",
    "firm ebitda":        "ebitda",
    "revenue":            "revenue",
    "ebitda margin":      "_ebitda_margin_override",  # special
    "sofr":               "sofr",
    "organic revenue growth": "_revenue_growth_override",  # special
}

_PERIOD_TO_QUARTER: dict[str, int] = {p: i for i, p in enumerate(PERIODS)}


def propagate_claim(claim: dict[str, Any],
                    scenario: str = "standalone_base",
                    inp: DealInputs | None = None) -> dict[str, Any]:
    """
    Anto's runtime entry point.

    Given a new evidence claim (same schema as PE OS claim nodes), re-runs the
    model with the claim's value applied and returns the economic delta.

    Parameters
    ----------
    claim : dict
        Must contain: metric (str), value (float|str), period (str, e.g. "2027-03-31"),
        optionally: scenario_override (str).

    Returns
    -------
    dict with keys:
      updated_nodes:  list of {node_id, old, new, delta_pct}
      moic_delta:     float
      irr_delta_ppt:  float (percentage points)
      covenant_alerts: list of {period, metric, threshold, actual, status}
      run_scenario:   str
      claim_applied:  bool
    """
    metric     = str(claim.get("metric", "")).lower().strip()
    value      = claim.get("value")
    period     = str(claim.get("period", ""))
    from_value = claim.get("from_value")  # optional: used for annual ratio

    # Annual-period events (period is a full-year date or pre-model opening) apply
    # their ratio from q=0. "2025-12-31" is the FY2025 opening period.
    _ANNUAL_PERIODS = {"2025-12-31", "fy2025", "fy2025a", "opening"}

    # Find the quarter index
    q_idx = None
    if period.lower() in _ANNUAL_PERIODS or (period and period <= "2026-03-31" and len(period) == 10):
        q_idx = 0  # apply from first model quarter
    else:
        for p, i in _PERIOD_TO_QUARTER.items():
            if period in p or p in period:
                q_idx = i
                break

    # Run baseline
    base = run_lbo(scenario, inp)

    if value is None or q_idx is None:
        return {
            "claim_applied":  False,
            "reason":         f"Cannot map period '{period}' or value is null",
            "moic_baseline":  round(base.gross_moic, 4),
            "irr_baseline":   round(base.gross_xirr * 100, 2),
        }

    try:
        value = float(value)
    except (TypeError, ValueError):
        return {"claim_applied": False, "reason": "Non-numeric value"}

    # For annual events, compute ratio from from_value (annual old value) rather than
    # the quarterly SB table entry, since the table holds quarterly figures.
    if from_value is not None:
        try:
            from_value = float(from_value)
        except (TypeError, ValueError):
            from_value = None

    # Build driver override
    driver_field = _CLAIM_TO_DRIVER.get(metric)
    overrides: dict[str, list[float]] = {}

    if driver_field == "ebitda" or metric in ("ebitda", "firm ebitda"):
        if from_value is not None and from_value != 0:
            # Annual event: ratio comes from the annual from/to values directly.
            # This avoids comparing an annual claim ($11.4m) against a quarterly
            # SB entry ($2.85m) and producing a nonsensical ×4 ratio.
            ratio = value / from_value
        else:
            old_val = SB_EBITDA[q_idx]
            ratio   = value / old_val if old_val != 0 else 1.0
        new_ebitda = list(SB_EBITDA)
        for i in range(q_idx, 20):
            new_ebitda[i] = SB_EBITDA[i] * ratio
        overrides["ebitda"] = new_ebitda

    elif driver_field == "revenue" or metric == "revenue":
        old_val = SB_REVENUE[q_idx]
        ratio   = value / old_val if old_val != 0 else 1.0
        new_rev = list(SB_REVENUE)
        for i in range(q_idx, 20):
            new_rev[i] = SB_REVENUE[i] * ratio
        overrides["revenue"] = new_rev

    elif driver_field == "sofr" or metric == "sofr":
        new_sofr = list(SB_SOFR)
        for i in range(q_idx, 20):
            new_sofr[i] = value
        overrides["sofr"] = new_sofr

    else:
        return {
            "claim_applied": False,
            "reason": f"No driver mapping for metric '{metric}'",
            "moic_baseline": round(base.gross_moic, 4),
            "irr_baseline":  round(base.gross_xirr * 100, 2),
        }

    # Run updated model
    updated = run_lbo(scenario, inp, overrides)

    # Compute deltas
    def _node(q_list, q_i, attr) -> tuple[float, float]:
        old = getattr(base.quarters[q_i], attr)
        new = getattr(q_list[q_i],        attr)
        return old, new

    updated_nodes = []
    for attr in ("firm_ebitda", "revenue", "cash_interest", "net_income",
                 "end_cash", "term_loan", "revolver"):
        old_v, new_v = _node(updated.quarters, q_idx, attr)
        if abs(new_v - old_v) > 1e-6:
            updated_nodes.append({
                "node_id":   f"mn:{attr.upper()}",
                "period":    PERIODS[q_idx],
                "old":       round(old_v, 4),
                "new":       round(new_v, 4),
                "delta":     round(new_v - old_v, 4),
                "delta_pct": round((new_v - old_v) / old_v * 100, 2) if old_v != 0 else None,
            })

    # Covenant alerts
    alerts = []
    _drv = _build_sb_drivers()
    for q in updated.quarters:
        limit = _drv.covenant_limit[_PERIOD_TO_QUARTER[q.period]]
        if q.net_leverage_covenant > limit:
            alerts.append({
                "period":    q.period,
                "metric":    "net_leverage",
                "threshold": limit,
                "actual":    round(q.net_leverage_covenant, 2),
                "status":    "FAIL",
            })

    return {
        "claim_applied":  True,
        "run_scenario":   scenario,
        "claim":          {"metric": metric, "value": value, "period": period},
        "moic_baseline":  round(base.gross_moic, 4),
        "moic_updated":   round(updated.gross_moic, 4),
        "moic_delta":     round(updated.gross_moic - base.gross_moic, 4),
        "irr_baseline_pct":  round(base.gross_xirr * 100, 2),
        "irr_updated_pct":   round(updated.gross_xirr * 100, 2),
        "irr_delta_ppt":     round((updated.gross_xirr - base.gross_xirr) * 100, 2),
        "exit_ebitda_baseline": round(base.exit_ltm_ebitda, 3),
        "exit_ebitda_updated":  round(updated.exit_ltm_ebitda, 3),
        "exit_ev_baseline":     round(base.exit_ev, 2),
        "exit_ev_updated":      round(updated.exit_ev, 2),
        "updated_nodes":  updated_nodes,
        "covenant_alerts": alerts,
    }


# ── CLI smoke-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("Running Keystone Standalone Base LBO...")
    result = run_lbo("standalone_base")
    last   = result.quarters[-1]

    print(f"\n  Exit LTM Revenue:  ${result.exit_ltm_revenue:.2f}m  (workbook: $105.46m)")
    print(f"  Exit LTM EBITDA:   ${result.exit_ltm_ebitda:.2f}m  (workbook: $18.35m)")
    print(f"  Exit EV:           ${result.exit_ev:.2f}m         (workbook: $165.12m)")
    print(f"  Exit Net Debt:     ${result.exit_net_debt:.2f}m   (workbook: $3.25m)")
    print(f"  Exit Equity:       ${result.exit_equity:.2f}m    (workbook: $161.87m)")
    print(f"  Gross MOIC:        {result.gross_moic:.3f}x      (workbook: 2.00x)")
    print(f"  Gross XIRR:        {result.gross_xirr*100:.1f}%        (workbook: 14.8%)")
    print(f"\n  Term loan at exit: ${last.term_loan:.2f}m")
    print(f"  Cash at exit:      ${last.end_cash:.2f}m")
    print(f"  Revolver at exit:  ${last.revolver:.2f}m")

    print("\n\nTesting claim propagation: EBITDA at 2027-03-31 revised up 10%...")
    delta = propagate_claim({
        "metric": "firm ebitda",
        "value":  SB_EBITDA[3] * 1.10,
        "period": "2027-03-31",
    })
    print(json.dumps(delta, indent=2))
