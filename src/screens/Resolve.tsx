import React, { useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { unknownById, workItemById, actorById, caseReadingById, questionById, workstreamById, workItemDisplayState, formatCount } from '../app/selectors';

export function Resolve(){
  const {snapshot,focusedQuestionId,focusedWorkstreamId,execute,actor,setActiveObject,pendingAction}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const workstream=workstreamById(snapshot,focusedWorkstreamId)??snapshot.workstreams[0];
  const question=questionById(snapshot,focusedQuestionId)??snapshot.questions.find(t=>t.workstreamId===workstream?.id);
  if(!question)return <EmptyCase/>;
  const reading=caseReadingById(snapshot,question.currentCaseReadingId); if(!reading)return <EmptyCase/>;
  const routes=question.workItemIds.map(id=>workItemById(snapshot,id)).filter(Boolean)!;
  const [selectedId,setSelectedId]=useState(routes.find(m=>m?.kind==='PANTA_PROPOSAL')?.id??routes[0]?.id);
  const [editing,setEditing]=useState(false);
  const [proposalText,setProposalText]=useState('');
  const selected=routes.find(m=>m?.id===selectedId);
  const unknowns=question.openUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);
  const canAdopt=actor?.entitlements.includes('ADOPT_WORK_ITEM')??false;
  const canAssign=actor?.entitlements.includes('ASSIGN_WORK_ITEM')??false;

  return <main className="p-page p-resolve-page">
    <section className="p-resolve-head"><div><div className="p-kicker">Resolve</div><h1>Close the evidence gap</h1><p>{reading.text}</p></div><div className="p-resolve-summary"><strong>{formatCount(routes.length,'evidence route')}</strong><span>{routes.filter(m=>m?.status==='ACTIVE'||m?.status==='BLOCKED').length} active · {routes.filter(m=>m&&!m.ownerActorId&&m.status!=='COMPLETED'&&m.status!=='CANCELLED'&&m.kind!=='PANTA_PROPOSAL').length} unassigned · {formatCount(routes.filter(m=>m?.kind==='PANTA_PROPOSAL'&&m?.status==='PROPOSED').length,'PANTA proposal')}</span></div></section>

    <section className="p-resolve-target"><div className="p-section-heading"><strong>What would materially reduce this uncertainty</strong></div><div className="p-resolution-criteria">{(question.resolutionCriteria??unknowns.map(g=>g!.title)).map((x,i)=><div key={x}><span>{String(i+1).padStart(2,'0')}</span><p>{x}</p></div>)}</div>{unknowns[0]&&<div className="p-current-gap"><strong>Current gap</strong><span>{unknowns[0]!.title}</span></div>}</section>

    <section className="p-mission-field">
      <div className="p-mission-routes"><div className="p-section-heading"><strong>Evidence routes</strong><span>{routes.length}</span></div>{routes.map((m,i)=>{if(!m)return null;const owner=actorById(snapshot,m.ownerActorId);return <button key={m.id} aria-pressed={selectedId===m.id} disabled={Boolean(pendingAction)} className={`p-mission-route ${selectedId===m.id?'is-selected':''}`} onClick={()=>setSelectedId(m.id)}><span className="p-route-index">{String(i+1).padStart(2,'0')}</span><div><strong>{m.name}</strong><small>{owner?.displayName??workItemDisplayState(m)}</small></div><p>{m.whatToObtain??'Claim route'}</p><b>→</b></button>})}</div>

      {selected&&<aside className="p-mission-aperture"><div className="p-kicker">Selected route</div><h2>{selected.name}</h2>{selected.kind==='PANTA_PROPOSAL'&&<p className="p-proposal-state">PANTA proposal · not adopted</p>}<Detail title="What to obtain">{editing?<textarea className="p-input" disabled={Boolean(pendingAction)} value={proposalText || selected.whatToObtain || ''} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>)=>setProposalText(e.target.value)}/>:selected.whatToObtain??'Evidence to obtain is not yet mapped.'}</Detail><Detail title="What this can change">{selected.canChangeObjectIds.length?selected.canChangeObjectIds.map(id=><button key={id} className="p-related-link" disabled={Boolean(pendingAction)} onClick={()=>void setActiveObject(id)}>{label(snapshot,id)}</button>):'No mapped case object.'}</Detail><Detail title="What would still remain open">{selected.remainingUnknownIds.length?selected.remainingUnknownIds.map(id=><button key={id} className="p-related-link" disabled={Boolean(pendingAction)} onClick={()=>void setActiveObject(id)}>{unknownById(snapshot,id)?.title??id}</button>):'No additional mapped gap.'}</Detail><div className="p-human-boundary"><strong>Requires human authority</strong><p>Adopting the route does not authorize external contact or spend.</p></div><div className="p-action-row">{selected.kind==='PANTA_PROPOSAL'&&selected.status==='PROPOSED'&&<>{editing?<><button className="p-btn p-btn-primary" disabled={Boolean(pendingAction)} onClick={()=>void execute({type:'UPDATE_WORK_ITEM_PROPOSAL',workItemId:selected.id,whatToObtain:proposalText || selected.whatToObtain || ''}).then(saved=>{if(saved)setEditing(false)})}>{pendingAction==='UPDATE_WORK_ITEM_PROPOSAL'?'Saving…':'Save proposal'}</button><button className="p-btn" disabled={Boolean(pendingAction)} onClick={()=>setEditing(false)}>Cancel</button></>:<><button className="p-btn p-btn-primary" disabled={!canAdopt||Boolean(pendingAction)} onClick={()=>void execute({type:'ADOPT_WORK_ITEM',workItemId:selected.id})}>Adopt this route</button><button className="p-btn" disabled={Boolean(pendingAction)} onClick={()=>{setProposalText(selected.whatToObtain||'');setEditing(true)}}>Edit</button><button className="p-btn p-btn-quiet" disabled={Boolean(pendingAction)} onClick={()=>void execute({type:'DISMISS_WORK_ITEM_PROPOSAL',workItemId:selected.id})}>Dismiss</button></>}</>}{!selected.ownerActorId&&selected.kind!=='PANTA_PROPOSAL'&&selected.status!=='COMPLETED'&&selected.status!=='CANCELLED'&&<button className="p-btn p-btn-primary" disabled={!canAssign||!snapshot.actors[0]||Boolean(pendingAction)} onClick={()=>snapshot.actors[0]&&void execute({type:'ASSIGN_WORK_ITEM',workItemId:selected.id,ownerActorId:snapshot.actors[0].id})}>Assign owner</button>}</div></aside>}
    </section>
  </main>;
}
function Detail({title,children}:{title:string;children:React.ReactNode}){return <section className="p-route-detail-block"><strong>{title}</strong><div>{children}</div></section>}
function humanState(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
function label(s:any,id:string){return s.workstreams.find((x:any)=>x.id===id)?.name??s.questions.find((x:any)=>x.id===id)?.name??s.caseReadings.find((x:any)=>x.id===id)?.text??s.quantities.find((x:any)=>x.id===id)?.label??id}
