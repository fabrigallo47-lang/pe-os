#!/usr/bin/env python3
"""Run PANTA's extraction stack against one evaluation case.

Reads one case JSON on stdin, writes one prediction on stdout, per the
contract in evaluation/README.md.

Two stages, in that order, because that order is the point:

1. EXTRACT with the real pipeline -- tools/extract_v2.parse_source, with
   PDFs routed through the PaddleOCR-VL engine and everything it now
   carries: markdown tables, undetected-region recovery, chart-value
   corroboration and geometric pair checking, slide reading order.
2. ANSWER by handing that extraction to Claude, which shapes it into the
   fields the case asks for.

The model never sees the document. It sees only what stage 1 read, so a
wrong answer is a extraction failure or a reasoning failure and the two
stay separable -- which is the only reason this is worth measuring. Gold
labels are stripped by the harness before we are invoked, so nothing here
can peek at them.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Haiku by default: this stage reshapes text the pipeline already read into
# the case's answer fields. It is not the part under test, and paying for a
# frontier model to do it would price the harness out of routine use.
# Override with PE_OS_EVAL_MODEL to check whether a failure is the extraction
# or the model reading it.
MODEL = os.environ.get("PE_OS_EVAL_MODEL", "claude-haiku-4-5")
PADDLE_PYTHON = Path(os.environ.get("PE_OS_PADDLE_PYTHON",
                                    "/venvs/paddle/bin/python"))
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _paddle_convert(pdf: Path):
    """Route a PDF (or an image, PaddleOCR-VL accepts both) through the real
    engine, exactly as the test UI does. Shaped as Path -> convert_page,
    which doubles as the pdf_engine factory parse_pptx's PDF-fallback tier
    needs (it does not know the exported PDF's path until soffice creates
    it, so it cannot receive a pre-bound convert_page)."""
    from extract_v2 import ROOT as _  # noqa: F401  (import guard)

    out_json = pdf.with_suffix(".eval.paddle.json")
    proc = subprocess.run(
        [str(PADDLE_PYTHON), str(ROOT / "tools" / "paddle_engine.py"),
         str(pdf), str(out_json)],
        capture_output=True, timeout=1800,
    )
    if not out_json.exists():
        tail = proc.stderr.decode("utf-8", errors="replace")[-400:]
        raise RuntimeError(f"paddle engine produced nothing: {tail}")
    payload = json.loads(out_json.read_text())
    if "error" in payload:
        raise RuntimeError(f"paddle engine failed: {payload['error']}")
    pages = payload.get("pages", {})

    def convert(image, page_num):
        page = pages.get(str(page_num)) or {}
        return page.get("markdown", ""), page.get("pictures", [])

    return convert


def extract(path: Path) -> str:
    """Everything the pipeline reads from one file, as text with locators.

    Images and PDFs share one convert_page (a bound per-page callable,
    since parse_pdf/parse_image already know the file they are reading).
    PPTX's PDF-fallback tier needs the factory form instead -- it creates
    its own PDF internally via soffice, so it cannot receive a callable
    pre-bound to a file it doesn't have yet -- and _paddle_convert is
    already exactly that shape.
    """
    from extract_v2 import parse_source

    suffix = path.suffix.lower()
    convert_page = _paddle_convert(path) if suffix in (".pdf", *IMAGE_SUFFIXES) else None
    pdf_engine = _paddle_convert if suffix == ".pptx" else None
    chunks = parse_source(path, convert_page=convert_page, pdf_engine=pdf_engine)
    return _render_chunks(chunks)


def _render_chunks(chunks) -> str:
    """Render chunks as locator-tagged text, headers and attachments included.

    Email headers and attachment filenames live on chunk.provenance, not
    chunk.body -- parse_email keeps them out of the body on purpose so
    re-chunking never splits a header across a word boundary. They still
    need to reach the answering stage, or "who is this from" has no source
    to cite even though the extractor read it.
    """
    parts = []
    for chunk in chunks:
        block = f"<<locator: {chunk.locator}>>\n{chunk.body}"
        prov = getattr(chunk, "provenance", None) or {}
        headers = prov.get("headers")
        if headers:
            block += "\n[headers] " + " | ".join(f"{k}={v}" for k, v in headers.items())
        names = prov.get("attachment_filenames")
        if names:
            block += "\n[attachments] " + ", ".join(names)
        parts.append(block)
    return "\n\n".join(parts)


MIN_USABLE_CHARS = 40   # below this an image/pdf extraction counts as "failed", not "short"


def _looks_degenerate(text: str, suffix: str) -> bool:
    """Whether an extraction is weak enough to warrant the vision fallback.

    Only applied to formats a vision model could plausibly rescue (images,
    PDFs) -- an empty XLSX extraction means the workbook was genuinely
    blank, not that a VLM should improvise numbers over a spreadsheet it
    was never shown.
    """
    if suffix not in (".pdf", *IMAGE_SUFFIXES):
        return False
    stripped = (text or "").strip()
    return not stripped or stripped.startswith("(extraction failed") or len(stripped) < MIN_USABLE_CHARS


def _vision_fallback_haiku(path: Path) -> str:
    """Last resort: ask Haiku 4.5 to transcribe the raw file directly when
    the local model pipeline (Granite/Paddle, run on the GPU pod, no
    Anthropic call) produced nothing usable.

    Lives here, not in tools/extract_v2.py, on purpose: this is the only
    place in the whole pipeline that already holds the Anthropic API key
    and already makes a cloud call (the answering stage). Wiring a live
    Anthropic call into the core extractor would be new cloud egress on a
    path meant to stay local-model-only under invariant 7 -- exactly the
    kind of thing that needs a policy-table row, not a silent default.
    This function is an explicit, separately-invoked safety net, not
    something parse_source ever calls on its own.

    The instruction is transcription, not interpretation: report only what
    is visibly present, do not infer or complete partial values. Every
    other output in this pipeline carries a marker saying whether it was
    read or model-derived; this one is model-derived by construction (a
    model looked at pixels), so it is always tagged that way.
    """
    import base64
    import anthropic

    media_type = {".pdf": "application/pdf"}.get(
        path.suffix.lower(), f"image/{path.suffix.lower().lstrip('.')}")
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    block_type = "document" if media_type == "application/pdf" else "image"

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": [
            {"type": block_type, "source": {"type": "base64", "media_type": media_type,
                                            "data": data}},
            {"type": "text", "text": (
                "Transcribe every piece of text and every numeric value visible in "
                "this file, exactly as shown. Do not infer, complete, or explain "
                "anything not literally present. Plain text output, no commentary."
            )},
        ]}],
    )
    if response.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in response.content if b.type == "text").strip()


def _apply_vision_fallback(extracted: dict[str, str], case: dict) -> None:
    """Replace any degenerate extraction in place with a Haiku transcription.

    Runs after the extraction stage regardless of whether it came from the
    pod cache or a live local run -- both can leave an input's text empty
    or failed, and the fallback only needs the case's declared input path
    to find the original file and try again.
    """
    inputs_by_id = {i.get("input_id"): i for i in case.get("inputs", [])}
    for input_id, text in list(extracted.items()):
        item = inputs_by_id.get(input_id) or {}
        rel = item.get("path") or item.get("uri")
        suffix = Path(rel).suffix.lower() if rel else ""
        if not rel or not _looks_degenerate(text, suffix):
            continue
        transcription = _vision_fallback_haiku(ROOT / rel)
        if transcription:
            extracted[input_id] = (
                "[vision-fallback, MODEL-DERIVED transcription, not read text -- "
                f"the local model pipeline returned nothing usable]\n{transcription}")


SYSTEM = """You convert an already-extracted document into one evaluation prediction.

You never see the source file. You see only what PANTA's extraction pipeline
read from it, with each block preceded by <<locator: ...>>. Work strictly from
that text.

Return ONE JSON object and nothing else. Allowed keys: status, answer, content,
fields, media, elements, evidence, confidence.

- status: "success" when the extraction supports an answer; "abstained" when the
  question cannot be answered from it. Abstaining when the text truly lacks the
  answer is correct behaviour and is scored as such -- guessing is not.
- answer: a string for a plain question, or an object when the query asks for
  several named values. Numbers that are numbers should be JSON numbers.
- fields: [{"name","value","input_id","locator"}] for field extraction.
- content: the document's readable text, for parsing tasks.
- media: [{"media_type","filename","locator","text"}] for images/attachments.
- evidence: [{"input_id","locator","quote","role"}] citing the blocks you used.

`role` MUST be exactly one of: "answer", "supporting", "contradicting", "context".
Use "answer" for the block the answer came from. No other value validates --
"primary", "source", "main" and the like are rejected outright.

`locator` MUST match one of these shapes exactly, including every required key:
  {"type":"page","page":1}                     (optional: index_base, bbox)
  {"type":"slide","slide":1}                   (optional: bbox)
  {"type":"cell","sheet":"Summary","range":"B4"}
  {"type":"word","section":"..."}              (section optional)
  {"type":"email_part","part":"body_text"}     (part is required; also
      "subject" / "headers" / "attachment"; optional message_id, attachment_name)
  {"type":"attachment","attachment_name":"x.pdf"}
  {"type":"image_region","bbox":[x0,y0,x1,y1]} (bbox is REQUIRED; optional
      page, slide, image_id)
Any id you copy into a locator (message_id, image_id, and similar) MUST be
copied byte-for-byte from where it appears in the extracted text -- including
surrounding punctuation like the angle brackets on an email Message-Id
(`<id@host>`). Locators are matched by exact string equality, so "cleaning up"
an id by trimming characters that look decorative turns a correct answer into
a scored miss.

Pick the shape matching the input's format. Omit bbox when the extraction gives
you no coordinates -- except for image_region, where it is required, so use the
region's coordinates if the extraction reports any and the full image extent
otherwise.

`confidence`, if given, MUST be a number between 0 and 1 -- not "high"/"low".

For a parsing task, also populate what the extraction shows:
- `elements`: [{"type","text","order","input_id","locator"}] where type is
  "title" / "paragraph" / "table" / "list" / "heading".
- `media`: [{"media_type","filename","locator","text"}] with media_type
  "image" / "chart" / "attachment". The extraction marks images and charts with
  [picture] / IMAGE_NOT_EXTRACTED / [chart] markers, and email attachments by
  filename -- report each one you can see, since an unreported attachment
  scores the same as one that was never found.

Report only what the extracted text supports."""


def answer(case: dict, extracted: dict[str, str]) -> dict:
    import anthropic

    blocks = "\n\n".join(
        f"### input_id: {input_id}\n{text or '(nothing extracted)'}"
        for input_id, text in extracted.items())
    query = case.get("query") or "(no query: return the parsed content itself)"
    prompt = (f"TASK: {case.get('task')}\nQUERY: {query}\n\n"
              f"EXTRACTED DOCUMENT TEXT:\n{blocks}")

    # Adaptive thinking is a 4.6+ parameter; Haiku 4.5 rejects it. Sent only
    # when the configured model actually takes it, so switching models with
    # PE_OS_EVAL_MODEL does not turn into a 400.
    extra = {}
    if not MODEL.startswith("claude-haiku-4-5"):
        extra["thinking"] = {"type": "adaptive"}

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        **extra,
    )
    if response.stop_reason == "refusal":
        return {"status": "error", "error": "model refused"}
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    return json.loads(text)


def main() -> int:
    case = json.load(sys.stdin)
    started = time.perf_counter()
    prediction = {"schema_version": "panta-eval.prediction/1.0",
                  "test_id": case.get("test_id"),
                  "system": {"name": "panta-extraction", "version": "PAN-113"}}
    try:
        # Stage 1 normally runs on the GPU pod and leaves its output here, so
        # the API key never has to travel to a rented machine -- and a scoring
        # change can be re-measured without re-reading every document.
        cache_path = os.environ.get("PE_OS_EXTRACTIONS")
        if cache_path:
            cached = json.loads(Path(cache_path).read_text())
            extracted = dict(cached.get(case.get("test_id"), {}))
            if not extracted:
                raise RuntimeError(f"no cached extraction for {case.get('test_id')}")
        else:
            extracted = {}
            for item in case.get("inputs", []):
                path = item.get("path") or item.get("uri")
                input_id = item.get("input_id")
                try:
                    extracted[input_id] = extract(ROOT / path)
                except Exception as exc:        # one bad input must not void the rest
                    extracted[input_id] = f"(extraction failed: {type(exc).__name__}: {exc})"
        _apply_vision_fallback(extracted, case)
        prediction.update(answer(case, extracted))
        prediction.setdefault("status", "success")
    except Exception as exc:
        prediction["status"] = "error"
        prediction["error"] = f"{type(exc).__name__}: {exc}"
    prediction["latency_ms"] = int((time.perf_counter() - started) * 1000)
    json.dump(prediction, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
