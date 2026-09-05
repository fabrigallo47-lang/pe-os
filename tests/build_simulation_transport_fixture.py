"""Regenerate checked-in transport examples using the real simulation engine."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend' / 'dynamics'))
from simulation_fixture import CASE_ID, PEER_ID, advanced_fixture
from app.simulation_routes import simulation_projection
from backend.dynamics.runtime.simulation import SimulationModel
from backend.dynamics.runtime.simulation_events import event_scenarios
from backend.dynamics.runtime.simulation_queries import inverse, compare

saved, events = advanced_fixture()
peer_saved, _ = advanced_fixture(PEER_ID)
case, graph, mapping = saved
peer_case, peer_graph, peer_mapping = peer_saved
model = SimulationModel(CASE_ID, case['caseVersion'], graph, mapping)
peer = SimulationModel(PEER_ID, peer_case['caseVersion'], peer_graph, peer_mapping)
snapshot = simulation_projection(case, model)
snapshot['simulationScenarios'], snapshot['simulationEventLimits'] = event_scenarios(model, graph, events)
base = dict(optionId='REVENUE', originObjectId='REVENUE', assumption='Test', caseVersion=model.case_version, scopeVersion=model.version)
requests = dict(inverse={**base, 'mode':'inverse', 'inverse':dict(outputId='LEVERAGE', target='3', lower='70', upper='100')},
    compare={**base, 'mode':'compare', 'percent':'-10', 'peerCaseId':PEER_ID, 'peerCaseVersion':peer.case_version, 'peerScopeVersion':peer.version},
    event={k:v for k,v in snapshot['simulationScenarios'][0]['request'].items() if k != 'value'})
results = dict(inverse=inverse(model, requests['inverse']), compare=compare(model, peer, requests['compare'], peer_case['caseRef']['name']), event=snapshot['simulationScenarios'][0])
(ROOT / 'tests/fixtures/simulation-queries.json').write_text(json.dumps(dict(snapshots={CASE_ID:snapshot, PEER_ID:simulation_projection(peer_case, peer)}, requests=requests, results=results), indent=2) + '\n')
