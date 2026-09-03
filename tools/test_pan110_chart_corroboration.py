#!/usr/bin/env python3
"""Chart-recognition output must be checked against the page's text layer.

PAN-100 found chart recognition produces "structurally confident but
factually wrong" values, which is why it is opt-in. The finding stands; what
changed is that it is now testable. In a vector PDF a chart's data labels are
real text objects, so a number the model reports should already be present as
read text -- and one that is not was not read, it was invented.

These tests pin the three outcomes that matter. The third is the one most
likely to rot: a rasterised page has no text layer to check against, and
"nothing to contradict it" must never be reported as corroboration.
"""
from __future__ import annotations

import unittest

from extract_v2 import _chart_corroboration

CHART = "[chart-recognition, MODEL-DERIVED not read text] bbox=[174, 339, 456, 708]"


class StubPage:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    def extract_words(self) -> list[dict]:
        return [{"text": t} for t in self._tokens]


# The real Goldman investor-day page 9 text layer, which is where these
# values genuinely sit despite the layout model calling the region a chart.
REAL = ["$35.3", "$50.4", "2017-2019", "2020-2022", "+43%"]


class ChartCorroborationTests(unittest.TestCase):

    def test_values_present_in_text_layer_are_corroborated(self) -> None:
        block = f"{CHART}\nYear | Value ($)\n2017-2019 | 35.3\n2020-2022 | 50.4"
        notes = _chart_corroboration(StubPage(REAL), block)
        self.assertEqual(len(notes), 1)
        self.assertIn("CORROBORATED", notes[0])
        # Corroborating the values must not be mistaken for confirming the
        # mapping: two real numbers can still be assigned to the wrong bars.
        self.assertIn("MAPPING", notes[0])

    def test_invented_values_are_named(self) -> None:
        block = (f"{CHART}\nYear | Value ($)\n2017-2019 | 35.3\n"
                 "2020-2022 | 61.7\n2023-2025 | 88.2")
        notes = _chart_corroboration(StubPage(REAL), block)
        self.assertIn("UNCORROBORATED", notes[0])
        for invented in ("61.7", "88.2", "2023-2025"):
            self.assertIn(invented, notes[0])
        self.assertNotIn("35.3", notes[0].split(":")[-1])

    def test_no_text_layer_makes_no_claim(self) -> None:
        """A rasterised page cannot corroborate anything -- and must not try."""
        block = f"{CHART}\nYear | Value ($)\n2017-2019 | 35.3"
        self.assertEqual(_chart_corroboration(StubPage([]), block), [])

    def test_currency_marks_do_not_break_matching(self) -> None:
        """'$50.4' on the page and '50.4' from the model are one value."""
        block = f"{CHART}\nYear | Value ($)\n2020-2022 | 50.4"
        self.assertIn("CORROBORATED", _chart_corroboration(StubPage(REAL), block)[0])

    def test_bbox_metadata_is_not_treated_as_a_value(self) -> None:
        """The header's bbox pixels describe where the chart is, not what it says.

        Validating them against the text layer flagged every chart as
        uncorroborated, which would have trained a reader to ignore the check.
        """
        block = f"{CHART}\nYear | Value ($)\n2017-2019 | 35.3\n2020-2022 | 50.4"
        notes = _chart_corroboration(StubPage(REAL), block)
        self.assertIn("CORROBORATED", notes[0])
        for pixel in ("174", "339", "456", "708"):
            self.assertNotIn(pixel, notes[0])

    def test_image_marker_is_not_mistaken_for_chart_output(self) -> None:
        """IMAGE_NOT_EXTRACTED mentions chart-recognition but carries no values."""
        marker = ("[picture] IMAGE_NOT_EXTRACTED: a chart bbox=[174, 339, 456, 708] "
                  "[chart-recognition output follows] is present on this page (PAN-100).")
        self.assertEqual(_chart_corroboration(StubPage(REAL), marker), [])


if __name__ == "__main__":
    unittest.main()
