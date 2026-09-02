"""PAN-102 -- XLSX header-path recovery, formatting-as-semantics, dropped-row fix.

Builds a small synthetic workbook that exercises the exact three real
failure modes found by hand-reading the real Keystone LBO model
(merged-cell titles invisible outside their top-left cell, section/period
header rows silently dropped on any formula-bearing sheet, and font-color
role blind to the standard IB/LBO input/formula/cross-sheet-link
convention), rather than depending on that large real fixture for a fast,
deterministic unit test.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2 import parse_xlsx  # noqa: E402


class PAN102XlsxSemanticContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "model.xlsx"

        wb = openpyxl.Workbook()
        model = wb.active
        model.title = "Model"
        model["A1"] = "Test Model Title"
        model.merge_cells("A1:C1")

        model["A3"] = "Line Item"
        model["B3"] = "FY2023"
        model["C3"] = "FY2024"

        model["A4"] = "Revenue"
        model["B4"] = 100
        model["B4"].font = Font(color="FF0000FF")  # blue -- hardcoded input
        model["C4"] = "=B4*1.1"
        model["C4"].font = Font(color="FF000000")  # black -- ordinary formula

        model["A5"] = "Section Title"  # text-only label row, no formula, no number

        model["A6"] = "Linked"
        model["B6"] = "='Other'!B1"
        model["B6"].font = Font(color="FF008000")  # green -- cross-sheet link

        other = wb.create_sheet("Other")
        other["B1"] = 42

        wb.save(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def _model_chunk_body(self) -> str:
        chunks = parse_xlsx(self.path)
        model_chunks = [c for c in chunks if c.section_heading == "Model"]
        self.assertEqual(len(model_chunks), 1)
        return model_chunks[0].body

    def test_merged_title_propagates_across_its_full_span(self):
        body = self._model_chunk_body()
        self.assertIn("A1=Test Model Title", body)
        self.assertIn("B1=Test Model Title", body)
        self.assertIn("C1=Test Model Title", body)

    def test_text_only_label_row_is_not_dropped_on_a_formula_sheet(self):
        body = self._model_chunk_body()
        # Model has a formula (C4), so the old filter dropped every row
        # without one of its own -- including this pure section-title row.
        self.assertIn("A5=Section Title", body)

    @staticmethod
    def _cell_piece(body: str, coordinate: str) -> str:
        """Cells within one row are '|'-joined on a single line; isolate one."""
        for line in body.splitlines():
            for piece in line.split(" | "):
                if piece.startswith(f"{coordinate}="):
                    return piece
        raise AssertionError(f"{coordinate} not found in body")

    def test_input_cell_gets_row_and_column_header_and_role(self):
        piece = self._cell_piece(self._model_chunk_body(), "B4")
        self.assertIn("Revenue", piece)
        self.assertIn("FY2023", piece)
        self.assertIn("role=input", piece)

    def test_formula_cell_gets_row_and_column_header(self):
        piece = self._cell_piece(self._model_chunk_body(), "C4")
        self.assertIn("Revenue", piece)
        self.assertIn("FY2024", piece)

    def test_cross_sheet_formula_is_classified(self):
        piece = self._cell_piece(self._model_chunk_body(), "B6")
        self.assertIn("role=cross_sheet_link", piece)

    def test_header_row_itself_is_not_self_annotated(self):
        body = self._model_chunk_body()
        line = next(l for l in body.splitlines() if l.startswith("A3="))
        self.assertNotIn("[", line)


if __name__ == "__main__":
    unittest.main()
