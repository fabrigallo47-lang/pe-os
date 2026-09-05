import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import {
  actorById,
  caseReadingById,
  decisionCriticalQuestions,
  formatCount,
  recordedDecision,
  unknownById,
  workstreamById,
} from '../app/selectors';
import { goTo } from '../app/routes';
import type { CaseMoment, DecisionDimension, Id, PantaCaseSnapshot, Question } from '../types/domain';

type RoomMode = 'REPLAY' | 'DECISION';

export function ReplayDecision(){
  const {snapshot,moments,asOf,setAsOf,returnToCurrent,pendingAction}=usePanta();
  const [mode,setMode]=useState<RoomMode>(asOf?'REPLAY':'DECISION');
  const meaningfulMoments=moments.filter(moment=>Boolean(moment.eventId));

  useEffect(()=>{if(asOf)setMode('REPLAY')},[asOf]);

  if(!snapshot)return <EmptyCase/>;

  const openReplay=async()=>{
    setMode('REPLAY');
    if(!asOf&&meaningfulMoments[0])await setAsOf(meaningfulMoments[0].asOf);
  };
  const openDecision=async()=>{
    if(asOf)await returnToCurrent();
    setMode('DECISION');
  };
  const replayAt=async(cutoff:string)=>{
    setMode('REPLAY');
    await setAsOf(cutoff);
  };

  return <main className={`p-page p-replay-page is-${mode.toLowerCase()}`}>
    <div className="p-replay-mode-tabs" role="tablist" aria-label="Replay and Decision modes">
      <button role="tab" aria-selected={mode==='REPLAY'} aria-controls="replay-panel" id="replay-tab" onClick={()=>void openReplay()}>Replay<span>Case through time</span></button>
      <button role="tab" aria-selected={mode==='DECISION'} aria-controls="decision-panel" id="decision-tab" onClick={()=>void openDecision()}>Decision<span>Institutional judgment</span></button>
    </div>
    {mode==='REPLAY'
      ? <ReplayMode snapshot={snapshot} moments={meaningfulMoments} asOf={asOf} pendingAction={pendingAction} setAsOf={setAsOf} onReturnCurrent={openDecision}/>
      : <DecisionMode snapshot={snapshot} pendingAction={pendingAction} onReplayAt={replayAt}/>}
  </main>;
}

function ReplayMode({snapshot,moments,asOf,pendingAction,setAsOf,onReturnCurrent}:{
  snapshot:PantaCaseSnapshot;
  moments:CaseMoment[];
  asOf?:string;
  pendingAction?:string;
  setAsOf:(asOf?:string)=>Promise<void>;
  onReturnCurrent:()=>Promise<void>;
}){
  const {setActiveObject}=usePanta();
  const recorded=recordedDecision(snapshot);

  return <section id="replay-panel" role="tabpanel" aria-labelledby="replay-tab" className="p-replay-mode">
    <header className="p-replay-head">
      <div><div className="p-kicker">Case replay</div><h1>What did we know and believe at this point?</h1><p>Select a meaningful case event to reconstruct the same case at that ledger cutoff.</p></div>
      {asOf&&<button className="p-btn" onClick={()=>void onReturnCurrent()}>Return to current</button>}
    </header>

    {moments.length?<nav className="p-replay-rail" aria-label="Meaningful case events">{moments.map(moment=><button key={moment.id} aria-pressed={moment.asOf===asOf} disabled={Boolean(pendingAction)} className={moment.asOf===asOf?'is-selected':''} onClick={()=>void setAsOf(moment.asOf)}><i aria-hidden="true"/><strong>{moment.label}</strong><small>{formatMomentDate(moment.asOf)}</small></button>)}</nav>:<div className="p-replay-empty">No meaningful case events are available for replay.</div>}

    <div className="p-replay-cutoff">
      <div><span>Ledger cutoff</span><strong>{formatRecordedTime(snapshot.asOf)}</strong></div>
      <div><span>Decision state then</span><strong>{recorded?humanPath(snapshot.decisionPaths.find(path=>path.id===recorded.pathId)?.label??recorded.decision??'Recorded'):'No institutional decision recorded'}</strong></div>
      <div><span>Frozen projection</span><strong>{snapshot.caseVersion}</strong></div>
    </div>

    <section className="p-replay-snapshot" aria-labelledby="replay-snapshot-title">
      <header><div><div className="p-kicker">Case at this point</div><h2 id="replay-snapshot-title">Workstreams stay in place. The case state moves.</h2></div><span>{formatCount(snapshot.workstreams.length,'workstream')}</span></header>
      <div className="p-replay-case">{snapshot.workstreams.map(workstream=>{
        const reading=caseReadingById(snapshot,workstream.currentCaseReadingId);
        const questions=workstream.questionIds.map(id=>snapshot.questions.find(question=>question.id===id)).filter((question):question is Question=>Boolean(question));
        const unknowns=workstream.openUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);
        return <article key={workstream.id} className="p-replay-case-row">
          <header><strong>{workstream.name}</strong>{questions.map(question=><span key={question.id}>{question.name}</span>)}</header>
          <div className="p-replay-reading"><span>Reading then</span>{reading?<button onClick={()=>void setActiveObject(reading.id)}>{reading.text}<small>Inspect reading →</small></button>:<p>No reading had been formed at this point.</p>}</div>
          <div className="p-replay-open"><span>What was still open then</span>{unknowns.length?unknowns.map(unknown=><button key={unknown!.id} onClick={()=>void setActiveObject(unknown!.id)}>{unknown!.title}<small>Inspect gap →</small></button>):<p>Nothing remained open in this workstream.</p>}</div>
        </article>;
      })}</div>
    </section>
  </section>;
}

function DecisionMode({snapshot,pendingAction,onReplayAt}:{snapshot:PantaCaseSnapshot;pendingAction?:string;onReplayAt:(cutoff:string)=>Promise<void>}){
  const {execute,actor,setActiveObject,openSource}=usePanta();
  const issues=decisionCriticalQuestions(snapshot);
  const issueIds=issues.map(issue=>issue.id).join('|');
  const [selectedId,setSelectedId]=useState(issues[0]?.id);
  const selected=issues.find(issue=>issue.id===selectedId)??issues[0];
  const [viewedIds,setViewedIds]=useState<Set<Id>>(()=>new Set(selected?[selected.id]:[]));
  const [recording,setRecording]=useState(false);
  const [pathId,setPathId]=useState('');
  const [rationale,setRationale]=useState('');
  const [conditionText,setConditionText]=useState('');
  const recorded=recordedDecision(snapshot);
  const canRecord=actor?.entitlements.includes('RECORD_DECISION')??false;

  useEffect(()=>{
    if(!issues.some(issue=>issue.id===selectedId))setSelectedId(issues[0]?.id);
    setViewedIds(new Set(issues[0]?[issues[0].id]:[]));
    setRecording(false);
  },[snapshot.caseVersion,issueIds]);
  useEffect(()=>{
    if(selected)setViewedIds(current=>new Set(current).add(selected.id));
  },[selected?.id]);

  const viewedCount=issues.filter(issue=>viewedIds.has(issue.id)).length;
  const reviewComplete=issues.length===0||viewedCount===issues.length;
  const selectedPath=snapshot.decisionPaths.find(path=>path.id===pathId);
  const sessionActor=actorById(snapshot,actor?.actorId);

  if(recorded){
    const path=snapshot.decisionPaths.find(value=>value.id===recorded.pathId);
    const recordedBy=actorById(snapshot,recorded.actorOrBodyId);
    const recordedConditions=(recorded.conditionIds??[]).map(id=>snapshot.conditions.find(condition=>condition.id===id)).filter(Boolean);
    const basisQuestions=(recorded.basisObjectIds??[]).map(id=>snapshot.questions.find(question=>question.id===id)).filter((question):question is Question=>Boolean(question));
    return <section id="decision-panel" role="tabpanel" aria-labelledby="decision-tab" className="p-decision-mode">
      <header className="p-decision-head"><div><div className="p-kicker">Decision desk</div><h1>The institutional decision is recorded.</h1><p>This case is no longer presented as undecided. PANTA preserves the accountable decision and its frozen basis.</p></div></header>
      <article className="p-recorded-desk">
        <header><span>Recorded decision</span><h2>{humanPath(path?.label??recorded.decision??'Recorded')}</h2><p>{snapshot.decision?.label}</p></header>
        <blockquote>{recorded.rationale}</blockquote>
        {recordedConditions.length>0&&<section><strong>Conditions</strong>{recordedConditions.map(condition=><button key={condition!.id} onClick={()=>void setActiveObject(condition!.id)}>{condition!.label}<span>Inspect →</span></button>)}</section>}
        <dl><div><dt>Actor</dt><dd>{recordedBy?.displayName??'Authorized decision body'}</dd></div><div><dt>Timestamp</dt><dd>{formatRecordedTime(recorded.recordedAt)}</dd></div><div><dt>Frozen case snapshot</dt><dd>{recorded.caseVersion}</dd></div></dl>
        <section className="p-recorded-basis"><div><strong>Supporting snapshot</strong><span>{formatCount(basisQuestions.length,'decision-critical question')}</span></div>{basisQuestions.map(question=><button key={question.id} onClick={()=>goTo('workstream',{workstreamId:question.workstreamId,questionId:question.id})}>{question.name}<span>Open workstream →</span></button>)}</section>
        <footer><button className="p-btn" onClick={()=>void onReplayAt(recorded.recordedAt)}>Replay supporting snapshot</button></footer>
      </article>
    </section>;
  }

  return <section id="decision-panel" role="tabpanel" aria-labelledby="decision-tab" className="p-decision-mode">
    <header className="p-decision-head"><div><div className="p-kicker">Decision desk</div><h1>What still needs judgment before we can decide?</h1><p>The live underwriting graph identifies the few questions carrying the decision. PANTA does not recommend an outcome.</p></div><div><strong>{issues.length}</strong><span>issues between this case and a decision</span></div></header>

    {issues.length&&selected?<div className="p-decision-workbench">
      <nav className="p-decision-issues" aria-label="Decision-critical underwriting questions">
        <div className="p-section-heading"><strong>Decision-critical questions</strong><span>{viewedCount} / {issues.length} reviewed</span></div>
        {issues.map((issue,index)=>{
          const workstream=workstreamById(snapshot,issue.workstreamId);
          const unresolved=issue.openUnknownIds.map(id=>unknownById(snapshot,id)).find(Boolean);
          return <button key={issue.id} aria-pressed={issue.id===selected.id} className={issue.id===selected.id?'is-selected':''} onClick={()=>setSelectedId(issue.id)}><span>{String(index+1).padStart(2,'0')}</span><div><small>{workstream?.name}</small><strong>{issue.name}</strong>{unresolved&&<p>{unresolved.title}</p>}</div><i>{viewedIds.has(issue.id)?'Reviewed':'Review'}</i></button>;
        })}
      </nav>
      <DecisionIssue snapshot={snapshot} question={selected} onInspect={setActiveObject} onOpenSource={openSource}/>
    </div>:<section className="p-decision-clear"><strong>No unresolved decision-critical questions remain.</strong><p>The backend has not identified an open underwriting issue that must be reviewed before this decision.</p></section>}

    <section className="p-decision-record-gate">
      <div><span>Question review</span><strong>{issues.length?`${viewedCount} of ${issues.length} reviewed`:'Clear'}</strong><p>{reviewComplete?'The decision desk has been reviewed. You may now record the accountable institutional judgment.':'Review every decision-critical question before recording the institutional decision.'}</p></div>
      {!recording?<button className="p-btn p-btn-primary" disabled={!reviewComplete||!canRecord||Boolean(pendingAction)} onClick={()=>setRecording(true)}>Continue to record decision</button>:<div className="p-decision-recorder">
        <label htmlFor="institutional-decision">Institutional decision</label>
        <select id="institutional-decision" value={pathId} disabled={Boolean(pendingAction)} onChange={event=>setPathId(event.target.value)}><option value="">Choose the institutional decision</option>{snapshot.decisionPaths.map(path=><option key={path.id} value={path.id}>{humanPath(path.label)}</option>)}</select>
        <label htmlFor="decision-rationale">Rationale</label>
        <textarea id="decision-rationale" className="p-input" disabled={Boolean(pendingAction)} placeholder="Record the accountable human rationale" value={rationale} onChange={(event:React.ChangeEvent<HTMLTextAreaElement>)=>setRationale(event.target.value)}/>
        {selectedPath?.label==='COMMIT_WITH_CONDITIONS'&&<><label htmlFor="decision-conditions">Conditions</label><textarea id="decision-conditions" className="p-input" disabled={Boolean(pendingAction)} placeholder="Condition required to close" value={conditionText} onChange={(event:React.ChangeEvent<HTMLTextAreaElement>)=>setConditionText(event.target.value)}/></>}
        <dl><div><dt>Actor</dt><dd>{sessionActor?.displayName??'Authorized decision maker'}</dd></div><div><dt>Timestamp</dt><dd>Fixed on submission</dd></div><div><dt>Frozen case snapshot</dt><dd>{snapshot.caseVersion} · {formatRecordedTime(snapshot.asOf)}</dd></div></dl>
        <div className="p-decision-record-actions"><button className="p-btn p-btn-primary" disabled={!pathId||!rationale.trim()||!canRecord||Boolean(pendingAction)} onClick={()=>void execute({type:'RECORD_DECISION',pathId,rationale,conditionText:conditionText||undefined})}>{pendingAction==='RECORD_DECISION'?'Recording decision…':'Record institutional decision'}</button><button className="p-btn p-btn-quiet" disabled={Boolean(pendingAction)} onClick={()=>setRecording(false)}>Cancel</button></div>
      </div>}
    </section>
  </section>;
}

function DecisionIssue({snapshot,question,onInspect,onOpenSource}:{snapshot:PantaCaseSnapshot;question:Question;onInspect:(id:Id)=>Promise<void>;onOpenSource:(id?:Id)=>void}){
  const reading=caseReadingById(snapshot,question.currentCaseReadingId);
  const unknowns=question.openUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);
  const workstream=workstreamById(snapshot,question.workstreamId);
  const dimensions=question.decisionDimensions!;
  const condition=dimensions.conditionId?snapshot.conditions.find(value=>value.id===dimensions.conditionId):undefined;
  const sourceId=question.claimIds.map(id=>snapshot.claims.find(claim=>claim.id===id)?.sourceId).find(Boolean);
  const context={workstreamId:question.workstreamId,questionId:question.id};

  return <article className="p-decision-issue-detail">
    <header><span>{workstream?.name}</span><h2>{question.name}</h2></header>
    <section className="p-decision-current"><h3>Current view</h3>{reading?<button onClick={()=>void onInspect(reading.id)}>{reading.text}<small>Inspect reading →</small></button>:<p>No current reading has been formed.</p>}</section>
    <section className="p-decision-unresolved"><h3>What remains unresolved</h3>{unknowns.length?unknowns.map(unknown=><button key={unknown!.id} onClick={()=>void onInspect(unknown!.id)}>{unknown!.title}<small>Inspect gap →</small></button>):<p>No open gap is attached to this question.</p>}</section>
    <section className="p-decision-why"><h3>Why it matters to the decision</h3><p>{question.decisionRelevance}</p></section>
    <div className="p-decision-dimensions">
      <Dimension label="Load-bearingness" dimension={dimensions.loadBearingness} onInspect={onInspect}/>
      <Dimension label="Severity" dimension={dimensions.severity} onInspect={onInspect}/>
      <Dimension label="Fragility" dimension={dimensions.fragility} onInspect={onInspect}/>
      <Dimension label="Decision criticality" dimension={dimensions.decisionCriticality} onInspect={onInspect}/>
    </div>
    {condition&&<section className="p-decision-condition"><h3>Condition to close</h3><button onClick={()=>void onInspect(condition.id)}>{condition.label}<small>Inspect condition →</small></button></section>}
    <footer className="p-decision-depth" aria-label="Explore this decision-critical question"><button onClick={()=>goTo('workstream',context)}>Workstream</button><button onClick={()=>goTo('trace',context)}>Trace</button><button onClick={()=>goTo('simulate',context)}>Simulate</button><button onClick={()=>goTo('resolve',context)}>Resolve</button><button disabled={!sourceId} onClick={()=>sourceId&&onOpenSource(sourceId)}>Source</button></footer>
  </article>;
}

function Dimension({label,dimension,onInspect}:{label:string;dimension:DecisionDimension;onInspect:(id:Id)=>Promise<void>}){
  const basisId=dimension.basisObjectIds[0];
  return basisId?<button className="p-decision-dimension" onClick={()=>void onInspect(basisId)}><span>{label}</span><p>{dimension.text}</p><small>Inspect basis →</small></button>:<div className="p-decision-dimension"><span>{label}</span><p>{dimension.text}</p></div>;
}

function humanPath(value:string){return value.toLowerCase().replaceAll('_',' ').replace(/^./,letter=>letter.toUpperCase())}
function formatMomentDate(value:string){try{return new Intl.DateTimeFormat('en',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value));}catch{return value}}
function formatRecordedTime(value:string){try{return new Intl.DateTimeFormat('en',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(value));}catch{return value}}
