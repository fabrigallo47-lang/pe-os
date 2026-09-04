#!/usr/bin/env python3
"""PAN-118: which module computes a deal must come from its profile.

`bridge_v7._normalize_execution_mapping` hardcoded
`"lbo_runtime_module": "tools/keystone_model.py"` as a string literal, so
every deal's execution mapping pointed at Keystone's workbook
transcription -- a 1198-line hand-mapping of
keystone_lbo_model_working.xlsx, by its own docstring "Keystone-specific".

For any other deal that is not a missing model, it is the WRONG model:
Silexara is a venture case with no LBO workbook at all, and would have been
handed Keystone's debt schedule and cash sweep. It also contradicts
CLAUDE.md: institutional semantics are per-deal in deal_profile.json,
"never hardcoded in tools/".

The literal is kept as the fallback on purpose. Keystone's profile does not
name a module, so it must keep resolving to exactly what it resolved to
before -- this is a bypass, not a removal.

    python3 tools/test_pan118_runtime_module_from_profile.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import bridge_v7
from tools.deal_profile import DealProfile, load_profile


class ProfileFieldTests(unittest.TestCase):
    def test_absent_means_absent_not_guessed(self):
        """The profile reports nothing rather than inventing a module."""
        profile = DealProfile("silexara", {})
        self.assertEqual(profile.runtime_module, "")
        self.assertEqual(profile.runtime_entrypoint, "")

    def test_profile_carries_a_declared_module(self):
        profile = DealProfile("silexara", {
            "runtime_module": "tools/silexara_model.py",
            "runtime_entrypoint": "propagate_claim",
        })
        self.assertEqual(profile.runtime_module, "tools/silexara_model.py")

    def test_keystone_profile_on_disk_names_no_module(self):
        """Why the fallback must stay: the real profile relies on it."""
        self.assertEqual(load_profile("keystone").runtime_module, "")


class MappingRoutingTests(unittest.TestCase):
    """The mapping is what the dynamics runtime is handed, so this is the
    field that decides which Python actually runs for a deal."""

    def _mapping_for(self, profile: DealProfile) -> dict:
        original = bridge_v7._profile
        bridge_v7._profile = lambda: profile
        try:
            return bridge_v7._normalize_execution_mapping(
                execution={"model_nodes": {}, "formulas": []},
                case_positions={},
                pm_directions=[],
                canonical_current_hash="deadbeef",
            )
        finally:
            bridge_v7._profile = original

    def test_a_deal_with_its_own_model_is_routed_to_it(self):
        mapping = self._mapping_for(DealProfile("silexara", {
            "runtime_module": "tools/silexara_model.py",
            "runtime_entrypoint": "compute_case",
        }))
        self.assertEqual(mapping["lbo_runtime_module"], "tools/silexara_model.py")
        self.assertEqual(mapping["lbo_runtime_entrypoint"], "compute_case")

    def test_a_deal_without_one_still_gets_the_previous_default(self):
        """The bypass must not change any deal that did not ask for it."""
        mapping = self._mapping_for(DealProfile("keystone", {}))
        self.assertEqual(mapping["lbo_runtime_module"], "tools/keystone_model.py")
        self.assertEqual(mapping["lbo_runtime_entrypoint"], "propagate_claim")


if __name__ == "__main__":
    unittest.main(verbosity=2)
