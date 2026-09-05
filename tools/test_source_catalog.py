from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.extract_v2_physical import SOURCE_REGISTRY, SYSTEM_PROMPT, _source_record
from tools.source_catalog import (
    DOC_TYPE_BY_SOURCE_TYPE,
    load_source_catalog,
    source_record_from_catalog,
    unmapped_source_types,
)


class SourceCatalogTests(unittest.TestCase):
    def test_csv_load_preserves_quoted_comma_and_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.csv"
            path.write_text(
                "source_id,title,source_type,filename,effective_at,known_at\n"
                'SRC-1,"First line, with comma\nsecond line",qoe_report,'
                "nested/report.pdf,2026-01-01,2026-01-02\n",
                encoding="utf-8",
            )
            catalog = load_source_catalog(path)

        self.assertEqual(list(catalog), ["report.pdf"])
        self.assertEqual(catalog["report.pdf"]["title"],
                         "First line, with comma\nsecond line")

    def test_json_load_and_basename_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps([{
                "source_id": "SRC-2",
                "title": "Call",
                "source_type": "call_transcript",
                "filename": "00_RAW_CORPUS/call.txt",
                "effective_at": "",
                "known_at": "2026-02-01",
            }]), encoding="utf-8")
            catalog = load_source_catalog(path)

        record = source_record_from_catalog(Path("elsewhere/call.txt"), catalog)
        self.assertIsNotNone(record)
        self.assertEqual(record["source_id"], "SRC-2")
        self.assertEqual(record["effective_date"], "")

    def test_explicit_source_type_mapping(self) -> None:
        catalog = {
            "deck.pdf": {"source_id": "SRC-D", "title": "Deck",
                         "source_type": "qoe_report"},
            "memo.pdf": {"source_id": "SRC-M", "title": "Memo",
                         "source_type": "investment_memo"},
            "research.md": {"source_id": "SRC-R", "title": "Research",
                            "source_type": "internal_research"},
            "call.txt": {"source_id": "SRC-C", "title": "Call",
                         "source_type": "call_transcript"},
        }
        self.assertEqual(source_record_from_catalog("deck.pdf", catalog)["doc_type"], "QoE Report")
        self.assertEqual(source_record_from_catalog("memo.pdf", catalog)["doc_type"], "IC Memo")
        self.assertEqual(source_record_from_catalog("research.md", catalog)["doc_type"], "Internal")
        self.assertEqual(source_record_from_catalog("call.txt", catalog)["doc_type"], "Call Transcript")
        self.assertNotIn("call_transcript", unmapped_source_types(catalog))

    def test_labels_are_phrases_the_prompt_mapping_actually_names(self) -> None:
        """The point of the catalog, and the thing a plain vocabulary check misses.

        doc_type is interpolated into the prompt and read against SYSTEM_PROMPT's
        "Source -> class mapping" block, so a label absent from that block teaches
        the model nothing. Before this, every transcript in a non-Keystone deal
        arrived labelled Other and "call transcript -> observed" never fired.
        """
        mapping_block = SYSTEM_PROMPT.split("Source → class mapping")[1][:1200].casefold()
        for source_type in ("call_transcript", "qoe_report", "ic_memo", "seller_cim"):
            label = DOC_TYPE_BY_SOURCE_TYPE[source_type]
            self.assertIn(label.casefold(), mapping_block,
                          f"{source_type} -> {label!r} is not a phrase the mapping names")

    def test_unmapped_type_is_other_and_reported(self) -> None:
        catalog = {"call.txt": {
            "source_id": "SRC-C", "title": "Call",
            "source_type": "new_unclassified_source",
        }}
        self.assertEqual(source_record_from_catalog("call.txt", catalog)["doc_type"], "Other")
        self.assertEqual(unmapped_source_types(catalog), {"new_unclassified_source"})

    def test_missing_file_and_malformed_rows_do_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.csv"
            malformed = Path(temp_dir) / "malformed.json"
            malformed.write_text("not json", encoding="utf-8")
            incomplete = Path(temp_dir) / "incomplete.json"
            incomplete.write_text(json.dumps([
                {"source_id": "SRC-X", "title": "No filename"},
                "not a row",
            ]), encoding="utf-8")
            self.assertEqual(load_source_catalog(missing), {})
            self.assertEqual(load_source_catalog(malformed), {})
            self.assertEqual(load_source_catalog(incomplete), {})
        self.assertIsNone(source_record_from_catalog("missing.pdf", {}))

    def test_no_catalog_preserves_existing_behavior(self) -> None:
        registered = _source_record(Path("keystone_seller_cim.md"))
        self.assertIs(registered, SOURCE_REGISTRY["keystone_seller_cim"])
        unknown = _source_record(Path("new_deal_source.pdf"))
        self.assertEqual(unknown, {
            "source_id": "SRC-NEW_DEAL_SOU",
            "name": "new_deal_source",
            "party": "unknown",
            "doc_type": "Other",
            "effective_date": "",
            "known_at": "",
            "manifest": ["ALL"],
        })

    def test_registry_precedes_catalog(self) -> None:
        catalog = {"keystone_seller_cim.md": {
            "source_id": "WRONG", "title": "Wrong", "source_type": "qoe_report",
        }}
        self.assertIs(_source_record(Path("keystone_seller_cim.md"), catalog),
                      SOURCE_REGISTRY["keystone_seller_cim"])


if __name__ == "__main__":
    unittest.main()
