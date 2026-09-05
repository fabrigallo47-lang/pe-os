"""Connected case -> memo -> review -> approval -> original citation/export acceptance."""
import asyncio
import copy
import json
import logging
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'backend/dynamics')]
import httpx
from fastapi import FastAPI, HTTPException
from app.live_outputs import OutputStore, compile_blocks, digest
from app.output_routes import output_router
from app.output_case import project_output_case
from app.memo_writer import MemoWriter
from ic_memo_fixture import ACTOR, build_memo_cases, simulated_writer


class OutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory()
        cls.cases = build_memo_cases(Path(cls.fixture_temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        logging.getLogger('httpx').setLevel(logging.WARNING)
        self.temp = tempfile.TemporaryDirectory()
        self.store = OutputStore(Path(self.temp.name) / 'outputs.db')
        self.case = copy.deepcopy(self.cases[0])
        self.actor = copy.deepcopy(ACTOR)
        self.writer = simulated_writer
        self.app = FastAPI()
        def auth(case_id, actor, token):
            if token != 'test-session': raise HTTPException(401, 'Session required')
            if case_id != 'MEMO-TEST' or actor != ACTOR['actorId']: raise HTTPException(403, 'Wrong principal or case')
            return self.actor
        writer = lambda b: self.writer(b)
        writer.redraft_with_profile = lambda b, profile: self.writer(b)
        self.app.include_router(output_router(lambda _: copy.deepcopy(self.case), auth, lambda _: self.store, writer))
        self.headers = {'X-Panta-Actor': ACTOR['actorId'], 'X-Panta-Session': 'test-session'}

    def tearDown(self): self.temp.cleanup()

    def request(self, method='GET', suffix='', **kwargs):
        async def call():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver') as client:
                return await client.request(method, '/api/v20/cases/MEMO-TEST/outputs' + suffix, headers=kwargs.pop('headers', self.headers), **kwargs)
        return asyncio.run(call())

    def command(self, operation, *, status=200, payload=None, kind='IC_MEMO', **fields):
        latest = self.store.latest('MEMO-TEST')
        previous = next((r for r in latest if r['artifact']['type'] == kind), None)
        body = payload or dict(actorId=ACTOR['actorId'], requestId=str(uuid.uuid4()), caseVersion=self.case['caseVersion'],
            expectedRevision=previous['revisionId'] if previous else None,
            action=dict(type=operation, artifactType=kind, artifactId=previous['artifact']['id'] if previous else None, **fields))
        response = self.request('POST', '/commands', json=body)
        self.assertEqual(response.status_code, status, response.text[:1000])
        return response.json()

    def create(self, kind='IC_MEMO'):
        return self.command('CREATE_ARTIFACT', kind=kind)['snapshot']

    def accept_all(self, kind='IC_MEMO'):
        snapshot = self.request().json()['snapshot']
        artifact = next(a for a in snapshot['artifacts'] if a['type'] == kind)
        for block in snapshot['artifactBlocks']:
            if block['artifactId'] == artifact['id'] and block.get('suggestion'):
                self.command('ACCEPT_ARTIFACT_SUGGESTION', kind=kind, blockId=block['id'])

    def test_compile_numbers_open_matters_and_human_attribution(self):
        before = copy.deepcopy(self.case)
        snapshot = self.create()
        self.assertEqual(self.case, before)
        text = '\n'.join(b['text'] for b in snapshot['artifactBlocks'])
        self.assertIn('EUR 5 million', text)
        self.assertIn('verification remains outstanding', text)
        self.assertIn('Test partner', text)
        self.assertTrue(all(b['boundObjectIds'] and b['frozenBasis'] for b in snapshot['artifactBlocks']))
        self.assertEqual(snapshot['artifacts'][0]['approvalStatus'], 'DRAFT')
        restarted = OutputStore(self.store.path)
        self.assertEqual(restarted.project(self.case), self.store.project(self.case))

    def test_no_candidate_or_unattributed_or_old_decision_laundering(self):
        self.case['caseReadings'][0]['institutionalState'] = 'CANDIDATE'
        self.case['quantities'][0]['institutionalState'] = 'CANDIDATE'
        self.case['humanPositions'][0]['authorActorId'] = 'UNKNOWN'
        self.case['decisions'] = [dict(id='OLD', caseVersion='older', rationale='Approve immediately')]
        snapshot = self.create()
        text = '\n'.join(b['text'] for b in snapshot['artifactBlocks'])
        self.assertNotIn('EUR 5 million', text)
        self.assertNotIn('Approve immediately', text)
        self.assertNotIn('Test partner (', text)
        self.assertIn('no current case reading', text)

    def test_stale_review_preserves_human_edit_then_reapproves_exact_version(self):
        snapshot = self.create()
        block = next(b for b in snapshot['artifactBlocks'] if b['boundObjectIds'] == ['READING-ROUND'])
        self.command('UPDATE_ARTIFACT_BLOCK', blockId=block['id'], text='Reviewer wording: proposed proceeds are EUR 5 million before fees.')
        approved = self.command('APPROVE_ARTIFACT')['snapshot']['artifacts'][0]
        self.assertEqual(approved['approvalStatus'], 'APPROVED')
        self.case = copy.deepcopy(self.cases[1])
        self.assertEqual(self.request(suffix=f"/{approved['id']}/export", params={'revision': approved['revisionId']}).status_code, 409)
        stale = self.request().json()['snapshot']
        self.assertEqual(stale['artifacts'][0]['approvalStatus'], 'DRAFT')
        self.assertGreater(stale['artifacts'][0]['pendingCaseChangeCount'], 0)
        synced = self.command('SYNC_ARTIFACT')['snapshot']
        proposal = next(b for b in synced['artifactBlocks'] if b['id'] == block['id'])
        self.assertIn('Reviewer wording', proposal['text'])
        self.assertIn('EUR 6 million', proposal['suggestion']['suggestedText'])
        self.command('APPROVE_ARTIFACT', status=409)
        self.accept_all()
        new = self.command('APPROVE_ARTIFACT')['snapshot']['artifacts'][0]
        self.assertEqual(new['approvalStatus'], 'APPROVED')
        self.assertNotEqual(new['revisionId'], approved['revisionId'])
        response = self.request(suffix=f"/{new['id']}/export", params={'revision': new['revisionId']})
        self.assertEqual(response.status_code, 200)
        self.assertIn('EUR 6 million', response.text)
        self.assertIn('source_version_id=sha256', response.text)
        self.assertIn('Open cited original', response.text)
        self.assertNotIn('<script', response.text)

    def test_dismiss_does_not_mark_old_text_current(self):
        self.create(); self.case = copy.deepcopy(self.cases[1])
        result = self.command('SYNC_ARTIFACT')['snapshot']
        block = next(b for b in result['artifactBlocks'] if b.get('suggestion'))
        self.command('DISMISS_ARTIFACT_SUGGESTION', blockId=block['id'])
        self.assertEqual(next(b for b in self.store.project(self.case)['artifactBlocks'] if b['id'] == block['id'])['freshnessStatus'], 'STALE')
        self.command('APPROVE_ARTIFACT', status=409)

    def test_missing_dependency_blocks_approval_and_missing_never_becomes_zero(self):
        self.case['quantities'][0]['value'] = None
        snapshot = self.create()
        self.assertIn('Not established', next(b['text'] for b in snapshot['artifactBlocks'] if b['title'] == 'Financial basis'))
        self.case['claims'] = []
        self.assertTrue(any(b['freshnessStatus'] == 'MISSING_BASIS' for b in self.store.project(self.case)['artifactBlocks']))
        self.command('APPROVE_ARTIFACT', status=409)

    def test_stale_source_flag_blocks_approval_even_unchanged_bytes(self):
        self.case['caseReadings'][0]['freshnessStatus'] = 'STALE'
        self.create(); self.command('APPROVE_ARTIFACT', status=409)

    def test_add_remove_membership_is_reviewed(self):
        self.create()
        self.case['unknowns'][0]['status'] = 'RESOLVED'
        self.case['questions'].append(dict(id='NEW-Q', name='A newly opened question'))
        result = self.command('SYNC_ARTIFACT')['snapshot']
        self.assertTrue(any(b.get('suggestion', {}).get('remove') for b in result['artifactBlocks']))
        self.assertTrue(any(b.get('suggestion', {}).get('signal') == 'New in the case' for b in result['artifactBlocks']))
        self.accept_all()
        self.command('APPROVE_ARTIFACT')

    def test_proposal_changed_again_cannot_be_accepted(self):
        self.create(); self.case = copy.deepcopy(self.cases[1])
        result = self.command('SYNC_ARTIFACT')['snapshot']
        block = next(b for b in result['artifactBlocks'] if b.get('suggestion'))
        self.case = copy.deepcopy(self.cases[0])
        self.command('ACCEPT_ARTIFACT_SUGGESTION', blockId=block['id'], status=409)

    def test_authenticated_role_and_case_isolation(self):
        self.assertEqual(self.request(headers={}).status_code, 401)
        self.assertEqual(self.request(headers={**self.headers, 'X-Panta-Actor': 'forged'}).status_code, 403)
        self.create()
        self.actor['entitlements'] = ['READ_CASE', 'EDIT_ARTIFACT']
        self.command('APPROVE_ARTIFACT', status=403)
        record = self.store.latest('MEMO-TEST')[0]
        body = dict(actorId='forged', requestId='forged', caseVersion=self.case['caseVersion'], expectedRevision=record['revisionId'],
            entitlements=['APPROVE_ARTIFACT'], snapshot={'caseVersion':'forged'}, action={'type':'APPROVE_ARTIFACT','artifactId':record['artifact']['id']})
        self.command('', payload=body, status=403)
        other = copy.deepcopy(self.case); other['caseRef']['id'] = 'OTHER'
        self.assertEqual(self.store.project(other)['artifacts'], [])

    def test_idempotency_and_optimistic_conflict(self):
        body = dict(actorId=ACTOR['actorId'], requestId='once', caseVersion=self.case['caseVersion'], action={'type':'CREATE_ARTIFACT','artifactType':'IC_MEMO'})
        self.command('', payload=body); self.command('', payload=body)
        self.assertEqual(len(self.store.latest('MEMO-TEST')), 1)
        body['action']['artifactType'] = 'DECK'; self.command('', payload=body, status=409)
        prior = self.store.latest('MEMO-TEST')[0]
        self.command('APPROVE_ARTIFACT')
        edit = dict(actorId=ACTOR['actorId'], requestId='stale-edit', caseVersion=self.case['caseVersion'], expectedRevision=prior['revisionId'], action=dict(type='SYNC_ARTIFACT',artifactId=prior['artifact']['id']))
        self.command('', payload=edit, status=409)

    def test_concurrent_editors_one_revision_wins(self):
        self.create(); prior = self.store.latest('MEMO-TEST')[0]
        def edit(number):
            try:
                self.store.mutate(self.case, ACTOR, dict(actorId=ACTOR['actorId'], requestId=str(number), caseVersion=self.case['caseVersion'], expectedRevision=prior['revisionId'], action=dict(type='UPDATE_ARTIFACT_BLOCK', artifactId=prior['artifact']['id'], blockId=prior['blocks'][0]['id'], text=f'Editor {number}')))
                return 200
            except HTTPException as exc: return exc.status_code
        with ThreadPoolExecutor(2) as pool: self.assertEqual(sorted(pool.map(edit, [1,2])), [200,409])

    def test_redraft_is_pending_and_never_rewrites_human_position(self):
        self.create(); view = copy.deepcopy(self.case['humanPositions'])
        result = self.command('REDRAFT_ARTIFACT')['snapshot']
        self.assertTrue(any(b.get('suggestion') for b in result['artifactBlocks']))
        self.assertFalse(next(b for b in result['artifactBlocks'] if b['title'] == 'Recorded views').get('suggestion'))
        self.command('APPROVE_ARTIFACT', status=409)
        self.accept_all(); self.command('APPROVE_ARTIFACT')
        self.assertEqual(view, self.case['humanPositions'])
        locked = next(b for b in result['artifactBlocks'] if b['editorialLocked'])
        self.command('UPDATE_ARTIFACT_BLOCK', blockId=locked['id'], text='Fake view', status=409)

    def test_bad_model_numbers_or_ids_roll_back(self):
        self.create(); prior = self.store.latest('MEMO-TEST')[0]
        self.writer = lambda b: {item['id']: item['text'].replace('EUR 5', 'EUR 500') for item in b}
        self.command('REDRAFT_ARTIFACT', status=502)
        self.assertEqual(prior, self.store.latest('MEMO-TEST')[0])

        self.writer = lambda _: {'unknown-id':'Forged text'}
        self.command('REDRAFT_ARTIFACT', status=502)
        self.assertEqual(prior, self.store.latest('MEMO-TEST')[0])

    def test_writing_model_does_not_lock_other_editors_or_overwrite_them(self):
        self.create(); prior = self.store.latest('MEMO-TEST')[0]
        def racing_writer(blocks):
            self.store.mutate(self.case, ACTOR, dict(actorId=ACTOR['actorId'], requestId='other-editor', caseVersion=self.case['caseVersion'], expectedRevision=prior['revisionId'],
                action=dict(type='UPDATE_ARTIFACT_BLOCK', artifactId=prior['artifact']['id'], blockId=blocks[0]['id'], text='Another reviewer saved this passage.')))
            return simulated_writer(blocks)
        self.writer = racing_writer
        self.command('REDRAFT_ARTIFACT', status=409)
        self.assertEqual(self.store.latest('MEMO-TEST')[0]['blocks'][0]['text'], 'Another reviewer saved this passage.')

    def test_malformed_action_and_unversioned_claim_fail_closed(self):
        body = dict(actorId=ACTOR['actorId'], requestId='malformed', caseVersion=self.case['caseVersion'], action=['CREATE_ARTIFACT'])
        self.command('', payload=body, status=422)
        self.case['claims'][0]['sourceVersionId'] = 'legacy-unverified'
        snapshot = self.create()
        self.assertTrue(any(b['freshnessStatus'] == 'MISSING_BASIS' for b in snapshot['artifactBlocks']))
        self.command('APPROVE_ARTIFACT', status=409)

    def test_production_router_uses_issued_session_server_role_and_persistent_store(self):
        import os
        import app.v20_router as runtime
        from app.output_case import production_output_router
        root = Path(self.temp.name)
        case_dir = root / 'deals' / 'MEMO-TEST'; case_dir.mkdir(parents=True)
        (case_dir / 'deal.md').write_text('# Test case')
        (case_dir / 'editorial_fund.json').write_text(json.dumps({'id': 'TEST-PRODUCTION-FUND', 'name': 'Synthetic production fund'}))
        projection = {'actor_directory':[{'id':ACTOR['actorId'],'name':'Test partner','role':'DEAL_PARTNER'}],
            'deal':{'case_id':'MEMO-TEST','entity':'Test','as_of_state_id':'S','as_of_date':'2026-01-01','question_spine':[{'id':'Q','label':'Open question'}]}}
        token, _ = runtime._issue_authenticated_session('MEMO-TEST', ACTOR['actorId'])
        self.headers['X-Panta-Session'] = token
        with patch.object(runtime, 'VAULT', root), patch.object(runtime, '_build_projection', return_value=projection), patch.dict(os.environ, {'PANTA_OUTPUT_DB':str(self.store.path), 'OPENAI_API_KEY':'', 'VERCEL':''}):
            self.app = FastAPI(); self.app.include_router(production_output_router())
            response = self.request()
            self.assertEqual(response.status_code, 200)
            self.case = response.json()['snapshot']
            self.assertIn('APPROVE_ARTIFACT', response.json()['actor']['entitlements'])
            self.assertIn('EDIT_EDITORIAL_PROFILE', response.json()['actor']['entitlements'])
            self.assertEqual(self.case['editorialContext']['profile']['fund']['id'], 'TEST-PRODUCTION-FUND')
            self.assertTrue(self.case['editorialContext']['configurable'])
            self.assertFalse(self.case['outputCapabilities']['aiRedraftAvailable'])
            self.create(); self.command('REDRAFT_ARTIFACT', status=503)
            self.command('APPROVE_ARTIFACT')
            self.app = FastAPI(); self.app.include_router(production_output_router())
            self.assertEqual(self.request().json()['snapshot']['artifacts'][0]['approvalStatus'], 'APPROVED')
            other_token, _ = runtime._issue_authenticated_session('OTHER', ACTOR['actorId'])
            self.assertEqual(self.request(headers={**self.headers, 'X-Panta-Session':other_token}).status_code, 403)
            projection['actor_directory'][0]['role'] = 'WORKSTREAM_REVIEWER'
            self.command('APPROVE_ARTIFACT', status=403)
            self.assertNotIn('EDIT_EDITORIAL_PROFILE', self.request().json()['actor']['entitlements'])

    def test_all_outputs_share_approval_and_export_cycle(self):
        for kind in ['IC_MEMO','MODEL','DECISION_PACK','DECK','TRACKER']:
            self.create(kind)
            approved = self.command('APPROVE_ARTIFACT', kind=kind)['snapshot']
            artifact = next(a for a in approved['artifacts'] if a['type'] == kind)
            for fmt in ['html','json'] + (['csv'] if kind in {'MODEL','TRACKER'} else []):
                response = self.request(suffix=f"/{artifact['id']}/export", params={'revision':artifact['revisionId'],'format':fmt})
                self.assertEqual(response.status_code, 200, response.text[:200])
                if fmt == 'json':
                    saved = response.json()
                    self.assertEqual(saved['approval']['contentHash'], digest(saved['blocks']))
                    self.assertTrue(all('_basis' in b for b in saved['blocks']))
            self.case['unknowns'][0]['title'] += ' updated'
            if kind != 'MODEL': self.assertNotEqual(self.store.project(self.case)['artifacts'][-1]['approvalStatus'], 'APPROVED')

    def test_escaped_export_and_csv_formula_injection(self):
        snapshot = self.create('TRACKER'); block = snapshot['artifactBlocks'][0]
        self.command('UPDATE_ARTIFACT_BLOCK', kind='TRACKER', blockId=block['id'], text='=HYPERLINK("bad") <script>bad</script>')
        artifact = self.command('APPROVE_ARTIFACT', kind='TRACKER')['snapshot']['artifacts'][0]
        html = self.request(suffix=f"/{artifact['id']}/export", params={'revision':artifact['revisionId']}).text
        self.assertIn('&lt;script&gt;', html); self.assertNotIn('<script>', html)
        csv = self.request(suffix=f"/{artifact['id']}/export", params={'revision':artifact['revisionId'],'format':'csv'}).text
        self.assertIn("'=HYPERLINK", csv)

    def test_projection_excludes_unadmitted_extraction_and_synthetic_human_views(self):
        projection = {'actor_directory': [], 'deal': {'case_id':'P','entity':'Test','as_of_state_id':'S','as_of_date':'2026-01-01',
            'claims':[{'claim_id':'CANDIDATE','statement':'Do not compile'}], 'positions':[], 'question_spine':[{'id':'Q','label':'Open question'}],
            'current_graph':{'case_positions':[{'position_id':'NOT-HUMAN','statement':'Computed text'}], 'model_nodes':[{'model_node_id':'N','name':'Value','value':5,'period':'FY2026','perimeter':'Group'}]}}}
        case = project_output_case(projection)
        self.assertFalse(case['claims']); self.assertFalse(case['humanPositions'])
        self.assertEqual(case['quantities'][0]['value'], 5)
        self.assertEqual(compile_blocks(case,'IC_MEMO','A')[0]['boundObjectIds'], ['Q'])
        projection['deal']['current_graph']['model_nodes'][0]['value']=6
        self.assertNotEqual(project_output_case(projection)['caseVersion'], case['caseVersion'])

    def test_responses_api_configuration_and_typed_output_parsing(self):
        blocks = [{'id':'A','text':'Proposed EUR 5 million.'}]
        response = httpx.Response(200, request=httpx.Request('POST','https://api.openai.com/v1/responses'), json={
            'status':'completed', 'output':[{'type':'reasoning'}, {'type':'message','content':[{'type':'output_text','text':json.dumps({'passages':[{'id':'A','text':'EUR 5 million proposed.'}]})}]}]})
        with patch('app.memo_writer.httpx.post', return_value=response) as call:
            result = MemoWriter('test-key', 'gpt-5.6-sol')(blocks)
            self.assertEqual(result['A'], 'EUR 5 million proposed.')
            body = call.call_args.kwargs['json']
            self.assertFalse(body['store']); self.assertEqual(body['model'], 'gpt-5.6-sol')
            self.assertTrue(body['text']['format']['strict'])


if __name__ == '__main__': unittest.main()
