#!/usr/bin/env python3
"""
binding_resolver — L3: decide which bindings are admissible, over the whole deal.

  L1  source_graph      what the files literally contain
  L2  proposals         candidate semantic identities per cell
  L3  resolver          which set of bindings is admissible          (this module)

The point of L3 is that meaning is not decided cell by cell. A proposal that
looks fine on its own can be inadmissible once the rest of the deal is on the
table: a cell cannot be revenue if the formula that produces it sums revenue,
and a quarterly series cannot bind to an annual concept however convincing its
label is. So the deal is resolved as a constraint system and the formula graph,
which L1 already recorded, does most of the work.

Constraints
-----------
  C1 UNIQUE_BINDING     one concept per (concept, period, scenario)
  C2 UNIT_COHERENCE     a binding's unit must match the concept's declared unit
  C3 PERIOD_ALIGNMENT   period granularity must match the concept's
  C4 PRECEDENT_SHAPE    a concept declared as a sum must be produced by a sum,
                        an input must not be produced by a formula
  C5 NO_SELF_REFERENCE  a concept cannot be bound to a cell that reads it back

On an over-constrained system
-----------------------------
It stops and asks. It does not pick a winner, and it does not quietly drop the
weakest constraint to make the numbers work — that is how a resolver becomes an
oracle nobody can audit.

But stopping in silence wastes what the resolver just learned, so alongside the
halt it emits a *lateral proposal*: the smallest relaxation that would admit a
solution, with the evidence for it. The proposal is a suggestion attached to the
conflict, never an action. The human decides; the resolver never does.

    python3 tools/binding_resolver.py --semantics L2/cell_semantics.json \\
                                      --source L1/source_graph.json \\
                                      --concepts concepts.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ── the objects being resolved ───────────────────────────────────────────────

@dataclass
class Concept:
    """A thing the deal knows about, independent of where it lives in a sheet."""
    concept_id: str
    label: str
    unit: str = ""
    granularity: str = ""          # quarter | fiscal_year | point | ""
    form: str = ""                 # input | sum | derived | ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class Binding:
    concept_id: str
    locator: str                   # SHEET!REF
    period: str = ""
    scenario: str = ""
    unit: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class Violation:
    code: str
    detail: str
    bindings: list[str]            # locators involved
    concept_id: str = ""
    relaxation: dict | None = None  # the lateral proposal, when one exists

    def as_dict(self) -> dict:
        return asdict(self)


# ── helpers ──────────────────────────────────────────────────────────────────

_QUARTER_END = re.compile(r"-(03-31|06-30|09-30|12-31)$")
_SUM_RE = re.compile(r"^=\s*SUM\s*\(", re.I)
_NORM_UNIT = {"$mm": "$m", "$m": "$m", "usd m": "$m", "%": "%", "x": "x", "days": "days"}


def norm_unit(u: str) -> str:
    return _NORM_UNIT.get((u or "").strip().lower(), (u or "").strip().lower())


def granularity_of(period: str) -> str:
    p = (period or "").strip()
    if not p:
        return ""
    if _QUARTER_END.search(p):
        return "quarter"
    if re.match(r"^FY\d{4}", p, re.I):
        return "fiscal_year"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", p):
        return "point"
    return ""


# ── the resolver ─────────────────────────────────────────────────────────────

@dataclass
class Resolution:
    admitted: list[Binding] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    halted: bool = False

    @property
    def status(self) -> str:
        if self.halted:
            return "HALTED_OVERCONSTRAINED"
        return "RESOLVED" if not self.violations else "RESOLVED_WITH_WARNINGS"


def resolve(bindings: list[Binding],
            concepts: dict[str, Concept],
            source: dict | None = None) -> Resolution:
    """
    Admit the set of bindings that satisfies every constraint.

    Where a constraint is violated the resolver halts rather than choosing, and
    attaches the smallest relaxation that would clear the conflict.
    """
    res = Resolution()
    cells = (source or {}).get("cells", {})
    violations: list[Violation] = []

    # C2 / C3 / C4 / C5 are per-binding: a binding that fails one is not admitted.
    survivors: list[Binding] = []
    for b in bindings:
        c = concepts.get(b.concept_id)
        if c is None:
            violations.append(Violation(
                "UNKNOWN_CONCEPT", f"{b.concept_id} non è dichiarato", [b.locator],
                b.concept_id))
            continue

        bad = False

        # C2 — unit coherence
        if c.unit and b.unit and norm_unit(c.unit) != norm_unit(b.unit):
            violations.append(Violation(
                "UNIT_COHERENCE",
                f"{b.locator} porta {b.unit!r} ma {c.concept_id} è dichiarato {c.unit!r}",
                [b.locator], c.concept_id,
                relaxation={"kind": "adopt_cell_unit", "from": c.unit, "to": b.unit,
                            "rationale": "il foglio dichiara l'unità nella colonna unità; "
                                         "il concetto potrebbe essere stato dichiarato male"}))
            bad = True

        # C3 — period granularity
        g = granularity_of(b.period)
        if c.granularity and g and c.granularity != g:
            violations.append(Violation(
                "PERIOD_ALIGNMENT",
                f"{b.locator} è {g} ma {c.concept_id} è {c.granularity}",
                [b.locator], c.concept_id,
                relaxation={"kind": "aggregate", "from": g, "to": c.granularity,
                            "rationale": f"una serie {g} può alimentare un concetto "
                                         f"{c.granularity} solo tramite aggregazione dichiarata"}))
            bad = True

        # C4 — the formula must have the shape the concept claims
        rec = cells.get(b.locator) or {}
        formula = rec.get("value") if rec.get("kind") == "formula" else None
        if c.form == "input" and formula:
            violations.append(Violation(
                "PRECEDENT_SHAPE",
                f"{c.concept_id} è dichiarato input ma {b.locator} è calcolato",
                [b.locator], c.concept_id,
                relaxation={"kind": "reclassify_form", "from": "input", "to": "derived",
                            "rationale": "la cella ha una formula, quindi non è un input"}))
            bad = True
        if c.form == "sum" and formula and not _SUM_RE.match(str(formula)):
            violations.append(Violation(
                "PRECEDENT_SHAPE",
                f"{c.concept_id} è dichiarato somma ma {b.locator} non è una SUM",
                [b.locator], c.concept_id))
            bad = True

        # C5 — a concept must not be bound to a cell that reads itself
        if b.locator in (rec.get("precedents") or []):
            violations.append(Violation(
                "NO_SELF_REFERENCE", f"{b.locator} si legge da sola",
                [b.locator], c.concept_id))
            bad = True

        if not bad:
            survivors.append(b)

    # C1 — uniqueness, decided across the whole set rather than per cell
    slots: dict[tuple[str, str, str], list[Binding]] = defaultdict(list)
    for b in survivors:
        slots[(b.concept_id, b.period, b.scenario)].append(b)

    admitted: list[Binding] = []
    for (cid, period, scenario), group in slots.items():
        if len(group) == 1:
            admitted.append(group[0])
            continue
        ranked = sorted(group, key=lambda x: -x.confidence)
        violations.append(Violation(
            "UNIQUE_BINDING",
            f"{cid} @ {period or '—'}/{scenario or '—'} ha {len(group)} celle candidate",
            [b.locator for b in group], cid,
            relaxation={
                "kind": "prefer_highest_confidence",
                "candidate": ranked[0].locator,
                "margin": round(ranked[0].confidence - ranked[1].confidence, 3),
                "rationale": "risolvibile solo se il margine è ritenuto sufficiente; "
                             "un margine nullo significa che le celle sono indistinguibili",
            }))

    res.admitted = admitted
    res.violations = violations
    # Over-constrained means a concept the deal declares cannot be satisfied at
    # all. Halt, do not choose.
    unresolved = {v.concept_id for v in violations if v.concept_id}
    satisfied = {b.concept_id for b in admitted}
    res.halted = bool(unresolved - satisfied)
    return res


# ── loading ──────────────────────────────────────────────────────────────────

def bindings_from_semantics(path: Path, concepts: dict[str, Concept],
                            floor: float = 0.6) -> list[Binding]:
    """Turn L2 proposals into candidate bindings by matching label to concept."""
    data = json.loads(path.read_text(encoding="utf-8"))
    by_alias: dict[str, str] = {}
    for c in concepts.values():
        for a in [c.label, *c.aliases]:
            by_alias[a.strip().lower()] = c.concept_id

    out: list[Binding] = []
    for sheet in data:
        for p in sheet.get("proposals", []):
            if p.get("confidence", 0) < floor:
                continue
            cid = by_alias.get((p.get("row_label") or "").strip().lower())
            if not cid:
                continue
            out.append(Binding(
                concept_id=cid, locator=p["cell"],
                period=p.get("col_header", ""), scenario=sheet.get("sheet", ""),
                unit=p.get("unit", ""), confidence=p.get("confidence", 0.0),
                evidence=p.get("evidence", []),
            ))
    return out


def load_concepts(path: Path) -> dict[str, Concept]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("concepts", raw) if isinstance(raw, dict) else raw
    return {c["concept_id"]: Concept(**c) for c in items}


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve bindings as a constraint system")
    ap.add_argument("--semantics", type=Path, required=True)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--concepts", type=Path, required=True)
    ap.add_argument("--floor", type=float, default=0.6)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    concepts = load_concepts(a.concepts)
    source = json.loads(a.source.read_text(encoding="utf-8")) if a.source else None
    cands = bindings_from_semantics(a.semantics, concepts, a.floor)
    res = resolve(cands, concepts, source)

    print(f"[binding_resolver] concetti dichiarati: {len(concepts)}")
    print(f"  candidati (conf >= {a.floor}) : {len(cands)}")
    print(f"  ammessi                      : {len(res.admitted)}")
    print(f"  violazioni                   : {len(res.violations)}")
    print(f"  esito                        : {res.status}")

    by_code: dict[str, int] = defaultdict(int)
    for v in res.violations:
        by_code[v.code] += 1
    for code, n in sorted(by_code.items(), key=lambda kv: -kv[1]):
        print(f"      {code:20} {n}")

    if res.halted:
        print("\n  FERMO: il sistema è sovra-vincolato. Non scelgo io.")
        print("  Proposte laterali (suggerimenti, non azioni):")
        for v in res.violations:
            if not v.relaxation:
                continue
            print(f"    · {v.code} su {v.concept_id}")
            print(f"      {v.detail}")
            print(f"      proposta: {v.relaxation['kind']} — {v.relaxation['rationale']}")

    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "resolution.json").write_text(json.dumps({
            "status": res.status,
            "halted": res.halted,
            "admitted": [asdict(b) for b in res.admitted],
            "violations": [v.as_dict() for v in res.violations],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  → {a.out / 'resolution.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
