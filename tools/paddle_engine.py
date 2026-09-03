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
import sys
from pathlib import Path

CHART_RECOGNITION = os.environ.get("PE_OS_PADDLE_CHARTS", "") == "1"


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
                        f"{str(content).strip()}"
                    )
                else:
                    pictures.append(f"{label}{where}")
                continue
            if content and str(content).strip():
                parts.append(str(content).strip())
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
