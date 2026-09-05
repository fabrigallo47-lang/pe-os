// Development-only adapter for a created case before any material has arrived.
// All names and ids in this file are synthetic and remain outside production src/.

export const EMPTY_CASE_ID = 'CASE-EMPTY';

const createdAt = '2026-01-12T09:00:00Z';
const owner = { id: 'ACT-EMPTY-OWNER', type: 'PERSON', displayName: 'Mara Bellini', role: 'Case Owner' };

const initialSnapshot = {
  caseRef: { id: EMPTY_CASE_ID, name: 'New investment case' },
  caseVersion: 'v1',
  asOf: createdAt,
  actors: [owner],
  workstreams: [],
  questions: [],
  caseReadings: [],
  unknowns: [],
  sources: [],
  sourceVersions: [],
  claims: [],
  metricDefinitions: [],
  metricObservations: [],
  assumptions: [],
  risks: [],
  modelNodes: [],
  outcomes: [],
  findings: [],
  humanPositions: [],
  workItems: [],
  quantities: [],
  artifacts: [],
  artifactBlocks: [],
  artifactDiffs: [],
  relations: [],
  events: [{
    id: 'EV-EMPTY-CREATED',
    caseId: EMPTY_CASE_ID,
    eventType: 'CASE_CREATED',
    objectType: 'case',
    objectId: EMPTY_CASE_ID,
    effectiveAt: createdAt,
    knownAt: createdAt,
    recordedAt: createdAt,
    actorOrPolicyId: owner.id,
    schemaVersion: '0.1.0',
    idempotencyKey: 'empty-case-created',
  }],
  pendingReviews: [],
  simulationOptions: [],
  conditions: [],
  decisionPaths: [],
  decisions: [],
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export class EmptyCaseAdapter {
  constructor() {
    this.current = clone(initialSnapshot);
  }

  async getSession() {
    return {
      actor: { actorId: owner.id, entitlements: ['READ_CASE', 'ADD_MATERIAL'] },
      actors: [owner],
    };
  }

  async listCases() {
    return [{ id: EMPTY_CASE_ID, name: this.current.caseRef.name }];
  }

  async loadCase(caseId, options) {
    if (caseId && caseId !== EMPTY_CASE_ID) return null;
    const snapshot = clone(this.current);
    snapshot.asOf = options?.asOf ?? this.current.asOf;
    return snapshot;
  }

  async listCaseMoments(caseId) {
    if (caseId !== EMPTY_CASE_ID) return [];
    return this.current.events
      .filter(event => event.eventType === 'CASE_CREATED' || event.eventType === 'SOURCE_REGISTERED')
      .map(event => ({
      id: `M-${event.id}`,
      asOf: event.knownAt,
      label: event.eventType === 'CASE_CREATED' ? 'Case created' : 'Material added',
      eventId: event.id,
      }));
  }

  async listJournalStates() {
    return [];
  }

  async loadJournal(caseId, query = {}) {
    if (caseId !== EMPTY_CASE_ID) return null;
    const start = query.since ? `${query.since.slice(0, 10)}T00:00:00Z` : undefined;
    const endValue = query.asOf || query.until;
    const end = endValue ? `${endValue.slice(0, 10)}T23:59:59.999Z` : undefined;
    const events = this.current.events
      .filter(event => (!start || event.knownAt >= start) && (!end || event.knownAt <= end))
      .filter(event => !query.kind || event.eventType === query.kind)
      .map(event => ({
        id: `sha256:empty-${event.id}`,
        eventId: event.id,
        caseId,
        eventType: event.eventType,
        kind: event.eventType,
        phase: event.eventType === 'CASE_CREATED' ? 'ORIGINATION' : 'DILIGENCE',
        label: event.eventType === 'CASE_CREATED' ? 'Case created' : event.eventType === 'SOURCE_REGISTERED' ? 'Material added' : 'Material version recorded',
        actorId: event.actorOrPolicyId,
        actorLabel: owner.displayName,
        actorSource: 'DECLARED',
        effectiveDate: (event.effectiveAt || event.knownAt).slice(0, 10),
        knownAt: event.knownAt,
        recordedAt: event.recordedAt,
        objectIds: event.objectIds || (event.objectId ? [event.objectId] : []),
        workstreamIds: [],
        correlationIds: [],
        source: 'RUNTIME_LEDGER',
      }));
    const eventKinds = events.reduce((counts, event) => ({ ...counts, [event.kind]: (counts[event.kind] || 0) + 1 }), {});
    const summary = { rulesVersion: 'journal-change-rules/1.1', changeCount: 0, advanced: 0, regressed: 0, changed: 0, opened: 0, closed: 0, workstreams: [], changes: [] };
    return {
      schemaVersion: 'case-journal/1.0',
      caseId,
      generatedAt: this.current.asOf,
      temporal: { since: query.since, until: query.until, asOf: query.asOf },
      eventCount: events.length,
      events,
      eventKinds,
      summary,
      drift: { status: 'UNAVAILABLE', reason: 'No closing state is available for an unformed case.' },
      integrity: { sources: ['RUNTIME_LEDGER'], runtimeLedgerIsPrimaryForAdmissionsAndSettlements: true, inferredSystemActorCount: 0, warnings: [] },
    };
  }

  async inspectObject(caseId, objectId) {
    if (caseId !== EMPTY_CASE_ID) return null;
    const source = this.current.sources.find(item => item.id === objectId);
    if (!source) return null;
    return {
      objectId,
      supportObjectIds: [],
      independentSupportObjectIds: [],
      unknownIds: [],
      dependentObjectIds: [],
      relatedObjectIds: [],
      sourceLocators: [{ sourceId: source.id, sourceVersionId: source.currentVersionId }],
      allowedActions: ['OPEN_SOURCE'],
    };
  }

  async searchCase(caseId, query) {
    if (caseId !== EMPTY_CASE_ID || !query.trim()) return [];
    const normalized = query.toLowerCase();
    return this.current.sources
      .filter(source => source.title.toLowerCase().includes(normalized))
      .map(source => ({ objectId: source.id, label: source.title, kind: 'source' }));
  }

  async runSimulation() {
    return null;
  }

  async execute(caseId, command) {
    if (caseId !== EMPTY_CASE_ID) return null;
    if (command.action.type !== 'ADD_MATERIAL') return clone(this.current);
    if (command.actorId !== owner.id) throw new Error('Only an authorized case actor can add material.');

    for (const [index, file] of command.action.files.entries()) {
      const sequence = this.current.sources.length + 1;
      const sourceId = `SRC-EMPTY-${sequence}`;
      const versionId = `SV-EMPTY-${sequence}`;
      const title = file.name || `Case material ${index + 1}`;
      this.current.sources.push({ id: sourceId, type: 'document', title, currentVersionId: versionId });
      this.current.sourceVersions.push({
        id: versionId,
        sourceId,
        contentHash: `empty-case-material-${sequence}`,
        knownAt: command.submittedAt,
        permissionScope: 'case',
      });
      this.current.events.push({
        id: `EV-EMPTY-SOURCE-${sequence}`,
        caseId: EMPTY_CASE_ID,
        eventType: 'SOURCE_REGISTERED',
        objectType: 'source',
        objectId: sourceId,
        effectiveAt: command.submittedAt,
        knownAt: command.submittedAt,
        recordedAt: command.submittedAt,
        actorOrPolicyId: command.actorId,
        schemaVersion: '0.1.0',
        idempotencyKey: `empty-source-${sequence}`,
      });
      this.current.events.push({
        id: `EV-EMPTY-VERSION-${sequence}`,
        caseId: EMPTY_CASE_ID,
        eventType: 'SOURCE_VERSION_RECORDED',
        objectType: 'sourceVersion',
        objectId: versionId,
        effectiveAt: command.submittedAt,
        knownAt: command.submittedAt,
        recordedAt: command.submittedAt,
        actorOrPolicyId: command.actorId,
        schemaVersion: '0.1.0',
        idempotencyKey: `empty-source-version-${sequence}`,
      });
    }
    this.current.caseVersion = `v${Number(this.current.caseVersion.slice(1)) + 1}`;
    this.current.asOf = command.submittedAt;
    return clone(this.current);
  }
}
