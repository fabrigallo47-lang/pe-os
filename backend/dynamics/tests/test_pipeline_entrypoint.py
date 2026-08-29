import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from app.v20_router import UnsupportedUploadFormat, _extraction_command
from tools.source_envelope import build_source_envelope


class PipelineEntrypointTests(unittest.TestCase):
    def test_live_intake_routes_supported_uploads_to_v2_and_rejects_legacy_xls(self):
        for suffix in (".xlsx", ".xlsm", ".pdf", ".md", ".txt"):
            with self.subTest(suffix=suffix):
                label, command = _extraction_command(
                    Path("/tmp") / f"synthetic{suffix}", "keystone", "job-36"
                )
                self.assertEqual(label, "SINGLE_V2")
                self.assertIn("extract_v2.py", " ".join(command))
                self.assertIn(f"synthetic{suffix}", " ".join(command))

        with self.assertRaisesRegex(UnsupportedUploadFormat, r"convert.*\.xlsx"):
            _extraction_command(Path("/tmp/legacy.xls"), "keystone", "job-36")

    def test_source_envelope_reaches_v2_without_keystone_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "vendor-note.md"
            source.write_text("Revenue was $10m in FY2025.\n", encoding="utf-8")
            envelope = build_source_envelope(
                source, "scout", "2026-08-29T00:00:00Z",
                declared_metadata={"document_type": "Vendor note", "issuer": "Seller"},
            )
            envelope_path = root / "source-envelope.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            output = root / "out"
            result = subprocess.run(
                [
                    sys.executable, str(REPO_ROOT / "tools" / "extract_v2.py"),
                    "--source", str(source), "--deal", "scout", "--output", str(output),
                    "--source-envelope", str(envelope_path), "--dry-run",
                ],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            chunks = json.loads((output / "SINGLE" / "chunks_debug.json").read_text())
            self.assertEqual(chunks[0]["source_id"], envelope["source_id"])

    def test_standalone_pipeline_reaches_api_boundary(self):
        """The live PDF/text entry point must import and convert before API use."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "keystone-source.md"
            source.write_text("Keystone revenue was $10m in FY2025.\n", encoding="utf-8")
            output = Path(tmp) / "output"
            env = os.environ.copy()
            for key in (
                "ANTHROPIC_API_KEY",
                "OPENROUTER_API_KEY",
                "PEOS_LLM_PROVIDER",
                "PEOS_MODEL",
                "PEOS_LLM_BASE_URL",
            ):
                env.pop(key, None)

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "pipeline.py"),
                    str(source),
                    "--deal",
                    "keystone",
                    "--out",
                    str(output),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1)
        self.assertIn("characters extracted", combined)
        self.assertIn("ANTHROPIC_API_KEY not set", combined)
        self.assertNotIn("ModuleNotFoundError", combined)


if __name__ == "__main__":
    unittest.main()
