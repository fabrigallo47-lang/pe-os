import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from app.v20_router import UnsupportedUploadFormat, _extraction_command


class PipelineEntrypointTests(unittest.TestCase):
    def test_live_intake_routes_open_xml_to_v2_and_rejects_legacy_xls(self):
        for suffix in (".xlsx", ".xlsm"):
            with self.subTest(suffix=suffix):
                label, command = _extraction_command(
                    Path("/tmp") / f"synthetic{suffix}", "keystone", "job-36"
                )
                self.assertEqual(label, "SINGLE_V2")
                self.assertIn("extract_v2.py", " ".join(command))
                self.assertIn(f"synthetic{suffix}", " ".join(command))

        with self.assertRaisesRegex(UnsupportedUploadFormat, r"convert.*\.xlsx"):
            _extraction_command(Path("/tmp/legacy.xls"), "keystone", "job-36")

    def test_standalone_pipeline_reaches_api_boundary(self):
        """The live PDF/text entry point must import and convert before API use."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "keystone-source.md"
            source.write_text("Keystone revenue was $10m in FY2025.\n", encoding="utf-8")
            output = Path(tmp) / "output"
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)

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
