import copy
import json
import unittest

from runtime import compute_operative_claims


def claim(claim_id, *, epistemic="asserted", known_at="2026-01-01T00:00:00Z", **fields):
    result = {
        "claim_id": claim_id,
        "entity": "Apex",
        "metric": "EBITDA",
        "period": "FY2025",
        "scope": "consolidated",
        "basis": "FirmView",
        "scenario": "base",
        "epistemic": epistemic,
        "known_at": known_at,
    }
    result.update(fields)
    return result


def graph(*claims):
    return {"claims": list(claims)}


class OperativeClaimsTests(unittest.TestCase):
    def test_attested_beats_newer_asserted_claim(self):
        report = compute_operative_claims(graph(
            claim("CL-ATTESTED", epistemic="attested", known_at="2026-01-01T00:00:00Z"),
            claim("CL-ASSERTED", known_at="2026-02-01T00:00:00Z"),
        ))
        group = report["groups"][0]
        self.assertEqual(group["operative_claim_id"], "CL-ATTESTED")
        self.assertEqual(group["rule_applied"], "EPISTEMIC_TIER")

    def test_recency_breaks_same_epistemic_tier(self):
        report = compute_operative_claims(graph(
            claim("CL-OLD", epistemic="observed", known_at="2026-01-01T00:00:00Z"),
            claim("CL-NEW", epistemic="observed", known_at="2026-02-01T00:00:00Z"),
        ))
        group = report["groups"][0]
        self.assertEqual(group["operative_claim_id"], "CL-NEW")
        self.assertEqual(group["rule_applied"], "RECENCY")

    def test_explicit_supersedes_beats_epistemic_tier(self):
        report = compute_operative_claims(graph(
            claim("CL-HIGH", epistemic="attested"),
            claim("CL-EXPLICIT", epistemic="asserted", supersedes="[[CL-HIGH]]"),
        ))
        group = report["groups"][0]
        self.assertEqual(group["operative_claim_id"], "CL-EXPLICIT")
        self.assertEqual(group["rule_applied"], "EXPLICIT_SUPERSEDES")

    def test_equal_tier_and_known_at_is_ambiguous(self):
        report = compute_operative_claims(graph(
            claim("CL-A", epistemic="derived"),
            claim("CL-B", epistemic="derived"),
        ))
        group = report["groups"][0]
        self.assertIsNone(group["operative_claim_id"])
        self.assertEqual(group["rule_applied"], "AMBIGUOUS")

    def test_different_metric_identities_are_not_grouped(self):
        report = compute_operative_claims(graph(
            claim("CL-FY25"),
            claim("CL-FY26", period="FY2026"),
            claim("CL-SELLER", basis="SellerView"),
        ))
        self.assertEqual(len(report["groups"]), 3)
        self.assertEqual({group["rule_applied"] for group in report["groups"]}, {"SOLE_CLAIM"})

    def test_input_graph_is_not_mutated_and_unresolvable_is_not_grouped(self):
        input_graph = graph(
            claim("CL-VALID"),
            {"claim_id": "CL-INCOMPLETE", "metric": "EBITDA", "known_at": "2026-01-01T00:00:00Z"},
        )
        before = json.dumps(input_graph, sort_keys=True)
        report = compute_operative_claims(input_graph)
        self.assertEqual(json.dumps(input_graph, sort_keys=True), before)
        self.assertEqual(report["unresolvable"], ["CL-INCOMPLETE"])
        self.assertEqual(len(report["groups"]), 1)

    def test_as_of_excludes_later_claims_and_changes_result(self):
        input_graph = graph(
            claim("CL-OLD", epistemic="observed", known_at="2026-01-01T00:00:00Z"),
            claim("CL-LATER", epistemic="observed", known_at="2026-02-01T00:00:00Z"),
        )
        historical = compute_operative_claims(input_graph, as_of="2026-01-15T00:00:00Z")
        current = compute_operative_claims(input_graph)
        self.assertEqual(historical["groups"][0]["operative_claim_id"], "CL-OLD")
        self.assertEqual(historical["groups"][0]["rule_applied"], "SOLE_CLAIM")
        self.assertEqual(current["groups"][0]["operative_claim_id"], "CL-LATER")


if __name__ == "__main__":
    unittest.main()
