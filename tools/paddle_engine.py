#!/usr/bin/env python3
"""Convert a PDF to per-page markdown with PaddleOCR-VL (PP-DocLayoutV3
layout + the 0.9B VLM), for comparison against Granite and classic Docling.

Runs as a SUBPROCESS in its own virtualenv, like tools/docling_engine.py,
and for a harder reason: paddlepaddle publishes no cp314 wheel at all, so
this cannot share an interpreter with a 3.14 environment. On the GPU image
everything is 3.13 and the split is only about transformers versions.

Measured locally on CPU: 12s for a chart page once models were cached --
not the 16 minutes an earlier attempt suggested, which came from feeding a
whole page to the experimental transformers shim with an OCR prompt
instead of using this pipeline.

Chart handling mirrors the Granite path deliberately. PP-DocLayoutV3
returns a `chart` block with a bounding box and, unless chart recognition
is enabled, empty content. That becomes an IMAGE_NOT_EXTRACTED marker
naming the label, its confidence and its box -- a declaration a human can
open, never invented numbers. With PE_OS_PADDLE_CHARTS=1 the optional
chart-to-table step runs and its output is included, still marked as
model-derived so it cannot be mistaken for read text.

Writes to a FILE, not stdout: like TableFormer, these pipelines log to
stdout and would corrupt JSON sharing that channel.

Run: /venvs/paddle/bin/python tools/paddle_engine.py <pdf> <out.json>
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

CHART_RECOGNITION = os.environ.get("PE_OS_PADDLE_CHARTS", "") == "1"
# A second OCR pass over the page, used only to find text the layout model
# never proposed a block for. Off with PE_OS_RECOVER_UNDETECTED=0.
RECOVER_UNDETECTED = os.environ.get("PE_OS_RECOVER_UNDETECTED", "1") != "0"


class _TableParser(HTMLParser):
    """Collect a <table> fragment as rows of plain-text cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._colspan = 1

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            try:
                self._colspan = max(1, int(dict(attrs).get("colspan", "1")))
            except ValueError:
                self._colspan = 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell).split())
            # A colspan cell is repeated across the columns it covers: a
            # merged header that silently shifts the columns under it turns
            # a readable table into a misaligned one.
            self._row.extend([text] * self._colspan)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _one_table_to_markdown(fragment: str) -> str:
    """Render one <table> fragment as a GitHub-flavoured pipe table.

    Returns the fragment UNCHANGED if nothing parsed. Emitting an empty
    table would silently drop the numbers a reviewer came to read, and a
    visible lump of HTML is a better failure than a confident blank.
    """
    parser = _TableParser()
    try:
        parser.feed(fragment)
    except Exception:
        return fragment
    rows = [r for r in parser.rows if r]
    if not rows:
        return fragment

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    cell = lambda c: c.replace("|", "\\|")           # noqa: E731
    out = ["| " + " | ".join(cell(c) for c in rows[0]) + " |",
           "| " + " | ".join("---" for _ in range(width)) + " |"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


_TABLE_RE = re.compile(r"<table\b.*?</table>", re.S | re.I)


def _tables_to_markdown(text: str) -> str:
    """Convert any <table> HTML inside a block to markdown.

    PaddleOCR-VL returns table blocks as HTML while Granite and classic
    Docling both go through export_to_markdown() and emit pipe tables. The
    UI escapes chunk bodies and renders them pre-wrap, so the HTML arrived
    as literal markup a reader cannot read -- and, worse, made the three
    engines look different where they actually agreed. Converting here
    keeps the field named "markdown" honest.
    """
    if "<table" not in text.lower():
        return text
    return _TABLE_RE.sub(lambda m: "\n" + _one_table_to_markdown(m.group(0)) + "\n", text)


def _ocr_lines_by_page(pdf: Path) -> dict[int, list[tuple[str, list[int]]]]:
    """Every text line the OCR model reads, with a box, per page.

    This exists because PP-DocLayoutV3 has a recall gap, not a reading
    problem. On Goldman's page 16 it proposed thirteen blocks and all
    thirteen were parsed -- but an entire second chart (AUS ($tn), $1.9,
    $2.1, $2.5, +13% CAGR) sat in none of them, so nothing ever read it. A
    region that is never proposed cannot be recovered by parsing the
    proposals better.

    Plain OCR detects text directly, with no layout opinion, and returns
    boxes in the SAME image space the layout blocks use -- which is what
    makes the two comparable. The PDF's own text layer cannot do this job:
    on this deck it lives inside a Form XObject whose matrix leaves glyphs
    reporting sub-point sizes at coordinates outside the page box.
    """
    from paddleocr import PaddleOCR

    # Orientation and unwarping are off: they are for photographed pages and
    # cost time on a born-digital slide that is already square.
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False)
    pages: dict[int, list[tuple[str, list[int]]]] = {}
    for index, res in enumerate(ocr.predict(str(pdf)), start=1):
        lines: list[tuple[str, list[int]]] = []
        polys = res.get("rec_polys")
        if polys is None:
            polys = res.get("dt_polys") or []
        for text, poly in zip(res.get("rec_texts") or [], polys):
            if not (text or "").strip():
                continue
            xs = [int(pt[0]) for pt in poly]
            ys = [int(pt[1]) for pt in poly]
            lines.append((text.strip(), [min(xs), min(ys), max(xs), max(ys)]))
        pages[index] = lines
    return pages


def _uncovered_lines(lines, boxes, pad: int = 8):
    """OCR lines whose centre falls in no layout block.

    Centre containment rather than full overlap: an OCR line and a layout
    block bound the same words slightly differently, and requiring
    containment would report half a paragraph as undetected.
    """
    out = []
    for text, box in lines:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        covered = any(b[0] - pad <= cx <= b[2] + pad and b[1] - pad <= cy <= b[3] + pad
                      for b in boxes if b)
        if not covered:
            out.append((text, box))
    return out


def _reading_order(lines, band: int = 20):
    """Sort boxed lines top-to-bottom, then left-to-right within a row."""
    return sorted(lines, key=lambda item: (item[1][1] // band, item[1][0]))


def _verify_pairs_geometrically(box, content: str, lines):
    """Check the chart model's label->value pairs against where the text sits.

    Corroborating that a number appears somewhere on the page says nothing
    about which bar it belongs to, and the header/empty-cell heuristics only
    notice a table that has visibly collapsed. Position settles it properly:
    in a column chart the value sits directly above its category label, so a
    correct pair shares an x-centre and a wrong one does not.

    On Goldman page 9 the OCR centres are $35.3 at x=260 against 2017-2019 at
    x=259, and $50.4 at x=396 against 2020-2022 at x=395 -- one pixel apart,
    where the columns themselves are 136px apart.

    Unlike a model's reading of pixels, this is an inspectable rule: two boxes
    either share a centre within the tolerance or they do not, and the numbers
    are in the output for a human to re-check.

    Returns (confirmed, contradicted, unchecked) label/value pair descriptions.
    """
    if not box or not content:
        return [], [], []
    rows = []
    for line in content.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            rows.append(cells)
    if len(rows) < 2:
        return [], [], []

    def centre_of(text):
        needle = _norm_compact(text)
        if not needle:
            return None
        for candidate, cbox in lines:
            cx, cy = (cbox[0] + cbox[2]) / 2, (cbox[1] + cbox[3]) / 2
            if not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
                continue
            if _norm_compact(candidate) == needle:
                return cx
        return None

    # A column is only meaningfully "the same" relative to the chart's width;
    # a fixed pixel tolerance would pass everything on a narrow chart.
    tolerance = max(8.0, (box[2] - box[0]) * 0.06)
    confirmed, contradicted, unchecked = [], [], []
    for cells in rows[1:]:
        label, values = cells[0], cells[1:]
        label_cx = centre_of(label)
        for value in values:
            if not any(ch.isdigit() for ch in value):
                continue
            value_cx = centre_of(value)
            pair = f"{label} -> {value}"
            if label_cx is None or value_cx is None:
                unchecked.append(pair)
            elif abs(label_cx - value_cx) <= tolerance:
                confirmed.append(pair)
            else:
                contradicted.append(f"{pair} (centres {int(label_cx)} vs {int(value_cx)})")
    return confirmed, contradicted, unchecked


def _unread_inside(block_box, content: str, lines) -> list[str]:
    """OCR lines sitting inside a block that its parsed content does not contain.

    A third failure mode, distinct from a region nobody proposed. Goldman's
    page 16 carries "+13% CAGR" INSIDE the detected chart box, so it counts
    as covered -- but chart recognition returns a data table and drops the
    annotation, and a covered region is never looked at again. The value is
    read, located, and still lost.

    Applied only to chart/figure/image blocks, where the content is a model's
    reading rather than a transcription. Running it over text blocks would
    report every OCR disagreement about a hyphen as missing content.
    """
    if not block_box:
        return []
    haystack = _norm_compact(content or "")
    out = []
    for text, box in lines:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        inside = (block_box[0] <= cx <= block_box[2] and block_box[1] <= cy <= block_box[3])
        if not inside:
            continue
        needle = _norm_compact(text)
        if needle and needle not in haystack:
            out.append(text)
    return out


def _norm_compact(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def _block_field(block, dict_key: str, attr: str):
    """Read one field from a parsing block, whichever shape it arrives in.

    paddleocr <= 3.6 yielded plain dicts keyed block_label/block_content/
    block_bbox. paddleocr 3.7.0 on paddlex 3.7.2 yields PaddleOCRVLBlock
    objects exposing .label/.content/.bbox instead, and dict access raises
    AttributeError. Reading both shapes keeps this engine tied to the model
    rather than to the wrapper class that happens to carry it.
    """
    if isinstance(block, dict):
        return block.get(dict_key)
    return getattr(block, attr, None)


def convert(pdf: Path) -> dict:
    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(use_chart_recognition=True) if CHART_RECOGNITION else PaddleOCRVL()

    ocr_pages: dict[int, list[tuple[str, list[int]]]] = {}
    if RECOVER_UNDETECTED:
        try:
            ocr_pages = _ocr_lines_by_page(pdf)
        except Exception as exc:                      # never lose the parse
            print(f"undetected-region recovery unavailable: {exc}", file=sys.stderr)

    pages: dict[str, dict] = {}
    for page_index, result in enumerate(pipeline.predict(str(pdf)), start=1):
        blocks = result.get("parsing_res_list", []) or []
        parts: list[str] = []
        pictures: list[str] = []
        for block in blocks:
            label = str(_block_field(block, "block_label", "label") or "")
            content = _block_field(block, "block_content", "content")
            box = _block_field(block, "block_bbox", "bbox")
            if label in ("chart", "image", "figure"):
                # The box is the locator a reviewer opens; keep it.
                where = f" bbox={list(box)}" if box else ""
                dropped = _unread_inside(box, str(content or ""),
                                         ocr_pages.get(page_index, []))
                if dropped:
                    parts.append(
                        f"[recovered] UNREAD_IN_CHART{where}: OCR reads these inside "
                        f"the chart region, but the chart output above does not "
                        f"contain them: " + " | ".join(dropped) +
                        ". Annotations are dropped by chart recognition, which "
                        "returns a data table; these are READ TEXT."
                    )
                if content and str(content).strip():
                    # Chart recognition ran. Mark it as model-derived, not read.
                    ok, bad, skipped = _verify_pairs_geometrically(
                        box, str(content), ocr_pages.get(page_index, []))
                    if ok or bad:
                        verdict = (f"{len(ok)} confirmed, {len(bad)} contradicted"
                                   + (f", {len(skipped)} unchecked" if skipped else ""))
                        detail = ""
                        if bad:
                            detail = (" CONTRADICTED: " + "; ".join(bad) +
                                      ". A value sitting over a different column than "
                                      "the label it was paired with is a mis-read "
                                      "mapping, not a mis-read number.")
                        elif ok:
                            detail = (" CONFIRMED by position: " + "; ".join(ok) +
                                      ". Each value shares an x-centre with its label, "
                                      "so the pairing is supported by where the text "
                                      "sits, not only by the model's say-so.")
                        parts.append(
                            f"[validation] GEOMETRY {verdict}.{detail}")
                    pictures.append(f"{label}{where} [chart-recognition output follows]")
                    parts.append(
                        f"[chart-recognition, MODEL-DERIVED not read text]{where}\n"
                        f"{_tables_to_markdown(str(content).strip())}"
                    )
                else:
                    pictures.append(f"{label}{where}")
                continue
            if content and str(content).strip():
                parts.append(_tables_to_markdown(str(content).strip()))
        boxes = [_block_field(b, "block_bbox", "bbox") for b in blocks]
        missed = _uncovered_lines(ocr_pages.get(page_index, []), boxes)
        # A lone short number in the margin is the slide number, which the
        # layout model labels `number` when it sees it and skips when it does
        # not. Reporting it as an undetected region on every page would bury
        # the real ones.
        if len(missed) == 1 and len(missed[0][0]) <= 3 and missed[0][0].isdigit():
            missed = []
        if missed:
            ordered = _reading_order(missed)
            xs0 = [b[0] for _, b in ordered]; ys0 = [b[1] for _, b in ordered]
            xs1 = [b[2] for _, b in ordered]; ys1 = [b[3] for _, b in ordered]
            region = [min(xs0), min(ys0), max(xs1), max(ys1)]
            # Deliberately NOT appended to `pictures`: that list becomes
            # IMAGE_NOT_EXTRACTED markers, and announcing "content was not
            # reliably extracted" about text we just recovered and printed
            # would contradict the line above it.
            parts.append(
                f"[recovered] UNDETECTED_REGION bbox={region}: the layout model "
                f"proposed no block covering this text, so nothing read it. "
                f"{len(ordered)} line(s), in reading order: "
                + " | ".join(t for t, _ in ordered)
            )

        pages[str(page_index)] = {
            "markdown": "\n\n".join(parts),
            "pictures": pictures,
        }
    return {"pages": pages, "page_count": len(pages),
            "chart_recognition": CHART_RECOGNITION}


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: paddle_engine.py <pdf> <out.json>", file=sys.stderr)
        return 2
    out_path = Path(sys.argv[2])
    captured = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, captured
    try:
        payload = convert(Path(sys.argv[1]))
        code = 0
    except Exception as exc:
        import traceback
        payload = {"error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()}
        code = 1
    finally:
        sys.stdout = real_stdout
    noise = captured.getvalue()
    payload["warnings"] = [l for l in noise.splitlines() if "WARNING" in l or "ERROR" in l]
    sys.stderr.write(noise)
    out_path.write_text(json.dumps(payload))
    return code


if __name__ == "__main__":
    sys.exit(main())
