import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { caseReadingById, questionById, workstreamById } from '../app/selectors';

export function Simulate(){
  const {snapshot,focusedQuestionId,focusedWorkstreamId,simulationResult,runSimulation,clearSimulation,setActiveObject}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const workstream=workstreamById(snapshot,focusedWorkstreamId)??snapshot.workstreams[0];
  const question=questionById(snapshot,focusedQuestionId)??snapshot.questions.find(t=>t.workstreamId===workstream?.id);
  const reading=question?caseReadingById(snapshot,question.currentCaseReadingId):undefined;
  const options=snapshot.simulationOptions.filter(x=>!question||x.originObjectId===question.id||x.originObjectId===reading?.id);
  const [optionId,setOptionId]=useState<string|undefined>(options.find(x=>x.enabled)?.id??options[0]?.id);
  const option=options.find(x=>x.id===optionId);
  const effects=simulationResult?.effects??[];
  const effectMap=useMemo(()=>new Map(effects.map(e=>[e.objectId,e])),[effects]);
  const [selectedImpactId,setSelectedImpactId]=useState<string|undefined>();
  const selectedImpact=effects.find(e=>e.objectId===selectedImpactId)??effects.find(e=>e.state!=='HOLDS');

  const run=async()=>{if(!option)return;const result=await runSimulation({optionId:option.id,originObjectId:option.originObjectId,assumption:option.assumption});setSelectedImpactId(result?.effects.find(e=>e.state!=='HOLDS')?.objectId)};
  return <main className="p-page p-sim-page">
    <section className="p-sim-setup">
      <div><div className="p-kicker">Simulation</div><h1>{option?.label??'Choose a test outcome'}</h1>{reading&&<p>Current: {reading.text}</p>}</div>
      <div className="p-sim-controls"><div className="p-outcome-choices">{options.map(o=><button key={o.id} disabled={!o.enabled} className={o.id===optionId?'is-selected':''} onClick={()=>{setOptionId(o.id);clearSimulation()}}>{o.label.replace(/^What if /,'').replace(/\?$/,'')}</button>)}</div>{simulationResult?<><button className="p-btn" onClick={()=>clearSimulation()}>Reset</button><span className="p-sandbox-note">Live case unchanged</span></>:<><button className="p-btn p-btn-primary" disabled={!option?.enabled} onClick={()=>void run()}>Run impact trace</button><span className="p-sandbox-note">Live case unchanged</span></>}</div>
    </section>

    {!simulationResult&&<section className="p-sim-baseline"><div className="p-section-heading"><strong>Current case baseline</strong><span>before the hypothetical</span></div>{snapshot.workstreams.map(w=>{const r=caseReadingById(snapshot,w.currentCaseReadingId);return <div key={w.id} className={`p-baseline-row ${w.id===workstream?.id?'is-origin':''}`}><strong>{w.name}</strong><span>{r?.text??'No current reading'}</span></div>})}</section>}

    {simulationResult&&<><section className="p-sim-trust"><div><strong>Case: {simulationResult.coverage.changedCount} changed · {simulationResult.coverage.heldCount} held</strong><span>{simulationResult.coverage.examinedCount} scoped objects evaluated</span></div><small>Current mapped case only{simulationResult.coverage.unmappedCount?` · ${simulationResult.coverage.unmappedCount} unmapped relationship${simulationResult.coverage.unmappedCount===1?'':'s'} remain`:''}</small></section>
      <section className="p-sim-field">
        <div className="p-sim-case"><div className="p-section-heading"><strong>Case impact</strong><span>current → simulated</span></div>{snapshot.workstreams.map(w=>{const r=caseReadingById(snapshot,w.currentCaseReadingId);const effect=effectMap.get(w.id)??effectMap.get(w.currentCaseReadingId);return <button key={w.id} className={`p-impact-row ${effect&&effect.state!=='HOLDS'?'is-changed':'is-held'} ${selectedImpact?.objectId===effect?.objectId?'is-selected':''}`} onClick={()=>{if(effect){setSelectedImpactId(effect.objectId);void setActiveObject(effect.objectId)}}}><div><strong>{w.name}</strong>{effect&&<span>{humanState(effect.state)}</span>}</div>{effect&&effect.state!=='HOLDS'?<div className="p-impact-diff"><span><small>Current</small>{effect.before??r?.text}</span><b>→</b><span><small>Simulated</small>{effect.after??'Changed under scenario'}</span></div>:<p>{r?.text}</p>}<small>{effect?reasonText(snapshot,effect.reasonRelationIds):'No mapped effect.'}</small></button>})}</div>
        <aside className="p-impact-spine"><div className="p-section-heading"><strong>How the effect travels</strong><span>{effects.filter(e=>!snapshot.workstreams.some(w=>w.id===e.objectId||w.currentCaseReadingId===e.objectId)).length} downstream</span></div><div className="p-impact-origin"><span>Hypothesis</span><strong>{option?.assumption}</strong></div>{effects.filter(e=>!snapshot.workstreams.some(w=>w.id===e.objectId||w.currentCaseReadingId===e.objectId)).map(e=><button key={e.objectId} className={`p-impact-step ${selectedImpact?.objectId===e.objectId?'is-selected':''}`} onClick={()=>{setSelectedImpactId(e.objectId);void setActiveObject(e.objectId)}}><span>{humanState(e.state)}</span><strong>{e.objectLabel}</strong><p>{e.after??e.before}</p><small>{reasonText(snapshot,e.reasonRelationIds)}</small></button>)}<div className="p-impact-human">The investment decision remains human.</div></aside>
      </section></>}
  </main>;
}
function humanState(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
function reasonText(snapshot:any,ids:string[]){return ids.map(id=>snapshot.relations.find((r:any)=>r.id===id)?.rationale).filter(Boolean).join(' · ')}
