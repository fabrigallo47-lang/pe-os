"""Generate transport acceptance data with the actual HTTP router and engine."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / 'tests', ROOT / 'backend' / 'dynamics'):
    sys.path.insert(0, str(path))
from tools.simulation_lab import create_app
from backend.dynamics.tests.test_simulation import ASGIClient
client = ASGIClient(create_app())
bootstrap = client.get('/api/v20/bootstrap').json()
headers = {'x-panta-actor': bootstrap['context']['authenticated_actor']['actor_id'], 'x-panta-session': bootstrap['session_id']}
url = '/api/v20/cases/' + bootstrap['context']['case_id'] + '/simulations'
snapshot = client.get(url, headers=headers).json()['snapshot']
scope = snapshot['graphSimulationScope']
request = dict(mode='graph', optionId='graph', originObjectId='graph', assumption='Hypothesis', caseVersion=scope['caseVersion'], graphVersion=scope['version'], mutations=[dict(operation='RETRACT', object_type='CLAIM', object_id='CUSTOMER-CALL')])
result = client.post(url, headers=headers, json=request).json()
event = next(r for r in snapshot['graphSimulationScenarios'] if r['request']['eventId'] == 'EVENT-CUSTOMER-WITHDRAWAL')
proposal_request = dict(text='Aumenta costi operativi del 10%', caseVersion=scope['caseVersion'], graphVersion=scope['version'])
proposal = client.post(url + '/propose', headers=headers, json=proposal_request).json()
combined_proposal = client.post(url + '/propose', headers=headers, json={**proposal_request, 'text': 'Riduci ricavi del 10%; ritira «Customer interviews indicate renewal intent»'}).json()
assert combined_proposal['status'] == 'READY'
combined_request = {**request, 'assumption': combined_proposal['text'], 'mutations': [m for item in combined_proposal['items'] for m in item['mutations']]}
combined_response = client.post(url, headers=headers, json=combined_request)
assert combined_response.status_code == 200
(ROOT / 'tests/fixtures/graph-simulation.json').write_text(json.dumps(dict(snapshot=snapshot, proposalRequest=proposal_request, proposalResult=proposal, requests=dict(graph=request, graph_event=event['request'], graph_combined=combined_request), results=dict(graph=result, graph_event=event, graph_combined=combined_response.json())), indent=2) + '\n')
