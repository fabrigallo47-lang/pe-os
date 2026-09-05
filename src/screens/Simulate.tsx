import React, { useEffect, useMemo, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { EmptyCase } from '../components/EmptyCase';
import { ImpactTrace } from '../components/CausalTrace';
import { caseReadingById, formatCount, normalizeSimulationEffects, questionById, simulationImpactCounts, workstreamById } from '../app/selectors';
import type { PantaCaseSnapshot, SimulationLimit, SimulationRequest } from '../types/domain';
import '../design/simulation.css';
import { GraphSimulation } from './GraphSimulation';

export function Simulate() {
  const { snapshot, clearSimulation, simulationRunning } = usePanta();
  const [workspace, setWorkspace] = useState<'graph' | 'financial'>('graph');
  if (!snapshot) return <EmptyCase />;
  return <><nav className="p-sim-modes p-sim-workspaces" aria-label="Simulation workspace">{([['graph', 'Case changes'], ['financial', 'Financial sensitivities']] as const).map(([id, label]) => <button key={id} aria-pressed={workspace === id} disabled={simulationRunning} onClick={() => { clearSimulation(); setWorkspace(id); }}>{label}</button>)}</nav>{workspace === 'graph' ? <GraphSimulation snapshot={snapshot} /> : <CaseSimulation snapshot={snapshot} />}</>;
}

function CaseSimulation({ snapshot }: { snapshot: PantaCaseSnapshot }) {
  const { adapter, cases, setCase, focusedQuestionId, focusedWorkstreamId, simulationResult, runSimulation, clearSimulation, setActiveObject, simulationRunning, refresh, loading } = usePanta();
  const scope = snapshot.simulationScope;
  const workstream = workstreamById(snapshot, focusedWorkstreamId) ?? snapshot.workstreams[0];
  const question = questionById(snapshot, focusedQuestionId) ?? snapshot.questions.find(q => q.workstreamId === workstream?.id);
  const reading = question ? caseReadingById(snapshot, question.currentCaseReadingId) : undefined;
  // Model inputs are case-wide. A question route must not hide a mapped input.
  const options = useMemo(() => snapshot.simulationOptions.filter(o => scope || !question || o.originObjectId === question.id || o.originObjectId === reading?.id), [snapshot.simulationOptions, scope, question, reading]);
  const [mode, setMode] = useState<NonNullable<SimulationRequest['mode']>>('manual');
  const [scenarioId, setScenarioId] = useState('');
  const scenario = snapshot.simulationScenarios?.find(s => s.id === scenarioId) ?? snapshot.simulationScenarios?.[0];
  const [outputId, setOutputId] = useState('');
  const [target, setTarget] = useState('');
  const [lower, setLower] = useState('');
  const [upper, setUpper] = useState('');
  const [percent, setPercent] = useState('-10');
  const [peerId, setPeerId] = useState('');
  const peerCaseId = cases.find(c => c.id === peerId && c.id !== snapshot.caseRef.id)?.id ?? cases.find(c => c.id !== snapshot.caseRef.id)?.id;
  const [peer, setPeer] = useState<PantaCaseSnapshot | null>(null);
  const [peerError, setPeerError] = useState('');
  useEffect(() => {
    let active = true;
    setPeer(null); setPeerError('');
    if (mode === 'compare' && peerCaseId) void adapter.loadCase(peerCaseId).then(value => { if (active) setPeer(value); }).catch(error => { if (active) setPeerError(error.message); });
    return () => { active = false; };
  }, [adapter, mode, peerCaseId, snapshot]);
  useEffect(() => { clearSimulation(); }, [mode, scenario?.id, outputId, target, lower, upper, percent, peerCaseId, clearSimulation]);
  const [optionId, setOptionId] = useState<string>();
  const option = options.find(o => o.id === (mode === 'event' ? scenario?.request.optionId : optionId)) ?? options.find(o => o.enabled) ?? options[0];
  const [value, setValue] = useState('');
  const [selectedImpactId, setSelectedImpactId] = useState<string>();
  useEffect(() => {
    setValue(option?.input?.value ?? '');
    setSelectedImpactId(undefined);
    clearSimulation();
  }, [snapshot.caseRef.id, snapshot.caseVersion, scope?.version, option?.id, option?.input?.value, clearSimulation]);
  useEffect(() => () => clearSimulation(), [clearSimulation]);
  const outputOptions = snapshot.modelNodes.filter(n => option?.scope?.coveredObjectIds.includes(n.id));
  const selectedOutput = outputOptions.find(n => n.id === outputId) ?? outputOptions[0];
  const result = (simulationResult?.request.mode ?? 'manual') === mode && simulationResult?.request.optionId === option?.id && (!scope || simulationResult.scopeVersion === scope.version) ? simulationResult : null;
  const effects = useMemo(() => normalizeSimulationEffects(result?.effects ?? []), [result]);
  const impactCounts = useMemo(() => simulationImpactCounts(effects), [effects]);
  const numericValid = !option?.input || (value.trim() !== '' && Number.isFinite(Number(value)) && Math.abs(Number(value)) <= 1e30 && (Number(value) === 0 || Math.abs(Number(value)) >= 1e-100));
  const finite = (v: string) => v.trim() !== '' && Number.isFinite(Number(v));
  const valid = mode === 'manual' ? numericValid : mode === 'event' ? !!scenario : mode === 'inverse' ? !!selectedOutput && [target, lower, upper].every(finite) && Number(lower) < Number(upper) : !!peer?.simulationScope && finite(percent);
  const canRun = option?.enabled && valid && !simulationRunning && !loading;
  async function run() {
    if (!option || !canRun) return;
    const body: SimulationRequest = { optionId: option.id, originObjectId: option.originObjectId, assumption: option.assumption,
      ...(scope ? { caseVersion: snapshot.caseVersion, scopeVersion: scope.version } : {}) };
    if (mode === 'manual' && option.input) body.value = value;
    if (mode === 'event') Object.assign(body, { mode, scenarioId: scenario?.id });
    if (mode === 'inverse') Object.assign(body, { mode, inverse: { outputId: selectedOutput?.id, target, lower, upper } });
    if (mode === 'compare') Object.assign(body, { mode, percent, peerCaseId, peerCaseVersion: peer?.caseVersion, peerScopeVersion: peer?.simulationScope?.version });
    const next = await runSimulation(body);
    setSelectedImpactId(next?.effects.find(e => e.state !== 'HOLDS')?.objectId);
  }
  const inspect = (id: string) => { setSelectedImpactId(id); void setActiveObject(id); };

  return <main className="p-page p-sim-page">
    <section className="p-sim-setup">
      <div><div className="p-kicker">Simulation</div><h1>{scope ? 'What changes if this assumption moves?' : option?.label ?? 'Choose a test outcome'}</h1>
        {reading && <p>Current: {reading.text}</p>}
        {scope && <p>Test the model from the current case. Inspect the calculations and their limits before you run.</p>}
      </div>
      <span className="p-sandbox-note">Live case unchanged</span>
    </section>

    {scope && <section className="p-sim-perimeter" aria-label="Declared simulation scope">
      <div className="p-section-heading"><strong>What this model can test</strong><span>{scope.computableCount} of {scope.modelNodeCount} model items calculable</span></div>
      <p>Results cover declared calculations only. Investment judgments and decisions require their own review.</p>
      {!options.length && <p>No admitted model inputs are available. Add a model and resolve its input identities to enable simulation.</p>}
      {!!scope.limits.length && <details><summary>{formatCount(scope.limits.length, 'model limitation')} to review</summary><Limits items={scope.limits} inspect={inspect} /></details>}
      {!!scope.notes?.length && <details><summary>Other declared model limits</summary>{scope.notes.map(note => <p key={note}>{note}</p>)}</details>}
      <button className="p-related-link" disabled={loading || simulationRunning} onClick={() => void refresh()}>Refresh current case and model</button>
    </section>}

    {scope && <nav className="p-sim-modes" aria-label="Simulation mode">
      {([['manual', 'Change an assumption'], ['event', 'From an event'], ['inverse', 'Find a threshold'], ['compare', 'Compare deals']] as const).map(([id, label]) => <button key={id} type="button" aria-pressed={mode === id} disabled={simulationRunning} onClick={() => setMode(id)}>{label}</button>)}
    </nav>}

    {mode === 'event' && <section className="p-sim-event-setup">
      <h2>Scenarios prepared from admitted events</h2>
      <p>Mapped evidence changes are applied together to the current model. Scenarios are prepared automatically when the case is loaded or refreshed.</p>
      {snapshot.simulationScenarios?.length ? <label className="p-sim-field">Event<select aria-label="Event scenario" value={scenario?.id ?? ''} disabled={simulationRunning} onChange={e => setScenarioId(e.target.value)}>{snapshot.simulationScenarios.map(s => <option key={s.id} value={s.id}>{s.event?.label}</option>)}</select></label> : <p>No admitted event has an executable scenario in this model.</p>}
      {scenario?.event && <EventBasis event={scenario.event} snapshot={snapshot} inspect={inspect} />}
      {snapshot.simulationEventLimits?.map(e => <p key={e.eventId} role="status">{e.label}: {e.reason}</p>)}
    </section>}
    <section className="p-sim-inputs" aria-label="Simulation setup">
      {mode !== 'event' && (scope && options.length > 0 ? <label className="p-sim-field"><span>Model input</span><select aria-label="Model input" value={option?.id ?? ''} disabled={simulationRunning} onChange={event => setOptionId(event.target.value)}>
        {options.map(o => <option key={o.id} value={o.id}>{o.label}{o.enabled ? '' : ' · unavailable'}</option>)}
      </select></label> : <div className="p-outcome-choices">{options.map(o => <button key={o.id} aria-pressed={o.id === option?.id} disabled={!o.enabled || simulationRunning} onClick={() => setOptionId(o.id)}>{o.label.replace(/^What if /, '').replace(/\?$/, '')}</button>)}</div>)}
      {mode !== 'event' && option?.input && <>
        <div className="p-sim-input-context"><button className="p-unboxed-select" onClick={() => inspect(option.originObjectId)}>Current: {option.input.value ?? 'Unavailable'} {option.input.unit}</button><span>{[option.input.period, option.input.scope].filter(Boolean).join(' · ')}</span></div>
        {mode === 'manual' && <label className="p-sim-field"><span>Hypothetical value {option.input.unit ? `(${option.input.unit})` : ''}</span><input type="number" step="any" aria-label="Hypothetical value" value={value} disabled={!option.enabled || simulationRunning} onChange={event => { setValue(event.target.value); clearSimulation(); }} /></label>}
        {mode === 'manual' && !numericValid && <p role="alert">Enter a finite number within the supported range.</p>}
        {option.scope && <p className="p-sim-reach">{formatCount(option.scope.coveredObjectIds.length, 'downstream calculation')} available · {formatCount(option.scope.limitedObjectIds.length, 'downstream limitation')}</p>}
      </>}
      {mode === 'inverse' && <>
        <label className="p-sim-field">Target output<select aria-label="Target output" value={selectedOutput?.id ?? ''} disabled={simulationRunning} onChange={e => setOutputId(e.target.value)}>{outputOptions.map(n => <option key={n.id} value={n.id}>{n.label} ({n.unit})</option>)}</select></label>
        <NumericField label="Target value" value={target} change={setTarget} disabled={simulationRunning} />
        <NumericField label="Lower input bound" value={lower} change={setLower} disabled={simulationRunning} />
        <NumericField label="Upper input bound" value={upper} change={setUpper} disabled={simulationRunning} />
        <p className="p-sim-reach">Find the input value that reaches this output. The search checks a continuous, strictly increasing or decreasing relationship within your bounds; other inputs stay at their current values.</p>
      </>}
      {mode === 'compare' && <>
        <label className="p-sim-field">Comparison case<select aria-label="Comparison case" value={peerCaseId ?? ''} disabled={simulationRunning || cases.length < 2} onChange={e => setPeerId(e.target.value)}>{cases.filter(c => c.id !== snapshot.caseRef.id).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <NumericField label="Change in both inputs (%)" value={percent} change={setPercent} disabled={simulationRunning} />
        <p className="p-sim-reach">Apply the same percentage shock to matching inputs. Compare only items with the same declared definition, unit, currency, period, scope, basis and scenario.</p>
        {!peerCaseId && <p>No other case is available for comparison.</p>}
        {peerCaseId && !peer && !peerError && <p role="status">Loading the comparison case…</p>}
        {peerError && <p role="alert">{peerError}</p>}
      </>}
      {option?.disabledReason && <p className="p-sim-unavailable" role="status">{option.disabledReason}</p>}
      {!options.length && !scope && <p>No simulation is available for this part of the case.</p>}
      <div className="p-action-row"><button className="p-btn p-btn-primary" disabled={!canRun} onClick={() => void run()}>{simulationRunning ? 'Calculating…' : mode === 'event' ? 'Inspect event scenario' : mode === 'inverse' ? 'Find threshold' : mode === 'compare' ? 'Compare sensitivity' : 'Run impact trace'}</button>
        {result && <button className="p-btn" onClick={() => { clearSimulation(); setValue(option?.input?.value ?? ''); }}>Reset</button>}
      </div>
    </section>

    {!scope && !result && <section className="p-sim-baseline"><div className="p-section-heading"><strong>Current case baseline</strong><span>before the hypothetical</span></div>{snapshot.workstreams.map(w => <div key={w.id} className={`p-baseline-row ${w.id === workstream?.id ? 'is-origin' : ''}`}><strong>{w.name}</strong><span>{caseReadingById(snapshot, w.currentCaseReadingId)?.text ?? 'No current reading'}</span></div>)}</section>}

    {result && <div aria-live="polite">
      {result.inverse && <section className="p-sim-answer" aria-label="Threshold result">
        <h2>{result.inverse.status === 'FOUND' ? 'Threshold found' : result.inverse.status === 'UNREACHABLE' ? 'Target outside these bounds' : 'No verified threshold'}</h2>
        {result.inverse.status === 'FOUND' ? <><p><button className="p-unboxed-select" onClick={() => inspect(option!.id)}>{option?.label}</button> reaches <strong>{displayNumber(result.inverse.inputValue!)} {option?.input?.unit}</strong> when <button className="p-unboxed-select" onClick={() => inspect(result.inverse!.outputId)}>{selectedOutput?.label}</button> reaches {displayNumber(result.inverse.actual!)} {selectedOutput?.unit}.</p><details><summary>Search accuracy and bounds</summary><p>Input bounds: {result.inverse.lower} to {result.inverse.upper}. Target: {result.inverse.target}. Residual: {result.inverse.residual}. Output tolerance: {result.inverse.tolerance}. {result.inverse.iterations} iterations. Verified direction: {result.inverse.direction?.toLowerCase()}.</p></details></> : <p role="status">{result.inverse.reason}</p>}
      </section>}
      {result.comparison && <section className="p-sim-comparison" aria-label="Deal comparison">
        <h2>Same {result.comparison.percent}% input change · two cases</h2>
        <p>{snapshot.caseRef.name} compared with <button className="p-unboxed-select" onClick={() => void setCase(result.comparison!.peerCaseId)}>{result.comparison.peerName}</button>. Values below use each case’s own current baseline.</p>
        <div className="p-sim-numbers"><table><caption>Comparable model sensitivity</caption><thead><tr><th>Model item</th><th>This case: current → scenario</th><th>Other case: current → scenario</th><th>Relative change: this / other</th></tr></thead><tbody>{result.comparison.rows.map(row => <tr key={row.objectId}><td><button className="p-unboxed-select" onClick={() => inspect(row.objectId)}>{row.label}</button><small>{row.current.unit}</small><details><summary>Comparison basis</summary>{Object.entries(row.identity).map(([key, val]) => <p key={key}>{key.replace('comparison_key', 'Shared definition')}: {val}</p>)}<p>Other case reference: {row.peerObjectId}</p></details></td><td>{displayNumber(row.current.before)} → {displayNumber(row.current.after)}</td><td>{displayNumber(row.peer.before)} → {displayNumber(row.peer.after)}</td><td>{row.current.percent === null ? 'Unavailable' : displayNumber(row.current.percent) + '%'} / {row.peer.percent === null ? 'Unavailable' : displayNumber(row.peer.percent) + '%'}</td></tr>)}</tbody></table></div>
        {!!result.comparison.exclusions.length && <details><summary>Items excluded from comparison ({result.comparison.exclusions.length})</summary>{result.comparison.exclusions.map(e => <p key={e.caseId + e.objectId}>{e.caseId === snapshot.caseRef.id ? snapshot.caseRef.name : result.comparison!.peerName} · {e.label}: {e.reason}</p>)}</details>}
      </section>}
      {!!effects.length && <section className="p-sim-trust"><div><strong>{scope ? 'Model' : 'Case'}: {impactCounts.changed} changed · {impactCounts.held} held</strong><span>{result.coverage.examinedCount} items examined · {result.coverage.unmappedCount} could not be calculated</span></div><small>Current mapped case only</small></section>}
      {effects.some(e => e.magnitude) && <div className="p-sim-numbers"><table><caption>Magnitude of the change</caption><thead><tr><th>Model item</th><th>Current</th><th>Hypothetical</th><th>Change</th><th>Relative change</th></tr></thead><tbody>
        {effects.filter(e => e.magnitude).map(e => <tr key={e.objectId}><td><button className="p-unboxed-select" onClick={() => inspect(e.objectId)}>{e.objectLabel}</button><small>{e.magnitude!.unit}</small></td><td title={e.magnitude!.before}>{displayNumber(e.magnitude!.before)}</td><td title={e.magnitude!.after}>{displayNumber(e.magnitude!.after)}</td><td title={e.magnitude!.delta}>{displayNumber(e.magnitude!.delta)}</td><td title={e.magnitude!.percent ?? 'The baseline is zero.'}>{e.magnitude!.percent === null ? 'Unavailable from zero' : displayNumber(e.magnitude!.percent) + '%'}</td></tr>)}
      </tbody></table></div>}
      {!!result.limits?.length && <section className="p-sim-stops"><h2>Where this test stops</h2><Limits items={result.limits} inspect={inspect} /></section>}
      {!!effects.length && <ImpactTrace title="How the effect travels" originLabel={result.event?.label ?? option?.label ?? 'Simulation hypothesis'} originDetail={result.request.assumption}
        effects={effects} currentLabel="Current" changedLabel="Simulated" selectedObjectId={selectedImpactId} onSelect={inspect} />}
      <p className="p-impact-human">The live case and the investment decision remain unchanged.</p>
    </div>}
  </main>;
}

function Limits({ items, inspect }: { items: SimulationLimit[]; inspect: (id: string) => void }) {
  return <ul className="p-sim-limits">{items.map(item => <li key={item.objectId}><button className="p-unboxed-select" onClick={() => inspect(item.objectId)}>{item.label}</button><span>{item.reason}</span></li>)}</ul>;
}
function displayNumber(value: string) { return Number(value).toLocaleString('en-GB', { maximumSignificantDigits: 8 }); }

function NumericField({ label, value, change, disabled }: { label: string; value: string; change: (value: string) => void; disabled: boolean }) {
  return <label className="p-sim-field">{label}<input aria-label={label} type="number" step="any" value={value} disabled={disabled} onChange={e => change(e.target.value)} /></label>;
}
function EventBasis({ event, snapshot, inspect }: { snapshot: PantaCaseSnapshot; event: NonNullable<import('../types/domain').SimulationResult['event']>; inspect: (id: string) => void }) {
  return <div className="p-sim-event-basis"><p>Known: {event.knownAt} · Effective: {event.effectiveAt ?? 'Not recorded'}</p><ul>{event.changes.map(c => <li key={c.ruleId}><button className="p-unboxed-select" onClick={() => inspect(c.inputId)}>{snapshot.modelNodes.find(n => n.id === c.inputId)?.label ?? c.inputId}</button> → {c.value}, from <button className="p-unboxed-select" onClick={() => inspect(c.claimId)}>{snapshot.claims.find(n => n.id === c.claimId)?.label ?? c.claimId}</button></li>)}</ul><details><summary>Event provenance</summary><p>Event: {event.eventId}</p><p>Recorded: {event.recordedAt ?? 'Not recorded'}</p><p>Sources: {event.sourceIds.join(', ')}</p><p className="p-sim-hash">Evidence hash: {event.eventHash}</p><p>Scenario calculated against the current case. Archived scenarios retain their original model and evidence basis.</p></details></div>;
}
