import type {
  Actor,
  Artifact,
  ArtifactBlock,
  CaseEvent,
  Unknown,
  Id,
  InspectionPayload,
  WorkItem,
  ObjectKind,
  ObjectRef,
  PantaCaseSnapshot,
  HumanPosition,
  Quantity,
  CaseReading,
  DecisionRecord,
  ImpactChange,
  Relation,
  Question,
  Workstream,
} from '../types/domain';

export function caseReadingById(snapshot: PantaCaseSnapshot, id?: Id): CaseReading | undefined {
  return id ? snapshot.caseReadings.find(x => x.id === id) : undefined;
}
export function unknownById(snapshot: PantaCaseSnapshot, id?: Id): Unknown | undefined {
  return id ? snapshot.unknowns.find(x => x.id === id) : undefined;
}
export function actorById(snapshot: PantaCaseSnapshot, id?: Id): Actor | undefined {
  return id ? snapshot.actors.find(x => x.id === id) : undefined;
}
/** Case ownership is derived from the earliest canonical creation event. */
export function caseOwner(snapshot: PantaCaseSnapshot): Actor | undefined {
  const creationEvent = [...snapshot.events]
    .filter(event => event.eventType === 'CASE_CREATED')
    .sort((left, right) => left.recordedAt.localeCompare(right.recordedAt) || left.id.localeCompare(right.id))[0];
  return actorById(snapshot, creationEvent?.actorOrPolicyId);
}
/** A case exists, but PANTA has not yet formed any case structure. */
export function isCaseUnformed(snapshot: PantaCaseSnapshot): boolean {
  return !snapshot.formation
    && snapshot.workstreams.length === 0
    && snapshot.questions.length === 0
    && snapshot.caseReadings.length === 0;
}
export function workItemById(snapshot: PantaCaseSnapshot, id?: Id): WorkItem | undefined {
  return id ? snapshot.workItems.find(x => x.id === id) : undefined;
}
export function eventById(snapshot: PantaCaseSnapshot, id?: Id): CaseEvent | undefined {
  return id ? snapshot.events.find(x => x.id === id) : undefined;
}
export function humanPositionById(snapshot: PantaCaseSnapshot, id?: Id): HumanPosition | undefined {
  return id ? snapshot.humanPositions.find(x => x.id === id) : undefined;
}
export function quantityById(snapshot: PantaCaseSnapshot, id?: Id): Quantity | undefined {
  return id ? snapshot.quantities.find(x => x.id === id) : undefined;
}
export function artifactById(snapshot: PantaCaseSnapshot, id?: Id): Artifact | undefined {
  return id ? snapshot.artifacts.find(x => x.id === id) : undefined;
}
export function blockById(snapshot: PantaCaseSnapshot, id?: Id): ArtifactBlock | undefined {
  return id ? snapshot.artifactBlocks.find(x => x.id === id) : undefined;
}
export function questionById(snapshot: PantaCaseSnapshot, id?: Id): Question | undefined {
  return id ? snapshot.questions.find(x => x.id === id) : undefined;
}
export function workstreamById(snapshot: PantaCaseSnapshot, id?: Id): Workstream | undefined {
  return id ? snapshot.workstreams.find(x => x.id === id) : undefined;
}

/** Deal Home attention summary. ID order remains backend-owned; the UI never invents priority. */
export function dealWorkstreamSummary(snapshot: PantaCaseSnapshot, workstream: Workstream) {
  const reading = caseReadingById(snapshot, workstream.currentCaseReadingId);
  const openPoint = workstream.openUnknownIds
    .map(id => unknownById(snapshot, id))
    .find(item => item?.status === 'OPEN');
  const nextStep = workstream.activeWorkItemIds
    .map(id => workItemById(snapshot, id))
    .find(item => item
      && item.status !== 'COMPLETED'
      && item.status !== 'CANCELLED'
      && item.institutionalState !== 'REJECTED'
      && item.institutionalState !== 'RETIRED');
  const owner = actorById(snapshot, workstream.ownerActorId);
  const nextStepOwner = actorById(snapshot, nextStep?.ownerActorId);
  const latestChange = eventById(snapshot, workstream.latestChangeEventId)
    ?? eventById(snapshot, reading?.lastChangeEventId);
  const humanPosition = humanPositionsForScope(snapshot, [workstream.id, reading?.id])[0];
  return { reading, openPoint, nextStep, owner, nextStepOwner, latestChange, humanPosition };
}

/** Resolve the canonical decision linked by the decision context before using a deterministic fallback. */
export function recordedDecision(snapshot: PantaCaseSnapshot): DecisionRecord | undefined {
  if (snapshot.decision?.status !== 'RECORDED') return undefined;
  const recordedDecisionId = snapshot.decision?.recordedDecisionId;
  if (recordedDecisionId) {
    const linked = snapshot.decisions.find(decision => decision.id === recordedDecisionId);
    if (linked) return linked;
  }
  return [...snapshot.decisions].sort((a, b) =>
    b.recordedAt.localeCompare(a.recordedAt) || b.id.localeCompare(a.id)
  )[0];
}

/** Backend-selected questions only; the frontend neither ranks nor scores the decision frontier. */
export function decisionCriticalQuestions(snapshot: PantaCaseSnapshot): Question[] {
  return snapshot.questions.filter(question => question.decisionDimensions
    && question.questionStatus !== 'RESOLVED'
    && question.questionStatus !== 'RISK_ACCEPTED'
    && question.questionStatus !== 'RETIRED');
}

/** Every simulated object appears once; a material effect wins over a duplicate HOLD. */
export function normalizeSimulationEffects(effects: ImpactChange[]): ImpactChange[] {
  const byObjectId = new Map<Id, ImpactChange>();
  for (const effect of effects) {
    const current = byObjectId.get(effect.objectId);
    if (!current || (current.state === 'HOLDS' && effect.state !== 'HOLDS')) {
      byObjectId.set(effect.objectId, effect);
    }
  }
  return [...byObjectId.values()];
}

export function simulationImpactCounts(effects: ImpactChange[]): { total: number; changed: number; held: number } {
  const normalized = normalizeSimulationEffects(effects);
  const held = normalized.filter(effect => effect.state === 'HOLDS').length;
  return { total: normalized.length, changed: normalized.length - held, held };
}

export function formatCount(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function formatRemaining(count: number, singular: string, plural = `${singular}s`): string {
  return `${formatCount(count, singular, plural)} ${count === 1 ? 'remains' : 'remain'}`;
}

export function humanPositionsForScope(snapshot: PantaCaseSnapshot, scopeIds: Array<Id | undefined>): HumanPosition[] {
  const ids = new Set(scopeIds.filter(Boolean) as Id[]);
  return snapshot.humanPositions.filter(p => ids.has(p.scopeObjectId) && (p.institutionalState === 'CURRENT' || p.institutionalState === 'APPROVED'));
}

export function relationsFrom(snapshot: PantaCaseSnapshot, id: Id): Relation[] {
  return snapshot.relations.filter(r => r.sourceObjectId === id);
}
export function relationsTo(snapshot: PantaCaseSnapshot, id: Id): Relation[] {
  return snapshot.relations.filter(r => r.targetObjectId === id);
}

export function objectKind(snapshot: PantaCaseSnapshot, id: Id): ObjectKind | undefined {
  if (snapshot.caseRef.id === id) return 'case';
  if (snapshot.actors.some(x => x.id === id)) return 'actor';
  if (snapshot.workstreams.some(x => x.id === id)) return 'workstream';
  if (snapshot.questions.some(x => x.id === id)) return 'question';
  if (snapshot.caseReadings.some(x => x.id === id)) return 'caseReading';
  if (snapshot.claims.some(x => x.id === id)) return 'claim';
  if (snapshot.metricDefinitions.some(x => x.id === id)) return 'metricDefinition';
  if (snapshot.metricObservations.some(x => x.id === id)) return 'metricObservation';
  if (snapshot.assumptions.some(x => x.id === id)) return 'assumption';
  if (snapshot.risks.some(x => x.id === id)) return 'risk';
  if (snapshot.modelNodes.some(x => x.id === id)) return 'modelNode';
  if (snapshot.outcomes.some(x => x.id === id)) return 'outcome';
  if (snapshot.sources.some(x => x.id === id)) return 'source';
  if (snapshot.sourceVersions.some(x => x.id === id)) return 'sourceVersion';
  if (snapshot.findings.some(x => x.id === id)) return 'finding';
  if (snapshot.humanPositions.some(x => x.id === id)) return 'humanPosition';
  if (snapshot.workItems.some(x => x.id === id)) return 'workItem';
  if (snapshot.quantities.some(x => x.id === id)) return 'quantity';
  if (snapshot.artifacts.some(x => x.id === id)) return 'artifact';
  if (snapshot.artifactBlocks.some(x => x.id === id)) return 'artifactBlock';
  if (snapshot.events.some(x => x.id === id)) return 'caseEvent';
  if (snapshot.unknowns.some(x => x.id === id)) return 'unknown';
  if (snapshot.conditions.some(x => x.id === id)) return 'condition';
  if (snapshot.decisions.some(x => x.id === id)) return 'decision';
  return undefined;
}

export function objectLabel(snapshot: PantaCaseSnapshot, id: Id): string {
  if (snapshot.caseRef.id === id) return snapshot.caseRef.name;
  const event = snapshot.events.find(x => x.id === id);
  return snapshot.workstreams.find(x => x.id === id)?.name
    ?? snapshot.questions.find(x => x.id === id)?.name
    ?? snapshot.caseReadings.find(x => x.id === id)?.text
    ?? snapshot.claims.find(x => x.id === id)?.label
    ?? snapshot.metricDefinitions.find(x => x.id === id)?.canonicalName
    ?? snapshot.metricObservations.find(x => x.id === id)?.displayLabel
    ?? snapshot.assumptions.find(x => x.id === id)?.statementOrValue
    ?? snapshot.risks.find(x => x.id === id)?.mechanism
    ?? snapshot.modelNodes.find(x => x.id === id)?.label
    ?? snapshot.outcomes.find(x => x.id === id)?.displayLabel
    ?? snapshot.sources.find(x => x.id === id)?.title
    ?? snapshot.findings.find(x => x.id === id)?.title
    ?? snapshot.humanPositions.find(x => x.id === id)?.text
    ?? snapshot.workItems.find(x => x.id === id)?.name
    ?? snapshot.quantities.find(x => x.id === id)?.label
    ?? snapshot.artifacts.find(x => x.id === id)?.title
    ?? snapshot.artifactBlocks.find(x => x.id === id)?.title
    ?? (event ? eventDisplayLabel(snapshot, event) : undefined)
    ?? snapshot.conditions.find(x => x.id === id)?.label
    ?? snapshot.unknowns.find(x => x.id === id)?.title
    ?? snapshot.actors.find(x => x.id === id)?.displayName
    ?? snapshot.decisions.find(x => x.id === id)?.rationale
    ?? id;
}

export function eventDisplayLabel(snapshot: PantaCaseSnapshot, event: CaseEvent): string {
  const base: Record<CaseEvent['eventType'], string> = {
    CASE_CREATED: 'Case created',
    SOURCE_REGISTERED: 'Source added',
    SOURCE_VERSION_RECORDED: 'Source updated',
    CLAIM_RECORDED: 'Claim recorded',
    METRIC_OBSERVATION_RECORDED: 'Metric recorded',
    QUESTION_PROPOSED: 'Question proposed',
    QUESTION_SPINE_CHANGED: 'Case structure changed',
    UNKNOWN_RECORDED: 'Gap recorded',
    HUMAN_POSITION_RECORDED: 'Human view recorded',
    CASE_READING_RECOMPUTED: 'Reading updated',
    ASSUMPTION_PROPOSED: 'Assumption proposed',
    ASSUMPTION_ADOPTED: 'Assumption adopted',
    ASSUMPTION_CHALLENGED: 'Assumption challenged',
    RISK_RECORDED: 'Risk recorded',
    MODEL_NODE_BOUND: 'Model binding updated',
    RELATION_ESTABLISHED: 'Relationship updated',
    CONDITION_RECORDED: 'Condition recorded',
    CONDITION_STATE_RECORDED: 'Condition updated',
    DECISION_RECORDED: 'Decision recorded',
    WORK_ITEM_RECORDED: 'Work added',
    WORK_ITEM_STATE_RECORDED: 'Work updated',
    ARTIFACT_VERSION_RECORDED: 'Output updated',
    OUTCOME_RECORDED: 'Outcome recorded',
    PROPOSAL_REJECTED: 'Proposal rejected',
    OBJECT_SUPERSEDED: 'Object superseded',
    OBJECT_RETIRED: 'Object retired',
  };
  const target = event.objectId && event.objectId !== event.id ? objectLabelWithoutEvent(snapshot, event.objectId) : undefined;
  return target ? `${base[event.eventType]} · ${target}` : base[event.eventType];
}

function objectLabelWithoutEvent(snapshot: PantaCaseSnapshot, id: Id): string | undefined {
  if (snapshot.caseRef.id === id) return snapshot.caseRef.name;
  return snapshot.workstreams.find(x => x.id === id)?.name
    ?? snapshot.questions.find(x => x.id === id)?.name
    ?? snapshot.caseReadings.find(x => x.id === id)?.text
    ?? snapshot.claims.find(x => x.id === id)?.label
    ?? snapshot.metricDefinitions.find(x => x.id === id)?.canonicalName
    ?? snapshot.metricObservations.find(x => x.id === id)?.displayLabel
    ?? snapshot.assumptions.find(x => x.id === id)?.statementOrValue
    ?? snapshot.risks.find(x => x.id === id)?.mechanism
    ?? snapshot.modelNodes.find(x => x.id === id)?.label
    ?? snapshot.outcomes.find(x => x.id === id)?.displayLabel
    ?? snapshot.sources.find(x => x.id === id)?.title
    ?? snapshot.findings.find(x => x.id === id)?.title
    ?? snapshot.humanPositions.find(x => x.id === id)?.text
    ?? snapshot.workItems.find(x => x.id === id)?.name
    ?? snapshot.quantities.find(x => x.id === id)?.label
    ?? snapshot.artifacts.find(x => x.id === id)?.title
    ?? snapshot.conditions.find(x => x.id === id)?.label
    ?? snapshot.unknowns.find(x => x.id === id)?.title
    ?? snapshot.actors.find(x => x.id === id)?.displayName;
}

export function objectRef(snapshot: PantaCaseSnapshot, id: Id): ObjectRef {
  return { id, kind: objectKind(snapshot, id) ?? 'caseEvent', label: objectLabel(snapshot, id) };
}

export function supportSummary(snapshot: PantaCaseSnapshot, reading: CaseReading): { total: number; independent: number; labels: string[] } {
  const activeSupportIds = new Set(reading.supportObjectIds);
  return {
    total: reading.supportObjectIds.length,
    independent: reading.independentSupportObjectIds.filter(id => activeSupportIds.has(id)).length,
    labels: reading.supportObjectIds.slice(0, 3).map(id => objectLabel(snapshot, id)),
  };
}

export interface LensViewModel {
  title: string;
  kind: string;
  supportCount: number;
  independentCount: number;
  supportRefs: ObjectRef[];
  unknowns: ObjectRef[];
  dependents: ObjectRef[];
  lastChange?: { eventId: Id; label: string; date: string; knownAt: string };
  related: ObjectRef[];
  sourceRefs: ObjectRef[];
  actions: InspectionPayload['allowedActions'];
}

export function composeLens(snapshot: PantaCaseSnapshot, inspection: InspectionPayload): LensViewModel {
  const supportRefs = inspection.supportObjectIds.map(id => objectRef(snapshot, id));
  const unknowns = inspection.unknownIds.map(id => objectRef(snapshot, id));
  const dependents = inspection.dependentObjectIds.map(id => objectRef(snapshot, id));
  const related = inspection.relatedObjectIds.map(id => objectRef(snapshot, id));
  const sourceRefs = inspection.sourceLocators.map(x => objectRef(snapshot, x.sourceId));
  const event = eventById(snapshot, inspection.lastChangeEventId);
  return {
    title: objectLabel(snapshot, inspection.objectId),
    kind: objectKind(snapshot, inspection.objectId) ?? 'object',
    supportCount: supportRefs.length,
    independentCount: inspection.independentSupportObjectIds.length,
    supportRefs,
    unknowns,
    dependents,
    lastChange: event ? { eventId: event.id, label: eventDisplayLabel(snapshot, event), date: event.effectiveAt ?? event.knownAt, knownAt: event.knownAt } : undefined,
    related,
    sourceRefs,
    actions: inspection.allowedActions,
  };
}

export function humanState(state?: string): string {
  if (!state) return '';
  return state.toLowerCase().replaceAll('_', ' ').replace(/^./, x => x.toUpperCase());
}

export function quantityDisplayState(quantity: Quantity): string {
  if (quantity.value == null) return 'Not yet established';
  if (quantity.freshnessStatus === 'STALE') return 'Stale';
  if (quantity.freshnessStatus === 'EXPIRED') return 'Expired';
  if (quantity.institutionalState === 'CANDIDATE') return 'Candidate';
  return 'Current';
}

export interface ObjectStateToken {
  axis: 'Freshness' | 'Evidence' | 'Decision' | 'Position' | 'Status';
  label: string;
  tone: 'current' | 'warning' | 'decision' | 'neutral';
}

/** Keep the kernel's independent state axes independent in every trace projection. */
export function objectStateTokens(snapshot: PantaCaseSnapshot, id: Id): ObjectStateToken[] {
  const reading = caseReadingById(snapshot, id);
  if (reading) return compactTokens([
    token('Freshness', reading.freshnessStatus),
    token('Evidence', reading.epistemicStatus),
    reading.decisionLinkStatus !== 'NO_DECISION' ? token('Decision', reading.decisionLinkStatus) : undefined,
  ]);

  const position = humanPositionById(snapshot, id);
  if (position) return [token('Position', position.institutionalState)];

  const quantity = quantityById(snapshot, id);
  if (quantity) return compactTokens([
    token('Freshness', quantity.freshnessStatus),
    token('Position', quantity.institutionalState),
  ]);

  const observation = snapshot.metricObservations.find(item => item.id === id);
  if (observation) return compactTokens([
    observation.freshnessStatus ? token('Freshness', observation.freshnessStatus) : undefined,
    token('Position', observation.institutionalState),
  ]);

  const modelNode = snapshot.modelNodes.find(item => item.id === id);
  if (modelNode) return compactTokens([
    modelNode.freshnessStatus ? token('Freshness', modelNode.freshnessStatus) : undefined,
    modelNode.executionStatus ? token('Status', modelNode.executionStatus) : undefined,
  ]);

  const assumption = snapshot.assumptions.find(item => item.id === id);
  if (assumption) return compactTokens([
    assumption.freshnessStatus ? token('Freshness', assumption.freshnessStatus) : undefined,
    assumption.epistemicStatus ? token('Evidence', assumption.epistemicStatus) : undefined,
    token('Status', assumption.status),
  ]);

  const question = questionById(snapshot, id);
  if (question) return [token('Status', question.questionStatus)];

  const unknown = unknownById(snapshot, id);
  if (unknown) return [token('Status', unknown.status)];

  const condition = snapshot.conditions.find(item => item.id === id);
  if (condition) return compactTokens([
    condition.freshnessStatus ? token('Freshness', condition.freshnessStatus) : undefined,
    token('Status', condition.status),
  ]);

  const workItem = workItemById(snapshot, id);
  if (workItem) return compactTokens([
    token('Status', workItem.status),
    workItem.institutionalState ? token('Position', workItem.institutionalState) : undefined,
  ]);

  const artifact = artifactById(snapshot, id);
  if (artifact) return compactTokens([
    token('Freshness', artifact.freshnessStatus),
    token('Status', artifact.syncStatus),
  ]);

  const risk = snapshot.risks.find(item => item.id === id);
  if (risk?.epistemicStatus) return [token('Evidence', risk.epistemicStatus)];
  return [];
}

/** Relationship copy remains investor-facing; relation vocabulary is never exposed as UI language. */
export function relationshipNarrative(snapshot: PantaCaseSnapshot, sourceId: Id, targetId: Id): string | undefined {
  return snapshot.relations.find(relation =>
    relation.sourceObjectId === sourceId
    && relation.targetObjectId === targetId
    && (relation.institutionalState === 'CURRENT' || relation.institutionalState === 'APPROVED')
  )?.rationale;
}

function token(axis: ObjectStateToken['axis'], value: string): ObjectStateToken {
  const warningValues = new Set(['STALE', 'EXPIRED', 'UNKNOWN', 'INSUFFICIENT', 'CONTESTED', 'INVALIDATED', 'BLOCKED', 'FAILED', 'BROKEN', 'BASIS_STALE', 'REOPENED']);
  const currentValues = new Set(['CURRENT', 'SUPPORTED', 'RESOLVED', 'SATISFIED', 'COMPLETED']);
  return {
    axis,
    label: humanState(value),
    tone: axis === 'Decision' ? 'decision' : warningValues.has(value) ? 'warning' : currentValues.has(value) ? 'current' : 'neutral',
  };
}

function compactTokens(tokens: Array<ObjectStateToken | undefined>): ObjectStateToken[] {
  return tokens.filter((value): value is ObjectStateToken => Boolean(value));
}

export function workItemDisplayState(item: WorkItem): string {
  if (item.kind === 'PANTA_PROPOSAL' && item.status === 'PROPOSED') return 'PANTA proposal · not adopted';
  if (!item.ownerActorId && item.status !== 'COMPLETED' && item.status !== 'CANCELLED') return 'Unassigned';
  return humanState(item.status);
}
