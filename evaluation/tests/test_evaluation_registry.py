from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation.registry import BenchmarkRegistry, DatasetManager


class EvaluationRegistryTests(unittest.TestCase):
    def test_registry_is_valid_and_covers_all_families(self) -> None:
        registry = BenchmarkRegistry.load()
        ids = {entry.dataset_id for entry in registry.entries()}
        self.assertTrue({
            "panta_smoke", "office_comprehension_bench", "omnidocbench", "docile",
            "docvqa", "slidevqa", "spreadsheetbench", "apache_tika_fixtures",
            "spreadsheetbench2", "qaconv", "emailsum",
        }.issubset(ids))

    def test_dataset_lock_is_deterministic_and_marks_bundled_data(self) -> None:
        registry = BenchmarkRegistry.load()
        with tempfile.TemporaryDirectory() as directory:
            manager = DatasetManager(registry, Path(directory))
            first = manager.write_lock(Path(directory) / "one.json")
            second = manager.write_lock(Path(directory) / "two.json")
        self.assertEqual(first, second)
        smoke = next(item for item in first["datasets"] if item["id"] == "panta_smoke")
        self.assertTrue(smoke["available"])


if __name__ == "__main__":
    unittest.main()
