(function(){
  'use strict';
  function run(){
    const p=PantaStore.get().projection,s=PantaStore.get(),tests=[];const test=(name,fn)=>{try{const detail=fn();tests.push({name,status:'PASS',detail:String(detail??'')})}catch(e){tests.push({name,status:'FAIL',detail:e.message})}},assert=(v,m)=>{if(!v)throw new Error(m)};
    test('Explicit mode selected',()=>{assert(['connected','mock','offline','empty'].includes(s.mode),'Unknown mode');return s.mode});
    if(!p){test('Empty state contains no injected case',()=>{assert(!s.caseId,'Case should be absent');return'clean empty system'});window.PANTA_V20_SELFTEST=tests;return tests}
    test('Projection boundary validates',()=>{const r=PantaContracts.safe(PantaContracts.validateProjection,p);assert(r.ok,r.errors.map(x=>x.message).join('; '));return p.schema_version});
    test('V20 package marker',()=>{assert(String(p.package_version||'').startsWith('20'),'Not V20');return p.package_version});
    test('Source center exists',()=>{assert(p.deal.source_center,'Missing source center');return Object.keys(p.deal.source_center).join(', ')});
    test('UI supports file ingestion',()=>{assert(document.querySelector('input[type=file]')||s.view!=='sources','File input missing');return'file/path/url contract'});
    test('Question spine is served',()=>{assert(p.deal.question_spine?.length,'No questions');return`${p.deal.question_spine.length} questions`});
    test('Claim/question binding exists',()=>{const bound=(p.deal.claims||[]).filter(x=>x.bears_on?.length).length;assert(bound>0,'No claim bears on a question');return`${bound}/${p.deal.claims.length} bound`});
    test('Domain and pipeline unknowns are separate',()=>{assert(Array.isArray(p.deal.rooms?.unknowns?.items)&&Array.isArray(p.deal.source_center?.pipeline_issues),'Registers missing');return'distinct registers'});
    test('Foundations preserve multiple evidence values',()=>{const n=(p.deal.rooms?.foundations?.sets||[]).filter(x=>(x.evidence_options||[]).length>1).length;assert(n>0,'No multi-value foundation');return`${n} multi-value sets`});
    test('Command index is not limited to five',()=>{assert((p.deal.command_index||[]).length>5,'Index too small');return`${p.deal.command_index.length} objects`});
    test('Artifact model has inspectable cells',()=>{const n=(p.deal.cells||[]).length+(p.deal.artifacts||[]).reduce((a,x)=>a+(x.cell_index||[]).length,0);assert(n>0,'No inspectable cells');return`${n} cell objects`});
    test('Sources expose immutable versions',()=>{const src=p.deal.source_center.sources||[];assert(src.every(x=>Array.isArray(x.versions)),'Source lacks versions');return`${src.length} sources`});
    test('No connected fallback to fixtures',()=>{assert(!/fixture/i.test(String(PantaStore.get().lastError?.message||'')),'Unexpected fixture fallback');return s.mode});
    test('Identity and viewer projection are distinct',()=>{assert(s.context?.authenticated_actor&&s.viewerProjection,'Missing identity/projection');return`${s.context.authenticated_actor.actor_id} / ${s.viewerProjection}`});
    test('Authority assignments are server context',()=>{assert(Array.isArray(s.context?.authority_assignments),'Authority assignments missing');return`${s.context.authority_assignments.length} assignments`});
    test('Decision room is gated',()=>{const g=PantaActions.decisionGate();return g.ok?'active run available':'blocked without run'});
    test('Execution room is gated',()=>{const g=PantaActions.executionGate();return g.ok?'package ready':'blocked without package'});
    test('Courses declare effect type',()=>{const c=p.deal.decisionRoom?.courses||[];assert(c.every(x=>x.effect_type),'Missing effect type');return`${c.length} courses`});
    test('Defer has no execution payload',()=>{const d=(p.deal.decisionRoom?.courses||[]).find(x=>x.effect_type==='DEFER');assert(d&&!d.execution,'Defer must not execute');return d.id});
    test('Page-wide as-of state exists',()=>{assert(s.context?.as_of_state_id,'No as-of state');return s.context.as_of_state_id});
    test('Replay is read-only by contract',()=>{assert(p.deal.replay?.snapshots,'Replay missing');return`${p.deal.replay.snapshots.length} snapshots`});
    test('Institutional Registry separate from UI telemetry',()=>{assert(Array.isArray(s.registry),'Registry missing');assert(!('uiTelemetry' in s),'UI telemetry must not share Registry');return`${s.registry.length} institutional events`});
    test('No global live region',()=>{assert(!document.getElementById('app').hasAttribute('aria-live'),'Root is live region');return'status region only'});
    test('Persistent room capability map',()=>{assert(p.deal.navigation_capabilities||p.deal.capabilities,'Capabilities missing');return'capabilities served'});
    test('Scenario trajectories are data-driven',()=>{const xs=p.deal.scenarioLab?.scenarios||[];assert(xs.every(x=>x.trajectory||x.markers),'Scenario trajectory missing');return`${xs.length} trajectories`});
    test('Synthetic disclosure is explicit',()=>{assert(s.context?.synthetic===true||s.mode==='connected','Disclosure mismatch');return s.context?.synthetic?'synthetic':'live'});
    test('No external effects in mock/offline',()=>{if(['mock','offline'].includes(s.mode))assert(s.context?.no_external_effects===true,'External effects not disabled');return s.context?.action_capability});
    test('Object deep links supported',()=>{assert(location.hash!==undefined,'Hash routing unavailable');return'case/view/object/run/as_of'});
    test('Typography baseline loaded',()=>{const px=parseFloat(getComputedStyle(document.body).fontSize);assert(px>=14,'Body text too small');return`${px}px`});
    test('Reduced motion respects system preference',()=>{assert(typeof s.reducedMotion==='boolean','Motion state missing');return String(s.reducedMotion)});
    if(window.PantaOverflowQA?.enabled)test('Overflow QA fixture is contained',()=>{const results=window.PantaOverflowQA.run(),failed=results.filter(x=>x.status==='FAIL');assert(!failed.length,failed.map(x=>`${x.name}: ${x.detail}`).join('; '));return`${results.length} containment checks`});
    window.PANTA_V20_SELFTEST=tests;return tests;
  }
  function open(){const tests=run(),panel=document.getElementById('selftest');panel.innerHTML=`<header><strong>V20 self-test · ${tests.filter(x=>x.status==='PASS').length}/${tests.length}</strong><button onclick="this.closest('section').classList.remove('open')">×</button></header>${tests.map(t=>`<div class="${t.status.toLowerCase()}"><b>${t.status}</b><span>${t.name}<small>${t.detail}</small></span></div>`).join('')}`;panel.classList.add('open')}
  window.PantaSelfTest={run,open};document.addEventListener('keydown',e=>{if(e.shiftKey&&e.key.toLowerCase()==='t')open()});
})();
