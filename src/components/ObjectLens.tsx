import React from 'react';
import { usePanta } from '../app/PantaContext';
import { actorById, composeLens, humanState } from '../app/selectors';
import { goTo } from '../app/routes';
import type { Actor } from '../types/domain';
import { ObjectCausalTrace } from './CausalTrace';
import { useDialogFocus, useMediaQuery } from './useDialogFocus';
import { inspectionSourceLocators } from '../app/sourceEvidence';
import '../design/source-evidence.css';

export function ObjectLens({ compact = false }: { compact?: boolean }) {
  const { snapshot, inspection, activeObjectId, inspecting, setActiveObject } = usePanta();
  const mobile = useMediaQuery('(max-width: 760px)');
  const activeActor = snapshot && activeObjectId ? actorById(snapshot, activeObjectId) : undefined;
  const open = Boolean(snapshot && (activeActor || inspection || (inspecting && activeObjectId)));
  const close = () => { void setActiveObject(undefined); };
  const dialogRef = useDialogFocus<HTMLElement>(open && mobile, close, undefined, '[data-object-lens-return]');
  if (!snapshot || !open) return null;

  const content = activeActor
    ? <ActorLensContents actor={activeActor} onClose={close} />
    : inspection ? <LensContents compact={compact} onClose={close} /> : <>
    <div className="p-object-lens-head"><div><div className="p-kicker">Selected</div><div id="object-lens-title" className="p-reading-small p-lens-title">Loading inspection…</div></div><button className="p-icon-btn" onClick={close} aria-label="Close inspection">×</button></div>
    <div className="p-lens-loading" role="status"><span className="p-progress-mark" aria-hidden="true"/>Opening the selected case object…</div>
  </>;

  if (mobile) return <div className="p-object-lens-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}><aside ref={dialogRef} tabIndex={-1} className={`p-object-lens p-object-lens-sheet p-fade-in ${compact ? 'is-compact' : ''}`} role="dialog" aria-modal="true" aria-labelledby="object-lens-title">{content}</aside></div>;
  return <aside className={`p-object-lens p-fade-in ${compact ? 'is-compact' : ''}`} aria-labelledby="object-lens-title">{content}</aside>;
}

function ActorLensContents({ actor, onClose }: { actor: Actor; onClose: () => void }) {
  const { snapshot, inspecting, setActiveObject } = usePanta();
  if (!snapshot) return null;
  const ownedWorkstreams = snapshot.workstreams.filter(workstream => workstream.ownerActorId === actor.id);
  const ownedWorkItems = snapshot.workItems.filter(item =>
    item.ownerActorId === actor.id && item.status !== 'COMPLETED' && item.status !== 'CANCELLED'
  );
  const inspect = (id: string) => { if (!inspecting) void setActiveObject(id); };

  return <>
    <div className="p-object-lens-head">
      <div>
        <div className="p-kicker">Case participant</div>
        <div id="object-lens-title" className="p-reading-small p-lens-title">{actor.displayName}</div>
        {(actor.role || actor.organisation) && <p className="p-person-role">{[actor.role, actor.organisation].filter(Boolean).join(' · ')}</p>}
      </div>
      <button className="p-icon-btn" onClick={onClose} aria-label="Close profile">×</button>
    </div>

    <LensSection title="Workstreams owned">
      {ownedWorkstreams.length
        ? ownedWorkstreams.map(workstream => <button key={workstream.id} className="p-related-link p-person-context-link" onClick={() => { onClose(); goTo('workstream', { workstreamId: workstream.id, questionId: workstream.questionIds[0] }); }}><span>{workstream.name}</span><em>Open workstream</em></button>)
        : <p>No workstream is currently assigned.</p>}
    </LensSection>

    <LensSection title="Diligence in hand">
      {ownedWorkItems.length
        ? ownedWorkItems.map(item => <button key={item.id} disabled={inspecting} className="p-related-link p-person-context-link" onClick={() => inspect(item.id)}><span>{item.name}</span><em>{humanState(item.status)}</em></button>)
        : <p>No current diligence step is assigned.</p>}
    </LensSection>

    <div className="p-lens-actions">
      <button className="p-btn p-btn-quiet" onClick={onClose}>Close profile</button>
    </div>
  </>;
}

function LensContents({ compact, onClose }: { compact: boolean; onClose: () => void }) {
  const { snapshot, inspection, inspecting, setActiveObject, openSource } = usePanta();
  if (!snapshot || !inspection) return null;
  const vm = composeLens(snapshot, inspection);
  const sourceLocators = inspectionSourceLocators(snapshot, inspection.objectId, inspection.sourceLocators);
  const inspect = (id: string) => { if (!inspecting) void setActiveObject(id); };

  return <>
    <div className="p-object-lens-head">
      <div><div className="p-kicker">Selected</div><div id="object-lens-title" className="p-reading-small p-lens-title">{vm.title}</div></div>
      <button className="p-icon-btn" onClick={onClose} aria-label="Close inspection">×</button>
    </div>

    <ObjectCausalTrace
      objectId={inspection.objectId}
      supportIds={inspection.supportObjectIds}
      independentSupportIds={inspection.independentSupportObjectIds}
      dependentIds={inspection.dependentObjectIds}
      compact={compact}
    />

    <LensSection title="Still missing">
      {vm.unknowns.length ? vm.unknowns.slice(0, 3).map(item => <button key={item.id} disabled={inspecting} className="p-related-link" onClick={() => inspect(item.id)}>{item.label}</button>) : <p>Nothing material is currently mapped as missing.</p>}
    </LensSection>

    <LensSection title="What changed">
      <p>{vm.lastChange ? `${vm.lastChange.label} · ${formatDate(vm.lastChange.date)}` : 'No mapped change event.'}</p>
      {vm.lastChange && <button className="p-related-link" onClick={() => goTo('replay', { asOf: vm.lastChange!.knownAt })}>Open in Replay</button>}
    </LensSection>

    {!!vm.related.length && <LensSection title="Where else this appears">
      {vm.related.slice(0, 5).map(item => <button key={item.id} disabled={inspecting} className="p-related-link" onClick={() => inspect(item.id)}>{item.label}</button>)}
    </LensSection>}

    {vm.actions.includes('OPEN_SOURCE') && sourceLocators.length > 0 && <LensSection title="Source passages">
      <div className="p-source-statement-links">{sourceLocators.map((ref, index) => <button key={index} className="p-related-link" onClick={() => openSource(ref)}><span>{snapshot.sources.find(source => source.id === ref.sourceId)?.title ?? 'Source unavailable'}</span><small>{ref.locator || snapshot.claims.find(claim => claim.id === ref.claimId)?.locator || 'Exact location not supplied'}</small></button>)}</div>
    </LensSection>}

    <div className="p-lens-actions">
      {vm.actions.includes('TRACE') && <button className="p-btn" onClick={() => goTo('trace')}>Trace</button>}
      {vm.actions.includes('SIMULATE') && <button className="p-btn" onClick={() => goTo('simulate')}>Simulate</button>}
      {vm.actions.includes('RESOLVE') && <button className="p-btn" onClick={() => goTo('resolve')}>Resolve</button>}
      {vm.actions.includes('OPEN_SOURCE') && sourceLocators[0] && <button className="p-btn" onClick={() => openSource(sourceLocators[0])}>Open source</button>}
      {vm.actions.includes('VIEW_IN_CASE') && <button className="p-btn p-btn-quiet" onClick={() => goTo('deal')}>View in case</button>}
    </div>
  </>;
}

function LensSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="p-lens-block"><h2 className="p-lens-label">{title}</h2><div className="p-lens-text">{children}</div></section>;
}
function formatDate(value: string) { try { return new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value)); } catch { return value; } }
