import copy
import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT, ROOT / 'tests', ROOT / 'backend' / 'dynamics'):
    sys.path.insert(0, str(path))

from fastapi import FastAPI, HTTPException
import httpx
from backend.dynamics.runtime.simulation import SimulationError, SimulationModel
from app.simulation_routes import simulation_router
from simulation_fixture import ACTOR, CASE_ID, fixture


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.case, self.graph, self.mapping = fixture()

    def model(self):
        return SimulationModel(CASE_ID, self.case['caseVersion'], self.graph, self.mapping)

    def request(self, value='90', input_id='REVENUE', model=None):
        model = model or self.model()
        return dict(optionId=input_id, originObjectId=input_id, value=value,
                    scopeVersion=model.version, caseVersion=model.case_version)

    def test_scope_precedes_calculation_and_declares_limits(self):
        scope = self.model().scope()
        self.assertEqual(scope['modelNodeCount'], 7)
        self.assertEqual(scope['computableCount'], 6)
        self.assertEqual([x['objectId'] for x in scope['limits']], ['IRR'])
        revenue = next(o for o in scope['options'] if o['id'] == 'REVENUE')
        self.assertEqual(revenue['scope']['limitedObjectIds'], ['IRR'])

    def test_shock_traverses_declared_formulas_and_retains_held_survivor(self):
        model = self.model()
        result = model.run(self.request(model=model))
        by_id = {x['objectId']: x for x in result['effects']}
        self.assertEqual(Decimal(by_id['PROFIT']['magnitude']['after']), 30)
        self.assertAlmostEqual(float(by_id['LEVERAGE']['magnitude']['after']), 80 / 30)
        self.assertEqual(by_id['CAP']['state'], 'HOLDS')
        self.assertEqual(result['effects'][0]['objectId'], 'REVENUE')
        self.assertNotIn('COST', by_id)
        self.assertNotIn('DEBT', by_id)
        self.assertEqual(result['coverage'], dict(examinedCount=5, changedCount=3, heldCount=1, unmappedCount=1))

    def test_no_state_or_mapping_or_human_record_is_mutated(self):
        before = copy.deepcopy((self.case, self.graph, self.mapping))
        model = self.model()
        request = self.request(model=model)
        self.assertEqual(model.run(request), model.run(request))
        self.assertEqual(before, (self.case, self.graph, self.mapping))
        self.assertEqual(model.run(self.request('100', model=model))['coverage']['changedCount'], 0)

    def test_zero_denominator_stops_only_its_branch(self):
        result = self.model().run(self.request('60'))
        self.assertIn('LEVERAGE', [x['objectId'] for x in result['limits']])
        self.assertIn('PROFIT', [x['objectId'] for x in result['effects']])
        self.assertNotIn('LEVERAGE', [x['objectId'] for x in result['effects']])

    def test_case_and_model_version_changes_reject_old_request(self):
        old = self.request()
        self.mapping['formulas'][0]['description'] = 'New formula record'
        with self.assertRaisesRegex(SimulationError, 'Refresh'):
            self.model().run(old)
        self.case['caseVersion'] = 'SIM-CASE-2'
        with self.assertRaisesRegex(SimulationError, 'Refresh'):
            self.model().run(old)

    def test_candidates_other_nodes_and_computed_outputs_cannot_be_overridden(self):
        self.graph['model_nodes'][0]['institutional_state'] = 'CANDIDATE'
        model = self.model()
        self.assertNotIn('REVENUE', model.nodes)
        for key in ('REVENUE', 'OTHER-CASE', 'PROFIT'):
            with self.subTest(key=key), self.assertRaises(SimulationError):
                model.run(self.request(input_id=key, model=model))

    def test_candidate_formula_is_not_traversed(self):
        self.mapping['formulas'][1]['institutional_state'] = 'CANDIDATE'
        model = self.model()
        self.assertEqual(model.closure('REVENUE'), {'REVENUE'})
        self.assertFalse(next(o for o in model.scope()['options'] if o['id'] == 'REVENUE')['enabled'])

    def test_initial_values_do_not_replace_missing_current(self):
        self.graph['model_nodes'][0].pop('value')
        model = self.model()
        self.assertNotIn('REVENUE', model.baseline)
        self.assertFalse(next(o for o in model.scope()['options'] if o['id'] == 'REVENUE')['enabled'])

    def test_semantic_scope_and_missing_mapping_are_visible_stops(self):
        self.graph['model_nodes'][0]['period'] = None
        self.mapping['model_nodes'] = self.mapping['model_nodes'][1:]
        model = self.model()
        self.assertIn('REVENUE', [x['objectId'] for x in model.scope()['limits']])
        self.assertNotIn('PROFIT', model.baseline)

    def test_inconsistent_baseline_does_not_silently_repair_current(self):
        self.graph['model_nodes'][3]['value'] = 500
        model = self.model()
        self.assertIn('reproduce', model.errors['PROFIT'])
        self.assertNotIn('LEVERAGE', model.baseline)

    def test_compiler_coverage_stops_are_preserved(self):
        self.mapping['coverage_limits'] = [dict(scope_ids=['PROFIT'], reason='The workbook has an unresolved external input.'),
                                           dict(scope_ids=['UNMAPPED-AREA'], reason='The operating forecast is incomplete.')]
        model = self.model()
        self.assertNotIn('PROFIT', model.baseline)
        self.assertIn('external input', model.errors['PROFIT'])
        self.assertIn('The operating forecast is incomplete.', model.scope()['notes'])

    def test_operand_identity_must_be_explicit_and_complete(self):
        for mutate in (lambda f: f.pop('operand_bindings'),
                       lambda f: f['operand_bindings'].update(revenue='OTHER-CASE'),
                       lambda f: f.update(fixture_parameters={'revenue': 999})):
            with self.subTest(mutate=mutate):
                self.case, self.graph, self.mapping = fixture()
                mutate(self.mapping['formulas'][1])
                self.assertNotIn('PROFIT', self.model().baseline)

    def test_circular_mapping_remains_a_limit(self):
        self.mapping['formulas'][1]['input_ids'] = ['CAP']
        self.mapping['formulas'][1]['operand_bindings'] = {'cap': 'CAP'}
        self.mapping['formulas'][1]['expression_or_function_ref'] = 'cap + 10'
        model = self.model()
        self.assertNotIn('PROFIT', model.baseline)
        self.assertIn('circular', model.errors['PROFIT'])

    def test_nonfinite_or_unbounded_requests_are_refused(self):
        for value in (True, None, '', 'NaN', 'Infinity', '1e999', '1e-999999999', [], {}):
            with self.subTest(value=value), self.assertRaises(SimulationError):
                self.model().run(self.request(value))

    def test_unsupported_expressions_never_execute(self):
        for expression in ('revenue ** 99999999', "__import__('os').getcwd()", 'revenue[0]', 'revenue + unknown'):
            with self.subTest(expression=expression):
                self.case, self.graph, self.mapping = fixture()
                self.mapping['formulas'][1]['expression_or_function_ref'] = expression
                self.assertNotIn('PROFIT', self.model().baseline)

    def test_duplicate_formula_ownership_is_rejected(self):
        self.mapping['formulas'].append({**self.mapping['formulas'][1], 'formula_id': 'DUPLICATE'})
        with self.assertRaisesRegex(SimulationError, 'More than one'):
            self.model()

    def test_excel_compiler_output_runs_without_transcribing_the_formula(self):
        from tools.formula_compiler import compile_formulas
        source = dict(workbook='synthetic.xlsx', cells={
            'INPUTS!A1': dict(kind='number', value=100),
            'INPUTS!A2': dict(kind='number', value=60),
            'MODEL!B1': dict(kind='formula', value='=Inputs!A1-Inputs!A2', evaluated_value=40, precedents=['INPUTS!A1', 'INPUTS!A2'])})
        compiled = compile_formulas(source, {'INPUTS!A1': 'REVENUE', 'INPUTS!A2': 'COST', 'MODEL!B1': 'PROFIT'})
        profit = next(f for f in compiled['formulas'] if f['output_id'] == 'PROFIT')
        self.mapping['formulas'][1] = profit
        result = self.model().run(self.request('90'))
        self.assertEqual(Decimal(next(e for e in result['effects'] if e['objectId'] == 'PROFIT')['magnitude']['after']), 30)


class SimulationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.saved = fixture()
        self.loaded = []
        def load(case_id):
            self.loaded.append(case_id)
            return copy.deepcopy(self.saved)
        def auth(case_id, actor_id, token):
            if (case_id, actor_id, token) != (CASE_ID, ACTOR['actorId'], 'TEST-TOKEN'):
                raise HTTPException(403, 'Invalid case session.')
            return ACTOR
        app = FastAPI()
        app.include_router(simulation_router(load, auth))
        self.client = ASGIClient(app)
        self.url = f'/api/v20/cases/{CASE_ID}/simulations'
        self.headers = {'X-Panta-Actor': ACTOR['actorId'], 'X-Panta-Session': 'TEST-TOKEN'}

    def payload(self):
        snapshot = self.client.get(self.url, headers=self.headers).json()['snapshot']
        return dict(optionId='REVENUE', originObjectId='REVENUE', value='90',
                    scopeVersion=snapshot['simulationScope']['version'], caseVersion=snapshot['caseVersion'])

    def test_authenticated_read_compute_and_no_mutation(self):
        before = copy.deepcopy(self.saved)
        response = self.client.post(self.url, headers=self.headers, json=self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['liveCaseUnchanged'])
        self.assertEqual(before, self.saved)

    def test_auth_precedes_case_loading(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.loaded, [])
        self.assertEqual(self.client.get(self.url.replace(CASE_ID, 'OTHER'), headers=self.headers).status_code, 403)

    def test_caller_cannot_supply_a_case_or_formulas(self):
        self.assertEqual(self.client.post(self.url, headers=self.headers, json={**self.payload(), 'mapping': {}}).status_code, 422)

    def test_stale_request_is_a_conflict(self):
        body = self.payload()
        self.saved[1]['model_nodes'][0]['value'] = 120
        self.assertEqual(self.client.post(self.url, headers=self.headers, json=body).status_code, 409)


class ASGIClient:
    def __init__(self, app):
        self.app = app

    def request(self, method, url, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test') as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)


if __name__ == '__main__':
    unittest.main()
