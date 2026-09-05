import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import { SimulationTextInput } from '../components/SimulationTextInput';
import type { GraphMutation, GraphSimulationObject, GraphSimulationReport, PantaCaseSnapshot } from '../types/domain';

const show = (value: unknown): string => value === null || value === undefined ? 'Not recorded' : typeof value === 'string' ? value : JSON.stringify(value);
const support = (value?: string) => value === 'TRUE' ? 'Supported' : value === 'FALSE' ? 'Unsupported' : value === 'UNKNOWN' ? 'Unresolved' : 'Not evaluated';
const fieldName = (name: string) => ({ runtime_state: 'Availability', support_result: 'Support', usable: 'Usable as support', member_claim_ids: 'Supporting evidence', counter_claim_ids: 'Contrary evidence', member_position_ids: 'Supporting conclusions', member_model_node_ids: 'Supporting model items', freshness_status: 'Freshness' }[name] ?? name.replaceAll('_', ' '));

export function GraphSimulation({ snapshot }: { snapshot: PantaCaseSnapshot }) {
  const { simulationResult, simulationRunning, runSimulation, clearSimulation, refresh, loading } = usePanta();
  const scope = snapshot.graphSimulationScope;
  const [mode, setMode] = useState<'describe' | 'edit' | 'add' | 'event'>('describe');
  const [objectId, setObjectId] = useState('');
  const [action, setAction] = useState('RETRACT');
  const [value, setValue] = useState<unknown>('');
  const [draft, setDraft] = useState<GraphMutation[]>([]);
  const [description, setDescription] = useState('');
  const [textReset, setTextReset] = useState(0);
  const [statement, setStatement] = useState('');
  const [targetId, setTargetId] = useState('');
  const [relation, setRelation] = useState<'SUPPORTS' | 'CONTRADICTS'>('CONTRADICTS');
  const [scenarioId, setScenarioId] = useState('');
  const [selected, setSelected] = useState('');
  const [version, setVersion] = useState<'CURRENT' | 'HYPOTHETICAL'>('HYPOTHETICAL');
  const obj = scope?.objects.find(o => o.id === objectId) ?? scope?.objects.find(o => o.canRetract || o.fields.length);
  const field = obj?.fields.find(f => f.id === action);
  const targets = scope?.objects.filter(o => o.kind === 'POSITION' && o.fields.length) ?? [];
  const target = targets.find(o => o.id === targetId) ?? targets[0];
  const scenario = snapshot.graphSimulationScenarios?.find(s => s.id === scenarioId) ?? snapshot.graphSimulationScenarios?.[0];
  const report = simulationResult?.graph?.version === scope?.version ? simulationResult?.graph : undefined;
  const busy = simulationRunning || loading;
  useEffect(() => { clearSimulation(); setDraft([]); setSelected(''); }, [snapshot.caseRef.id, scope?.version, clearSimulation]);
  useEffect(() => {
    setAction(obj?.canRetract ? 'RETRACT' : obj?.fields[0]?.id ?? '');
  }, [obj?.id]);
  useEffect(() => { setValue(field?.value ?? (field?.control === 'references' ? [] : field?.control === 'boolean' ? true : field?.choices?.[0] ?? '')); }, [obj?.id, field?.id, field?.value]);
  useEffect(() => () => clearSimulation(), [clearSimulation]);
  function changeMode(next: typeof mode) { setMode(next); clearSimulation(); }
  function addChange() {
    let change: GraphMutation;
    if (mode === 'add' && target && statement.trim()) {
      change = { operation: 'ADD', object_type: 'CLAIM', object_id: 'HYPOTHETICAL:' + crypto.randomUUID(), statement: statement.trim(), relation_type: relation, target_position_id: target.id };
      setStatement('');
    } else if (obj && (action === 'RETRACT' || field)) {
      change = action === 'RETRACT' ? { operation: 'RETRACT', object_type: obj.kind, object_id: obj.id } : { operation: 'CORRECT', object_type: obj.kind, object_id: obj.id, field: field!.id, from: obj.current[field!.id] ?? null, to: value };
    } else return;
    // One pending change per field; replacing it prevents accidental stale-from chains.
    setDraft(items => [...items.filter(m => m.object_id !== change.object_id || m.field !== change.field), change]);
    setDescription(''); clearSimulation();
  }
  async function run(proposed?: { mutations: GraphMutation[]; text: string }) {
    if (!scope) return;
    const result = await runSimulation({ mode: mode === 'event' ? 'graph_event' : 'graph', optionId: 'graph', originObjectId: 'graph', assumption: proposed?.text || description || 'Hypothetical case changes',
      graphVersion: scope.version, caseVersion: scope.caseVersion, ...(mode === 'event' ? { eventId: scenario?.request.eventId, eventHash: scenario?.request.eventHash } : { mutations: proposed?.mutations ?? draft }) });
    if (result) { setSelected(''); if (proposed) { setDraft(proposed.mutations); setDescription(proposed.text); } }
    setVersion('HYPOTHETICAL');
  }
  return <main className="p-page p-sim-page p-graph-sim">
    <header><div className="p-eyebrow">Simulate · {snapshot.caseRef.name}</div><h1>What changes in the case?</h1><p>Change evidence, assumptions or their connections. Follow the consequences through the current case.</p></header>
    {!scope ? <section className="p-sim-perimeter"><p role="status">{snapshot.graphSimulationUnavailable ?? 'This workspace has no connected graph simulation runtime.'}</p><button className="p-btn" disabled={busy} onClick={() => void refresh()}>Refresh current case</button></section> : <>
      <section className="p-sim-perimeter"><div className="p-section-heading"><strong>{scope.objects.length} current case items</strong><span>Basis: {scope.asOf}</span></div>
        <p>Each test runs on a separate copy. Current, Approved and recorded human views remain unchanged.</p>
        <details><summary>What this test can establish</summary>{scope.notes.map(note => <p key={note}>{note}</p>)}<p>Rewording a statement does not invent new reasoning. If the case lacks a rule for its consequences, the result shows that limit. Add or remove evidence connections through an existing evidence path.</p>
          {!!scope.coverageLimits.length && <pre>{JSON.stringify(scope.coverageLimits, null, 2)}</pre>}</details>
        <button className="p-related-link" disabled={busy} onClick={() => void refresh()}>Refresh current case</button>
      </section>
      <nav className="p-sim-modes" aria-label="Graph change type">{([['describe', 'Describe a change'], ['edit', 'Change an item or connection'], ['add', 'Add hypothetical evidence'], ['event', 'From an admitted event']] as const).map(([id, label]) => <button key={id} disabled={busy} aria-pressed={mode === id} onClick={() => changeMode(id)}>{label}</button>)}</nav>
      <section aria-label="Graph simulation setup">
        {mode === 'describe' && <SimulationTextInput snapshot={snapshot} disabled={busy} resetToken={textReset} onEditing={() => { clearSimulation(); setDraft([]); setDescription(''); }} onInspect={setSelected} onSimulate={(mutations, text) => run({ mutations, text })} />}
        {mode === 'edit' && <div className="p-sim-inputs">
          <label className="p-sim-field">Case item<select aria-label="Case item" value={obj?.id ?? ''} disabled={busy} onChange={e => setObjectId(e.target.value)}>{scope.objects.map(o => <option key={o.id} value={o.id}>{o.kindLabel} · {o.label}</option>)}</select></label>
          {obj && <button className="p-related-link" onClick={() => setSelected(obj.id)}>Inspect current item</button>}
          {obj && !obj.canRetract && !obj.fields.length ? <p>{obj.limitation}</p> : <label className="p-sim-field">Change<select aria-label="Change" value={action} disabled={busy} onChange={e => setAction(e.target.value)}>{obj?.canRetract && <option value="RETRACT">Withdraw this item</option>}{obj?.fields.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></label>}
          {field && <div className="p-graph-value"><p>Current: {field.control === 'references' ? (field.value as string[] | null)?.map(id => scope.objects.find(o => o.id === id)?.label ?? id).join(' · ') || 'No connections' : show(field.value)}</p>
            {field.control === 'references' ? <fieldset disabled={busy}><legend>Hypothetical connections</legend>{[...scope.objects.filter(o => o.kind === field.referenceKind && o.fields.length).map(o => ({ id: o.id, label: o.label })), ...draft.filter(m => m.operation === 'ADD' && m.object_type === field.referenceKind).map(m => ({ id: m.object_id, label: m.statement! }))].map(o => <label key={o.id}><input type="checkbox" checked={Array.isArray(value) && value.includes(o.id)} onChange={e => setValue(e.target.checked ? [...(Array.isArray(value) ? value : []), o.id] : (Array.isArray(value) ? value : []).filter(id => id !== o.id))} />{o.label}</label>)}</fieldset>
              : field.control === 'boolean' || field.control === 'choice' ? <label className="p-sim-field">Hypothetical value<select aria-label="Hypothetical field value" disabled={busy} value={String(value)} onChange={e => setValue(field.control === 'boolean' ? e.target.value === 'true' : e.target.value)}>{(field.control === 'boolean' ? ['true', 'false'] : field.choices ?? []).map(v => <option key={v} value={v}>{v === 'true' ? 'Usable' : v === 'false' ? 'Not usable' : v.replaceAll('_', ' ').toLowerCase()}</option>)}</select></label>
              : <label className="p-sim-field">Hypothetical value<input aria-label="Hypothetical field value" maxLength={4000} value={value === null ? '' : String(value)} disabled={busy} onChange={e => setValue(e.target.value)} /></label>}
          </div>}
          <button className="p-btn" disabled={busy || draft.length >= 50 || !(action === 'RETRACT' ? obj?.canRetract : field)} onClick={addChange}>Add to scenario</button>
        </div>}
        {mode === 'add' && <div className="p-sim-inputs"><label className="p-sim-field">Hypothetical evidence<textarea aria-label="Hypothetical evidence" value={statement} disabled={busy} maxLength={4000} onChange={e => setStatement(e.target.value)} /></label>
          <label className="p-sim-field">Effect on conclusion<select aria-label="Effect on conclusion" value={relation} disabled={busy} onChange={e => setRelation(e.target.value as typeof relation)}><option value="CONTRADICTS">Challenges</option><option value="SUPPORTS">Supports</option></select></label>
          <label className="p-sim-field">Conclusion<select aria-label="Conclusion" value={target?.id ?? ''} disabled={busy} onChange={e => setTargetId(e.target.value)}>{targets.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label>
          <p className="p-sim-reach">This is a hypothesis, with no attributed human author. Connect it to an evidence path as a further change when that path should use it.</p>
          <button className="p-btn" disabled={busy || !target || !statement.trim() || draft.length >= 50} onClick={addChange}>Add to scenario</button></div>}
        {mode === 'event' ? <div className="p-sim-event-setup"><h2>Scenarios prepared from admitted events</h2><p>The recorded event is tested against Current on load or refresh. An event already applied to Current may produce no further change.</p>
          {scenario ? <><label className="p-sim-field">Admitted event<select aria-label="Admitted graph event" value={scenario.id} disabled={busy} onChange={e => { setScenarioId(e.target.value); clearSimulation(); }}>{snapshot.graphSimulationScenarios?.map(s => <option key={s.id} value={s.id}>{s.graph?.event.label ?? s.graph?.event.event}</option>)}</select></label><EventDetails report={scenario.graph!} /></> : <p>No executable admitted event is available.</p>}
          {snapshot.graphSimulationEventLimits?.map(e => <p key={e.eventId}>{e.label}: {e.reason}</p>)}
        </div> : mode !== 'describe' ? <section className="p-graph-draft" aria-label="Scenario changes"><h2>Your scenario · {draft.length} {draft.length === 1 ? 'change' : 'changes'}</h2>{!draft.length && <p>Add a change to begin. You can combine several changes in one test.</p>}{draft.map((m, index) => <div key={m.object_id + m.field}><button className="p-unboxed-select" onClick={() => setSelected(m.object_id)}>{m.statement ?? scope.objects.find(o => o.id === m.object_id)?.label ?? m.object_id}</button><span>{mutationLabel(m, scope.objects, draft)}</span><button className="p-related-link" disabled={busy} aria-label={'Remove change ' + (index + 1)} onClick={() => { setDraft(items => items.filter((_, i) => i !== index)); setDescription(''); clearSimulation(); }}>Remove</button></div>)}</section> : null}
        <div className="p-action-row">{mode !== 'describe' && <button className="p-btn p-btn-primary" disabled={busy || (mode === 'event' ? !scenario : !draft.length)} onClick={() => void run()}>{simulationRunning ? 'Tracing consequences…' : mode === 'event' ? 'Inspect event consequences' : 'Simulate case changes'}</button>}<button className="p-btn" disabled={busy || (!draft.length && !report)} onClick={() => { setDraft([]); setSelected(''); setDescription(''); setTextReset(value => value + 1); clearSimulation(); }}>Reset scenario</button></div>
      </section>
      {report && <section className="p-graph-results" aria-label="Graph simulation results" aria-live="polite">
        <div className="p-section-heading"><h2>{report.counts.changed} changed · {report.counts.held} held</h2><span>{report.counts.examined} examined · {report.counts.unavailable} unresolved</span></div>
        <p>Support compares an evaluation of Current with this hypothetical. “Held” means an examined item has no resulting change; it does not mean that every possible consequence is known.</p>
        <nav className="p-sim-modes" aria-label="Graph comparison">{(['CURRENT', 'HYPOTHETICAL'] as const).map(v => <button key={v} aria-pressed={version === v} onClick={() => setVersion(v)}>{v === 'CURRENT' ? 'Current connections' : 'Hypothetical connections'}</button>)}</nav>
        <PropagationGraph report={report} version={version} selected={selected} inspect={setSelected} />
        <div className="p-sim-numbers"><table><caption>Changes and surviving support</caption><thead><tr><th>Case item</th><th>Result</th><th>Current → hypothetical</th></tr></thead><tbody>{report.rows.map(row => <tr key={row.id}><td><button className="p-unboxed-select" onClick={() => setSelected(row.id)}>{row.label}</button><small>{row.kindLabel}{row.isOrigin ? ' · changed directly' : ''}</small></td><td>{row.status === 'CHANGED' ? row.unresolved ? 'Changed · unresolved' : 'Changed' : row.status === 'HELD' ? 'Held' : 'Unresolved'}</td><td>{row.changes.length ? row.changes.map(c => <div key={c.field}><strong>{fieldName(c.field)}: </strong>{c.field === 'support_result' ? support(String(c.before)) + ' → ' + support(String(c.after)) : c.field === 'runtime_state' ? availability(c.before) + ' → ' + availability(c.after) : displayValue(c.before, report.labels) + ' → ' + displayValue(c.after, report.labels)}</div>) : row.afterSupport ? support(row.beforeSupport) + ' → ' + support(row.afterSupport) : row.reasons.join(' ') || 'No stored change.'}</td></tr>)}</tbody></table></div>
        {!!report.issues.length && <section className="p-sim-stops"><h2>Where review or further evidence is needed</h2>{report.issues.map((issue, index) => <div key={index}><h3>{issue.category}</h3><p>{issue.reason}</p>{issue.objectIds.filter(id => report.labels[id]).map(id => <button key={id} className="p-related-link" onClick={() => setSelected(id)}>{report.labels[id]}</button>)}<details><summary>Recorded reason and required action</summary><pre>{JSON.stringify(issue.raw, null, 2)}</pre></details></div>)}</section>}
        <details><summary>Scenario basis and complete transition record</summary><EventDetails report={report} /><p>Hypothesis: {simulationResult?.request.assumption}</p><p>Scenario: {simulationResult?.id}</p><p>Case version: {scope.caseVersion}. Engine: {report.engineVersion}.</p><pre>{JSON.stringify(report.engineResult, null, 2)}</pre></details>
        <p className="p-impact-human">The live case and the investment decision remain unchanged.</p>
      </section>}
      {selected && <ItemInspection key={selected} id={selected} report={report} objects={scope.objects} draft={draft} close={() => setSelected('')} />}
    </>}
  </main>;
}

function availability(value: unknown) { const flags = value as Record<string, unknown> | null; return flags?.lifecycle === 'RETRACTED' ? 'Withdrawn' : !flags || !Object.keys(flags).length ? 'Available' : 'Availability updated'; }
function displayValue(value: unknown, labels: Record<string, string>) { return Array.isArray(value) ? value.map(v => labels[String(v)] ?? show(v)).join(' · ') || 'No connections' : show(value); }
function mutationLabel(m: GraphMutation, objects: GraphSimulationObject[], draft: GraphMutation[]) {
  const labels = Object.fromEntries([...objects.map(o => [o.id, o.label]), ...draft.filter(d => d.operation === 'ADD').map(d => [d.object_id, d.statement])]);
  return m.operation === 'RETRACT' ? 'Withdraw this item' : m.operation === 'ADD' ? (m.relation_type === 'CONTRADICTS' ? 'Challenges ' : 'Supports ') + labels[m.target_position_id!] : fieldName(m.field!) + ': ' + displayValue(m.to, labels);
}
function EventDetails({ report }: { report: GraphSimulationReport }) { return <details><summary>Event evidence and timing</summary><p>{report.event.label ?? report.event.event}</p><p>Effective: {report.event.effective_date} · Known: {report.event.known_at}</p><p>Sources: {report.event.source_ids.join(', ')}</p><pre>{JSON.stringify(report.event, null, 2)}</pre></details>; }

function ItemInspection({ id, report, objects, draft, close }: { id: string; report?: GraphSimulationReport; objects: GraphSimulationObject[]; draft: GraphMutation[]; close: () => void }) {
  const row = report?.rows.find(r => r.id === id), obj = objects.find(o => o.id === id), added = draft.find(m => m.object_id === id && m.operation === 'ADD');
  return <aside className="p-graph-inspection" aria-label="Simulation item inspection"><div className="p-section-heading"><h2>{row?.label ?? obj?.label ?? added?.statement ?? id}</h2><button className="p-btn" onClick={close}>Close inspection</button></div><p>{row?.kindLabel ?? obj?.kindLabel ?? 'Hypothetical evidence'}</p>
    {row && <><p>Current support: {support(row.beforeSupport)}. Hypothetical support: {support(row.afterSupport)}.</p>{row.reasons.map((r, i) => <p key={i}>{r}</p>)}</>}
    <div className="p-graph-inspection-columns"><section><h3>Current</h3><p>{show((row?.before ?? obj?.current)?.statement ?? (row?.before ?? obj?.current)?.value ?? obj?.label)}</p><p>{availability(obj?.currentFlags)}</p><details><summary>Stored object and provenance</summary><pre>{JSON.stringify(row?.before ?? obj?.current ?? null, null, 2)}</pre>{obj && <pre>{JSON.stringify(obj.currentFlags, null, 2)}</pre>}</details></section><section><h3>{report ? 'Hypothetical' : 'Pending changes'}</h3><p>{show(row?.after?.statement ?? row?.after?.value ?? added?.statement ?? obj?.label)}</p>{row?.changes.map(c => <p key={c.field}>{fieldName(c.field)}: {c.field === 'runtime_state' ? availability(c.after) : c.field === 'support_result' ? support(String(c.after)) : displayValue(c.after, report?.labels ?? {})}</p>)}<details><summary>Stored object and changes</summary><pre>{JSON.stringify(row?.after ?? (report ? obj?.current : draft.filter(m => m.object_id === id)) ?? null, null, 2)}</pre></details></section></div>
    {report && <><h3>Actual evidence connections</h3>{report.edges.filter(e => e.target === id || e.source === id).map(e => <p key={e.version + e.id + e.source + e.target}>{e.version === 'CURRENT' ? 'Current' : 'Hypothetical'}: {report.labels[e.source]} → {e.label} → {report.labels[e.target]}</p>)}<details><summary>Support calculation and provenance</summary><pre>{JSON.stringify({ changes: row?.changes, reachedVia: row?.reachedVia, routes: report.engineResult.transition_output.route_results, support: report.engineResult.transition_output.support_combination_results }, null, 2)}</pre></details></>}
  </aside>;
}

function PropagationGraph({ report, version, selected, inspect }: { report: GraphSimulationReport; version: 'CURRENT' | 'HYPOTHETICAL'; selected: string; inspect: (id: string) => void }) {
  const edges = report.edges.filter(e => e.version === version);
  const ids = [...new Set([...report.rows.map(r => r.id), ...edges.flatMap(e => [e.source, e.target])])];
  const depths = new Map(ids.map(id => [id, 0]));
  // Bounded layout only: runtime edges and effects remain authoritative, including cycles.
  for (let i = 0; i < Math.min(ids.length, 5); i++) for (const e of edges) if (e.source !== e.target && !report.rows.find(r => r.id === e.target)?.isOrigin) depths.set(e.target, Math.min(4, Math.max(depths.get(e.target)!, depths.get(e.source)! + 1)));
  const columns = new Map<number, string[]>();
  for (const id of ids) { const depth = depths.get(id)!; columns.set(depth, [...(columns.get(depth) ?? []), id]); }
  const positions = new Map(ids.map(id => [id, { x: 12 + depths.get(id)! * 230, y: 14 + columns.get(depths.get(id)!)!.indexOf(id) * 102 }]));
  const width = (Math.max(0, ...columns.keys()) + 1) * 230, height = Math.max(1, ...[...columns.values()].map(c => c.length)) * 102 + 20;
  return <div className="p-graph-canvas" aria-label="Propagation through actual case connections"><svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}><defs><marker id="simulation-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
    {edges.map(e => { const a = positions.get(e.source)!, b = positions.get(e.target)!; return <path key={e.id + e.source + e.target} d={`M ${a.x + 198} ${a.y + 36} C ${a.x + 215} ${a.y + 36}, ${b.x - 20} ${b.y + 36}, ${b.x - 3} ${b.y + 36}`} fill="none" stroke="currentColor" opacity=".3" markerEnd="url(#simulation-arrow)"><title>{report.labels[e.source]} {e.label} {report.labels[e.target]}</title></path>; })}
    {ids.map(id => { const pos = positions.get(id)!, row = report.rows.find(r => r.id === id); return <foreignObject key={id} x={pos.x} y={pos.y} width="198" height="84"><button className={'p-graph-node ' + (row?.status ?? 'WITNESS')} aria-pressed={selected === id} onClick={() => inspect(id)}><small>{row?.isOrigin ? 'Changed directly' : row?.status === 'CHANGED' ? row.unresolved ? 'Changed · unresolved' : 'Changed' : row?.status === 'HELD' ? 'Held' : row?.status === 'UNAVAILABLE' ? 'Unresolved' : 'Supporting context'}</small><span>{report.labels[id]}</span></button></foreignObject>; })}
  </svg><p>Lines show declared case relationships. Select an item to inspect both states and its evidence paths.</p></div>;
}
