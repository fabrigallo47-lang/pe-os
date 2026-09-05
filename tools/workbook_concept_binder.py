#!/usr/bin/env python3
"""Propose which workbook cell carries which institutional concept.

The gap this fills
------------------
compile_workbook_formula_graphs() captures the real workbook faithfully and
assigns no meaning: 29,476 cells, 10,700 formulas, Excel syntax, by design. The
rest of the pipeline — materiality, authority, the institutional MOIC/IRR, the
independent validator — expects the 75 curated concepts that compiler_v7.py
writes out by hand (MN-EV, MN-SPONSOR-EQUITY, MN-NET-LEVERAGE...). Between the
raw graph and the curated one, one step was never automated: which cell is which
concept. execution_mapping_compiler.populate_execution_mapping() already takes
exactly that as its `binding_resolution` argument.

What this does NOT do
---------------------
Admit a binding. Tying a cell to an institutional concept incorrectly produces a
wrong number wearing the face of a right one, which is the failure the whole
epistemic apparatus exists to prevent. Everything here is emitted as a PROPOSAL
carrying the evidence it was made from, for a human to admit or reject. Nothing
in this module writes an admitted binding, and `binding_resolution()` refuses to
build one out of anything that has not been admitted.

How a proposal is made
----------------------
Deterministically, from the label a human already wrote next to the number:

  Inputs!A3 = "Enterprise value"        -> the value lives at Inputs!B3
  Scenario_Drivers!A5 = "Revenue"       -> the series lives along row 5

so a concept is matched by comparing its curated label against the sheet's own
row/column labels. No model, no embedding: a token-containment test that can be
read, argued with, and shown to the person admitting it.

Scoring
-------
compiler_v7.py's hand-written `workbook_ref` on 74 of 75 nodes is a ground truth
this can be measured against, so the proposer's accuracy is a number rather than
an impression. See score_proposals().
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Words that carry no discriminating power in a financial model's row labels.
# Kept deliberately short: over-stripping makes unlike concepts look alike.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "to", "for", "at", "in", "on", "by",
    "total", "net", "per", "value", "amount", "balance",
})
_WORD = re.compile(r"[^a-z0-9]+")
_CELL_REF = re.compile(r"^(?P<sheet>[^!]+)!(?P<col>[A-Z]+)(?P<row>\d+)$")
_RANGE_REF = re.compile(
    r"^(?P<sheet>[^!]+)!(?P<c1>[A-Z]+)(?P<r1>\d+):(?P<c2>[A-Z]+)(?P<r2>\d+)$")

# A proposal must clear this to be worth a human's attention. It is a review
# bar, not an admission bar -- admission is always a person's act.
MIN_SCORE = 0.5


def _tokens(text: Any) -> list[str]:
    return [w for w in _WORD.split(str(text or "").lower()) if w and w not in _STOPWORDS]


def _score(concept_label: str, cell_label: str) -> float:
    """Containment, biased toward the concept being fully present in the label.

    Jaccard punishes a long curated label ("Firm Underwriting EBITDA (opening,
    annual)") against a short sheet label ("Firm EBITDA") even when the sheet
    label is exactly right, so the numerator is the overlap and the denominator
    is the SHORTER side.
    """
    a, b = set(_tokens(concept_label)), set(_tokens(cell_label))
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def parse_ref(ref: str) -> tuple[str, int, int, int] | None:
    """(sheet, first_row, first_col_index, last_row) for a cell or a range.

    Returns None for anything this module will not guess at: a defined name, a
    prose reference like "CIM / management accounts", a bare sheet.
    """
    text = str(ref or "").split(":", 1)[-1] if ".xlsx:" in str(ref) else str(ref or "")
    text = text.strip()
    m = _RANGE_REF.match(text)
    if m:
        return (m.group("sheet"), int(m.group("r1")), _col_index(m.group("c1")),
                int(m.group("r2")))
    m = _CELL_REF.match(text)
    if m:
        row = int(m.group("row"))
        return (m.group("sheet"), row, _col_index(m.group("col")), row)
    return None


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def _cells_by_sheet(cells: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[tuple[int, int], Mapping]]:
    out: dict[str, dict[tuple[int, int], Mapping]] = {}
    for cell in cells.values():
        sheet = str(cell.get("sheet") or "")
        row, col = cell.get("row"), cell.get("col")
        if not sheet or not isinstance(row, int) or not isinstance(col, int):
            continue
        out.setdefault(sheet.casefold(), {})[(row, col)] = cell
    return out


def row_label(sheet_cells: Mapping[tuple[int, int], Mapping], row: int,
              before_col: int, max_scan: int = 6) -> str | None:
    """The text a human put to the left of this row's numbers.

    Scans leftward from the value column rather than assuming column A: models
    routinely indent, and the nearest label to the left is the one a reader
    understands the row by.
    """
    for col in range(max(1, before_col - 1), 0, -1):
        if before_col - col > max_scan:
            break
        cell = sheet_cells.get((row, col))
        if cell is None:
            continue
        value = cell.get("value")
        if not (isinstance(value, str) and value.strip() and cell.get("kind") == "text"):
            continue
        # Financial models put a units column between the label and the numbers.
        # Taking the nearest text made 10 of 28 rows resolve to '$mm', 'days' or
        # '%' -- a unit is not a concept name, so keep scanning left past it.
        if is_unit_only(value):
            continue
        return value.strip()
    return None


_UNIT_ONLY = frozenset({
    "mm", "m", "bn", "k", "x", "pct", "percent", "days", "day", "bps", "yrs",
    "years", "months", "usd", "eur", "gbp", "unit", "units", "ratio", "multiple",
})


def is_unit_only(text: str) -> bool:
    """True when the cell states a unit or format rather than naming a thing."""
    stripped = str(text or "").strip()
    if not stripped:
        return True
    if stripped in {"%", "x", "$", "£", "€"}:
        return True
    words = [w for w in _WORD.split(stripped.lower()) if w]
    return bool(words) and all(w in _UNIT_ONLY for w in words)


def propose(graph: Mapping[str, Any], concepts: Sequence[Mapping[str, Any]],
            candidate_refs: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Propose a concept for each candidate cell/range, with its evidence.

    `candidate_refs` maps model_node_id -> workbook ref when the region to test
    is already known (the compiler_v7 refs, or a prior admitted set). Every
    returned record is a PROPOSAL; none is admitted.
    """
    cells = graph.get("cells") or {}
    by_sheet = _cells_by_sheet(cells)
    labels = {c.get("model_node_id"): str(c.get("label") or "") for c in concepts}

    proposals: list[dict[str, Any]] = []
    for node_id, ref in (candidate_refs or {}).items():
        parsed = parse_ref(ref)
        if parsed is None:
            proposals.append({
                "model_node_id": node_id, "workbook_ref": ref, "status": "PROPOSED",
                "score": 0.0, "cell_label": None,
                "reason": "reference is not a cell or range this module will resolve",
            })
            continue
        sheet, row, col, _ = parsed
        sheet_cells = by_sheet.get(sheet.casefold())
        if sheet_cells is None:
            proposals.append({
                "model_node_id": node_id, "workbook_ref": ref, "status": "PROPOSED",
                "score": 0.0, "cell_label": None,
                "reason": f"sheet {sheet!r} is not in the captured graph",
            })
            continue
        label = row_label(sheet_cells, row, col)
        concept_label = labels.get(node_id, "")
        proposals.append({
            "model_node_id": node_id,
            "workbook_ref": ref,
            "sheet": sheet,
            "row": row,
            "cell_label": label,
            "concept_label": concept_label,
            "score": round(_score(concept_label, label or ""), 3),
            "status": "PROPOSED",
            "reason": "label adjacency" if label else "no adjacent text label found",
        })
    return proposals


def score_proposals(proposals: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """How often the sheet's own label agrees with the curated concept name.

    This is the honest measure of whether label adjacency can carry the binding:
    high agreement means a proposer can do this work for a new deal; low
    agreement means the labels do not determine the concept and a human (or a
    model proposing to a human) has to.
    """
    items = list(proposals)
    scored = [p for p in items if p.get("cell_label")]
    agree = [p for p in scored if float(p.get("score") or 0) >= MIN_SCORE]
    return {
        "proposals": len(items),
        "with_label": len(scored),
        "no_label": len(items) - len(scored),
        "agreeing": len(agree),
        "agreement_rate": round(len(agree) / len(scored), 3) if scored else 0.0,
    }


def verify_refs(graph: Mapping[str, Any],
                concepts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Check each concept's declared value against the cell its ref names.

    A workbook_ref is only worth anything if the cell it points at holds the
    number the concept claims. Nothing verified this, and on the real Keystone
    workbook it does not hold: the Inputs sheet uses TWO layouts -- row 3 is
    label|value|unit while row 46 is label|unit|value -- so refs written as
    column B land on the unit cell in every scenario block.

    Reports; changes nothing. A value disagreement is a modelling question for a
    human (is the workbook stale, or is the underwriting deliberately different?)
    and answering it by overwriting either side would destroy the evidence that
    the two ever disagreed.
    """
    cells = graph.get("cells") or {}
    by_sheet = _cells_by_sheet(cells)
    findings: list[dict[str, Any]] = []
    for concept in concepts:
        ref = concept.get("workbook_ref")
        declared = concept.get("initial_value")
        parsed = parse_ref(str(ref or ""))
        if parsed is None or not isinstance(declared, (int, float)) or isinstance(declared, bool):
            continue
        sheet, row, col, _ = parsed
        sheet_cells = by_sheet.get(sheet.casefold())
        if sheet_cells is None:
            continue
        cell = sheet_cells.get((row, col))
        found = cell.get("value") if cell else None
        numeric = found if isinstance(found, (int, float)) and not isinstance(found, bool) else None
        if numeric is not None and abs(float(numeric) - float(declared)) <= 1e-9:
            continue
        # Where else on this row does the declared value actually sit?
        elsewhere = [c for (r, _c), c in sheet_cells.items()
                     if r == row and isinstance(c.get("value"), (int, float))
                     and not isinstance(c.get("value"), bool)
                     and abs(float(c["value"]) - float(declared)) <= 1e-9]
        findings.append({
            "model_node_id": concept.get("model_node_id"),
            "workbook_ref": ref,
            "declared_value": declared,
            "cell_value": found,
            "cell_is_unit": isinstance(found, str) and is_unit_only(found),
            "value_found_at": sorted(c["locator"] for c in elsewhere) or None,
            "verdict": ("ref points at a unit cell" if isinstance(found, str)
                        and is_unit_only(found) else
                        "cell is empty" if found is None else
                        "cell holds a different number"),
        })
    return findings


def binding_resolution(proposals: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Turn ADMITTED proposals into execution_mapping_compiler's input shape.

    Refuses anything still marked PROPOSED. A binding reaches the compiler only
    because a person put it there.
    """
    out: list[dict[str, str]] = []
    for p in proposals:
        if p.get("status") != "ADMITTED":
            continue
        ref, node_id = p.get("workbook_ref"), p.get("model_node_id")
        if ref and node_id:
            out.append({"locator": str(ref).split(".xlsx:")[-1], "model_node_id": str(node_id)})
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: workbook_concept_binder.py <workbook_formula_graphs.json> "
              "<execution_mapping.json>", file=sys.stderr)
        return 2
    graphs = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    mapping = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    graph = graphs["workbooks"][0]["graph"]
    concepts = mapping.get("model_nodes", [])
    refs = {c["model_node_id"]: c.get("workbook_ref") or ""
            for c in concepts if c.get("workbook_ref")}
    proposals = propose(graph, concepts, refs)
    report = score_proposals(proposals)
    print(json.dumps(report, indent=2))
    print(f"\nadmitted bindings available: {len(binding_resolution(proposals))} "
          f"(every proposal starts PROPOSED — admission is a human act)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
