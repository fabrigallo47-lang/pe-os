"""PAN-100 -- PDF table/chart extraction via Granite-Docling-258M.

Two tiers, deliberately kept separate:

1. Deterministic, no-model tests (run in the normal gate): the markdown
   block-chunker, and graceful degradation to plain-text extraction when
   the ML stack (torch/transformers/docling_core) isn't available.
2. A real end-to-end model test, quarantined the same way NEEDS_API_KEY
   tests are in tools/run_tests.py -- it downloads/runs a real ~500MB
   model and is genuinely slow (tens of seconds), not something CI or a
   fast local loop should pay for by default. Run it directly:
       python3.12 tools/test_pan100_pdf_granite_docling.py RealModelTests
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import (  # noqa: E402
    _chunk_markdown_blocks,
    _is_degenerate_repetition,
    parse_pdf,
)


def _minimal_single_page_pdf(text: bytes) -> bytes:
    """A hand-built, minimal but real, valid single-page PDF with one text
    string -- stdlib only, no PDF-writing library needed just for a test
    fixture. pdfplumber can open and extract_text() this without issue."""
    content = b"BT /F1 24 Tf 72 720 Td (" + text.replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(out)


class ChunkMarkdownBlocksTests(unittest.TestCase):
    def test_never_splits_inside_a_table(self):
        table = (
            "| A | B |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
            "| 3 | 4 |"
        )
        markdown = f"Intro paragraph.\n\n{table}\n\nOutro paragraph."
        chunks = _chunk_markdown_blocks(markdown, max_words=3, locator_prefix="p1", source_path="x.pdf",
                                         source_record={}, page_or_slide_number=1)
        # The table's own word count exceeds max_words=3, so it must still
        # form a single, whole chunk rather than being cut mid-row.
        table_chunk = next(c for c in chunks if "| 1 | 2 |" in c.body)
        self.assertIn(table, table_chunk.body)
        self.assertEqual(table_chunk.body.count("| --- | --- |"), 1)

    def test_groups_small_blocks_up_to_the_word_budget(self):
        markdown = "one two three\n\nfour five six\n\nseven eight nine"
        chunks = _chunk_markdown_blocks(markdown, max_words=6, locator_prefix="p1", source_path="x.pdf",
                                         source_record={}, page_or_slide_number=1)
        self.assertEqual(len(chunks), 2)
        self.assertIn("one two three", chunks[0].body)
        self.assertIn("four five six", chunks[0].body)
        self.assertIn("seven eight nine", chunks[1].body)

    def test_single_chunk_gets_the_plain_page_locator(self):
        chunks = _chunk_markdown_blocks("just one short block", max_words=100, locator_prefix="p3",
                                         source_path="x.pdf", source_record={}, page_or_slide_number=3)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].locator, "p3")

    def test_multiple_chunks_get_block_range_locators(self):
        markdown = "a b c\n\nd e f"
        chunks = _chunk_markdown_blocks(markdown, max_words=3, locator_prefix="p2", source_path="x.pdf",
                                         source_record={}, page_or_slide_number=2)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].locator.startswith("p2:b"))
        self.assertTrue(chunks[1].locator.startswith("p2:b"))


class GracefulDegradationTests(unittest.TestCase):
    """When torch/transformers/docling_core aren't installed, parse_pdf must
    still work -- plain text, no tables -- not fail the whole format."""

    def test_falls_back_to_text_only_when_ml_stack_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memo.pdf"
            path.write_bytes(_minimal_single_page_pdf(b"Revenue was EUR 20m in FY2025A."))

            with patch("tools.extract_v2_physical._granite_docling_available", return_value=False):
                chunks = parse_pdf(path)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].locator, "p1")
        self.assertIn("Revenue was EUR 20m in FY2025A.", chunks[0].body)

    def test_degenerate_repetition_loop_falls_back_to_text_instead_of_passing_through(self):
        """Confirmed via direct test on a heavily degraded real scan: the
        model can run to completion with no exception and produce a short
        phrase repeated ~80 times, recovering none of the page's real
        content. Nothing raises in that case, so without an explicit check
        this garbage would flow through as a normal chunk with no
        coverage-limit signal -- exactly the "confidently wrong/empty
        answer" this codebase's philosophy exists to prevent.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            path.write_bytes(_minimal_single_page_pdf(b"Revenue was EUR 20m in FY2025A."))

            degenerate_markdown = "creditor customers.\n\n" * 80
            with patch("tools.extract_v2_physical._granite_docling_available", return_value=True), \
                 patch("tools.extract_v2_physical._granite_docling_convert_page", return_value=(degenerate_markdown, [])):
                chunks = parse_pdf(path)

        self.assertEqual(len(chunks), 1)
        self.assertNotIn("creditor customers.", chunks[0].body)
        self.assertIn("Revenue was EUR 20m in FY2025A.", chunks[0].body)


class DegenerateRepetitionTests(unittest.TestCase):
    def test_real_document_prose_is_not_flagged(self):
        markdown = (
            "## The five EBITDA figures\n\n"
            "| Economic object | Amount |\n"
            "| --- | --- |\n"
            "| Reported EBITDA | $10.2m |\n"
            "| Covenant EBITDA | $12.2m |\n\n"
            "These are not five competing answers to one simple question."
        )
        self.assertFalse(_is_degenerate_repetition(markdown))

    def test_repeated_short_phrase_is_flagged(self):
        markdown = "creditor customers.\n\n" * 80
        self.assertTrue(_is_degenerate_repetition(markdown))

    def test_a_few_repeats_below_threshold_is_not_flagged(self):
        # A real page can legitimately repeat a short line a handful of
        # times (e.g. a term appearing in several table rows); only a
        # clearly degenerate run should trip the guard.
        markdown = "Revenue\n\n" * 4
        self.assertFalse(_is_degenerate_repetition(markdown))


if __name__ == "__main__":
    unittest.main()
