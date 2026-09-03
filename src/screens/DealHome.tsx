import React from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ObjectLens } from '../components/ObjectLens';
import { HumanPositionNote } from '../components/HumanPositionNote';
import { eventById, eventDisplayLabel, unknownById, workItemById, actorById, humanPositionsForScope, caseReadingById, supportSummary } from '../app/selectors';
import { goTo } from '../app/routes';

export function DealHome() {
  const { snapshot, setActiveObject, activeObjectId, setFocusedWorkstream } = usePanta();
  if (!snapshot) return <EmptyCase />;
  const premise = caseReadingById(snapshot, snapshot.premiseCaseReadingId);
  const findings = snapshot.findings.filter(f => f.status === 'NEW').slice(0, 3);

  return <main className="p-page p-deal-page">
    <section className="p-deal-head">
      <div>
        <div className="p-kicker">Deal Home</div>
        <div className="p-deal-identity"><h1 className="p-title">{snapshot.caseRef.name}</h1>{snapshot.caseRef.stage&&<span>{snapshot.caseRef.stage}</span>}{snapshot.caseRef.geography&&<span>{snapshot.caseRef.geography}</span>}{snapshot.caseRef.sector&&<span>{snapshot.caseRef.sector}</span>}</div>
        {premise && <button className="p-premise p-selectable" onClick={()=>void setActiveObject(premise.id)}>{premise.text}</button>}
      </div>
      <aside className="p-deal-decision"><div className="p-kicker">Decision point</div><div className="p-reading-small">{snapshot.decision?.label ?? 'No decision scheduled'}</div>{snapshot.decision?.dueAt&&<div className="p-meta">{snapshot.decision.dueAt}</div>}</aside>
    </section>

    {!!findings.length && <section className="p-attention-band">
      <div className="p-section-heading"><strong>New since your last review</strong><span className="p-meta">{findings.length} material update{findings.length===1?'':'s'}</span></div>
      <div className="p-findings-strip">{findings.map(f=><button key={f.id} className={`p-finding p-selectable ${activeObjectId===f.id?'p-selected':''}`} onClick={()=>void setActiveObject(f.id)}><strong>{f.title}</strong><span>{f.proposition}</span><small>PANTA found</small></button>)}</div>
    </section>}

    <section className="p-deal-table">
      <div className="p-deal-grid-head"><span>Workstream</span><span>Current view</span><span>Latest change</span><span>Work underway</span><span>Still open</span></div>
      {snapshot.workstreams.map(w=>{
        const reading=caseReadingById(snapshot,w.currentCaseReadingId); if(!reading)return null;
        const supports=supportSummary(snapshot,reading);
        const event=eventById(snapshot,w.latestChangeEventId);
        const workItems=w.activeWorkItemIds.map(id=>workItemById(snapshot,id)).filter(Boolean);
        const unknowns=w.openUnknownIds.map(id=>unknownById(snapshot,id)).filter(Boolean);
        const owner=actorById(snapshot,w.ownerActorId);
        const humanPositions=humanPositionsForScope(snapshot,[w.id,reading.id]);
        return <article key={w.id} className={`p-deal-row ${activeObjectId===reading.id?'p-selected':''}`}>
          <div className="p-deal-workstream"><button onClick={()=>{setFocusedWorkstream(w.id);goTo('workstream')}}><strong>{w.name}</strong></button>{owner&&<span>{owner.displayName}</span>}{humanPositions[0]&&<HumanPositionNote position={humanPositions[0]}/>}</div>
          <button className="p-deal-reading p-selectable" onClick={()=>void setActiveObject(reading.id)}><span>{reading.text}</span><small className={supports.independent===0?'is-emphasis':''}>{supports.total} current support{supports.total===1?'':'s'} · {supports.independent?`${supports.independent} independent`:'no independent evidence'}</small></button>
          <div className="p-deal-fact">{event?<><span>{eventDisplayLabel(snapshot,event)}</span><small>{event.effectiveAt??event.knownAt}</small></>:<span>—</span>}</div>
          <div className="p-deal-fact">{workItems.length?workItems.map(m=><button key={m!.id} className="p-inline-link" onClick={()=>void setActiveObject(m!.id)}>{m!.name}</button>):<span>No active work</span>}</div>
          <div className="p-deal-fact">{unknowns.length?unknowns.slice(0,2).map(g=><button key={g!.id} className="p-inline-link" onClick={()=>void setActiveObject(g!.id)}>{g!.title}</button>):<span>Nothing material open</span>}</div>
        </article>;
      })}
    </section>
    <div className="p-floating-lens"><ObjectLens compact/></div>
  </main>;
}
