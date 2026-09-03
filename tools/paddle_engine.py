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
                if content and str(content).strip():
                    # Chart recognition ran. Mark it as model-derived, not read.
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
