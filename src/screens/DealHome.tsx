import React from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { HumanPositionNote } from '../components/HumanPositionNote';
import { ObjectLens } from '../components/ObjectLens';
import { caseReadingById, dealWorkstreamSummary, decisionCriticalQuestions, eventDisplayLabel, formatCount, humanState } from '../app/selectors';
import { goTo } from '../app/routes';
import type { CaseReading, Id, PantaCaseSnapshot, WorkItem, Workstream } from '../types/domain';

export function DealHome() {
  const { snapshot, setActiveObject, activeObjectId } = usePanta();
  if (!snapshot) return <EmptyCase />;
  const premise = caseReadingById(snapshot, snapshot.premiseCaseReadingId);
  const findings = snapshot.findings.filter(f => f.status === 'NEW').slice(0, 3);
  const decisionIssues = decisionCriticalQuestions(snapshot);
  const decisionState = snapshot.decision?.status === 'RECORDED' ? 'Institutional decision recorded' : formatCount(decisionIssues.length,'decision-critical issue');

  return <main className="p-page p-deal-page">
    <section className="p-deal-head">
      <div>
        <div className="p-kicker">Deal Home</div>
        <div className="p-deal-identity"><h1 className="p-title">{snapshot.caseRef.name}</h1>{snapshot.caseRef.stage&&<span>{snapshot.caseRef.stage}</span>}{snapshot.caseRef.geography&&<span>{snapshot.caseRef.geography}</span>}{snapshot.caseRef.sector&&<span>{snapshot.caseRef.sector}</span>}</div>
        {premise && <button aria-pressed={activeObjectId===premise.id} className="p-premise p-selectable" onClick={()=>void setActiveObject(premise.id)}>{premise.text}</button>}
      </div>
      <aside className="p-deal-decision"><div className="p-kicker">Decision point</div><div className="p-reading-small">{snapshot.decision?.label ?? 'No decision scheduled'}</div>{snapshot.decision&&<><div className="p-meta">{decisionState} · {snapshot.decision.dueAt?`Due ${formatDecisionDate(snapshot.decision.dueAt)}`:'Date not set'}</div>{snapshot.decision.status!=='RECORDED'&&<div className="p-deal-decision-options">Review the underwriting questions that carry the decision.</div>}</>}<button className="p-inline-route" onClick={() => goTo('replay')}>{snapshot.decision ? 'Open Decision desk' : 'Review case history'}<span aria-hidden="true">→</span></button></aside>
    </section>

    {!!findings.length && <section className="p-attention-band">
      <div className="p-section-heading"><strong>New since your last review</strong><span className="p-meta">{findings.length} material update{findings.length===1?'':'s'}</span></div>
      <div className="p-findings-strip">{findings.map(f=><button key={f.id} aria-pressed={activeObjectId===f.id} className={`p-finding p-selectable ${activeObjectId===f.id?'p-selected':''}`} onClick={()=>void setActiveObject(f.id)}><strong>{f.title}</strong><span>{f.proposition}</span><small>PANTA found</small></button>)}</div>
    </section>}

    <section className="p-workstream-list" aria-labelledby="deal-workstreams-title">
      <header className="p-workstream-list-head">
        <div><div className="p-kicker">Workstreams</div><h2 id="deal-workstreams-title">Where the case stands</h2></div>
        <p>Current investment view, an open point to prove, and the next diligence move.</p>
      </header>
      <div className="p-workstream-bands">
        {snapshot.workstreams.map(workstream => <WorkstreamBand
          key={workstream.id}
          snapshot={snapshot}
          workstream={workstream}
          activeObjectId={activeObjectId}
          onInspect={id => void setActiveObject(id)}
        />)}
      </div>
    </section>
    <div className="p-floating-lens"><ObjectLens compact/></div>
  </main>;
}

function WorkstreamBand({ snapshot, workstream, activeObjectId, onInspect }: {
  snapshot: PantaCaseSnapshot;
  workstream: Workstream;
  activeObjectId?: Id;
  onInspect: (id: Id) => void;
}) {
  const { reading, openPoint, nextStep, owner, nextStepOwner, latestChange, humanPosition } = dealWorkstreamSummary(snapshot, workstream);
  const selected = Boolean(activeObjectId && [reading?.id, openPoint?.id, nextStep?.id, humanPosition?.id].includes(activeObjectId));
  const headerOwner = owner ?? (!workstream.ownerActorId ? nextStepOwner : undefined);
  const headerOwnerLabel = owner ? 'Workstream owner' : headerOwner ? 'Next-step owner' : 'Workstream owner';
  const detailCount = Number(Boolean(openPoint)) + Number(Boolean(nextStep || openPoint?.resolutionPath));
  const titleId = `deal-workstream-${workstream.id}`;
  const openWorkstream = () => goTo('workstream', { workstreamId: workstream.id, questionId: workstream.questionIds[0] });

  return <article aria-labelledby={titleId} className={`p-workstream-band ${selected ? 'is-selected' : ''}`}>
    <header className="p-workstream-band-head">
      <h3 id={titleId} className="p-workstream-title"><button className="p-workstream-route" onClick={openWorkstream}>
        <strong>{workstream.name}</strong><span>Open workstream</span><i aria-hidden="true">→</i>
      </button></h3>
      {headerOwner
        ? <button data-object-lens-return aria-pressed={activeObjectId === headerOwner.id} className="p-workstream-owner" onClick={() => onInspect(headerOwner.id)}>
          <span>{headerOwnerLabel}</span><strong>{headerOwner.displayName}</strong><em>Profile</em>
        </button>
        : <div className="p-workstream-owner is-unassigned"><span>Workstream owner</span><strong>{workstream.ownerActorId ? 'Owner unavailable' : 'Unassigned'}</strong></div>}
    </header>

    <div className={`p-workstream-band-body has-${detailCount}-details`}>
      {reading
        ? <button data-object-lens-return aria-pressed={activeObjectId === reading.id} className="p-workstream-view p-workstream-inspect" onClick={() => onInspect(reading.id)}>
          <span className="p-workstream-label">Where we stand {readingAttention(reading) && <em>{readingAttention(reading)}</em>}</span>
          <strong>{reading.text}</strong>
          <span className="p-workstream-cue">Inspect</span>
        </button>
        : <div className="p-workstream-view"><span className="p-workstream-label">Where we stand</span><strong>No current view has been formed yet.</strong></div>}

      {openPoint && <button data-object-lens-return aria-pressed={activeObjectId === openPoint.id} className="p-workstream-detail p-workstream-inspect" onClick={() => onInspect(openPoint.id)}>
        <span className="p-workstream-label">Still to prove</span>
        <strong>{openPoint.title}</strong>
        <span className="p-workstream-cue">Inspect</span>
      </button>}

      {nextStep
        ? <div className="p-workstream-detail p-workstream-next">
          <button data-object-lens-return aria-pressed={activeObjectId === nextStep.id} className="p-workstream-next-main p-workstream-inspect" onClick={() => onInspect(nextStep.id)}>
            <span className="p-workstream-label">Next step <em>{nextStepState(nextStep)}</em></span>
            <strong>{nextStep.name}</strong>
            {nextStep.whatToObtain && <small>{nextStep.whatToObtain}</small>}
            <span className="p-workstream-cue">Inspect</span>
          </button>
          {nextStepOwner && nextStepOwner.id !== headerOwner?.id && <button data-object-lens-return aria-pressed={activeObjectId === nextStepOwner.id} className="p-workstream-step-owner" onClick={() => onInspect(nextStepOwner.id)}>Next-step owner · {nextStepOwner.displayName} · Profile</button>}
          {!nextStepOwner && nextStep.ownerActorId && <span className="p-workstream-step-owner is-unavailable">Next-step owner unavailable</span>}
        </div>
        : openPoint?.resolutionPath && <section className="p-workstream-detail p-workstream-next"><span className="p-workstream-label">Possible next step</span><strong>{openPoint.resolutionPath}</strong></section>}

      {latestChange && <button className="p-workstream-change" onClick={() => goTo('replay', { asOf: latestChange.knownAt })}>
        <span className="p-workstream-label">What changed</span>
        <strong>{eventDisplayLabel(snapshot, latestChange)}</strong>
        <small>{formatShortDate(latestChange.effectiveAt ?? latestChange.knownAt)} · Open in Replay</small>
      </button>}
    </div>
    {humanPosition && <div className="p-workstream-position"><HumanPositionNote position={humanPosition}/></div>}
  </article>;
}

function nextStepState(item: WorkItem): string {
  if (item.institutionalState === 'CANDIDATE' || (item.kind === 'PANTA_PROPOSAL' && item.status === 'PROPOSED')) return 'Proposed · not adopted';
  return humanState(item.status);
}

function readingAttention(reading: CaseReading): string | undefined {
  if (reading.freshnessStatus === 'STALE' || reading.freshnessStatus === 'EXPIRED') return 'Needs refresh';
  if (reading.freshnessStatus === 'UNKNOWN') return 'Freshness unknown';
  return undefined;
}

function formatDecisionDate(value:string){try{return new Intl.DateTimeFormat('en',{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(value));}catch{return value}}
function formatShortDate(value:string){try{return new Intl.DateTimeFormat('en',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value));}catch{return value}}
