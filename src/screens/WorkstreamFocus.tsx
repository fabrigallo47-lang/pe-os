import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ObjectLens } from '../components/ObjectLens';
import { HumanPositionNote } from '../components/HumanPositionNote';
import { eventById, eventDisplayLabel, unknownById, workItemById, actorById, humanPositionsForScope, caseReadingById, supportSummary, workItemDisplayState } from '../app/selectors';
import { goTo } from '../app/routes';

export function WorkstreamFocus() {
  const { snapshot, focusedWorkstreamId, focusedQuestionId, setFocusedQuestion, setActiveObject } = usePanta();
  const workstream = snapshot?.workstreams.find(w=>w.id===focusedWorkstreamId) ?? snapshot?.workstreams[0];
  const questions = snapshot?.questions.filter(t=>t.workstreamId===workstream?.id) ?? [];
  const [selectedId,setSelectedId]=useState<string|undefined>(focusedQuestionId ?? questions[0]?.id);
  useEffect(()=>{if(focusedQuestionId)setSelectedId(focusedQuestionId);else if(!questions.some(t=>t.id===selectedId))setSelectedId(questions[0]?.id)},[focusedQuestionId,questions,selectedId]);
  if(!snapshot||!workstream)return <EmptyCase/>;
  const wsReading=caseReadingById(snapshot,workstream.currentCaseReadingId);
  const selected=questions.find(t=>t.id===selectedId) ?? questions[0];
  const selectedReading=selected?caseReadingById(snapshot,selected.currentCaseReadingId):undefined;
  const owner=actorById(snapshot,workstream.ownerActorId);
  const relevantFindings=snapshot.findings.filter(f=>f.affectedObjectIds.some(id=>id===workstream.id||questions.some(t=>t.id===id))).slice(0,2);
  const enter=(route:'trace'|'simulate'|'resolve')=>{if(selected)goTo(route,{workstreamId:workstream?.id,questionId:selected.id})};

  return <main className="p-page p-workstream-page">
    <section className="p-ws-head">
      <div><div className="p-kicker">{workstream.name}</div>{wsReading&&<button className="p-reading p-unboxed-select" onClick={()=>void setActiveObject(wsReading.id)}>{wsReading.text}</button>}{wsReading?.supportingLine&&<p className="p-subtitle">{wsReading.supportingLine}</p>}</div>
      <div className="p-ws-now"><span className="p-kicker">Current work</span>{workstream.activeWorkItemIds.slice(0,2).map(id=>{const m=workItemById(snapshot,id);return m?<button key={id} onClick={()=>void setActiveObject(id)}>{m.name}</button>:null})}{owner&&<small>{owner.displayName}</small>}</div>
    </section>

    {!!relevantFindings.length&&<section className="p-ws-finding-line"><strong>New in this workstream</strong>{relevantFindings.map(f=><button key={f.id} onClick={()=>void setActiveObject(f.id)}>{f.proposition}<small>PANTA found</small></button>)}</section>}

    <section className="p-question-index" aria-label="Reasoning questions">
      {questions.map(t=>{const r=caseReadingById(snapshot,t.currentCaseReadingId);const ss=r?supportSummary(snapshot,r):{total:0,independent:0};const gap=unknownById(snapshot,t.openUnknownIds[0]);return <button key={t.id} aria-pressed={selected?.id===t.id} className={selected?.id===t.id?'is-selected':''} onClick={()=>{setSelectedId(t.id);setFocusedQuestion(t.id);void setActiveObject(undefined)}}><strong>{t.name}</strong><span>{humanState(t.questionStatus)}</span>{r&&<small>{r.text}</small>}<em>{ss.independent?`${ss.independent} independent`:'No independent evidence'}{gap?` · ${gap.title}`:''}</em></button>})}
    </section>

    {selected&&selectedReading&&<section className="p-ws-focus">
      <div className="p-ws-focus-reading"><div className="p-kicker">Selected question</div><button className="p-reading p-unboxed-select" onClick={()=>void setActiveObject(selectedReading.id)}>{selectedReading.text}</button>{selectedReading.supportingLine&&<p>{selectedReading.supportingLine}</p>}<div className="p-action-row"><button className="p-btn" onClick={()=>enter('trace')}>Trace</button><button className="p-btn p-btn-primary" onClick={()=>enter('simulate')}>Simulate</button><button className="p-btn" onClick={()=>enter('resolve')}>Resolve</button></div>{humanPositionsForScope(snapshot,[selected.id,selectedReading.id]).map(p=><HumanPositionNote key={p.id} position={p}/>)}</div>
      <div className="p-ws-focus-detail">
        <FocusColumn title="What supports this">{selected.claimIds.map(id=>{const e=snapshot.claims.find(x=>x.id===id);return e?<button key={id} className="p-focus-row" onClick={()=>void setActiveObject(id)}><strong>{e.label}</strong><span>{e.contribution}</span><small>{selectedReading.independentSupportObjectIds.includes(id)?'Independent evidence':'Not independent'}</small></button>:null})}</FocusColumn>
        <FocusColumn title="Where this matters">{selectedReading.relatedObjectIds.map(id=><button key={id} className="p-focus-row" onClick={()=>void setActiveObject(id)}><strong>{label(snapshot,id)}</strong></button>)}</FocusColumn>
        <FocusColumn title="Work that can resolve it">{selected.workItemIds.map(id=>{const m=workItemById(snapshot,id);const p=actorById(snapshot,m?.ownerActorId);return m?<button key={id} className="p-focus-row" onClick={()=>void setActiveObject(id)}><strong>{m.name}</strong><span>{p?.displayName ?? workItemDisplayState(m)}</span>{m.kind==='PANTA_PROPOSAL'&&<small>PANTA proposal · not adopted</small>}</button>:null})}</FocusColumn>
      </div>
    </section>}

    {!!selected?.chronologyEventIds.length&&<section className="p-ws-evolution"><div className="p-section-heading"><strong>How this reading changed</strong><span className="p-meta">select a moment to replay the case</span></div><div className="p-time-ribbon">{selected.chronologyEventIds.map(id=>{const e=eventById(snapshot,id);return e?<button key={id} className="p-time-node" onClick={()=>goTo('replay',{asOf:e.knownAt})}><span>{e.effectiveAt??e.knownAt}</span><strong>{eventDisplayLabel(snapshot,e)}</strong><small>Open in Replay</small></button>:null})}</div></section>}

    <div className="p-floating-lens"><ObjectLens compact/></div>
  </main>;
}

function FocusColumn({title,children}:{title:string;children:React.ReactNode}){return <div className="p-focus-column"><strong>{title}</strong><div>{children}</div></div>}
function humanState(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
function label(snapshot:any,id:string){return snapshot.workstreams.find((x:any)=>x.id===id)?.name??snapshot.questions.find((x:any)=>x.id===id)?.name??snapshot.workItems.find((x:any)=>x.id===id)?.name??snapshot.unknowns.find((x:any)=>x.id===id)?.title??snapshot.quantities.find((x:any)=>x.id===id)?.label??snapshot.caseReadings.find((x:any)=>x.id===id)?.text??id}
