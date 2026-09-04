import unittest

from runtime.consequence_reasoning import (
    EvidenceState,
    ProofGraph,
    evidence_and,
    evidence_or,
)


class FourValuedEvidenceTests(unittest.TestCase):
    def test_public_adapter_preserves_v20_three_value_contract(self):
        self.assertEqual(EvidenceState.TRUE.public_state, "TRUE")
        self.assertEqual(EvidenceState.FALSE.public_state, "FALSE")
        self.assertEqual(EvidenceState.NEITHER.public_state, "UNKNOWN")
        self.assertEqual(EvidenceState.BOTH.public_state, "UNKNOWN")

    def test_conjunction_and_disjunction_preserve_conflicting_evidence(self):
        self.assertIs(
            evidence_and([EvidenceState.TRUE, EvidenceState.BOTH]),
            EvidenceState.BOTH,
        )
        self.assertIs(
            evidence_or([EvidenceState.BOTH, EvidenceState.TRUE]),
            EvidenceState.TRUE,
        )
        self.assertIs(
            evidence_or([EvidenceState.BOTH]),
            EvidenceState.BOTH,
        )


class ProofGraphTests(unittest.TestCase):
    def test_retains_only_minimal_support_environments(self):
        graph = ProofGraph()
        graph.ensure_fact("A", EvidenceState.TRUE, evidence_token="claim:A")
        graph.ensure_fact("B", EvidenceState.TRUE, evidence_token="claim:B")
        graph.ensure_fact("C", EvidenceState.TRUE, evidence_token="claim:C")
        graph.derive_and("AB", ["A", "B"], rule_id="RULE-AND")
        target = graph.derive_or("TARGET", ["AB", "C"], rule_id="RULE-OR")

        self.assertIs(target.state, EvidenceState.TRUE)
        self.assertEqual(
            target.positive_environments,
            (
                frozenset({"claim:C"}),
                frozenset({"claim:A", "claim:B"}),
            ),
        )
        self.assertEqual(target.negative_environments, ())

    def test_counterevidence_retains_support_and_refutation_separately(self):
        graph = ProofGraph()
        graph.ensure_fact(
            "SUPPORT-FACT", EvidenceState.TRUE, evidence_token="claim:support"
        )
        graph.ensure_fact(
            "COUNTER-FACT", EvidenceState.TRUE, evidence_token="claim:counter"
        )
        graph.derive_and(
            "SUPPORT", ["SUPPORT-FACT"], rule_id="RULE-SUPPORT"
        )
        graph.derive_or(
            "COUNTER", ["COUNTER-FACT"], rule_id="RULE-COUNTER"
        )
        route = graph.derive_with_counterevidence(
            "ROUTE",
            "SUPPORT",
            "COUNTER",
            rule_id="RULE-ROUTE",
        )

        self.assertIs(route.state, EvidenceState.BOTH)
        self.assertEqual(
            route.positive_environments,
            (frozenset({"claim:support"}),),
        )
        self.assertEqual(
            route.negative_environments,
            (frozenset({"claim:counter"}),),
        )

    def test_bounded_labels_do_not_change_exact_truth_state(self):
        graph = ProofGraph(max_environments_per_sign=1)
        graph.ensure_fact("A", EvidenceState.TRUE, evidence_token="claim:A")
        graph.ensure_fact("B", EvidenceState.TRUE, evidence_token="claim:B")
        target = graph.derive_or("TARGET", ["A", "B"], rule_id="RULE-OR")

        self.assertIs(target.state, EvidenceState.TRUE)
        self.assertEqual(len(target.positive_environments), 1)
        self.assertTrue(target.labels_truncated)

    def test_truncation_propagates_through_later_derivations(self):
        graph = ProofGraph(max_environments_per_sign=1)
        graph.ensure_fact("A", EvidenceState.TRUE, evidence_token="claim:A")
        graph.ensure_fact("B", EvidenceState.TRUE, evidence_token="claim:B")
        graph.ensure_fact("C", EvidenceState.TRUE, evidence_token="claim:C")
        graph.derive_or("A-OR-B", ["A", "B"], rule_id="RULE-OR")
        target = graph.derive_and(
            "TARGET", ["A-OR-B", "C"], rule_id="RULE-AND"
        )

        self.assertIs(target.state, EvidenceState.TRUE)
        self.assertEqual(len(target.positive_environments), 1)
        self.assertTrue(target.labels_truncated)


if __name__ == "__main__":
    unittest.main()
