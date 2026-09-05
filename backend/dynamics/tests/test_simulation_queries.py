import copy
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from backend.dynamics.tests.test_simulation import ASGIClient
from backend.dynamics.runtime.simulation import SimulationModel, SimulationError
from backend.dynamics.runtime.simulation_queries import inverse, compare
from backend.dynamics.runtime.simulation_events import event_scenarios
from app.simulation_routes import simulation_router
from app.simulation_store import ScenarioStore
from simulation_fixture import ACTOR, CASE_ID, PEER_ID, advanced_fixture
from fastapi import FastAPI, HTTPException


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.saved, self.events = advanced_fixture()
        self.peer_saved, _ = advanced_fixture(PEER_ID)
        self.model = self.make(self.saved)
        self.peer = self.make(self.peer_saved)

    def make(self, saved):
        case, graph, mapping = saved
        return SimulationModel(case['caseRef']['id'], case['caseVersion'], graph, mapping)

    def request(self, **kwargs):
        return dict(optionId='REVENUE', originObjectId='REVENUE', caseVersion=self.model.case_version, scopeVersion=self.model.version, **kwargs)

    def solve(self, **changes):
        return inverse(self.model, self.request(mode='inverse', inverse={**dict(outputId='LEVERAGE', target='3', lower='70', upper='100'), **changes}))

    def comparison(self, **kwargs):
        return compare(self.model, self.peer, self.request(mode='compare', percent='-10', peerCaseVersion=self.peer.case_version, peerScopeVersion=self.peer.version, **kwargs), 'Peer')

    def test_inverse_reaches_leverage_threshold_and_replays_forward(self):
        result = self.solve()
        answer = result['inverse']
        self.assertEqual(answer['status'], 'FOUND')
        self.assertAlmostEqual(float(answer['inputValue']), 86.6666666667, places=6)
        self.assertLessEqual(abs(Decimal(answer['residual'])), Decimal(answer['tolerance']))
        replay = self.model.run({**result['request'], 'value': answer['inputValue']})
        self.assertEqual(result['effects'], replay['effects'])
        self.assertEqual(result, self.solve())

    def test_increasing_inverse_and_endpoint(self):
        for target, value in [('25', 85), ('10', 70), ('40', 100)]:
            with self.subTest(target=target):
                result = self.solve(outputId='PROFIT', target=target)
                self.assertEqual(result['inverse']['status'], 'FOUND')
                self.assertAlmostEqual(float(result['inverse']['inputValue']), value, places=6)

    def test_unreachable_target_has_no_fabricated_impact(self):
        result = self.solve(target='50')
        self.assertEqual(result['inverse']['status'], 'UNREACHABLE')
        self.assertEqual(result['effects'], [])
        self.assertNotIn('inputValue', result['inverse'])

    def test_pole_and_piecewise_output_never_claim_unique_threshold(self):
        for query in [dict(lower='50'), dict(outputId='CAP', target='30')]:
            result = self.solve(**query)
            self.assertEqual(result['inverse']['status'], 'UNSUPPORTED')
            self.assertEqual(result['effects'], [])

    def test_nonmonotone_polynomial_is_not_solved_by_arbitrary_sampling(self):
        formula = next(f for f in self.saved[2]['formulas'] if f['output_id'] == 'PROFIT')
        formula['expression_or_function_ref'] = '(revenue - cost) * (revenue - 80) / 20'
        self.model = self.make(self.saved)
        self.assertEqual(self.solve(outputId='PROFIT', target='10', lower='50', upper='100')['inverse']['status'], 'UNSUPPORTED')

    def test_invalid_bounds_target_and_unrelated_output(self):
        for change in [dict(lower='100', upper='70'), dict(target='NaN'), dict(outputId='DEBT'), dict(outputId='IRR'), dict(lower='1e999')]:
            with self.subTest(change=change), self.assertRaises(SimulationError):
                self.solve(**change)

    def test_comparison_equal_shock_different_sensitivity(self):
        result = self.comparison()
        rows = {r['objectId']: r for r in result['comparison']['rows']}
        self.assertEqual(Decimal(rows['PROFIT']['current']['after']), 30)
        self.assertEqual(Decimal(rows['PROFIT']['peer']['after']), 18)
        self.assertEqual(Decimal(rows['PROFIT']['current']['percent']), -25)
        self.assertEqual(Decimal(rows['PROFIT']['peer']['percent']), -40)
        self.assertTrue(any(r['objectId'] == 'IRR' for r in result['comparison']['exclusions']))
        self.assertNotIn('peerSessionId', json.dumps(result))

    def test_mismatched_dimensions_or_missing_definition_fail_closed(self):
        for dimension in ('currency', 'period', 'perimeter', 'basis', 'scenario', 'unit', 'comparison_key'):
            with self.subTest(dimension=dimension):
                changed = copy.deepcopy(self.peer_saved)
                changed[1]['model_nodes'][0][dimension] = 'different'
                self.peer = self.make(changed)
                with self.assertRaisesRegex(SimulationError, 'unambiguous input'):
                    self.comparison()
        self.peer = self.make(self.peer_saved)

    def test_output_definition_mismatch_excludes_only_that_row(self):
        self.peer.nodes['PROFIT']['comparison_key'] = 'different'
        result = self.comparison()
        self.assertNotIn('PROFIT', [r['objectId'] for r in result['comparison']['rows']])
        self.assertIn('LEVERAGE', [r['objectId'] for r in result['comparison']['rows']])

    def test_candidate_peer_and_duplicate_comparison_identity_cannot_match(self):
        self.peer.nodes['DEBT'].update({k: v for k, v in self.peer.nodes['REVENUE'].items() if k in ('comparison_key', 'unit', 'currency', 'period', 'perimeter', 'basis', 'scenario')})
        with self.assertRaises(SimulationError):
            self.comparison()
        changed = copy.deepcopy(self.peer_saved)
        changed[1]['model_nodes'][0]['institutional_state'] = 'CANDIDATE'
        self.peer = self.make(changed)
        with self.assertRaises(SimulationError):
            self.comparison()

    def test_peer_version_is_pinned(self):
        request = self.request(mode='compare', percent='-10', peerCaseVersion='OLD', peerScopeVersion=self.peer.version)
        with self.assertRaisesRegex(SimulationError, 'Refresh'):
            compare(self.model, self.peer, request, 'Peer')

    def test_events_apply_multiple_inputs_atomically_and_keep_lineage(self):
        before = copy.deepcopy((self.saved, self.events))
        results, limits = event_scenarios(self.model, self.saved[1], self.events)
        self.assertEqual(limits, [])
        self.assertEqual(len(results), 1)
        result = results[0]
        effects = {e['objectId']: e for e in result['effects']}
        self.assertEqual(Decimal(effects['PROFIT']['magnitude']['after']), 25)
        self.assertEqual(Decimal(effects['LEVERAGE']['magnitude']['after']), Decimal('3.2'))
        self.assertEqual(len(result['event']['changes']), 2)
        self.assertEqual(result['event']['eventId'], self.events[0]['event_id'])
        self.assertEqual(result['event']['sourceIds'], ['SOURCE-UPDATE'])
        self.assertEqual(before, (self.saved, self.events))
        self.assertEqual((results, limits), event_scenarios(self.model, self.saved[1], self.events))

    def test_unadmitted_or_unmapped_events_do_not_generate_scenarios(self):
        for change in [dict(admission_mode=None), dict(institutional_state='CANDIDATE'), dict(case_id='OTHER'), dict(event='UNMAPPED')]:
            events = [{**self.events[0], **change}]
            self.assertEqual(event_scenarios(self.model, self.saved[1], events)[0], [])

    def test_one_invalid_event_change_blocks_whole_scenario(self):
        for change in [dict(unit='USD'), dict(value='unknown'), dict(operation='RETRACT'), dict(period=None)]:
            events = copy.deepcopy(self.events)
            events[0]['mutations'][0].update(change)
            results, limits = event_scenarios(self.model, self.saved[1], events)
            self.assertEqual(results, [])
            self.assertEqual(len(limits), 1)

    def test_duplicate_mutations_and_conflicting_rules_are_rejected(self):
        events = copy.deepcopy(self.events)
        events[0]['mutations'].append(events[0]['mutations'][0])
        self.assertEqual(event_scenarios(self.model, self.saved[1], events)[0], [])
        self.model.mapping['simulation_event_rules'][1]['input_id'] = 'REVENUE'
        self.assertEqual(event_scenarios(self.model, self.saved[1], self.events)[0], [])

    def test_all_queries_preserve_both_cases_human_views_and_decisions(self):
        before = copy.deepcopy((self.saved, self.peer_saved))
        self.solve(); self.comparison(); event_scenarios(self.model, self.saved[1], self.events)
        self.assertEqual(before, (self.saved, self.peer_saved))


class QueryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ScenarioStore(Path(self.temp.name) / 'scenarios.sqlite3')
        self.saved = {cid: advanced_fixture(cid) for cid in (CASE_ID, PEER_ID)}
        self.loaded = []
        def auth(cid, actor, token):
            if cid not in self.saved or actor != ACTOR['actorId'] or token != cid + '-TOKEN':
                raise HTTPException(403, 'Invalid case session.')
            return ACTOR
        def load(cid):
            self.loaded.append(cid)
            return copy.deepcopy(self.saved[cid][0])
        app = FastAPI()
        app.include_router(simulation_router(load, auth, lambda cid: copy.deepcopy(self.saved[cid][1]), lambda _: self.store))
        self.client = ASGIClient(app)
        self.url = '/api/v20/cases/' + CASE_ID + '/simulations'
        self.headers = {'X-Panta-Actor': ACTOR['actorId'], 'X-Panta-Session': CASE_ID + '-TOKEN'}
        self.snapshot = self.client.get(self.url, headers=self.headers).json()['snapshot']
        self.body = dict(optionId='REVENUE', originObjectId='REVENUE', caseVersion=self.snapshot['caseVersion'], scopeVersion=self.snapshot['simulationScope']['version'])

    def tearDown(self):
        self.temp.cleanup()

    def post(self, body):
        return self.client.post(self.url, headers=self.headers, json=body)

    def peer_body(self):
        case, graph, mapping = self.saved[PEER_ID][0]
        model = SimulationModel(PEER_ID, case['caseVersion'], graph, mapping)
        return dict(**self.body, mode='compare', percent='-10', peerCaseId=PEER_ID, peerActorId=ACTOR['actorId'], peerSessionId=PEER_ID+'-TOKEN', peerCaseVersion=model.case_version, peerScopeVersion=model.version)

    def test_event_is_automatically_prepared_archived_and_inspectable(self):
        scenario = self.snapshot['simulationScenarios'][0]
        body = {k: v for k, v in scenario['request'].items() if k != 'value'}
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), scenario)
        saved = self.client.get(self.url + '/archive/' + scenario['id'], headers=self.headers)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['result'], scenario)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM scenarios').fetchone()[0], 1)
        self.assertEqual(self.client.get(self.url + '/archive/' + scenario['id']).status_code, 403)

    def test_new_basis_creates_new_scenario_preserves_original_archive(self):
        old = self.snapshot['simulationScenarios'][0]
        self.saved[CASE_ID][0][0]['caseVersion'] = 'NEW'
        fresh = self.client.get(self.url, headers=self.headers).json()['snapshot']['simulationScenarios'][0]
        self.assertNotEqual(old['id'], fresh['id'])
        self.assertEqual(self.store.read(CASE_ID, old['id'])['result'], old)
        self.assertEqual(self.post({k: v for k, v in old['request'].items() if k != 'value'}).status_code, 409)
        with self.store.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute('DELETE FROM scenarios')

    def test_inverse_http_success_and_invalid_request(self):
        response = self.post(dict(**self.body, mode='inverse', inverse=dict(outputId='LEVERAGE', target='3', lower='70', upper='100')))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['inverse']['status'], 'FOUND')
        self.assertEqual(self.post(dict(**self.body, mode='inverse', inverse={})).status_code, 422)

    def test_comparison_requires_independent_peer_access_before_loading_peer(self):
        body = self.peer_body()
        self.loaded.clear()
        self.assertEqual(self.post({**body, 'peerSessionId': CASE_ID+'-TOKEN'}).status_code, 403)
        self.assertNotIn(PEER_ID, self.loaded)
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['comparison']['peerCaseId'], PEER_ID)
        self.assertNotIn('TOKEN', response.text)

    def test_stale_peer_and_injected_model_are_rejected(self):
        body = self.peer_body()
        self.saved[PEER_ID][0][0]['caseVersion'] = 'NEW'
        self.assertEqual(self.post(body).status_code, 409)
        self.assertEqual(self.post({**self.body, 'mode': 'event', 'overrides': {'REVENUE': 5}}).status_code, 422)

class ProductionSimulationTests(unittest.TestCase):
    def test_real_bootstrap_auth_ledger_archive_and_model_routes(self):
        import os
        from unittest.mock import patch
        import app.v20_router as runtime
        from app.simulation_routes import production_simulation_router
        from backend.dynamics.runtime import ledger_store
        saved, events = advanced_fixture()
        case, graph, mapping = saved
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deal_dir = root / 'deals' / CASE_ID
            deal_dir.mkdir(parents=True)
            (deal_dir / 'deal.md').write_text('# Synthetic production case')
            pipeline = root / 'pipeline'
            pipeline.mkdir()
            (pipeline / 'execution_mapping.json').write_text(json.dumps(mapping))
            projection = dict(actor_directory=[dict(id=ACTOR['actorId'], name='Test reviewer')], deal=dict(case_id=CASE_ID,
                entity='Production route test', as_of_state_id='CURRENT-TEST', as_of_date='2026-09-05', current_graph=graph,
                question_spine=[dict(id='MODEL-Q', label='Test question')]))
            context = dict(case_id=CASE_ID, authenticated_actor=dict(actor_id=ACTOR['actorId']))
            with patch.object(runtime, 'VAULT', root), patch.object(runtime, '_build_projection', return_value=projection), \
                 patch.object(runtime, '_pipeline_out_for_case', return_value=pipeline), patch.object(runtime, '_make_context', return_value=context), \
                 patch.object(runtime, '_current_state_id', return_value='CURRENT-TEST'), patch.object(runtime, '_load_profile', return_value={}), \
                 patch.object(runtime, '_available_case_ids', return_value=[CASE_ID]), patch.object(ledger_store, 'PIPELINE_OUT', root / 'ledger'), \
                 patch.dict(os.environ, {'PANTA_SIMULATION_DB': str(root / 'scenarios.sqlite3'), 'VERCEL': ''}):
                for event in events:
                    ledger_store.append_event(CASE_ID, event)
                app = FastAPI(); app.include_router(runtime.v20); app.include_router(production_simulation_router())
                client = ASGIClient(app)
                boot = client.get('/api/v20/bootstrap?case_id=' + CASE_ID)
                self.assertEqual(boot.status_code, 200, boot.text)
                headers = {'X-Panta-Actor': ACTOR['actorId'], 'X-Panta-Session': boot.json()['session_id']}
                url = '/api/v20/cases/' + CASE_ID + '/simulations'
                read = client.get(url, headers=headers)
                self.assertEqual(read.status_code, 200, read.text)
                snapshot = read.json()['snapshot']
                self.assertEqual(len(snapshot['simulationScenarios']), 1)
                evidence_claim = next(c for c in snapshot['claims'] if c['id'] == 'CLAIM-REVENUE')
                self.assertEqual(evidence_claim['tracking']['period'], 'FY2027')
                self.assertTrue(evidence_claim['tracking']['unit'])
                body = dict(mode='inverse', optionId='REVENUE', originObjectId='REVENUE', caseVersion=snapshot['caseVersion'], scopeVersion=snapshot['simulationScope']['version'], inverse=dict(outputId='LEVERAGE', target='3', lower='70', upper='100'))
                result = client.post(url, headers=headers, json=body)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['inverse']['status'], 'FOUND')
                scenario = snapshot['simulationScenarios'][0]
                archive = client.get(url + '/archive/' + scenario['id'], headers=headers)
                self.assertEqual(archive.json()['evidence']['event_id'], events[0]['event_id'])
                self.assertEqual(client.get(url, headers={**headers, 'X-Panta-Actor': 'IMPOSTOR'}).status_code, 403)
                self.assertEqual(len(ledger_store.read_ledger(CASE_ID)), 1)
