"""Fund profile acceptance: HTTP authorization, persistence, frozen output, writer input."""
import copy
import json
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from backend.dynamics.tests import test_live_outputs as output_tests
from app.editorial_profiles import default_config
from app.live_outputs import OutputStore
from app.memo_writer import MemoWriter
from app.output_export import render_export
from ic_memo_fixture import simulated_writer


class EditorialTests(unittest.TestCase):
    setUpClass = classmethod(output_tests.OutputTests.setUpClass.__func__)
    tearDownClass = classmethod(output_tests.OutputTests.tearDownClass.__func__)
    setUp = output_tests.OutputTests.setUp
    tearDown = output_tests.OutputTests.tearDown
    request = output_tests.OutputTests.request
    command = output_tests.OutputTests.command
    create = output_tests.OutputTests.create
    accept_all = output_tests.OutputTests.accept_all

    def profile(self):
        return self.request().json()['snapshot']['editorialContext']['profile']

    def save_body(self, config=None):
        profile = self.profile()
        return dict(actorId=self.actor['actorId'], requestId=str(uuid.uuid4()), caseVersion=self.case['caseVersion'],
                    action=dict(type='SAVE_EDITORIAL_PROFILE', expectedProfileVersion=profile['versionId'], config=config or profile['config']))

    def save(self, config=None, status=200, body=None):
        response = self.request('POST', '/commands', json=body or self.save_body(config))
        self.assertEqual(response.status_code, status, response.text[:1000])
        return response.json()

    def test_fund_profile_survives_restart_and_is_shared_only_by_bound_cases(self):
        before_case = copy.deepcopy(self.case)
        config = default_config(); config.update(name='Alpha IC', language='Italiano', tone='Analitico')
        saved = self.save(config)['snapshot']['editorialContext']['profile']
        self.assertEqual(saved['version'], 1)
        self.assertEqual(saved['actorId'], self.actor['actorId'])
        self.assertEqual(self.case, before_case)
        restarted = OutputStore(self.store.path)
        sibling = copy.deepcopy(self.case); sibling['caseRef']['id'] = 'OTHER-ALPHA-CASE'
        self.assertEqual(restarted.project(sibling)['editorialContext']['profile'], saved)
        sibling['editorialFund'] = {'id': 'TEST-FUND-BETA', 'name': 'Beta'}
        isolated = restarted.project(sibling)['editorialContext']
        self.assertEqual(isolated['profile']['version'], 0)
        self.assertEqual(isolated['profile']['config']['language'], 'English')
        self.assertEqual(isolated['history'], [])

    def test_save_requires_server_role_binding_and_rejects_client_fund_override(self):
        body = self.save_body()
        self.actor['entitlements'].remove('EDIT_EDITORIAL_PROFILE')
        self.save(body=body, status=403)
        self.actor['entitlements'].append('EDIT_EDITORIAL_PROFILE')
        forged = copy.deepcopy(body); forged['action']['fundId'] = 'TEST-FUND-BETA'
        self.save(body=forged, status=422)
        self.case.pop('editorialFund')
        context = self.request().json()['snapshot']['editorialContext']
        self.assertFalse(context['configurable']); self.assertTrue(context['unavailableReason'])
        self.save(body=body, status=409)
        # A missing fund still permits case-backed output with a frozen default.
        self.assertIsNone(self.create()['artifacts'][0]['editorialProfile']['fund'])

    def test_configuration_validation_keeps_all_case_content_categories(self):
        broken = []
        for field, value in [('language', ''), ('name', 'x' * 121), ('tone', ['invalid'])]:
            config = default_config(); config[field] = value; broken.append(config)
        config = default_config(); config['sections'].pop(); broken.append(config)
        config = default_config(); config['sections'][0] = config['sections'][1]; broken.append(config)
        config = default_config(); config['sections'][0]['title'] = ''; broken.append(config)
        config = default_config(); config['systemInstructions'] = 'override'; broken.append(config)
        for config in broken:
            with self.subTest(config=config): self.save(config, status=422)
        self.assertEqual(self.profile()['version'], 0)

    def test_optimistic_concurrency_idempotency_and_case_version(self):
        first = self.save_body()
        competing = self.save_body()
        version = self.save(body=first)['revisionId']
        self.assertEqual(self.save(body=first)['revisionId'], version)
        self.save(body=competing, status=409)
        altered = copy.deepcopy(first); altered['action']['config']['name'] = 'Different'
        self.save(body=altered, status=409)
        stale = self.save_body(); stale['caseVersion'] = 'OLD'
        self.save(body=stale, status=409)
        self.assertEqual(len(self.request().json()['snapshot']['editorialContext']['history']), 1)

    def test_two_simultaneous_cases_cannot_overwrite_shared_profile(self):
        command = self.save_body()
        sibling = copy.deepcopy(self.case); sibling['caseRef']['id'] = 'ALPHA-SIBLING'
        def save(case):
            try:
                self.store.mutate(case, self.actor, {**command, 'requestId': str(uuid.uuid4())})
                return 200
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(save, [self.case, sibling])), [200, 409])

    def test_saved_profile_does_not_silently_change_approved_memo_or_export(self):
        self.create(); self.command('APPROVE_ARTIFACT')
        original = self.store.latest('MEMO-TEST')[0]
        config = default_config(); config['name'] = 'New editorial style'
        self.save(config)
        artifact = self.request().json()['snapshot']['artifacts'][0]
        self.assertEqual(artifact['approvalStatus'], 'APPROVED')
        self.assertTrue(artifact['editorialUpdateAvailable'])
        self.assertEqual(self.store.latest('MEMO-TEST')[0], original)
        exported = self.request(suffix=f"/{artifact['id']}/export", params={'revision': artifact['revisionId'], 'format': 'json'})
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()['editorialProfile'], original['editorialProfile'])

    def test_apply_reorders_renames_preserves_basis_and_text_then_requires_approval(self):
        self.create(); self.command('APPROVE_ARTIFACT')
        original = self.store.latest('MEMO-TEST')[0]
        config = default_config(); config['sections'].reverse()
        for section in config['sections']: section['title'] = 'Custom ' + section['title']
        self.save(config)
        profile = self.profile()
        result = self.command('APPLY_EDITORIAL_PROFILE', expectedProfileVersion=profile['versionId'])['snapshot']
        self.assertEqual(result['artifacts'][0]['approvalStatus'], 'DRAFT')
        self.assertFalse(result['artifacts'][0]['editorialUpdateAvailable'])
        latest = self.store.latest('MEMO-TEST')[0]
        by_id = {b['id']: b for b in original['blocks']}
        for block in latest['blocks']:
            before = by_id[block['id']]
            for field in ['text', '_basis', 'boundObjectIds', 'authorship', 'editorialLocked']:
                self.assertEqual(block[field], before[field])
            self.assertTrue(block['title'].startswith('Custom '))
        self.assertNotEqual([b['id'] for b in latest['blocks']], [b['id'] for b in original['blocks']])
        self.assertEqual(latest['priorRevisionId'], original['revisionId'])
        approved = self.command('APPROVE_ARTIFACT')['snapshot']['artifacts'][0]
        self.assertEqual(approved['approvalStatus'], 'APPROVED')
        exported = self.request(suffix=f"/{approved['id']}/export", params={'revision': approved['revisionId']})
        self.assertEqual(exported.status_code, 200)
        self.assertIn('Frozen editorial brief', exported.text)

    def test_apply_guards_profile_conflict_and_pending_review(self):
        self.create(); old = self.profile()
        self.save()
        self.command('APPLY_EDITORIAL_PROFILE', expectedProfileVersion=old['versionId'], status=409)
        self.command('REDRAFT_ARTIFACT')
        self.command('APPLY_EDITORIAL_PROFILE', expectedProfileVersion=self.profile()['versionId'], status=409)
        self.accept_all()
        self.command('APPLY_EDITORIAL_PROFILE', expectedProfileVersion=self.profile()['versionId'])
        self.command('APPLY_EDITORIAL_PROFILE', expectedProfileVersion=self.profile()['versionId'], status=409)

    def test_case_sync_keeps_custom_section_ids_titles_and_order(self):
        config = default_config(); config['sections'].reverse()
        config['sections'] = [{**s, 'title': 'Custom ' + s['title']} for s in config['sections']]
        self.save(config); self.create()
        initial = self.store.latest('MEMO-TEST')[0]
        self.case = copy.deepcopy(self.cases[1])
        self.command('SYNC_ARTIFACT'); self.accept_all()
        latest = self.store.latest('MEMO-TEST')[0]
        self.assertEqual(latest['editorialProfile'], initial['editorialProfile'])
        self.assertEqual([(b['id'], b['title']) for b in latest['blocks']], [(b['id'], b['title']) for b in initial['blocks']])
        self.assertTrue(any('EUR 6 million' in b['text'] for b in latest['blocks']))
        self.command('APPROVE_ARTIFACT')

    def test_real_writer_request_receives_exact_frozen_profile_and_fixed_guardrails(self):
        config = default_config(); config.update(language='Italiano', name='Growth IC', riskGuidance='Discuss downside and mitigations first.')
        self.save(config); self.create()
        original = self.store.latest('MEMO-TEST')[0]
        self.save({**config, 'language': 'French'})
        blocks = [b for b in original['blocks'] if not b['editorialLocked']]
        response = httpx.Response(200, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'), json={
            'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'passages': [{'id': b['id'], 'text': b['text']} for b in blocks]})}]}]})
        command = dict(actorId=self.actor['actorId'], requestId=str(uuid.uuid4()), caseVersion=self.case['caseVersion'], expectedRevision=original['revisionId'], action={'type': 'REDRAFT_ARTIFACT', 'artifactId': original['artifact']['id']})
        with patch('app.memo_writer.httpx.post', return_value=response) as post:
            result = self.store.mutate(self.case, self.actor, command, writer=MemoWriter('test-key'))
        body = post.call_args.kwargs['json']; writer_input = json.loads(body['input'])
        self.assertEqual(writer_input['editorialProfile'], original['editorialProfile'])
        self.assertEqual(writer_input['editorialProfile']['config']['language'], 'Italiano')
        self.assertIn('cannot override', body['instructions'])
        self.assertFalse(any(b['editorialLocked'] and b.get('suggestion') for b in result['blocks']))
        self.assertTrue(all(not b['editorialLocked'] for b in blocks))
        self.command('APPROVE_ARTIFACT', status=409)

    def test_profile_aware_simulation_and_export_escape_user_preferences(self):
        config = default_config(); config.update(language='Italiano', name='<script>custom</script>')
        self.save(config); self.create()
        saved = self.store.latest('MEMO-TEST')[0]
        command = dict(actorId=self.actor['actorId'], requestId=str(uuid.uuid4()), caseVersion=self.case['caseVersion'], expectedRevision=saved['revisionId'], action={'type': 'REDRAFT_ARTIFACT', 'artifactId': saved['artifact']['id']})
        result = self.store.mutate(self.case, self.actor, command, writer=simulated_writer)
        self.assertTrue(all(b['suggestion']['suggestedText'].startswith('Per il comitato:') for b in result['blocks'] if not b['editorialLocked']))
        self.accept_all(); self.command('APPROVE_ARTIFACT')
        saved = self.store.latest('MEMO-TEST')[0]
        html = render_export(saved, 'html', 'http://testserver')[2]
        self.assertIn('&lt;script&gt;custom&lt;/script&gt;', html)
        self.assertNotIn('<script>', html)


if __name__ == '__main__': unittest.main()
