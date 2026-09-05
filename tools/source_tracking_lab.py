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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
import app.v20_router as router
from source_document_fixtures import build_fixture_case
from typed_statement_fixture import build_typed_fixture


def main():
    with tempfile.TemporaryDirectory(prefix="panta-source-lab-") as temporary:
        root = Path(temporary)
        fixture = build_fixture_case(root)
        typed = build_typed_fixture(root)
        router.VAULT = root / "vault"
        router.CASE_PIPELINE_ROOT = root / "cases"
        router.PIPELINE_OUT = root / "legacy"
        app = FastAPI()
        app.add_middleware(GZipMiddleware, minimum_size=1024)
        references = {}
        # Expose only the three read endpoints, never case mutation or real-case readers.
        for route in router.v20.routes:
            if "/source-document" in route.path:
                app.router.routes.append(route)

        @app.get("/api/source-tracking-lab")
        def lab_fixture():
            return {"caseId": fixture["caseId"], "citations": fixture["citations"], "typedClaims": typed["projected"]}

        def reference_case(simulate=False):
            if simulate not in references:
                from tools.repository_tracking_case import build_repository_case
                try:
                    references[simulate] = build_repository_case(root, simulate_locations=simulate)
                except (FileNotFoundError, ValueError) as exc:
                    raise HTTPException(422, str(exc)) from exc
            return references[simulate]

        @app.get("/api/source-tracking-lab/reference")
        def reference_fixture(simulate: bool = False):
            case = reference_case(simulate)
            return {key: case[key] for key in ("snapshot", "entries", "report", "audit")}

        @app.get("/api/source-tracking-lab/reference/inspect")
        def reference_inspection(object_id: str, simulate: bool = False):
            return reference_case(simulate)["inspect"](object_id)

        uvicorn.run(app, host="127.0.0.1", port=8176, log_level="warning")


if __name__ == "__main__":
    main()
