#!/usr/bin/env python3
"""G6: the lens observes and narrates, and moves nothing.

The read-only property is proved, not asserted: every file under the deal is
hashed before and after, and the digests must be identical. "It only reads" is
the kind of claim that quietly stops being true.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.deal_state_lens import _frontmatter, narrate, observe  # noqa: E402

VAULT = ROOT / "vault"


def _fingerprint(root: Path) -> dict[str, str]:
    """Path -> content digest for every file beneath root."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _write_deal(root: Path) -> None:
    deal = root / "deals" / "demo"
    (deal / "questions").mkdir(parents=True)
    (deal / "claims").mkdir()
    (deal / "events").mkdir()
    (deal / "deal.md").write_text(
        "---\ntype: deal\nid: demo\nstate: S3_SCREENING_ASSESSMENT\n"
        "lead: \"[[fabrizio]]\"\nopened: 2026-07-13\n---\n", encoding="utf-8")
    (deal / "questions" / "q1.md").write_text(
        "---\nid: Q-01\nstate: open\ncritical: true\n---\n", encoding="utf-8")
    (deal / "questions" / "q2.md").write_text(
        "---\nid: Q-02\nstate: resolved\ncritical: false\n---\n", encoding="utf-8")
    (deal / "claims" / "c1.md").write_text(
        "---\nid: c1\nepistemic: observed\nbears-on:\n- Q-01\n---\n", encoding="utf-8")
    (deal / "claims" / "c2.md").write_text(
        "---\nid: c2\nepistemic: asserted\nbears-on: []\n---\n", encoding="utf-8")
    (deal / "events" / "e1.md").write_text(
        "---\nid: ev-1\nkind: DEAL_REGISTERED\nat: 2026-07-13T20:22:52\n---\n",
        encoding="utf-8")


class ReadOnlyTests(unittest.TestCase):
    def test_observing_changes_nothing_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "vault"
            _write_deal(root)
            before = _fingerprint(root)
            narrate(observe("demo", vault=root))
            self.assertEqual(_fingerprint(root), before,
                             "the lens wrote to the vault; it must only read")

    def test_observing_the_real_vault_changes_nothing(self) -> None:
        """The one that would actually cost something if it were wrong."""
        deal_dir = VAULT / "deals" / "astrelia"
        if not deal_dir.is_dir():
            self.skipTest("astrelia not present")
        before = _fingerprint(deal_dir)
        narrate(observe("astrelia"))
        self.assertEqual(_fingerprint(deal_dir), before)


class ObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "vault"
        _write_deal(self.root)
        self.picture = observe("demo", vault=self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_it_reports_the_resolved_state_rather_than_deriving_one(self) -> None:
        """Invariant 10: state is resolved by the backbone rule from events,
        exposure and blockers. A second implementation here would be a
        competing answer, and two answers is worse than none."""
        self.assertEqual(self.picture["state"], "S3_SCREENING_ASSESSMENT")

    def test_absent_state_is_said_plainly_not_filled_in(self) -> None:
        (self.root / "deals" / "demo" / "deal.md").unlink()
        text = narrate(observe("demo", vault=self.root))
        self.assertIn("no resolved state", text)
        self.assertNotIn("S3_", text)

    def test_open_and_critical_questions_are_separated(self) -> None:
        self.assertEqual(self.picture["questions"]["total"], 2)
        self.assertEqual(self.picture["questions"]["open"], 1)
        self.assertEqual(self.picture["questions"]["critical_open"], ["Q-01"])

    def test_a_claim_bearing_on_nothing_is_counted_as_unbound(self) -> None:
        """`bears-on: []` is an empty list written inline. Read as the string
        '[]' it is truthy, and a claim nobody asked for would count as bound.
        On the real keystone deal that is 19 claims of 836."""
        self.assertEqual(self.picture["claims"]["unbound"], 1)

    def test_flush_left_list_items_are_parsed(self) -> None:
        """Vault files write sequence items at column 0. Requiring indentation
        dropped every binding and reported 817 of 836 keystone claims unbound."""
        fm = _frontmatter(self.root / "deals" / "demo" / "claims" / "c1.md")
        self.assertEqual(fm["bears-on"], ["Q-01"])

    def test_a_missing_deal_is_reported_not_raised(self) -> None:
        picture = observe("no-such-deal", vault=self.root)
        self.assertFalse(picture["exists"])
        self.assertIn("no such deal", narrate(picture))

    def test_the_narration_says_it_holds_no_authority(self) -> None:
        self.assertIn("nothing here was admitted", narrate(self.picture))


if __name__ == "__main__":
    unittest.main(verbosity=2)
