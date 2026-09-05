"""Regression coverage using the existing documents and supplied Keystone graphs."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT, ROOT / 'backend/dynamics', ROOT / 'backend/dynamics/tests'):
    sys.path.insert(0, str(path))
from fastapi import FastAPI
import app.v20_router as router
from test_source_documents import ApiClient
from tools.repository_tracking_case import build_repository_case, evaluation_addresses, CASE_ID, PACKAGE_NAME, digest


class RepositoryNativeDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.previous = {key: getattr(router, key) for key in ('VAULT', 'CASE_PIPELINE_ROOT', 'PIPELINE_OUT')}
        router.VAULT, router.CASE_PIPELINE_ROOT, router.PIPELINE_OUT = cls.root/'vault', cls.root/'cases', cls.root/'legacy'
        inbox = router.VAULT/'inbox'
        inbox.mkdir(parents=True)
        cls.documents, records = {}, []
        cls.cases = [json.loads(line) for line in (ROOT/'evaluation/fixtures/cases/panta_smoke.ndjson').read_text().splitlines() if line.strip()]
        for case in cls.cases:
            for item in case['inputs']:
                path = ROOT/item['path']
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise AssertionError('Supplied document fixture hash changed')
                (inbox/path.name).write_bytes(data)
                version = 'sha256:'+item['sha256']
                cls.documents[path.name] = {'source_id':path.stem,'source_version_id':version}
                records.append({'case_id':'DOC-TEST','source_envelope':{'case_id':'DOC-TEST','source_id':path.stem,'source_version_id':version,'stored_filename':path.name}})
        (inbox/'.ingest-manifest.json').write_text(json.dumps({'items':records}))
        app = FastAPI(); app.include_router(router.v20)
        cls.client = ApiClient(app)

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.previous.items(): setattr(router,key,value)
        cls.temp.cleanup()

    def descriptor(self, filename, locator):
        response = self.client.get('/api/v20/cases/DOC-TEST/source-document',params={**self.documents[filename],'locator':locator})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_all_supplied_evaluation_addresses_open_at_their_recorded_precision(self):
        count = 0
        for case in self.cases:
            inputs = {i['input_id']:i for i in case['inputs']}
            for item, locator in evaluation_addresses(case):
                if item.get('input_id') not in inputs: continue
                filename = Path(inputs[item['input_id']]['path']).name
                with self.subTest(filename=filename,locator=locator):
                    descriptor = self.descriptor(filename,locator)
                    self.assertEqual(descriptor['position']['status'],'LOCATED')
                    view = self.client.get(descriptor['view_url'])
                    self.assertEqual(view.status_code,200,view.text[:200])
                    count += 1
        self.assertGreater(count,35)

    def test_excel_without_dimension_metadata_retains_cached_value_and_formula(self):
        descriptor = self.descriptor('panta_financial_model.xlsx',"'Summary'!B6")
        view = self.client.get(descriptor['view_url'])
        self.assertIn('aria-label="B6"><strong>45</strong><code>=B4-B5</code>',view.text)
        self.assertEqual(descriptor['position']['bounds'],[2,6,2,6])

    def test_docx_section_pptx_chart_and_email_are_original_native_content(self):
        examples = [('panta_acquisition_review.docx','section:Investment decision','Maria Rossi recorded the approval.'),
                    ('panta_revenue_review.pptx','slide:1','22'),
                    ('panta_approval.eml','message-id:<panta-email-001@example.test>:body','Project Aurora was approved on 2026-08-15.')]
        for filename,locator,text in examples:
            descriptor=self.descriptor(filename,locator)
            self.assertIn(text,self.client.get(descriptor['view_url']).text)
        wrong=self.descriptor('panta_approval.eml','message-id:<wrong>:body')
        self.assertEqual(wrong['position']['status'],'UNRESOLVED')
        missing=self.descriptor('panta_acquisition_review.docx','section:Nonexistent')
        self.assertEqual(missing['position']['status'],'UNRESOLVED')

    def test_image_and_pdf_regions_reject_out_of_bounds_and_malformed_addresses(self):
        for filename,prefix in [('panta_test_visual.png','image:1'),('panta_investment_report.pdf','p1')]:
            for suffix in (':rect:0,0,99999,99999',':rect:NaN,2,3,4',':rect:8,8,2,2'):
                response=self.client.get('/api/v20/cases/DOC-TEST/source-document',params={**self.documents[filename],'locator':prefix+suffix})
                self.assertEqual(response.status_code,422,response.text[:200])
        unknown=self.descriptor('panta_test_visual.png','image:2:rect:1,1,2,2')
        self.assertEqual(unknown['position']['status'],'UNRESOLVED')
        self.assertIsNone(unknown['position']['box'])


@unittest.skipUnless((ROOT.parent/PACKAGE_NAME).is_dir() and (ROOT.parent/'GOLD/keystone_execution_mapping_v1 (3).json').is_file(), 'Supplied Keystone test package is not available')
class RepositoryGraphTrackingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.case=build_repository_case(cls.root)
        cls.previous={key:getattr(router,key) for key in ('VAULT','CASE_PIPELINE_ROOT','PIPELINE_OUT')}
        router.VAULT,router.CASE_PIPELINE_ROOT,router.PIPELINE_OUT=cls.root/'vault',cls.root/'cases',cls.root/'legacy'
        app=FastAPI();app.include_router(router.v20);cls.client=ApiClient(app)

    @classmethod
    def tearDownClass(cls):
        for path,expected in cls.case['report']['source_hashes'].items():
            if digest(Path(path))!=expected: raise AssertionError('An original test artifact was modified')
        for key,value in cls.previous.items():setattr(router,key,value)
        cls.temp.cleanup()

    def test_all_registered_originals_are_downloaded_byte_for_byte(self):
        for source_id,document in self.case['documents'].items():
            response=self.client.get('/api/v20/cases/'+CASE_ID+'/source-document/file',params={'source_id':source_id,'source_version_id':document.version_id})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,document.data)

    def test_full_mapping_is_audited_and_indirect_nodes_retain_declared_paths(self):
        report=self.case['report']
        self.assertEqual(report['model_node_count'],14318)
        self.assertEqual(report['declared_edge_count'],30996)
        self.assertEqual(report['source_count'],19)
        self.assertEqual(report['model_location_counts'],{'LOCATED':14279})
        self.assertEqual(report['canonical_location_counts'],{'LOCATED':45,'UNRESOLVED':30})
        self.assertEqual(report['evaluation_location_counts'],{'LOCATED':36})
        self.assertEqual(len(report['nodes_without_direct_locator']),39)
        self.assertEqual(len(report['nodes_with_source_overview_only']),7)
        self.assertEqual(len(report['indirect_paths']),32)
        self.assertEqual(report['direct_reference_counts'].get('INVALID',0),0)
        self.assertEqual(report['nodes_without_source_path'],[])
        for identity,path in report['indirect_paths'].items():
            self.assertEqual(path[0],identity)
            self.assertTrue(self.case['refs'][path[-1]][0]['locator'])
            for child,parent in zip(path,path[1:]):
                self.assertIn(parent,self.case['inspect'](child)['supportObjectIds'])

    def test_all_statements_roundtrip_without_hiding_ambiguous_locators(self):
        for row in self.case['audit']:
            if not (row['id'].startswith('CL-') or row['id'].startswith('EVAL-')):continue
            ref=self.case['refs'][row['id']][0]
            params={'source_id':ref['sourceId'],'source_version_id':ref['sourceVersionId'],'locator':ref['locator'],'claim_id':ref['claimId']}
            response=self.client.get('/api/v20/cases/'+CASE_ID+'/source-document',params=params)
            self.assertEqual(response.status_code,200,response.text)
            descriptor=response.json()
            self.assertEqual(descriptor['locator'],row['locator'])
            self.assertEqual(descriptor['position']['status'],row['status'])
            view=self.client.get(descriptor['view_url'])
            self.assertEqual(view.status_code,200,view.text[:200])
            if row['status']=='UNRESOLVED':self.assertIn('without a verified passage selection',view.text)

    def test_multi_sheet_reference_and_literal_document_headings(self):
        for identity,expected in [('CL-037',['Inputs!B12','QoE_Bridge!F19']),('CL-029',['Executive findings','Normalized EBITDA schedule'])]:
            ref=self.case['refs'][identity][0]
            response=self.client.get('/api/v20/cases/'+CASE_ID+'/source-document',params={'source_id':ref['sourceId'],'source_version_id':ref['sourceVersionId'],'locator':ref['locator']})
            self.assertEqual(response.status_code,200,response.text)
            data=response.json();self.assertEqual(data['position']['status'],'LOCATED')
            view=self.client.get(data['view_url'])
            for text in expected:self.assertIn(text,view.text)

    def test_simulated_precise_capture_opens_all_thirty_original_passages(self):
        simulation=build_repository_case(self.root,simulate_locations=True)
        report=simulation['report']
        self.assertEqual(report['canonical_location_counts'],{'LOCATED':75})
        self.assertEqual(report['unresolved_references'],[])
        self.assertEqual(self.case['report']['canonical_location_counts'],{'LOCATED':45,'UNRESOLVED':30})
        self.assertEqual(len(report['simulated_location_mappings']),30)
        for entry in report['simulated_location_mappings']:
            with self.subTest(claim=entry['claim_id']):
                ref=simulation['refs'][entry['claim_id']][0]
                response=self.client.get('/api/v20/cases/'+report['case_id']+'/source-document',params={
                    'source_id':ref['sourceId'],'source_version_id':ref['sourceVersionId'],
                    'locator':ref['locator'],'claim_id':ref['claimId']})
                self.assertEqual(response.status_code,200,response.text)
                descriptor=response.json()
                self.assertEqual(descriptor['position']['spans'],entry['line_spans'])
                view=self.client.get(descriptor['view_url'])
                self.assertEqual(view.status_code,200)
                selected={i for a,b in entry['line_spans'] for i in range(a,b+1)}
                self.assertEqual(view.text.count('class="text-line selected"'),len(selected))
                lines=simulation['documents'][entry['source_id']].data.decode().splitlines()
                hashes=['sha256:'+hashlib.sha256('\n'.join(lines[a-1:b]).encode()).hexdigest() for a,b in entry['line_spans']]
                self.assertEqual(hashes,entry['span_hashes'])
        self.assertIn('validation answer key is excluded',next(c for c in simulation['snapshot']['claims'] if c['id']=='CL-M20')['limitation'])
        for source in simulation['snapshot']['sources']:
            source_claims=simulation['inspect'](source['id'])['dependentObjectIds']
            self.assertEqual(set(source_claims),{c['id'] for c in simulation['snapshot']['claims'] if c['sourceId']==source['id']})

    def test_simulation_fails_if_source_graph_or_recorded_reference_changed(self):
        from copy import deepcopy
        from dataclasses import replace
        from tools.tracking_location_simulation import apply_location_simulation
        claims=[{'claim_id':c['id'],'source_id':c['sourceId'],'locator':c['locator']} for c in self.case['snapshot']['claims']]
        graph_hash=self.case['snapshot']['caseVersion']
        with self.assertRaises(ValueError):apply_location_simulation(deepcopy(claims),self.case['documents'],'sha256:'+'0'*64)
        wrong=deepcopy(claims);next(c for c in wrong if c['claim_id']=='CL-011')['locator']='Other reference'
        with self.assertRaises(ValueError):apply_location_simulation(wrong,self.case['documents'],graph_hash)
        docs=dict(self.case['documents']);docs['SRC-DR']=replace(docs['SRC-DR'],data=b'changed text')
        with self.assertRaises(ValueError):apply_location_simulation(deepcopy(claims),docs,graph_hash)

    def test_multiple_line_ranges_reject_partial_or_invalid_selections(self):
        ref=self.case['refs']['CL-011'][0]
        for locator in ('lines:94-96,99999-100000','lines:94-96,97-96','lines:94-96,garbage'):
            response=self.client.get('/api/v20/cases/'+CASE_ID+'/source-document',params={
                'source_id':ref['sourceId'],'source_version_id':ref['sourceVersionId'],'locator':locator})
            self.assertEqual(response.status_code,422,response.text)


if __name__=='__main__':unittest.main()
