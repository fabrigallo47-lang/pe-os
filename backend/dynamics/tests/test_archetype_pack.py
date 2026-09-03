import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tools import archetype_pack  # noqa: E402
from tools.extract_v2_physical import TOPIC_ENUM  # noqa: E402


class ArchetypePackTests(unittest.TestCase):
    def setUp(self):
        archetype_pack.load_pack.cache_clear()

    def tearDown(self):
        archetype_pack.load_pack.cache_clear()

    def test_buyout_workstreams_are_exactly_nine_and_stably_sorted(self):
        pack = archetype_pack.load_pack()
        ids = archetype_pack.workstream_ids(pack)

        self.assertEqual(ids, [
            "COMMERCIAL_AND_MARKET",
            "FINANCIAL_QOE",
            "FINANCING_AND_LIQUIDITY",
            "LEGAL_REGULATORY",
            "MANAGEMENT_SPONSOR_AND_GOVERNANCE",
            "MODEL_VALUATION_AND_RETURNS",
            "OPERATIONS_TECHNOLOGY_AND_EXECUTION",
            "TAX_AND_STRUCTURING",
            "VALUE_CREATION_AND_OWNERSHIP_READINESS",
        ])

    def test_extractor_topics_are_workstreams_plus_other(self):
        self.assertEqual(TOPIC_ENUM, archetype_pack.workstream_ids(archetype_pack.load_pack()) + ["OTHER"])

    def test_every_workstream_has_a_governing_question(self):
        pack = archetype_pack.load_pack()
        for workstream_id in archetype_pack.workstream_ids(pack):
            self.assertTrue(pack["workstreams"][workstream_id]["governing_question"])

    def test_question_family_ids_are_unique_pack_wide(self):
        pack = archetype_pack.load_pack()
        family_ids = [
            family["id"]
            for workstream_id in archetype_pack.workstream_ids(pack)
            for family in archetype_pack.question_families(pack, workstream_id)
        ]

        self.assertEqual(len(family_ids), len(set(family_ids)))

    def test_question_families_project_to_a_stable_governed_spine(self):
        spine = archetype_pack.canonical_question_spine(archetype_pack.load_pack())

        self.assertEqual(len(spine), 54)
        self.assertEqual(spine[0]["id"], "BF-COM-01")
        self.assertEqual(spine[0]["question_family_id"], "BF-COM-01")
        self.assertEqual(spine[0]["archetype_id"], "buyout")
        self.assertEqual(spine[0]["archetype_pack_version"], "0.2.0")
        self.assertTrue(spine[0]["governing_question"])
        self.assertEqual(len({item["id"] for item in spine}), len(spine))

    def test_missing_pack_names_the_expected_path(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing-pack.yaml"
            with patch.object(archetype_pack, "PACK_PATHS", {"buyout": missing_path}):
                with self.assertRaises(FileNotFoundError) as raised:
                    archetype_pack.load_pack()

        self.assertIn(str(missing_path), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
