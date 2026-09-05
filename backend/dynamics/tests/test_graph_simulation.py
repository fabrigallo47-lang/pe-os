import copy
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT, ROOT / 'tests', ROOT / 'backend' / 'dynamics'):
    sys.path.insert(0, str(path))
from fastapi import FastAPI, HTTPException
from graph_simulation_fixture import graph_fixture
from simulation_fixture import CASE_ID, ACTOR
from backend.dynamics.runtime.graph_simulation import GraphSimulation, truth_states
from backend.dynamics.runtime.simulation import SimulationError, digest
from backend.dynamics.runtime.panta_transition_engine import apply_state_transition, compare_incremental_global
from app.simulation_routes import simulation_router
from app.simulation_store import ScenarioStore
from backend.dynamics.tests.test_simulation import ASGIClient


def withdraw(identity, kind='CLAIM'):
    return dict(operation='RETRACT', object_type=kind, object_id=identity)


def change(identity, field, value, kind='CLAIM'):
    return dict(operation='CORRECT', object_type=kind, object_id=identity, field=field, to=value)


class GraphSimulationTests(unittest.TestCase):
    def setUp(self):
        (self.case, self.graph, self.mapping), self.events, self.inputs = graph_fixture()
        self.sim = GraphSimulation(CASE_ID, self.case['caseVersion'], self.inputs)

    def request(self, mutations):
        return dict(mode='graph', optionId='graph', originObjectId='graph', assumption='Hypothesis', caseVersion=self.sim.case_version, graphVersion=self.sim.version, mutations=mutations)

    def run_changes(self, changes):
        request = self.request(changes)
        original = copy.deepcopy((self.inputs, request, self.sim.state))
        result = self.sim.run(request)
        # Compare the complete runtime result against a separately invoked live
        # transition, not another projection or just a selected numeric output.
        expected = apply_state_transition(self.inputs['prior_state'], [self.sim.manual_event(changes)], self.mapping, self.inputs['materiality_policy'], self.inputs['authority_policy'])
        self.assertEqual(result['graph']['engineResult'], expected)
        self.assertEqual(original, (self.inputs, request, self.sim.state))
        self.assertEqual(expected['candidate_state']['approved_snapshot'], self.sim.state['approved_snapshot'])
        self.assertEqual(expected['candidate_state']['current_graph']['stated_positions'], self.graph['stated_positions'])
        self.assertEqual(expected['candidate_state']['history'], self.sim.state['history'])
        self.assertEqual(result, self.sim.run(request))
        return result['graph']

    def test_withdrawal_preserves_independent_surviving_route(self):
        report = self.run_changes([withdraw('CUSTOMER-CALL')])
        rows = {r['id']: r for r in report['rows']}
        self.assertEqual(rows['INTERVIEW-PATH']['afterSupport'], 'FALSE')
        self.assertEqual(rows['RETENTION']['status'], 'HELD')
        self.assertEqual(rows['DEBT-SERVICE']['status'], 'HELD')
        self.assertNotIn('ISOLATED-CLAIM', rows)
        self.assertTrue(any(e['source'] == 'RENEWAL-RECORD' for e in report['edges']))

    def test_total_support_loss_propagates_through_conclusions_without_rewriting_decisions(self):
        report = self.run_changes([withdraw('CUSTOMER-CALL'), withdraw('RENEWAL-RECORD')])
        for identity in ('RETENTION', 'FINANCING-PATH', 'DEBT-SERVICE'):
            self.assertEqual(next(r for r in report['rows'] if r['id'] == identity)['afterSupport'], 'FALSE')
        self.assertTrue(all(p['decision_status'] == 'ACCEPTED' for p in report['engineResult']['candidate_state']['current_graph']['case_positions']))

    def test_withdrawn_route_cannot_prove_its_target(self):
        report = self.run_changes([withdraw('INTERVIEW-PATH', 'SUPPORT_ROUTE'), withdraw('RECORD-PATH', 'SUPPORT_ROUTE')])
        self.assertEqual(truth_states(report['engineResult']['transition_output'])['DEBT-SERVICE'], 'FALSE')
        self.assertIn('SUPPORT_ROUTE_RETRACTED', report['engineResult']['transition_output']['route_results'][1]['reason_codes'])

    def test_structural_evidence_replacement_uses_actual_before_and_after_edges(self):
        report = self.run_changes([change('RECORD-PATH', 'member_claim_ids', ['CUSTOMER-LOSS'], 'SUPPORT_ROUTE')])
        edges = report['edges']
        self.assertTrue(any(e['source'] == 'RENEWAL-RECORD' and e['target'] == 'RECORD-PATH' and e['version'] == 'CURRENT' for e in edges))
        self.assertFalse(any(e['source'] == 'RENEWAL-RECORD' and e['target'] == 'RECORD-PATH' and e['version'] == 'HYPOTHETICAL' for e in edges))
        self.assertEqual(truth_states(report['engineResult']['transition_output'])['RECORD-PATH'], 'FALSE')

    def test_counterevidence_and_removed_alternative_make_conflict_and_review_visible(self):
        report = self.run_changes([change('CUSTOMER-LOSS', 'usable', True), withdraw('RECORD-PATH', 'SUPPORT_ROUTE')])
        self.assertEqual(truth_states(report['engineResult']['transition_output'])['RETENTION'], 'UNKNOWN')
        self.assertTrue(report['engineResult']['transition_output']['human_stops'])
        self.assertTrue(report['engineResult']['transition_output']['blocked_components'])
        self.assertGreater(report['counts']['unavailable'], 0, 'A changed but unresolved result must not be counted as completely established.')

    def test_new_hypothetical_evidence_can_join_a_counterevidence_path(self):
        added = dict(operation='ADD', object_type='CLAIM', object_id='HYPOTHETICAL:LOSS', statement='A contract will terminate', target_position_id='RETENTION', relation_type='CONTRADICTS')
        report = self.run_changes([added, change('INTERVIEW-PATH', 'counter_claim_ids', ['HYPOTHETICAL:LOSS'], 'SUPPORT_ROUTE')])
        self.assertIn('HYPOTHETICAL:LOSS', report['labels'])
        self.assertEqual(truth_states(report['engineResult']['transition_output'])['INTERVIEW-PATH'], 'UNKNOWN')
        self.assertTrue(any(e['source'] == 'HYPOTHETICAL:LOSS' and e['target'] == 'RETENTION' and e['relation'] == 'CONTRADICTS' for e in report['edges']))
        unbound = self.run_changes([added])
        self.assertTrue(any(issue['raw'].get('reason_code') == 'NO_DECLARED_SUPPORT_ROUTE_MEMBERSHIP' for issue in unbound['issues']))

    def test_mixed_graph_and_financial_changes_share_one_transition(self):
        report = self.run_changes([withdraw('CUSTOMER-CALL'), change('REVENUE', 'value', '90', 'MODEL_NODE')])
        nodes = {n['model_node_id']: n for n in report['engineResult']['candidate_state']['current_graph']['model_nodes']}
        self.assertEqual(Decimal(nodes['PROFIT']['value']), 30)
        self.assertEqual(nodes['IRR']['freshness_status'], 'STALE')
        self.assertEqual(truth_states(report['engineResult']['transition_output'])['INTERVIEW-PATH'], 'FALSE')
        self.assertTrue(any('IRR' in issue['objectIds'] for issue in report['issues']))

    def test_text_change_discloses_that_it_cannot_infer_new_logic(self):
        report = self.run_changes([change('CUSTOMER-CALL', 'statement', 'The customer will not renew')])
        self.assertTrue(any(issue['raw'].get('reason_code') == 'NO_IMPLICIT_SEMANTIC_REINTERPRETATION' for issue in report['issues']))

    def test_freshness_and_conflicting_from_are_real_runtime_outputs(self):
        report = self.run_changes([change('CUSTOMER-CALL', 'freshness_status', 'STALE')])
        self.assertEqual(truth_states(report['engineResult']['transition_output'])['INTERVIEW-PATH'], 'UNKNOWN')
        report = self.run_changes([{**change('CUSTOMER-CALL', 'usable', False), 'from': 'incorrect'}])
        self.assertEqual(report['counts']['changed'], 0)
        self.assertIn('PRIOR_VALUE_MISMATCH', json.dumps(report['engineResult']))

    def test_human_views_frozen_axes_and_unadmitted_objects_are_protected(self):
        invalid = [change('HUMAN-1', 'statement', 'Invented human view', 'STATED_POSITION'),
            change('RETENTION', 'decision_status', 'REJECTED', 'POSITION'), change('RETENTION', 'decision_status_at_ic', 'REJECTED', 'POSITION'),
            change('MISSING', 'usable', True), {**withdraw('CUSTOMER-CALL'), 'actor_id': 'SOMEONE'},
            change('RECORD-PATH', 'member_claim_ids', ['MISSING'], 'SUPPORT_ROUTE'),
            dict(operation='ADD', object_type='STATED_POSITION', object_id='HYPOTHETICAL:HUMAN', statement='Fake')]
        for mutation in invalid:
            with self.subTest(mutation=mutation), self.assertRaises(SimulationError):
                self.sim.run(self.request([mutation]))

    def test_complete_execution_basis_is_version_pinned(self):
        request = self.request([withdraw('CUSTOMER-CALL')])
        for field in ('materiality_policy', 'authority_policy', 'execution_mapping', 'prior_state'):
            changed = copy.deepcopy(self.inputs)
            changed[field]['revision'] = 'Changed outside the display projection'
            with self.subTest(field=field), self.assertRaisesRegex(SimulationError, 'Refresh'):
                GraphSimulation(CASE_ID, self.sim.case_version, changed).run(request)

    def test_manual_request_bounds_and_id_uniqueness(self):
        for mutations in ([], [withdraw('CUSTOMER-CALL')] * 51, [change('CUSTOMER-CALL', 'statement', 'x' * 4001)]):
            with self.subTest(mutations=str(mutations)[:50]), self.assertRaises(SimulationError):
                self.sim.run(self.request(mutations))

    def test_direct_live_engine_and_global_oracle_agree_for_support_cascades(self):
        # A pure support graph isolates the oracle from intentionally unsupported
        # financial fixture branches and unrelated stale model baselines.
        inputs = copy.deepcopy(self.inputs)
        graph = inputs['prior_state']['current_graph']
        graph['model_nodes'] = []
        graph['support_routes'][-1].pop('member_model_node_ids')
        mapping = {**self.mapping, 'model_nodes': [], 'formulas': [], 'directed_model_edges': []}
        for mutations in ([withdraw('CUSTOMER-CALL')], [withdraw('CUSTOMER-CALL'), withdraw('RENEWAL-RECORD')],
            [withdraw('INTERVIEW-PATH', 'SUPPORT_ROUTE'), withdraw('RECORD-PATH', 'SUPPORT_ROUTE')],
            [change('CUSTOMER-LOSS', 'usable', True), withdraw('RECORD-PATH', 'SUPPORT_ROUTE')]):
            oracle = compare_incremental_global(inputs['prior_state'], [self.sim.manual_event(mutations)], mapping, inputs['materiality_policy'], inputs['authority_policy'])
            self.assertTrue(oracle['equivalent'], oracle['comparisons'])


class GraphSimulationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.saved, self.events, self.inputs = graph_fixture()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = ScenarioStore(Path(self.temp.name) / 'scenarios.sqlite3')
        self.loads = []
        def load(case_id):
            self.loads.append(case_id); return copy.deepcopy(self.saved)
        def auth(case_id, actor_id, token):
            if (case_id, actor_id, token) != (CASE_ID, ACTOR['actorId'], 'TOKEN'):
                raise HTTPException(403, 'No case access')
            return ACTOR
        app = FastAPI()
        app.include_router(simulation_router(load, auth, lambda _: copy.deepcopy(self.events), lambda _: self.store, lambda _: copy.deepcopy(self.inputs)))
        self.client = ASGIClient(app); self.url = f'/api/v20/cases/{CASE_ID}/simulations'
        self.headers = {'x-panta-actor': ACTOR['actorId'], 'x-panta-session': 'TOKEN'}

    def snapshot(self):
        response = self.client.get(self.url, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json()['snapshot']

    def body(self):
        scope = self.snapshot()['graphSimulationScope']
        return dict(mode='graph', caseVersion=scope['caseVersion'], graphVersion=scope['version'], mutations=[withdraw('CUSTOMER-CALL')])

    def test_authenticated_manual_run_and_frozen_archive_replay(self):
        before = copy.deepcopy((self.saved, self.inputs, self.events))
        response = self.client.post(self.url, headers=self.headers, json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(before, (self.saved, self.inputs, self.events))
        archive = self.client.get(self.url + '/archive/' + result['id'], headers=self.headers).json()
        self.inputs['authority_policy']['revision'] = 'later'
        replay = GraphSimulation(CASE_ID, result['caseVersion'], archive['transitionInputs']).run(result['request'])
        self.assertEqual(replay, result)
        self.assertEqual(self.client.get(self.url + '/archive/' + result['id']).status_code, 403)

    def test_access_precedes_graph_state_and_event_loading(self):
        self.assertEqual(self.client.post(self.url, json={}).status_code, 403)
        self.assertEqual(self.client.get(self.url.replace(CASE_ID, 'OTHER'), headers=self.headers).status_code, 403)
        self.assertEqual(self.loads, [])

    def test_policy_change_and_split_projection_fail_closed(self):
        request = self.body()
        self.inputs['authority_policy']['revision'] = 'changed'
        self.assertEqual(self.client.post(self.url, headers=self.headers, json=request).status_code, 409)
        self.inputs['prior_state']['current_graph']['claims'][0]['statement'] = 'A new Current'
        self.assertIn('Refresh', self.snapshot()['graphSimulationUnavailable'])

    def test_caller_cannot_supply_policy_state_or_fabricate_event(self):
        request = self.body()
        for field in ('prior_state', 'mapping', 'authority_policy', 'event'):
            self.assertEqual(self.client.post(self.url, headers=self.headers, json={**request, field: {}}).status_code, 422)

    def test_general_event_automatic_preparation_and_evidence_pin(self):
        snapshot = self.snapshot()
        result = next(r for r in snapshot['graphSimulationScenarios'] if r['request']['eventId'] == 'EVENT-CUSTOMER-WITHDRAWAL')
        response = self.client.post(self.url, headers=self.headers, json=result['request'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), result)
        self.events[-1]['label'] = 'Revised recorded evidence'
        self.assertEqual(self.client.post(self.url, headers=self.headers, json=result['request']).status_code, 409)
        self.assertEqual(self.store.read(CASE_ID, result['id'])['result'], result)

    def test_candidate_and_other_case_events_are_not_simulated(self):
        self.events[-1]['institutional_state'] = 'CANDIDATE'
        self.events[0]['case_id'] = 'OTHER'
        self.assertEqual(self.snapshot()['graphSimulationScenarios'], [])

    def test_production_router_loads_real_bundle_through_authenticated_bootstrap(self):
        import app.v20_router as runtime
        from app.simulation_routes import production_simulation_router
        case, graph, mapping = self.saved
        with patch.object(runtime, '_case_vault_dir', return_value=Path(self.temp.name)), \
             patch.object(runtime, '_pipeline_out_for_case', return_value=Path(self.temp.name)), \
             patch.object(runtime, '_build_projection', return_value={'deal': {'current_graph': graph}}), \
             patch('app.output_case.project_output_case', return_value=case), \
             patch.object(runtime, '_authenticated_principal') as authenticated, \
             patch('backend.dynamics.runtime.ledger_store.read_ledger', return_value=[]), \
             patch.dict('os.environ', {'PANTA_SIMULATION_DB': str(self.store.path)}):
            (Path(self.temp.name) / 'deal.md').write_text('Synthetic case')
            from backend.dynamics.service import REQUIRED_INPUTS
            for key, filename in REQUIRED_INPUTS.items():
                (Path(self.temp.name) / filename).write_text(json.dumps(self.inputs[key]))
            (Path(self.temp.name) / 'runtime_state.json').write_text(json.dumps(self.inputs['prior_state']))
            app = FastAPI(); app.include_router(production_simulation_router()); client = ASGIClient(app)
            files_before = {p.name: p.read_bytes() for p in Path(self.temp.name).glob('*.json')}
            scope = client.get(self.url, headers=self.headers).json()['snapshot']['graphSimulationScope']
            response = client.post(self.url, headers=self.headers, json={**self.body(), 'graphVersion': scope['version']})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(authenticated.called)
            self.assertEqual(files_before, {p.name: p.read_bytes() for p in Path(self.temp.name).glob('*.json')})


if __name__ == '__main__':
    unittest.main()
