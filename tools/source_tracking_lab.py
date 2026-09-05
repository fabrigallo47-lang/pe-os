"""Isolated native-source lab. Uses temporary synthetic files, never the repository vault.

Run: .venv/bin/python tools/source_tracking_lab.py
Then npm run lab and open /source-tracking.html.
"""
import sys
import tempfile
import secrets
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "tests", ROOT / "backend" / "dynamics"):
    sys.path.insert(0, str(path))

from fastapi import FastAPI, HTTPException, Request
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
        from ic_memo_fixture import build_memo_cases, ACTOR, simulated_writer
        from app.live_outputs import OutputStore
        from app.output_routes import output_router
        memo_cases = build_memo_cases(root)
        memo_current = [memo_cases[0]]
        memo_token = secrets.token_urlsafe(32)
        memo_store = OutputStore(root / 'memo-revisions.sqlite3')

        def memo_case(case_id):
            if case_id != 'MEMO-TEST':
                raise HTTPException(404, 'Unknown output test case.')
            return copy.deepcopy(memo_current[0])

        def memo_auth(case_id, actor_id, token):
            if case_id != 'MEMO-TEST' or actor_id != ACTOR['actorId'] or token != memo_token:
                raise HTTPException(403, 'Invalid output lab session.')
            return ACTOR

        app.include_router(output_router(memo_case, memo_auth, lambda _: memo_store, simulated_writer,
                                        writer_label='Simulated writer · no live model call'))

        @app.get('/api/source-tracking-lab/memo/session')
        def memo_session():
            return dict(actorId=ACTOR['actorId'], sessionId=memo_token)

        @app.post('/api/source-tracking-lab/memo/change')
        def memo_change(request: Request, payload: dict):
            memo_auth('MEMO-TEST', ACTOR['actorId'], request.headers.get('x-panta-session'))
            if payload.get('amount') not in (5, 6):
                raise HTTPException(422, 'Choose a predefined test scenario.')
            memo_current[0] = memo_cases[0 if payload['amount'] == 5 else 1]
            return {'caseVersion': memo_current[0]['caseVersion']}
        references = {}
        # Source endpoints remain read-only; output mutations are scoped to the fictional case above.
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
