import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { HumanPositionNote } from '../components/HumanPositionNote';
import { unknownById, objectLabel, humanPositionsForScope, caseReadingById, supportSummary, questionById, workstreamById } from '../app/selectors';
import { goTo } from '../app/routes';

export function Trace(){
  const {snapshot,focusedQuestionId,focusedWorkstreamId,setActiveObject,openSource}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const workstream=workstreamById(snapshot,focusedWorkstreamId)??snapshot.workstreams[0];
  const question=questionById(snapshot,focusedQuestionId)??snapshot.questions.find(t=>t.workstreamId===workstream?.id);
  if(!question)return <EmptyCase/>;
  const reading=caseReadingById(snapshot,question.currentCaseReadingId); if(!reading)return <EmptyCase/>;
  const supports=reading.supportObjectIds;
  const [selectedSupportId,setSelectedSupportId]=useState<string|undefined>(supports[0]);
  const [excluded,setExcluded]=useState<string[]>([]);
  const activeSupports=supports.filter(id=>!excluded.includes(id));
  const selectedClaim=snapshot.claims.find(e=>e.id===selectedSupportId);
  const selectedSource=selectedClaim?.sourceId?snapshot.sources.find(s=>s.id===selectedClaim.sourceId):snapshot.sources.find(s=>s.id===selectedSupportId);
  const selectedFinding=snapshot.findings.find(f=>f.id===selectedSupportId);
  const selectedPosition=snapshot.humanPositions.find(p=>p.id===selectedSupportId);
  const stats=useMemo(()=>supportSummary(snapshot,{...reading,supportObjectIds:activeSupports}),[snapshot,reading,activeSupports]);
  const unknowns=reading.unknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);
  const humanPositions=humanPositionsForScope(snapshot,[question.id,reading.id]);
  const testWithout=async()=>{
    if(!selectedSupportId)return;
    const next=excluded.includes(selectedSupportId)?excluded.filter(x=>x!==selectedSupportId):[...excluded,selectedSupportId];
    setExcluded(next);
    await setActiveObject(reading.id,{excludeObjectIds:next});
  };

  return <main className="p-page p-trace-page">
    <section className="p-trace-summary">
      <div><h1>{stats.independent===0?'No independent evidence':`${stats.independent} independent support${stats.independent===1?'':'s'}`}</h1><p>{stats.total} current support{stats.total===1?'':'s'} · {reading.relatedObjectIds.length} places in the case rely on it</p>{unknowns[0]&&<p className="p-trace-gap"><span>Still missing</span>{unknowns[0]!.title}</p>}</div>
      <div className="p-trace-state">{humanState(reading.epistemicStatus)}{reading.computedAt&&<span>{reading.computedAt}</span>}</div>
    </section>

    {excluded.length>0&&<div className="p-basis-test"><strong>Temporary basis test</strong><span>{activeSupports.length} support{activeSupports.length===1?'':'s'} remain · live case unchanged</span><button onClick={()=>{setExcluded([]);void setActiveObject(undefined)}}>Reset</button></div>}

    <section className="p-trace-field">
      <aside className="p-trace-supports">
        <div className="p-section-heading"><strong>What supports this</strong><span>{supports.length}</span></div>
        {supports.map(id=>{
          const evidence=snapshot.claims.find(e=>e.id===id); const finding=snapshot.findings.find(f=>f.id===id); const position=snapshot.humanPositions.find(p=>p.id===id);
          const title=evidence?.label??finding?.title??position?.text??objectLabel(snapshot,id);
          const meta=evidence?(reading.independentSupportObjectIds.includes(id)?'Independent evidence':evidence.type):finding?'PANTA finding':position?'Human view':'';
          return <button key={id} className={`p-trace-support ${selectedSupportId===id?'is-selected':''} ${excluded.includes(id)?'is-excluded':''}`} onClick={()=>setSelectedSupportId(id)}><strong>{title}</strong>{meta&&<span>{meta}</span>}</button>
        })}
      </aside>

      <section className="p-source-aperture">
        {selectedClaim&&<><div className="p-source-aperture-head"><div><strong>{selectedSource?.title??selectedClaim.label}</strong><span>{selectedSource?.occurredAt??selectedClaim.type}</span></div>{selectedSource&&<button className="p-shell-link" onClick={()=>openSource(selectedSource.id)}>Open source</button>}</div>{selectedClaim.contribution&&<p>{selectedClaim.contribution}</p>}{selectedClaim.excerpt&&<blockquote>“{selectedClaim.excerpt}”</blockquote>}{selectedClaim.limitation&&<div className="p-source-limit"><span>What this doesn't prove</span><p>{selectedClaim.limitation}</p></div>}</>}
        {selectedFinding&&<><div className="p-source-aperture-head"><strong>{selectedFinding.title}</strong><span>PANTA finding</span></div><p>{selectedFinding.proposition}</p><div className="p-source-limit"><span>How PANTA found this</span>{selectedFinding.derivationObjectIds.map(id=><button key={id} onClick={()=>void setActiveObject(id)}>{objectLabel(snapshot,id)}</button>)}</div></>}
        {selectedPosition&&<HumanPositionNote position={selectedPosition}/>} 
        {!selectedClaim&&!selectedFinding&&!selectedPosition&&<p className="p-muted">Select a mapped support object.</p>}
        {selectedSupportId&&<button className="p-btn p-test-without" onClick={()=>void testWithout()}>{excluded.includes(selectedSupportId)?'Restore this support':'Test without this'}</button>}
      </section>

      <section className="p-trace-reading">
        <div className="p-provenance-rule" aria-hidden="true"/>
        <h2>{reading.text}</h2>{reading.supportingLine&&<p>{reading.supportingLine}</p>}
        <div className="p-action-row"><button className="p-btn" onClick={()=>goTo('simulate')}>Simulate</button><button className="p-btn" onClick={()=>goTo('resolve')}>Resolve</button></div>
        {humanPositions.map(p=><HumanPositionNote key={p.id} position={p}/>) }
      </section>

      <aside className="p-trace-matters">
        <div className="p-section-heading"><strong>Where this matters</strong><span>{reading.relatedObjectIds.length}</span></div>
        {reading.relatedObjectIds.map(id=><button key={id} className="p-consequence-row" onClick={()=>void setActiveObject(id)}><strong>{objectLabel(snapshot,id)}</strong><span>{relationReason(snapshot,reading.id,id)}</span></button>)}
      </aside>
    </section>
  </main>;
}
function humanState(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
function relationReason(snapshot:any,from:string,to:string){return snapshot.relations.find((r:any)=>r.sourceObjectId===from&&r.targetObjectId===to)?.rationale??''}
