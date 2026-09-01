import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.dynamics.runtime.panta_transition_engine import (  # noqa: E402
    MUTATION_OBJECT_TYPES,
)
from tools.kernel_object_inventory import audit_inventory, load_inventory  # noqa: E402


class Pan82KernelObjectInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = load_inventory()
        cls.by_type = {
            item["kernel_type"]: item for item in cls.inventory["objects"]
        }

    def test_inventory_has_all_22_kernel_types_and_no_contract_drift(self):
        self.assertEqual(audit_inventory(self.inventory), [])
        self.assertEqual(len(self.by_type), 22)

    def test_runtime_defs_separate_kernel_aliases_from_graph_constructs(self):
        contracts = self.inventory["frozen_contracts"]
        aliases = {
            schema_def
            for values in contracts["kernel_object_aliases"].values()
            for schema_def in values
        }
        graph_defs = set(contracts["non_kernel_graph_defs"])

        self.assertEqual(
            aliases,
            {"claim", "position", "stated_position", "model_node"},
        )
        self.assertEqual(
            graph_defs,
            {"position_edge", "claim_position_edge", "position_model_binding"},
        )
        self.assertEqual(aliases | graph_defs, set(contracts["canonical_case_defs"]))

    def test_only_two_first_class_runtime_gaps_remain_after_pan74(self):
        runtime_gaps = {
            item["kernel_type"]
            for item in self.inventory["objects"]
            if item["classification"] == "RUNTIME_GAP"
        }
        self.assertEqual(runtime_gaps, {"Assumption", "Condition"})
        for object_type in runtime_gaps:
            self.assertTrue(self.by_type[object_type]["follow_up_issue"])

    def test_inventory_does_not_invent_dynamic_mutation_types(self):
        declared = set(
            self.inventory["frozen_contracts"]["dynamic_mutation_object_types"]
        )
        self.assertEqual(declared, set(MUTATION_OBJECT_TYPES))
        for item in self.inventory["objects"]:
            mutation_type = item["dynamic_mutation_type"]
            if mutation_type is not None:
                self.assertIn(mutation_type, MUTATION_OBJECT_TYPES)

    def test_semantic_only_types_never_claim_a_dynamic_mutation(self):
        semantic_only = {
            item["kernel_type"]
            for item in self.inventory["objects"]
            if item["classification"] == "SEMANTIC_ONLY"
        }
        self.assertEqual(
            semantic_only,
            {"Interaction", "Utterance", "Definition", "MetricObservation", "Risk"},
        )
        for object_type in semantic_only:
            self.assertIsNone(self.by_type[object_type]["dynamic_mutation_type"])

    def test_audit_records_pan74_as_additive_without_position_rename(self):
        self.assertEqual(
            self.inventory["status"],
            "ENGINEERING_AUDIT_NON_BINDING",
        )
        boundary = self.inventory["classification_policy"]["freeze_boundary"]
        self.assertIn("PAN-74 adds StatedPosition", boundary)
        self.assertIn("without renaming", boundary)
        self.assertIn("POSITION/CaseReading", boundary)


if __name__ == "__main__":
    unittest.main()
