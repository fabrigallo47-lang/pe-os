import React from 'react';
import { usePanta } from '../app/PantaContext';
import { composeLens } from '../app/selectors';
import { goTo } from '../app/routes';

export function ObjectLens({ compact = false }: { compact?: boolean }) {
  const { snapshot, inspection, setActiveObject, openSource } = usePanta();
  if (!snapshot || !inspection) return null;
  const vm = composeLens(snapshot, inspection);
  const evidenceSentence = vm.supportCount
    ? `${vm.supportCount} current support${vm.supportCount === 1 ? '' : 's'}${vm.independentCount ? ` · ${vm.independentCount} independent` : ' · no independent evidence'}`
    : 'No mapped support';

  return <aside className={`p-object-lens p-fade-in ${compact ? 'is-compact' : ''}`}>
    <div className="p-object-lens-head">
      <div><div className="p-kicker">Selected</div><div className="p-reading-small p-lens-title">{vm.title}</div></div>
      <button className="p-icon-btn" onClick={() => void setActiveObject(undefined)} aria-label="Close inspection">×</button>
    </div>

    <LensSection title="Why we believe this">
      <p>{evidenceSentence}</p>
      {vm.supportRefs.slice(0,3).map(x => <button key={x.id} className="p-related-link" onClick={() => void setActiveObject(x.id)}>{x.label}</button>)}
    </LensSection>

    <LensSection title="Still missing">
      {vm.unknowns.length ? vm.unknowns.slice(0,3).map(x => <button key={x.id} className="p-related-link" onClick={() => void setActiveObject(x.id)}>{x.label}</button>) : <p>Nothing material is currently mapped as missing.</p>}
    </LensSection>

    <LensSection title="Why it matters">
      {vm.dependents.length ? vm.dependents.slice(0,4).map(x => <button key={x.id} className="p-related-link" onClick={() => void setActiveObject(x.id)}>{x.label}</button>) : <p>No mapped downstream consequence.</p>}
    </LensSection>

    <LensSection title="What changed">
      <p>{vm.lastChange ? `${vm.lastChange.label} · ${formatDate(vm.lastChange.date)}` : 'No mapped change event.'}</p>
    </LensSection>

    {!!vm.related.length && <LensSection title="Where else this appears">
      {vm.related.slice(0,5).map(x => <button key={x.id} className="p-related-link" onClick={() => void setActiveObject(x.id)}>{x.label}</button>)}
    </LensSection>}

    <div className="p-lens-actions">
      {vm.actions.includes('TRACE') && <button className="p-btn" onClick={() => goTo('trace')}>Trace</button>}
      {vm.actions.includes('SIMULATE') && <button className="p-btn" onClick={() => goTo('simulate')}>Simulate</button>}
      {vm.actions.includes('RESOLVE') && <button className="p-btn" onClick={() => goTo('resolve')}>Resolve</button>}
      {vm.actions.includes('OPEN_SOURCE') && vm.sourceRefs[0] && <button className="p-btn" onClick={() => openSource(vm.sourceRefs[0].id)}>Open source</button>}
      {vm.actions.includes('VIEW_IN_CASE') && <button className="p-btn p-btn-quiet" onClick={() => goTo('deal')}>View in case</button>}
    </div>
  </aside>;
}

function LensSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="p-lens-block"><div className="p-lens-label">{title}</div><div className="p-lens-text">{children}</div></section>;
}
function formatDate(value:string){try{return new Intl.DateTimeFormat('en',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value));}catch{return value}}
