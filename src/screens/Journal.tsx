import React, { useEffect, useMemo, useRef, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { formatCount, objectKind } from '../app/selectors';
import { EmptyCase } from '../components/EmptyCase';
import type { JournalQuery } from '../providers/PantaBackendAdapter';
import type {
  CaseJournal,
  JournalChange,
  JournalEvent,
  JournalStateRef,
  JournalTrend,
  PantaCaseSnapshot,
} from '../types/domain';

interface FilterValues {
  since: string;
  until: string;
  asOf: string;
  workstream: string;
  kind: string;
  baselineStateId: string;
  currentStateId: string;
  closeStateId: string;
}

const blankFilters = (asOf?: string): FilterValues => ({
  since: '',
  until: '',
  asOf: asOf?.slice(0, 10) ?? '',
  workstream: '',
  kind: '',
  baselineStateId: '',
  currentStateId: '',
  closeStateId: '',
});

export function Journal() {
  const { adapter, snapshot, asOf, setActiveObject } = usePanta();
  const caseId = snapshot?.caseRef.id;
  const [draft, setDraft] = useState<FilterValues>(() => blankFilters(asOf));
  const [query, setQuery] = useState<JournalQuery>(() => cleanQuery(blankFilters(asOf)));
  const [journal, setJournal] = useState<CaseJournal | null>();
  const [states, setStates] = useState<JournalStateRef[]>([]);
  const [stateIndexError, setStateIndexError] = useState<string>();
  const [loadError, setLoadError] = useState<{ message: string; integrityConflict: boolean }>();
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [knownKinds, setKnownKinds] = useState<string[]>([]);
  const loadRequest = useRef(0);

  useEffect(() => {
    const next = blankFilters(asOf);
    setDraft(next);
    setQuery(cleanQuery(next));
    setJournal(undefined);
    setStates([]);
    setStateIndexError(undefined);
    setKnownKinds([]);
  }, [caseId, asOf]);

  useEffect(() => {
    if (!caseId) return;
    let active = true;
    setStateIndexError(undefined);
    void adapter.listJournalStates(caseId)
      .then(items => { if (active) setStates(items); })
      .catch(error => {
        if (!active) return;
        setStates([]);
        setStateIndexError(errorMessage(error));
      });
    return () => { active = false; };
  }, [adapter, caseId, reload]);

  useEffect(() => {
    if (!caseId) return;
    const requestId = ++loadRequest.current;
    setLoading(true);
    setLoadError(undefined);
    void adapter.loadJournal(caseId, query)
      .then(result => {
        if (requestId !== loadRequest.current) return;
        setJournal(result);
        if (result) {
          setKnownKinds(current => [...new Set([...current, ...Object.keys(result.eventKinds)])].sort());
        }
      })
      .catch(error => {
        if (requestId !== loadRequest.current) return;
        const status = typeof error === 'object' && error && 'status' in error ? Number(error.status) : undefined;
        setJournal(undefined);
        setLoadError({ message: errorMessage(error), integrityConflict: status === 409 });
      })
      .finally(() => { if (requestId === loadRequest.current) setLoading(false); });
  }, [adapter, caseId, query, reload]);

  const stateLabels = useMemo(() => new Map(states.map((state, index) => [
    state.stateId ?? state.versionId ?? String(index),
    `${index === states.length - 1 ? 'Latest state' : `State ${index + 1}`} · ${formatStateTime(state)}`,
  ])), [states]);

  if (!snapshot || !caseId) return <EmptyCase />;

  const applyFilters = (event: React.FormEvent) => {
    event.preventDefault();
    setQuery(cleanQuery(draft));
  };
  const resetFilters = () => {
    const next = blankFilters(asOf);
    setDraft(next);
    setQuery(cleanQuery(next));
  };

  return <main className="p-page p-journal-page">
    <header className="p-journal-head">
      <div>
        <div className="p-kicker">Case changes</div>
        <h1>What changed, when did we know it, and who acted?</h1>
        <p>Compare two recorded case states and read the institutional timeline without changing the live case.</p>
      </div>
      {journal && <div className="p-journal-freshness"><span>History generated</span><strong>{formatTimestamp(journal.generatedAt)}</strong></div>}
    </header>

    <form className="p-journal-filters" onSubmit={applyFilters}>
      <div className="p-journal-filter-grid">
        <FilterField label="Known since"><input type="date" value={draft.since} max={draft.until || undefined} onChange={event => setDraftValue(setDraft, 'since', event.target.value)} /></FilterField>
        <FilterField label="Known through"><input type="date" value={draft.until} min={draft.since || undefined} onChange={event => setDraftValue(setDraft, 'until', event.target.value)} /></FilterField>
        <FilterField label="Case area"><select value={draft.workstream} onChange={event => setDraftValue(setDraft, 'workstream', event.target.value)}><option value="">All case areas</option>{snapshot.workstreams.map(workstream => <option key={workstream.id} value={workstream.id}>{workstream.name}</option>)}</select></FilterField>
        <FilterField label="Event kind"><select value={draft.kind} onChange={event => setDraftValue(setDraft, 'kind', event.target.value)}><option value="">All event kinds</option>{knownKinds.map(kind => <option key={kind} value={kind}>{humanToken(kind)}</option>)}</select></FilterField>
      </div>
      <details className="p-journal-comparison">
        <summary>Comparison and close-state options</summary>
        <div>
          <FilterField label="Known by"><input type="date" value={draft.asOf} onChange={event => setDraftValue(setDraft, 'asOf', event.target.value)} /></FilterField>
          <StateField label="Compare from" value={draft.baselineStateId} emptyLabel="Automatic prior state" states={states} labels={stateLabels} onChange={value => setDraftValue(setDraft, 'baselineStateId', value)} />
          <StateField label="Compare to" value={draft.currentStateId} emptyLabel="Latest eligible state" states={states} labels={stateLabels} onChange={value => setDraftValue(setDraft, 'currentStateId', value)} />
          <StateField label="Closing state" value={draft.closeStateId} emptyLabel="No close-state comparison" states={states} labels={stateLabels} onChange={value => setDraftValue(setDraft, 'closeStateId', value)} />
        </div>
        {stateIndexError && <p role="status">Recorded state choices are unavailable: {stateIndexError}</p>}
      </details>
      <div className="p-action-row">
        <button className="p-btn p-btn-primary" type="submit" disabled={loading}>Apply filters</button>
        <button className="p-btn" type="button" disabled={loading} onClick={() => setReload(value => value + 1)}>Refresh</button>
        <button className="p-btn p-btn-quiet" type="button" disabled={loading} onClick={resetFilters}>Reset</button>
      </div>
    </form>

    {loading && <JournalLoading />}
    {!loading && loadError && <JournalError error={loadError} onRetry={() => setReload(value => value + 1)} />}
    {!loading && journal === null && <section className="p-journal-unavailable"><strong>Case changes are not connected.</strong><p>The active backend adapter does not provide the Case Journal projection for this case.</p></section>}
    {!loading && journal && <JournalContent journal={journal} snapshot={snapshot} onInspect={setActiveObject} />}
  </main>;
}

function JournalContent({ journal, snapshot, onInspect }: { journal: CaseJournal; snapshot: PantaCaseSnapshot; onInspect: (id?: string) => Promise<void> }) {
  const summary = journal.summary;
  return <div className="p-journal-content p-fade-in">
    <section className="p-journal-window" aria-label="Compared case states">
      <div><span>Compared from</span><strong>{journal.baseline ? formatStateTime(journal.baseline) : 'No prior recorded state'}</strong></div>
      <span aria-hidden="true">→</span>
      <div><span>Compared to</span><strong>{journal.current ? formatStateTime(journal.current) : 'No recorded state available'}</strong></div>
    </section>

    <section className="p-journal-summary" aria-labelledby="journal-summary-title">
      <header><div><div className="p-kicker">State difference</div><h2 id="journal-summary-title">How the case moved</h2></div><span>{formatCount(summary.changeCount, 'case change')}</span></header>
      <div className="p-journal-metrics">
        <Metric label="Advanced" value={summary.advanced} tone="advanced" />
        <Metric label="Regressed" value={summary.regressed} tone="regressed" />
        <Metric label="Changed" value={summary.changed} tone="changed" />
        <Metric label="Opened" value={summary.opened} tone="opened" />
        <Metric label="Closed" value={summary.closed} tone="closed" />
      </div>
      {summary.workstreams.length > 0 && <div className="p-journal-workstreams">{summary.workstreams.map(item => <article key={item.workstreamId}>
        <div><span>Case area</span><strong>{workstreamLabel(snapshot, item.workstreamId)}</strong></div>
        <b className={toneClass(item.netDirection)}>{directionLabel(item.netDirection)}</b>
        <small>{formatCount(item.changeCount, 'change')} · {item.advanced} advanced · {item.regressed} regressed</small>
      </article>)}</div>}
      {summary.changes.length > 0 ? <div className="p-journal-changes">{summary.changes.map(change => <ChangeRow key={change.id} change={change} snapshot={snapshot} onInspect={onInspect} />)}</div> : <p className="p-journal-none">No semantic difference exists between the selected case states.</p>}
    </section>

    <DriftPanel drift={journal.drift} />

    <section className="p-journal-timeline" aria-labelledby="journal-timeline-title">
      <header><div><div className="p-kicker">Institutional timeline</div><h2 id="journal-timeline-title">What was recorded</h2></div><span>{formatCount(journal.eventCount, 'event')}</span></header>
      {journal.events.length > 0 ? <ol>{journal.events.map(event => <EventRow key={event.id} event={event} snapshot={snapshot} onInspect={onInspect} />)}</ol> : <p className="p-journal-none">No events match the selected time and case-area filters.</p>}
    </section>

    {journal.integrity.warnings.length > 0 && <section className="p-journal-warnings"><strong>History notes</strong>{journal.integrity.warnings.map(warning => <p key={warning}>{warning}</p>)}</section>}
  </div>;
}

function ChangeRow({ change, snapshot, onInspect }: { change: JournalChange; snapshot: PantaCaseSnapshot; onInspect: (id?: string) => Promise<void> }) {
  const inspectable = Boolean(objectKind(snapshot, change.objectId)) && change.changeType !== 'REMOVED';
  return <article className="p-journal-change">
    <div className="p-journal-change-main">
      <span>{workstreamLabel(snapshot, change.workstreamId)} · {humanToken(change.objectType)}</span>
      <strong>{change.label}</strong>
      <p>{change.reason}</p>
      {change.changedFields.length > 0 && <small>Changed: {change.changedFields.map(humanToken).join(', ')}</small>}
    </div>
    <div className="p-journal-change-state">
      <b className={toneClass(change.trend)}>{directionLabel(change.trend)}{change.movement ? ` · ${humanToken(change.movement)}` : ''}</b>
      <div><span>{change.beforeStatus ? humanToken(change.beforeStatus) : change.changeType === 'ADDED' ? 'Not present' : '—'}</span><i aria-hidden="true">→</i><strong>{change.afterStatus ? humanToken(change.afterStatus) : change.changeType === 'REMOVED' ? 'Removed' : 'Updated'}</strong></div>
      {inspectable && <button onClick={() => void onInspect(change.objectId)}>Inspect current object →</button>}
    </div>
  </article>;
}

function EventRow({ event, snapshot, onInspect }: { event: JournalEvent; snapshot: PantaCaseSnapshot; onInspect: (id?: string) => Promise<void> }) {
  const objectId = event.objectIds.find(id => Boolean(objectKind(snapshot, id)));
  const actor = snapshot.actors.find(item => item.id === event.actorId);
  const actorLabel = actor?.displayName ?? (event.actorSource === 'INFERRED_SYSTEM' ? 'PANTA system' : event.actorLabel ?? 'Recorded actor');
  return <li>
    <div className="p-journal-time"><strong>{formatDate(event.effectiveDate)}</strong><span>Effective</span></div>
    <article>
      <header><div><span>{humanToken(event.phase)} · {humanToken(event.kind)}</span><h3>{event.label}</h3></div><small>{sourceLabel(event.source)}</small></header>
      {event.detail && <p>{event.detail}</p>}
      <dl>
        <div><dt>Known</dt><dd>{formatTimestamp(event.knownAt)}</dd></div>
        <div><dt>Recorded</dt><dd>{formatTimestamp(event.recordedAt)}</dd></div>
        <div><dt>Actor</dt><dd>{actorLabel}{event.actorSource === 'INFERRED_SYSTEM' ? ' · inferred legacy attribution' : ''}</dd></div>
      </dl>
      {objectId && <button onClick={() => void onInspect(objectId)}>Inspect linked object →</button>}
    </article>
  </li>;
}

function DriftPanel({ drift }: { drift: CaseJournal['drift'] }) {
  if (drift.status === 'UNAVAILABLE') return <section className="p-journal-drift is-unavailable"><div><div className="p-kicker">After close</div><h2>No closing state selected</h2></div><p>Select an explicit closing state to measure later movement. Current change is never presented as post-close drift by assumption.</p></section>;
  return <section className="p-journal-drift"><div><div className="p-kicker">After close</div><h2>Movement since the selected closing state</h2></div><div className="p-journal-drift-counts"><span><strong>{drift.changeCount}</strong> changes</span><span><strong>{drift.advanced}</strong> advanced</span><span><strong>{drift.regressed}</strong> regressed</span></div></section>;
}

function JournalLoading() {
  return <section className="p-journal-loading" role="status" aria-live="polite"><span className="p-progress-mark" aria-hidden="true" /><div><strong>Loading recorded case changes</strong><p>Checking the timeline and selected state comparison.</p></div></section>;
}

function JournalError({ error, onRetry }: { error: { message: string; integrityConflict: boolean }; onRetry: () => void }) {
  return <section className="p-journal-error" role="alert"><div><strong>{error.integrityConflict ? 'The history integrity check failed' : 'Case changes could not be loaded'}</strong><p>{error.integrityConflict ? 'No partial or unverified history is shown.' : 'The current case remains unchanged.'}</p><small>{error.message}</small></div><button className="p-btn" onClick={onRetry}>Try again</button></section>;
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="p-journal-field"><span>{label}</span>{children}</label>;
}

function StateField({ label, value, emptyLabel, states, labels, onChange }: { label: string; value: string; emptyLabel: string; states: JournalStateRef[]; labels: Map<string, string>; onChange: (value: string) => void }) {
  return <FilterField label={label}><select value={value} onChange={event => onChange(event.target.value)}><option value="">{emptyLabel}</option>{states.map((state, index) => {
    const id = state.stateId ?? state.versionId ?? String(index);
    return <option key={id} value={id}>{labels.get(id)}</option>;
  })}</select></FilterField>;
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className={`is-${tone}`}><strong>{value}</strong><span>{label}</span></div>;
}

function cleanQuery(values: FilterValues): JournalQuery {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => Boolean(value))) as JournalQuery;
}

function setDraftValue(setDraft: React.Dispatch<React.SetStateAction<FilterValues>>, key: keyof FilterValues, value: string) {
  setDraft(current => ({ ...current, [key]: value }));
}

function workstreamLabel(snapshot: PantaCaseSnapshot, id: string): string {
  if (!id || id === 'UNASSIGNED') return 'Cross-case';
  const direct = snapshot.workstreams.find(workstream => workstream.id === id);
  if (direct) return direct.name;
  const question = snapshot.questions.find(item => item.id === id);
  const parent = question && snapshot.workstreams.find(workstream => workstream.id === question.workstreamId);
  return parent?.name ?? 'Other case area';
}

function toneClass(value: JournalTrend | 'MIXED_OR_NEUTRAL'): string {
  return `is-${value.toLowerCase().replaceAll('_', '-')}`;
}

function directionLabel(value: JournalTrend | 'MIXED_OR_NEUTRAL'): string {
  return value === 'MIXED_OR_NEUTRAL' ? 'Mixed or neutral' : humanToken(value);
}

function humanToken(value: string): string {
  return value.toLowerCase().replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
}

function sourceLabel(value: JournalEvent['source']): string {
  if (value === 'RUNTIME_LEDGER') return 'Case ledger';
  if (value === 'AUTHORITY_LEDGER') return 'Authority record';
  return 'Institutional record';
}

function formatDate(value: string): string {
  try { return new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)); } catch { return value; }
}

function formatTimestamp(value: string): string {
  try { return new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' }).format(new Date(value)); } catch { return value; }
}

function formatStateTime(state: JournalStateRef): string {
  if (state.knownAt) return formatTimestamp(state.knownAt);
  if (state.effectiveDate) return formatDate(state.effectiveDate);
  return 'Recorded state';
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown Case Journal error.';
}
