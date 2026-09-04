import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ObjectLens } from '../components/ObjectLens';
import { CaseLifecycle } from '../components/CaseLifecycle';
import { eventById, eventDisplayLabel, caseReadingById, quantityDisplayState, recordedDecision } from '../app/selectors';
import type { Artifact, ArtifactBlock, Quantity } from '../types/domain';

const TABS=['IC_MEMO','MODEL','DECISION_PACK'] as const;
type OutputTab=typeof TABS[number];

export function Outputs(){
  const {snapshot,execute,actor,setActiveObject,pendingAction}=usePanta();
  const [tab,setTab]=useState<OutputTab>('IC_MEMO');
  const [mode,setMode]=useState<'READ'|'EDIT'>('READ');
  const [reviewDiff,setReviewDiff]=useState(false);
  if(!snapshot)return <EmptyCase/>;
  const artifact=snapshot.artifacts.find(a=>a.type===tab);
  const totalPending=snapshot.artifacts.reduce((n,a)=>n+a.pendingCaseChangeCount,0);
  const canSync=actor?.entitlements.includes('SYNC_ARTIFACT')??false;
  const canEdit=actor?.entitlements.includes('EDIT_ARTIFACT')??false;
  const diffCount=artifact?snapshot.artifactDiffs.filter(diff=>diff.artifactId===artifact.id).length:0;
  const hasDiffDetails=diffCount>0;
  const busy=Boolean(pendingAction);
  const sync=async()=>{if(!artifact)return;if(await execute({type:'SYNC_ARTIFACT',artifactId:artifact.id}))setReviewDiff(true)};
  const selectTab=(next:OutputTab)=>{setTab(next);setMode('READ');setReviewDiff(false);void setActiveObject(undefined)};
  const moveTab=(event:React.KeyboardEvent<HTMLDivElement>)=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const currentIndex=TABS.indexOf(tab);
    const nextIndex=event.key==='Home'?0:event.key==='End'?TABS.length-1:event.key==='ArrowRight'?(currentIndex+1)%TABS.length:(currentIndex-1+TABS.length)%TABS.length;
    const next=TABS[nextIndex];selectTab(next);window.requestAnimationFrame(()=>document.getElementById(`output-tab-${next}`)?.focus());
  };

  return <main className="p-page p-output-page">
    <header className="p-output-toolbar">
      <div className="p-output-tabs" role="tablist" aria-label="Outputs" onKeyDown={moveTab}>{TABS.map(t=><button key={t} id={`output-tab-${t}`} role="tab" aria-selected={tab===t} aria-controls={`output-panel-${t}`} tabIndex={tab===t?0:-1} className={tab===t?'is-active':''} onClick={()=>selectTab(t)}>{label(t)}</button>)}</div>
      <div className="p-output-actions">{artifact&&artifact.pendingCaseChangeCount>0&&<><button className="p-change-count" aria-pressed={hasDiffDetails?reviewDiff:undefined} disabled={!hasDiffDetails} title={!hasDiffDetails?'The backend did not provide artifact diff details':undefined} onClick={()=>setReviewDiff(x=>!x)}>{artifact.pendingCaseChangeCount} case change{artifact.pendingCaseChangeCount===1?'':'s'}</button>{!hasDiffDetails&&<span className="p-diff-unavailable">Change details unavailable</span>}</>}{artifact?<button className="p-btn p-btn-accent" disabled={!canSync||busy} onClick={()=>void sync()}>{pendingAction==='SYNC_ARTIFACT'?'Syncing…':'Sync with case'}</button>:<button className="p-btn p-btn-primary" disabled={!canEdit||busy} onClick={()=>void execute({type:'CREATE_ARTIFACT',artifactType:tab})}>Create from case</button>}{totalPending>0&&<button className="p-btn" disabled={!canSync||busy} onClick={()=>void execute({type:'SYNC_ALL_ARTIFACTS'})}>{pendingAction==='SYNC_ALL_ARTIFACTS'?'Syncing all…':'Sync all outputs'}</button>}{tab==='IC_MEMO'&&<div className="p-segmented" aria-label="Memo mode"><button aria-pressed={mode==='READ'} className={mode==='READ'?'is-active':''} onClick={()=>setMode('READ')}>Read</button><button aria-pressed={mode==='EDIT'} disabled={!canEdit||busy} className={mode==='EDIT'?'is-active':''} onClick={()=>setMode('EDIT')}>Edit</button></div>}</div>
    </header>

    <div id={`output-panel-${tab}`} role="tabpanel" aria-labelledby={`output-tab-${tab}`} tabIndex={0}>
      {tab==='IC_MEMO'&&<MemoSurface artifact={artifact} mode={mode} reviewDiff={reviewDiff}/>}
      {tab==='MODEL'&&<ModelSurface artifact={artifact} quantities={snapshot.quantities} reviewDiff={reviewDiff}/>}
      {tab==='DECISION_PACK'&&<DecisionPackSurface artifact={artifact} reviewDiff={reviewDiff}/>}
    </div>
  </main>;
}

function MemoSurface({artifact,mode,reviewDiff}:{artifact?:Artifact;mode:'READ'|'EDIT';reviewDiff:boolean}){
  const {snapshot,execute,setActiveObject,inspection,pendingAction}=usePanta();
  const blocks=artifact?.blockIds.map(id=>snapshot?.artifactBlocks.find(b=>b.id===id)).filter(Boolean) as ArtifactBlock[]|undefined;
  const [drafts,setDrafts]=useState<Record<string,string>>({});
  if(!snapshot)return <EmptyCase/>;
  if(!artifact)return <OutputEmpty title="IC Memo" artifactType="IC_MEMO"/>;
  const diffs=snapshot.artifactDiffs.filter(d=>d.artifactId===artifact.id);
  return <div className={`p-output-stage ${inspection?'has-lens':''}`}>
    <article className="p-memo-paper">
      <header className="p-memo-title-block"><div><h1>{artifact.title}</h1><span>Investment Committee Memorandum</span></div><div className="p-meta">{artifact.lastSyncedAt?`Synced · ${artifact.lastSyncedAt}`:'Connected to current case'}</div></header>
      {reviewDiff&&diffs.length>0&&<div className="p-sync-review"><strong>{diffs.length} synchronized change{diffs.length===1?'':'s'}</strong>{diffs.slice(0,4).map(d=>{const event=eventById(snapshot,d.causeEventId);return <div key={d.id} className="p-sync-change">{d.before&&<del>{d.before}</del>}<b>→</b>{d.after&&<ins>{d.after}</ins>}<small>{event?eventDisplayLabel(snapshot,event):'Case change'}</small></div>})}</div>}
      {reviewDiff&&!diffs.length&&<DiffUnavailable/>}
      <div className="p-memo-content">{blocks?.map((b,i)=><MemoBlock key={b.id} block={b} index={i+1} mode={mode} value={drafts[b.id]??b.text??''} disabled={Boolean(pendingAction)} onChange={text=>setDrafts(d=>({...d,[b.id]:text}))} onSave={text=>void execute({type:'UPDATE_ARTIFACT_BLOCK',artifactId:artifact.id,blockId:b.id,text})} onSelect={()=>void setActiveObject(b.boundObjectIds[0]??b.id)} onAccept={()=>void execute({type:'ACCEPT_ARTIFACT_SUGGESTION',artifactId:artifact.id,blockId:b.id})} onDismiss={()=>void execute({type:'DISMISS_ARTIFACT_SUGGESTION',artifactId:artifact.id,blockId:b.id})}/>)}</div>
    </article>
    {inspection&&<aside className="p-output-lens"><ObjectLens/></aside>}
  </div>;
}

function MemoBlock({block,index,mode,value,disabled,onChange,onSave,onSelect,onAccept,onDismiss}:{block:ArtifactBlock;index:number;mode:'READ'|'EDIT';value:string;disabled:boolean;onChange:(x:string)=>void;onSave:(x:string)=>void;onSelect:()=>void;onAccept:()=>void;onDismiss:()=>void}){
  return <section className={`p-memo-block ${block.authorship==='HUMAN_AUTHORED'?'is-human':''}`}><div className="p-memo-block-head"><span>{String(index).padStart(2,'0')}</span>{block.title&&<strong>{block.title}</strong>}{block.authorship==='HUMAN_AUTHORED'&&<small>Human-authored{block.recordedAt?` · ${block.recordedAt}`:''}</small>}</div>{mode==='EDIT'?<textarea className="p-memo-editor" disabled={disabled} value={value} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>)=>onChange(e.target.value)} onBlur={()=>onSave(value)}/>:<button className="p-memo-sentence" disabled={disabled} onClick={onSelect}>{block.text??'—'}</button>}{block.suggestion&&<aside className="p-anchored-suggestion"><strong>{block.suggestion.signal}</strong><p>{block.suggestion.suggestedText}</p><div className="p-action-row"><button className="p-btn p-btn-accent" disabled={disabled} onClick={onAccept}>Accept</button><button className="p-btn" disabled={disabled} onClick={onSelect}>Inspect why</button><button className="p-btn p-btn-quiet" disabled={disabled} onClick={onDismiss}>Dismiss</button></div></aside>}</section>;
}

function ModelSurface({artifact,quantities,reviewDiff}:{artifact?:Artifact;quantities:Quantity[];reviewDiff:boolean}){
  const {snapshot,setActiveObject,inspection}=usePanta();
  if(!snapshot)return <EmptyCase/>;
  const rows=(artifact?.quantityIds.length?artifact.quantityIds.map(id=>quantities.find(q=>q.id===id)).filter(Boolean):quantities) as Quantity[];
  if(!artifact&&!rows.length)return <OutputEmpty title="Model" artifactType="MODEL"/>;
  const diffs=artifact?snapshot.artifactDiffs.filter(d=>d.artifactId===artifact.id):[];
  return <div className={`p-output-stage ${inspection?'has-lens':''}`}><section className="p-model-sheet"><header className="p-model-head"><div><h1>{artifact?.title??'Case Model'}</h1><p>Mapped quantities only · unknown inputs remain unknown</p></div><span className="p-meta">Select a cell to inspect or simulate</span></header><div className="p-formula-bar"><b>fx</b><span>Object-aware financial surface</span></div><div className="p-model-grid p-model-grid-head"><span></span><span>Metric</span><span>Current value</span><span>Unit / scope</span><span>Case state</span></div>{rows.map((q,i)=><button key={q.id} className="p-model-grid p-model-row" onClick={()=>void setActiveObject(q.id)}><span>{i+1}</span><strong>{q.label}</strong><b>{q.display??q.value??'Not yet established'}</b><span>{q.unit??q.currency??q.perimeter.scope??'—'}</span><span>{quantityDisplayState(q)}</span></button>)}</section>{reviewDiff&&diffs.length>0&&<div className="p-inline-review">{diffs.map(d=><div key={d.id}>{d.before&&<del>{d.before}</del>}<b> → </b>{d.after&&<ins>{d.after}</ins>}</div>)}</div>}{reviewDiff&&!diffs.length&&<DiffUnavailable/>}{inspection&&<aside className="p-output-lens"><ObjectLens/></aside>}</div>;
}

function DecisionPackSurface({artifact,reviewDiff}:{artifact?:Artifact;reviewDiff:boolean}){
  const {snapshot,setActiveObject,inspection}=usePanta(); if(!snapshot)return <EmptyCase/>; if(!artifact)return <div><OutputEmpty title="Decision Pack" artifactType="DECISION_PACK"/><CaseLifecycle/></div>;
  const open=snapshot.conditions.filter(c=>c.status==='OPEN'); const diffs=snapshot.artifactDiffs.filter(d=>d.artifactId===artifact.id); const recorded=recordedDecision(snapshot);
  return <div className={`p-output-stage ${inspection?'has-lens':''}`}><div><section className="p-decision-pack"><header><div className="p-kicker">Decision Pack</div><h1>{artifact.title}</h1><p>{snapshot.decision?.label}</p></header><div className="p-decision-pack-grid"><div><strong>Current case</strong>{snapshot.premiseCaseReadingId&&<button onClick={()=>void setActiveObject(snapshot.premiseCaseReadingId)}>{caseReadingById(snapshot,snapshot.premiseCaseReadingId)?.text}</button>}</div><div><strong>Decision frontier</strong>{open.map(c=><button key={c.id} onClick={()=>void setActiveObject(c.id)}>{c.label}<span>→</span></button>)}</div></div><section className="p-decision-branches"><strong>Human branches</strong><div>{snapshot.decisionPaths.map(p=><span className="p-branch-label" key={p.id}>{humanState(p.label)}</span>)}</div></section><footer><strong>Recorded decision</strong><p>{recorded?recorded.rationale:'No institutional decision recorded.'}</p></footer></section>{reviewDiff&&diffs.length>0&&<div className="p-inline-review">{diffs.map(d=><div key={d.id}>{d.before&&<del>{d.before}</del>}<b> → </b>{d.after&&<ins>{d.after}</ins>}</div>)}</div>}{reviewDiff&&!diffs.length&&<DiffUnavailable/>}<CaseLifecycle/></div>{inspection&&<aside className="p-output-lens"><ObjectLens/></aside>}</div>;
}

function OutputEmpty({title,artifactType}:{title:string;artifactType:string}){const {execute,actor,pendingAction}=usePanta();const can=actor?.entitlements.includes('EDIT_ARTIFACT')??false;return <section className="p-empty"><div><h1>{title}</h1><p>This artifact has not been created from the current case.</p><button className="p-btn p-btn-primary" disabled={!can||Boolean(pendingAction)} onClick={()=>void execute({type:'CREATE_ARTIFACT',artifactType})}>Create from case</button></div></section>}
function DiffUnavailable(){return <div className="p-inline-review p-diff-empty" role="status"><strong>Change details unavailable</strong><p>This backend reported pending case changes but did not provide artifact diff details for this output.</p></div>}
function label(k:OutputTab){return k==='IC_MEMO'?'IC Memo':k==='MODEL'?'Model':'Decision Pack'}
function humanState(v:string){return v.toLowerCase().replaceAll('_',' ').replace(/^./,x=>x.toUpperCase())}
