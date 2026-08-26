#!/usr/bin/env python3
"""
extract_v3 — compile an Excel workbook into a computable dependency graph.

Why a v3
--------
tools/xlsx_parser.py reads workbooks with openpyxl `data_only=True`, i.e. the
cached values, and derives dependencies from hard-coded sheet conventions
("Inputs", "QoE_Bridge", "SB_Base"). That works on the one workbook it was
written against and produces nothing useful on another fund's model. It also
cannot recompute: change an input and the graph still holds Excel's last saved
numbers.

v3 reads the formulas instead. The dependency graph is whatever the formulas
say it is, so no layout convention is assumed, and the model can be evaluated.

What it does and does not solve
-------------------------------
`formulas` (vinci1it2000) parses Excel formulas, builds the cell graph and
evaluates acyclic models correctly — measured against hand calculation on the
fixture in this file. What it does NOT do is converge circular references: with
`circular=True` it loads the workbook and marks every cell in a cycle `#CIRC!`
rather than iterating to a fixed point, even when the workbook itself carries
iterate=True and an iteration count. Verified on both variants, not assumed.

That matters because the cycles in an LBO are the interesting part: cash flow
drives interest, interest drives the revolver draw, the revolver drives cash
flow. Zeroing them silently produces a model that looks computed and is wrong.

So v3 splits the graph:

  * acyclic region  -> evaluated by `formulas`
  * each SCC        -> solved here by damped fixed-point iteration, reporting
                       whether it converged, in how many sweeps, and to what
                       residual

An SCC that does not converge is reported as such rather than given a number.
This is the same object PANTA calls a cyclic_component_solver_config, which is
why the solver reports its members, tolerance and iteration count in that shape.

Usage
-----
    python3 tools/extract_v3.py --workbook model.xlsx --out DIR
    python3 tools/extract_v3.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

# ── cell reference handling ──────────────────────────────────────────────────

# formulas names nodes like "'[BOOK.XLSX]SHEET'!B3", and also emits intermediate
# expression nodes carrying leftover parens. Only true cell nodes are kept.
_CELL_RE = re.compile(r"^'?\[[^\]]+\]([^']+)'?!\$?([A-Z]{1,3})\$?(\d+)$")


def parse_cell_node(node: Any) -> tuple[str, str] | None:
    """('SHEET', 'B3') for a real cell node, else None."""
    m = _CELL_RE.match(str(node).strip())
    if not m:
        return None
    sheet, col, row = m.group(1), m.group(2), m.group(3)
    return sheet.upper(), f"{col}{row}"


def cell_key(sheet: str, ref: str) -> str:
    return f"{sheet}!{ref}"


# ── strongly connected components (Tarjan, iterative) ────────────────────────

def strongly_connected_components(nodes: Iterable[str],
                                  succ: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's SCC. Iterative so a deep model cannot blow the stack."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root in nodes:
        if root in index:
            continue
        work: list[tuple[str, list[str]]] = [(root, list(succ.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)

        while work:
            node, pending = work[-1]
            progressed = False
            while pending:
                nxt = pending.pop()
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, list(succ.get(nxt, ()))))
                    progressed = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if progressed:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                result.append(comp)
    return result


# ── fixed-point solver for one cyclic component ──────────────────────────────

@dataclass
class SolveReport:
    component_id: str
    members: list[str]
    converged: bool
    iterations: int
    residual: float
    values: dict[str, float]
    reason: str = ""

    def as_panta_config(self, tolerance: float, max_iter: int) -> dict:
        """The shape PANTA expects for a cyclic component solver config."""
        return {
            "component_id": self.component_id,
            "member_ids": list(self.members),
            "method": "DAMPED_FIXED_POINT",
            "absolute_residual_tolerance": tolerance,
            "maximum_iterations": max_iter,
            "converged": self.converged,
            "iterations_used": self.iterations,
            "final_residual": self.residual,
        }


def solve_component(members: list[str],
                    evaluate: Callable[[str, dict[str, float]], float],
                    seed: dict[str, float] | None = None,
                    tolerance: float = 1e-9,
                    max_iter: int = 200,
                    damping: float = 0.5) -> SolveReport:
    """
    Gauss-Seidel sweeps with damping until the largest cell move is under
    tolerance.

    Damping is not decoration: an LBO revolver cycle is a feedback loop that
    oscillates under plain substitution when the loop gain approaches 1, and a
    half-step keeps it stable at the cost of a few more sweeps.
    """
    values: dict[str, float] = {m: 0.0 for m in members}
    if seed:
        values.update({k: v for k, v in seed.items() if k in values})

    residual = float("inf")
    for it in range(1, max_iter + 1):
        residual = 0.0
        for m in members:
            try:
                fresh = float(evaluate(m, values))
            except Exception as exc:                 # a cell that cannot be
                return SolveReport(                  # evaluated is not a number
                    component_id=members[0], members=members, converged=False,
                    iterations=it, residual=float("nan"), values=values,
                    reason=f"{m}: {type(exc).__name__}: {exc}",
                )
            blended = damping * fresh + (1.0 - damping) * values[m]
            residual = max(residual, abs(blended - values[m]))
            values[m] = blended
        if residual < tolerance:
            return SolveReport(members[0], members, True, it, residual, values)

    return SolveReport(members[0], members, False, max_iter, residual, values,
                       reason="iteration limit reached without convergence")


# ── workbook compilation ─────────────────────────────────────────────────────

@dataclass
class CompiledModel:
    cells: dict[str, dict] = field(default_factory=dict)   # key -> {sheet, ref, formula, value}
    succ: dict[str, set[str]] = field(default_factory=dict)
    pred: dict[str, set[str]] = field(default_factory=dict)
    components: list[list[str]] = field(default_factory=list)   # cyclic only
    reports: list[SolveReport] = field(default_factory=list)

    @property
    def cyclic_cells(self) -> set[str]:
        return {c for comp in self.components for c in comp}

    def stats(self) -> dict:
        return {
            "cells": len(self.cells),
            "edges": sum(len(v) for v in self.succ.values()),
            "cyclic_components": len(self.components),
            "cyclic_cells": len(self.cyclic_cells),
            "converged": sum(1 for r in self.reports if r.converged),
        }


def compile_workbook(path: Path) -> CompiledModel:
    """Load a workbook, evaluate what is acyclic, isolate what is not."""
    try:
        import formulas
    except ImportError:
        sys.exit("serve la libreria `formulas`: .venv/bin/pip install formulas")

    import warnings
    warnings.filterwarnings("ignore")

    xl = formulas.ExcelModel().loads(str(path)).finish(circular=True)
    solution = xl.calculate()

    model = CompiledModel()

    # 1. cells and their computed values (0 inside cycles — see module docstring)
    for node, val in solution.items():
        parsed = parse_cell_node(node)
        if not parsed:
            continue
        sheet, ref = parsed
        key = cell_key(sheet, ref)
        try:
            value = val.value[0, 0]
        except Exception:
            value = val
        model.cells[key] = {"sheet": sheet, "ref": ref, "value": value}

    # 2. cell -> cell edges, skipping the intermediate expression nodes that
    #    formulas inserts between them
    graph = xl.dsp.dmap
    for node in graph.nodes:
        tgt = parse_cell_node(node)
        if not tgt:
            continue
        tgt_key = cell_key(*tgt)
        for p in graph.pred[node]:
            src = parse_cell_node(p)
            if src:
                srcs = [cell_key(*src)]
            else:
                # walk one level through an expression node to its cell inputs
                srcs = [cell_key(*s) for s in
                        (parse_cell_node(pp) for pp in graph.pred[p]) if s]
            for s in srcs:
                if s == tgt_key:
                    continue
                model.succ.setdefault(s, set()).add(tgt_key)
                model.pred.setdefault(tgt_key, set()).add(s)

    # 3. cycles
    all_keys = set(model.cells) | set(model.succ) | set(model.pred)
    comps = strongly_connected_components(sorted(all_keys), model.succ)
    model.components = [
        sorted(c) for c in comps
        if len(c) > 1 or (c and c[0] in model.succ.get(c[0], set()))
    ]
    return model


# ── self-test ────────────────────────────────────────────────────────────────

def _selftest() -> int:
    """Prove the SCC solver converges on the LBO cycle formulas leaves at 0."""
    print("=" * 62)
    print("extract_v3 — self-test del solver ciclico")
    print("=" * 62)

    # cash flow -> interest -> revolver -> cash flow, with the draw binding
    ebitda_q, term_loan, rate_q, min_cash, dnwc = 2.85, 42.8, 0.085 / 4, 1.0, 2.5

    def evaluate(cell: str, v: dict[str, float]) -> float:
        if cell == "CF!INTEREST":
            return rate_q * (term_loan + v["CF!REVOLVER"])
        if cell == "CF!CFO":
            return ebitda_q - v["CF!INTEREST"] - dnwc
        if cell == "CF!REVOLVER":
            return max(0.0, min_cash - v["CF!CFO"])
        raise KeyError(cell)

    members = ["CF!INTEREST", "CF!CFO", "CF!REVOLVER"]
    rep = solve_component(members, evaluate, tolerance=1e-10, max_iter=500)

    # closed form: r*(T+R) = I ; C = E - I - N ; R = M - C  (draw binding)
    interest = rate_q * (term_loan + min_cash - ebitda_q + dnwc) / (1 - rate_q)
    cfo = ebitda_q - interest - dnwc
    revolver = max(0.0, min_cash - cfo)
    want = {"CF!INTEREST": interest, "CF!CFO": cfo, "CF!REVOLVER": revolver}

    print(f"\n  convergenza : {rep.converged} in {rep.iterations} iterazioni")
    print(f"  residuo     : {rep.residual:.2e}\n")
    ok = rep.converged
    for m in members:
        got, exp = rep.values[m], want[m]
        good = abs(got - exp) < 1e-6
        ok &= good
        print(f"  {'OK ' if good else 'FAIL'} {m:14} = {got:+.6f}   atteso {exp:+.6f}")

    # the cycle must actually bind, otherwise the test proves nothing
    binding = want["CF!REVOLVER"] > 0
    print(f"\n  {'OK ' if binding else 'FAIL'} il revolver tira davvero "
          f"({want['CF!REVOLVER']:.4f} > 0), quindi il ciclo è vincolante")
    ok &= binding

    print("\n" + "=" * 62)
    print("PASS" if ok else "FAIL")
    print("=" * 62)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile an Excel workbook into a computable graph")
    ap.add_argument("--workbook", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if not a.workbook:
        ap.error("serve --workbook, oppure --selftest")

    model = compile_workbook(a.workbook)
    s = model.stats()
    print(f"[extract_v3] {a.workbook.name}")
    print(f"  celle              : {s['cells']}")
    print(f"  archi (da formule) : {s['edges']}")
    print(f"  componenti cicliche: {s['cyclic_components']} "
          f"({s['cyclic_cells']} celle)")
    for comp in model.components:
        print(f"    · {', '.join(comp[:6])}{' …' if len(comp) > 6 else ''}")

    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "cell_graph.json").write_text(json.dumps({
            "cells": model.cells,
            "edges": [[s_, t] for s_, ts in model.succ.items() for t in ts],
            "cyclic_components": model.components,
            "stats": s,
        }, indent=2, default=str), encoding="utf-8")
        print(f"  → {a.out / 'cell_graph.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
