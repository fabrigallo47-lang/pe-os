#!/usr/bin/env python3
"""
Regression suite for defects found in the 2026-08-25 audit.

Each test pins a bug that was silent — the code ran, produced plausible output,
and was wrong. They are grouped by the defect they prevent from returning.

  python3 tools/test_regression.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import runtime as rt
from tools import deal_profile as dp
from tools import minigraph as mg
from tools import grounding_gate as gg
from tools.deal_profile import DealProfile

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f"  [{detail}]" if detail else ""))


# ── 1. Model-graph shape: the staleness cascade ──────────────────────────────
# model_graph.json is a flat adjacency map. Three call sites read it as
# {"nodes": [...], "dependencies": {...}}, so subject lookup returned None and
# the cascade walked zero edges — it marked 1 node instead of 40.

def test_cascade() -> None:
    print("\n1. Staleness cascade over a flat adjacency graph")
    flat = {
        "MN-QOE-EBITDA":  ["MN-BASE-MOIC", "MN-BASE-IRR"],
        "MN-BASE-MOIC":   ["MN-EXIT"],
        "MN-BASE-IRR":    [],
        "MN-EXIT":        [],
        "MN-FIRM-EBITDA": [],
        "stale_nodes":    ["MN-QOE-EBITDA"],      # marker, never a node
    }
    check("subject resolves on adjacency shape",
          rt._node_for_subject(flat, "QoE-normalized EBITDA") == "MN-QOE-EBITDA")
    check("generic EBITDA falls back to firm basis",
          rt._node_for_subject(flat, "EBITDA") == "MN-FIRM-EBITDA")
    check("'stale_nodes' is not treated as a model node",
          "stale_nodes" not in [n["model_node_id"] for n in
                                ([{"model_node_id": k} for k in flat
                                  if k not in rt._GRAPH_RESERVED_KEYS])])

    # richer shape must still work
    rich = {"nodes": [{"model_node_id": "MN-QOE-EBITDA", "name": "QoE EBITDA"}],
            "dependencies": {"MN-QOE-EBITDA": []}}
    check("richer {'nodes':[...]} shape still resolves",
          rt._node_for_subject(rich, "QoE EBITDA") == "MN-QOE-EBITDA")

    # cascade must walk transitively: QOE -> {MOIC, IRR} -> EXIT  == 4 nodes
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        deal_dir = Path(td) / "deals" / "t" / "models"
        deal_dir.mkdir(parents=True)
        (deal_dir / "model_graph.json").write_text(json.dumps(
            {k: v for k, v in flat.items() if k != "stale_nodes"}))
        old_vault = rt.VAULT
        try:
            rt.VAULT = Path(td)
            g = json.loads((deal_dir / "model_graph.json").read_text())
            chain = rt._mark_model_node_stale("t", g, "MN-QOE-EBITDA")
        finally:
            rt.VAULT = old_vault
    check("cascade walks transitively, not just the trigger node",
          len(chain) == 4, f"marked {len(chain)}: {chain}")


# ── 2. Benchmark scorer field name ───────────────────────────────────────────
# The scorer read item["epistemic"]; extract_v2 emits "epistemic_class", so the
# epistemic dimension scored 0.0% by construction regardless of quality.

def test_benchmark_field() -> None:
    print("\n2. Benchmark reads the epistemic field the extractor writes")
    src = (ROOT / "tools" / "benchmark_runner.py").read_text()
    check("scorer accepts epistemic_class",
          'item.get("epistemic_class")' in src)
    e3 = json.loads((ROOT / "pipeline_out/e3/K-IC/e3_claims.json").read_text())
    claims = e3.get("claims", [])
    if claims:
        keys = set(claims[0])
        check("extractor really emits 'epistemic_class', not 'epistemic'",
              "epistemic_class" in keys and "epistemic" not in keys)


# ── 3. Deal profile: no cross-deal perimeter leakage ─────────────────────────
# bridge_v7 defaulted a missing perimeter to the literal "Alderstone standalone",
# so any second deal would carry Alderstone's economic scope.

def test_deal_profile() -> None:
    print("\n3. Deal profile never lends one deal's perimeter to another")
    empty = DealProfile("other-deal")
    check("unknown deal gets no perimeter, not a borrowed one",
          empty.cp_perimeter("CP-EBITDA-FIRM", None) == "")
    check("unknown deal records a warning instead of guessing",
          len(empty.warnings) > 0)
    check("'unknown' from the extractor is not accepted as a perimeter",
          empty.cp_perimeter("CP-REVENUE", "unknown") == "")
    check("a deal's own claim perimeter is still honoured",
          empty.cp_perimeter("CP-REVENUE", "Astrelia consolidated")
          == "Astrelia consolidated")
    check("no deal-specific literal remains in bridge_v7",
          "Alderstone" not in (ROOT / "tools" / "bridge_v7.py").read_text())

    ks = dp.load_profile("keystone")
    check("keystone profile loads", ks.loaded)
    check("keystone maps all 27 positions", len(ks.cp_institutional) == 27,
          f"{len(ks.cp_institutional)}")
    check("CP-EBITDA-FIRM keeps its event-conformant perimeter",
          ks.cp_perimeter("CP-EBITDA-FIRM", None)
          == "Alderstone standalone, firm underwriting definition")
    check("CP-EBITDA-FIRM keeps its time-frequency unit",
          ks.cp_unit("CP-EBITDA-FIRM", "$m") == "$m/year")

    try:
        dp.load_profile("no-such-deal", strict=True)
        check("strict mode refuses a missing profile", False)
    except FileNotFoundError:
        check("strict mode refuses a missing profile", True)


# ── 4. Grounding gate ────────────────────────────────────────────────────────
# The extractor bled a customer name into an IC-memo claim and typed it
# `attested`. The gate must route that to human review without adjudicating.

def test_grounding_gate() -> None:
    print("\n4. Grounding gate catches mis-scoped and unsourced claims")
    prof = dp.load_profile("keystone")

    riverton = {
        "claim_id": "t-1",
        "statement": "The Firm prices the Riverton transaction on $11.4m EBITDA.",
        "perimeter": "Riverton Group",
        "epistemic_class": "attested",
        "value": "11.4",
        "locator": "keystone_ic_memo.md::## Concern block",
    }
    codes = {f["code"] for f in gg.check_claim(riverton, prof)}
    check("counterparty-as-perimeter is caught",
          "PERIMETER_IS_COUNTERPARTY" in codes, str(sorted(codes)))
    check("that finding blocks admission",
          "PERIMETER_IS_COUNTERPARTY" in gg.BLOCKING)

    good = {
        "claim_id": "t-2",
        "statement": "Firm-underwritten EBITDA at entry is $11.4m.",
        "perimeter": "Alderstone standalone, firm underwriting definition",
        "epistemic_class": "attested",
        "value": "11.4",
        "locator": "keystone_ic_memo.md::## Concern block",
    }
    check("a well-scoped, sourced claim is clean",
          gg.check_claim(good, prof) == [], str(gg.check_claim(good, prof)))

    derived = {
        "claim_id": "t-3", "statement": "Total debt is $9.4m.",
        "perimeter": "Alderstone standalone", "epistemic_class": "derived",
        "value": "9.4", "derivation": "9.0 + 0.4",
        "locator": "keystone_ic_memo.md::## X",
    }
    codes = {f["code"] for f in gg.check_claim(derived, prof)}
    check("derived value is not required to appear verbatim in source",
          "VALUE_NOT_IN_SOURCE" not in codes)
    no_deriv = {**derived, "derivation": ""}
    check("derived without a derivation is blocked (invariant 3)",
          "DERIVATION_MISSING" in {f["code"] for f in gg.check_claim(no_deriv, prof)})

    # number grounding tolerances
    check("accounting negative $(0.20)m grounds -0.2",
          gg._number_in_text("-0.2", "a reserve of $(0.20)m was applied"))
    check("a rounded quote grounds against fuller precision",
          gg._number_in_text("30.7", "gross margin of 30.72%"))
    check("spelled-out counts ground",
          gg._number_in_text("8", "approximately eight years"))
    check("an invented midpoint does not ground",
          not gg._number_in_text("1.5", "capex is approximately 1%-2% of revenue"))
    check("a value unrelated to the statement does not ground",
          not gg._number_in_text("1092.0", "7 active staff members"))


# ── 5. minigraph: stdlib replacement for the networkx slice ──────────────────
# graph_store took a networkx dependency, breaking the stdlib-only invariant and
# making the UI unimportable on a clean checkout.

def test_minigraph() -> None:
    print("\n5. minigraph matches known-correct graph algorithms")
    g = mg.DiGraph()
    for a, b in [("A", "B"), ("B", "C"), ("C", "A")]:
        g.add_edge(a, b)
    pr = mg.pagerank(g)
    check("pagerank is uniform on a symmetric 3-cycle",
          all(abs(pr[n] - 1 / 3) < 1e-4 for n in "ABC"))
    check("pagerank sums to 1", abs(sum(pr.values()) - 1.0) < 1e-9)

    dangling = mg.DiGraph(); dangling.add_edge("A", "B")
    prd = mg.pagerank(dangling)
    check("dangling mass is conserved", abs(sum(prd.values()) - 1.0) < 1e-9)

    path = mg.DiGraph(); path.add_edge("A", "B"); path.add_edge("B", "C")
    bc = mg.betweenness_centrality(path, normalized=False)
    check("betweenness: only the middle node scores",
          abs(bc["B"] - 1.0) < 1e-9 and bc["A"] == 0.0 and bc["C"] == 0.0)
    check("betweenness normalises by (n-1)(n-2)",
          abs(mg.betweenness_centrality(path)["B"] - 0.5) < 1e-9)
    check("shortest_path follows edge direction",
          mg.shortest_path(path, "A", "C") == ["A", "B", "C"])
    try:
        mg.shortest_path(path, "C", "A")
        check("unreachable target raises", False)
    except mg.NetworkXNoPath:
        check("unreachable target raises", True)

    rt_g = mg.DiGraph(); rt_g.add_node("X", type="claim"); rt_g.add_edge("X", "Y", rel="supports")
    back = mg.node_link_graph(mg.node_link_data(rt_g))
    check("node_link round-trip preserves nodes, edges and attrs",
          back.number_of_nodes() == 2 and back.has_edge("X", "Y")
          and back.nodes["X"].get("type") == "claim")

    check("graph_store imports with no third-party graph library",
          "minigraph" in (ROOT / "tools" / "graph_store.py").read_text())




# ── 6. Excel compiler: cycles and cell semantics ─────────────────────────────
# extract_v3 reads formulas rather than cached values, and sheet_semantics must
# never borrow a header across a block boundary — that produced a confident
# wrong period on a table that carries none.

def test_excel() -> None:
    print("\n6. Excel: solver ciclico e semantica delle celle")
    from tools.extract_v3 import (solve_component, strongly_connected_components,
                                  parse_cell_node)

    check("parse_cell_node riconosce una cella vera",
          parse_cell_node("'[M.XLSX]Cashflow'!B3") == ("CASHFLOW", "B3"))
    check("parse_cell_node scarta un nodo di espressione",
          parse_cell_node("'[M.XLSX]Cashflow'!B3))") is None)

    succ = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}}
    comps = [sorted(c) for c in strongly_connected_components(
        ["a", "b", "c", "d"], succ) if len(c) > 1]
    check("Tarjan trova il ciclo a->b->c->a", comps == [["a", "b", "c"]], str(comps))

    # revolver loop with the draw binding, same closed form as the self-test
    e, t, r, m, n = 2.85, 42.8, 0.085 / 4, 1.0, 2.5

    def ev(cell, v):
        if cell == "I": return r * (t + v["R"])
        if cell == "C": return e - v["I"] - n
        if cell == "R": return max(0.0, m - v["C"])
        raise KeyError(cell)

    rep = solve_component(["I", "C", "R"], ev, tolerance=1e-10, max_iter=500)
    want_i = r * (t + m - e + n) / (1 - r)
    check("punto fisso converge", rep.converged, f"{rep.iterations} iterazioni")
    check("converge al valore in forma chiusa",
          abs(rep.values["I"] - want_i) < 1e-6,
          f"{rep.values['I']:.6f} vs {want_i:.6f}")
    check("un componente non convergente non viene spacciato per risolto",
          not solve_component(["x"], lambda c, v: v["x"] + 1.0,
                              tolerance=1e-12, max_iter=5).converged)

    from tools.sheet_semantics import classify_period, infer_unit
    check("periodo: FY2025A riconosciuto", classify_period("FY2025A") == "fiscal_year")
    check("periodo: 'Value' non è un periodo", classify_period("Value") is None)
    check("unità: number_format batte l'etichetta",
          infer_unit("Revenue", "0.0%") == ("%", "number_format"))
    check("unità: '(x)' letto come multiplo", infer_unit("Net leverage (x)", "General")[0] == "x")


def main() -> int:
    print("=" * 62)
    print("REGRESSION SUITE — 2026-08-25 audit")
    print("=" * 62)
    for t in (test_cascade, test_benchmark_field, test_deal_profile,
              test_grounding_gate, test_minigraph, test_excel):
        t()
    print()
    print("=" * 62)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"    FAILED: {f}")
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
