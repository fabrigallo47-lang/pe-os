import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class PipelineEntrypointTests(unittest.TestCase):
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
