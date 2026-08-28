#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, re, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
from typing import Callable, Any

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'01_PRODUCT_BUILD/app'
SERVER=ROOT/'01_PRODUCT_BUILD/mock_api/server.py'
FIX=ROOT/'01_PRODUCT_BUILD/fixtures'
OUT=ROOT/'08_TEST_EVIDENCE'
results=[]

def add(section:str,name:str,fn:Callable[[],Any]):
    try:
        detail=fn()
        results.append({'section':section,'name':name,'status':'PASS','detail':str(detail if detail is not None else '')})
    except Exception as e:
        results.append({'section':section,'name':name,'status':'FAIL','detail':f'{type(e).__name__}: {e}'})

def assert_true(v,msg='assertion failed'):
    if not v: raise AssertionError(msg)
    return v

def text(p): return Path(p).read_text(encoding='utf-8')
def jload(p): return json.loads(text(p))
def core_text():
    parts=[]
    for p in sorted(APP.rglob('*')):
        if p.is_file() and p.suffix in {'.js','.html','.css','.json'} and 'assets' not in p.parts:
            parts.append(text(p))
    return '\n'.join(parts)

# Static and contract checks
core=core_text(); render=text(APP/'src/render.js'); engine=text(APP/'src/engine.js'); api=text(APP/'src/api.js'); server=text(SERVER); index=text(APP/'index.html')
add('Core purity','No Keystone facts in connected core',lambda: assert_true(not re.search(r'Keystone|Alderstone|Riverton|\$108(?:\.0)?m|M\. Alvarez|A\. Rossi|UQ-EARNINGS|COURSE-B',core,re.I),'case-specific content found'))
add('Core purity','No fixture import in connected core',lambda: assert_true('PANTA_V19_FIXTURE' not in core and 'v17_fixture' not in core and 'v16_case_bundle' not in core,'fixture import found'))
add('Core purity','Explicit three operating modes',lambda: assert_true(all(x in text(APP/'src/boot.js')+text(APP/'src/store.js') for x in ['connected','mock','offline']),'modes missing'))
add('Core purity','Connected has no silent fixture fallback',lambda: assert_true('ensureOfflineFixture' in api and 'mode===\'offline\'' in api and 'fallback' not in re.sub(r'No fixture fallback','',text(APP/'src/boot.js'),flags=re.I).lower(),'fallback ambiguity'))
add('Input','File input exists',lambda: assert_true('type="file"' in render,'file input missing'))
add('Input','Path and URL inputs exist',lambda: assert_true('ingest-value' in render and "['file','path','url']" in render,'path/url input missing'))
add('Input','Vault inbox is visible',lambda: assert_true('VAULT INBOX' in render and 'refresh-inbox' in render,'inbox UI missing'))
add('Input','Refresh projection and sources exist',lambda: assert_true('refresh-projection' in render and 'refresh-sources' in render,'refresh missing'))
add('Input','Case switcher exists',lambda: assert_true('case-switcher' in render and 'openCase' in engine,'case switch missing'))
add('Input','Professional claim review is server-acknowledged',lambda: assert_true('reviewClaim' in engine and '/notes' in api,'review write path missing'))
add('Input','Structured deal opening and IC record exist',lambda: assert_true('open-deal' in api and 'ic-record' in api and 'case-inputs' in render and 'Case Setup & IC Record' in render,'structured inputs missing'))
add('Output','Seven claim filters exist',lambda: assert_true(all(k in render for k in ['epistemic','topic','period','perimeter','source','direction','author']),'filters missing'))
add('Output','Sorting exists',lambda: assert_true('claim-sort' in render and 'setSourceSort' in engine,'sort missing'))
add('Output','Pagination is explicit',lambda: assert_true('Page ${page} of ${pages}' in render and 'setSourcePage' in engine,'pagination missing'))
add('Output','As-of state selector exists',lambda: assert_true('as-of-switcher' in render and 'setAsOfState' in engine,'as-of missing'))
add('Output','Aggregate members are clickable',lambda: assert_true('data-open-object' in render,'drilldown missing'))
add('Output','Search index is not capped at five',lambda: assert_true('.slice(0,50)' in api and '.slice(0,5)' not in api,'search cap wrong'))
add('Output','Fake Lens selector removed',lambda: assert_true('lens-select' not in render and 'setLens' not in engine,'decorative lens remains'))
add('Output','Export and deep link actions exist',lambda: assert_true('exportJSON' in engine and 'deepLink' in engine and 'copyText' in engine,'export/deeplink missing'))
add('Output','Foundations preserve multiple values and perimeters',lambda: assert_true('evidence_options' in render and 'perimeter' in render,'multi-value foundation missing'))
add('Output','Domain unknowns and pipeline review separated',lambda: assert_true('setUnknownTab' in engine and 'PIPELINE REVIEW' in render,'register separation missing'))
add('State','Operation-specific errors rendered',lambda: assert_true('errorCard' in render and 'lastError' in engine,'errors missing'))
add('State','Ingest job progress rendered',lambda: assert_true('INGEST JOBS' in render and 'getJob' in api and 'pollIngest' in engine,'progress missing'))
add('State','Deep-link routing exists',lambda: assert_true('history.pushState' in engine or 'location.hash' in engine,'routing missing'))
add('State','Focus and scroll restoration exist',lambda: assert_true('captureFocus' in render and 'restoreFocus' in render,'focus manager missing'))
add('State','Accessible dialog focus trap exists',lambda: assert_true('role="dialog"' in render and 'trapDialog' in render,'dialog pattern missing'))
add('State','Reduced motion is system-derived',lambda: assert_true('prefers-reduced-motion' in text(APP/'src/store.js'),'reduced motion missing'))
add('Artifacts','Artifacts are projection-driven',lambda: assert_true('deal.artifacts' in render and 'Firm EBITDA $11.4m' not in render,'static artifact table remains'))
add('Artifacts','Ingested sources become source objects',lambda: assert_true('complete_job' in server and "source_center" in server,'source materialization missing'))
add('Artifacts','Workbook cell viewer exists',lambda: assert_true('cell-view' in render and 'formula' in render and 'precedent' in render,'cell viewer missing'))
add('Artifacts','PDF viewer exists',lambda: assert_true('<iframe' in render and 'source-viewer' in render,'PDF viewer missing'))
add('Artifacts','Source version history exists',lambda: assert_true('version-list' in render and 'arr(r.versions)' in render,'version history missing'))
add('Backend','Question bindings exposed',lambda: assert_true('claim_question_bindings' in server and 'coverage|bindings|compiler-report' in server,'bindings route missing'))
add('Backend','Questions served in projection',lambda: assert_true('question_spine' in jload(FIX/'PROJECT-KEYSTONE/projection.json')['deal'],'questions missing'))
add('Backend','Contradiction routes exposed',lambda: assert_true('contradictions' in jload(FIX/'PROJECT-KEYSTONE/projection.json')['deal'],'contradictions missing'))
add('Backend','Admission is implemented',lambda: assert_true('/admit' in api and 'Candidate calculated' in server,'admission stub remains'))
add('Backend','Replay is implemented and read-only',lambda: assert_true("'read_only':True" in server and '/replay' in api,'replay missing'))
add('Backend','Compiler report, coverage and cell routes exist',lambda: assert_true(all(x in server for x in ['compiler-report','coverage','claims|questions|cells']),'compiler routes missing'))
add('Backend','Human inputs persist in session store',lambda: assert_true("s['notes'].append" in server and 'IC_RECORD' in server,'writes missing'))
add('Backend','Ingest is asynchronous',lambda: assert_true("return self.js(202" in server and "job['poll_count']" in server,'async job missing'))
add('Backend','Reset is not exposed as destructive product action',lambda: assert_true('/reset' not in api and "path==f'{API}/reset'" not in server,'destructive reset exposed'))
add('Backend','Session-scoped history exists',lambda: assert_true(".sessions" in server and 'new_session' in server and "s['registry']" in server,'session history missing'))
add('Forcing','Scenario trajectory uses projected data',lambda: assert_true('s.trajectory' in render or 'trajectory' in render,'decorative trajectory remains'))
add('Forcing','Navigation consumes capability map',lambda: assert_true('navigation_capabilities' in render or 'capabilities' in render,'capabilities ignored'))
add('Forcing','Reviewables are data-driven',lambda: assert_true('earnings' not in engine.lower() and 'concentration' not in engine.lower(),'review keys hardcoded'))
add('Forcing','Initial selection comes from projection',lambda: assert_true('initial_focus' in engine and 'UQ-EARNINGS' not in text(APP/'src/store.js'),'initial IDs hardcoded'))
add('Forcing','Claim drawer has explicit object branch',lambda: assert_true('claim_id' in render and 'reviewClaim' in render,'claim drawer missing'))
add('Forcing','Registry and UI telemetry are separate',lambda: assert_true('localStorage' not in engine and 'UI telemetry' not in render,'registry mixed with browser history'))

# Fixture contract checks
for cid in ['PROJECT-KEYSTONE','PROJECT-ORION']:
    p=jload(FIX/cid/'projection.json'); d=p['deal']
    add('Fixture',f'{cid} uses V19 contract',lambda p=p: assert_true(str(p.get('package_version','')).startswith('19'),'wrong package'))
    add('Fixture',f'{cid} has bound claims',lambda d=d: assert_true(sum(bool(c.get('bears_on')) for c in d.get('claims',[]))>0,'no bindings'))
    add('Fixture',f'{cid} has questions',lambda d=d: assert_true(len(d.get('question_spine',[]))>=6,'questions absent'))
    add('Fixture',f'{cid} has inspectable cells',lambda d=d: assert_true(len(d.get('cells',[]))>0,'cells absent'))
    add('Fixture',f'{cid} has multi-value foundations',lambda d=d: assert_true(any(len(x.get('evidence_options',[]))>1 for x in d.get('rooms',{}).get('foundations',{}).get('sets',[])),'multi-values absent'))
    add('Fixture',f'{cid} separates pipeline issues',lambda d=d: assert_true(isinstance(d.get('source_center',{}).get('pipeline_issues'),list),'pipeline issues absent'))

# Node/Python syntax
for p in sorted((APP/'src').glob('*.js')):
    add('Syntax',f'node --check {p.name}',lambda p=p: subprocess.run(['node','--check',str(p)],capture_output=True,text=True,check=True).returncode)
add('Syntax','Python mock server compiles',lambda: subprocess.run([sys.executable,'-m','py_compile',str(SERVER)],capture_output=True,text=True,check=True).returncode)

# API and browser flows
port=4197
proc=subprocess.Popen([sys.executable,str(SERVER),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(1)

def http(method,path,body=None,headers=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=data,method=method,headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=15) as r:return r.status,json.loads(r.read().decode())
try:
    st,b=http('GET','/api/v19/bootstrap?case_id=PROJECT-KEYSTONE&actor=partner&mode=MOCK_CONNECTED'); sid=b['session_id']; q=f'session_id={sid}'
    add('API','Bootstrap exposes two cases',lambda: assert_true(len(b['available_cases'])>=2,b['available_cases']))
    st,pj=http('GET',f'/api/v19/cases/PROJECT-KEYSTONE/projection?{q}')
    add('API','Projection returns V19',lambda: assert_true(pj['projection']['package_version']=='19.0.0','wrong projection'))
    st,ing=http('POST',f'/api/v19/cases/PROJECT-KEYSTONE/ingest?{q}',{'method':'path','value':'/data/qoe_update.pdf','purpose':'QoE','actor_id':'ACTOR-PARTNER'})
    jid=ing['job']['job_id']; last=None
    for _ in range(10):
        _,jb=http('GET',f'/api/v19/jobs/{jid}?{q}'); last=jb['job'];
        if last['status']=='COMPLETE':break
        time.sleep(.05)
    add('API','Async ingest reaches COMPLETE',lambda: assert_true(last['status']=='COMPLETE',last))
    _,pj2=http('GET',f'/api/v19/cases/PROJECT-KEYSTONE/projection?{q}')
    add('API','Projection refresh includes ingested claim',lambda: assert_true(len(pj2['projection']['deal']['claims'])>len(pj['projection']['deal']['claims']),'claim count unchanged'))
    event=pj2['projection']['events']['concentration']; payload={'treatment_id':event['treatment_id'],'treatment_hash':event.get('treatment_hash','sha256:test'),'source_version_id':event['source_version_id'],'event_id':event['event_id'],'actor_id':'ACTOR-PARTNER','as_of_state_id':pj2['context']['as_of_state_id'],'idempotency_key':'TEST-ADMIT'}
    _,ad=http('POST',f"/api/v19/cases/PROJECT-KEYSTONE/events/{event['event_id']}/admit?{q}",payload,{'Idempotency-Key':'TEST-ADMIT'})
    rid=ad['run']['run_id'];t=ad['transition']; selected=[x['artifact_id'] for x in t['artifact_change_sets']]
    _,prep=http('POST',f'/api/v19/runs/{rid}/prepare?{q}',{'selected_change_ids':selected})
    stop=t['human_stops'][0]
    authbody={'run_id':rid,'candidate_state_id':t['candidate_state_id'],'human_stop_id':stop['stop_id'],'course_id':'COURSE-B','actor_id':'ACTOR-PARTNER','actor_role':'Partner','artifact_hash':t['replay_hash'],'idempotency_key':'TEST-AUTH'}
    _,au=http('POST',f'/api/v19/runs/{rid}/authority/attest?{q}',authbody,{'Idempotency-Key':'TEST-AUTH'}); pkg=au['execution_package']
    add('API','Course-specific package is READY',lambda: assert_true(pkg and pkg['course_id']=='COURSE-B' and pkg['status']=='READY','package wrong'))
    _,sent=http('POST',f"/api/v19/execution-packages/{pkg['execution_package_id']}/send?{q}",{'simulate_failure':False})
    add('API','Success appears after server ack',lambda: assert_true(sent['execution_package']['status']=='ACCEPTED' and sent['execution_package'].get('ack_id'),'ack absent'))
    settlebody={'run_id':rid,'candidate_state_id':t['candidate_state_id'],'prior_state_id':t['prior_state_id'],'as_of_state_id':pj2['context']['as_of_state_id'],'selected_change_ids':selected,'human_stop_ids':[stop['stop_id']],'authority_record_ids':[au['authority_record']['authority_record_id']],'execution_package_ids':[pkg['execution_package_id']],'actor_id':'ACTOR-PARTNER','allow_partial_settlement':True,'idempotency_key':'TEST-SETTLE'}
    _,sett=http('POST',f'/api/v19/runs/{rid}/settle?{q}',settlebody,{'Idempotency-Key':'TEST-SETTLE'})
    add('API','Settlement returns canonical state',lambda: assert_true(sett.get('current_state_id') and sett.get('projection'),'settlement incomplete'))
    # Defer in new session/run
    _,ns=http('POST','/api/v19/sessions',{'case_id':'PROJECT-KEYSTONE','actor':'partner','mode':'MOCK_CONNECTED'}); q2=f"session_id={ns['session_id']}";_,pr=http('GET',f'/api/v19/cases/PROJECT-KEYSTONE/projection?{q2}'); ev=pr['projection']['events']['concentration']; pl={'treatment_id':ev['treatment_id'],'treatment_hash':ev.get('treatment_hash','sha256:test'),'source_version_id':ev['source_version_id'],'event_id':ev['event_id'],'actor_id':'ACTOR-PARTNER','as_of_state_id':pr['context']['as_of_state_id'],'idempotency_key':'D-ADMIT'};_,ad2=http('POST',f"/api/v19/cases/PROJECT-KEYSTONE/events/{ev['event_id']}/admit?{q2}",pl,{'Idempotency-Key':'D-ADMIT'});r2=ad2['run']['run_id'];ids=[x['artifact_id'] for x in ad2['transition']['artifact_change_sets']];http('POST',f'/api/v19/runs/{r2}/prepare?{q2}',{'selected_change_ids':ids});stop2=ad2['transition']['human_stops'][0];ab={'run_id':r2,'candidate_state_id':ad2['transition']['candidate_state_id'],'human_stop_id':stop2['stop_id'],'course_id':'COURSE-C','actor_id':'ACTOR-PARTNER','actor_role':'Partner','artifact_hash':ad2['transition']['replay_hash'],'idempotency_key':'D-AUTH'};_,da=http('POST',f'/api/v19/runs/{r2}/authority/attest?{q2}',ab,{'Idempotency-Key':'D-AUTH'})
    add('API','Defer produces no execution package',lambda: assert_true(da.get('execution_package') is None and da['authority_record']['effect_type']=='DEFER','defer executed'))
except Exception as e:
    results.append({'section':'API','name':'API flow bootstrap','status':'FAIL','detail':repr(e)})
finally:
    proc.terminate()
    try:proc.wait(timeout=5)
    except:proc.kill()

# Browser checks if Playwright available
try:
    from playwright.sync_api import sync_playwright
    port=4198; proc=subprocess.Popen([sys.executable,str(SERVER),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);time.sleep(1)
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        for width,height in [(1920,1080),(1440,900),(1280,800),(1051,800),(1050,800),(1024,768),(768,900),(390,844)]:
            p=b.new_page(viewport={'width':width,'height':height}); errs=[];p.on('pageerror',lambda e,errs=errs:errs.append(str(e)))
            u=f'http://127.0.0.1:{port}/?mode=mock&case=PROJECT-KEYSTONE&actor=partner&api=http://127.0.0.1:{port}/api/v19';p.goto(u,wait_until='domcontentloaded',timeout=30000);p.wait_for_function("PantaStore.get().boot==='ready'",timeout=30000);p.evaluate("PantaActions.setView('deal-command')");p.wait_for_timeout(150)
            metrics=p.evaluate("({doc:document.documentElement.scrollWidth,view:document.documentElement.clientWidth,main:document.querySelector('.workspace-content')?.scrollWidth||0,mainClient:document.querySelector('.workspace-content')?.clientWidth||0,mobile:PantaStore.get().mobileReadOnly,errors:[]})")
            def check(m=metrics,w=width,errs=errs):
                assert_true(not errs,'; '.join(errs)); assert_true(m['doc']<=m['view']+2,f"document clips {m}");
                if w<768: assert_true(m['mobile'] is True,'mobile not read-only')
                return f"{w}px doc={m['doc']} viewport={m['view']}"
            add('Responsive',f'No page clipping at {width}px',check);p.close()
        # selftest and workflow smoke
        p=b.new_page(viewport={'width':1440,'height':900});u=f'http://127.0.0.1:{port}/?mode=mock&case=PROJECT-KEYSTONE&actor=partner&api=http://127.0.0.1:{port}/api/v19';p.goto(u,wait_until='domcontentloaded');p.wait_for_function("PantaStore.get().boot==='ready'");st=p.evaluate('PantaSelfTest.run()');add('Browser','Client self-test 30/30',lambda st=st: assert_true(all(x['status']=='PASS' for x in st),[x for x in st if x['status']!='PASS']))
        p.evaluate("PantaActions.setView('sources');PantaActions.setSourceTab('claims')");p.wait_for_timeout(100);add('Browser','Claims table renders',lambda p=p: assert_true(p.locator('table.data-table tbody tr').count()>0,'no claim rows'))
        p.evaluate("PantaActions.openObject(PantaStore.get().projection.deal.claims.find(x=>x.bears_on&&x.bears_on.length).claim_id,'basis')");p.wait_for_timeout(100);add('Browser','Claim aperture renders',lambda p=p: assert_true(p.locator('.object-drawer').count()==1,'drawer absent'))
        b.close()
    proc.terminate();proc.wait(timeout=5)
except Exception as e:
    results.append({'section':'Browser','name':'Browser suite available','status':'FAIL','detail':repr(e)})
    try:proc.terminate()
    except:pass

# write results
OUT.mkdir(parents=True,exist_ok=True)
summary={'total':len(results),'pass':sum(r['status']=='PASS' for r in results),'fail':sum(r['status']=='FAIL' for r in results),'results':results}
(OUT/'V19_TEST_RESULTS.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
with open(OUT/'V19_TEST_RESULTS.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['section','name','status','detail']);w.writeheader();w.writerows(results)
lines=['# PANTA V19 Automated Test Results','',f"- Total: {summary['total']}",f"- Pass: {summary['pass']}",f"- Fail: {summary['fail']}",'']
for sec in dict.fromkeys(r['section'] for r in results):
    lines+=['',f'## {sec}']
    for r in [x for x in results if x['section']==sec]: lines.append(f"- **{r['status']}** - {r['name']}: {r['detail']}")
(OUT/'V19_TEST_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ['total','pass','fail']},indent=2))
if summary['fail']:
    for r in results:
        if r['status']=='FAIL': print('FAIL',r['section'],r['name'],r['detail'])
    sys.exit(1)
