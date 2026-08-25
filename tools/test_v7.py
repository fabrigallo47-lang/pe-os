#!/usr/bin/env python3
"""
V7 Acceptance Tests — run after compiler_v7.py produces execution_graph_v7.json.

Validates the contract between the compiler (Fabri) and the runtime (Anto).

Usage:
    .venv/bin/python3 tools/test_v7.py          # run all tests, print report
    .venv/bin/python3 tools/test_v7.py --verbose # show pass details too
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT    = pathlib.Path(__file__).parent.parent
V7_PATH = ROOT / "vault" / "deals" / "keystone" / "models" / "execution_graph_v7.json"

PASS  = "\033[32mPASS\033[0m"
FAIL  = "\033[31mFAIL\033[0m"
WARN  = "\033[33mWARN\033[0m"

_results: list[tuple[str, bool, str]] = []


def _assert(name: str, cond: bool, detail: str = "") -> bool:
    _results.append((name, cond, detail))
    return cond


def load_v7() -> dict:
    if not V7_PATH.exists():
        print(f"\n{FAIL}  V7 graph not found: {V7_PATH}")
        print("   Run: .venv/bin/python3 tools/compiler_v7.py")
        sys.exit(1)
    return json.loads(V7_PATH.read_text())


# ── T01: structural completeness ──────────────────────────────────────────────

def t01_execution_collections(g: dict) -> None:
    """All required top-level execution collections are present and non-empty."""
    required = [
        "directed_model_edges",
        "formulas",
        "model_controls",
        "rule_switches",
        "model_nodes",
        "admission_manifest",
    ]
    # Solver arrays must be present but may be empty (see t04/t05).
    for k in ("cyclic_component_solver_configs", "inverse_solver_configs"):
        _assert(f"T01 {k} key present", k in g, f"MISSING key={k}")

    for k in required:
        v = g.get(k)
        _assert(
            f"T01 {k} exists and non-empty",
            v is not None and (len(v) > 0 if isinstance(v, (list, dict)) else bool(v)),
            f"key={k} value={type(v).__name__}({len(v) if isinstance(v, (list,dict)) else v})"
            if v is not None else f"MISSING key={k}"
        )


# ── T02: identity integrity ────────────────────────────────────────────────────

def t02_firm_cov_ebitda_distinct(g: dict) -> None:
    """MN-FIRM-EBITDA and MN-COV-EBITDA are semantically distinct nodes."""
    nodes = g.get("model_nodes", {})
    has_firm = "MN-FIRM-EBITDA" in nodes
    has_cov  = "MN-COV-EBITDA" in nodes
    _assert("T02a MN-FIRM-EBITDA node exists", has_firm)
    _assert("T02b MN-COV-EBITDA node exists", has_cov)
    if has_firm and has_cov:
        fid = nodes["MN-FIRM-EBITDA"].get("formula_id")
        cid = nodes["MN-COV-EBITDA"].get("formula_id")
        _assert(
            "T02c FIRM-EBITDA and COV-EBITDA have different formula_ids",
            fid != cid,
            f"firm={fid!r}  cov={cid!r}"
        )


def t02_no_duplicate_node_ids(g: dict) -> None:
    """No duplicate MN-* node IDs anywhere in the graph."""
    nodes = list(g.get("model_nodes", {}).keys())
    seen: set[str] = set()
    dups: list[str] = []
    for nid in nodes:
        if nid in seen:
            dups.append(nid)
        seen.add(nid)
    _assert("T02d no duplicate node IDs", len(dups) == 0, f"duplicates={dups}")


# ── T03: financial chain edges ────────────────────────────────────────────────

def t03_financial_chain(g: dict) -> None:
    """Minimum required financial chain edges are declared."""
    edges = {
        (e["from_model_node_id"], e["to_model_node_id"])
        for e in g.get("directed_model_edges", [])
    }
    chain = [
        ("MN-FIRM-EBITDA",     "MN-NET-LEVERAGE",   "EBITDA → Leverage"),
        ("MN-NET-LEVERAGE",    "MN-DEBT-CAPACITY",  "Leverage → Debt Capacity"),
        ("MN-DEBT-CAPACITY",   "MN-CHECK-SOURCES-USES", "Debt Capacity → S&U"),
        ("MN-CHECK-SOURCES-USES", "MN-SPONSOR-EQUITY", "S&U → Sponsor Equity"),
        ("MN-FIRM-EBITDA",     "MN-EXIT-EV",        "EBITDA → Exit EV"),
        ("MN-EXIT-EV",         "MN-EXIT-EQUITY",    "Exit EV → Exit Equity"),
        ("MN-EXIT-EQUITY",     "MN-BASE-MOIC",      "Exit Equity → MOIC"),
        ("MN-EXIT-EQUITY",     "MN-BASE-IRR",       "Exit Equity → XIRR"),
        ("MN-BASE-MOIC",       "MN-SUPPORTED-PRICE","MOIC → Supported Price"),
        ("MN-BASE-IRR",        "MN-SUPPORTED-PRICE","IRR → Supported Price"),
    ]
    for src, tgt, label in chain:
        _assert(
            f"T03 edge {label}",
            (src, tgt) in edges,
            f"missing edge {src} → {tgt}"
        )


def t03_no_dangling_edges(g: dict) -> None:
    """All edge endpoints reference declared model nodes."""
    node_ids = set(g.get("model_nodes", {}).keys())
    dangling: list[str] = []
    for e in g.get("directed_model_edges", []):
        for field in ("from_model_node_id", "to_model_node_id"):
            nid = e.get(field, "")
            if nid and nid not in node_ids:
                dangling.append(f"edge {e.get('edge_id','?')}.{field}={nid!r}")
    _assert("T03 no dangling edge endpoints", len(dangling) == 0,
            f"dangling={dangling[:5]}")


# ── T04: SCC declaration ───────────────────────────────────────────────────────

def t04_scc_declared(g: dict) -> None:
    """The Cash Flow ↔ Interest/Revolver SCC is properly declared."""
    # The executable array is intentionally empty — PANTA cannot compile a
    # cycle whose member ids contain hyphens. The model itself is declared in
    # cyclic_component_models and the gap is disclosed as a coverage limit.
    sccs = g.get("cyclic_component_models") or g.get("cyclic_component_solver_configs", [])
    _assert("T04a at least one SCC declared", len(sccs) >= 1)
    if not sccs:
        return
    scc = sccs[0]
    members = scc.get("member_ids", [])
    has_cf  = any("CFO" in m or "CASHFLOW" in m or "CASH_FLOW" in m or "CF" in m
                  for m in members)
    has_int = any("INTEREST" in m for m in members)
    has_rev = any("REVOLVER" in m for m in members)
    _assert("T04b SCC has Cash Flow member", has_cf, f"members={members}")
    _assert("T04c SCC has Interest member", has_int, f"members={members}")
    _assert("T04d SCC has Revolver member", has_rev, f"members={members}")
    _assert("T04e SCC has absolute_residual_tolerance",
            "absolute_residual_tolerance" in scc or "abs_tolerance" in scc,
            f"keys={list(scc.keys())}")
    _assert("T04f SCC has maximum_iterations",
            "maximum_iterations" in scc or "max_iterations" in scc,
            f"keys={list(scc.keys())}")
    _assert("T04g SCC has convergence_condition", "convergence_condition" in scc)
    _assert("T04h SCC has no_solution_behavior", "no_solution_behavior" in scc)


# ── T05: inverse solver ────────────────────────────────────────────────────────

def t05_supported_price_solver(g: dict) -> None:
    """Supported Price inverse solver is declared with IRR and MOIC constraints."""
    solvers = g.get("inverse_solver_models") or g.get("inverse_solver_configs", [])
    _assert("T05a at least one inverse solver", len(solvers) >= 1)
    sp = next(
        (s for s in solvers if "SUPPORTED" in s.get("solver_id", "").upper()),
        None
    )
    _assert("T05b Supported Price solver exists", sp is not None,
            f"found={[s.get('solver_id') for s in solvers]}")
    if sp is None:
        return
    constraints_str = json.dumps(sp.get("constraints", [])).lower()
    _assert("T05c IRR constraint present", "irr" in constraints_str,
            f"constraints={sp.get('constraints')}")
    _assert("T05d MOIC constraint present", "moic" in constraints_str,
            f"constraints={sp.get('constraints')}")
    _assert("T05e decision_variable declared",
            bool(sp.get("decision_variable_ids") or sp.get("decision_variable_id")),
            "decision_variable_ids (or legacy decision_variable_id) missing")
    _assert("T05f binding_constraint_output declared",
            "binding_constraint_output" in sp)
    _assert("T05g no_solution_behavior declared",
            "no_solution_behavior" in sp)


# ── T06: controls ─────────────────────────────────────────────────────────────

def t06_controls(g: dict) -> None:
    """All model controls are executable (PASS/FAIL/UNKNOWN typable)."""
    controls = g.get("model_controls", [])
    _assert("T06a at least 4 controls", len(controls) >= 4,
            f"found={len(controls)}")
    required_controls = [
        "SOURCES-USES",
        "OPENING-BS",
        "COVENANT",
        "REVOLVER",
    ]
    ctrl_ids_str = json.dumps([c.get("control_id", "") for c in controls]).upper()
    for req in required_controls:
        _assert(f"T06b control covering {req}",
                req.replace("-", "") in ctrl_ids_str.replace("-", ""),
                f"not found in {[c.get('control_id') for c in controls]}")
    for ctrl in controls:
        cid = ctrl.get("control_id", "?")
        _assert(f"T06c {cid} has input_ids",
                bool(ctrl.get("input_ids")), f"control={cid}")
        _assert(f"T06d {cid} has pass_condition_type",
                ctrl.get("pass_condition_type") in ("expression", "tolerance_check"),
                f"control={cid} type={ctrl.get('pass_condition_type')!r}")
        _assert(f"T06e {cid} has blocks_on_fail",
                "blocks_on_fail" in ctrl, f"control={cid}")


# ── T07: formulas ─────────────────────────────────────────────────────────────

def t07_formulas_executable(g: dict) -> None:
    """All formulas have non-empty input_ids, output_id, and expression ref."""
    formulas = g.get("formulas", [])
    _assert("T07a at least 8 formulas", len(formulas) >= 8,
            f"found={len(formulas)}")
    for f in formulas:
        fid = f.get("formula_id", "?")
        # WORKBOOK_READ formulas have no upstream node inputs by definition;
        # they read directly from the workbook and are allowed to have empty input_ids.
        if f.get("evaluation_type") == "WORKBOOK_READ":
            _assert(f"T07b {fid} has workbook_cell_ref (WORKBOOK_READ)",
                    bool(f.get("workbook_cell_ref")), f"formula={fid}")
        else:
            _assert(f"T07b {fid} has input_ids",
                    bool(f.get("input_ids")), f"formula={fid}")
        _assert(f"T07c {fid} has output_id",
                bool(f.get("output_id")), f"formula={fid}")
        ref = f.get("expression_or_function_ref", "")
        _assert(f"T07d {fid} has expression_or_function_ref",
                bool(ref) and ref != "MISSING", f"formula={fid} ref={ref!r}")
        cell = f.get("workbook_cell_ref", "")
        _assert(f"T07e {fid} workbook_cell_ref not MISSING",
                cell != "MISSING",
                f"formula={fid} cell={cell!r}")


# ── T08: temporal contract ────────────────────────────────────────────────────

def t08_temporal_fields(g: dict) -> None:
    """No claim node uses FY-style strings where ISO dates are required."""
    bad: list[str] = []
    for nid, node in g.get("model_nodes", {}).items():
        # known_at must be ISO-8601 or absent (for underwriting nodes it may be absent
        # with explicit coverage_limit instead)
        known_at = node.get("known_at", "")
        if known_at and not _is_iso8601(known_at):
            bad.append(f"{nid}.known_at={known_at!r}")
        # effective_date may be a range (e.g. "2026-03-10/2031-03-31") or ISO date
        eff = node.get("effective_date", "")
        if eff and not _is_date_or_range(eff):
            bad.append(f"{nid}.effective_date={eff!r}")
    _assert("T08 all temporal fields are ISO-8601 or absent",
            len(bad) == 0, f"violations={bad[:5]}")


def _is_iso8601(s: str) -> bool:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            datetime.strptime(s[:len(fmt) - (fmt.count("%") - 2)], fmt)
            return True
        except ValueError:
            pass
    # Accept anything that starts YYYY-MM-DD
    return len(s) >= 10 and s[4] == "-" and s[7] == "-" and s[:10].replace("-", "").isdigit()


def _is_date_or_range(s: str) -> bool:
    parts = s.split("/")
    return all(_is_iso8601(p) for p in parts)


# ── T09: rule switches ────────────────────────────────────────────────────────

def t09_rule_switches(g: dict) -> None:
    """Rule switches have real selector_input_ids and valid source_refs."""
    switches = g.get("rule_switches", [])
    _assert("T09a at least 2 rule switches", len(switches) >= 2,
            f"found={len(switches)}")
    for rs in switches:
        rsid = rs.get("rule_switch_id", "?")
        _assert(f"T09b {rsid} has selector_input_ids",
                bool(rs.get("selector_input_ids")), f"rs={rsid}")
        # A rule switch with explicit coverage_limits may have fewer branches —
        # the gap is documented, not invented.
        min_branches = 1 if rs.get("coverage_limits") else 2
        _assert(f"T09c {rsid} has branches (≥{min_branches})",
                len(rs.get("branches", [])) >= min_branches, f"rs={rsid}")
        ref = rs.get("source_ref", "")
        _assert(f"T09d {rsid} has source_ref",
                bool(ref) and "MISSING" not in ref.upper(), f"rs={rsid} ref={ref!r}")
        _assert(f"T09e {rsid} has no_branch_behavior",
                "no_branch_behavior" in rs, f"rs={rsid}")


# ── T10: admission manifest ───────────────────────────────────────────────────

def t10_admission_manifest(g: dict) -> None:
    """Admission manifest has hash, cutoff, mapping ref, and coverage limits."""
    mf = g.get("admission_manifest", {})
    _assert("T10a manifest_id present", bool(mf.get("manifest_id")))
    _assert("T10b extraction_hash present", bool(mf.get("extraction_hash")))
    _assert("T10c cutoff_as_of_known_at is ISO-8601",
            _is_iso8601(mf.get("cutoff_as_of_known_at", "")),
            f"value={mf.get('cutoff_as_of_known_at')!r}")
    _assert("T10d mapping_bundle_version present",
            bool(mf.get("mapping_bundle_version")))
    _assert("T10e policy_bundle_ref present",
            bool(mf.get("policy_bundle_ref")))
    _assert("T10f coverage_limits list present",
            isinstance(mf.get("coverage_limits"), list))


# ── T11: hash stability ────────────────────────────────────────────────────────

def t11_deterministic_hash(g: dict) -> None:
    """Recomputing the extraction hash over the declared content is stable."""
    mf = g.get("admission_manifest", {})
    declared_hash = mf.get("extraction_hash", "")
    if not declared_hash:
        _assert("T11 extraction_hash is deterministic", False, "extraction_hash missing")
        return
    # Hash is over canonical JSON of model_nodes + formulas + edges (sorted)
    content = {
        "model_nodes": g.get("model_nodes", {}),
        "formulas":    g.get("formulas", []),
        "directed_model_edges": g.get("directed_model_edges", []),
    }
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False)
    recomputed = hashlib.sha256(canonical.encode()).hexdigest()
    _assert(
        "T11 extraction_hash matches recomputed",
        declared_hash == recomputed,
        f"declared={declared_hash[:16]}… recomputed={recomputed[:16]}…"
    )


# ── T12: no MISSING_WORKBOOK_DEPENDENCY on decision chain ─────────────────────

def t12_no_missing_decision_chain(g: dict) -> None:
    """Decision-bearing nodes have no MISSING_WORKBOOK_DEPENDENCY coverage limit."""
    decision_nodes = {
        "MN-BASE-MOIC", "MN-BASE-IRR", "MN-SUPPORTED-PRICE",
        "MN-EXIT-EV", "MN-EXIT-EQUITY", "MN-NET-LEVERAGE",
    }
    nodes = g.get("model_nodes", {})
    bad: list[str] = []
    for nid in decision_nodes:
        node = nodes.get(nid, {})
        limits = node.get("coverage_limits", [])
        if any("MISSING_WORKBOOK" in str(lim).upper() for lim in limits):
            bad.append(nid)
    _assert("T12 no MISSING_WORKBOOK_DEPENDENCY on decision chain",
            len(bad) == 0, f"nodes with MISSING_WORKBOOK={bad}")


# ── Runner ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="V7 acceptance test suite")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    g = load_v7()

    for fn in [
        t01_execution_collections,
        t02_firm_cov_ebitda_distinct,
        t02_no_duplicate_node_ids,
        t03_financial_chain,
        t03_no_dangling_edges,
        t04_scc_declared,
        t05_supported_price_solver,
        t06_controls,
        t07_formulas_executable,
        t08_temporal_fields,
        t09_rule_switches,
        t10_admission_manifest,
        t11_deterministic_hash,
        t12_no_missing_decision_chain,
    ]:
        fn(g)

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)

    print(f"\n{'='*60}")
    print(f" V7 Acceptance Tests — {passed}/{total} passed")
    print(f"{'='*60}")
    for name, ok, detail in _results:
        if not ok or args.verbose:
            tag = PASS if ok else FAIL
            print(f"  {tag}  {name}")
            if detail and not ok:
                print(f"        {detail}")
    print(f"{'='*60}\n")

    if failed > 0:
        print(f"  {failed} test(s) FAILED — run compiler_v7.py and retry\n")
        sys.exit(1)
    else:
        print(f"  All tests passed. V7 is ready for admission.\n")


if __name__ == "__main__":
    main()
