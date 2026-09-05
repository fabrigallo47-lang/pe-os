import type { Id, InspectionPayload, PantaCaseSnapshot } from '../types/domain';

export interface TrackingLink { objectId: Id; label: string; available: boolean }

/** Navigation over supplied references only. This never computes support or propagation. */
export function trackingLinks(snapshot: PantaCaseSnapshot, selected: Id): TrackingLink[] {
  const objects = new Set(Object.values(snapshot).flatMap(value => Array.isArray(value)
    ? value.filter(item => item && typeof item.id === 'string').map(item => item.id as string) : []));
  const links = new Map<string, TrackingLink>();
  const connect = (from: Id | undefined, to: Id | undefined, forward: string, reverse: string, resolved = true) => {
    if (!from || !to || from === to || (selected !== from && selected !== to)) return;
    const objectId = selected === from ? to : from;
    const label = selected === from ? forward : reverse;
    links.set(`${objectId}|${label}`, { objectId, label, available: resolved && objects.has(objectId) });
  };
  for (const version of snapshot.sourceVersions) connect(version.id, version.sourceId, 'Document', 'Document version');
  for (const claim of snapshot.claims) {
    connect(claim.id, claim.sourceVersionId, 'Cited version', 'Statement in this version');
    const version = snapshot.sourceVersions.find(item => item.id === claim.sourceVersionId && (!claim.sourceId || item.sourceId === claim.sourceId));
    if (version) connect(claim.id, version.sourceId, 'Source document', 'Statement from this document');
  }
  for (const item of [...snapshot.quantities, ...snapshot.metricObservations]) {
    for (const id of item.sourceObjectIds) connect(item.id, id, 'Input', 'Used in calculation / observation');
  }
  for (const item of snapshot.caseReadings) {
    for (const id of item.supportObjectIds) connect(item.id, id, 'Reading basis', 'Used in this reading');
  }
  for (const item of snapshot.humanPositions) connect(item.id, item.scopeObjectId, 'View concerns', 'Personal view on this');
  for (const item of snapshot.decisions) {
    for (const id of item.basisObjectIds ?? []) connect(item.id, id, 'Recorded decision basis', 'Used in recorded decision', item.caseVersion === snapshot.caseVersion);
    for (const id of item.conditionIds ?? []) connect(item.id, id, 'Decision condition', 'Condition of decision', item.caseVersion === snapshot.caseVersion);
  }
  for (const item of snapshot.artifactBlocks) {
    for (const id of item.boundObjectIds) connect(item.id, id, 'Section basis', 'Used in output section');
  }
  for (const relation of snapshot.relations) {
    if (relation.caseId !== snapshot.caseRef.id || !['CURRENT', 'APPROVED'].includes(relation.institutionalState)) continue;
    const labels: Record<string, [string, string]> = {
      SUPPORTS: ['Supports', 'Supported by'], CHALLENGES: ['Challenges', 'Challenged by'],
      CONTRADICTS: ['Contradicts', 'Contradicted by'], CORROBORATES: ['Corroborates', 'Corroborated by'],
      DERIVES_FROM: ['Derived from', 'Used in derivation'], DRIVES: ['Affects', 'Affected by'],
      ABOUT: ['Concerns', 'Mentioned in'], BEARS_ON: ['Relevant to', 'Relevant evidence'],
      CONDITIONS: ['Conditions', 'Conditional on'], RESOLVES: ['Resolves', 'Resolved by'],
      ADOPTS: ['Adopts', 'Adopted by'], SUPERSEDES: ['Replaces', 'Replaced by'], PRODUCES: ['Produces', 'Produced by'],
    };
    const labelsForType = labels[relation.type];
    const frozenBasisAvailable = !snapshot.decisions.some(item =>
      (item.id === relation.sourceObjectId || item.id === relation.targetObjectId) && item.caseVersion !== snapshot.caseVersion);
    if (labelsForType) connect(relation.sourceObjectId, relation.targetObjectId, ...labelsForType, frozenBasisAvailable);
  }
  return [...links.values()];
}

/** An existing projection object is inspectable even without additional backend analysis. */
export function projectionInspection(snapshot: PantaCaseSnapshot, id: Id): InspectionPayload | null {
  const exists = Object.values(snapshot).some(value => Array.isArray(value) && value.some(item => item?.id === id));
  const claim = snapshot.claims.find(item => item.id === id);
  const version = snapshot.sourceVersions.find(item => item.id === (claim?.sourceVersionId ?? id));
  const source = snapshot.sources.find(item => item.id === id);
  const sourceId = version?.sourceId ?? source?.id;
  const sourceLocators = sourceId && (!claim?.sourceId || claim.sourceId === sourceId)
    ? [{ sourceId, sourceVersionId: version?.id ?? source?.currentVersionId, ...(claim ? { claimId: claim.id, locator: claim.locator } : {}) }] : [];
  return exists ? { objectId: id, supportObjectIds: [], independentSupportObjectIds: [], dependentObjectIds: [],
    unknownIds: [], relatedObjectIds: [], sourceLocators, allowedActions: sourceLocators.length ? ['OPEN_SOURCE'] : [] } : null;
}
