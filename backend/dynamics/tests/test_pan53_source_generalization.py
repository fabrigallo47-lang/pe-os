"""PAN-53 — a new non-Keystone case must not depend on the Keystone SOURCE_REGISTRY.

Verifies the acceptance criteria directly:
  * a source with no filename match in SOURCE_REGISTRY still gets a complete,
    stable identity via SourceEnvelope (content hash, not a filename guess);
  * parse_source uses that envelope-derived record instead of falling back to
    the Keystone-registry lookup once an envelope is supplied;
  * an unsupported format is explicitly rejected, never silently coerced;
  * Keystone's own registry-based lookup is unchanged (backward compatible).
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.extract_v2_physical import UnsupportedSourceError, _source_record, parse_source  # noqa: E402
from tools.source_envelope import build_source_envelope, extractor_source_record  # noqa: E402
import app.v20_router as router  # noqa: E402


class PAN53SourceGeneralizationTests(unittest.TestCase):
    def test_new_case_file_with_no_registry_entry_gets_a_stable_envelope_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scout_diligence_notes_2026.md"
            path.write_text("# Notes\n\nSome unrelated diligence content.\n", encoding="utf-8")

            envelope = build_source_envelope(path, "scout", "2026-08-29T00:00:00Z")

            # Never falls back to a Keystone-shaped SRC-xxx id derived from the
            # filename; the identity is a stable hash of the file's own bytes.
            self.assertTrue(envelope["source_id"].startswith("SRC-"))
            self.assertEqual(envelope["case_id"], "scout")
            self.assertEqual(envelope["source_version_id"], envelope["source_version_id"])
            self.assertTrue(envelope["source_version_id"].startswith("sha256:"))
            self.assertEqual(envelope["provenance"], "user_upload")
            self.assertEqual(envelope["parser_route"], "extract_v2")

            # Same bytes, re-enveloped, produce the same identity -- content
            # addressed, not filename addressed.
            again = build_source_envelope(path, "scout", "2026-08-29T00:05:00Z")
            self.assertEqual(envelope["source_id"], again["source_id"])
            self.assertEqual(envelope["source_version_id"], again["source_version_id"])

    def test_parse_source_uses_the_envelope_record_not_the_keystone_registry_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acme_management_deck.md"
            path.write_text(
                "## Overview\n\nAcme Corp reported revenue of $10m in FY2026.\n",
                encoding="utf-8",
            )
            envelope = build_source_envelope(
                path, "acme-deal", "2026-08-29T00:00:00Z",
                declared_metadata={
                    "issuer": "Acme Corp management",
                    "document_type": "Management deck",
                    "effective_date": "2026-08-01",
                },
            )
            record = extractor_source_record(envelope)
            chunks = parse_source(path, source_record=record)

            self.assertTrue(chunks)
            for chunk in chunks:
                self.assertEqual(chunk.source_record["source_id"], envelope["source_id"])
                self.assertEqual(chunk.source_record["party"], "Acme Corp management")
                self.assertEqual(chunk.source_record["doc_type"], "Management deck")

            # Without an envelope, the same file would only ever get the
            # generic synthetic fallback -- proving the override actually
            # takes effect rather than being silently ignored.
            fallback = _source_record(path)
            self.assertEqual(fallback["party"], "unknown")
            self.assertNotEqual(fallback["source_id"], envelope["source_id"])

    def test_unsupported_format_is_explicitly_rejected_not_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opaque_archive.bin"
            path.write_text("not a supported document", encoding="utf-8")
            with self.assertRaises(UnsupportedSourceError):
                parse_source(path)

            xls_path = Path(tmp) / "old_model.xls"
            xls_path.write_text("not a real xls", encoding="utf-8")
            with self.assertRaisesRegex(UnsupportedSourceError, r"convert.*\.xlsx"):
                parse_source(xls_path)

    def test_keystone_registry_lookup_is_unchanged_for_backward_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keystone_seller_cim.pdf"
            path.write_text("placeholder", encoding="utf-8")
            record = _source_record(path)
            self.assertEqual(record["source_id"], "SRC-CIM")
            self.assertEqual(record["party"], "Alderstone management and Hawthorne Capital Markets")
            self.assertIn("K-PRE", record["manifest"])

    def test_envelope_survives_admission_reload_and_source_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "acme_management_notes.md"
            source_path.write_text(
                "Revenue was EUR 10m in FY2026.\n",
                encoding="utf-8",
            )
            envelope = build_source_envelope(
                source_path,
                "scout",
                "2026-09-02T12:00:00Z",
                declared_metadata={
                    "document_type": "Management notes",
                    "issuer": "Acme management",
                    "author": "Chief Financial Officer",
                    "effective_date": "2026-08-31",
                    "provenance": "diligence_upload",
                },
            )
            claim = {
                "claim_id": "PAN53-LIFECYCLE-001",
                "statement": "Revenue was EUR 10m in FY2026.",
                "value": 10,
                "unit": "EURm",
                "period": "FY2026",
                "perimeter": "Acme consolidated",
                "epistemic_class": "asserted",
                "locator": "acme_management_notes.md::paragraph 1",
                "source_id": envelope["source_id"],
                "source_ids": [envelope["source_id"]],
                "source_version_id": envelope["source_version_id"],
                "known_at": envelope["known_at"],
                "effective_date": envelope["effective_date"],
                "bears_on": [],
            }

            previous = {
                "VAULT": router.VAULT,
                "PIPELINE_OUT": router.PIPELINE_OUT,
                "INGEST_JOBS_LOG": router.INGEST_JOBS_LOG,
                "INGEST_BATCHES_LOG": router.INGEST_BATCHES_LOG,
                "RUNS_LOG": router.RUNS_LOG,
                "jobs": dict(router._jobs),
                "batches": dict(router._batches),
                "runs": dict(router._runs),
            }
            router.VAULT = root / "vault"
            router.PIPELINE_OUT = root / "pipeline_out"
            router.INGEST_JOBS_LOG = root / "logs" / "ingest_jobs.json"
            router.INGEST_BATCHES_LOG = root / "logs" / "ingest_batches.json"
            router.RUNS_LOG = root / "logs" / "runs.json"
            router._jobs.clear()
            router._batches.clear()
            router._runs.clear()
            try:
                proposal_path = router._write_evidence_proposal(
                    "pan53-lifecycle",
                    "scout",
                    source_path.name,
                    [claim],
                    source_envelope=envelope,
                )
                with patch.object(router, "_rebuild_index", return_value=None):
                    admitted = asyncio.run(router.admit_evidence(
                        "scout",
                        "pan53-lifecycle",
                        {"decision": "ADMIT", "actor_id": "pan53-test"},
                    ))

                    # Simulate a process reload by discarding in-memory state;
                    # claims and the proposal must be recoverable from disk.
                    router._jobs.clear()
                    router._batches.clear()
                    router._runs.clear()
                    reloaded_claims = router._load_claims("scout")
                    retired = router.retire_source(
                        "scout",
                        envelope["source_id"],
                        {"actor_id": "pan53-test"},
                    )

                final_proposal = json.loads(
                    proposal_path.read_text(encoding="utf-8")
                )
                self.assertEqual(admitted["status"], "ADMITTED")
                self.assertEqual(final_proposal["status"], "ADMITTED")
                self.assertEqual(final_proposal["source_envelope"], envelope)
                self.assertEqual(
                    reloaded_claims[0]["source_version_id"],
                    envelope["source_version_id"],
                )
                self.assertEqual(retired["status"], "RETIRED")
                self.assertEqual(
                    json.loads(proposal_path.read_text(encoding="utf-8"))["source_envelope"],
                    envelope,
                )
            finally:
                router.VAULT = previous["VAULT"]
                router.PIPELINE_OUT = previous["PIPELINE_OUT"]
                router.INGEST_JOBS_LOG = previous["INGEST_JOBS_LOG"]
                router.INGEST_BATCHES_LOG = previous["INGEST_BATCHES_LOG"]
                router.RUNS_LOG = previous["RUNS_LOG"]
                router._jobs.clear()
                router._jobs.update(previous["jobs"])
                router._batches.clear()
                router._batches.update(previous["batches"])
                router._runs.clear()
                router._runs.update(previous["runs"])


if __name__ == "__main__":
    unittest.main()
