import asyncio
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import BackgroundTasks


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import app.v20_router as router  # noqa: E402
from tools.excel_formula_graph import compile_workbook  # noqa: E402
from tools.extract_v2 import UnsupportedSourceError, parse_source  # noqa: E402
from tools.source_graph import capture  # noqa: E402


FIXTURE = ROOT / "tools" / "fixtures" / "pan51_formula_model.xlsx"
EXPECTATIONS = ROOT / "tools" / "fixtures" / "pan51_formula_expectations.json"
CACHED_FIXTURE = ROOT / "tools" / "fixtures" / "pan36_synthetic_model.xlsx"


class PAN51FormulaCaptureTests(unittest.TestCase):
    def test_fixture_preserves_expected_formulas_and_dependencies(self):
        expected = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
        source = capture(FIXTURE)
        formulas = {
            locator: cell
            for locator, cell in source.cells.items()
            if cell.kind == "formula"
        }
        self.assertEqual(len(formulas), expected["formula_count"])
        for locator, contract in expected["formulas"].items():
            with self.subTest(locator=locator):
                cell = formulas[locator]
                self.assertEqual(cell.value, contract["formula_text"])
                self.assertEqual(cell.precedents, contract["precedents"])
                self.assertEqual(cell.formula_status, contract["formula_status"])
                for field in (
                    "named_references",
                    "external_references",
                    "unsupported_functions",
                ):
                    if field in contract:
                        self.assertEqual(getattr(cell, field), contract[field])

    def test_missing_cache_is_evaluated_only_when_supported_and_never_invented(self):
        graph = compile_workbook(FIXTURE)
        expected = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
        formula_nodes = {
            node["locator"]: node
            for node in graph["nodes"]
            if node.get("type") == "model_node" and node.get("cell_kind") == "formula"
        }
        self.assertEqual(len(formula_nodes), 8)
        for locator, value in expected["expected_evaluated_values"].items():
            with self.subTest(locator=locator):
                node = formula_nodes[locator]
                self.assertAlmostEqual(node["value"], value)
                self.assertIsNone(node["cached_value"])
                self.assertEqual(node["value_origin"], "DETERMINISTIC_FORMULA_EVALUATION")
                self.assertEqual(node["evaluation_status"], "EVALUATED")
                self.assertFalse(node["unknown"])
                self.assertIsNone(node["human_stop_reason"])
        for locator in expected["human_stop_locators"]:
            with self.subTest(locator=locator):
                node = formula_nodes[locator]
                self.assertIsNone(node["value"])
                self.assertIsNone(node["cached_value"])
                self.assertEqual(node["evaluation_status"], "HUMAN_STOP")
                self.assertTrue(node["unknown"])
                self.assertTrue(node["human_stop_reason"])
        self.assertEqual(len(graph["coverage_limits"]), 2)
        self.assertEqual(graph["status"], "HUMAN_STOP")

    def test_displayed_cache_is_separate_from_formula_text(self):
        graph = compile_workbook(CACHED_FIXTURE)
        formula_nodes = [
            node for node in graph["nodes"]
            if node.get("type") == "model_node" and node.get("cell_kind") == "formula"
        ]
        self.assertTrue(formula_nodes)
        self.assertTrue(all(node["formula_text"].startswith("=") for node in formula_nodes))
        self.assertTrue(all(node["cached_value"] is not None for node in formula_nodes))
        self.assertTrue(all(node["value_origin"] == "DETERMINISTIC_FORMULA_EVALUATION" for node in formula_nodes))
        self.assertTrue(all(node["evaluation_status"] == "EVALUATED" for node in formula_nodes))
        for node in formula_nodes:
            self.assertAlmostEqual(float(node["value"]), float(node["cached_value"]))

    def test_formula_graph_has_directed_cross_sheet_range_name_and_external_edges(self):
        graph = compile_workbook(FIXTURE)
        relations = {edge["rel"] for edge in graph["edges"]}
        self.assertIn("DIRECTED_MODEL_DEPENDENCY", relations)
        self.assertIn("RANGE_MEMBER", relations)
        self.assertIn("NAMED_MODEL_DEPENDENCY", relations)
        self.assertIn("EXTERNAL_MODEL_DEPENDENCY", relations)
        formulas = {item["locator"]: item for item in graph["formulas"]}
        self.assertEqual(formulas["OUTPUTS!B8"]["formula_status"], "UNSUPPORTED_FUNCTION")
        self.assertEqual(formulas["OUTPUTS!B7"]["formula_status"], "EXTERNAL_LINK")
        self.assertGreaterEqual(len(formulas["OUTPUTS!B5"]["input_model_node_ids"]), 2)

    def test_open_xml_routes_are_equivalent_and_legacy_xls_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            xlsm = Path(tmp) / "formula-model.xlsm"
            shutil.copyfile(FIXTURE, xlsm)
            xlsx_chunks = parse_source(FIXTURE, max_words=100)
            xlsm_chunks = parse_source(xlsm, max_words=100)
        self.assertEqual(len(xlsx_chunks), len(xlsm_chunks))
        self.assertTrue(any("FORMULA(=IF(" in chunk.body for chunk in xlsm_chunks))
        with self.assertRaisesRegex(UnsupportedSourceError, r"convert.*\.xlsx"):
            parse_source(Path("legacy.xls"))

    def test_documented_smoke_command_writes_expected_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "formula-graph.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "excel_formula_graph.py"),
                    "--workbook",
                    str(FIXTURE),
                    "--out",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("8 formulas, 14 dependencies, 2 Human Stops", result.stdout)
        self.assertEqual(payload["schema_version"], "excel-formula-graph/1.0")


class PAN51V20AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_pipeline = router.PIPELINE_OUT
        self.previous_vault = router.VAULT
        self.previous_jobs_log = router.INGEST_JOBS_LOG
        self.previous_jobs = dict(router._jobs)
        router.PIPELINE_OUT = self.root / "pipeline"
        router.VAULT = self.root / "vault"
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router._jobs.clear()
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

    def tearDown(self):
        self.index_patch.stop()
        router.PIPELINE_OUT = self.previous_pipeline
        router.VAULT = self.previous_vault
        router.INGEST_JOBS_LOG = self.previous_jobs_log
        router._jobs.clear()
        router._jobs.update(self.previous_jobs)
        self.temporary.cleanup()

    def test_formula_nodes_reach_preview_and_remain_linked_after_admission(self):
        model_graph = compile_workbook(FIXTURE)
        background = BackgroundTasks()

        def extractor(command, **_kwargs):
            output = Path(command[command.index("--output") + 1]) / "SINGLE"
            output.mkdir(parents=True, exist_ok=True)
            (output / "e3_claims.json").write_text(
                json.dumps({"deal": "keystone", "claims": []}),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="formula fixture", stderr="")

        request = router._InlineJSONRequest({
            "file_name": FIXTURE.name,
            "purpose": "PAN-51 formula graph admission",
            "content_b64": base64.b64encode(FIXTURE.read_bytes()).decode("ascii"),
        })
        with patch.object(router.subprocess, "run", side_effect=extractor):
            queued = asyncio.run(router.ingest("keystone", request, background))
            for task in background.tasks:
                asyncio.run(task())
        job_id = queued["job_id"]
        proposal_payload = router.get_evidence_proposal("keystone", job_id)["proposal"]
        self.assertEqual(
            proposal_payload["excel_formula_graph"]["source"]["digest"],
            model_graph["source"]["digest"],
        )

        preview = router.get_evidence_proposal("keystone", job_id)
        self.assertEqual(preview["semantic_preview"]["formula_nodes"], 8)
        self.assertFalse(preview["semantic_preview"]["current_mutated"])
        self.assertFalse(router._excel_model_graphs_path("keystone").exists())

        admitted = asyncio.run(router.admit_evidence(
            "keystone",
            job_id,
            {"decision": "ADMIT", "actor_id": "reviewer-pan51"},
        ))
        self.assertEqual(admitted["semantic_graph"]["formula_nodes"], 8)
        semantic = json.loads(
            (router.PIPELINE_OUT / "semantic_current_graph.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(semantic["excel_formulas"]), 8)
        self.assertTrue(any(
            edge.get("rel") == "DIRECTED_MODEL_DEPENDENCY"
            for edge in semantic["edges"]
        ))
        self.assertEqual(
            semantic["excel_model_sources"][0]["admission"]["reviewed_by"],
            "reviewer-pan51",
        )
        projection = router.projection("keystone")["projection"]
        live_graph = projection["deal"]["semantic_current_graph"]
        self.assertEqual(len(live_graph["excel_formulas"]), 8)
        output_id = next(
            item["output_model_node_id"]
            for item in live_graph["excel_formulas"]
            if item["locator"] == "OUTPUTS!B9"
        )
        self.assertTrue(any(
            edge.get("target") == output_id
            and edge.get("rel") == "DIRECTED_MODEL_DEPENDENCY"
            for edge in live_graph["edges"]
        ))

        traced = router._semantic_graph_from_claims([{
            "claim_id": "formula-grounded-claim",
            "statement": "Revenue is produced by the workbook formula.",
            "subject": "Synthetic company revenue",
            "metric": "Revenue",
            "value": None,
            "unit": "$m",
            "period": "FY2026E",
            "perimeter": "Synthetic standalone base",
            "epistemic_class": "derived",
            "epistemic": "derived",
            "locator": f"{FIXTURE.name}::Outputs!2:2",
            "source_id": FIXTURE.name,
            "source_ids": [FIXTURE.name],
        }], "keystone")
        grounded_edge = next(
            edge for edge in traced["edges"]
            if edge.get("source") == "claim:000"
            and edge.get("rel") == "GROUNDED_IN_MODEL"
        )
        revenue_formula = next(
            item for item in traced["excel_formulas"]
            if item["locator"] == "OUTPUTS!B2"
        )
        self.assertEqual(
            grounded_edge["target"],
            revenue_formula["output_model_node_id"],
        )
        self.assertTrue(any(
            edge.get("target") == grounded_edge["target"]
            and edge.get("rel") == "DIRECTED_MODEL_DEPENDENCY"
            for edge in traced["edges"]
        ))

    def test_identical_workbook_bytes_keep_distinct_source_identities(self):
        first = compile_workbook(FIXTURE)
        second = json.loads(json.dumps(first))
        second["source"]["source_id"] = "second-copy.xlsx"
        second["source"]["workbook"] = "second-copy.xlsx"

        router._admit_excel_formula_graph(
            "keystone",
            {"proposal_id": "proposal-first", "excel_formula_graph": first},
            "reviewer-pan51",
        )
        router._admit_excel_formula_graph(
            "keystone",
            {"proposal_id": "proposal-second", "excel_formula_graph": second},
            "reviewer-pan51",
        )

        stored = router._load_excel_model_graphs("keystone")
        self.assertEqual(len(stored), 2)
        self.assertEqual(
            {item["source"]["source_id"] for item in stored},
            {FIXTURE.name, "second-copy.xlsx"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
