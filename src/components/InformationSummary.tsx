import React, { useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { actorById, humanState, objectLabel } from '../app/selectors';
import { trackingLinks } from '../app/trackingLinks';

/** Concise context from the selected canonical object; never infer missing dimensions. */
export function InformationSummary({ objectId }: { objectId: string }) {
  const { snapshot, setActiveObject, inspecting, openSource } = usePanta();
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
  const decision = snapshot.decisions.find(item => item.id === objectId);
  const block = snapshot.artifactBlocks.find(item => item.id === objectId);
  const context = claim?.tracking;
  const number = quantity ?? observation;
  const dimensions = quantity?.perimeter ?? observation ?? context;
  const value = quantity?.display ?? (number?.value != null ? String(number.value) : context?.value != null ? String(context.value) : node?.currentValue != null ? String(node.currentValue) : undefined);
  const body = block?.text ?? claim?.normalizedStatement ?? human?.text ?? reading?.text ?? finding?.proposition ?? assumption?.statementOrValue ?? risk?.mechanism ?? decision?.rationale ?? (outcome?.observedValueOrState != null ? String(outcome.observedValueOrState) : undefined);
  const definition = snapshot.metricDefinitions.find(item => item.id === number?.metricDefinitionId);
  const kind = claim?.claimKind ?? context?.claimKind;
  const rows = [
    ['Type', block ? 'Output passage' : kind ? humanState(kind) : human ? 'Personal view' : reading ? 'PANTA synthesis' : finding ? 'Proposed finding' : assumption ? 'Assumption' : decision ? 'Recorded decision' : undefined],
    ['Value', value == null ? undefined : quantity?.display ?? [value, number?.currency ?? context?.currency, number?.unit ?? context?.unit ?? node?.unit].filter(Boolean).join(' · ')],
    ['Precision', context?.bound && context.bound !== 'NONE' ? humanState(context.bound) : undefined],
    ['Source value', context?.rawValue != null && String(context.rawValue) !== value ? String(context.rawValue) : undefined],
    ['Metric', definition?.canonicalName ?? context?.metric],
    ['Definition', definition?.basisDefinition ?? context?.definition],
    ['Entity', context?.entity],
    ['Period', dimensions?.period], ['Scope', dimensions?.scope], ['Basis', dimensions?.basis],
    ['Measure', dimensions?.measurement], ['Scenario', dimensions?.scenario ?? assumption?.scenario],
    ['Environment', quantity?.perimeter.geographyOrEnvironment],
    ['Author', human || decision ? actorById(snapshot, human?.authorActorId ?? decision?.actorOrBodyId)?.displayName ?? 'Author details unavailable' : undefined],
    ['Recorded', block?.recordedAt ?? human?.recordedAt ?? decision?.recordedAt], ['Computed', reading?.computedAt],
    ['Passage author', block?.authorActorId ? actorById(snapshot, block.authorActorId)?.displayName ?? block.authorActorId : undefined],
    ['Writing assistant', block?.writerModel],
    ['Reviewed by', block?.reviewedBy ? actorById(snapshot, block.reviewedBy)?.displayName ?? block.reviewedBy : undefined],
    ['Reviewed at', block?.reviewedAt],
    ['Decision', decision?.decision ?? snapshot.decisionPaths.find(item => item.id === decision?.pathId)?.label],
    ['Case version at decision', decision?.caseVersion],
  ].filter((row): row is [string, string] => typeof row[1] === 'string' && row[1].length > 0);
  const inputs = [...new Set([...(number?.sourceObjectIds ?? []), ...(quantity?.assumptionObjectIds ?? [])])];
  return <section className="p-information-summary" aria-label="Information summary">
    {body && <p>{body}</p>}
    {block && <div><span className="p-field-label">Basis saved with this passage</span>{block.freshnessStatus && block.freshnessStatus !== 'CURRENT' && <p>This passage needs review. Connections below open the current case; these citations retain the saved source version.</p>}{block.frozenBasis?.map(ref => <div key={ref.objectId}><p>{ref.text}</p>{ref.sourceLocator && <button className="p-related-link" onClick={() => openSource({ ...ref.sourceLocator!, artifactBlockId: block.id })}>Open cited passage · {ref.sourceLocator.locator ?? 'Document'}</button>}</div>)}</div>}
    {!!rows.length && <dl>{rows.map(([label, text]) => <div key={label}><dt>{label}</dt><dd>{text}</dd></div>)}</dl>}
    {(quantity?.formula || context?.derivation) && <div><span className="p-field-label">Calculation</span><code>{quantity?.formula ?? context?.derivation}</code></div>}
    {claim && (!context || !!context.missingFields.length) && <div><span className="p-field-label">Context still missing</span><p>{context ? context.missingFields.map(humanState).join(' · ') : 'Definition, period, scope, basis and unit have not been supplied.'}</p></div>}
    {!!context?.validationNotes.length && <div><span className="p-field-label">Needs verification</span>{context.validationNotes.map(note => <p key={note}>{note}</p>)}</div>}
    {decision && decision.caseVersion !== snapshot.caseVersion && <p>This decision used an earlier case version. Its basis is available in that recorded version.</p>}
    {!!inputs.length && <div><span className="p-field-label">Calculation / observation inputs</span>{inputs.map(id => <button key={id} className="p-related-link" disabled={inspecting} onClick={() => { void setActiveObject(id); }}>{objectLabel(snapshot, id)}</button>)}</div>}
    {claim?.limitation && <div><span className="p-field-label">What this doesn't prove</span><p>{claim.limitation}</p></div>}
    <RecordedConnections key={objectId} objectId={objectId} />
  </section>;
}

function RecordedConnections({ objectId }: { objectId: string }) {
  const { snapshot, setActiveObject, inspecting } = usePanta();
  const [expanded, setExpanded] = useState(false);
  const links = useMemo(() => snapshot ? trackingLinks(snapshot, objectId) : [], [snapshot, objectId]);
  if (!snapshot || !links.length) return null;
  return <div aria-label="Recorded connections"><span className="p-field-label">Recorded connections</span>
    {(expanded ? links : links.slice(0, 5)).map(link => <button key={`${link.objectId}-${link.label}`} className="p-related-link" disabled={inspecting || !link.available} onClick={() => { void setActiveObject(link.objectId); }}>
      {link.label}: {objectLabel(snapshot, link.objectId)}{!link.available && ' · Not available in this case version'}
    </button>)}
    {links.length > 5 && <button className="p-related-link" onClick={() => setExpanded(value => !value)}>{expanded ? 'Show fewer recorded connections' : `Show all ${links.length} recorded connections`}</button>}
  </div>;
}
