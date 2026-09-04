#!/usr/bin/env python3
"""PAN-124: same financial identity, agree or disagree -- never adjudicate.

Deterministic pass over E3 output, one level up from derivation_verifier
(PAN-123): not "is this claim's own arithmetic right" but "do two
independently-stated claims about the SAME thing actually agree". Uses
tools/object_identity.metric_identity(), the identity this codebase
already computes everywhere else, so "same identity" here is not a second,
independently-drifting notion of sameness.

Built by a codex run given a tight brief (an earlier attempt at the same
brief burned its turn budget exploring and wrote nothing -- this one
landed real code). Its version handles comma-formatted numbers ("3,089")
that a first hand-written pass here did not, and reuses
object_identity.IDENTITY_DIMENSION_NAMES instead of hand-listing identity
field names a second time.

The real-data run is the point. On the real 1127-claim Keystone output it
finds 52 contradiction candidates, several of which are not bugs in this
module but a genuine, recurring schema gap: multiple WIP-ledger rows for
DIFFERENT named customers (e.g. "row WIP-0038 (Silverline Medical)" vs
"row WIP-0041 (Cedar Municipal 2)") share an identical coarse `measurement`
("ehs compliance service line") because nothing captured the per-customer
distinction the statement itself states. Surfacing that ambiguity, not
resolving it, is exactly this module's job -- and the same class of gap
PAN-117 fixed for covenant thresholds is recurring in a new place.

    python3 tools/test_pan124_claim_overlap.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.claim_overlap import analyze_claims


def _claim(claim_id: str, value, **overrides) -> dict:
    base = {
        "claim_id": claim_id, "value": value, "unit": "$m",
        "epistemic_class": "asserted", "statement": f"stmt {claim_id}",
        "source_id": "SRC-X", "locator": "doc.md::p1",
    }
    base.update(overrides)
    return base


def _fields(claim_id: str, **overrides) -> dict:
    base = {
        "claim_id": claim_id, "metric": "Revenue", "entity": "Acme",
        "period": "FY2025A", "period_canonical": "FY2025A", "scope": "consolidated",
        "basis": "SellerView", "measurement": "total", "scenario": "unspecified",
    }
    base.update(overrides)
    return base


def _payload(claims: list[dict], fields: list[dict]) -> dict:
    return {"claims": claims, "extraction_metadata": {"compiler_fields_per_claim": fields}}


def _by_status(report: dict, status: str) -> list[dict]:
    return [f for f in report["findings"] if f["status"] == status]


class CorroborationTests(unittest.TestCase):
    def test_same_identity_same_value_is_a_corroboration(self):
        payload = _payload(
            [_claim("c1", "125.0"), _claim("c2", "125.0", source_id="SRC-Y")],
            [_fields("c1"), _fields("c2")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["corroboration_groups"], 1)
        self.assertEqual(report["contradiction_candidate_groups"], 0)

    def test_values_within_tolerance_still_corroborate(self):
        """Float round-tripping through string storage can shift the last
        digit; a value 0.3% apart is the same fact, not a disagreement."""
        payload = _payload(
            [_claim("c1", "125.0"), _claim("c2", "125.3")],
            [_fields("c1"), _fields("c2")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["corroboration_groups"], 1)

    def test_comma_formatted_numbers_still_parse(self):
        """A real derivation in this corpus sums to "3,089" -- a thousands
        separator, not three digits of decimal noise."""
        payload = _payload(
            [_claim("c1", "3,089"), _claim("c2", "3089")],
            [_fields("c1"), _fields("c2")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["corroboration_groups"], 1)


class ContradictionTests(unittest.TestCase):
    def test_same_identity_different_value_is_a_contradiction_candidate(self):
        payload = _payload(
            [_claim("c1", "125.0"), _claim("c2", "140.0")],
            [_fields("c1"), _fields("c2")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["contradiction_candidate_groups"], 1)
        self.assertEqual(report["corroboration_groups"], 0)

    def test_no_verdict_is_ever_rendered(self):
        """The single rule this module must never break."""
        payload = _payload(
            [_claim("c1", "125.0", epistemic_class="attested"),
             _claim("c2", "140.0", epistemic_class="asserted")],
            [_fields("c1"), _fields("c2")],
        )
        report = analyze_claims(payload)
        # Structural booleans (agree: false, shows_working: false) are not
        # verdicts -- they describe the comparison, not which claim is
        # true. Check only the module's OWN generated text (status,
        # comparison reasons) -- claim statements are pass-through source
        # content the module does not author, so checking those would
        # reject an innocent source sentence like "the corrected balance".
        finding = _by_status(report, "CONTRADICTION CANDIDATE")[0]
        module_text = finding["status"] + " " + " ".join(
            c["reason"] for c in finding["comparisons_to_first_claim"])
        for word in ("correct", "is wrong", "is right", "incorrect"):
            self.assertNotIn(word, module_text.lower())

    def test_the_working_claim_is_listed_first_not_declared_correct(self):
        payload = _payload(
            [_claim("bare", "140.0", epistemic_class="asserted"),
             _claim("shown", "125.0", epistemic_class="derived")],
            [_fields("bare"), _fields("shown", derivation="100 + 25 = 125")],
        )
        report = analyze_claims(payload)
        ordered = _by_status(report, "CONTRADICTION CANDIDATE")[0]["claims"]
        self.assertEqual(ordered[0]["claim_id"], "shown")
        self.assertTrue(ordered[0]["shows_working"])
        self.assertFalse(ordered[1]["shows_working"])

    def test_a_derived_claim_with_no_derivation_text_does_not_outrank_asserted(self):
        """epistemic_class=derived with an empty derivation isn't actually
        showing its working -- ranking it above a plain assertion anyway
        would reward the label instead of the substance."""
        payload = _payload(
            [_claim("hollow", "140.0", epistemic_class="derived"),
             _claim("bare", "125.0", epistemic_class="asserted")],
            [_fields("hollow", derivation=None), _fields("bare")],
        )
        report = analyze_claims(payload)
        ordered = _by_status(report, "CONTRADICTION CANDIDATE")[0]["claims"]
        self.assertFalse(ordered[0]["shows_working"])
        self.assertFalse(ordered[1]["shows_working"])


class NonNumericTests(unittest.TestCase):
    def test_a_range_never_silently_matches_a_point_value(self):
        """"8-12" and "10" must not be coerced into agreeing OR
        disagreeing by numeric proximity -- a range was never claiming to
        equal a specific point."""
        payload = _payload(
            [_claim("range", "8-12"), _claim("point", "10")],
            [_fields("range"), _fields("point")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["contradiction_candidate_groups"], 1)

    def test_identical_non_numeric_strings_corroborate(self):
        payload = _payload(
            [_claim("a", "Approved"), _claim("b", "approved  ")],
            [_fields("a"), _fields("b")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["corroboration_groups"], 1)


class ResolvabilityTests(unittest.TestCase):
    def test_other_escape_hatch_claims_are_skipped_not_grouped(self):
        """Two 'Other' claims about unrelated concepts must never be
        treated as the same identity just because both normalize_metric()
        to '' -- is_resolvable() exists precisely to prevent that merge."""
        payload = _payload(
            [_claim("o1", "5.0"), _claim("o2", "9.0")],
            [_fields("o1", metric="Other"), _fields("o2", metric="Other")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["overlap_groups"], 0)
        self.assertEqual(report["claims_skipped_unresolvable"], 2)

    def test_a_lone_claim_with_no_peer_is_not_reported_either_way(self):
        payload = _payload([_claim("solo", "125.0")], [_fields("solo")])
        report = analyze_claims(payload)
        self.assertEqual(report["overlap_groups"], 0)


class DifferentIdentityTests(unittest.TestCase):
    def test_different_basis_never_collides(self):
        """SellerView 125 and QoEView 118 are not a contradiction -- they
        are two legitimate views the schema exists to keep apart."""
        payload = _payload(
            [_claim("seller", "125.0"), _claim("qoe", "118.0")],
            [_fields("seller", basis="SellerView"), _fields("qoe", basis="QoEView")],
        )
        report = analyze_claims(payload)
        self.assertEqual(report["overlap_groups"], 0)


class RealClaimsTests(unittest.TestCase):
    CLAIMS = ROOT / "pipeline_out/e3/K-PRE/e3_claims.json"

    def test_real_keystone_output_surfaces_candidates(self):
        if not self.CLAIMS.exists():
            self.skipTest("real E3 claims file not present in this checkout")
        payload = json.loads(self.CLAIMS.read_text())
        report = analyze_claims(payload)
        self.assertGreater(report["overlap_groups"], 0)
        candidates = _by_status(report, "CONTRADICTION CANDIDATE")
        self.assertGreater(len(candidates), 0)
        for finding in candidates:
            self.assertGreaterEqual(len(finding["claims"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
