#!/usr/bin/env python3
"""Self-contained acceptance tests for PAN-36's V2 merge contract."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.dynamics.runtime.extraction_adapter import validate_extraction_graph
from tools.adapter_alpha import (
    E3AdapterInputError,
    compile_e3_runtime_bundle,
    e3_to_extraction_graph,
)
from tools.extract_v2 import (
    CLAIM_TOOL,
    Chunk,
    RawClaim,
    SYSTEM_PROMPT,
    UnsupportedSourceError,
    _is_fatal_provider_error,
    _provider_retry_delay,
    _source_record,
    annotate_chunk,
    assemble,
    load_manifest,
    parse_markdown,
    parse_source,
    validate,
)
from tools.extraction_quality import score_e3


FIXTURE = ROOT / "tools" / "fixtures" / "pan36_synthetic_model.xlsx"
EXECUTION = (
    ROOT
    / "pipeline_out"
    / "e3"
    / "K-PRE"
    / "adapter_alpha"
    / "execution_graph_v7.json"
)


def _raw_dso_claim(source: Path, locator: str) -> dict:
    return {
        "metric": "DSO",
        "value": 62,
        "unit": "days",
        "period": "FY2026E",
        "perimeter": "Synthetic standalone base scenario",
        "epistemic_class": "attested",
        "direction": "supports",
        "topic": "Operational",
        "definition_id": None,
        "statement": "Synthetic standalone base DSO is 62 days in FY2026E.",
        "locator": locator,
        "source_id": "SRC-MODEL",
        "source_path": str(source),
        "known_at": "2026-08-29",
        "derivation": None,
        "author": "Synthetic test fixture",
    }


def _e3_manifest() -> dict:
    claim = {
        "claim_id": "pan36-dso-fy2025",
        "statement": "Synthetic standalone base DSO is 64 days in FY2025A.",
        "source_id": "SRC-MODEL",
        "locator": "pan36_synthetic_model.xlsx::Inputs!1:4",
        "epistemic_class": "attested",
        "value": "64.0",
        "unit": "days",
        "definition_id": None,
        "period": "FY2025A",
        "perimeter": "Synthetic standalone base scenario",
        "ground_truth_flag": False,
        "validation_only": False,
        "notes": None,
    }
    return {
        "schema_version": "e3-1.0",
        "manifest_id": "PAN36-SYNTHETIC",
        "deal": "keystone",
        "claims": [claim],
        "extraction_metadata": {
            "compiler_fields_per_claim": [
                {
                    "claim_id": claim["claim_id"],
                    "metric": "DSO",
                    "direction": "supports",
                    "topic": "Operational",
                    "derivation": None,
                    "author": "Synthetic test fixture",
                }
            ]
        },
    }


class WorkbookV2ContractTests(unittest.TestCase):
    def test_l2_tool_schema_requires_non_empty_identity_strings(self) -> None:
        claim_schema = CLAIM_TOOL["input_schema"]["properties"]["claims"]["items"]
        self.assertTrue(
            {"period", "perimeter", "locator_hint"}
            <= set(claim_schema["required"])
        )
        for field in ("period", "perimeter", "locator_hint"):
            with self.subTest(field=field):
                field_schema = claim_schema["properties"][field]
                self.assertEqual(field_schema["type"], "string")
                self.assertEqual(field_schema["minLength"], 1)
                self.assertRegex("x", field_schema["pattern"])
                self.assertNotRegex("   ", field_schema["pattern"])

    def test_l2_blank_identity_uses_only_safe_source_and_chunk_metadata(self) -> None:
        class ToolUseBlock:
            type = "tool_use"
            name = "emit_claims"
            input = {
                "claims": [
                    {
                        "metric": "Revenue",
                        "value": 100,
                        "unit": "$m",
                        "period": "   ",
                        "perimeter": "   ",
                        "epistemic_class": "asserted",
                        "direction": "supports",
                        "topic": "Financial Performance",
                        "statement": "Revenue was $100m.",
                        "locator_hint": "   ",
                    }
                ]
            }

        class Messages:
            def create(self, **_request):
                return type("Response", (), {"content": [ToolUseBlock()]})()

        client = type("Client", (), {"messages": Messages()})()
        chunk = Chunk(
            chunk_id="ch-safe-metadata-fallback",
            locator="keystone_seller_cim.md::## Revenue",
            body="Revenue was $100m.",
            source_path="keystone_seller_cim.md",
            source_type="md",
            source_record=_source_record(Path("keystone_seller_cim.md")),
            word_count=3,
            section_heading="## Revenue",
        )

        claims = annotate_chunk(chunk, client, "keystone", rate_limit_delay=0)

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].period, "as of 2025-10-27")
        self.assertEqual(claims[0].perimeter, "unknown")
        self.assertEqual(claims[0].locator, "keystone_seller_cim.md::## Revenue")

    def test_legacy_cache_null_identity_fields_remain_readable(self) -> None:
        raw = RawClaim(
            metric="Revenue",
            value=100,
            unit="$m",
            period=None,
            perimeter=None,
            epistemic_class="asserted",
            direction="supports",
            topic="Financial Performance",
            definition_id=None,
            statement="Historical cached revenue claim.",
            locator="legacy.md::line 1",
            source_id="SRC-LEGACY",
            source_path="legacy.md",
            known_at="",
        )

        canonical = validate(raw)
        graph = assemble([canonical])

        self.assertEqual(canonical.period, "")
        self.assertEqual(canonical.period_iso, "unknown")
        self.assertEqual(canonical.perimeter, "unknown")
        self.assertEqual(graph.admitted_count, 1)
        self.assertEqual(graph.rejected_count, 0)

    def test_derived_without_non_whitespace_derivation_is_rejected(self) -> None:
        raw = RawClaim(
            metric="Revenue Growth",
            value=10,
            unit="%",
            period="FY2026E",
            perimeter="Synthetic standalone base scenario",
            epistemic_class="derived",
            direction="supports",
            topic="Financial Performance",
            definition_id=None,
            statement="Revenue growth is 10%.",
            locator="synthetic.xlsx::Inputs!C3",
            source_id="SRC-MODEL",
            source_path="synthetic.xlsx",
            known_at="2026-08-29",
            derivation="   ",
        )

        canonical = validate(raw)
        graph = assemble([canonical])

        self.assertIn("derived claim missing derivation field", canonical.validation_errors)
        self.assertEqual(graph.admitted_count, 0)
        self.assertEqual(graph.rejected_count, 1)

    def test_transient_provider_errors_honor_retry_after(self) -> None:
        error = RuntimeError("retry_after_seconds: 5")
        error.status_code = 429
        self.assertEqual(_provider_retry_delay(error, 0), 5.0)
        self.assertIsNone(_provider_retry_delay(RuntimeError("bad request"), 0))

    def test_fatal_key_and_billing_errors_stop_the_remaining_batch(self) -> None:
        self.assertTrue(_is_fatal_provider_error(RuntimeError("billing_error")))
        self.assertTrue(_is_fatal_provider_error(RuntimeError("Key limit exceeded")))
        self.assertFalse(_is_fatal_provider_error(RuntimeError("temporary timeout")))

    def test_l2_batch_can_escalate_provider_errors_for_checkpointing(self) -> None:
        class FailingMessages:
            def create(self, **_request):
                raise RuntimeError("provider budget exhausted")

        client = type(
            "FailingClient",
            (),
            {"messages": FailingMessages()},
        )()
        chunk = Chunk(
            chunk_id="ch-provider-failure",
            locator="keystone_lbo_model_working.xlsx::Inputs!1:4",
            body="A1=Revenue | B1=100",
            source_path="keystone_lbo_model_working.xlsx",
            source_type="xlsx",
            source_record=_source_record(Path("keystone_lbo_model_working.xlsx")),
            word_count=2,
        )
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            annotate_chunk(
                chunk,
                client,
                "keystone",
                rate_limit_delay=0,
                raise_errors=True,
            )

    def test_real_keystone_workbook_name_resolves_to_canonical_model_source(self) -> None:
        record = _source_record(Path("keystone_lbo_model_working.xlsx"))
        self.assertEqual(record["source_id"], "SRC-MODEL")
        self.assertEqual(record["known_at"], "2026-03-05")
        self.assertEqual(record["manifest"], ["K-PRE", "K-IC", "K-LIVE"])

    def test_l2_prompt_pins_period_perimeter_locator_and_epistemic_rules(self) -> None:
        for section in (
            "PERIOD EXTRACTION — mandatory",
            "PERIMETER INFERENCE — mandatory",
            "LOCATOR HINT",
            "Computed by you → derived",
        ):
            self.assertIn(section, SYSTEM_PROMPT)
        for required_rule in (
            "Meeting notes / call transcript / DDQ → observed",
            "Opening Balance Sheet",
            "Seller View",
            "QoE View",
            "Firm View",
            "Statutory",
            "timestamp 00:14:22",
        ):
            self.assertIn(required_rule, SYSTEM_PROMPT)

    def test_l1_markdown_chunks_expose_section_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "keystone_seller_cim.md"
            source.write_text("## Revenue Analysis\nRevenue was 100 in FY2024.", encoding="utf-8")
            chunks = parse_markdown(source, max_words=80)
        self.assertEqual(chunks[0].section_heading, "## Revenue Analysis")
        self.assertIsNone(chunks[0].page_or_slide_number)

    def test_manifest_can_read_external_sensitive_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp)
            expected = source_dir / "keystone_seller_cim.md"
            expected.write_text("## Revenue\nRevenue was 100.", encoding="utf-8")
            paths = load_manifest("K-IC", "keystone", source_dir)
        self.assertEqual(paths, [expected])

    def test_versioned_xlsx_fixture_has_cell_locators_and_formulas(self) -> None:
        chunks = parse_source(FIXTURE, max_words=80)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.locator.startswith(FIXTURE.name + "::") for chunk in chunks))
        self.assertTrue(any("Inputs!1:5" in chunk.locator for chunk in chunks))
        self.assertTrue(any("FORMULA(=Inputs!C2)" in chunk.body for chunk in chunks))
        self.assertTrue(all(chunk.section_heading for chunk in chunks))

    def test_xlsm_uses_the_same_read_only_open_xml_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xlsm = Path(tmp) / "pan36_synthetic_model.xlsm"
            shutil.copyfile(FIXTURE, xlsm)
            chunks = parse_source(xlsm, max_words=80)
        self.assertTrue(chunks)
        self.assertTrue(any("pan36_synthetic_model.xlsm::Inputs!1:5" in c.locator for c in chunks))
        self.assertTrue(any("FORMULA(=Inputs!C2)" in c.body for c in chunks))

    def test_legacy_xls_has_a_conversion_error(self) -> None:
        with self.assertRaisesRegex(UnsupportedSourceError, r"convert.*\.xlsx"):
            parse_source(Path("legacy_model.xls"))

    def test_cached_xlsx_and_xlsm_runs_reach_e3_without_credentials(self) -> None:
        for suffix in (".xlsx", ".xlsm"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                source = tmp_path / f"synthetic{suffix}"
                shutil.copyfile(FIXTURE, source)
                locator = parse_source(source, max_words=80)[0].locator
                output = tmp_path / "out"
                cache_dir = output / "SINGLE"
                cache_dir.mkdir(parents=True)
                (cache_dir / "raw_claims_cache.json").write_text(
                    json.dumps([_raw_dso_claim(source, locator)]),
                    encoding="utf-8",
                )
                env = os.environ.copy()
                for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "PEOS_LLM_PROVIDER"):
                    env.pop(key, None)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "tools" / "extract_v2.py"),
                        "--source",
                        str(source),
                        "--deal",
                        "pan36-synthetic",
                        "--output",
                        str(output),
                        "--chunk-words",
                        "80",
                    ],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                e3 = json.loads((cache_dir / "e3_claims.json").read_text())
                self.assertEqual(len(e3["claims"]), 1)
                formula_graphs = json.loads(
                    (cache_dir / "workbook_formula_graphs.json").read_text()
                )
                workbook = formula_graphs["workbooks"][0]
                self.assertGreater(workbook["summary"]["formula_count"], 0)
                self.assertGreater(workbook["summary"]["precedent_edge_count"], 0)
                formula = next(
                    cell for cell in workbook["graph"]["cells"].values()
                    if cell["kind"] == "formula"
                )
                self.assertTrue(formula["value"].startswith("="))
                self.assertTrue(formula["precedents"])
                self.assertEqual(formula["evaluation_status"], "CALCULATED_ACYCLIC")
                self.assertIsNotNone(formula["evaluated_value"])
                self.assertEqual(
                    workbook["summary"]["evaluated_formula_count"],
                    workbook["summary"]["formula_count"],
                )
                self.assertIn("workbook_formula_graphs", e3["extraction_metadata"])
                self.assertEqual(
                    e3["extraction_metadata"]["workbook_formula_graphs"][0]["artifact"],
                    "workbook_formula_graphs.json",
                )
                claim = e3["claims"][0]
                self.assertEqual(claim["period"], "FY2026E")
                self.assertEqual(claim["perimeter"], "Synthetic standalone base scenario")
                self.assertEqual(claim["epistemic_class"], "attested")
                self.assertIn(f"synthetic{suffix}::Inputs!", claim["locator"])

    def test_completed_chunk_cache_records_model_provenance_in_e3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "keystone_lbo_model_working.xlsx"
            shutil.copyfile(FIXTURE, source)
            chunks = parse_source(source, max_words=80)
            output = tmp_path / "out"
            cache_dir = output / "SINGLE"
            cache_dir.mkdir(parents=True)
            (cache_dir / "raw_claims_cache.json").write_text(
                json.dumps([_raw_dso_claim(source, chunks[0].locator)]),
                encoding="utf-8",
            )
            (cache_dir / "l2_chunk_status.json").write_text(
                json.dumps(
                    {
                        "total_chunks": len(chunks),
                        "completed_chunk_ids": [chunk.chunk_id for chunk in chunks],
                        "completed_chunk_models": {
                            chunk.chunk_id: "test/provider" for chunk in chunks
                        },
                        "models_used": ["test/provider"],
                        "failed_chunks": [],
                        "complete": True,
                    }
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
                env.pop(key, None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "extract_v2.py"),
                    "--source",
                    str(source),
                    "--deal",
                    "keystone",
                    "--output",
                    str(output),
                    "--chunk-words",
                    "80",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            e3 = json.loads((cache_dir / "e3_claims.json").read_text())
            metadata = e3["extraction_metadata"]
            self.assertTrue(metadata["l2_complete"])
            self.assertEqual(metadata["llm_models"], ["test/provider"])


class E3RuntimeAdapterContractTests(unittest.TestCase):
    def test_public_adapter_preserves_identity_fields_and_validates_graph(self) -> None:
        e3 = _e3_manifest()
        graph = e3_to_extraction_graph(e3)
        validate_extraction_graph(graph)
        claim = graph["nodes"][0]
        self.assertEqual(claim["stable_id"], "pan36-dso-fy2025")
        self.assertEqual(claim["metric"], "DSO")
        self.assertEqual(claim["period"], "FY2025A")
        self.assertEqual(claim["perimeter"], "Synthetic standalone base scenario")
        self.assertEqual(claim["epistemic"], "attested")
        self.assertEqual(claim["locator"], "pan36_synthetic_model.xlsx::Inputs!1:4")
        self.assertRegex(graph["graph"]["e3_claims_sha256"], r"^[0-9a-f]{64}$")
        quality = score_e3(e3)
        self.assertEqual(quality["rates"]["complete_identity"], 1.0)
        self.assertEqual(quality["rates"]["excel_locator"], 1.0)

    def test_invalid_or_ambiguous_e3_fails_before_runtime_compilation(self) -> None:
        duplicate = _e3_manifest()
        duplicate["claims"].append(copy.deepcopy(duplicate["claims"][0]))
        with self.assertRaisesRegex(E3AdapterInputError, "duplicate E3 claim_id"):
            e3_to_extraction_graph(duplicate)

        missing_locator = _e3_manifest()
        del missing_locator["claims"][0]["locator"]
        with self.assertRaisesRegex(E3AdapterInputError, "missing required fields: locator"):
            e3_to_extraction_graph(missing_locator)

    def test_runtime_bundle_is_compiled_through_the_same_public_contract(self) -> None:
        artifacts = compile_e3_runtime_bundle(
            _e3_manifest(),
            EXECUTION,
            status="TEST",
            deal="keystone",
        )
        self.assertEqual(len(artifacts.extraction_graph["nodes"]), 1)
        self.assertEqual(artifacts.bundle["manifest"]["admitted_claim_count"], 1)
        self.assertEqual(len(artifacts.bundle["current_graph"]["claims"]), 1)
        source = (ROOT / "app" / "v20_router.py").read_text(encoding="utf-8")
        self.assertIn("compile_e3_runtime_bundle", source)
        self.assertNotIn("from tools.adapter_alpha import _e3_to_extraction_graph", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
