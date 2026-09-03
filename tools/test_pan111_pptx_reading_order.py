#!/usr/bin/env python3
"""A slide's shapes must be read in reading order, not z-order.

`slide.shapes` yields the order shapes were added to the XML. A deck author
who drew a value box before its caption gets those emitted in that order, so
the extraction holds every word and none of the relationships -- the failure
reported as "content is correct but position is a bit missing".

The two-column case is the one that matters. Sorting on `top` alone looks
like an improvement and is not: it interleaves the columns, which reads worse
than z-order did.
"""
from __future__ import annotations

import unittest

from extract_v2 import _pptx_reading_order

SLIDE_H = 6858000          # EMU, a standard 7.5in slide
INCH = 914400


class Shape:
    def __init__(self, name: str, top_in: float | None, left_in: float | None) -> None:
        self.name = name
        self.top = None if top_in is None else int(top_in * INCH)
        self.left = None if left_in is None else int(left_in * INCH)

    def __repr__(self) -> str:
        return self.name


def order(shapes: list[Shape]) -> list[str]:
    return [s.name for s in _pptx_reading_order(shapes, SLIDE_H)]


class PptxReadingOrderTests(unittest.TestCase):

    def test_z_order_is_replaced_by_reading_order(self) -> None:
        """Author drew the value first, the caption after; read caption first."""
        shapes = [Shape("value", top_in=3.0, left_in=1.0),
                  Shape("caption", top_in=1.0, left_in=1.0)]
        self.assertEqual(order(shapes), ["caption", "value"])

    def test_two_columns_are_not_interleaved(self) -> None:
        """The case that makes sorting by `top` alone worse than doing nothing.

        Left column rows sit a few points off the right column's, so a naive
        top sort would emit L1, R1, L2, R2 mixed by millimetres instead of
        reading each row across.
        """
        shapes = [
            Shape("R2", top_in=3.02, left_in=5.0),
            Shape("L1", top_in=1.00, left_in=0.5),
            Shape("R1", top_in=1.03, left_in=5.0),
            Shape("L2", top_in=3.00, left_in=0.5),
        ]
        self.assertEqual(order(shapes), ["L1", "R1", "L2", "R2"])

    def test_same_row_reads_left_to_right(self) -> None:
        shapes = [Shape("c", top_in=2.0, left_in=6.0),
                  Shape("a", top_in=2.0, left_in=1.0),
                  Shape("b", top_in=2.0, left_in=3.0)]
        self.assertEqual(order(shapes), ["a", "b", "c"])

    def test_unpositioned_shapes_keep_relative_order_at_the_end(self) -> None:
        """A placeholder inheriting its position must not be given a fake one."""
        shapes = [Shape("floating1", None, None),
                  Shape("bottom", top_in=5.0, left_in=1.0),
                  Shape("floating2", None, None),
                  Shape("top", top_in=1.0, left_in=1.0)]
        self.assertEqual(order(shapes), ["top", "bottom", "floating1", "floating2"])

    def test_no_slide_height_does_not_crash(self) -> None:
        """slide_height can be None; degrade to a plain top/left sort."""
        shapes = [Shape("b", top_in=2.0, left_in=1.0), Shape("a", top_in=1.0, left_in=1.0)]
        self.assertEqual([s.name for s in _pptx_reading_order(shapes, None)], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
