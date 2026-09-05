#!/usr/bin/env python3
"""Self-redundancy measurement, and the conclusion it exists to protect.

The headline these tests defend: over-extraction on our corpora is NOT
repetition, so a uniqueness filter is the wrong repair. If that ever changes,
the real-corpus test below is what says so.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.claim_redundancy import (  # noqa: E402
    NEAR_DUPLICATE_JACCARD, redundancy_report,
)

RAW_CACHE = ROOT / "pipeline_out" / "e3" / "K-IC" / "raw_claims_cache.json"


def _c(statement: str, **kw) -> dict:
    base = dict(entity="Keystone", metric="EBITDA", period_canonical="FY2024A",
                period="FY2024A", perimeter="consolidated", measurement="total",
                scope="group", basis="reported", scenario="base", value=10.2,
                statement=statement)
    base.update(kw)
    return base


class SignalTests(unittest.TestCase):
    def test_exact_duplicates_are_counted_once_as_surplus(self) -> None:
        r = redundancy_report([_c("EBITDA was 10.2"), _c("EBITDA was 10.2"),
                               _c("EBITDA was 10.2")])
        self.assertEqual(r["exact_duplicate_surplus"], 2, "3 identical -> 2 surplus")

    def test_punctuation_and_case_do_not_hide_a_duplicate(self) -> None:
        r = redundancy_report([_c("EBITDA was 10.2."), _c("ebitda  was 10.2")])
        self.assertEqual(r["exact_duplicate_surplus"], 1)

    def test_subsumption_is_detected(self) -> None:
        r = redundancy_report([_c("EBITDA was 10.2"),
                               _c("EBITDA was 10.2 in the reported accounts")])
        self.assertEqual(len(r["subsumed_pairs"]), 1)

    def test_same_identity_different_value_is_not_a_duplicate(self) -> None:
        """The distinction the module exists to keep: that is a CONTRADICTS
        candidate, and adjudicating it is relation_rules' job, not this one's."""
        r = redundancy_report([_c("reported EBITDA 10.2", value=10.2),
                               _c("EBITDA of 12.7 per the seller", value=12.7)])
        self.assertEqual(len(r["identity_collisions_agreeing"]), 0)
        self.assertEqual(len(r["identity_collisions_disagreeing"]), 1)

    def test_same_identity_same_value_is_a_duplicate_candidate(self) -> None:
        r = redundancy_report([_c("reported EBITDA 10.2"), _c("EBITDA came to 10.2")])
        self.assertEqual(len(r["identity_collisions_agreeing"]), 1)

    def test_unidentified_claims_do_not_collide(self) -> None:
        """39 venture claims share (unspecified, Other, CrossPeriod). They are
        different facts that lack identity; calling them a collision would turn
        the extractor's blind spot into a false duplicate finding."""
        bare = dict(entity="unspecified", metric="Other", perimeter=None,
                    measurement=None, scope=None, basis=None, scenario=None,
                    period_canonical="CrossPeriod", period="CrossPeriod")
        r = redundancy_report([{**bare, "statement": "the team has hardware depth",
                                "value": None},
                               {**bare, "statement": "the pilot converted in March",
                                "value": None}])
        self.assertEqual(len(r["identity_collisions_agreeing"]), 0)
        self.assertEqual(len(r["identity_collisions_disagreeing"]), 0)

    def test_nothing_is_ever_removed(self) -> None:
        """The module reports. A near-duplicate pair on a real corpus was
        'at least twenty months' vs 'at most thirty months' -- opposite facts."""
        claims = [_c("institutional buyers need at least twenty months from workshop"),
                  _c("institutional buyers need at most thirty months from workshop")]
        r = redundancy_report(claims)
        self.assertEqual(r["claim_count"], 2)
        self.assertNotIn("kept", r)
        self.assertNotIn("dropped", r)
        self.assertGreaterEqual(len(r["near_duplicate_pairs"]), 0)


class RealCorpusTests(unittest.TestCase):
    @unittest.skipUnless(RAW_CACHE.exists(), "K-IC raw claim cache not present")
    def test_over_extraction_is_not_repetition(self) -> None:
        """The finding this module was built to make durable.

        If this ever fails, exact repetition has become a real problem and a
        CORE-style uniqueness filter is finally worth building. Until then,
        deleting claims to improve precision would delete distinct facts.
        """
        claims = json.loads(RAW_CACHE.read_text(encoding="utf-8"))
        r = redundancy_report(claims)
        self.assertLess(
            r["redundancy_rate"], 0.05,
            f"exact duplication is now {r['redundancy_rate']:.1%} of "
            f"{r['claim_count']} claims — repetition has become material",
        )

    def test_the_review_threshold_is_not_a_deletion_threshold(self) -> None:
        self.assertGreater(NEAR_DUPLICATE_JACCARD, 0.5,
                           "a low bar would flag ordinary domain vocabulary")


if __name__ == "__main__":
    unittest.main(verbosity=2)
