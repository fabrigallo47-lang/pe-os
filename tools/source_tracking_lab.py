"""Isolated native-source lab. Uses temporary synthetic files, never the repository vault.

Run: .venv/bin/python tools/source_tracking_lab.py
Then npm run lab and open /source-tracking.html.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "tests", ROOT / "backend" / "dynamics"):
    sys.path.insert(0, str(path))

from fastapi import FastAPI
import uvicorn
import app.v20_router as router
from source_document_fixtures import build_fixture_case


def main():
    with tempfile.TemporaryDirectory(prefix="panta-source-lab-") as temporary:
        root = Path(temporary)
        fixture = build_fixture_case(root)
        router.VAULT = root / "vault"
        router.CASE_PIPELINE_ROOT = root / "cases"
        router.PIPELINE_OUT = root / "legacy"
        app = FastAPI()
        # Expose only the three read endpoints, never case mutation or real-case readers.
        for route in router.v20.routes:
            if "/source-document" in route.path:
                app.router.routes.append(route)

        @app.get("/api/source-tracking-lab")
        def lab_fixture():
            return {"caseId": fixture["caseId"], "citations": fixture["citations"]}

        uvicorn.run(app, host="127.0.0.1", port=8176, log_level="warning")


if __name__ == "__main__":
    main()
