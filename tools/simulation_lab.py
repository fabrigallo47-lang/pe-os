"""Isolated acceptance server using the production bootstrap/transport shapes."""
import copy
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / 'tests', ROOT / 'backend' / 'dynamics'):
    sys.path.insert(0, str(path))

from fastapi import FastAPI, HTTPException
import uvicorn
from app.simulation_routes import simulation_router
from app.simulation_store import ScenarioStore
from simulation_fixture import ACTOR, CASE_ID, PEER_ID
from graph_simulation_fixture import graph_fixture
from app.simulation_proposals import configured_proposal_model


def create_app():
    app = FastAPI()
    saved = {cid: graph_fixture(cid) for cid in (CASE_ID, PEER_ID)}
    tokens = {cid: secrets.token_urlsafe(32) for cid in saved}
    store = ScenarioStore(Path(tempfile.mkdtemp(prefix='panta-simulation-lab-')) / 'scenarios.sqlite3')

    def load(case_id):
        if case_id not in saved:
            raise HTTPException(404, 'Unknown simulation test case.')
        return copy.deepcopy(saved[case_id][0])

    def auth(case_id, actor_id, session):
        if case_id not in saved or actor_id != ACTOR['actorId'] or session != tokens[case_id]:
            raise HTTPException(403, 'Invalid simulation lab session.')
        return ACTOR

    @app.get('/api/v20/bootstrap')
    def bootstrap(case_id: str = CASE_ID):
        if case_id not in saved:
            raise HTTPException(404, 'Unknown simulation test case.')
        return dict(session_id=tokens[case_id], available_cases=list(saved),
                    context=dict(case_id=case_id, authenticated_actor=dict(actor_id=ACTOR['actorId'])))

    app.include_router(simulation_router(load, auth, lambda cid: copy.deepcopy(saved[cid][1]), lambda _: store,
        lambda cid: copy.deepcopy(saved[cid][2]), configured_proposal_model()))
    return app


if __name__ == '__main__':
    uvicorn.run(create_app(), host='127.0.0.1', port=8177, log_level='warning')
