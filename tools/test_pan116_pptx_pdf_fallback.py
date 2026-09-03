#!/usr/bin/env python3
"""A slide native reading could not touch gets a second, PDF-rendered look.

Native chart/table data (real numbers from the chart's own XML) always
stays primary and is never overridden -- these tests exist to pin that a
slide with genuine content is left alone, and that the fallback degrades
to nothing (never an exception) when soffice or a model is unavailable.
Runs with no soffice, no GPU, no python-pptx Presentation object: the
trigger predicate and the render helper are both pure enough to test with
plain strings and a stub engine.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from extract_v2 import _render_pptx_as_pdf, _slide_needs_pdf_fallback


class SlideNeedsFallbackTests(unittest.TestCase):

    def test_native_chart_text_does_not_trigger(self):
        parts = ["Q3 leads the revenue trajectory",
                "[Chart 1] Chart (COLUMN_CLUSTERED (51)): : Q1=10.0, Q2=15.0, Q3=22.0"]
        self.assertFalse(_slide_needs_pdf_fallback(parts))

    def test_image_not_extracted_triggers(self):
        parts = ["[Picture 1] IMAGE_NOT_EXTRACTED: a picture is present ..."]
        self.assertTrue(_slide_needs_pdf_fallback(parts))

    def test_unsupported_graphic_frame_triggers(self):
        parts = ["[Diagram] UNSUPPORTED_GRAPHIC_FRAME: a modern chart ..."]
        self.assertTrue(_slide_needs_pdf_fallback(parts))

    def test_empty_slide_does_not_trigger(self):
        self.assertFalse(_slide_needs_pdf_fallback([]))


class RenderPptxAsPdfDegradesGracefullyTests(unittest.TestCase):
    """The fallback must never turn a missing tool into a crash."""

    def test_no_soffice_returns_none(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(_render_pptx_as_pdf(
                Path("/does/not/matter.pptx"), lambda pdf: (lambda i, p: ("", []))))

    def test_soffice_present_but_export_fails_returns_none(self):
        import subprocess
        with mock.patch("shutil.which", return_value="/usr/bin/soffice"), \
             mock.patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "soffice")):
            self.assertIsNone(_render_pptx_as_pdf(
                Path("/does/not/matter.pptx"), lambda pdf: (lambda i, p: ("", []))))


if __name__ == "__main__":
    unittest.main()
