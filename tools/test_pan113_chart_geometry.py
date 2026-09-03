#!/usr/bin/env python3
"""A chart pairing is checked against where the text actually sits.

Knowing a number appears somewhere on the page says nothing about which bar
it belongs to. In a column chart the value sits above its category label, so
a correct pair shares an x-centre and a wrong one does not -- and that is a
rule a human can re-check from the numbers printed in the output, unlike a
model's reading of pixels.

The measurements here are the real ones from Goldman's investor-day deck.
"""
from __future__ import annotations

import unittest

from tools.paddle_engine import _verify_pairs_geometrically

CHART_BOX = [174, 339, 456, 708]        # page 9's chart, 282px wide


def line(text: str, cx: int, cy: int, w: int = 40, h: int = 20):
    return (text, [cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2])


# Page 9 as OCR actually read it: values above, labels below, one pixel of
# horizontal drift between a value and its own label.
PAGE9 = [line("$50.4", 396, 388), line("$35.3", 260, 468),
         line("2017-2019", 259, 694), line("2020-2022", 395, 694)]

GOOD = "Year | Value ($)\n2017-2019 | 35.3\n2020-2022 | 50.4"
SWAPPED = "Year | Value ($)\n2017-2019 | 50.4\n2020-2022 | 35.3"


class ChartGeometryTests(unittest.TestCase):

    def test_correct_pairing_is_confirmed(self) -> None:
        ok, bad, _ = _verify_pairs_geometrically(CHART_BOX, GOOD, PAGE9)
        self.assertEqual(len(ok), 2)
        self.assertEqual(bad, [])

    def test_swapped_pairing_is_contradicted(self) -> None:
        """The failure the value check cannot see: both numbers are real."""
        ok, bad, _ = _verify_pairs_geometrically(CHART_BOX, SWAPPED, PAGE9)
        self.assertEqual(ok, [])
        self.assertEqual(len(bad), 2)
        self.assertIn("centres", bad[0])

    def test_tolerance_scales_with_chart_width(self) -> None:
        """A fixed pixel tolerance would pass everything on a narrow chart.

        The columns here are 136px apart and the drift is 1px, so a
        width-relative tolerance separates them; one set to a large constant
        would call the swapped pairing correct too.
        """
        narrow = [50, 0, 90, 300]        # 40px wide
        lines = [line("A", 55, 250, w=6), line("1", 85, 100, w=6)]
        ok, bad, _ = _verify_pairs_geometrically(narrow, "H | V\nA | 1", lines)
        self.assertEqual(ok, [])
        self.assertEqual(len(bad), 1)

    def test_text_absent_from_ocr_is_unchecked_not_confirmed(self) -> None:
        """Missing evidence must never be reported as supporting evidence."""
        ok, bad, skipped = _verify_pairs_geometrically(
            CHART_BOX, "Year | Value\n1066 | 99.9", PAGE9)
        self.assertEqual(ok, [])
        self.assertEqual(bad, [])
        self.assertEqual(len(skipped), 1)

    def test_currency_and_punctuation_do_not_block_matching(self) -> None:
        """The table says 35.3 where the page says $35.3."""
        ok, _, _ = _verify_pairs_geometrically(CHART_BOX, GOOD, PAGE9)
        self.assertTrue(any("35.3" in pair for pair in ok))

    def test_no_box_or_no_content_returns_nothing(self) -> None:
        self.assertEqual(_verify_pairs_geometrically(None, GOOD, PAGE9), ([], [], []))
        self.assertEqual(_verify_pairs_geometrically(CHART_BOX, "", PAGE9), ([], [], []))


if __name__ == "__main__":
    unittest.main()
