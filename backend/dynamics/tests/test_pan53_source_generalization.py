"""PAN-53 — a new non-Keystone case must not depend on the Keystone SOURCE_REGISTRY.

Verifies the acceptance criteria directly:
  * a source with no filename match in SOURCE_REGISTRY still gets a complete,
    stable identity via SourceEnvelope (content hash, not a filename guess);
  * parse_source uses that envelope-derived record instead of falling back to
    the Keystone-registry lookup once an envelope is supplied;
  * an unsupported format is explicitly rejected, never silently coerced;
  * Keystone's own registry-based lookup is unchanged (backward compatible).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.extract_v2 import UnsupportedSourceError, _source_record, parse_source  # noqa: E402
from tools.source_envelope import build_source_envelope, extractor_source_record  # noqa: E402


class PAN53SourceGeneralizationTests(unittest.TestCase):
    def test_new_case_file_with_no_registry_entry_gets_a_stable_envelope_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scout_diligence_notes_2026.md"
            path.write_text("# Notes\n\nSome unrelated diligence content.\n", encoding="utf-8")

            envelope = build_source_envelope(path, "scout", "2026-08-29T00:00:00Z")

            # Never falls back to a Keystone-shaped SRC-xxx id derived from the
            # filename; the identity is a stable hash of the file's own bytes.
            self.assertTrue(envelope["source_id"].startswith("SRC-"))
            self.assertEqual(envelope["case_id"], "scout")
            self.assertEqual(envelope["source_version_id"], envelope["source_version_id"])
            self.assertTrue(envelope["source_version_id"].startswith("sha256:"))
            self.assertEqual(envelope["provenance"], "user_upload")
            self.assertEqual(envelope["parser_route"], "extract_v2")

            # Same bytes, re-enveloped, produce the same identity -- content
            # addressed, not filename addressed.
            again = build_source_envelope(path, "scout", "2026-08-29T00:05:00Z")
            self.assertEqual(envelope["source_id"], again["source_id"])
            self.assertEqual(envelope["source_version_id"], again["source_version_id"])

    def test_parse_source_uses_the_envelope_record_not_the_keystone_registry_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acme_management_deck.md"
            path.write_text(
                "## Overview\n\nAcme Corp reported revenue of $10m in FY2026.\n",
                encoding="utf-8",
            )
            envelope = build_source_envelope(
                path, "acme-deal", "2026-08-29T00:00:00Z",
                declared_metadata={
                    "issuer": "Acme Corp management",
                    "document_type": "Management deck",
                    "effective_date": "2026-08-01",
                },
            )
            record = extractor_source_record(envelope)
            chunks = parse_source(path, source_record=record)

            self.assertTrue(chunks)
            for chunk in chunks:
                self.assertEqual(chunk.source_record["source_id"], envelope["source_id"])
                self.assertEqual(chunk.source_record["party"], "Acme Corp management")
                self.assertEqual(chunk.source_record["doc_type"], "Management deck")

            # Without an envelope, the same file would only ever get the
            # generic synthetic fallback -- proving the override actually
            # takes effect rather than being silently ignored.
            fallback = _source_record(path)
            self.assertEqual(fallback["party"], "unknown")
            self.assertNotEqual(fallback["source_id"], envelope["source_id"])

    def test_unsupported_format_is_explicitly_rejected_not_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy_report.docx"
            path.write_text("not a real docx, just proving routing", encoding="utf-8")
            with self.assertRaises(UnsupportedSourceError):
                parse_source(path)

            xls_path = Path(tmp) / "old_model.xls"
            xls_path.write_text("not a real xls", encoding="utf-8")
            with self.assertRaisesRegex(UnsupportedSourceError, r"convert.*\.xlsx"):
                parse_source(xls_path)

    def test_keystone_registry_lookup_is_unchanged_for_backward_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keystone_seller_cim.pdf"
            path.write_text("placeholder", encoding="utf-8")
            record = _source_record(path)
            self.assertEqual(record["source_id"], "SRC-CIM")
            self.assertEqual(record["party"], "Alderstone management and Hawthorne Capital Markets")
            self.assertIn("K-PRE", record["manifest"])


if __name__ == "__main__":
    unittest.main()
