from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.model_resolver import (  # noqa: E402
    Concept,
    proposals_from_semantics,
    resolve_model,
)
from tools.ingest_service import ingest_workbook  # noqa: E402


class PAN65ModelResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.concepts = {
            "C-REV": Concept(
                "C-REV", "Revenue", unit="$m", granularity="quarter", form="input"
            ),
            "C-COST": Concept(
                "C-COST", "Costs", unit="$m", granularity="quarter", form="input"
            ),
            "C-EBITDA": Concept(
                "C-EBITDA", "EBITDA", unit="$m", granularity="quarter", form="derived"
            ),
            "C-MARGIN": Concept(
                "C-MARGIN", "Margin", unit="%", granularity="quarter", form="input"
            ),
        }
        self.source = {
            "schema": "source-graph-1",
            "cells": {
                "MODEL!A1": {
                    "kind": "number",
                    "value": 100,
                    "precedents": [],
                },
                "MODEL!B1": {
                    "kind": "number",
                    "value": 40,
                    "precedents": [],
                },
                "MODEL!C1": {
                    "kind": "formula",
                    "value": "=A1-B1",
                    "evaluated_value": 60,
                    "precedents": ["MODEL!A1", "MODEL!B1"],
                },
                "MODEL!D1": {
                    "kind": "number",
                    "value": 0.4,
                    "precedents": [],
                },
                "MODEL!A2": {
                    "kind": "number",
                    "value": 100,
                    "precedents": [],
                },
            },
        }

    @staticmethod
    def _proposal(concept_id: str, locator: str, unit: str = "$m", **extra):
        return {
            "concept_id": concept_id,
            "concept_label": concept_id,
            "locator": locator,
            "period": "2026-06-30",
            "scenario": "Base",
            "unit": unit,
            "confidence": 0.9,
            "evidence": ["MODEL!A0"],
            **extra,
        }

    def test_resolution_is_deterministic_and_every_binding_is_explained(self):
        proposals = [
            self._proposal("C-REV", "MODEL!A1"),
            self._proposal("C-COST", "MODEL!B1"),
            self._proposal("C-EBITDA", "MODEL!C1"),
            # An exact duplicate is one observation, not a second model node.
            self._proposal("C-REV", "MODEL!A1", confidence=0.8),
        ]

        first = resolve_model(proposals, self.source, self.concepts)
        second = resolve_model(list(reversed(proposals)), self.source, self.concepts)

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "RESOLVED")
        self.assertEqual(first["binding_count"], 3)
        self.assertEqual(first["coverage_limits"], [])
        self.assertEqual(
            len({item["model_node_id"] for item in first["bindings"]}),
            3,
        )
        for binding in first["bindings"]:
            self.assertTrue(binding["reason_codes"])
            self.assertTrue(binding["explanation"])
        revenue = next(
            item for item in first["bindings"] if item["concept_id"] == "C-REV"
        )
        self.assertIn("DUPLICATE_PROPOSALS_COLLAPSED", revenue["reason_codes"])

    def test_two_cells_for_one_identity_remain_an_explicit_ambiguity(self):
        result = resolve_model(
            [
                self._proposal("C-REV", "MODEL!A1"),
                self._proposal("C-REV", "MODEL!A2"),
            ],
            self.source,
            self.concepts,
        )

        self.assertEqual(result["binding_count"], 0)
        self.assertTrue(result["halted"])
        self.assertEqual(result["coverage_limit_count"], 1)
        limit = result["coverage_limits"][0]
        self.assertEqual(limit["reason_code"], "AMBIGUOUS_IDENTITY")
        self.assertEqual(
            limit["candidate_locators"], ["MODEL!A1", "MODEL!A2"]
        )
        self.assertEqual(limit["resolution"], "HUMAN_STOP")

    def test_claim_locator_can_disambiguate_without_silent_guessing(self):
        result = resolve_model(
            [
                self._proposal("C-REV", "MODEL!A1"),
                self._proposal("C-REV", "MODEL!A2"),
            ],
            self.source,
            self.concepts,
            claims=[
                {
                    "claim_id": "CLAIM-REV",
                    "concept_id": "C-REV",
                    "locator": "model.xlsx::MODEL!2:1",
                    "period": "2026-06-30",
                    "scenario": "Base",
                    "unit": "$mm",
                    "value": 100,
                }
            ],
        )

        self.assertEqual(result["binding_count"], 1)
        self.assertEqual(result["coverage_limits"], [])
        binding = result["bindings"][0]
        self.assertEqual(binding["locator"], "MODEL!A2")
        self.assertIn("CLAIM_LOCATOR_MATCH", binding["reason_codes"])
        self.assertIn("CLAIM_DISAMBIGUATED_IDENTITY", binding["reason_codes"])

    def test_declared_unit_conflict_is_never_overridden_by_confidence(self):
        result = resolve_model(
            [self._proposal("C-REV", "MODEL!A1", unit="%", confidence=0.999)],
            self.source,
            self.concepts,
        )

        self.assertEqual(result["binding_count"], 0)
        self.assertEqual(
            result["coverage_limits"][0]["reason_code"],
            "DECLARED_UNIT_CONFLICT",
        )

    def test_conflicting_r5_declarations_on_same_cell_are_not_deduplicated(self):
        result = resolve_model(
            [
                self._proposal("C-REV", "MODEL!A1", unit="$m", confidence=0.95),
                self._proposal("C-REV", "MODEL!A1", unit="%", confidence=0.90),
            ],
            self.source,
            concepts=None,
        )

        self.assertEqual(result["binding_count"], 0)
        self.assertEqual(result["coverage_limit_count"], 1)
        self.assertEqual(
            result["coverage_limits"][0]["reason_code"],
            "PROPOSAL_DECLARATION_CONFLICT",
        )

    def test_additive_formula_with_mixed_units_blocks_only_its_output(self):
        mixed_source = json.loads(json.dumps(self.source))
        mixed_source["cells"]["MODEL!C1"]["value"] = "=A1+D1"
        mixed_source["cells"]["MODEL!C1"]["precedents"] = [
            "MODEL!A1",
            "MODEL!D1",
        ]
        result = resolve_model(
            [
                self._proposal("C-REV", "MODEL!A1"),
                self._proposal("C-MARGIN", "MODEL!D1", unit="%"),
                self._proposal("C-EBITDA", "MODEL!C1"),
            ],
            mixed_source,
            self.concepts,
        )

        self.assertEqual(
            {item["concept_id"] for item in result["bindings"]},
            {"C-REV", "C-MARGIN"},
        )
        self.assertIn(
            "FORMULA_UNIT_CONFLICT",
            {item["reason_code"] for item in result["coverage_limits"]},
        )

    def test_claim_value_conflict_becomes_coverage_limit(self):
        result = resolve_model(
            [self._proposal("C-REV", "MODEL!A1")],
            self.source,
            self.concepts,
            claims=[
                {
                    "claim_id": "CLAIM-REV",
                    "concept_id": "C-REV",
                    "period": "2026-06-30",
                    "scenario": "Base",
                    "unit": "$m",
                    "value": 110,
                }
            ],
        )

        self.assertEqual(result["binding_count"], 0)
        self.assertEqual(
            result["coverage_limits"][0]["reason_code"],
            "CLAIM_VALUE_CONFLICT",
        )

    def test_current_r5_sheet_semantics_envelope_maps_through_declared_aliases(self):
        proposals = proposals_from_semantics(
            [
                {
                    "sheet": "MODEL",
                    "proposals": [
                        {
                            "cell": "MODEL!A1",
                            "row_label": "Turnover",
                            "col_header": "2026-06-30",
                            "unit": "$m",
                            "confidence": 0.91,
                            "evidence": ["MODEL!A0"],
                        },
                        {
                            "cell": "MODEL!B1",
                            "row_label": "Unknown metric",
                            "col_header": "2026-06-30",
                            "unit": "$m",
                            "confidence": 0.99,
                        },
                    ],
                }
            ],
            {
                "C-REV": Concept(
                    "C-REV",
                    "Revenue",
                    unit="$m",
                    granularity="quarter",
                    aliases=["Turnover"],
                )
            },
        )

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].concept_id, "C-REV")
        self.assertEqual(proposals[0].locator, "MODEL!A1")
        self.assertEqual(proposals[0].scenario, "MODEL")

    def test_workbook_ingest_exposes_resolver_reasons_and_coverage_contract(self):
        proposal = SimpleNamespace(
            cell="MODEL!A1",
            row_label="Revenue",
            col_header="2026-06-30",
            record_key="",
            unit="$m",
            section="Operating model",
            confidence=0.91,
            evidence=["MODEL!A0"],
        )
        report = SimpleNamespace(
            sheet="MODEL",
            kind="model_sheet",
            proposals=[proposal],
            confident=[proposal],
        )
        graph = SimpleNamespace(
            digest="sha256:pan65",
            stats=lambda: {"cells": 1},
            to_json=lambda: self.source,
        )
        concepts = {
            "concepts": [
                {
                    "concept_id": "C-REV",
                    "label": "Revenue",
                    "unit": "$m",
                    "granularity": "quarter",
                    "form": "input",
                    "aliases": [],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "model.xlsx"
            workbook.write_bytes(b"synthetic")
            concepts_path = root / "concepts.json"
            concepts_path.write_text(json.dumps(concepts), encoding="utf-8")
            with (
                patch("tools.source_graph.capture", return_value=graph),
                patch("tools.sheet_semantics.load_judgments", return_value={}),
                patch("tools.sheet_semantics.analyse_workbook", return_value=[report]),
            ):
                result = ingest_workbook(
                    workbook,
                    concepts_path=concepts_path,
                    compute=False,
                    claims=[
                        {
                            "claim_id": "CLAIM-REV",
                            "concept_id": "C-REV",
                            "locator": "model.xlsx::MODEL!1:1",
                            "period": "2026-06-30",
                            "scenario": "MODEL",
                            "unit": "$m",
                            "value": 100,
                        }
                    ],
                )

        self.assertEqual(result["L3_resolution"]["admitted"], 1)
        self.assertEqual(result["L3_resolution"]["coverage_limits"], [])
        self.assertEqual(result["L3_resolution"]["reachability_status"], "NOT_AVAILABLE")
        binding = result["bindings"][0]
        self.assertTrue(binding["model_node_id"].startswith("MN-C-REV-"))
        self.assertIn("CLAIM_LOCATOR_MATCH", binding["reason_codes"])
        self.assertTrue(binding["explanation"])

    def test_cli_writes_the_versioned_resolution_contract(self):
        proposals = {
            "proposals": [
                self._proposal(
                    "C-REV",
                    "MODEL!A1",
                    concept_label="Revenue",
                    declared_unit="$m",
                    declared_form="input",
                )
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "proposals.json"
            source_path = root / "source.json"
            output_path = root / "resolution.json"
            proposal_path.write_text(json.dumps(proposals), encoding="utf-8")
            source_path.write_text(json.dumps(self.source), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "model_resolver.py"),
                    "--proposals",
                    str(proposal_path),
                    "--source",
                    str(source_path),
                    "--out",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["schema_version"], "model-binding-resolution/1.0")
        self.assertEqual(result["binding_count"], 1)
        self.assertIn("RESOLVED", completed.stdout)


if __name__ == "__main__":
    unittest.main()
