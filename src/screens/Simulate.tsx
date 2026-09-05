import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ImpactTrace } from '../components/CausalTrace';
import { caseReadingById, formatCount, formatRemaining, normalizeSimulationEffects, questionById, simulationImpactCounts, workstreamById } from '../app/selectors';

export function Simulate(){
  const {snapshot,focusedQuestionId,focusedWorkstreamId,simulationResult,runSimulation,clearSimulation,setActiveObject,simulationRunning}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const workstream=workstreamById(snapshot,focusedWorkstreamId)??snapshot.workstreams[0];
  const question=questionById(snapshot,focusedQuestionId)??snapshot.questions.find(t=>t.workstreamId===workstream?.id);
  const reading=question?caseReadingById(snapshot,question.currentCaseReadingId):undefined;
  const options=snapshot.simulationOptions.filter(x=>!question||x.originObjectId===question.id||x.originObjectId===reading?.id);
  const [optionId,setOptionId]=useState<string|undefined>(options.find(x=>x.enabled)?.id??options[0]?.id);
  const option=options.find(x=>x.id===optionId);
  const effects=useMemo(()=>normalizeSimulationEffects(simulationResult?.effects??[]),[simulationResult]);
  const impactCounts=useMemo(()=>simulationImpactCounts(effects),[effects]);
  const [selectedImpactId,setSelectedImpactId]=useState<string|undefined>();
  const selectedImpact=effects.find(e=>e.objectId===selectedImpactId)??effects.find(e=>e.state!=='HOLDS');

  const run=async()=>{if(!option)return;const result=await runSimulation({optionId:option.id,originObjectId:option.originObjectId,assumption:option.assumption});setSelectedImpactId(result?.effects.find(e=>e.state!=='HOLDS')?.objectId)};
  return <main className="p-page p-sim-page">
    <section className="p-sim-setup">
      <div><div className="p-kicker">Simulation</div><h1>{option?.label??'Choose a test outcome'}</h1>{reading&&<p>Current: {reading.text}</p>}</div>
      <div className="p-sim-controls"><div className="p-outcome-choices">{options.map(o=><button key={o.id} aria-pressed={o.id===optionId} disabled={!o.enabled||simulationRunning} className={o.id===optionId?'is-selected':''} onClick={()=>{setOptionId(o.id);clearSimulation()}}>{o.label.replace(/^What if /,'').replace(/\?$/,'')}</button>)}</div>{simulationResult?<><button className="p-btn" onClick={()=>clearSimulation()}>Reset</button><span className="p-sandbox-note">Live case unchanged</span></>:<><button className="p-btn p-btn-primary" disabled={!option?.enabled||simulationRunning} onClick={()=>void run()}>{simulationRunning?'Running impact trace…':'Run impact trace'}</button><span className="p-sandbox-note">Live case unchanged</span></>}</div>
    </section>

    {!simulationResult&&<section className="p-sim-baseline"><div className="p-section-heading"><strong>Current case baseline</strong><span>before the hypothetical</span></div>{snapshot.workstreams.map(w=>{const r=caseReadingById(snapshot,w.currentCaseReadingId);return <div key={w.id} className={`p-baseline-row ${w.id===workstream?.id?'is-origin':''}`}><strong>{w.name}</strong><span>{r?.text??'No current reading'}</span></div>})}</section>}

    {simulationResult&&<><section className="p-sim-trust"><div><strong>Case: {impactCounts.changed} changed · {impactCounts.held} held</strong><span>{formatCount(impactCounts.total,'mapped object')} shown</span></div><small>Current mapped case only{simulationResult.coverage.unmappedCount?` · ${formatRemaining(simulationResult.coverage.unmappedCount,'unmapped relationship')}`:''}</small></section>
      <ImpactTrace
        title="How the effect travels"
        originLabel={option?.label??'Simulation hypothesis'}
        originDetail={option?.assumption}
        effects={effects.map(effect=>({...effect,before:effect.before??currentObjectState(snapshot,effect.objectId)}))}
        currentLabel="Current"
        changedLabel="Simulated"
        selectedObjectId={selectedImpact?.objectId}
        onSelect={objectId=>{setSelectedImpactId(objectId);void setActiveObject(objectId)}}
      />
      <p className="p-impact-human">The live case and the investment decision remain unchanged.</p></>}
  </main>;
}
function currentObjectState(snapshot:any,id:string){const reading=caseReadingById(snapshot,id);if(reading)return reading.text;const workstream=snapshot.workstreams.find((item:any)=>item.id===id);if(workstream)return caseReadingById(snapshot,workstream.currentCaseReadingId)?.text??workstream.name;return 'Current mapped state'}
