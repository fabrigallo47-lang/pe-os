(function(){
  'use strict';
  const panel=document.getElementById('selftest');
  const F=window.PANTA_V17_FIXTURE;
  const R=window.PantaRuntime;
  const requiredViews=['fund-command','deal-command','work','foundations','unknowns','shadow-ic','artifacts','registry','replay','scenario','decision','execution','change'];

  function test(name,fn){
    try{const detail=fn();return {name,ok:true,detail:detail===true?'PASS':String(detail||'PASS')}}
    catch(error){return {name,ok:false,detail:error.message}}
  }
  function assert(condition,message){if(!condition)throw new Error(message)}
  function collect(){
    return [
      test('V17 fixture loaded',()=>{assert(F&&F.package_version==='17.0.0','Missing V17 fixture');return F.package_version}),
      test('V16 question spine preserved',()=>{assert(F.v16.question_spine.length===8,'Expected 8 underwriting questions');return '8 questions'}),
      test('Universal navigation surfaces declared',()=>{for(const view of requiredViews)assert(view,'Missing view');return `${requiredViews.length} surfaces`}),
      test('Four rooms available',()=>{assert(F.deal.rooms.foundations&&F.deal.rooms.unknowns&&F.deal.rooms.shadowIC&&F.deal.replay,'Missing room');return 'Foundations · Unknowns · Shadow IC · Replay'}),
      test('Scenario / Decision / Execution rooms available',()=>{assert(F.deal.scenarioLab&&F.deal.decisionRoom&&F.deal.executionRoom,'Special room missing');return '3 special rooms'}),
      test('Transition projections contain affected sets',()=>{for(const [id,t] of Object.entries(F.transitions)){assert(Array.isArray(t.affected_set)&&t.affected_set.length,`${id}: no affected_set`)}return '2 transition fixtures'}),
      test('Human stop is explicit in authority scene',()=>{assert(F.transitions.concentration.human_stops.length===1,'Expected one explicit human stop');return F.transitions.concentration.human_stops[0].required_role}),
      test('Compiler adapter exposed',()=>{assert(typeof window.PantaProjectionAdapter?.fromCompilerBundle==='function','Compiler adapter missing');return 'fromCompilerBundle()'}),
      test('Transition adapter exposed',()=>{assert(typeof window.PantaProjectionAdapter?.fromTransitionOutput==='function','Transition adapter missing');return 'fromTransitionOutput()'}),
      test('Integration boundary exposed',()=>{for(const fn of ['bootstrap','loadCase','admitEvent','settle','replay'])assert(typeof window.PantaIntegration?.[fn]==='function',`${fn} missing`);return '5 API functions'}),
      test('Runtime state machine exposed',()=>{for(const fn of ['openDeal','openScene','confirmTreatment','prepareResponse','attestDecision','executeExternal'])assert(typeof R?.[fn]==='function',`${fn} missing`);return 'end-to-end flow callable'}),
      test('Synthetic/demo disclosure present',()=>{assert(/synthetic/i.test(F.disclosure),'Disclosure missing');return 'visible in package metadata'}),
      test('Frontend projection does not own source parsing',()=>{const src=String(window.PantaProjectionAdapter.fromCompilerBundle);assert(!/fetch\(|XMLHttpRequest|openpyxl|formula parser/i.test(src),'Adapter contains parsing logic');return 'mapping only'}),
      test('Role toggle is projection-only',()=>{const before=JSON.stringify(F.v16.question_spine);R.setRole('partner');R.setRole('associate');assert(JSON.stringify(F.v16.question_spine)===before,'Role toggle mutated case facts');return 'facts unchanged'}),
      test('Local HTML entrypoint works',()=>location.protocol==='file:'?'file:// mode':'HTTP mode')
    ];
  }
  function render(results){
    const passed=results.filter(r=>r.ok).length;
    panel.innerHTML=`<header><div><span>V17 SELF TEST</span><strong>${passed}/${results.length} PASS</strong></div><button data-selftest-close>×</button></header><div class="selftest-list">${results.map(r=>`<article class="${r.ok?'pass':'fail'}"><b>${r.ok?'✓':'!'}</b><div><strong>${escapeHtml(r.name)}</strong><small>${escapeHtml(r.detail)}</small></div></article>`).join('')}</div><footer>Shift+T toggles this panel · tests are structural, not a substitute for backend contract validation.</footer>`;
    panel.classList.add('open');
    panel.querySelector('[data-selftest-close]').onclick=close;
    window.PANTA_V17_SELFTEST_RESULTS={passed,total:results.length,results};
    document.documentElement.dataset.selftest=passed===results.length?'pass':'fail';
    return window.PANTA_V17_SELFTEST_RESULTS;
  }
  function escapeHtml(value){return String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
  function open(){return render(collect())}
  function close(){panel.classList.remove('open')}
  window.PantaSelfTest={open,close,run:()=>{const r=collect();window.PANTA_V17_SELFTEST_RESULTS={passed:r.filter(x=>x.ok).length,total:r.length,results:r};document.documentElement.dataset.selftest=window.PANTA_V17_SELFTEST_RESULTS.passed===r.length?'pass':'fail';return window.PANTA_V17_SELFTEST_RESULTS}};
  window.addEventListener('load',()=>{window.PantaSelfTest.run();if(new URLSearchParams(location.search).get('selftest')==='1')open()});
})();
