import React, { useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { unknownById, caseReadingById, eventDisplayLabel, recordedDecision } from '../app/selectors';

export function ReplayDecision(){
  const {snapshot,moments,asOf,setAsOf,returnToCurrent,execute,actor,setActiveObject,pendingAction}=usePanta();
  const [pathId,setPathId]=useState<string>();
  const [rationale,setRationale]=useState('');
  const [conditions,setConditions]=useState('');
  if(!snapshot)return <EmptyCase/>;
  const current=!asOf;
  const canRecord=actor?.entitlements.includes('RECORD_DECISION')??false;
  const openConditions=snapshot.conditions.filter(c=>c.status==='OPEN');
  const selectedPath=snapshot.decisionPaths.find(p=>p.id===pathId);
  const recorded=recordedDecision(snapshot);

  return <main className="p-page p-replay-page">
    <section className="p-replay-head"><div><div className="p-kicker">Replay & Decision</div><h1>{current?'Current case':'Case as it stood then'}</h1><p>{current?'Inspect the present decision state or rewind the same case to a prior cutoff.':`Replay · ${snapshot.asOf}`}</p></div>{!current&&<button className="p-btn" onClick={()=>void returnToCurrent()}>Return to current</button>}</section>

    <section className="p-replay-rail">{moments.map(m=>{const selected=asOf?m.asOf===asOf:m.asOf===moments[moments.length-1]?.asOf;return <button key={m.id} aria-pressed={selected} disabled={Boolean(pendingAction)} className={selected?'is-selected':''} onClick={()=>void setAsOf(m.asOf===moments[moments.length-1]?.asOf?undefined:m.asOf)}><span>{m.label}</span>{m.eventId&&<small>{(()=>{const e=snapshot.events.find(e=>e.id===m.eventId);return e?eventDisplayLabel(snapshot,e):undefined})()}</small>}</button>})}</section>

    <section className="p-replay-field">
      <div className="p-replay-case"><div className="p-section-heading"><strong>{current?'Current case':'Replay · case as it stood then'}</strong><span>{snapshot.caseVersion}</span></div>{snapshot.workstreams.map(w=>{const r=caseReadingById(snapshot,w.currentCaseReadingId);const unknowns=w.openUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);return <article key={w.id} className="p-replay-case-row"><strong>{w.name}</strong><button onClick={()=>r&&void setActiveObject(r.id)}>{r?.text??'No reading'}</button><div>{unknowns[0]?<button onClick={()=>void setActiveObject(unknowns[0]!.id)}>{unknowns[0]!.title}</button>:<span>—</span>}</div></article>})}</div>

      <aside className="p-decision-rail"><div className="p-section-heading"><strong>{current?'What still stands between the case and a decision':'What was still decision-relevant'}</strong><span>{openConditions.length}</span></div>{openConditions.map((c,i)=><button key={c.id} className="p-frontier-item" onClick={()=>void setActiveObject(c.id)}><span>{String(i+1).padStart(2,'0')}</span><strong>{c.label}</strong></button>)}
        {current&&<section className="p-decision-desk"><div className="p-section-heading"><strong>Human decision paths</strong></div><div className="p-decision-paths">{snapshot.decisionPaths.map(p=><button key={p.id} aria-pressed={pathId===p.id} disabled={Boolean(pendingAction)} className={pathId===p.id?'is-selected':''} onClick={()=>setPathId(p.id)}>{humanPath(p.label)}</button>)}</div>{selectedPath&&<div className="p-decision-aperture"><strong>{humanPath(selectedPath.label)}</strong><p>{selectedPath.meaning}</p><textarea className="p-input" aria-label="Human rationale" disabled={Boolean(pendingAction)} placeholder="Human rationale" value={rationale} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>)=>setRationale(e.target.value)}/>{selectedPath.label==='COMMIT_WITH_CONDITIONS'&&<textarea className="p-input" aria-label="Decision conditions" disabled={Boolean(pendingAction)} placeholder="Conditions" value={conditions} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>)=>setConditions(e.target.value)}/>}<div className="p-meta">Snapshot: {snapshot.asOf} · {snapshot.caseVersion}</div><button className="p-btn p-btn-primary" disabled={!canRecord||!rationale.trim()||Boolean(pendingAction)} onClick={()=>void execute({type:'RECORD_DECISION',pathId:selectedPath.id,rationale,conditionText:conditions||undefined})}>{pendingAction==='RECORD_DECISION'?'Recording decision…':'Record institutional decision'}</button></div>}</section>}
        {recorded&&<section className="p-recorded-decision"><strong>Recorded decision</strong><p>{humanPath(snapshot.decisionPaths.find(p=>p.id===recorded.pathId)?.label??recorded.decision??'')}</p><small>{recorded.recordedAt} · snapshot {recorded.caseVersion}</small></section>}
      </aside>
    </section>
  </main>;
}
function humanPath(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
