#!/usr/bin/env python3
"""L2 — propose what a workbook cell *means*, from the L1 graph alone.

Where this sits
---------------
  L1  source_graph.py     what the file literally contains        (no interpretation)
  L2  this module         proposes economic identities            (proposal only)
  L3  model_resolver.py   decides which proposals are admissible  (global constraints)

Why it exists
-------------
``=Model!D42 - Model!D41`` is arithmetic on addresses. It means nothing outside
the sheet. Something has to say "D42 is Firm EBITDA for FY2026 on the base case"
before the dynamics engine can compute with it or bind it to a case position.

Today that job is done by ``tools/xlsx_parser.py``, which recognises Keystone's
workbook by hard-coded sheet names and row offsets (``_parse_qoe_ebitda``,
``SCENARIO_SHEETS``, ``CANONICAL_ID_MAP``). It yields 59 concepts and works on
exactly one file. Point it at any other LBO model and it returns nothing useful.

This module recovers the same concepts from signals every financial model has,
so a workbook nobody has seen before is still readable.

A cell has two coordinates, not one
-----------------------------------
The mistake worth avoiding: treating the row label as the whole meaning. A
financial model is a grid, and a cell means the intersection of its row and its
column::

    QOE_BRIDGE r3:   Adjustment      | Reported | Seller View | QoE View | Firm View
    QOE_BRIDGE r19:  Adjusted EBITDA |     10.2 |        12.7 |     11.9 |      11.4

``C19`` is not "Adjusted EBITDA". It is *Adjusted EBITDA under the Seller View* —
and the four numbers beside it are the other four EBITDAs, which is precisely the
distinction the whole system exists to preserve. Read the row alone and they
collapse into one contradicted quantity.

Which axis carries which dimension is not fixed. On the sheet above, the row is
the metric and the column is the basis. Two sheets later it inverts::

    OWNERSHIP_RETURNS r3:  Case            | Exit LTM Revenue | Exit Multiple
    OWNERSHIP_RETURNS r4:  Standalone Base |           105.46 |             9

so L2 reports both coordinates verbatim and lets L3 decide which is metric,
which is basis, which is period. Guessing that here would hard-code one house's
layout convention — the exact failure this module replaces.

The signals
-----------
1. **Row label** — nearest text to the left. 10,042 of Keystone's 29,476 cells are
   text, and they are the map.
2. **Column header** — nearest text above, in a row that is mostly text. Carries
   the basis or the period, and decides whether a horizontal run is one series
   across periods or several distinct quantities side by side.
3. **Number format** — ``0.0%`` vs ``$#,##0.0`` vs ``0.0x`` distinguishes a margin
   from a dollar amount from a multiple. The modeller declaring the dimension in
   a field that cannot be confused with prose.
4. **Topology** — a cell with no precedents was typed by a human (an input); a
   cell nothing depends on is terminal (an output, or a check).

What this module refuses to do
------------------------------
It proposes; it never decides. Every proposal carries the signals that produced it
and separate extraction, identity, binding and relation confidence — not a single
score that lets certainty at one stage leak into another. This module has no
binding target or relation evidence, so those dimensions remain zero. A cell whose
meaning cannot be recovered gets no proposal at all rather than a guess, because a
wrong binding propagates silently through the dependency graph while a missing one
is visible as a coverage limit.

Ambiguity between proposals is L3's problem: only a solver looking at the whole
deal at once can know that two cells cannot both be "Firm EBITDA FY2025 base
case". Deciding that here, cell by cell, is exactly the failure mode this
architecture is built to avoid.

Usage
-----
    python3 tools/model_semantics.py <workbook.xlsx>            # propose + report
    python3 tools/model_semantics.py <workbook.xlsx> --json out.json
    python3 tools/model_semantics.py <workbook.xlsx> --benchmark # vs xlsx_parser
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Unit inference from number format ─────────────────────────────────────────
# Excel number formats are a small, stable language. These patterns cover what
# financial models actually use; anything unmatched yields "" rather than a guess.
_FORMAT_UNIT: tuple[tuple[str, str], ...] = (
    (r"%", "%"),
    (r'\$|USD', "$"),
    (r'£|GBP', "£"),
    (r'€|EUR', "€"),
    (r'"x"|\bx\b', "x"),
    (r'"\s*d(ay)?s?\s*"', "days"),
)

# Colour and condition sections — `[Red]`, `[<=100]` — are presentation, not
# dimension. They must be stripped before matching or the `d` in `[Red]` reads as
# "days" and every dollar figure in the workbook is silently mislabelled.
_FORMAT_NOISE = re.compile(r"\[[^\]]*\]")

# Labels that mark a balance/tie-out cell rather than an economic quantity. These
# are conventions shared across models, not Keystone-specific strings.
_CONTROL_WORDS = (
    "check", "balance", "tie", "reconcil", "must equal", "diff", "variance",
    "control", "assert",
)

# A label that is a section heading, not a row label. Headings sit above data
# rather than beside it, so they must not be attached to the row below.
_HEADING_HINTS = ("---", "===", "section", "table", ":")

# A column header governs every row beneath it until the next header row — which
# is what actually ends a block, not a row count. A QoE bridge runs sixteen
# adjustment rows below its header before reaching the total; a fixed reach cuts
# the total off from the very columns that name it. This bound only stops a
# header at the top of a long sheet from claiming rows hundreds down.
_HEADER_REACH = 60


def _is_year_like(value: Any) -> bool:
    """A bare calendar year — the one numeric that labels a column, not data."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return n.is_integer() and 1900 <= n <= 2100


# A column header that names a time period means the run beside it is one
# quantity observed repeatedly. Any other header means the cells are different
# quantities that happen to sit next to each other.
_PERIOD_HEADER = re.compile(
    r"^\s*(FY\s?\d{2,4}[AEPF]?|\d{4}[AEPF]?|Q[1-4](\s?\d{2,4})?|H[12]|LTM|NTM"
    r"|Opening|Entry|Exit|Year\s?\d+|Yr\s?\d+"
    r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
    re.I,
)


@dataclass(frozen=True)
class ProposalConfidence:
    """Confidence by semantic stage, per the v0.2 extraction contract.

    These values are deliberately not collapsed into an ``overall`` score:
    confidence that L1 content was extracted cannot establish an economic
    identity, a binding to another object, or a semantic/runtime relation.
    """

    extraction: float = 0.0
    identity: float = 0.0
    binding: float = 0.0
    relation: float = 0.0

    def __post_init__(self) -> None:
        for dimension in ("extraction", "identity", "binding", "relation"):
            value = getattr(self, dimension)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(
                    f"confidence.{dimension} must be a finite number between 0 and 1"
                )


@dataclass
class ConceptProposal:
    """One proposed economic meaning for one cell or one row-range of cells."""

    sheet: str
    cells: str                       # "B3" or "C40:H40"
    label: str                       # row coordinate, verbatim — never invented
    header: str                      # column coordinate, verbatim — "" if none
    kind: str                        # input | assumption_series | output | model_control | ...
    unit: str
    values: Any
    signals: dict[str, Any] = field(default_factory=dict)
    confidence: ProposalConfidence = field(default_factory=ProposalConfidence)

    def __post_init__(self) -> None:
        if not isinstance(self.confidence, ProposalConfidence):
            raise TypeError(
                "confidence must be ProposalConfidence with separate extraction, "
                "identity, binding and relation values"
            )

    @property
    def name(self) -> str:
        """Both coordinates, joined. Neither half alone identifies the quantity."""
        if self.header and self.label:
            return f"{self.label} — {self.header}"
        return self.label or self.header

    @property
    def locator(self) -> str:
        return f"{self.sheet}!{self.cells}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["locator"] = self.locator
        d["name"] = self.name
        return d


def cell_value(cell: dict) -> Any:
    """A formula's value is its evaluation; a literal's is what was typed.

    Both keys are always present, and ``evaluated_value`` is None on literals —
    so ``.get("evaluated_value", fallback)`` silently returns None instead of
    falling back. Getting this wrong nulls every input in the workbook.
    """
    evaluated = cell.get("evaluated_value")
    return cell.get("value") if evaluated is None else evaluated


# ── Signal extraction ─────────────────────────────────────────────────────────

def _unit_from_format(number_format: str | None) -> str:
    fmt = _FORMAT_NOISE.sub("", (number_format or "").strip())
    if not fmt or fmt.lower() == "general":
        return ""
    for pattern, unit in _FORMAT_UNIT:
        if re.search(pattern, fmt, re.I):
            return unit
    return ""


def _unit_from_text(text: str | None) -> str:
    """A modeller often writes the unit in its own column: `Enterprise value | $mm | 108.0`."""
    t = (text or "").strip()
    if not t or len(t) > 8:
        return ""
    if re.fullmatch(r"[$£€]\s?(mm?|bn|k)?|%|x|days?|bps|yrs?", t, re.I):
        return t
    return ""


def _is_heading(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if any(h in t.lower() for h in _HEADING_HINTS):
        return True
    # ALL CAPS with no digits reads as a banner, not a row label.
    return t.isupper() and not any(c.isdigit() for c in t) and len(t.split()) > 1


def _looks_like_control(label: str) -> bool:
    low = label.lower()
    return any(w in low for w in _CONTROL_WORDS)


# ── The proposer ──────────────────────────────────────────────────────────────

class SemanticProposer:
    """Turns an L1 cell graph into concept proposals. Never mutates its input."""

    def __init__(self, graph: dict[str, Any]):
        self.cells: dict[str, dict] = graph.get("cells", {})
        self._by_pos: dict[tuple[str, int, int], dict] = {}
        self._rows: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for cell in self.cells.values():
            key = (cell["sheet"], cell["row"], cell["col"])
            self._by_pos[key] = cell
            self._rows[(cell["sheet"], cell["row"])].append(cell)
        for row in self._rows.values():
            row.sort(key=lambda c: c["col"])
        self._dependents = self._invert_precedents()
        self._header_rows = self._find_header_rows()

    def _find_header_rows(self) -> dict[str, list[int]]:
        """Rows that label columns rather than hold data, per sheet.

        "Mostly text" is the obvious rule and it is wrong: the header row that
        matters most is usually numeric, because period columns are years::

            A39=Case / Driver | B39=Unit | C39=2026 | D39=2027 | E39=2028

        Two text cells out of eight would reject exactly the row that makes a
        six-column run a time series. So the test is inverted: a row is a header
        when none of its numbers look like data — every numeric cell is a bare
        year. That keeps the row above, and rejects ``Enterprise value | $mm |
        108.0``, which is data whether or not most of its cells are text.
        """
        headers: dict[str, list[int]] = defaultdict(list)
        for (sheet, row), cells in self._rows.items():
            populated = [c for c in cells if c.get("value") is not None]
            if len(populated) < 2:
                continue
            numeric = [c for c in populated if c.get("kind") in ("number", "formula")]
            if any(not _is_year_like(cell_value(c)) for c in numeric):
                continue                      # carries data, so it is not a header
            if not any(c.get("kind") == "text" for c in populated):
                continue                      # a bare row of numbers labels nothing
            headers[sheet].append(row)
        for rows in headers.values():
            rows.sort()
        return headers

    def _header_for(self, sheet: str, col: int, data_row: int) -> str:
        """The column's label: nearest header row above this data row.

        Bounded by _HEADER_REACH — a header thirty rows up belongs to a different
        block, and attaching it would invent a relationship the sheet never made.
        """
        for header_row in reversed(self._header_rows.get(sheet, [])):
            if header_row >= data_row:
                continue
            if data_row - header_row > _HEADER_REACH:
                break
            cell = self._by_pos.get((sheet, header_row, col))
            if cell is None or cell.get("value") is None:
                break          # nearest header governs even where this column is blank
            text = str(cell_value(cell)).strip()
            return "" if _is_heading(text) else text
        return ""

    def _invert_precedents(self) -> dict[str, set[str]]:
        """precedents says what a cell reads; this says what reads a cell.

        Needed for the topology signal: 'nothing depends on this' is what
        separates a terminal output from an intermediate calculation, and it is
        only visible from the reverse edges.
        """
        dependents: dict[str, set[str]] = defaultdict(set)
        for locator, cell in self.cells.items():
            for precedent in cell.get("precedents") or []:
                dependents[precedent.upper()].add(locator)
        return dependents

    # ── row anatomy ───────────────────────────────────────────────────────────

    def _label_for_row(self, sheet: str, row: int, value_col: int) -> tuple[str, str]:
        """The nearest meaningful text to the left. Returns (label, source_ref)."""
        best: tuple[str, str] = ("", "")
        for col in range(value_col - 1, 0, -1):
            cell = self._by_pos.get((sheet, row, col))
            if not cell or cell.get("kind") != "text":
                continue
            text = str(cell.get("value") or "").strip()
            if not text or _unit_from_text(text):
                continue           # a unit column is not the label
            if _is_heading(text):
                continue
            best = (text, cell["ref"])
            break                  # nearest wins: closer text describes the row
        return best

    def _value_run(self, sheet: str, row: int, start_col: int) -> list[dict]:
        """Consecutive numeric/formula cells from start_col — a scalar or a series."""
        run: list[dict] = []
        col = start_col
        while True:
            cell = self._by_pos.get((sheet, row, col))
            if not cell or cell.get("kind") not in ("number", "formula", "date"):
                break
            run.append(cell)
            col += 1
        return run

    def _classify(self, run: list[dict], label: str) -> tuple[str, dict]:
        """Kind from topology first, label only to separate controls from economics."""
        has_precedents = any(c.get("precedents") for c in run)
        has_dependents = any(self._dependents.get(c["locator"].upper()) for c in run)
        series = len(run) > 1

        topology = (
            "no_precedents" if not has_precedents
            else "terminal" if not has_dependents
            else "intermediate"
        )

        if _looks_like_control(label):
            kind = "model_control_series" if series else "model_control"
        elif not has_precedents:
            # Typed by a human. A run of typed numbers across periods is an
            # assumption schedule; a lone typed number is a deal input.
            kind = "assumption_series" if series else "input"
        elif not has_dependents:
            kind = "output_series" if series else "output"
        else:
            kind = "derived_series" if series else "derived"

        return kind, {
            "topology": topology,
            "series_length": len(run),
            "has_precedents": has_precedents,
            "has_dependents": has_dependents,
        }

    def _unit(self, sheet: str, row: int, run: list[dict]) -> tuple[str, str]:
        """Format first — it is the modeller's own declaration of dimension."""
        for cell in run:
            unit = _unit_from_format(cell.get("number_format"))
            if unit:
                return unit, "number_format"
        first_col = run[0]["col"]
        for col in range(first_col - 1, max(0, first_col - 4), -1):
            cell = self._by_pos.get((sheet, row, col))
            if cell and cell.get("kind") == "text":
                unit = _unit_from_text(str(cell.get("value") or ""))
                if unit:
                    return unit, "adjacent_text"
        return "", ""

    # ── main entry ────────────────────────────────────────────────────────────

    def propose(self) -> list[ConceptProposal]:
        proposals: list[ConceptProposal] = []
        claimed: set[str] = set()

        for (sheet, row), cells in sorted(self._rows.items()):
            for cell in cells:
                if cell["locator"] in claimed:
                    continue
                if cell.get("kind") not in ("number", "formula"):
                    continue

                run = self._value_run(sheet, row, cell["col"])
                if not run:
                    continue

                label, label_ref = self._label_for_row(sheet, row, run[0]["col"])
                if not label:
                    # No label anywhere to the left. Refusing to propose is the
                    # point: an unlabelled number is not a concept, and inventing
                    # a name for it would put a fiction into the dependency graph.
                    claimed.update(c["locator"] for c in run)
                    continue

                for group in self._split_run(sheet, row, run):
                    proposals.append(self._build(sheet, row, group, label, label_ref))
                claimed.update(c["locator"] for c in run)

        return proposals

    def _split_run(self, sheet: str, row: int, run: list[dict]) -> list[list[dict]]:
        """One series, or several distinct quantities — the headers decide.

        Consecutive columns headed by periods are the same quantity over time and
        stay together. Columns headed by anything else (``Seller View`` beside
        ``QoE View``) are different quantities and must not be merged: doing so
        is exactly how five legitimate EBITDAs collapse into one contradiction.
        """
        groups: list[list[dict]] = []
        current: list[dict] = []
        for cell in run:
            header = self._header_for(sheet, cell["col"], row)
            if _PERIOD_HEADER.match(header) or not header:
                current.append(cell)
                continue
            if current:
                groups.append(current)
                current = []
            groups.append([cell])          # named, non-period column stands alone
        if current:
            groups.append(current)
        return groups

    def _build(self, sheet: str, row: int, run: list[dict],
               label: str, label_ref: str) -> ConceptProposal:
        kind, topo = self._classify(run, label)
        unit, unit_source = self._unit(sheet, row, run)
        values = [cell_value(c) for c in run]

        # A series spans its columns, so it is headed by the span. Naming it after
        # the first column alone would label six years of growth "2026".
        first = self._header_for(sheet, run[0]["col"], row)
        last = self._header_for(sheet, run[-1]["col"], row)
        header = first if (len(run) == 1 or first == last or not last) else f"{first}–{last}"

        # Confidence is stage-specific. L1 source coordinates and values are
        # deterministically preserved for every emitted proposal, while the
        # economic identity depends on four independent signals. This L2 pass
        # proposes no binding target and no relation, so assigning either of
        # those a positive score would invent evidence that is not available.
        identity_signals = {
            "label": bool(label),
            "header": bool(header),
            "unit": bool(unit),
            "decided_topology": topo["topology"] != "intermediate",
        }
        extraction_signals = {
            "source_cells_grounded": all(bool(c.get("ref")) for c in run),
            "source_values_preserved": all("value" in c for c in run),
        }
        extraction_confidence = round(
            sum(extraction_signals.values()) / len(extraction_signals), 2
        )
        identity_confidence = round(
            sum(identity_signals.values()) / len(identity_signals), 2
        )
        return ConceptProposal(
            sheet=sheet,
            cells=run[0]["ref"] if len(run) == 1 else f"{run[0]['ref']}:{run[-1]['ref']}",
            label=label,
            header=header,
            kind=kind,
            unit=unit,
            values=values[0] if len(values) == 1 else values,
            signals={
                "label_ref": label_ref,
                "unit_source": unit_source,
                "sheet": sheet,
                "header_is_period": bool(header) and bool(_PERIOD_HEADER.match(header)),
                "confidence_basis": {
                    "extraction": extraction_signals,
                    "identity": identity_signals,
                    "binding": {"candidate_binding_evidence": False},
                    "relation": {"relation_evidence": False},
                },
                **topo,
            },
            confidence=ProposalConfidence(
                extraction=extraction_confidence,
                identity=identity_confidence,
                binding=0.0,
                relation=0.0,
            ),
        )


def propose_from_workbook(path: Path) -> list[ConceptProposal]:
    from tools.source_graph import capture
    return SemanticProposer(capture(path).to_json()).propose()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _report(proposals: list[ConceptProposal]) -> None:
    from collections import Counter
    print(f"proposte: {len(proposals)}")
    print(f"per kind: {dict(Counter(p.kind for p in proposals))}")
    for dimension in ("extraction", "identity", "binding", "relation"):
        distribution = Counter(
            getattr(proposal.confidence, dimension) for proposal in proposals
        )
        print(
            f"confidenza {dimension}: "
            f"{dict(sorted(distribution.items(), reverse=True))}"
        )
    print(f"con unità: {sum(1 for p in proposals if p.unit)}")


def _benchmark(path: Path, proposals: list[ConceptProposal]) -> None:
    """Compare coverage against the hard-coded parser this module must replace."""
    from tools.xlsx_parser import parse_workbook

    target = parse_workbook(path)
    ours = {(p.sheet.upper(), p.cells.upper()) for p in proposals}
    hit = [n for n in target if (n.sheet.upper(), n.cell.upper()) in ours]
    missed = [n for n in target if (n.sheet.upper(), n.cell.upper()) not in ours]

    print(f"\nxlsx_parser (hardcoded): {len(target)} concetti")
    print(f"ritrovati da L2        : {len(hit)} ({100*len(hit)/len(target):.0f}%)")
    if missed:
        print(f"mancanti               : {len(missed)}")
        for n in missed[:12]:
            print(f"   {n.sheet}!{n.cell:14} {n.name[:44]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="L2 — proposta semantica da grafo L1")
    ap.add_argument("workbook", type=Path)
    ap.add_argument("--json", type=Path, help="scrivi le proposte su file")
    ap.add_argument("--benchmark", action="store_true",
                    help="confronta la copertura con tools/xlsx_parser.py")
    args = ap.parse_args()

    if not args.workbook.exists():
        print(f"non trovato: {args.workbook}", file=sys.stderr)
        return 1

    proposals = propose_from_workbook(args.workbook)
    _report(proposals)

    if args.json:
        args.json.write_text(
            json.dumps([p.to_dict() for p in proposals], indent=1, ensure_ascii=False,
                       default=str),
            encoding="utf-8")
        print(f"scritto: {args.json}")

    if args.benchmark:
        _benchmark(args.workbook, proposals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
