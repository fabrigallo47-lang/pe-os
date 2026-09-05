import React from 'react';
import { usePanta } from '../app/PantaContext';
import { actorById, humanState, objectLabel } from '../app/selectors';

/** Concise context from the selected canonical object; never infer missing dimensions. */
export function InformationSummary({ objectId }: { objectId: string }) {
  const { snapshot, setActiveObject, inspecting } = usePanta();
  if (!snapshot) return null;
  const claim = snapshot.claims.find(item => item.id === objectId);
  const quantity = snapshot.quantities.find(item => item.id === objectId);
  const observation = snapshot.metricObservations.find(item => item.id === objectId);
  const human = snapshot.humanPositions.find(item => item.id === objectId);
  const reading = snapshot.caseReadings.find(item => item.id === objectId);
  const finding = snapshot.findings.find(item => item.id === objectId);
  const assumption = snapshot.assumptions.find(item => item.id === objectId);
  const node = snapshot.modelNodes.find(item => item.id === objectId);
  const risk = snapshot.risks.find(item => item.id === objectId);
  const outcome = snapshot.outcomes.find(item => item.id === objectId);
  const number = quantity ?? observation;
  const dimensions = quantity?.perimeter ?? observation;
  const value = quantity?.display ?? (number?.value != null ? String(number.value) : node?.currentValue != null ? String(node.currentValue) : undefined);
  const body = claim?.normalizedStatement ?? human?.text ?? reading?.text ?? finding?.proposition ?? assumption?.statementOrValue ?? risk?.mechanism ?? (outcome?.observedValueOrState != null ? String(outcome.observedValueOrState) : undefined);
  const rows = [
    ['Type', claim?.claimKind ? humanState(claim.claimKind) : human ? 'Personal view' : reading ? 'PANTA synthesis' : finding ? 'Proposed finding' : assumption ? 'Assumption' : undefined],
    ['Value', value == null ? undefined : quantity?.display ?? [value, number?.currency, number?.unit ?? node?.unit].filter(Boolean).join(' · ')],
    ['Period', dimensions?.period], ['Scope', dimensions?.scope], ['Basis', dimensions?.basis],
    ['Measure', dimensions?.measurement], ['Scenario', dimensions?.scenario ?? assumption?.scenario],
    ['Environment', quantity?.perimeter.geographyOrEnvironment],
    ['Author', human ? actorById(snapshot, human.authorActorId)?.displayName ?? 'Author details unavailable' : undefined],
    ['Recorded', human?.recordedAt], ['Computed', reading?.computedAt],
  ].filter((row): row is [string, string] => typeof row[1] === 'string' && row[1].length > 0);
  const inputs = [...new Set([...(number?.sourceObjectIds ?? []), ...(quantity?.assumptionObjectIds ?? [])])];
  if (!body && !rows.length && !quantity?.formula && !inputs.length) return null;
  return <section className="p-information-summary" aria-label="Information summary">
    {body && <p>{body}</p>}
    {!!rows.length && <dl>{rows.map(([label, text]) => <div key={label}><dt>{label}</dt><dd>{text}</dd></div>)}</dl>}
    {quantity?.formula && <div><span className="p-field-label">Calculation</span><code>{quantity.formula}</code></div>}
    {!!inputs.length && <div><span className="p-field-label">Calculation / observation inputs</span>{inputs.map(id => <button key={id} className="p-related-link" disabled={inspecting} onClick={() => { void setActiveObject(id); }}>{objectLabel(snapshot, id)}</button>)}</div>}
    {claim?.limitation && <div><span className="p-field-label">What this doesn't prove</span><p>{claim.limitation}</p></div>}
  </section>;
}
