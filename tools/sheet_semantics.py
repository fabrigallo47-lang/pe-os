#!/usr/bin/env python3
"""
sheet_semantics — infer what a cell *means*, with the evidence for it.

extract_v3 gives a computable graph of cells. `CASHFLOW!B3` is not a concept
though: nothing downstream can bind it to quarterly interest expense. This
module builds that bridge.

Design rule
-----------
Deterministic first, model only where there is genuine ambiguity. Everything
here is deterministic: labels come from the sheet's own text, units from number
formats and label suffixes, periods from column headers. Each proposal carries
the cells its evidence came from, so a human can check the reasoning rather than
the conclusion — the same stance as the grounding gate on claims.

What this does NOT do is decide. A proposal below the confidence floor is
routed to review, not silently bound. An LLM pass over the low-confidence
remainder is the intended next layer, not a replacement for this one.

Layout assumption, stated openly
--------------------------------
Financial models are overwhelmingly laid out as a label column on the left and
a period header row on top. That is an assumption, not a law, so
`infer_orientation` measures it per sheet and reports what it found instead of
taking it for granted.

    python3 tools/sheet_semantics.py --workbook model.xlsx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ── period recognition ───────────────────────────────────────────────────────

_PERIOD_PATTERNS = [
    (re.compile(r"^FY\s?(\d{4})\s?([AEF])?$", re.I),        "fiscal_year"),
    (re.compile(r"^(\d{4})\s?([AEF])$", re.I),              "fiscal_year"),
    (re.compile(r"^Q([1-4])\s?(FY)?\s?(\d{2,4})?$", re.I),  "quarter"),
    (re.compile(r"^(LTM|NTM)\b", re.I),                     "trailing"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"),                    "date"),
    (re.compile(r"^(Opening|Closing|Entry|Exit)$", re.I),   "anchor"),
]


def classify_period(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    for pattern, kind in _PERIOD_PATTERNS:
        if pattern.match(t):
            return kind
    return None


# ── unit recognition ─────────────────────────────────────────────────────────

_UNIT_FROM_LABEL = [
    (re.compile(r"\bmultiple\b|\(x\)|\bx\b\s*$", re.I), "x"),
    (re.compile(r"\brate\b|\bmargin\b|\bgrowth\b|%", re.I), "%"),
    (re.compile(r"\bdays\b|\bDSO\b|\bDPO\b", re.I), "days"),
    (re.compile(r"\bIRR\b", re.I), "%"),
    (re.compile(r"\bMOIC\b", re.I), "x"),
]


def infer_unit(label: str, number_format: str | None) -> tuple[str, str]:
    """(unit, where it came from). Number format beats label wording."""
    fmt = (number_format or "").lower()
    if "%" in fmt:
        return "%", "number_format"
    if "$" in fmt or "usd" in fmt:
        return "$", "number_format"
    if "€" in fmt or "eur" in fmt:
        return "€", "number_format"
    for pattern, unit in _UNIT_FROM_LABEL:
        if pattern.search(label or ""):
            return unit, "label"
    return "", "unknown"


# ── proposals ────────────────────────────────────────────────────────────────

@dataclass
class ConceptProposal:
    cell: str                      # SHEET!B3
    concept: str                   # human-readable name
    row_label: str = ""
    col_header: str = ""
    unit: str = ""
    unit_source: str = ""
    period_kind: str | None = None
    is_formula: bool = False
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)   # cells the label came from
    issues: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.confidence < 0.6 or bool(self.issues)


@dataclass
class SheetReport:
    sheet: str
    orientation: str                      # labels_left | labels_top | unclear
    label_column: str | None = None
    header_row: int | None = None
    proposals: list[ConceptProposal] = field(default_factory=list)

    @property
    def confident(self) -> list[ConceptProposal]:
        return [p for p in self.proposals if not p.needs_review]

    @property
    def review(self) -> list[ConceptProposal]:
        return [p for p in self.proposals if p.needs_review]


# ── inference ────────────────────────────────────────────────────────────────

def _is_text(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip()) and not v.startswith("=")


def infer_orientation(ws, probe_rows: int = 30, probe_cols: int = 20) -> tuple[str, str | None, int | None]:
    """
    Measure where the labels are instead of assuming.

    A label column is a column that is mostly text while the columns to its
    right are mostly numeric; a header row is the mirror image.
    """
    max_r = min(ws.max_row, probe_rows)
    max_c = min(ws.max_column, probe_cols)
    if max_r < 2 or max_c < 2:
        return "unclear", None, None

    def text_share_col(c: int) -> float:
        vals = [ws.cell(row=r, column=c).value for r in range(1, max_r + 1)]
        seen = [v for v in vals if v is not None]
        return (sum(1 for v in seen if _is_text(v)) / len(seen)) if seen else 0.0

    def text_share_row(r: int) -> float:
        vals = [ws.cell(row=r, column=c).value for c in range(1, max_c + 1)]
        seen = [v for v in vals if v is not None]
        return (sum(1 for v in seen if _is_text(v)) / len(seen)) if seen else 0.0

    label_col = next((c for c in range(1, max_c + 1) if text_share_col(c) >= 0.7), None)
    header_row = next((r for r in range(1, max_r + 1) if text_share_row(r) >= 0.7), None)

    from openpyxl.utils import get_column_letter
    if label_col and header_row:
        return "labels_left", get_column_letter(label_col), header_row
    if label_col:
        return "labels_left", get_column_letter(label_col), None
    if header_row:
        return "labels_top", None, header_row
    return "unclear", None, None


def _row_is_blank(ws, row: int, max_col: int) -> bool:
    return all(ws.cell(row=row, column=c).value is None
               for c in range(1, max_col + 1))


def _col_is_blank(ws, col: int, max_row: int) -> bool:
    return all(ws.cell(row=r, column=col).value is None
               for r in range(1, max_row + 1))


def _scan_left(ws, row: int, col: int, limit: int = 12) -> tuple[str, str]:
    """Nearest label to the left, stopping at the block boundary."""
    max_row = min(ws.max_row, 200)
    for c in range(col - 1, max(1, col - limit) - 1, -1):
        # A fully empty column separates blocks: a label beyond it belongs to
        # a different table and must not be borrowed.
        if _col_is_blank(ws, c, max_row):
            return "", ""
        v = ws.cell(row=row, column=c).value
        if _is_text(v):
            return v.strip(), ws.cell(row=row, column=c).coordinate
    return "", ""


def _scan_up(ws, row: int, col: int, limit: int = 12) -> tuple[str, str]:
    """
    Nearest header above, stopping at the block boundary.

    Without this the scan crosses a blank row into the previous block and
    attaches, say, FY2024A to a covenant table that carries no period at all —
    a wrong answer delivered at high confidence, which is worse than none.
    """
    max_col = min(ws.max_column, 200)
    for r in range(row - 1, max(1, row - limit) - 1, -1):
        if _row_is_blank(ws, r, max_col):
            return "", ""
        v = ws.cell(row=r, column=col).value
        if _is_text(v):
            return v.strip(), ws.cell(row=r, column=col).coordinate
    return "", ""


def analyse_sheet(ws) -> SheetReport:
    orientation, label_col, header_row = infer_orientation(ws)
    report = SheetReport(sheet=ws.title.upper(), orientation=orientation,
                         label_column=label_col, header_row=header_row)

    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if v is None:
                continue
            is_formula = isinstance(v, str) and v.startswith("=")
            # A cell that holds only text is a label, not a quantity.
            if _is_text(v) and not is_formula:
                continue

            row_label, row_src = _scan_left(ws, cell.row, cell.column)
            col_header, col_src = _scan_up(ws, cell.row, cell.column)

            evidence = [c for c in (row_src, col_src) if c]
            issues: list[str] = []
            if not row_label and not col_header:
                issues.append("nessuna etichetta trovata né a sinistra né sopra")

            period_kind = classify_period(col_header)
            unit, unit_source = infer_unit(row_label, cell.number_format)

            # Confidence is built from what was actually found, so a reader can
            # see why a proposal is weak rather than trusting a bare number.
            confidence = 0.0
            if row_label:
                confidence += 0.55
            if col_header:
                confidence += 0.25
            if period_kind:
                confidence += 0.10
            if unit_source == "number_format":
                confidence += 0.10
            confidence = round(min(confidence, 1.0), 2)

            concept = " · ".join(p for p in (row_label, col_header) if p) or "?"
            report.proposals.append(ConceptProposal(
                cell=f"{ws.title.upper()}!{cell.coordinate}",
                concept=concept, row_label=row_label, col_header=col_header,
                unit=unit, unit_source=unit_source, period_kind=period_kind,
                is_formula=is_formula, confidence=confidence,
                evidence=evidence, issues=issues,
            ))
    return report


def analyse_workbook(path: Path) -> list[SheetReport]:
    try:
        import openpyxl
    except ImportError:
        sys.exit("serve openpyxl")
    # data_only=False so formula cells are visible as formulas, not stale values.
    wb = openpyxl.load_workbook(str(path), data_only=False)
    return [analyse_sheet(ws) for ws in wb]


def main() -> int:
    ap = argparse.ArgumentParser(description="Infer cell meaning from sheet layout")
    ap.add_argument("--workbook", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--show", type=int, default=6, help="righe da mostrare per foglio")
    a = ap.parse_args()

    reports = analyse_workbook(a.workbook)
    total = sum(len(r.proposals) for r in reports)
    conf = sum(len(r.confident) for r in reports)

    print(f"[sheet_semantics] {a.workbook.name}")
    for r in reports:
        print(f"\n  {r.sheet}  ({r.orientation}"
              f"{', etichette in ' + r.label_column if r.label_column else ''}"
              f"{', header riga ' + str(r.header_row) if r.header_row else ''})")
        print(f"    proposte {len(r.proposals)} · sicure {len(r.confident)} · da rivedere {len(r.review)}")
        for p in r.proposals[:a.show]:
            mark = " " if not p.needs_review else "?"
            unit = f" [{p.unit}]" if p.unit else ""
            per = f" ({p.period_kind})" if p.period_kind else ""
            print(f"      {mark} {p.cell:16} {p.concept}{unit}{per}  conf={p.confidence}")
        if len(r.proposals) > a.show:
            print(f"        … altre {len(r.proposals) - a.show}")

    print(f"\n  totale: {conf}/{total} sicure "
          f"({round(100 * conf / total) if total else 0}%), "
          f"{total - conf} in coda di revisione")

    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        payload = [{"sheet": r.sheet, "orientation": r.orientation,
                    "label_column": r.label_column, "header_row": r.header_row,
                    "proposals": [asdict(p) for p in r.proposals]} for r in reports]
        (a.out / "cell_semantics.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  → {a.out / 'cell_semantics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
