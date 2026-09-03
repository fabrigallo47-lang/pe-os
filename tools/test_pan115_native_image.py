#!/usr/bin/env python3
"""Standalone images (.png/.jpg/...) are a first-class parse_source format.

Before this, a raw image hit UNSUPPORTED_SOURCE unconditionally -- any
screenshot in a data room was simply rejected, even though the exact same
model that reads a PDF page can read a rendered image just as well. This
pins the dispatch and the degenerate/fallback behaviour with a stub
convert_page so it runs with no GPU, no model weights, and no network call.
"""
from __future__ import annotations

import io
import unittest
from pathlib import Path

from extract_v2_physical import IMAGE_SUFFIXES, parse_image, parse_source


def _tiny_png(path: Path) -> None:
    from PIL import Image
    Image.new("RGB", (40, 40), color="white").save(path)


class NativeImageTests(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.png = Path(self._tmp.name) / "shot.png"
        _tiny_png(self.png)

    def test_image_suffixes_are_recognised(self):
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
            self.assertIn(suffix, IMAGE_SUFFIXES)

    def test_parse_source_dispatches_images_to_parse_image(self):
        stub = lambda image, page_num: ("Risk: LOW", [])
        chunks = parse_source(self.png, convert_page=stub)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Risk: LOW", chunks[0].body)

    def test_convert_page_result_reaches_the_chunk_body(self):
        stub = lambda image, page_num: ("Approved investment EUR 42,500", ["chart"])
        chunks = parse_image(self.png, convert_page=stub)
        body = "\n".join(c.body for c in chunks)
        self.assertIn("EUR 42,500", body)
        self.assertIn("IMAGE_NOT_EXTRACTED", body)   # the picture marker, still declared

    def test_no_model_and_no_fallback_raises_a_declared_rejection(self):
        """Silence is not an acceptable outcome for an image nobody could read."""
        from extract_v2_physical import UnsupportedSourceError
        with self.assertRaises(UnsupportedSourceError):
            parse_image(self.png, convert_page=lambda image, page_num: ("", []))

    def test_vision_fallback_only_runs_when_the_model_path_is_empty(self):
        calls = []

        def vision_fallback(path):
            calls.append(path)
            return "fallback text"

        # Model path succeeds -- fallback must not be called.
        parse_image(self.png, convert_page=lambda i, p: ("real content", []),
                   vision_fallback=vision_fallback)
        self.assertEqual(calls, [])

        # Model path empty -- fallback is the only source of content.
        chunks = parse_image(self.png, convert_page=lambda i, p: ("", []),
                             vision_fallback=vision_fallback)
        self.assertEqual(calls, [self.png])
        self.assertIn("fallback text", chunks[0].body)
        self.assertIn("MODEL-DERIVED", chunks[0].body)


if __name__ == "__main__":
    unittest.main()
