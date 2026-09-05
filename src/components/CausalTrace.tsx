import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { humanState, objectLabel, objectRef, objectStateTokens, relationshipNarrative } from '../app/selectors';
import type { Id, ImpactChange, ObjectRef, PantaCaseSnapshot } from '../types/domain';

type LensDirection = 'why' | 'matters';
type ImpactView = 'flow' | 'audit';

export function ObjectCausalTrace({ objectId, supportIds, dependentIds, independentSupportIds, compact = false }: {
  objectId: Id;
  supportIds: Id[];
  dependentIds: Id[];
  independentSupportIds: Id[];
  compact?: boolean;
}) {
  const { snapshot, inspecting, setActiveObject } = usePanta();
  const [direction, setDirection] = useState<LensDirection>(supportIds.length ? 'why' : 'matters');
  const [expanded, setExpanded] = useState(false);
  if (!snapshot) return null;

  const refs = (direction === 'why' ? supportIds : dependentIds).map(id => objectRef(snapshot, id));
  const selectedStates = objectStateTokens(snapshot, objectId);
  const inspect = (id: Id) => { if (!inspecting) void setActiveObject(id); };

  return <section className={`p-causal-lens ${compact ? 'is-compact' : ''}`} aria-label="Causal trace">
    <div className="p-causal-direction" role="group" aria-label="Trace direction">
      <button type="button" aria-pressed={direction === 'why'} onClick={() => setDirection('why')}>Why?</button>
      <button type="button" aria-pressed={direction === 'matters'} onClick={() => setDirection('matters')}>Where it matters</button>
    </div>

    <TraceNode snapshot={snapshot} item={objectRef(snapshot, objectId)} states={selectedStates} focus />

    <div className={`p-causal-branch is-${direction}`}>
      <div className="p-causal-branch-head">
        <strong>{direction === 'why' ? 'What supports this' : 'What moves with this'}</strong>
        <span>{refs.length}</span>
      </div>
      {refs.length ? (expanded ? refs : refs.slice(0, compact ? 3 : 5)).map(item => {
        const sourceId = direction === 'why' ? item.id : objectId;
        const targetId = direction === 'why' ? objectId : item.id;
        const narrative = relationshipNarrative(snapshot, sourceId, targetId);
        const context = direction === 'why' && independentSupportIds.includes(item.id) ? 'Independent support' : narrative;
        return <div className="p-causal-hop" key={item.id}>
          <span className="p-causal-rule" aria-hidden="true" />
          <button type="button" disabled={inspecting} onClick={() => inspect(item.id)}>
            <TraceNode snapshot={snapshot} item={item} states={objectStateTokens(snapshot, item.id)} context={context} />
          </button>
        </div>;
      }) : <p className="p-causal-empty">{direction === 'why' ? 'No mapped support.' : 'No mapped downstream consequence.'}</p>}
    </div>
    {refs.length > (compact ? 3 : 5) && <button type="button" className="p-related-link" onClick={() => setExpanded(value => !value)}>{expanded ? 'Show fewer connections' : `Show all ${refs.length} connections`}</button>}
    {!!refs.length && <p className="p-causal-hint">Open an item to continue the trace from there.</p>}
  </section>;
}

function TraceNode({ snapshot, item, states, context, focus = false }: {
  snapshot: PantaCaseSnapshot;
  item: ObjectRef;
  states: ReturnType<typeof objectStateTokens>;
  context?: string;
  focus?: boolean;
}) {
  const kind = objectKindLabel(objectRef(snapshot, item.id).kind);
  return <span className={`p-causal-node ${focus ? 'is-focus' : ''}`}>
    <span className="p-causal-node-meta">{kind}</span>
    <strong>{item.label}</strong>
    {context && <span className="p-causal-reason">{context}</span>}
    {!!states.length && <span className="p-causal-states">{states.map(state => <span key={`${state.axis}-${state.label}`} className={`is-${state.tone}`}><small>{state.axis}</small>{state.label}</span>)}</span>}
  </span>;
}

export function ImpactTrace({ title, originLabel, originDetail, effects, currentLabel, changedLabel, selectedObjectId, onSelect }: {
  title: string;
  originLabel: string;
  originDetail?: string;
  effects: ImpactChange[];
  currentLabel: string;
  changedLabel: string;
  selectedObjectId?: Id;
  onSelect: (objectId: Id) => void;
}) {
  const { snapshot } = usePanta();
  const [view, setView] = useState<ImpactView>('flow');
  const uniqueEffects = useMemo(() => {
    const byObject = new Map<Id, ImpactChange>();
    for (const effect of effects) {
      const current = byObject.get(effect.objectId);
      if (!current || (current.state === 'HOLDS' && effect.state !== 'HOLDS')) byObject.set(effect.objectId, effect);
    }
    return [...byObject.values()];
  }, [effects]);
  const heldCount = uniqueEffects.filter(effect => effect.state === 'HOLDS').length;
  const changedCount = uniqueEffects.length - heldCount;

  return <section className="p-impact-trace" aria-label={title}>
    <header className="p-impact-trace-head">
      <div><h2>{title}</h2><p>{changedCount} changed · {heldCount} held · every affected object remains visible</p></div>
      <div className="p-impact-view" role="group" aria-label="Impact trace view">
        <button type="button" aria-pressed={view === 'flow'} onClick={() => setView('flow')}>Flow</button>
        <button type="button" aria-pressed={view === 'audit'} onClick={() => setView('audit')}>Audit</button>
      </div>
    </header>

    {view === 'flow' ? <div className="p-impact-ripple">
      <div className="p-impact-ripple-origin"><span>Starting point</span><strong>{originLabel}</strong>{originDetail && <p>{originDetail}</p>}</div>
      <ol>{uniqueEffects.map((effect, index) => <li key={effect.objectId} className={effect.state === 'HOLDS' ? 'is-held' : 'is-changed'}>
        <button type="button" aria-pressed={selectedObjectId === effect.objectId} onClick={() => onSelect(effect.objectId)}>
          <span className="p-impact-order">{String(index + 1).padStart(2, '0')}</span>
          <span className="p-impact-effect-state">{humanState(effect.state)}</span>
          <strong>{effect.objectLabel}</strong>
          <span className="p-impact-ripple-diff"><small>{currentLabel}</small>{effect.before ?? 'Not supplied'}<b>→</b><small>{changedLabel}</small>{effect.after ?? (effect.state === 'HOLDS' ? effect.before ?? 'Held' : 'Changed')}</span>
          {snapshot && <ReasonPath snapshot={snapshot} relationIds={effect.reasonRelationIds} />}
        </button>
      </li>)}</ol>
    </div> : <div className="p-impact-audit-wrap"><table className="p-impact-audit">
      <thead><tr><th>Object</th><th>Effect</th><th>{currentLabel}</th><th>{changedLabel}</th><th>Why reached</th></tr></thead>
      <tbody>{uniqueEffects.map(effect => <tr key={effect.objectId} className={effect.state === 'HOLDS' ? 'is-held' : ''}>
        <td><button type="button" onClick={() => onSelect(effect.objectId)}>{effect.objectLabel}</button></td>
        <td>{humanState(effect.state)}</td>
        <td>{effect.before ?? '—'}</td>
        <td>{effect.after ?? (effect.state === 'HOLDS' ? effect.before ?? 'Held' : 'Changed')}</td>
        <td>{snapshot ? relationSummary(snapshot, effect.reasonRelationIds) : '—'}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}

function ReasonPath({ snapshot, relationIds }: { snapshot: PantaCaseSnapshot; relationIds: Id[] }) {
  const relations = relationIds.map(id => snapshot.relations.find(relation => relation.id === id)).filter(Boolean);
  if (!relations.length) return <span className="p-impact-unmapped">No mapped propagation reason.</span>;
  return <span className="p-impact-reason-path">{relations.map(relation => relation && <span key={relation.id}>
    <b>{objectLabel(snapshot, relation.sourceObjectId)} → {objectLabel(snapshot, relation.targetObjectId)}</b>
    {relation.rationale && <small>{relation.rationale}</small>}
  </span>)}</span>;
}

function relationSummary(snapshot: PantaCaseSnapshot, relationIds: Id[]): string {
  const narratives = relationIds.map(id => snapshot.relations.find(relation => relation.id === id)?.rationale).filter(Boolean);
  return narratives.join(' · ') || 'No mapped propagation reason';
}

function objectKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    caseReading: 'Case reading',
    humanPosition: 'Human position',
    metricDefinition: 'Metric definition',
    metricObservation: 'Metric observation',
    modelNode: 'Model output',
    sourceVersion: 'Source version',
    workItem: 'Work item',
    artifactBlock: 'Output section',
    caseEvent: 'Case change',
  };
  return labels[kind] ?? humanState(kind);
}
