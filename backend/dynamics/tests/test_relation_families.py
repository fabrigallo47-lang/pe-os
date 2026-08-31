import unittest
from pathlib import Path

from runtime.panta_transition_engine import (
    RELATION_VOCABULARY,
    _build_execution_adjacency,
    compute_affected_set,
    is_runtime_relation,
)


def graph_with_challenge() -> dict:
    return {
        "schema_version": "1.1.0",
        "case_id": "PAN-83",
        "canonical_as_of": "2026-01-01",
        "claims": [],
        "case_positions": [
            {"position_id": "P-SOURCE", "name": "Source"},
            {"position_id": "P-TARGET", "name": "Target"},
        ],
        "model_nodes": [],
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [
            {
                "edge_id": "PDE-CHALLENGES",
                "from_position_id": "P-SOURCE",
                "to_position_id": "P-TARGET",
                "relation_type": "CHALLENGES",
            }
        ],
        "position_model_bindings": [],
        "decision_snapshot": {},
    }


class RelationFamiliesTests(unittest.TestCase):
    def test_every_relation_declares_a_kernel_family(self):
        self.assertTrue(all(definition.get("family") for definition in RELATION_VOCABULARY.values()))
        self.assertEqual(
            {definition["family"] for definition in RELATION_VOCABULARY.values()},
            {
                "provenance_and_attribution",
                "semantic_binding_non_traversal",
                "runtime_relations",
                # The kernel declares four. The PAN-83 ticket named three, and
                # scoping to the ticket left ASSIGNED_TO, PRODUCES, REQUIRED_FOR
                # and SUPERSEDES_EXPLICITLY undeclared — where an unknown relation
                # is indistinguishable from a typo.
                "operational_relations",
            },
        )

    def test_frozen_runtime_relations_remain_traversable(self):
        for relation in ("SUPPORTS", "CONTRADICTS", "DERIVES_FROM"):
            self.assertEqual(RELATION_VOCABULARY[relation]["family"], "runtime_relations")
            self.assertTrue(is_runtime_relation(relation))

    def test_challenges_is_semantic_and_not_traversable(self):
        challenges = RELATION_VOCABULARY["CHALLENGES"]
        self.assertEqual(challenges["relation_class"], "SEMANTIC")
        self.assertEqual(challenges["runtime_mapping_status"], "PENDING_ADAPTER")
        self.assertFalse(is_runtime_relation("CHALLENGES"))

    def test_challenges_dependency_is_visible_coverage_limit(self):
        coverage_limits: list[dict] = []
        adjacency = _build_execution_adjacency(graph_with_challenge(), {}, coverage_limits)

        self.assertNotIn("P-SOURCE", adjacency)
        self.assertEqual(coverage_limits[0]["relation"], "CHALLENGES")
        self.assertEqual(coverage_limits[0]["reason_code"], "PENDING_ADAPTER")

        impact = compute_affected_set(graph_with_challenge(), ["P-SOURCE"])
        self.assertEqual(impact["visited_ids"], ["P-SOURCE"])
        self.assertEqual(impact["coverage_limits"], coverage_limits)




class KernelFamilyCompletenessTests(unittest.TestCase):
    """The vocabulary must cover every family the kernel declares, not a subset.

    The PAN-83 spec named three families; the kernel declares four. Scoping to
    the spec left operational_relations out, so ASSIGNED_TO and its siblings were
    simply unknown — and an unknown relation is indistinguishable from a typo.
    """

    KERNEL = (
        Path(__file__).resolve().parents[3]
        / "vault/policy/archetypes/semantic_handoff_v0_2"
        / "01_universal_investment_kernel_v0_2.yaml"
    )

    def setUp(self):
        import yaml
        self.families = yaml.safe_load(self.KERNEL.read_text(encoding="utf-8"))["relation_families"]

    def test_every_kernel_relation_is_declared(self):
        from runtime.panta_transition_engine import RELATION_VOCABULARY
        for family, relations in self.families.items():
            if not isinstance(relations, list):
                continue                      # the trailing `rule:` prose entry
            for relation in relations:
                self.assertIn(relation, RELATION_VOCABULARY,
                              f"{relation} ({family}) is in the kernel but not the vocabulary")

    def test_only_runtime_family_traverses(self):
        from runtime.panta_transition_engine import is_runtime_relation
        for family, relations in self.families.items():
            if not isinstance(relations, list):
                continue
            expected = family == "runtime_relations"
            for relation in relations:
                self.assertEqual(is_runtime_relation(relation), expected,
                                 f"{relation} is in {family}; traversable should be {expected}")

    def test_operational_relations_never_affect_case_state(self):
        # A task being assigned to someone must not propagate into computed
        # economics. Asserted separately because it is the failure that would
        # look harmless in a diff.
        from runtime.panta_transition_engine import is_runtime_relation
        for relation in ("ASSIGNED_TO", "PRODUCES", "REQUIRED_FOR", "SUPERSEDES_EXPLICITLY"):
            self.assertFalse(is_runtime_relation(relation))


if __name__ == "__main__":
    unittest.main()
