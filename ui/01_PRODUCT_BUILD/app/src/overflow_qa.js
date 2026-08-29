(function(){
  'use strict';
  const params=new URLSearchParams(location.search);
  const enabled=params.get('qa')==='overflow';
  const long=(kind,index)=>`${kind}-${String(index).padStart(3,'0')}-${'institutional-provenance-and-underwriting-context-'.repeat(4)}${index}`;
  const clone=value=>JSON.parse(JSON.stringify(value));
  const sources=()=>Array.from({length:36},(_,index)=>({
    source_id:`QA-SOURCE-${index}`,
    name:`${long('source-file',index)}.xlsx`,
    file_name:`${long('source-file',index)}.xlsx`,
    status:'INGESTED',
    type:'QA fixture',
    claim_count:4,
    latest_version_id:`sha256:${long('version',index)}`,
    ingested_at:new Date(Date.UTC(2026,7,29,10,index%60)).toISOString(),
    versions:[{version_id:`QA-VERSION-${index}`,known_at:'2026-08-29T10:00:00Z'}],
  }));
  const inbox=()=>Array.from({length:48},(_,index)=>({
    id:`QA-INTAKE-${index}`,
    job_id:`QA-JOB-${index}`,
    case_id:PantaStore.get().caseId||'keystone',
    name:`${long('incoming-source',index)}.${index%4===0?'pdf':index%4===1?'txt':index%4===2?'md':'xlsx'}`,
    path:`vault/inbox/${long('durable-source-path',index)}`,
    status:index%9===0?'ERROR':'COMPLETE',
    stage:index%9===0?'Failed':'Proposal ready',
    admission_status:index%3===0?'PENDING_REVIEW':null,
    proposed_claim_count:12+index,
    size:2000+index,
    uploaded_at:'2026-08-29T10:00:00Z',
    message:long('high-cardinality-ingest-message',index),
  }));
  const claims=()=>Array.from({length:120},(_,index)=>({
    claim_id:`QA-CLAIM-${index}`,
    id:`QA-CLAIM-${index}`,
    statement:`${long('claim',index)} — a deliberately long assertion used to verify wrapping, local scrolling and accessible inspection without changing production data.`,
    value:index,
    unit:index%2?'%':'days',
    source_id:`QA-SOURCE-${index%36}`,
    locator:`Workbook with a deliberately long name ${long('locator',index)}::Operating Model!row-${index}`,
    period:`FY20${26+index%4}`,
    perimeter:long('consolidated-perimeter',index),
    epistemic_class:'asserted',
    direction:'CONTEXT',
    bears_on:[],
  }));
  const foundations=()=>Array.from({length:24},(_,index)=>({
    id:`QA-FOUNDATION-${index}`,
    label:long('load-bearing-foundation',index),
    economic:`${long('economic-consequence',index)} with enough content to exercise nested card wrapping and vertical scroll ownership.`,
    strength:index%4===0?'CONTESTED':index%3===0?'WEAK':'STRONG',
    evidence_options:Array.from({length:8},(_,option)=>({
      claim_id:`QA-CLAIM-${(index*5+option)%120}`,
      value:index*10+option,
      unit:'%',
      definition_id:long('definition',option),
      perimeter:long('perimeter',option),
      relation:option%3===0?'CONTRADICTS':'SUPPORTS',
    })),
  }));
  function apply(){
    if(!enabled)return false;
    const state=PantaStore.get();
    if(!state.projection)return false;
    const next={};
    if(!state.projection.deal?.qa_overflow_fixture){
      const projection=clone(state.projection),deal=projection.deal;
      deal.qa_overflow_fixture=true;
      deal.claims=[...(deal.claims||[]),...claims()];
      deal.source_center=deal.source_center||{};
      deal.source_center.sources=[...(deal.source_center.sources||[]),...sources()];
      deal.source_center.inbox=[...(deal.source_center.inbox||[]),...inbox()];
      deal.rooms=deal.rooms||{};
      deal.rooms.foundations=deal.rooms.foundations||{};
      deal.rooms.foundations.sets=[...(deal.rooms.foundations.sets||[]),...foundations()];
      next.projection=projection;
    }
    if((state.sources||[]).length<36)next.sources=sources();
    if((state.inbox||[]).length<48)next.inbox=inbox();
    if(Object.keys(next).length){PantaStore.set(next);document.body.dataset.qaFixture='overflow';return true}
    return false;
  }
  function run(){
    const check=(name,pass,detail)=>({name,status:pass?'PASS':'FAIL',detail});
    const root=document.documentElement,workspace=document.querySelector('.workspace-content');
    const results=[
      check('No document-level horizontal overflow',root.scrollWidth<=innerWidth+1,`${root.scrollWidth}/${innerWidth}`),
      check('Workspace is width-contained',!workspace||workspace.scrollWidth<=workspace.clientWidth+1,workspace?`${workspace.scrollWidth}/${workspace.clientWidth}`:'not rendered'),
    ];
    document.querySelectorAll('.table-scroll,.foundation-nodes,.source-grid,.batch-list,.unknown-list,.registry-list').forEach((node,index)=>{
      const style=getComputedStyle(node),owns=['auto','scroll'].includes(style.overflowX)||['auto','scroll'].includes(style.overflowY);
      results.push(check(`Overflow owner ${index+1}`,owns||node.scrollWidth<=node.clientWidth+1,`${node.className}: ${node.scrollWidth}×${node.scrollHeight} / ${node.clientWidth}×${node.clientHeight}`));
    });
    window.PANTA_OVERFLOW_QA_RESULTS=results;
    return results;
  }
  window.PantaOverflowQA={enabled,apply,run};
  if(enabled)PantaStore.subscribe(()=>queueMicrotask(apply));
})();
