import type {
  CaseJournal,
  JournalChange,
  JournalChangeSummary,
  JournalDrift,
  JournalEvent,
  JournalStateRef,
  JournalTrend,
  JournalWorkstreamSummary,
} from '../types/domain';
import type { JournalQuery } from './PantaBackendAdapter';

type JsonRecord = Record<string, unknown>;

export interface JournalHttpOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  signal?: AbortSignal;
}

export class JournalHttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'JournalHttpError';
    this.status = status;
  }
}

function record(value: unknown, at: string): JsonRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Invalid Case Journal response: ${at} must be an object.`);
  }
  return value as JsonRecord;
}

function text(value: unknown, at: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`Invalid Case Journal response: ${at} must be a non-empty string.`);
  }
  return value;
}

function optionalText(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function count(value: unknown, at: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new Error(`Invalid Case Journal response: ${at} must be a non-negative integer.`);
  }
  return value;
}

function list(value: unknown, at: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`Invalid Case Journal response: ${at} must be an array.`);
  return value;
}

function textList(value: unknown, at: string): string[] {
  return list(value ?? [], at).map((item, index) => text(item, `${at}[${index}]`));
}

function stateReference(value: unknown, at: string): JournalStateRef | undefined {
  if (value == null) return undefined;
  const source = record(value, at);
  const state: JournalStateRef = {
    stateId: optionalText(source.state_id),
    versionId: optionalText(source.version_id),
    knownAt: optionalText(source.known_at),
    effectiveDate: optionalText(source.effective_date),
    graphHash: optionalText(source.graph_hash),
  };
  return Object.values(state).some(Boolean) ? state : undefined;
}

function trend(value: unknown, at: string): JournalTrend {
  const token = text(value, at);
  if (token !== 'ADVANCED' && token !== 'REGRESSED' && token !== 'CHANGED') {
    throw new Error(`Invalid Case Journal response: ${at} has an unsupported value.`);
  }
  return token;
}

function journalChange(value: unknown, index: number): JournalChange {
  const at = `summary.changes[${index}]`;
  const source = record(value, at);
  const changeType = text(source.change_type, `${at}.change_type`);
  if (changeType !== 'ADDED' && changeType !== 'REMOVED' && changeType !== 'UPDATED') {
    throw new Error(`Invalid Case Journal response: ${at}.change_type has an unsupported value.`);
  }
  const rawMovement = optionalText(source.movement);
  if (rawMovement && rawMovement !== 'OPENED' && rawMovement !== 'CLOSED') {
    throw new Error(`Invalid Case Journal response: ${at}.movement has an unsupported value.`);
  }
  return {
    id: text(source.change_id, `${at}.change_id`),
    objectId: text(source.object_id, `${at}.object_id`),
    objectType: text(source.object_type, `${at}.object_type`),
    collection: text(source.collection, `${at}.collection`),
    label: text(source.label, `${at}.label`),
    workstreamId: text(source.workstream_id, `${at}.workstream_id`),
    beforeWorkstreamId: optionalText(source.before_workstream_id),
    afterWorkstreamId: optionalText(source.after_workstream_id),
    changeType,
    trend: trend(source.trend, `${at}.trend`),
    movement: rawMovement as JournalChange['movement'],
    reason: text(source.reason, `${at}.reason`),
    beforeStatus: optionalText(source.before_status),
    afterStatus: optionalText(source.after_status),
    changedFields: textList(source.changed_fields ?? [], `${at}.changed_fields`),
  };
}

function workstreamSummary(value: unknown, index: number): JournalWorkstreamSummary {
  const at = `summary.workstreams[${index}]`;
  const source = record(value, at);
  const netDirection = text(source.net_direction, `${at}.net_direction`);
  if (!['ADVANCED', 'REGRESSED', 'CHANGED', 'MIXED_OR_NEUTRAL'].includes(netDirection)) {
    throw new Error(`Invalid Case Journal response: ${at}.net_direction has an unsupported value.`);
  }
  return {
    workstreamId: text(source.workstream_id, `${at}.workstream_id`),
    changeCount: count(source.change_count, `${at}.change_count`),
    advanced: count(source.advanced, `${at}.advanced`),
    regressed: count(source.regressed, `${at}.regressed`),
    changed: count(source.changed, `${at}.changed`),
    netDirection: netDirection as JournalWorkstreamSummary['netDirection'],
    changeIds: textList(source.change_ids ?? [], `${at}.change_ids`),
  };
}

function changeSummary(value: unknown, at = 'summary'): JournalChangeSummary {
  const source = record(value, at);
  if (source.rules_version !== 'journal-change-rules/1.1') {
    throw new Error('Unsupported Case Journal change rules. Expected journal-change-rules/1.1.');
  }
  const changes = list(source.changes, `${at}.changes`).map(journalChange);
  const workstreams = list(source.workstreams, `${at}.workstreams`).map(workstreamSummary);
  const changeCount = count(source.change_count, `${at}.change_count`);
  const advanced = count(source.advanced, `${at}.advanced`);
  const regressed = count(source.regressed, `${at}.regressed`);
  const changed = count(source.changed, `${at}.changed`);
  if (changeCount !== changes.length || advanced + regressed + changed !== changeCount) {
    throw new Error(`Invalid Case Journal response: ${at} counts do not match its changes.`);
  }
  return {
    rulesVersion: 'journal-change-rules/1.1',
    changeCount,
    advanced,
    regressed,
    changed,
    opened: count(source.opened, `${at}.opened`),
    closed: count(source.closed, `${at}.closed`),
    workstreams,
    changes,
  };
}

function journalEvent(value: unknown, index: number): JournalEvent {
  const at = `events[${index}]`;
  const source = record(value, at);
  if (source.schema_version !== 'case-journal-event/1.0') {
    throw new Error(`Unsupported Case Journal event schema at ${at}.`);
  }
  const actorSource = text(source.actor_source, `${at}.actor_source`);
  if (actorSource !== 'DECLARED' && actorSource !== 'INFERRED_SYSTEM') {
    throw new Error(`Invalid Case Journal response: ${at}.actor_source has an unsupported value.`);
  }
  const eventSource = text(source.source, `${at}.source`);
  if (!['RUNTIME_LEDGER', 'VAULT_EVENT', 'AUTHORITY_LEDGER'].includes(eventSource)) {
    throw new Error(`Invalid Case Journal response: ${at}.source has an unsupported value.`);
  }
  return {
    id: text(source.journal_id, `${at}.journal_id`),
    eventId: text(source.event_id, `${at}.event_id`),
    caseId: text(source.case_id, `${at}.case_id`),
    eventType: text(source.event_type, `${at}.event_type`),
    kind: text(source.kind, `${at}.kind`),
    phase: text(source.phase, `${at}.phase`),
    label: optionalText(source.label) ?? text(source.event_type, `${at}.event_type`),
    detail: optionalText(source.detail),
    actorId: text(source.actor_id, `${at}.actor_id`),
    actorLabel: optionalText(source.actor_label),
    actorSource,
    effectiveDate: text(source.effective_date, `${at}.effective_date`),
    knownAt: text(source.known_at, `${at}.known_at`),
    recordedAt: text(source.recorded_at, `${at}.recorded_at`),
    objectIds: textList(source.object_ids ?? [], `${at}.object_ids`),
    workstreamIds: textList(source.workstream_ids ?? [], `${at}.workstream_ids`),
    correlationIds: textList(source.correlation_ids ?? [], `${at}.correlation_ids`),
    source: eventSource as JournalEvent['source'],
  };
}

/** Validate and translate the canonical snake_case API response into the V4 UI projection. */
export function projectCaseJournal(value: unknown): CaseJournal {
  const source = record(value, 'journal');
  if (source.schema_version !== 'case-journal/1.0') {
    throw new Error('Unsupported Case Journal schema. Expected case-journal/1.0.');
  }
  const temporal = record(source.temporal, 'temporal');
  const eventKindsSource = record(source.event_kinds ?? {}, 'event_kinds');
  const eventKinds: Record<string, number> = {};
  for (const [key, value] of Object.entries(eventKindsSource)) eventKinds[key] = count(value, `event_kinds.${key}`);
  const driftSource = record(source.drift, 'drift');
  const driftStatus = text(driftSource.status, 'drift.status');
  let drift: JournalDrift;
  if (driftStatus === 'UNAVAILABLE') {
    drift = { status: 'UNAVAILABLE', reason: text(driftSource.reason, 'drift.reason') };
  } else if (driftStatus === 'AVAILABLE') {
    drift = {
      status: 'AVAILABLE',
      baselineStateId: optionalText(driftSource.baseline_state_id),
      currentStateId: optionalText(driftSource.current_state_id),
      ...changeSummary(driftSource, 'drift'),
    };
  } else {
    throw new Error('Invalid Case Journal response: drift.status has an unsupported value.');
  }
  const integrity = record(source.integrity, 'integrity');
  if (integrity.runtime_ledger_is_primary_for_admissions_and_settlements !== true) {
    throw new Error('Invalid Case Journal response: runtime ledger primacy is not asserted.');
  }
  const caseId = text(source.case_id, 'case_id');
  const events = list(source.events, 'events').map(journalEvent);
  const eventCount = count(source.event_count, 'event_count');
  if (eventCount !== events.length || events.some(event => event.caseId !== caseId)) {
    throw new Error('Invalid Case Journal response: event count or case identity is inconsistent.');
  }
  return {
    schemaVersion: 'case-journal/1.0',
    caseId,
    generatedAt: text(source.generated_at, 'generated_at'),
    temporal: {
      since: optionalText(temporal.since),
      until: optionalText(temporal.until),
      asOf: optionalText(temporal.as_of),
    },
    baseline: stateReference(source.baseline, 'baseline'),
    current: stateReference(source.current, 'current'),
    eventCount,
    events,
    eventKinds,
    summary: changeSummary(source.summary),
    drift,
    integrity: {
      sources: textList(integrity.sources, 'integrity.sources'),
      runtimeLedgerIsPrimaryForAdmissionsAndSettlements: true,
      inferredSystemActorCount: count(integrity.inferred_system_actor_count ?? 0, 'integrity.inferred_system_actor_count'),
      warnings: textList(integrity.warnings ?? [], 'integrity.warnings'),
    },
  };
}

/** Validate the graph-version index and expose only immutable CURRENT states. */
export function projectJournalStates(value: unknown): JournalStateRef[] {
  const source = record(value, 'graph versions');
  return list(source.versions, 'versions')
    .map((item, index) => record(item, `versions[${index}]`))
    .filter(item => item.kind === 'CURRENT')
    .map((item, index) => {
      const state = stateReference(item, `versions[${index}]`);
      if (!state?.stateId || !state.versionId) {
        throw new Error(`Invalid graph-version response: versions[${index}] has no state identity.`);
      }
      return state;
    });
}

export function journalRequestPath(caseId: string, query: JournalQuery = {}): string {
  const params = new URLSearchParams();
  const fields: Array<[keyof JournalQuery, string]> = [
    ['since', 'since'],
    ['until', 'until'],
    ['asOf', 'as_of_date'],
    ['workstream', 'workstream'],
    ['kind', 'kind'],
    ['baselineStateId', 'baseline_state_id'],
    ['currentStateId', 'current_state_id'],
    ['closeStateId', 'close_state_id'],
  ];
  for (const [field, parameter] of fields) {
    const value = query[field];
    if (value) params.set(parameter, value);
  }
  const suffix = params.toString();
  return `/api/v20/cases/${encodeURIComponent(caseId)}/journal${suffix ? `?${suffix}` : ''}`;
}

async function getJson(path: string, options: JournalHttpOptions): Promise<unknown> {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  if (!fetchImpl) throw new Error('No HTTP transport is available for the Case Journal.');
  const baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
  const response = await fetchImpl(`${baseUrl}${path}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal: options.signal,
  });
  if (!response.ok) {
    const body = (await response.text()).trim();
    let detail = body;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === 'string') detail = parsed.detail;
    } catch {
      // Non-JSON upstream errors remain visible in their bounded response form.
    }
    detail = detail.slice(0, 500);
    throw new JournalHttpError(response.status, detail || `Case Journal request failed (${response.status}).`);
  }
  return response.json();
}

/** Same-origin V20 transport helper for concrete PantaBackendAdapter implementations. */
export async function fetchCaseJournal(caseId: string, query: JournalQuery = {}, options: JournalHttpOptions = {}): Promise<CaseJournal> {
  return projectCaseJournal(await getJson(journalRequestPath(caseId, query), options));
}

/** Same-origin V20 transport helper for the Journal state selectors. */
export async function fetchJournalStates(caseId: string, options: JournalHttpOptions = {}): Promise<JournalStateRef[]> {
  const path = `/api/v20/cases/${encodeURIComponent(caseId)}/graph-versions`;
  return projectJournalStates(await getJson(path, options));
}
