#!/usr/bin/env python3
"""Read wider than you write: each fragment sees its neighbours, extracts from itself.

Chunk boundaries cut references in half. derive_relations already admitted it --
"a derivation or scenario link whose counterpart lives in a different chunk
produces no edge here" -- and the benchmark measured relation_recall at 20% and
derivation_accuracy at 25%.

Overlapping EXTRACTION windows would fix that and introduce two new problems: the
same fact extracted twice, and an ambiguous locator for it. Padding that is read
but never extracted from has neither, and measured (GLM 5.2, same 11 cases):

    derivation_accuracy   25.0% -> 100.0%
    identity_accuracy     50.0% ->  66.7%
    measurement_accuracy  37.0% ->  52.6%
    relation_recall       10.0% ->  20.0%
    overall               75.1% ->  78.0%
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import (  # noqa: E402
    CONTEXT_PAD_WORDS, Chunk, _fragment_with_context, _pad_with_context,
)


def _chunk(index: int, body: str, source: str = "a.md") -> Chunk:
    return Chunk(chunk_id=f"c{index}", locator=f"loc{index}", body=body,
                 source_path=source, source_type="md", source_record={},
                 word_count=len(body.split()))


class PaddingTests(unittest.TestCase):
    def test_a_fragment_sees_both_neighbours(self) -> None:
        chunks = _pad_with_context(
            [_chunk(1, "alpha one two"), _chunk(2, "beta"), _chunk(3, "gamma three")],
            pad_words=2)
        self.assertEqual(chunks[1].context_before, "one two")
        self.assertEqual(chunks[1].context_after, "gamma three")

    def test_the_ends_of_a_document_are_not_padded_with_nothing(self) -> None:
        chunks = _pad_with_context([_chunk(1, "first"), _chunk(2, "last")], pad_words=4)
        self.assertEqual(chunks[0].context_before, "")
        self.assertEqual(chunks[-1].context_after, "")

    def test_padding_never_crosses_a_source_boundary(self) -> None:
        """A chunk seeing another document's text would let one source's numbers
        be attributed to another -- a provenance error, not a context win."""
        chunks = _pad_with_context(
            [_chunk(1, "doc a tail", "a.md"), _chunk(2, "doc b head", "b.md")],
            pad_words=4)
        self.assertEqual(chunks[1].context_before, "")
        self.assertEqual(chunks[0].context_after, "")

    def test_padding_is_bounded(self) -> None:
        chunks = _pad_with_context(
            [_chunk(1, " ".join(str(n) for n in range(500))), _chunk(2, "x")],
            pad_words=10)
        self.assertEqual(len(chunks[1].context_before.split()), 10)

    def test_zero_padding_is_a_no_op(self) -> None:
        chunks = _pad_with_context([_chunk(1, "a"), _chunk(2, "b")], pad_words=0)
        self.assertTrue(all(not c.context_before and not c.context_after for c in chunks))

    def test_the_default_is_small_on_purpose(self) -> None:
        """Padding is read, never extracted from, so a large value buys input
        tokens and diluted attention without ever adding a claim."""
        self.assertLessEqual(CONTEXT_PAD_WORDS, 200)


class PromptTests(unittest.TestCase):
    def test_an_unpadded_chunk_keeps_exactly_its_body(self) -> None:
        """The guard: sources that never pad must reach the model unchanged."""
        chunk = _chunk(1, "just the body")
        self.assertEqual(_fragment_with_context(chunk), "just the body")

    def test_the_extractable_region_is_named_unmistakably(self) -> None:
        chunk = _chunk(2, "the fragment")
        chunk.context_before, chunk.context_after = "before text", "after text"
        prompt = _fragment_with_context(chunk)
        self.assertIn("do NOT extract claims from this", prompt)
        self.assertIn("extract ONLY from this", prompt)
        self.assertIn("must be stated in the FRAGMENT itself", prompt)

    def test_every_region_reaches_the_model(self) -> None:
        chunk = _chunk(3, "MIDDLE")
        chunk.context_before, chunk.context_after = "LEFT", "RIGHT"
        prompt = _fragment_with_context(chunk)
        for text in ("LEFT", "MIDDLE", "RIGHT"):
            self.assertIn(text, prompt)

    def test_the_fragment_is_delimited_on_both_sides(self) -> None:
        """Without a closing marker the model cannot tell where its licence to
        extract ends, and a claim from the padding would carry this chunk's
        locator while its text lives in the neighbour."""
        chunk = _chunk(4, "body")
        chunk.context_after = "tail"
        prompt = _fragment_with_context(chunk)
        self.assertIn("----- FRAGMENT (extract ONLY from this) -----", prompt)
        self.assertIn("----- END FRAGMENT -----", prompt)
        self.assertLess(prompt.index("----- END FRAGMENT -----"), prompt.index("tail"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
